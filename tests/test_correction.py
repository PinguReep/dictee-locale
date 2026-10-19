"""A correction reported from Rémy: active at once, a proper noun joins the
terms, and the endpoint stays loopback only."""

import http.client
import json

import pytest

import local_api
from vocab import Vocabulary


def test_a_reported_correction_is_active_at_once(tmp_path):
    v = Vocabulary(tmp_path / "v.json")
    rule = v.correct("Rémi Sanchez", "Rémy Sanchez")
    assert rule["active"] and rule["source"] == "remy"
    assert v.apply_rules("dis à rémi sanchez de venir")[0] == "dis à Rémy Sanchez de venir"
    assert "Rémy Sanchez" in v.terms()
    # Kept on disk, like the review-box rules.
    assert Vocabulary(tmp_path / "v.json").apply_rules("Rémi Sanchez")[0] == "Rémy Sanchez"


def test_an_accent_or_a_capital_can_be_corrected_on_purpose(tmp_path):
    v = Vocabulary(tmp_path / "v.json")
    v.correct("leo", "Léo")
    assert v.apply_rules("appelle leo demain")[0] == "appelle Léo demain"


@pytest.mark.parametrize("heard,wanted", [("", "x"), ("x", ""), ("même", "même"),
                                          ("un deux trois quatre cinq", "x"), ("x" * 81, "y")])
def test_a_bad_pair_is_refused(tmp_path, heard, wanted):
    with pytest.raises(ValueError):
        Vocabulary(tmp_path / "v.json").correct(heard, wanted)


def post(port, body, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"}
    if host:
        headers["Host"] = host
    conn.request("POST", local_api.CORRECTIONS, json.dumps(body).encode(), headers)
    r = conn.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def test_endpoint_learns_and_refuses_foreign_hosts(tmp_path):
    v = Vocabulary(tmp_path / "v.json")
    server = local_api.start(0, {"vocabulary": v})
    port = server.server_address[1]
    try:
        assert post(port, {"entendu": "Mixtrale", "voulu": "Mistral"}) == \
            (200, {"ok": True, "de": "mixtrale", "vers": "Mistral", "active": True})
        assert v.apply_rules("Mixtrale marche")[0] == "Mistral marche"
        assert post(port, {"entendu": "", "voulu": "x"})[0] == 400
        assert post(port, {"entendu": "a", "voulu": "b"}, host="evil.example")[0] == 403
    finally:
        server.shutdown()
