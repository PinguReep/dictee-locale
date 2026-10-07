import pytest

import main

E = main.extract_voice_command


@pytest.mark.parametrize("text, expected", [
    ("On se voit au garage, colibri envoyé, colibri envoyé", ("On se voit au garage", "send")),
    ("Merci. Colibri envoie. Colibri envoie. Colibri, envoie.", ("Merci.", "send")),
    ("Relis ça. Colibri colle, colibri, colle", ("Relis ça.", "paste")),
    ("Bonjour Paul, à demain. Colibri, envoie.", ("Bonjour Paul, à demain.", "send")),
    ("Top. Colibri envoi", ("Top.", "send")),
    ("Top. Colibri, envoyer.", ("Top.", "send")),
    ("Top. Colibri envoie-le.", ("Top.", "send")),
    ("Top. Colibri, envoie ça.", ("Top.", "send")),
    ("Top. Colibri en voie.", ("Top.", "send")),
    ("Top. Colibri, au revoir.", ("Top.", "send")),
    ("Top. Kolibri envoi", ("Top.", "send")),
    ("Top. Coli bri, envoie.", ("Top.", "send")),
    ("Top. Call Libri, call.", ("Top.", "paste")),
    ("Top. Colibri, collé.", ("Top.", "paste")),
    ("Top. Colibri, col.", ("Top.", "paste")),
    ("Top. Colibri-colle", ("Top.", "paste")),
    ("y'a pas de soucis, colibricole", ("y'a pas de soucis", "paste")),
    ("Ok. Colibrienvoie.", ("Ok.", "send")),
    ("See you. Colibri, send.", ("See you.", "send")),
    ("Thanks a lot. Colibri, send it.", ("Thanks a lot.", "send")),
    ("Here is the plan. Calibri, paste this.", ("Here is the plan.", "paste")),
    ("Sounds good. Colibri paste.", ("Sounds good.", "paste")),
    ("Colibri, envoie.", ("", "send")),
    ("ok Colibri envoie", ("ok", "send")),
    # must not trigger
    ("Le colibri colle sa fleur puis vole", ("Le colibri colle sa fleur puis vole", None)),
    ("Sur la colline, colle", ("Sur la colline, colle", None)),
    ("Je colle le lien et je t'envoie", ("Je colle le lien et je t'envoie", None)),
    ("pas moi, dicter, colle", ("pas moi, dicter, colle", None)),
    ("tu peux coller dès maintenant", ("tu peux coller dès maintenant", None)),
])
def test_extract_voice_command(text, expected):
    assert E(text) == expected


def test_live_fallback_strips_odd_spelling():
    assert E("merci pour tout, dicter, call", assume_command="paste") == \
        ("merci pour tout", "paste")


class Harness:
    def __init__(self, locked=False, physical=None):
        self.state, self.locked, self.events, self.physical = "idle", locked, [], physical
        self.c = main.HotkeyController(
            {"ctrl", "alt"}, lambda: self.state, lambda: self.locked,
            self.start, self.stop,
            is_down=(lambda k: k in self.physical) if physical is not None else None)

    def start(self):
        self.state = "recording"
        self.events.append("start")

    def stop(self):
        self.state = "idle"
        self.events.append("stop")

    def keys(self, *seq):
        for item in seq:
            self.c.handle(item[1:], item[0] == "+")


def test_push_to_talk():
    h = Harness()
    h.keys("+ctrl", "+alt", "-alt")
    assert h.events == ["start", "stop"]


def test_hands_free_tap_tap():
    h = Harness(locked=True)
    h.keys("+ctrl", "+alt", "-alt", "-ctrl")
    assert (h.events, h.state) == (["start"], "recording")
    h.keys("+ctrl", "+alt", "-alt", "-ctrl")
    assert h.events == ["start", "stop"]


def test_altgr_character_does_not_send():
    h = Harness(locked=True)
    h.keys("+ctrl", "+alt", "-alt", "-ctrl")
    h.keys("+ctrl", "+alt", "+0", "-0", "-alt", "-ctrl")
    assert h.state == "recording"


def test_stuck_keys_recovered():
    phys = {"ctrl", "alt"}
    h = Harness(physical=phys)
    h.keys("+ctrl", "+alt")
    h.state = "idle"
    phys.clear()
    h.c.down_since = {k: v - 5 for k, v in h.c.down_since.items()}
    h.keys("+shift")
    assert h.c.pressed == {"shift"}
    phys.update({"ctrl", "alt"})
    h.keys("-shift", "+ctrl", "+alt")
    assert h.events[-1] == "start"
