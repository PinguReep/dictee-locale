"""Local transcription endpoint for Rémy (or any OpenAI-compatible client on
this PC): POST /v1/audio/transcriptions.

Same chain as hotkey dictation -- the Whisper model already loaded, the learned
vocabulary, the faithful cleanup -- without any of the desktop parts: no review
box, no history, no paste, no sound. The audio stays in memory and is never
written. Listens on 127.0.0.1 only (`api_port` in config.json, null = off).
"""

import io
import json
import threading
import time
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BYTES = 25 * 1024 * 1024  # same ceiling as OpenAI's endpoint
PATH = "/v1/audio/transcriptions"


def parse_multipart(content_type, body):
    """Returns (fields, files) from a multipart/form-data body."""
    head = (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode("latin-1")
    msg = BytesParser(policy=email_policy).parsebytes(head + body)
    fields, files = {}, {}
    if not msg.is_multipart():
        return fields, files
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        data = part.get_payload(decode=True) or b""
        if part.get_filename() is not None:
            files[name] = data
        else:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files


def run_pipeline(audio, language, deps):
    """Transcribes, applies the vocabulary rules and the faithful cleanup.
    Returns (text, voice command or None)."""
    vocabulary = deps["vocabulary"]
    text, detected = deps["transcribe"](audio, vocabulary.hotwords(), language)
    command = None
    if deps.get("voice_commands") and text:
        text, command = deps["extract_command"](text)
    if not text:
        return "", command
    text, _ = vocabulary.apply_rules(text)
    cleaned = deps["clean"](text, detected, vocabulary.terms())
    if cleaned:
        text = cleaned[0]
    return text, command


class Handler(BaseHTTPRequestHandler):
    server_version = "DicteeLocale"

    def log_message(self, fmt, *args):  # never log request lines
        pass

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message):
        self._send(status, {"error": {"message": message, "type": "dictee_locale"}})

    def _host_ok(self):
        # Loopback only, by name too: a web page cannot rebind its own domain
        # to 127.0.0.1 and read the answer.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1")

    def do_GET(self):
        if not self._host_ok():
            return self._error(403, "host")
        if self.path in ("/health", "/v1/health"):
            return self._send(200, {"ok": True})
        if self.path == "/v1/models":
            return self._send(200, {"object": "list", "data": [
                {"id": self.server.deps["model_name"], "object": "model", "owned_by": "dictee-locale"}]})
        return self._error(404, "not found")

    def do_POST(self):
        if not self._host_ok():
            return self._error(403, "host")
        if self.path.split("?")[0] != PATH:
            return self._error(404, "not found")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return self._error(400, "empty body")
        if length > MAX_BYTES:
            return self._error(413, "audio too large (25 MB max)")
        content_type = self.headers.get("Content-Type") or ""
        if "multipart/form-data" not in content_type:
            return self._error(400, "multipart/form-data expected")
        fields, files = parse_multipart(content_type, self.rfile.read(length))
        data = files.get("file")
        if not data:
            return self._error(400, "missing 'file'")
        language = fields.get("language")
        if language not in ("fr", "en"):
            language = self.server.deps["language"]()
        deps = self.server.deps
        started = time.time()
        try:
            audio = deps["decode"](io.BytesIO(data))
            with self.server.lock:
                text, command = run_pipeline(audio, language, deps)
        except Exception as exc:  # undecodable audio, model or cleanup failure
            print(f"[error] API transcription failed: {type(exc).__name__}: {exc}")
            return self._error(500, "transcription failed")
        # Stats only, never the text (same rule as dictation.log).
        print(f"[api ] {len(audio) / 16000:.1f}s -> {len(text.split())} words "
              f"in {time.time() - started:.1f}s" + (f", command {command}" if command else ""))
        if fields.get("response_format") == "text":
            body = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None
        return self._send(200, {"text": text, "command": command})


def start(port, deps):
    """Starts the endpoint in a daemon thread; returns the server."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.deps = deps
    server.lock = threading.Lock()  # one API transcription at a time
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[info] Local transcription API on http://127.0.0.1:{port}{PATH}")
    return server
