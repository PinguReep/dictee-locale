"""Local push-to-talk dictation MVP.

Hold the hotkey, speak (French or English), release. The audio is transcribed
locally with faster-whisper, optionally cleaned up by a local Ollama model, and
the result is pasted into the currently focused app.
"""

import collections
import ctypes
import importlib.util
import json
import os
import re
import sys
import threading
import time
import tkinter as tk
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import keyboard
import numpy as np
import pyperclip
import pystray
import requests
import sounddevice as sd

# Reused connection to Ollama; trust_env=False skips the per-request Windows
# proxy lookup.
OLLAMA_SESSION = requests.Session()
OLLAMA_SESSION.trust_env = False
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw

from overlay import Overlay

# When frozen by PyInstaller, config/logs live next to the .exe.
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent
CONFIG_PATH = APP_DIR / "config.json"


def ensure_single_instance():
    """Exits quietly if another instance already holds the named mutex."""
    ctypes.windll.kernel32.CreateMutexW(None, False, "DicteeLocale_SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        print("[info] Already running (check the tray icon). Exiting.")
        sys.exit(0)


class TimestampedLog:
    """Prefixes each log line with the time, to spot slow or stuck steps."""

    def __init__(self, stream):
        self.stream = stream
        self.at_line_start = True

    def write(self, text):
        for part in text.splitlines(keepends=True):
            if self.at_line_start and part.strip():
                self.stream.write(time.strftime("%H:%M:%S "))
            self.stream.write(part)
            self.at_line_start = part.endswith("\n")
        return len(text)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def setup_frozen_logging():
    """In a --noconsole exe there is no stdout: send prints to a log file."""
    if getattr(sys, "frozen", False) and sys.stdout is None:
        log = open(APP_DIR / "dictation.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = TimestampedLog(log)
        print(f"--- started {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

DEFAULTS = {
    "hotkey": "ctrl+alt",
    "whisper_model": "large-v3-turbo",
    "whisper_compute_type": "float16",
    "ollama_enabled": True,
    "ollama_model": "qwen2.5:7b",
    "ollama_url": "http://127.0.0.1:11434",
    "paste_delay_ms": 300,
    "sample_rate": 16000,
    "microphone_device": None,
    "dictionary": [],
    "language": "mix",  # "fr", "en", or "mix" (auto between the two)
    "transcript_ttl_seconds": 20,  # resend window for the last transcript
    "hands_free_lock": False,  # pill padlock: tap hotkey to start, tap to send
    "voice_commands": True,  # "Colibri, colle." / "Colibri, envoie." at the end
    "ollama_keep_alive": -1,  # keep the cleanup model loaded (-1 = always)
}

LANGUAGE_LABELS = {"fr": "Français", "en": "English", "mix": "Mix FR + EN"}

MIN_RECORDING_SECONDS = 0.3

# The `keyboard` lib reports sided and LOCALIZED key names (on French Windows
# the right Alt is "alt gr", Shift is "maj", etc.). Collapse them so a hotkey
# like "ctrl+alt" matches any physical variant of those modifiers.
KEY_ALIASES = {
    "left ctrl": "ctrl", "right ctrl": "ctrl",
    "ctrl gauche": "ctrl", "ctrl droite": "ctrl", "ctrl droit": "ctrl",
    "left alt": "alt", "right alt": "alt", "alt gr": "alt",
    "alt gauche": "alt", "alt droite": "alt", "alt droit": "alt",
    "left shift": "shift", "right shift": "shift",
    "maj": "shift", "maj gauche": "shift", "maj droite": "shift",
    "left windows": "windows", "right windows": "windows",
}


def normalize_key(name):
    return KEY_ALIASES.get(name.lower(), name.lower())


VK_CODES = {"ctrl": (0x11,), "alt": (0x12,), "shift": (0x10,),
            "windows": (0x5B, 0x5C)}


def key_physically_down(name):
    """True if the (normalized) key is down right now; unknown keys: True."""
    codes = VK_CODES.get(name)
    if codes is None:
        return True
    return any(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000
               for vk in codes)

CLEANUP_SYSTEM_PROMPT = """You clean up raw speech-to-text transcripts.

Rules:
- Remove filler words (um, uh, like, you know, euh, ben, bah, genre, du coup,
tu vois, quoi, attends, bref, en fait) when they carry no meaning.
- Remove stutters, repeated words and false starts: keep only the completed
thought ("je je voulais", "on... on devrait" -> "je voulais", "on devrait").
- Add proper punctuation and capitalization.
- Preserve the original meaning and wording. Never summarize, expand, or answer \
questions contained in the text.
- Apply self-corrections: if the speaker corrects themselves ("send it Monday, \
no wait, Tuesday" / "lundi, non plutot mardi"), keep only the corrected version.
- NEVER translate. The output must be in the exact same language as the input. \
Do not change times, dates, numbers, or names beyond fixing punctuation.
- In French text, keep English technical terms (anglicisms) exactly as spoken: \
"push", "deploy", "pull request", "feature" must NOT be turned into French words.
- Output ONLY the final cleaned text. No commentary, no quotes, no explanations."""

# Few-shot examples: small local models follow the rules far more reliably
# with one demonstration per language than with instructions alone.
CLEANUP_EXAMPLES = [
    ("hello um so I'll send the report on uh Monday no wait Tuesday morning",
     "Hello, I'll send the report on Tuesday morning."),
    ("bonjour euh du coup on se voit lundi non plutot mardi a quinze heures",
     "Bonjour, on se voit mardi à quinze heures."),
    # Franglais: anglicisms must survive the cleanup untouched.
    ("euh j'ai push le fix sur la branche main tu peux review avant le deploy",
     "J'ai push le fix sur la branche main, tu peux review avant le deploy."),
    # Stutters, false starts and fillers all collapse into the clean thought.
    ("attends euh je je voulais dire qu'on qu'on devrait genre partir "
     "plus tot quoi",
     "Je voulais dire qu'on devrait partir plus tôt."),
]


def load_config():
    config = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[warn] Could not read config.json ({exc}), using defaults.")
    else:
        print("[warn] config.json not found, using defaults.")
    # "localhost" costs ~2s per request on Windows (IPv6 attempt first);
    # Ollama only listens on IPv4.
    config["ollama_url"] = config["ollama_url"].replace("localhost", "127.0.0.1")
    return config


def save_config(config):
    try:
        CONFIG_PATH.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"[warn] Could not save config.json: {exc}")


def make_icon_image(color):
    """Draws a small round microphone icon for the system tray."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, 60, 60], fill=color)
    d.rounded_rectangle([26, 14, 38, 36], radius=6, fill="white")
    d.line([32, 36, 32, 46], fill="white", width=4)
    d.line([22, 47, 42, 47], fill="white", width=4)
    return img


class HotkeyController:
    """Turns raw key events into start/stop decisions.

    Unlocked: push-to-talk (hold to record, release to send).
    Locked (pill padlock): the release after starting is ignored and recording
    continues hands-free; the next full press+release of the hotkey sends.
    A hotkey hold that also presses another key (e.g. AltGr+0 for "@" on
    AZERTY, since AltGr = Ctrl+Alt) never ends a hands-free recording.
    Stopping happens on release so no modifier is still down during Ctrl+V.
    """

    def __init__(self, hotkey_parts, get_state, is_locked, start, stop,
                 is_down=None):
        self.parts = hotkey_parts
        self.is_down = is_down  # physical key state, to recover lost key-ups
        self.down_since = {}
        self.get_state = get_state
        self.is_locked = is_locked
        self.start = start
        self.stop = stop
        self.pressed = set()
        self.held = False
        self.hands_free = False
        self.stop_pending = False
        self.other_key = False

    def handle(self, name, is_down):
        name = normalize_key(name)
        now = time.monotonic()
        if is_down:
            self.pressed.add(name)
            self.down_since.setdefault(name, now)
        else:
            self.pressed.discard(name)
            self.down_since.pop(name, None)
        if self.is_down is not None:
            # A key-up can be lost (secure desktop, elevated window, sleep):
            # that key then counts as held forever and the hotkey goes dead.
            stale = {k for k in self.pressed
                     if k != name and now - self.down_since[k] > 1.5
                     and not self.is_down(k)}
            if stale:
                self.pressed -= stale
                for k in stale:
                    del self.down_since[k]
                print(f"[warn] Recovered stuck keys: {sorted(stale)}")
        held = self.parts <= self.pressed
        press, release = held and not self.held, self.held and not held
        self.held = held
        if press:
            self.other_key = False
        elif held and is_down and name not in self.parts:
            self.other_key = True

        state = self.get_state()
        if state == "idle" and press:
            self.hands_free = self.stop_pending = False
            self.start()
        elif state == "recording":
            if press and self.hands_free:
                self.stop_pending = True
            elif release:
                if self.stop_pending:
                    self.stop_pending = False
                    if not self.other_key:
                        self.stop()
                elif self.hands_free:
                    pass
                elif self.is_locked():
                    self.hands_free = True
                    print("[rec ] Hands-free: press the hotkey again to send.")
                else:
                    self.stop()


class Recorder:
    """Records mic audio to RAM via a sounddevice callback."""

    def __init__(self, sample_rate, device, levels=None):
        self.sample_rate = sample_rate
        self.device = device
        self.levels = levels  # optional deque fed with RMS for the overlay
        self._chunks = []
        self._stream = None

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"[warn] Audio status: {status}")
        self._chunks.append(indata.copy())
        if self.levels is not None:
            self.levels.append(float(np.sqrt((indata ** 2).mean())))

    def start(self):
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()

    def switch_device(self, device):
        """Applies a new input device immediately, even mid-recording.

        Audio already captured is kept; the stream is reopened on the new
        device and keeps appending to the same buffer.
        """
        self.device = device
        if self._stream is None:
            return
        self._stream.stop()
        self._stream.close()
        self._stream = None
        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=device,
                callback=self._callback,
            )
            self._stream.start()
        except sd.PortAudioError as exc:
            print(f"[error] Could not switch microphone mid-recording: {exc}")

    def snapshot(self, seconds):
        """Last `seconds` of the ongoing recording, without stopping it."""
        need = int(seconds * self.sample_rate)
        tail, total = [], 0
        for chunk in reversed(list(self._chunks)):
            tail.append(chunk)
            total += len(chunk)
            if total >= need:
                break
        if not tail:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(tail[::-1]).flatten()[-need:]

    def stop(self):
        """Stops the stream and returns the recording as a 1-D float32 array."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._chunks)
        self._chunks = []
        return audio.flatten()


def add_cuda_dll_dirs():
    """Makes pip-installed CUDA DLLs (nvidia-cublas/cudnn-cu12) findable.

    On Windows ctranslate2 needs cuBLAS/cuDNN on the DLL search path; the pip
    packages ship them under site-packages/nvidia/*/bin.
    """
    locations = []
    spec = importlib.util.find_spec("nvidia")
    if spec is not None and spec.submodule_search_locations:
        locations.extend(Path(p) for p in spec.submodule_search_locations)
    if getattr(sys, "frozen", False):  # bundled by PyInstaller
        locations.append(Path(getattr(sys, "_MEIPASS", APP_DIR)) / "nvidia")
        locations.append(APP_DIR / "_internal" / "nvidia")
    for location in locations:
        if not location.is_dir():
            continue
        for bin_dir in location.glob("*/bin"):
            if any(bin_dir.glob("*.dll")):
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]


def load_whisper(config):
    """Loads the Whisper model, falling back to CPU if the GPU is unusable.

    device="auto" picks CUDA when an NVIDIA GPU is present, but failures
    (missing/incompatible CUDA libs) only surface on the first transcription,
    so we warm up with a short silence to catch that at startup. The CPU
    fallback forces int8: float16 is a GPU compute type.
    """
    add_cuda_dll_dirs()
    attempts = [("auto", config["whisper_compute_type"]), ("cpu", "int8")]
    for device, compute_type in attempts:
        try:
            model = WhisperModel(
                config["whisper_model"],
                device=device,
                compute_type=compute_type,
            )
            warmup = np.zeros(8000, dtype=np.float32)
            segments, _ = model.transcribe(warmup, vad_filter=False)
            list(segments)
            return model
        except Exception as exc:
            if device == "cpu":
                print(f"[error] Could not load Whisper model: {exc}")
                sys.exit(1)
            print(f"[warn] GPU unusable ({exc}), falling back to CPU (int8).")
    return None  # unreachable


# Whisper was trained on YouTube subtitles: on silence or room noise it
# invents these sign-off lines. Long hands-free recordings are full of pauses.
HALLUCINATION_PATTERNS = (
    "merci d'avoir regardé", "merci de m'avoir regardé", "sous-titr",
    "amara.org", "abonnez-vous", "vous abonner", "thanks for watching",
    "thank you for watching", "subscribe to",
)
HALLUCINATION_MAX_WORDS = 12  # longer segments are kept: likely real speech

# Anti-hallucination decoding: cut silences aggressively before decoding,
# don't let one invented line seed the next window, and skip segments
# surrounded by long silence.
WHISPER_OPTIONS = {
    "vad_filter": True,
    "vad_parameters": {"min_silence_duration_ms": 500, "speech_pad_ms": 300},
    "condition_on_previous_text": False,
    "word_timestamps": True,
    "hallucination_silence_threshold": 2.0,
}


def join_segments(segments):
    kept = []
    for segment in segments:
        text = segment.text.strip()
        lowered = text.lower().replace("’", "'")
        if (len(text.split()) <= HALLUCINATION_MAX_WORDS
                and any(p in lowered for p in HALLUCINATION_PATTERNS)):
            print(f"[info] Dropped hallucinated segment: {text!r}")
            continue
        kept.append(text)
    return " ".join(kept).strip()


def transcribe(model, audio, dictionary=(), language="mix"):
    # initial_prompt biases Whisper toward these spellings — this is how
    # personal-dictionary terms (names, tech jargon) survive transcription.
    initial_prompt = ", ".join(dictionary) if dictionary else None
    forced = language if language in ("fr", "en") else None
    segments, info = model.transcribe(
        audio, language=forced, initial_prompt=initial_prompt,
        **WHISPER_OPTIONS
    )
    text = join_segments(segments)
    if forced is None and text and info.language not in ("fr", "en"):
        # Mix mode: short clips get misdetected (e.g. Japanese). Constrain the
        # choice to fr/en using the detection probabilities and redo the pass.
        probs = dict(info.all_language_probs or [])
        best = "fr" if probs.get("fr", 0.0) >= probs.get("en", 0.0) else "en"
        print(f"[info] Detected '{info.language}', constraining to '{best}' "
              f"(mix mode).")
        segments, info = model.transcribe(
            audio, language=best, initial_prompt=initial_prompt,
            **WHISPER_OPTIONS
        )
        text = join_segments(segments)
    if text:
        print(f"[info] Language: {info.language} "
              f"(p={info.language_probability:.2f})")
    return text, info.language


# Spoken end-of-dictation commands: "... à demain. Colibri, envoie."
# "Colibri" sounds like no common word, so ordinary sentences never trigger;
# only the very last words spoken count. Matching is lenient because the
# final transcription may spell the command differently ("col", "call").
VOICE_WAKE_WORD = "colibri"
VOICE_SPLIT_SEND = {"voie", "voix", "vois", "voit"}  # "envoie" heard "en voie"
VOICE_TAIL_SECONDS = 4.0
VOICE_SILENCE_SECONDS = 0.6  # silence required after the command (live check)
VOICE_CHECK_INTERVAL = 1.0


def _plain(word):
    decomposed = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _is_wake(word):
    return SequenceMatcher(None, word, VOICE_WAKE_WORD).ratio() >= 0.75


def _verb(word):
    if _is_wake(word):
        return None
    if word.startswith(("col", "kol")) or word in ("call", "coal", "paste"):
        return "paste"
    if word.startswith(("envo", "anvo")) or word == "send":
        return "send"
    return None


def extract_voice_command(text, assume_command=None):
    """Splits a trailing voice command off the transcript.

    Returns (text_without_command, "paste" | "send" | None). When the live
    check already heard a command (`assume_command`), the trailing command
    words are removed even if this transcription spelled them oddly.
    """
    tokens = list(re.finditer(r"\w+", text))
    words = [_plain(t.group()) for t in tokens]
    n = len(words)

    def wake_start(end):
        if end >= 0 and _is_wake(words[end]):
            return end
        if end >= 1 and _is_wake(words[end - 1] + words[end]):
            return end - 1
        return None

    command = start = None
    if n >= 3 and words[-2] == "en" and words[-1] in VOICE_SPLIT_SEND:
        start = wake_start(n - 3)
        command = "send" if start is not None else None
    if command is None and n >= 2 and _verb(words[-1]):
        start = wake_start(n - 2)
        command = _verb(words[-1]) if start is not None else None
    if command is None and assume_command:
        command = assume_command
        start = next((i for i in range(n - 1, max(n - 5, -1), -1)
                      if _is_wake(words[i])), max(n - 2, 0))
        print("[warn] Command spelled differently in the final transcript; "
              "trailing words removed.")
    if command is None:
        return text, None
    if n == 0:
        return "", command
    return text[:tokens[start].start()].rstrip(" ,;:-\u2013\u2014\n"), command


def detect_live_voice_command(model, tail, language, sample_rate):
    """Looks for a command at the end of the last seconds of a hands-free
    recording, followed by a short silence. Returns "paste", "send" or None.
    """
    segments, _ = model.transcribe(
        tail, language=language if language in ("fr", "en") else "fr",
        beam_size=1, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        condition_on_previous_text=False, word_timestamps=True,
    )
    words = [w for segment in segments for w in (segment.words or [])]
    if len(words) < 2:
        return None
    _, command = extract_voice_command("".join(w.word for w in words))
    if command is None:
        return None
    if words[-1].end > len(tail) / sample_rate - VOICE_SILENCE_SECONDS:
        return None  # still talking right after the command words
    return command


def clean_with_ollama(text, config, language=None):
    """Returns the cleaned transcript, or None if Ollama failed."""
    url = config["ollama_url"].rstrip("/") + "/api/chat"
    system = CLEANUP_SYSTEM_PROMPT
    if language in ("fr", "en"):
        lang_name = "French" if language == "fr" else "English"
        system += (f"\n\nThe transcript below is in {lang_name}. "
                   f"Your output MUST be in {lang_name}.")
    messages = [{"role": "system", "content": system}]
    for raw, cleaned in CLEANUP_EXAMPLES:
        messages.append({"role": "user", "content": raw})
        messages.append({"role": "assistant", "content": cleaned})
    messages.append({"role": "user", "content": text})
    payload = {
        "model": config["ollama_model"],
        "messages": messages,
        "stream": False,
        "keep_alive": config.get("ollama_keep_alive", -1),
        "options": {"temperature": 0},
    }
    # A slow or stuck Ollama must never freeze dictation: fall back to the
    # raw transcript after a short wait that grows with the text length.
    timeout = 10 + len(text.split()) / 20
    try:
        response = OLLAMA_SESSION.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        cleaned = response.json()["message"]["content"].strip()
    except (requests.RequestException, KeyError, ValueError) as exc:
        print(f"[warn] Ollama cleanup failed ({exc}), using raw transcript.")
        return None
    # Models sometimes wrap their answer in quotes despite instructions.
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
        cleaned = cleaned[1:-1].strip()
    return cleaned or None


def paste_text(text, paste_delay_ms):
    try:
        previous_clipboard = pyperclip.paste()
    except pyperclip.PyperclipException:
        previous_clipboard = None
    pyperclip.copy(text)
    time.sleep(0.15)  # let the clipboard settle before pasting
    keyboard.send("ctrl+v")
    time.sleep(paste_delay_ms / 1000)
    if previous_clipboard is not None:
        try:
            pyperclip.copy(previous_clipboard)
        except pyperclip.PyperclipException:
            pass


def list_input_devices():
    """Returns [(index, name)] of input devices, deduplicated by name.

    Windows exposes each mic through several host APIs (MME, DirectSound,
    WASAPI...); we only keep the host API of the default input to avoid
    listing every mic 3-4 times.
    """
    devices = sd.query_devices()
    try:
        default_input = sd.default.device[0]
        hostapi = devices[default_input]["hostapi"] if default_input >= 0 else None
    except (TypeError, IndexError):
        hostapi = None
    result, seen = [], set()
    for index, device in enumerate(devices):
        if device["max_input_channels"] <= 0:
            continue
        if hostapi is not None and device["hostapi"] != hostapi:
            continue
        name = device["name"].strip()
        if name in seen or "Mappeur de sons" in name or "Sound Mapper" in name:
            continue
        seen.add(name)
        result.append((index, name))
    return result


def check_microphone(config):
    try:
        device = sd.query_devices(config["microphone_device"], kind="input")
        print(f"[info] Microphone: {device['name']}")
    except (sd.PortAudioError, ValueError) as exc:
        print(f"[error] No usable microphone found: {exc}")
        sys.exit(1)


def warm_up_ollama(config):
    """Loads the cleanup model in the background so the first dictation is fast.

    At login the app can start before Ollama, so retry for a couple of minutes.
    A /api/generate call without a prompt just loads the model.
    """
    url = config["ollama_url"].rstrip("/") + "/api/generate"
    payload = {"model": config["ollama_model"],
               "keep_alive": config.get("ollama_keep_alive", -1)}
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            OLLAMA_SESSION.post(url, json=payload, timeout=120).raise_for_status()
            print(f"[info] Ollama model '{config['ollama_model']}' warmed up.")
            return
        except requests.ConnectionError:
            time.sleep(5)
        except requests.RequestException as exc:
            print(f"[warn] Ollama warm-up failed: {exc}")
            return


def check_ollama(config):
    """Warns (without exiting) if Ollama or the model is unavailable."""
    if not config["ollama_enabled"]:
        print("[info] Ollama cleanup disabled, raw transcripts will be pasted.")
        return
    try:
        response = OLLAMA_SESSION.get(
            config["ollama_url"].rstrip("/") + "/api/tags", timeout=3
        )
        response.raise_for_status()
        models = [m["name"] for m in response.json().get("models", [])]
    except (requests.RequestException, ValueError) as exc:
        print(f"[warn] Ollama unreachable ({exc}). Raw transcripts will be pasted.")
        return
    wanted = config["ollama_model"]
    if not any(name == wanted or name.split(":")[0] == wanted for name in models):
        print(f"[warn] Model '{wanted}' not found in Ollama. "
              f"Run: ollama pull {wanted}")
    else:
        print(f"[info] Ollama ready with model '{wanted}'.")


def main():
    setup_frozen_logging()
    ensure_single_instance()
    config = load_config()
    check_microphone(config)
    check_ollama(config)
    if config["ollama_enabled"]:
        threading.Thread(target=warm_up_ollama, args=(config,),
                         daemon=True).start()

    print(f"[info] Loading Whisper model '{config['whisper_model']}' "
          f"({config['whisper_compute_type']})...")
    model = load_whisper(config)
    print("[info] Whisper model loaded.")

    levels = collections.deque(maxlen=64)
    quit_event = threading.Event()
    # Last transcript, RAM only, purged after transcript_ttl_seconds so the
    # pill's resend button can paste it again.
    last_transcript = {"text": None, "at": 0.0}
    if os.environ.get("DICTEE_LAST_TRANSCRIPT"):  # test hook
        last_transcript.update(text=os.environ["DICTEE_LAST_TRANSCRIPT"],
                               at=time.time())
    recorder = Recorder(config["sample_rate"], config["microphone_device"],
                        levels)
    hotkey = config["hotkey"]
    hotkey_parts = {normalize_key(p.strip()) for p in hotkey.split("+")}
    debug_keys = "--debug-keys" in sys.argv
    # idle -> recording -> processing (pill shown) | pasting (hidden) -> idle
    state = {"value": "idle"}
    # Each start, cancel and resend opens a new session. Background work only
    # pastes and resets the state if its session is still the current one.
    session = {"id": 0}
    lock = threading.RLock()

    icons = {
        "idle": make_icon_image("#3B82F6"),        # blue
        "recording": make_icon_image("#EF4444"),   # red
        "processing": make_icon_image("#F59E0B"),  # orange
    }
    icons["pasting"] = icons["processing"]
    tray = pystray.Icon("dictation", icons["idle"], "Dictée locale")

    def set_state(value):
        state["value"] = value
        tray.icon = icons[value]

    def set_language(mode):
        def handler(icon, item):
            config["language"] = mode
            save_config(config)
            print(f"[info] Langue: {LANGUAGE_LABELS[mode]}")
        return handler

    def quit_app(icon, item):
        keyboard.unhook_all()
        tray.stop()
        quit_event.set()  # the overlay's tick loop closes the tk mainloop

    tray.menu = pystray.Menu(
        pystray.MenuItem(f"Dictée locale — maintenir {hotkey}", None,
                         enabled=False),
        pystray.Menu.SEPARATOR,
        *(pystray.MenuItem(
            LANGUAGE_LABELS[mode], set_language(mode), radio=True,
            checked=(lambda m: lambda item: config["language"] == m)(mode))
          for mode in ("fr", "en", "mix")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter", quit_app),
    )

    def is_current(my_id):
        return session["id"] == my_id

    def finish(my_id):
        with lock:
            if is_current(my_id):
                set_state("idle")

    def process(audio, my_id, live_command=None):
        try:
            duration = len(audio) / config["sample_rate"]
            if duration < MIN_RECORDING_SECONDS:
                print("[info] Recording too short, ignoring.")
                return
            print(f"[info] Transcribing {duration:.1f}s of audio...")
            text, language = transcribe(model, audio, config["dictionary"],
                                        config["language"])
            command = None
            if config.get("voice_commands", True):
                text, command = extract_voice_command(
                    text, assume_command=live_command)
                last_words = re.findall(r"\w+", text)[-3:]
                if not command and any(_is_wake(_plain(w)) for w in last_words):
                    print("[warn] Wake word heard but no command understood: "
                          f"{' '.join(last_words)!r}")
                if command:
                    print(f"[info] Voice command: {command}")
            if not is_current(my_id):
                print("[info] Dictation cancelled.")
                return
            if not text and command != "send":
                print("[info] Nothing transcribed, skipping paste.")
                return
            if text:
                print(f"[raw ] {text}")
                if config["ollama_enabled"]:
                    cleaned = clean_with_ollama(text, config, language)
                    if cleaned:
                        text = cleaned
                        print(f"[clean] {text}")
                if not is_current(my_id):
                    print("[info] Dictation cancelled.")
                    return
                paste_text(text, config["paste_delay_ms"])
                last_transcript.update(text=text, at=time.time())
                print("[info] Pasted.")
            if command == "send":
                keyboard.send("enter")
                print("[info] Sent (Enter).")
        finally:
            finish(my_id)

    def start_recording():
        with lock:
            if state["value"] != "idle":
                return
            session["id"] += 1
            my_id = session["id"]
            set_state("recording")
            try:
                recorder.start()
            except sd.PortAudioError as exc:
                print(f"[error] Could not start recording: {exc}")
                set_state("idle")
                return
        print("[rec ] Recording... release the hotkey to stop.")
        if config.get("voice_commands", True):
            threading.Thread(target=watch_voice_commands, args=(my_id,),
                             daemon=True).start()

    def stop_recording(live_command=None, my_id=None):
        with lock:
            if state["value"] != "recording":
                return
            if my_id is not None and not is_current(my_id):
                return
            my_id = session["id"]
            set_state("processing")
            audio = recorder.stop()
        threading.Thread(target=process, args=(audio, my_id, live_command),
                         daemon=True).start()

    def cancel():
        with lock:
            if state["value"] not in ("recording", "processing"):
                return
            if state["value"] == "recording":
                recorder.stop()
            session["id"] += 1
            set_state("idle")
        print("[info] Dictation cancelled.")

    def resend():
        with lock:
            if state["value"] != "recording" or not last_transcript["text"]:
                return
            recorder.stop()
            session["id"] += 1
            my_id = session["id"]
            set_state("pasting")
        threading.Thread(target=paste_last, args=(my_id,), daemon=True).start()

    def paste_last(my_id):
        try:
            # Clicked while holding the hotkey: wait for the release so no
            # modifier is still down during Ctrl+V.
            deadline = time.time() + 10
            while controller.held and time.time() < deadline:
                time.sleep(0.02)
            text = last_transcript["text"]
            if controller.held or not text or not is_current(my_id):
                print("[info] Resend skipped.")
                return
            paste_text(text, config["paste_delay_ms"])
            last_transcript["at"] = time.time()  # resend refreshes the window
            print("[info] Resent last transcript.")
        finally:
            finish(my_id)

    def watch_voice_commands(my_id):
        last_check = 0.0
        while True:
            time.sleep(0.2)
            if state["value"] != "recording" or not is_current(my_id):
                return
            # Push-to-talk reads the command from the final transcript on
            # release; the live check is only for hands-free dictation.
            if not controller.hands_free or controller.held:
                continue
            if time.monotonic() - last_check < VOICE_CHECK_INTERVAL:
                continue
            last_check = time.monotonic()
            tail = recorder.snapshot(VOICE_TAIL_SECONDS)
            if len(tail) < 1.5 * config["sample_rate"]:
                continue
            try:
                command = detect_live_voice_command(
                    model, tail, config["language"], config["sample_rate"])
            except Exception as exc:
                print(f"[warn] Voice command check failed: {exc}")
                return
            if command:
                print(f"[info] Voice command heard: {command}")
                stop_recording(live_command=command, my_id=my_id)
                return

    controller = HotkeyController(
        hotkey_parts,
        get_state=lambda: state["value"],
        is_locked=lambda: config.get("hands_free_lock", False),
        start=start_recording,
        stop=stop_recording,
        is_down=key_physically_down,
    )

    def on_key_event(event):
        if not event.name:
            return
        controller.handle(event.name, event.event_type == keyboard.KEY_DOWN)
        if debug_keys:
            print(f"[keys] {event.event_type:<4} {event.name!r:<16} "
                  f"held={sorted(controller.pressed)}")

    keyboard.hook(on_key_event)

    def on_microphone(index):
        recorder.switch_device(index)  # applies immediately, even mid-recording

    # tkinter owns the main thread (overlay); the tray icon runs detached.
    root = tk.Tk()
    root.withdraw()
    Overlay(root, levels, state, quit_event, config, save_config,
            list_input_devices, on_microphone, last_transcript,
            actions={"resend": resend, "cancel": cancel})
    tray.run_detached()

    print(f"[info] Ready. Hold '{hotkey}' and speak. "
          f"Quit from the tray icon (or Ctrl+C here).")
    if debug_keys:
        print("[info] Key debug on: every key event will be printed.")
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    quit_event.set()
    tray.stop()
    print("[info] Bye.")


if __name__ == "__main__":
    main()
