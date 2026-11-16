"""Pauses Spotify while a dictation records, and resumes it afterwards.

Uses Windows' media session manager (the one behind the volume flyout's
media controls), so it acts on Spotify itself whatever the audio device.
Only a track that is actually playing is paused, and only a track we paused
is resumed: music already paused stays paused.

Nothing here raises: Spotify closed or the WinRT bindings missing only log
a line.
"""

import asyncio
import threading

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
    )
    HAVE_WINRT = True
except Exception:  # pragma: no cover - optional dependency
    HAVE_WINRT = False


async def _spotify_session():
    manager = await SessionManager.request_async()
    for session in manager.get_sessions():
        if "spotify" in (session.source_app_user_model_id or "").lower():
            return session
    return None


async def _pause_if_playing():
    session = await _spotify_session()
    if session is None:
        return None
    if session.get_playback_info().playback_status != Status.PLAYING:
        return False
    return bool(await session.try_pause_async())


async def _resume():
    session = await _spotify_session()
    return session is not None and bool(await session.try_play_async())


class SpotifyPauser:
    """engage() at recording start, release() at recording end."""

    def __init__(self, log=print):
        self.log = log
        self._lock = threading.Lock()
        self.wanted = False
        self._paused_by_us = False
        self._busy = False

    def engage(self):
        self.wanted = True
        threading.Thread(target=self._engage_now, daemon=True).start()

    def release(self):
        self.wanted = False
        threading.Thread(target=self.restore, daemon=True).start()

    def restore(self):
        with self._lock:
            if not self._paused_by_us:
                return
            self._paused_by_us = False
        try:
            ok = asyncio.run(_resume())
            self.log("[info] Spotify resumed." if ok
                     else "[warn] Spotify could not be resumed.")
        except Exception as exc:
            self.log(f"[warn] Spotify resume failed: {exc}")

    def _engage_now(self):
        if not HAVE_WINRT:
            self.log("[warn] Spotify pause unavailable: winrt not installed.")
            return
        with self._lock:
            if self._busy or self._paused_by_us:
                return
            self._busy = True
        try:
            paused = asyncio.run(_pause_if_playing())
            if paused is None:
                self.log("[info] Spotify pause: Spotify is not open.")
            elif paused:
                with self._lock:
                    self._paused_by_us = True
                self.log("[info] Spotify paused.")
        except Exception as exc:
            self.log(f"[warn] Spotify pause failed: {exc}")
        finally:
            with self._lock:
                self._busy = False
        if not self.wanted:  # the recording ended while we were pausing
            self.restore()
