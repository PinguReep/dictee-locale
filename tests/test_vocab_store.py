import numpy as np

from private_store import PrivateStore, migrate_plain_log
from vocab import Vocabulary


def test_seeded_rules_apply_with_context(tmp_path):
    v = Vocabulary(tmp_path / "v.json")
    assert v.apply_rules("je teste cloud code avec opus")[0] == \
        "je teste Claude code avec opus"
    # "cloud" without any AI context stays "cloud"
    assert v.apply_rules("mes photos sont dans le cloud")[0] == \
        "mes photos sont dans le cloud"
    assert v.apply_rules("tu connais quen ?")[0] == "tu connais Qwen ?"
    assert "Qwen" in v.hotwords()


def test_learning_activates_after_two_corrections(tmp_path):
    v = Vocabulary(tmp_path / "v.json")
    v.learn("on a testé Mixtrale hier", "on a testé Mistral hier")
    assert v.apply_rules("Mixtrale marche")[0] == "Mixtrale marche"
    v.learn("Mixtrale est rapide", "Mistral est rapide")
    assert v.apply_rules("Mixtrale marche")[0] == "Mistral marche"
    # persisted
    assert Vocabulary(tmp_path / "v.json").apply_rules("Mixtrale")[0] == "Mistral"


def test_rewrites_are_not_learned(tmp_path):
    v = Vocabulary(tmp_path / "v.json")
    assert v.learn("je pense que c'est bon", "finalement on verra demain") == []
    assert v.learn("il est grand", "il est petit") == []  # content edit


def test_store_roundtrip_is_encrypted(tmp_path):
    store = PrivateStore(tmp_path)
    audio = np.sin(np.linspace(0, 100, 16000)).astype(np.float32) * 0.5
    rid = store.add({"raw": "texte secret", "final": "Texte secret."}, audio)
    assert b"secret" not in (tmp_path / "historique.dat").read_bytes()
    assert b"RIFF" not in (tmp_path / "audio" / f"{rid}.bin").read_bytes()
    (record,) = store.records()
    assert record["final"] == "Texte secret." and record["audio"]
    back, sr = store.audio(rid)
    assert sr == 16000 and np.abs(back - audio).max() < 1e-3


def test_purge_and_clear(tmp_path):
    store = PrivateStore(tmp_path, retention_days=1)
    store.add({"final": "vieux", "at": 0}, np.zeros(1600, np.float32))
    store.add({"final": "récent"})
    assert store.purge_old() == 1
    assert [r["final"] for r in store.records()] == ["récent"]
    assert not list((tmp_path / "audio").glob("*.bin"))
    store.clear()
    assert store.records() == []


def test_migrate_plain_log(tmp_path):
    log = tmp_path / "dictation.log"
    log.write_text("10:00:00 [info] Transcribing 2.0s of audio...\n"
                   "10:00:01 [raw ] bonjour euh\n"
                   "10:00:01 [clean] Bonjour.\n"
                   "10:00:01 [info] Pasted.\n", encoding="utf-8")
    store = PrivateStore(tmp_path / "prive")
    assert migrate_plain_log(log, store) == 1
    content = log.read_text(encoding="utf-8")
    assert "bonjour" not in content.lower() and "Transcribing" in content
    assert store.records()[0]["final"] == "Bonjour."
    assert migrate_plain_log(log, store) == 0  # idempotent
