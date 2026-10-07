"""Encrypted, local-only history of dictations (text and optional audio).

Everything is encrypted with Windows DPAPI (user scope): only this Windows
account on this PC can decrypt it, and nothing is stored as plain text, so
a text search over the disk finds no dictation. It lives outside the app
folder, so rebuilding the exe keeps it:
    %LOCALAPPDATA%\\DicteeLocale\\prive
"""

import base64
import ctypes
import ctypes.wintypes as wt
import io
import json
import os
import re
import threading
import time
import uuid
import wave
from pathlib import Path

import numpy as np

_ENTROPY = b"DicteeLocale/prive/v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
for _fn in (_crypt32.CryptProtectData, _crypt32.CryptUnprotectData):
    _fn.argtypes = [ctypes.POINTER(_Blob), wt.LPCWSTR, ctypes.POINTER(_Blob),
                    ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
                    ctypes.POINTER(_Blob)]
    _fn.restype = wt.BOOL
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p


def _blob(data):
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _dpapi(function, data):
    source, _keep = _blob(data)
    entropy, _keep2 = _blob(_ENTROPY)
    out = _Blob()
    if not function(ctypes.byref(source), None, ctypes.byref(entropy), None,
                    None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def protect(data):
    return _dpapi(_crypt32.CryptProtectData, data)


def unprotect(data):
    return _dpapi(_crypt32.CryptUnprotectData, data)


def default_root():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "DicteeLocale" / "prive"


def _wav_bytes(audio, sample_rate):
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buffer.getvalue()


class PrivateStore:
    """Append-only encrypted journal: one DPAPI blob (base64) per line."""

    def __init__(self, root=None, retention_days=30):
        self.root = Path(root) if root else default_root()
        self.audio_dir = self.root / "audio"
        self.history = self.root / "historique.dat"
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def add(self, record, audio=None, sample_rate=16000):
        """Stores a record (dict) and optional audio; returns its id."""
        record = dict(record)
        record.setdefault("id", time.strftime("%Y%m%d-%H%M%S-")
                          + uuid.uuid4().hex[:6])
        record.setdefault("at", time.time())
        if audio is not None and len(audio):
            data = protect(_wav_bytes(audio, sample_rate))
            (self.audio_dir / f"{record['id']}.bin").write_bytes(data)
            record["audio"] = True
        line = base64.b64encode(
            protect(json.dumps(record, ensure_ascii=False).encode("utf-8")))
        with self._lock, open(self.history, "ab") as f:
            f.write(line + b"\n")
        return record["id"]

    def records(self):
        """All records, oldest first (decrypted in memory only)."""
        if not self.history.exists():
            return []
        out = []
        with self._lock:
            lines = self.history.read_bytes().splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                out.append(json.loads(unprotect(base64.b64decode(line))))
            except (OSError, ValueError):
                continue  # written by another Windows account or corrupted
        return out

    def audio(self, record_id):
        """(float32 array, sample_rate) of a record, or None."""
        path = self.audio_dir / f"{record_id}.bin"
        if not path.exists():
            return None
        with wave.open(io.BytesIO(unprotect(path.read_bytes()))) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            return pcm.astype(np.float32) / 32768.0, w.getframerate()

    def purge_old(self):
        """Deletes records (and audio) older than the retention period."""
        if not self.retention_days:
            return 0
        limit = time.time() - self.retention_days * 86400
        keep, dropped = [], 0
        for record in self.records():
            if record.get("at", 0) >= limit:
                keep.append(record)
                continue
            dropped += 1
            (self.audio_dir / f"{record.get('id')}.bin").unlink(missing_ok=True)
        if dropped:
            self._rewrite(keep)
        return dropped

    def remove(self, record_ids):
        """Deletes the given records and their audio."""
        record_ids = set(record_ids)
        keep = [r for r in self.records() if r.get("id") not in record_ids]
        for record_id in record_ids:
            (self.audio_dir / f"{record_id}.bin").unlink(missing_ok=True)
        self._rewrite(keep)

    def clear(self):
        """Deletes the whole history and all audio."""
        with self._lock:
            self.history.unlink(missing_ok=True)
            for path in self.audio_dir.glob("*.bin"):
                path.unlink(missing_ok=True)

    def _rewrite(self, records):
        tmp = self.history.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            for record in records:
                f.write(base64.b64encode(protect(
                    json.dumps(record, ensure_ascii=False).encode("utf-8")))
                    + b"\n")
        with self._lock:
            os.replace(tmp, self.history)


_TEXT_LINE = re.compile(r"^(?P<time>\d\d:\d\d:\d\d )?\[(?P<kind>raw |clean)\] (?P<text>.*)$")
_STATUS_LINE = re.compile(r"^(\d\d:\d\d:\d\d )?(\[[a-z ]{2,8}\]|---)")
_COUNT = re.compile(r"\d+ (words|mots)(, \d+ rewrite\(s\) refused"
                    r"| \(moved to private history\))?")
_TIME = re.compile(r"^\d\d:\d\d:\d\d ")


def migrate_plain_log(log_path, store):
    """Moves dictated text found in the old plain-text log into the encrypted
    store, then rewrites the log without it. Returns the number of entries
    moved. Status lines (times, durations, warnings) stay in the log.

    A dictation with line breaks was logged on several lines: the unlabelled
    lines right after a [raw ]/[clean] line belong to it, even when that
    first line was already moved by an earlier version of this function."""
    log_path = Path(log_path)
    if not log_path.exists():
        return 0
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    kept, entries, owner = [], [], None  # entry: [kind or None, time, lines]
    for line in lines:
        match = _TEXT_LINE.match(line)
        if match:
            counted = _COUNT.fullmatch(match["text"])
            entries.append([None if counted else match["kind"], match["time"] or "",
                            [] if counted else [match["text"]]])
            owner = len(entries) - 1
            kept.append(line if counted else owner)  # int: rewritten below
        elif owner is not None and not _STATUS_LINE.match(line):
            entries[owner][2].append(_TIME.sub("", line, count=1))
        else:
            owner = None
            kept.append(line)
    if not any(parts for _, _, parts in entries):
        return 0
    moved, pending_raw = 0, None
    for kind, _, parts in entries:
        text = "\n".join(parts)
        if kind is None:  # lines left behind by an earlier migration
            if parts:
                store.add({"legacy": True, "raw": "", "final": text})
                moved += 1
        elif kind == "raw ":
            if pending_raw is not None:
                store.add({"legacy": True, "raw": pending_raw, "final": pending_raw})
                moved += 1
            pending_raw = text
        else:
            store.add({"legacy": True, "raw": pending_raw or "", "final": text})
            moved += 1
            pending_raw = None
    if pending_raw is not None:
        store.add({"legacy": True, "raw": pending_raw, "final": pending_raw})
        moved += 1
    out = []
    for item in kept:
        if isinstance(item, int):
            kind, at, parts = entries[item]
            item = (f"{at}[{kind}] {len(' '.join(parts).split())} words "
                    f"(moved to private history)")
        out.append(item)
    tmp = log_path.with_suffix(".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, log_path)
    return moved
