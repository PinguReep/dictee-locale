# Local Wispr Flow Clone — Research & Build Plan

Goal: a fully local, system-wide dictation app for Windows 11 that does what Wispr
Flow does — hold a hotkey, speak, release, and clean formatted text appears in
whatever app has focus.

## 1. How Wispr Flow actually works

Wispr Flow is not "just Whisper." It's a two-stage pipeline wrapped in OS-level
integration:

1. **Capture** — a global hotkey (push-to-talk or toggle) records microphone audio
   system-wide, regardless of which app is focused.
2. **ASR (speech-to-text)** — the raw audio is transcribed (cloud-side in their case).
3. **LLM post-processing** — the raw transcript is rewritten by a language model:
   - removes filler words ("um", "uh", "like")
   - adds punctuation and capitalization
   - applies *backtracking*: "send it Monday — no wait, Tuesday" → "send it Tuesday"
   - formats lists when you dictate enumerations
   - applies a personal dictionary (names, jargon, product terms)
   - optionally matches tone to context (formal/casual)
4. **Injection** — the final text is inserted into the focused app as if typed
   (works in any app that accepts keyboard input).

Extras on top of the base: Command Mode ("make that more concise" edits the last
dictation), voice snippets (spoken cue → canned text), shared team dictionaries,
code-aware formatting (camelCase, file tagging in Cursor).

**Base functionality to clone** = hotkey → record → transcribe → LLM cleanup →
paste into active window, plus a personal dictionary. Everything else is v2.

## 2. Key constraint: Ollama does not do speech-to-text

Ollama runs LLMs only. The "whisper" models on ollama.com (e.g. dimavz/whisper-tiny)
are text-input stubs that cannot process audio. So the local stack splits:

- **ASR**: run Whisper locally via a dedicated runtime.
- **Ollama**: does the LLM cleanup stage — which is exactly the part that makes
  Wispr Flow feel magical vs. plain Whisper.

## 3. Proposed architecture (Windows 11)

```
[global hotkey down]                      keyboard lib / Win32 RegisterHotKey
        │
        ▼
[record mic to RAM buffer]                sounddevice, 16 kHz mono float32
        │  (hotkey up)
        ▼
[transcribe]                              faster-whisper (CTranslate2)
        │                                 model: distil-small.en or large-v3-turbo (GPU)
        ▼
[cleanup via Ollama]                      POST http://localhost:11434/api/chat
        │                                 model: qwen2.5:3b-instruct or llama3.2:3b
        │                                 system prompt: filler removal, punctuation,
        │                                 backtracking, dictionary terms; temp 0
        ▼
[inject into focused app]                 set clipboard → send Ctrl+V → restore clipboard
                                          (fallback: simulated typing for apps that
                                          block paste)
```

Single Python process, system-tray resident (pystray), config in a TOML/JSON file.

### Component choices and why

| Stage | Choice | Why |
|-------|--------|-----|
| Language | Python 3.11+ | Every open-source clone (OpenWhisper, etc.) uses it; all libs mature |
| Hotkey | `keyboard` package | True global hooks on Windows, supports press/release (push-to-talk) |
| Audio | `sounddevice` | Low-latency PortAudio bindings, records straight to numpy in RAM |
| ASR | `faster-whisper` | 4x faster than openai/whisper, int8 CPU mode, GPU if available; alt: whisper.cpp or NVIDIA Parakeet (fastest English-only) |
| Cleanup LLM | Ollama + a 3B instruct model | 3B is plenty for text cleanup and keeps latency ~sub-second; escalate to 7–8B if quality disappoints |
| Injection | `pyperclip` + Ctrl+V | Clipboard-paste is the most reliable cross-app method; typing simulation is the fallback |
| Tray/UI | `pystray` + toast notifications | Minimal; a settings GUI is v2 |

### Model sizing (pick at install time)

- CPU-only: `distil-small.en` or `base` (Whisper) + `llama3.2:3b` — usable, ~1–3 s round trip for a sentence.
- NVIDIA GPU ≥6 GB: `large-v3-turbo` (Whisper) + `qwen2.5:7b` — near-Wispr quality.

## 4. Build phases

**Phase 0 — environment (½ day)**
- Install Ollama, pull the cleanup model, verify `http://localhost:11434` responds.
- Python venv; install faster-whisper, sounddevice, keyboard, pyperclip, pystray.
- Detect GPU (torch/ctranslate2 CUDA check) to pick Whisper model size.

**Phase 1 — core loop (1–2 days)**
- Push-to-talk recorder: hold hotkey (e.g. Ctrl+Win) → buffer audio → release → stop.
- Feed buffer to faster-whisper, print raw transcript.
- Pipe transcript through Ollama with the cleanup system prompt, temperature 0.
- Clipboard-paste result into the focused window; restore prior clipboard.
- Milestone: dictate into Notepad, Gmail, Cursor.

**Phase 2 — quality (1–2 days)**
- Tune the cleanup prompt: filler words, backtracking corrections, list formatting,
  "output only the cleaned text" guardrails (LLMs love adding commentary).
- Personal dictionary: user word list injected into both Whisper (`initial_prompt`)
  and the LLM system prompt; auto-append words the user corrects (v2).
- VAD (silence trimming via faster-whisper's built-in Silero VAD) to cut latency.
- Streaming: start transcribing while still recording (chunked) if latency bothers.

**Phase 3 — app polish (1–2 days)**
- System tray icon with recording indicator, model picker, hotkey config.
- Toggle mode in addition to push-to-talk.
- Auto-start with Windows; single-instance lock.
- Snippets: "insert my calendly" → canned text (simple keyword match before LLM).

**Phase 4 — stretch (later)**
- Command Mode: second hotkey routes speech as an *instruction* applied to the last
  output (pure LLM call, easy win).
- Tone/style presets per app (detect focused app via win32gui, swap system prompt).
- Multilingual: Whisper multilingual model + language auto-detect.

## 5. Risks / gotchas

- **Latency** is the whole game. Wispr feels instant; local CPU-only will feel
  laggy with big models. Start small, measure, and use VAD + int8 quantization.
- **LLM over-editing**: cleanup models rewrite meaning if the prompt is loose.
  Temperature 0, strict prompt, and a "raw mode" hotkey escape hatch.
- **`keyboard` lib needs the script elevated** for hooks in elevated windows; run
  non-elevated and accept that dictation won't reach admin apps, or ship both.
- **Clipboard race**: restore the clipboard after a short delay or some apps paste
  the restored (old) content.
- **Secure fields** (password boxes) block synthetic paste — expected, fine.

## 6. Prior art worth reading before writing code

- OpenWhispr (github.com/OpenWhispr/openwhispr) — Electron, local Whisper/Parakeet
- OpenWhisper (github.com/fsouza-dot/OpenWhisper) — pure-Python push-to-talk, closest to this plan
- Voicetypr (github.com/moinulmoin/voicetypr) — Tauri/Rust, Windows + macOS
- Handy — Rust, another local dictation tool
