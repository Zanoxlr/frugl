# Phase 2: Voice Talk-Agent Roadmap

Research + design doc. No build. Goal: let a user speak to the Frugl advisor and get a
spoken, conversational answer back, running on THIS VPS with minimal new infrastructure.

Author's note on scope: phase 1 is a text app (`POST /chat` -> `claude -p` -> text). Phase 2
wraps that same brain in a voice loop. Nothing about the advisor logic, grounding, or the
`claude -p` invocation changes. We add a mic on the front and a speaker on the back.

---

## 0. TL;DR

- **Recommended architecture: turn-based pipeline (option a), but built on the streaming STT
  WebSocket that already exists**, plus streamed LLM output and per-sentence TTS. This reuses
  every VPS asset, needs no new metered account beyond the STT the VPS already pays for, and is
  buildable in a day or two.
- **Realistic per-turn latency: ~5 to 9 seconds** from the moment the user stops talking to the
  first spoken word back, dominated by `claude -p` (4 to 9s). With filler audio and streamed TTS
  the *perceived* wait drops to ~1 to 2s because the user hears something almost immediately.
- **VPS services usability:**
  - TTS (`:47850`, Edge TTS) is **usable as-is** for Slovenian. Good voices, ~2s to synthesize a
    short reply. One-line API. Only gap: it does not stream, so we either accept the 2s or add a
    small streaming endpoint.
  - Transcription (`:47823`, Speechmatics) is **usable, but only via the right endpoints.** The
    realtime WebSocket (`/transcribe/realtime`) and the `/upload` path force a single language and
    work fine. The batch `/transcribe` and `/transcribe/file` endpoints still use the two-language
    auto-detect config that gets jobs rejected, so **do not** use those two for voice. Use the
    WebSocket.

---

## 1. What is actually on the VPS (verified 2026-07-18)

### 1.1 TTS server, `http://localhost:47850` (Tailscale `http://100.100.35.101:47850`)

Real and running (`tts-server.service`, source `/home/claude/tts-server/server.py`). It wraps
Microsoft Edge TTS (`edge_tts`), which synthesizes against Microsoft's public neural-voice
endpoint. Free, not a metered API key, but it does depend on Microsoft's servers being reachable.

API:

- `POST /generate` with `{"text": "...", "voice": "...", "speed": 1.0}` -> JSON
  `{"id","voice","speed","chars","url"}`. It synthesizes the **whole** clip to an MP3 on disk, then
  returns. It does not stream.
- `GET /listen/<id>` -> raw `audio/mpeg` stream of that clip (this is what an `<audio>` tag plays).
- `GET /play/<id>` -> a full HTML player page (not needed for the app).
- `GET /voices`, `GET /health`.

Language: if `voice` is omitted, a marker-word heuristic picks Slovenian vs English (needs >=2 SL
marker words to choose SL). For the advisor we should **pass the voice explicitly** rather than
trust auto-detect, because short replies may not trip the heuristic.

Slovenian voices available: `sl-SI-RokNeural` (male) and `sl-SI-PetraNeural` (female), both tagged
"Friendly, Positive". Default SL voice in the server is Rok.

Measured latency: `POST /generate` for a 53-char Slovenian sentence took **2.1s wall** and produced
**4.5s of audio**. That 2.1s is fixed synthesis-then-save overhead; it grows roughly with reply
length. This is the number that matters for the latency budget.

### 1.2 Transcription server, `http://localhost:47823`

Real and running (`transcription-api.service`, source `/root/transcription-api/app.py`, v3.0.0,
Speechmatics-backed). Speechmatics is a **metered external API** (key in the service `.env`). There
is no subscription alternative for cloud STT, so this is the one place the "use the subscription,
not metered APIs" rule cannot apply unless we go local (see 1.3).

The known two-language bug is **half-fixed** in this version, and that shapes which endpoints we use:

- `_build_job_config()` only attaches `LanguageIdentificationConfig(expected_languages=["sl","en"])`
  when `language == "auto"`. That two-language auto config is the one the earlier memory note says
  gets rejected.
- `POST /transcribe` (URL) and `POST /transcribe/file` (upload) both call it with the default
  `auto` -> **still on the buggy two-language path. Avoid for voice.**
- `POST /upload` (the HTML form path) calls `_transcribe_path(target)` which defaults to
  `language="sl"` -> single language -> works.
- **`WS /transcribe/realtime`** takes `{"command":"start","language":"en"|"sl"}`, forces a single
  language, streams PCM16 16 kHz mono up, and pushes back `partial` / `final` / `ready` / `error`
  JSON events with `enable_partials=True, max_delay=1.0`. This is a real, working, low-latency
  streaming STT relay and it is the asset that makes good voice UX possible here.

