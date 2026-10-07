# Dictée Locale

🇫🇷 [Version française](README.md)

Voice dictation for Windows, **100 % local**. Hold **Ctrl+Alt** in any
application, speak **English or French**, release: your voice is transcribed
on your PC, cleaned up (no more "um", stutters or false starts, punctuation
added), then pasted wherever your cursor is.

Nothing goes to the Internet: no account, no subscription, no cloud. Think of
it as a local, private alternative to Wispr Flow.

> The app's interface (tray menu, review box, settings panel) is in French.
> The few labels you will meet are translated [below](#french-labels).

## Features

- **Dictate anywhere**: Word, Gmail, Discord, VS Code, your browser… any
  field you can type in.
- **Smart cleanup**: a local AI model removes "um", "uh", stutters, repeated
  words and false starts, adds punctuation and applies your self-corrections
  ("Monday, no wait, Tuesday" → "Tuesday").
- **Faithful cleanup**: the text keeps your words and your tone. The model
  can only remove hesitations, punctuate and spell your terms correctly; any
  other rewrite is undone automatically.
- **English, French or both**: 🇬🇧, 🇫🇷 or 🇫🇷+🇬🇧 (automatic detection
  limited to these two languages).
- **Your clipboard is preserved**: whatever you had copied (text, images,
  files…) is restored after pasting.
- **Floating pill** at the bottom of the screen while you dictate: live
  waveform of your microphone and the flag of the active language.
- **One-click settings**: click the flag on the pill to change language or
  microphone, without restarting the app, even mid-dictation.
- **Hands-free mode (padlock 🔒)**: Ctrl+Alt starts dictating, you move
  between windows, Ctrl+Alt again and the text is pasted where you are.
- **Resend the last text (↺)**: if the paste went nowhere (no text field
  selected), one click pastes it again, for 20 seconds. The text only lives
  in memory, then it is wiped.
- **Cancel (✕)**: started talking and changed your mind? One click and
  nothing is pasted.
- **Voice commands**: end with "Colibri, paste." to paste without touching
  the keyboard, or "Colibri, send." to paste and press Enter.
- **A vocabulary that learns**: AI model names, products, first names…
  Whisper is steered towards the right spellings and recurring mistakes are
  fixed automatically.
- **Review (learning mode)**: a box shows the text before pasting, with the
  changes highlighted. Your corrections teach the vocabulary.
- **Privacy**: encrypted history on your PC, dictated text kept out of the
  Win+V clipboard history and of the clipboard cloud sync.
- **Subtle sounds**: a soft wooden click when the text is pasted, a click
  plus a short gust of wind when a message is sent, and a glass ping as soon
  as "Colibri" is understood.
- **Icon near the clock**: blue = ready, red = recording, orange =
  processing. Right-click → language or quit.

## Requirements

- Windows 10 or 11.
- Ideally an **NVIDIA** graphics card (transcription is then near-instant).
  Without one it still works on the CPU, only slower: see
  [Settings](#settings-configjson) to switch to a lighter model.
- **Ollama** for the text cleanup (optional but recommended):
  1. Install it from <https://ollama.com>.
  2. In a terminal: `ollama pull qwen2.5:7b` (≈ 4.7 GB).

  Without Ollama, the app pastes the raw transcription.

## Quick start (exe)

1. Download `DicteeLocale-windows.zip` from the
   [latest release](https://github.com/PinguReep/dictee-locale/releases/latest)
   and unzip it anywhere (keep the whole folder).
2. Run `DicteeLocale\DicteeLocale.exe`.
3. **First launch: be patient.** The app downloads the speech recognition
   model (≈ 1.6 GB) and shows nothing meanwhile. When it is ready, the blue
   icon appears at the bottom right, near the clock (sometimes hidden in the
   ˄ tray).
4. Right-click the icon → **English** if you mostly speak English.
5. Click in a text field, hold **Ctrl+Alt**, speak, release.

To start the app with Windows: `Win+R` → `shell:startup` → put a shortcut to
the exe in that folder.

## Usage

**Classic dictation**: hold Ctrl+Alt, speak, release. The text shows up in
under a second.

**While dictating**, the pill buttons light up on hover and can be clicked
(your cursor never loses focus):

| Element | Action |
|---|---|
| Flag | Opens the settings: language and microphone. Everything closes when you release |
| 🔒 Padlock | Turns hands-free mode on/off (stays on until the next click) |
| ↺ | Pastes the last text at the cursor and closes the pill (visible for 20 s after a dictation). If you are holding Ctrl+Alt, it pastes when you release |
| ✕ | Cancels the current dictation: nothing is pasted |

**Hands-free mode**: hold Ctrl+Alt, click the padlock, release. Recording
goes on; switch windows, place your cursor, then press and release Ctrl+Alt
to send. Typing `@`, `#` or `€` (AltGr) while dictating does not interrupt
it.

## Learning phase

Turn on **Relecture avant collage** (*review before pasting*, right-click on
the icon). After each dictation a box appears above the pill:

- words changed by the vocabulary or the cleanup are **blue**: a click puts
  back what Whisper heard; removed words are listed;
- without any action, the text is pasted after 4 s
  (`review_timeout_seconds`, `0` = wait);
- hover over the box to stop the countdown, click inside to fix things with
  the keyboard, then **Enter** (or the button, or Ctrl+Alt) to paste,
  **Esc** or **Annuler** (*cancel*) to throw it away;
- every correction is remembered: the same correction seen twice becomes a
  permanent rule, and proper nouns join the vocabulary.

Correct mistakes **in the box**, not after pasting: the app cannot see edits
made in the other application.

The vocabulary lives in `%LOCALAPPDATA%\DicteeLocale\vocabulaire.json` (you
can edit it by hand). With `spark_url` (an OpenAI-compatible server on your
local network), a model reviews your corrections once a day and suggests
general rules; only the corrected words and a few words of context are sent
to it, and never outside the local network.

## Voice commands

End your dictation with one of these phrases, **last**, then pause briefly:

| You say | Effect |
|---|---|
| "Colibri, paste." | Pastes the text (like Ctrl+Alt) |
| "Colibri, send." | Pastes the text, then presses **Enter** |

- "Colibri" is French for hummingbird: it was picked because no common word
  sounds like it. "Colibri, send it." and "Colibri, paste this." work too,
  as do the French versions ("Colibri, colle." / "Colibri, envoie.").
- In **hands-free mode** the command is detected live: no need to touch the
  keyboard, handy with a wireless headset.
- A glass ping confirms right away that the command was understood, handy
  for long messages that take a moment to process.
- When holding Ctrl+Alt, the command applies when you release.
- "Colibri, send." on its own sends a message that was already pasted.
- The command is never pasted into your text and only counts at the very
  end: "colibri" or "send" in the middle of a sentence trigger nothing, and
  neither do long silences.
- To turn them off: `"voice_commands": false`.

## French labels

| Where | Label | Meaning |
|---|---|---|
| Tray menu | Dictée locale — maintenir ctrl+alt | Local dictation — hold ctrl+alt |
| Tray menu | Français / English / Mix FR + EN | Dictation language |
| Tray menu | Relecture avant collage | Review before pasting (learning mode) |
| Tray menu | Historique… | History (double-click a line to copy it) |
| Tray menu | Analyser mes corrections (Spark) | Analyse my corrections on the LAN server |
| Tray menu | Effacer l'historique… | Delete the whole history |
| Tray menu | Quitter | Quit |
| Settings panel | RÉGLAGES · LANGUE · MICROPHONE | Settings · Language · Microphone |
| Review box | Relecture · clic sur un mot bleu : version entendue | Review · click a blue word: what was heard |
| Review box | Retiré · Annuler · Coller ⏎ | Removed · Cancel · Paste |

## Settings (`config.json`)

The file sits next to the exe. It is created as soon as you change a setting
from the pill; you can also copy the one from this repository.

| Key | Default | Purpose |
|-----|---------|---------|
| `hotkey` | `ctrl+alt` | Dictation shortcut (e.g. `ctrl+shift`, `f9`) |
| `language` | `mix` | `fr`, `en` or `mix` |
| `whisper_model` | `large-v3-turbo` | Transcription model. Without an NVIDIA card: `small` |
| `whisper_compute_type` | `float16` | `float16` on NVIDIA, `int8` on CPU |
| `ollama_enabled` | `true` | `false` to paste the raw text |
| `ollama_model` | `qwen2.5:7b` | Cleanup model (`qwen2.5:3b` = lighter) |
| `ollama_url` | `http://127.0.0.1:11434` | Ollama address. Keep `127.0.0.1`: `localhost` adds ~2 s per request on Windows |
| `dictionary` | tech terms | Words and proper nouns to spell right (names, brands, jargon) |
| `microphone_device` | `null` | `null` = default microphone (can be changed from the pill) |
| `hands_free_lock` | `false` | Hands-free mode |
| `transcript_ttl_seconds` | `20` | How long the ↺ resend stays available |
| `voice_commands` | `true` | "Colibri, paste." / "Colibri, send." commands |
| `ollama_keep_alive` | `-1` | Keeps the cleanup model loaded (`-1` = always, or e.g. `"30m"`) |
| `sounds` | `true` | Ping when "Colibri" is understood, click on paste, click + gust on send |
| `review_mode` | `false` | Review box before pasting (learning phase) |
| `review_timeout_seconds` | `4` | Auto-paste of an untouched box (`0` = wait) |
| `save_history` | `true` | Encrypted history (needed for learning) |
| `save_audio` | `false` | Also keep the audio, encrypted (benchmarks, fine-tuning) |
| `history_retention_days` | `30` | How long the history is kept |
| `spark_url` | `null` | LLM server on your local network to analyse your corrections |
| `microphone_name` | `null` | Chosen microphone, found again by name even when USB devices change |
| `paste_delay_ms` | `300` | Wait before restoring your clipboard |
| `sample_rate` | `16000` | Do not change |

## Privacy

- **Nothing leaves your PC.** One deliberate exception: the analysis of your
  corrections, sent to `spark_url`, which is refused unless it is on the
  local network.
- **Encrypted history** with Windows protection (DPAPI) in
  `%LOCALAPPDATA%\DicteeLocale\prive`: only your Windows account on this PC
  can read it. To view it: right-click the icon → **Historique…**
  (double-click to copy). **Effacer l'historique…** deletes everything.
- **The `dictation.log` file never contains dictated text**: only the steps,
  durations and word counts. Logs from older versions are moved into the
  encrypted history on first launch.
- **Clipboard**: dictated text enters neither the Win+V history nor the cloud
  sync, and whatever you had copied is put back as it was.

## Troubleshooting

A `dictation.log` file next to the exe details what is happening (never the
dictated text).

**Nothing happens with Ctrl+Alt**
- Is the blue icon shown near the clock? If not, the app is still loading
  (or crashed: check `dictation.log`).
- Another program may already use Ctrl+Alt: change `hotkey`.
- Windows launched as administrator do not receive the dictation.

**The pill stays on screen / Ctrl+Alt no longer responds**
- Click ✕ to cancel. If Ollama is slow to answer, the app pastes the raw text
  after about ten seconds instead of hanging.
- `dictation.log` is timestamped: it shows which step dragged on.

**The text is not cleaned up ("um" kept)**
- Ollama is not running or the model is missing: `ollama pull qwen2.5:7b`.
  The log says `Ollama cleanup failed` or `not found in Ollama`.

**`GPU unusable` in the log / slow transcription**
- No usable NVIDIA card: set `whisper_model` to `small` and
  `whisper_compute_type` to `int8`.

**Phantom sentences ("Thanks for watching!")**
- Whisper sometimes invents them during long silences. The best-known ones
  are filtered; if a new one shows up, add a piece of it to
  `HALLUCINATION_PATTERNS` in `main.py`.

**Wrong microphone**
- Click the flag on the pill while dictating and pick the right microphone.

## Tools

```powershell
.venv\Scripts\python -m pytest                          # tests
.venv\Scripts\python tools\eval_cleanup.py qwen2.5:7b   # cleanup on test sentences
.venv\Scripts\python tools\calibration.py               # recording session (~10 min)
.venv-bench\Scripts\python tools\benchmark.py          # compare engines on your voice
```

**Benchmark on your voice**: `calibration.py` has you read 40 sentences (AI
names, tech jargon; mostly French for now) and keeps them encrypted as
references. `benchmark.py` then compares Whisper turbo and large-v3,
Parakeet v3, Canary 1B v2 and Qwen3-ASR, and only prints scores (error rate,
missed vocabulary terms, latency). Your real dictations reviewed by hand with
audio (`save_audio`) are only added if you ask: `benchmark.py --avec-dictees`.

The benchmarked engines live in a separate environment to keep the app
light:

```powershell
python -m venv .venv-bench
.venv-bench\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu128
.venv-bench\Scripts\pip install qwen-asr onnx-asr faster-whisper sounddevice keyboard pystray pillow requests numpy
.venv-bench\Scripts\pip uninstall -y onnxruntime
.venv-bench\Scripts\pip install onnxruntime-gpu
```

## From source

Python 3.11+:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Or double-click `run.bat`. Useful option: `run.bat --debug-keys` prints every
key detected (handy if the shortcut does not react).

On an NVIDIA card, also install the CUDA libraries in the venv:
`pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` (loaded automatically).

**Rebuild the exe** (needs `pip install pyinstaller`):

```powershell
.\build.ps1
```

The script stops the app, rebuilds it, keeps the exe's `config.json` and
`dictation.log`, then relaunches `dist\DicteeLocale\DicteeLocale.exe`.

### How it works

Microphone (sounddevice, 16 kHz) → local transcription with **faster-whisper**
(`large-v3-turbo`, silence filter + anti-hallucination) → cleanup by
**Ollama** (`qwen2.5:7b`, prompt with FR/EN examples, every edit checked
against what you said) → paste through the clipboard + Ctrl+V, then clipboard
restore. Interface: tkinter (pill and settings, windows that never take the
focus) and pystray (tray icon).
