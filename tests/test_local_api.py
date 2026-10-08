"""Local transcription endpoint (local_api.py): the hotkey chain without the
desktop parts, loopback only, nothing kept."""

import http.client
import json

import local_api


class FakeVocabulary:
    def hotwords(self):
        return "Rémy, Motion"

    def terms(self):
        return ["Rémy", "Motion"]

    def apply_rules(self, text):
        return text.replace("remi", "Rémy"), 1


def deps(**over):
    calls = {"clean": 0}

    def clean(text, language, terms):
        calls["clean"] += 1
        return text.replace("euh ", ""), 0

    base = {
        "vocabulary": FakeVocabulary(),
        "transcribe": lambda audio, hotwords, language: ("euh dis à remi bonjour. Colibri, envoie.", language),
        "extract_command": lambda text: (text.replace(" Colibri, envoie.", ""), "send"),
        "clean": clean,
        "voice_commands": True,
        "language": lambda: "fr",
        "decode": lambda f: [0.0] * 16000,
        "model_name": "large-v3-turbo",
    }
    base.update(over)
    return base, calls


def multipart(fields, file_bytes):
    boundary = "----remy"
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.webm"\r\n'
        f"Content-Type: audio/webm\r\n\r\n".encode() + file_bytes + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", b"".join(parts)


def test_parse_multipart_reads_fields_and_file():
    ctype, body = multipart({"language": "fr", "model": "x"}, b"\x00\x01audio")
    fields, files = local_api.parse_multipart(ctype, body)
    assert fields == {"language": "fr", "model": "x"}
    assert files["file"] == b"\x00\x01audio"


def test_pipeline_applies_vocabulary_cleanup_and_command():
    d, calls = deps()
    text, command = local_api.run_pipeline([0.0], "fr", d)
    assert text == "dis à Rémy bonjour."
    assert command == "send"
    assert calls["clean"] == 1


def test_endpoint_end_to_end_without_review_or_history():
    d, _ = deps()
    server = local_api.start(0, d)
    port = server.server_address[1]
    try:
        ctype, body = multipart({"language": "fr", "response_format": "json"}, b"audio")
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("POST", local_api.PATH, body, {"Content-Type": ctype})
        r = conn.getresponse()
        assert r.status == 200
        assert json.loads(r.read()) == {"text": "dis à Rémy bonjour.", "command": "send"}

        # A foreign Host (DNS rebinding from a web page) is refused.
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("POST", local_api.PATH, body, {"Content-Type": ctype, "Host": "evil.example"})
        assert conn.getresponse().status == 403

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("POST", local_api.PATH, b"x", {"Content-Type": "text/plain"})
        assert conn.getresponse().status == 400
    finally:
        server.shutdown()
