"""
Thin wrapper around the `claude -p` CLI (OAuth subscription, not a metered API key).

Adversary-verified invocation: skip MCP init + feed the prompt via stdin so the CLI
never blocks on an empty stdin. Takes a naive 10-19s cold call down to ~4s.

Kept deliberately swappable: the whole app calls ask(); phase-2 voice reuses this
unchanged (STT -> ask() -> TTS).
"""
from __future__ import annotations
import json
import subprocess
from typing import Optional

CLAUDE_BIN = "/usr/bin/claude"

# Skip all MCP servers (slack/codebase-memory load on every call otherwise and ~2x latency).
_BASE_ARGS = [
    CLAUDE_BIN,
    "--strict-mcp-config",
    "--mcp-config", '{"mcpServers":{}}',
    "--output-format", "json",
    "-p",
]


class LlmError(Exception):
    pass


def ask(prompt: str, *, timeout: int = 45) -> str:
    """Run one grounded prompt through `claude -p`, return the model's text.

    Raises LlmError on non-zero exit / timeout / unparseable output so callers can
    serve a fallback reply instead of showing an error on stage.
    """
    try:
        proc = subprocess.run(
            _BASE_ARGS,
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
