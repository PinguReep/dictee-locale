"""Mutes Discord itself (its own mute button) while a dictation records.

Talks to the running Discord client over its local RPC pipe
(\\\\.\\pipe\\discord-ipc-N): GET_VOICE_SETTINGS to read the current mute
state, SET_VOICE_SETTINGS {mute: true} at recording start, and the previous
state put back at the end. A mic that was already muted stays muted. This
is independent of headsets and of the Windows mixer.

Discord only allows rpc.voice.* calls to an application the user owns, so a
one-time setup is needed (see README): a Discord application whose client
id and secret are in config.json; the first use shows Discord's "Authorize"
prompt and the tokens are then saved in config.json and refreshed.

Nothing here raises: Discord closed, no credentials, authorization refused
or a stale token only log a line.
"""

import json
import os
import struct
import threading
import time
import uuid

import requests

OP_HANDSHAKE, OP_FRAME, OP_CLOSE = 0, 1, 2
SCOPES = ["rpc", "rpc.voice.read", "rpc.voice.write"]
TOKEN_URL = "https://discord.com/api/oauth2/token"
AUTHORIZE_TIMEOUT = 120  # seconds to click "Authorize" in Discord
RPC_TIMEOUT = 5


class DiscordRPCError(Exception):
    pass


class DiscordRPC:
    """Minimal synchronous client for Discord's local RPC pipe."""

    def __init__(self, client_id):
        self.client_id = str(client_id)
        self.pipe = None

    def connect(self):
        last = None
        for n in range(10):
            try:
                self.pipe = open(rf"\\.\pipe\discord-ipc-{n}", "r+b", buffering=0)
                break
            except OSError as exc:
                last = exc
        if self.pipe is None:
            raise DiscordRPCError(f"Discord is not running ({last})")
        self._send(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
        ready = self._read(timeout=RPC_TIMEOUT)
        if ready.get("evt") != "READY":
            raise DiscordRPCError(f"unexpected handshake reply: {ready}")

    def close(self):
        if self.pipe is not None:
            try:
                self._send(OP_CLOSE, {})
            except Exception:
                pass
            try:
                self.pipe.close()
            except Exception:
                pass
            self.pipe = None

    def command(self, cmd, args=None, timeout=RPC_TIMEOUT):
        nonce = str(uuid.uuid4())
        self._send(OP_FRAME, {"cmd": cmd, "args": args or {}, "nonce": nonce})
        deadline = time.time() + timeout
        while True:
            reply = self._read(timeout=max(0.1, deadline - time.time()))
            if reply.get("nonce") != nonce:
                continue  # an event or another reply: skip
            if reply.get("evt") == "ERROR":
                data = reply.get("data") or {}
                raise DiscordRPCError(
                    f"{cmd}: {data.get('message')} (code {data.get('code')})")
            return reply.get("data") or {}

    def _send(self, opcode, payload):
        body = json.dumps(payload).encode("utf-8")
        self.pipe.write(struct.pack("<II", opcode, len(body)) + body)

    def _read(self, timeout):
        """Reads one frame. The pipe has no timeout: read in a helper
        thread and give up (closing the pipe) when the deadline passes."""
        result = {}

        def reader():
            try:
                header = self.pipe.read(8)
                if len(header) < 8:
                    result["error"] = "pipe closed"
                    return
                opcode, length = struct.unpack("<II", header)
                body = b""
                while len(body) < length:
                    chunk = self.pipe.read(length - len(body))
                    if not chunk:
                        break
                    body += chunk
                result["opcode"] = opcode
                result["frame"] = json.loads(body.decode("utf-8") or "{}")
            except Exception as exc:
                result["error"] = str(exc)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            self.close()
            raise DiscordRPCError("no reply from Discord in time")
        if "error" in result:
            raise DiscordRPCError(result["error"])
        if result.get("opcode") == OP_CLOSE:
            raise DiscordRPCError(f"Discord closed the connection: "
                                  f"{result.get('frame')}")
        return result.get("frame") or {}


class DiscordMuter:
    """engage() at recording start, release() at recording end.

    Both return immediately and work in a background thread; release() is
    safe to call even if engage() never ran or is still connecting."""

    def __init__(self, config, save_config, log=print):
        self.config = config
        self.save_config = save_config
        self.log = log
        self._lock = threading.Lock()
        self.wanted = False
        self._previous = None  # mute state before we touched it
        self._busy = False

    # ----------------------------------------------------------- public --

    @property
    def configured(self):
        return bool(self.config.get("discord_client_id")
                    and self.config.get("discord_client_secret"))

    def engage(self):
        self.wanted = True
        threading.Thread(target=self._engage_now, daemon=True).start()

    def release(self):
        self.wanted = False
        threading.Thread(target=self.restore, daemon=True).start()

    def restore(self):
        with self._lock:
            if self._previous is None:
                return
            previous, self._previous = self._previous, None
            try:
                self._with_rpc(lambda rpc: rpc.command(
                    "SET_VOICE_SETTINGS", {"mute": previous}))
                self.log(f"[info] Discord mute put back to "
                         f"{'muted' if previous else 'unmuted'}.")
            except DiscordRPCError as exc:
                self.log(f"[warn] Discord unmute failed: {exc}")

    # ---------------------------------------------------------- internal --

    def _engage_now(self):
        if not self.configured:
            self.log("[warn] Discord mute: set discord_client_id and "
                     "discord_client_secret in config.json (see README).")
            return
        with self._lock:
            if self._busy or self._previous is not None:
                return
            self._busy = True
        try:
            def do(rpc):
                settings = rpc.command("GET_VOICE_SETTINGS")
                previous = bool(settings.get("mute"))
                if not previous:
                    rpc.command("SET_VOICE_SETTINGS", {"mute": True})
                return previous
            previous = self._with_rpc(do)
            with self._lock:
                self._previous = previous
            self.log("[info] Discord microphone muted."
                     if not previous else
                     "[info] Discord was already muted: left as is.")
        except DiscordRPCError as exc:
            self.log(f"[warn] Discord mute failed: {exc}")
        finally:
            with self._lock:
                self._busy = False
        if not self.wanted:  # the recording ended while we were connecting
            self.restore()

    def _with_rpc(self, action):
        """Connects, authenticates (refreshing or authorizing as needed),
        runs `action(rpc)` and closes the pipe."""
        rpc = DiscordRPC(self.config["discord_client_id"])
        rpc.connect()
        try:
            self._authenticate(rpc)
            return action(rpc)
        finally:
            rpc.close()

    def _authenticate(self, rpc):
        auth = self.config.get("discord_auth") or {}
        token = auth.get("access_token")
        if token and auth.get("expires_at", 0) < time.time() + 60:
            token = self._refresh(auth)
        if not token:
            token = self._authorize(rpc)
        try:
            rpc.command("AUTHENTICATE", {"access_token": token})
        except DiscordRPCError:
            # Stale or revoked token: ask Discord again, once.
            token = self._authorize(rpc)
            rpc.command("AUTHENTICATE", {"access_token": token})

    def _authorize(self, rpc):
        self.log("[info] Discord: waiting for you to click Authorize in "
                 "Discord...")
        data = rpc.command("AUTHORIZE", {"client_id": self.config["discord_client_id"],
                                         "scopes": SCOPES},
                           timeout=AUTHORIZE_TIMEOUT)
        return self._exchange({"grant_type": "authorization_code",
                               "code": data.get("code")})

    def _refresh(self, auth):
        try:
            return self._exchange({"grant_type": "refresh_token",
                                   "refresh_token": auth.get("refresh_token")})
        except DiscordRPCError as exc:
            self.log(f"[warn] Discord token refresh failed: {exc}")
            return None

    def _exchange(self, params):
        form = {"client_id": self.config["discord_client_id"],
                "client_secret": self.config["discord_client_secret"],
                **params}
        if params["grant_type"] == "authorization_code":
            form["redirect_uri"] = self.config.get("discord_redirect_uri",
                                                   "http://127.0.0.1")
        try:
            r = requests.post(TOKEN_URL, data=form, timeout=15)
            if r.status_code != 200 and "redirect_uri" in form:
                del form["redirect_uri"]  # some apps have no redirect set
                r = requests.post(TOKEN_URL, data=form, timeout=15)
            if r.status_code != 200:
                raise DiscordRPCError(f"token exchange failed: {r.text[:200]}")
            tokens = r.json()
        except requests.RequestException as exc:
            raise DiscordRPCError(f"token exchange failed: {exc}")
        self.config["discord_auth"] = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "expires_at": time.time() + float(tokens.get("expires_in", 0)),
        }
        self.save_config(self.config)
        return tokens["access_token"]
