import tkinter as tk

import pytest

from review_box import ReviewBox, back_span, delete_word, forward_span


@pytest.mark.parametrize("before, deleted", [
    ("Salut tout le monde", "monde"),
    ("Salut tout le monde   ", "monde   "),
    ("on se voit demain.", "."),
    ("c'est aujourd'hui", "aujourd'hui"),
    ("un truc peut-être", "peut-être"),
    ("", ""),
])
def test_back_span(before, deleted):
    assert before[len(before) - back_span(before):] == deleted


@pytest.mark.parametrize("after, deleted", [
    ("Salut tout le monde", "Salut "),
    ("   Salut", "   "),
    ("... et puis", "... "),
    ("l'IA marche", "l'IA "),
    ("", ""),
])
def test_forward_span(after, deleted):
    assert after[:forward_span(after)] == deleted


@pytest.fixture(scope="module")
def root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def test_delete_word_in_text(root):
    text = tk.Text(root)
    text.insert("1.0", "Envoie le lien du dépôt GitHub")
    text.mark_set("insert", "end-1c")
    delete_word(text, forward=False)
    assert text.get("1.0", "end-1c") == "Envoie le lien du dépôt "
    text.mark_set("insert", "1.0")
    delete_word(text, forward=True)
    assert text.get("1.0", "end-1c") == "le lien du dépôt "
    text.tag_add("sel", "1.0", "1.3")  # a selection is deleted as a whole
    delete_word(text, forward=False)
    assert text.get("1.0", "end-1c") == "lien du dépôt "


class FakeRoot:
    def __init__(self):
        self.calls = []

    def after(self, _ms, function):
        self.calls.append(function)


def test_enter_and_escape_only_answer_a_shown_unfocused_box():
    box = ReviewBox(FakeRoot())
    assert not box.intercept("enter")          # no box: Entrée goes to the app
    box.visible = True
    assert box.intercept("enter") and box.root.calls == [box.validate]
    assert box.intercept("esc") and box.root.calls[-1] == box.cancel
    box.activated = True                       # focused box: Tk handles keys
    assert not box.intercept("enter")
