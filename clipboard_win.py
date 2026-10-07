"""Native Windows clipboard: private text + full save/restore.

- Dictated text is placed on the clipboard with the formats that keep it out
  of the Win+V history and out of cloud clipboard sync.
- The previous clipboard is saved in every format (text, images, files,
  HTML...) and restored after the paste, instead of text only.
"""

import ctypes
import ctypes.wintypes as wt
import struct
import time

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
# GDI-handle formats (not global memory) are skipped: Windows synthesizes
# them again from CF_DIB / CF_UNICODETEXT.
_SKIP_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}
_MAX_FORMAT_BYTES = 64 * 1024 * 1024

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.OpenClipboard.argtypes = [wt.HWND]
_user32.OpenClipboard.restype = wt.BOOL
_user32.CloseClipboard.restype = wt.BOOL
_user32.EmptyClipboard.restype = wt.BOOL
_user32.EnumClipboardFormats.argtypes = [wt.UINT]
_user32.EnumClipboardFormats.restype = wt.UINT
_user32.GetClipboardData.argtypes = [wt.UINT]
_user32.GetClipboardData.restype = wt.HANDLE
_user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
_user32.SetClipboardData.restype = wt.HANDLE
_user32.RegisterClipboardFormatW.argtypes = [wt.LPCWSTR]
_user32.RegisterClipboardFormatW.restype = wt.UINT
_kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wt.HGLOBAL
_kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
_kernel32.GlobalUnlock.restype = wt.BOOL
_kernel32.GlobalSize.argtypes = [wt.HGLOBAL]
_kernel32.GlobalSize.restype = ctypes.c_size_t
_kernel32.GlobalFree.argtypes = [wt.HGLOBAL]
_kernel32.GlobalFree.restype = wt.HGLOBAL

_PRIVACY_FORMATS = (
    ("ExcludeClipboardContentFromMonitorProcessing", b"\x00"),
    ("CanIncludeInClipboardHistory", struct.pack("<I", 0)),
    ("CanUploadToCloudClipboard", struct.pack("<I", 0)),
)


class _Open:
    """Opens the clipboard, retrying while another app holds it."""

    def __enter__(self):
        for _ in range(50):
            if _user32.OpenClipboard(None):
                return self
            time.sleep(0.02)
        raise OSError("clipboard busy")

    def __exit__(self, *exc):
        _user32.CloseClipboard()


def _put(fmt, data):
    handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
    if not handle:
        return
    pointer = _kernel32.GlobalLock(handle)
    if pointer:
        ctypes.memmove(pointer, data, len(data))
        _kernel32.GlobalUnlock(handle)
    if not _user32.SetClipboardData(fmt, handle):
        _kernel32.GlobalFree(handle)  # ownership stays with us on failure


def _mark_private():
    for name, value in _PRIVACY_FORMATS:
        fmt = _user32.RegisterClipboardFormatW(name)
        if fmt:
            _put(fmt, value)


def snapshot():
    """Every clipboard format as [(format, bytes)], to restore later."""
    saved = []
    with _Open():
        fmt = 0
        while True:
            fmt = _user32.EnumClipboardFormats(fmt)
            if not fmt:
                break
            if fmt in _SKIP_FORMATS:
                continue
            handle = _user32.GetClipboardData(fmt)
            if not handle:
                continue
            size = _kernel32.GlobalSize(handle)
            if not size or size > _MAX_FORMAT_BYTES:
                continue
            pointer = _kernel32.GlobalLock(handle)
            if not pointer:
                continue
            try:
                saved.append((fmt, ctypes.string_at(pointer, size)))
            finally:
                _kernel32.GlobalUnlock(handle)
    return saved


def set_private_text(text):
    """Puts text on the clipboard, excluded from Win+V history and sync."""
    with _Open():
        _user32.EmptyClipboard()
        _put(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
        _mark_private()


def restore(saved):
    """Puts back a snapshot() (without adding it to the Win+V history)."""
    with _Open():
        _user32.EmptyClipboard()
        for fmt, data in saved:
            _put(fmt, data)
        if saved:
            _mark_private()


def get_text():
    """Current clipboard text, or None (used by tests)."""
    with _Open():
        handle = _user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = _kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(pointer) if pointer else None
        finally:
            _kernel32.GlobalUnlock(handle)
