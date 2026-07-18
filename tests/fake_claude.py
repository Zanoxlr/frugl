#!/usr/bin/env python3
"""A stand-in for `claude -p --output-format stream-json`, driven by FAKE_MODE, so the
async streaming transport (framing, timeout, stderr-drain, non-zero exit, kill) can be
tested hermetically. Emits the same NDJSON event shapes the real CLI does.

Modes: normal | hang | nonzero_mid | big_stderr
"""
import json
import os
import sys
import time

mode = os.environ.get("FAKE_MODE", "normal")

# Drain stdin (the prompt) so the caller's stdin write/drain completes.
sys.stdin.buffer.read()


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def delta(text, kind="text_delta"):
    emit({"type": "stream_event", "event": {"type": "content_block_delta",
                                            "delta": {"type": kind, "text": text}}})


if mode == "big_stderr":
    sys.stderr.write("x" * 200000)  # would deadlock if the caller PIPEd + didn't drain stderr
    sys.stderr.flush()

# Init + non-text noise the stream parser must ignore.
emit({"type": "system", "subtype": "init"})
delta("NOISE", kind="thinking_delta")

if mode == "hang":
    delta("zacetek ")
    time.sleep(30)  # caller's wall-clock timeout must kill us
    sys.exit(0)

delta("pozdravljen ")
delta("Marko")

if mode == "nonzero_mid":
    sys.exit(1)  # exit non-zero after streaming some tokens

emit({"type": "result", "subtype": "success", "is_error": False, "result": "pozdravljen Marko"})
sys.exit(0)