So: the VPS already has streaming Slovenian STT. We just have to point at the WebSocket, not the
batch endpoints, and we have to know the language up front (or default to `sl` and offer an EN
toggle) because the realtime relay does not auto-detect.

### 1.3 Local Whisper as an STT alternative

`faster-whisper` 1.2.1 is installed in the transcription venv. The box is **CPU-only** (AMD EPYC,
8 vCPU, no GPU). Consequences for Slovenian voice:

- Slovenian is a lower-resource language for Whisper. Only `large-v3` is genuinely good on SL;
  `small`/`medium` degrade noticeably on inflected Slovenian and on colloquial no-sumniki speech.
- `large-v3` on 8 CPU cores runs well below realtime (roughly 5 to 10x the audio duration for a
  cold-ish transcribe), which kills conversational latency. `medium int8` is ~1 to 2x realtime but
  weaker on SL.
- Whisper has no built-in streaming; you chunk with a VAD and stitch, which is real work.

**Verdict:** local Whisper is not the low-latency Slovenian path on this hardware. Keep the
Speechmatics realtime WebSocket as primary. Local Whisper is only worth it as an **offline / cost /
privacy fallback** (batch transcription with `large-v3` when latency does not matter), or later if a
GPU box (the render server on Contabo) is in play. Note it as a fallback, do not build on it.

---

## 2. Architecture options

### (a) Turn-based pipeline (RECOMMENDED)

```
browser mic ──PCM16 16k──▶ STT (Speechmatics RT WS :47823)
                                     │ final transcript
                                     ▼
                             POST /chat (existing)  ──▶ claude -p  (~4-9s)
                                     │ text reply (streamed sentence by sentence)
                                     ▼
                             TTS (:47850)  ──▶ MP3
                                     │
browser <audio> ◀────────────────────┘   playback
```

One turn: user talks, we detect end of speech, we already have the transcript (STT ran live while
they spoke), we call the existing `/chat`, we synthesize the reply, we play it. Simple, reuses
everything, no realtime audio model to run.

**Why this wins here:** the advisor brain is a subprocess call (`claude -p`), not a low-latency
model we can stream tokens into a voice model. Turn-based is the natural fit, and the VPS already
has both ends (streaming STT + fast TTS). It is also the honest UX for a *grounded* advisor: the
user says a full thought, the AI answers a full thought.

**Latency:** see section 3. Naive sequential is ~7 to 10s; with the three hiding tricks it *feels*
like ~1 to 2s.

### (b) Streaming / realtime with barge-in

Full-duplex: continuous partial transcripts, the AI can start answering before the user fully
stops, and the user can interrupt the AI mid-sentence ("barge-in"), which stops playback and
re-opens the mic. This is what makes hosted voice agents feel human.

What it would take on top of (a):

- **Endpointing / turn detection** instead of a simple "user pressed stop" or fixed silence
  timeout. You need a VAD that decides "they finished a thought" fast and accurately. The RT WS
  gives partials; you still need the turn-taking policy on top.
- **Barge-in:** detect user speech energy during playback, immediately pause the `<audio>`, flush
  the pending TTS queue, and treat the new utterance as the next turn. Requires mic stays open
  during playback and echo handling so the AI does not transcribe its own voice (acoustic echo
  cancellation, or headphones, or a push-to-talk compromise).
- **Streaming everything:** `claude -p --output-format stream-json` so tokens arrive incrementally,
  chunk the text at sentence boundaries, and pipe each sentence to TTS as it completes so audio
  starts before the full reply exists. The current TTS server does not stream a single clip, so
  you either synthesize per sentence (already helps a lot) or add a chunked endpoint using
  `edge_tts`'s native `Communicate.stream()`.
- **Interruptible playback state machine** on the client, plus a way to cancel an in-flight
  `claude -p` if the user barges in with a correction.

This is a meaningfully bigger build (echo cancellation and turn-taking are the hard parts) and it
is an "ocean," not a "lake." Recommendation: **do (a) first, add barge-in as a fast-follow** once
the turn-based loop is proven, since per-sentence streamed TTS from (a) is 80% of the felt benefit.

### (c) Hosted realtime voice API (e.g. OpenAI Realtime, Gemini Live, ElevenLabs Conversational)

These give barge-in, sub-second latency, and one integration instead of three. Why we would *not*
lead with one:

