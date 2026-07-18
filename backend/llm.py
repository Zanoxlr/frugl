"""
Thin wrapper around the `claude -p` CLI (OAuth subscription, not a metered API key).

Adversary-verified invocation: skip MCP init + feed the prompt via stdin so the CLI
never blocks on an empty stdin. Takes a naive 10-19s cold call down to ~4s.

Kept deliberately swappable: the whole app calls ask(); phase-2 voice reuses this
unchanged (STT -> ask() -> TTS).
"""
from __future__ import annotations
import asyncio
import json
import os
import signal
import subprocess
from typing import AsyncIterator, Optional

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/usr/bin/claude")

_MCP_OFF = ["--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']

# Skip all MCP servers (slack/codebase-memory load on every call otherwise and ~2x latency).
_BASE_ARGS = [CLAUDE_BIN, *_MCP_OFF, "--output-format", "json", "-p"]

# Streaming: emit token deltas as they arrive. --verbose is required for stream-json;
# its noise goes to stderr, which we discard.
_STREAM_ARGS = [
    CLAUDE_BIN, *_MCP_OFF,
    "--output-format", "stream-json",
    "--include-partial-messages",
    "--verbose",
    "-p",
]


class LlmError(Exception):
    pass


def _with_model(args, model):
    """Insert `--model <alias>` before the trailing -p, if a model is pinned."""
    if not model:
        return list(args)
    out = list(args)
    out[-1:-1] = ["--model", model]
    return out


def ask(prompt: str, *, timeout: int = 45, model: Optional[str] = None) -> str:
    """Run one grounded prompt through `claude -p`, return the model's text.

    Raises LlmError on non-zero exit / timeout / unparseable output so callers can
    serve a fallback reply instead of showing an error on stage.
    """
    try:
        proc = subprocess.run(
            _with_model(_BASE_ARGS, model),
            input=prompt,            # prompt via stdin: no ARG_MAX limit, no empty-stdin wait
            capture_output=True,     # stdout only into .stdout; stderr stays separate (MCP/warn noise)
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise LlmError(f"claude -p timed out after {timeout}s") from e

    if proc.returncode != 0:
        raise LlmError(f"claude -p exited {proc.returncode}: {proc.stderr[:400]}")

    # --output-format json returns an envelope; the reply text is in "result".
    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise LlmError(f"unparseable stdout: {proc.stdout[:400]}") from e

    text = env.get("result")
    if not text:
        raise LlmError(f"no result field in envelope: {proc.stdout[:400]}")
    return text.strip()


def ask_safe(prompt: str, fallback: str, *, timeout: int = 45) -> tuple[str, Optional[str]]:
    """ask() but never raises: returns (text, error). On failure text=fallback."""
    try:
        return ask(prompt, timeout=timeout), None
    except LlmError as e:
        return fallback, str(e)


async def stream(prompt: str, *, timeout: int = 45, model: Optional[str] = None) -> AsyncIterator[str]:
    """Async-stream a grounded prompt through `claude -p`, yielding text deltas as
    they arrive. `model` pins a tier ('haiku'/'sonnet'/'opus'); None = CLI default.
    Raises LlmError on timeout / non-zero exit / result error so callers can emit a
    fallback. Cleans up the whole process group on any exit (incl. the consumer
    abandoning the generator on client disconnect).
    """
    proc = await asyncio.create_subprocess_exec(
        *_with_model(_STREAM_ARGS, model),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,   # --verbose noise; draining a PIPE would deadlock
        start_new_session=True,              # own process group so killpg reaps node children
    )

    async def _feed():
        try:
            proc.stdin.write(prompt.encode())
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    feeder = asyncio.create_task(_feed())  # write concurrently: no stdin/stdout deadlock

    buf = b""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    saw_error = False
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise LlmError("claude -p stream timed out after %ss" % timeout)
            try:
                chunk = await asyncio.wait_for(proc.stdout.read(65536), timeout=remaining)
            except asyncio.TimeoutError:
                raise LlmError("claude -p stream timed out after %ss" % timeout)
            if not chunk:
                break  # EOF
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    evt = json.loads(raw)
                except json.JSONDecodeError:
                    continue  # partial/non-JSON line; skip
                etype = evt.get("type")
                if etype == "stream_event":
                    ev = evt.get("event", {})
                    if ev.get("type") == "content_block_delta":
                        delta = ev.get("delta", {})
                        # ONLY text deltas — never thinking/tool/init events.
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            yield delta["text"]
                elif etype == "result" and evt.get("is_error"):
                    saw_error = True
    finally:
        feeder.cancel()
        if proc.returncode is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass

    if saw_error:
        raise LlmError("claude -p reported a result error")
    if proc.returncode not in (0, None):
        raise LlmError("claude -p exited %s" % proc.returncode)


if __name__ == "__main__":
    import time
    demo_data = (
        'DATA (telco add-ons, T2 operator):\n'
        '- T2 KING tier: VOYO = FREE (included), HBO Premium = FREE, CineStar Premiere = FREE\n'
        '- T2 OPTIMUM tier: VOYO = PAID, HBO Premium = PAID, CineStar Premiere = PAID\n'
    )
    system = (
        "Si svetovalec za telekom pakete. Odgovarjaj SAMO iz DATA. "
        "Ce podatka ni, reci da ga nimas. Pisi po slovensko brez sumnikov, na kratko.\n\n"
    )
    q = "je HBO na paketu T2 KING zastonj ali doplacam?"
    prompt = system + demo_data + "\nVprasanje: " + q
    t = time.time()
    try:
        out = ask(prompt)
        print(f"[{time.time()-t:.1f}s] OK\n{out}")
    except LlmError as e:
        print(f"[{time.time()-t:.1f}s] FAIL: {e}")
