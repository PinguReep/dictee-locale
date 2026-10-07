import pytest

from fidelity import constrain

TERMS = ["Claude Code", "Claude", "Opus", "Qwen"]


@pytest.mark.parametrize("raw, llm, expected", [
    # register kept
    ("euh t'as vu le le truc", "Tu as vu le truc ?", "T'as vu le truc ?"),
    ("ouais c'est bon pour les infos", "Oui, c'est bon pour les informations.",
     "Ouais, c'est bon pour les infos."),
    ("j'aimerais qu'on a fini", "Je voudrais que nous avons fini.",
     "J'aimerais qu'on a fini."),
    # meaning never inverted, words never added
    ("j'ai compris", "Je n'ai pas compris.", "J'ai compris."),
    ("bah faut que je push la feature", "Il faut que je pousse la fonctionnalité.",
     "Faut que je push la feature."),
    ("il reste 3 tâches", "Il reste trois tâches.", "Il reste 3 tâches."),
    # allowed: fillers, stutters, corrected false start, punctuation
    ("euh je je voulais dire bonjour", "Je voulais dire bonjour.",
     "Je voulais dire bonjour."),
    ("on se voit lundi non plutôt mardi", "On se voit mardi.", "On se voit mardi."),
    ("qu'on qu'on regarde ça", "Qu'on regarde ça.", "Qu'on regarde ça."),
    # allowed: spelling-only and vocabulary terms
    ("est ce que tu viens", "Est-ce que tu viens ?", "Est-ce que tu viens ?"),
    ("je teste cloud code avec opus", "Je teste Claude Code avec Opus.",
     "Je teste Claude Code avec Opus."),
    ("tu connais quen", "Tu connais Qwen ?", "Tu connais Qwen ?"),
])
def test_constrain(raw, llm, expected):
    assert constrain(raw, llm, TERMS)[0] == expected


def test_partial_spelling_kept_rewording_refused():
    text, refused = constrain("est ce que ya un souci", "Est-ce qu'il y a un souci ?")
    assert text.startswith("Est-ce que")
    assert "ya un souci" in text and "il y a" not in text
    assert refused == 1


def test_no_change_means_no_refusal():
    assert constrain("bonjour tout le monde", "Bonjour tout le monde.") == \
        ("Bonjour tout le monde.", 0)


def test_empty_model_output_keeps_raw():
    assert constrain("bonjour", "") == ("bonjour", 1)


def test_hesitations_always_dropped():
    from fidelity import drop_hesitations
    assert drop_hesitations("Euh, je voulais dire. euh bonjour") == "Je voulais dire. Bonjour"
    assert drop_hesitations("Le humour et la hummus") == "Le humour et la hummus"