- **Metered, and against the team rule.** The advisor's whole cost model is "LLM via the `claude`
  subscription, not a per-token API." A hosted voice API is billed per audio minute on top, and it
  replaces `claude -p` with a different, metered model, so we would lose the grounded-advisor
  behavior we already tuned and pay for the privilege.
- **Slovenian quality is uneven** across these providers and hard to guarantee; the VPS Speechmatics
  path is already tuned for SL, and Edge TTS SL voices are solid.
- **Grounding / control.** Our value is the strict "answer only from DATA, no hallucinated prices"
  system prompt. Handing the conversation to a hosted voice model weakens that control.

When it *would* make sense: if barge-in and sub-second latency become the product (a true phone-like
agent) and the subscription-only constraint is relaxed. Worth a spike then, not now. If we ever want
hosted quality without abandoning `claude -p`, the middle path is: keep `claude -p` as the brain and
only rent a hosted STT+TTS with barge-in, not a full realtime LLM.

---

## 3. Latency budget

Where the seconds go in one turn (option a), from "user stops talking" to "first audio out":

| Stage | Time | Notes |
|---|---|---|
| Endpoint detection (silence) | 0.3 - 0.8s | fixed silence window; tune shorter for snappier feel |
| STT finalize | ~0.5 - 1.0s | Speechmatics RT `max_delay=1.0`; partials already streamed live, so only the tail costs time |
| **`claude -p`** | **4 - 9s** | the dominant cost; ~4s warmed with empty MCP + `--output-format json`, up to 9s cold or on long context |
| TTS synth (short reply) | ~2 - 3s | measured 2.1s for a 53-char SL sentence; scales with length |
| Network / playback start | <0.2s | negligible on tailnet / local |
| **Total, naive sequential** | **~7 - 10s** | too slow if done blindly |

### Hiding the seconds

The LLM is the wall. Three tricks turn a 7 to 10s real wait into a ~1 to 2s *perceived* wait:

1. **Filler audio, instantly.** The moment we have the final transcript, before `claude -p` returns,
   play a short pre-synthesized SL filler ("mhm, samo trenutek", "ok, poglejmo"). Pre-generate a
   handful of these MP3s once and cache them; playback starts in <200ms. This alone removes the
   dead-air problem.
2. **Stream the LLM, synthesize per sentence.** Run `claude -p --output-format stream-json`, split
   the incoming text at sentence boundaries, and fire the first sentence to TTS as soon as it lands.
   The user hears real content after roughly `first-sentence-of-LLM (~2 to 4s) + TTS (~1.5s)`
   instead of waiting for the whole reply. Queue the rest of the sentences behind it.
3. **Keep replies short.** The advisor system prompt already mandates short, one-thought SMS-style
   answers. That is not just a UX choice, it directly caps TTS time. Enforce it (the prompt already
   says "ena misel na sporocilo, ne stena teksta").

Also keep the `claude -p` process warm and the MCP config empty (`--strict-mcp-config --mcp-config
'{"mcpServers":{}}'`), exactly as phase 1 already does, since that is what pulls the LLM from 10 to
19s down to ~4s.

---

## 4. Slovenian-specific notes

### STT (speech in)

- Use the Speechmatics **realtime WebSocket with `language: "sl"`**. It is enhanced-model Slovenian
  and works today. Do not use the batch endpoints (two-language auto -> rejected).
- The relay does not auto-detect language. Default to `sl`, expose a small EN toggle for
  English-speaking users. Do not try to run both at once, that is the original bug.
- Expect some errors on very colloquial or code-switched speech (SL sentence with English brand and
  package names like "Arena", "T-2 KING", "GB"). Speechmatics handles proper nouns reasonably, but
  plan for the advisor to tolerate slightly noisy transcripts (it already reasons over intent, not
  exact strings).

### TTS (speech out)

- Edge TTS SL voices (`sl-SI-RokNeural`, `sl-SI-PetraNeural`) are natural and pleasant. Pick one as
  the advisor's voice and keep it consistent (a consistent voice is part of the product's
  personality). Rok is the current default; Petra is a fine alternative.
- **The no-sumniki rule cuts the other way for TTS.** The advisor writes Slovenian *without*
  sumniki (`cas` not `cas`, `se` not `se`, `ze` not `ze`) for the chat UI and to not look like AI.
  But Edge TTS pronounces based on spelling: feeding it de-sumnik'd text can mispronounce words
  (`se` for "se" vs "se", `cas`, `prihranis`). **For the TTS path we should send the *correctly
  accented* Slovenian text**, not the no-sumniki version shown on screen. Practically this means the
  advisor produces (or we keep) a properly-accented copy of the reply for synthesis while the
  on-screen bubble stays no-sumniki. Simplest implementation: ask `claude -p` for the reply *with*
  sumniki and strip them for display, rather than the reverse. This is the single most important
  Slovenian voice-quality detail in this doc.
- Numbers, prices, and units: Edge TTS reads "8 EUR" and "34,90" acceptably in SL, but verify a few
  price read-outs during the demo since the advisor quotes prices verbatim.

---

## 5. Minimal phase-2 build (smallest thing that demos)

Goal: a mic button on the existing chat screen that records, transcribes, calls the **existing**
`/chat`, and plays the reply. Everything the phase-1 plan builds is reused unchanged.

**Reuse as-is:** the whole phase-1 backend (`POST /chat`, grounding, `claude -p` invocation), the
frontend chat screen, the TTS server, the Speechmatics realtime WS. New code is thin glue.

### Smallest version (v2.0, "walkie-talkie")

Push-to-talk, no streaming, prove the loop end to end:

1. **Frontend:** add a mic button. On press, `getUserMedia`, record with `MediaRecorder`. On
   release, we have an audio blob.
2. **STT:** open the Speechmatics realtime WS during recording, stream PCM16 16 kHz mono, collect
   `final` events into the transcript. (Slightly more work than a batch POST, but it is the endpoint
   that actually works, and it gives live partials for free, which look great on stage.) Default
   `language: "sl"`.
3. **Chat:** send the final transcript to the **existing** `POST /chat` with the current vertical
   and history. No change to the backend.
4. **TTS:** take the text reply, `POST /generate` to `:47850` with `voice: "sl-SI-RokNeural"`, get
   back an `id`, set an `<audio src="/listen/<id>">` and play it. Show the text bubble at the same
   time.
5. **Fallback:** if STT or TTS fails, fall back to the existing text chat (type instead of talk).
   Never show a hard error on stage, mirror the phase-1 stance.

That is the entire minimum. It is a few hundred lines of frontend glue plus a tiny STT-WS proxy if
we do not want the browser holding the Speechmatics key (we should proxy through our backend so the
key stays server-side; the VPS WS already sits on our backend host, so point the browser at
`:47823`'s WS on the tailnet, or add a thin pass-through route in our FastAPI).

### First upgrade (v2.1, "feels fast")

Add the two cheap latency hides once the loop works:

- Pre-generate ~5 SL filler clips, play one instantly on transcript-final.
- Switch `/chat` to `claude -p --output-format stream-json`, split at sentence boundaries, and TTS
  sentence by sentence so audio starts on the first sentence.

### Later (v2.2, optional, "barge-in")

Only if the product wants phone-like duplex: keep the mic open during playback, add VAD-based
barge-in that stops audio and cancels the in-flight `claude -p`, add echo handling (headphones or
AEC). This is the option-b work and is a separate, larger effort.

---

## 6. Open questions / risks to flag

- **Microphone over HTTP:** `getUserMedia` requires a secure context. The app must be served over
  HTTPS or `localhost` (the tailnet IP over plain HTTP will be blocked by browsers for mic access).
  Confirm how the demo is served (tailnet + a TLS cert, or a tunnel).
- **Speechmatics key exposure:** do not put the STT key in the browser. Proxy the WS through our
  backend, or rely on the existing `:47823` service which already holds the key server-side and only
  exposes the relay.
- **Edge TTS dependency:** it hits Microsoft's endpoint. If that is flaky or blocked, TTS fails.
  Cache filler clips locally and keep the text-only fallback.
- **Cost:** Speechmatics is metered per audio minute. A voice demo with a few users is cheap, but a
  public B2C launch needs a cost model (or the local-Whisper fallback on a GPU box). `claude -p`
  stays on the subscription. Edge TTS is free.
- **No-sumniki vs TTS pronunciation:** resolve the accented-text-for-TTS approach (section 4) early,
  it affects how `/chat` returns text.

---

## 7. One-paragraph recommendation

Build the turn-based pipeline (option a) on top of the two services the VPS already runs: the
Speechmatics **realtime WebSocket** for streaming Slovenian STT (not the batch endpoints, which are
still on the broken two-language path) and the Edge TTS server for Slovenian speech out. Keep the
phase-1 `claude -p` advisor exactly as is. Expect ~5 to 9s of real per-turn latency dominated by the
LLM, and hide it with an instant filler clip plus per-sentence streamed TTS so it feels like ~1 to
2s. Send correctly-accented Slovenian into TTS even though the screen shows the no-sumniki version.
Skip hosted realtime voice APIs for now (metered, weaker SL control, breaks the subscription-only
rule); revisit only if true barge-in becomes the product.
