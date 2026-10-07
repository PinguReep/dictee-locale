"""Faithful cleanup: the LLM may only punctuate and drop disfluencies.

The model output is aligned word by word with the transcript, and each
difference is accepted only if it is one of:
  - removal of a filler ("euh", "bah"...) or of a stutter ("je je");
  - removal of a false start that the speaker corrected ("lundi, non, mardi");
  - a spelling-only change ("est ce" -> "est-ce", case, accents);
  - writing a vocabulary term ("cloud" -> "Claude").
Anything else (rewording, register changes, added words, a negation...) is
undone: the transcript's own words are put back.
"""

import re
import unicodedata
from difflib import SequenceMatcher

FILLERS = {"euh", "euhh", "heu", "hum", "humm", "hmm", "mmh", "mh", "bah",
           "ben", "um", "uh", "uhm", "er", "erm"}
CORRECTION_MARKERS = {"non", "pardon", "attends", "plutot", "enfin", "oups",
                      "no", "wait", "sorry", "rather", "mean"}
MAX_FALSE_START = 6

_WORD = re.compile(r"[\w'’-]+")


def _key(word):
    decomposed = unicodedata.normalize("NFKD", word.lower().replace("’", "'"))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _letters(keys):
    return "".join(k.replace("-", "").replace("'", "") for k in keys)


def _pieces(text):
    """[(word, separator that follows it)] plus the leading separator."""
    matches = list(_WORD.finditer(text))
    if not matches:
        return text, []
    lead = text[:matches[0].start()]
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(), text[m.end():end]))
    return lead, out


def _removal_ok(raw_keys, i1, i2):
    removed = raw_keys[i1:i2]
    if all(k in FILLERS for k in removed):
        return True
    # stutter: each removed word repeats a neighbour ("je je", "qu'on qu'on")
    if all((i > 0 and raw_keys[i - 1] == raw_keys[i])
           or (i + 1 < len(raw_keys) and raw_keys[i + 1] == raw_keys[i])
           or raw_keys[i] in FILLERS for i in range(i1, i2)):
        return True
    # repeated multi-word chunk ("on devrait on devrait")
    n = i2 - i1
    if raw_keys[i1:i2] == raw_keys[i2:i2 + n] or (i1 >= n and raw_keys[i1 - n:i1] == raw_keys[i1:i2]):
        return True
    # false start the speaker corrected ("lundi non plutôt mardi")
    return n <= MAX_FALSE_START and any(k in CORRECTION_MARKERS for k in removed)


def _replace_ok(raw_keys, i1, i2, new_words, terms):
    if _letters(raw_keys[i1:i2]) == _letters(_key(w) for w in new_words):
        return True  # spelling only
    candidate = " ".join(new_words)
    if _key(candidate) in terms:
        heard = " ".join(raw_keys[i1:i2])
        return SequenceMatcher(None, heard, _key(candidate)).ratio() >= 0.5
    return False


def _spelling_groups(raw_keys, clean_keys, i, i2, j, j2):
    """Longest run of word groups whose letters match ("est ce" ~ "est-ce").
    Returns the (i, j) reached."""
    while i < i2 and j < j2:
        ra = ca = ""
        ii, jj = i, j
        while ii < i2 or jj < j2:
            if (len(ra) <= len(ca) and ii < i2) or jj >= j2:
                ra += _letters([raw_keys[ii]])
                ii += 1
            else:
                ca += _letters([clean_keys[jj]])
                jj += 1
            if ra == ca:
                break
            if not (ra.startswith(ca) or ca.startswith(ra)):
                return i, j
        if ra != ca:
            return i, j
        i, j = ii, jj
    return i, j


def constrain(raw, cleaned, terms=()):
    """Returns (faithful text, number of refused edits)."""
    terms = {_key(t) for t in terms}
    raw_lead, raw_pieces = _pieces(raw)
    lead, clean_pieces = _pieces(cleaned)
    if not raw_pieces:
        return cleaned, 0
    if not clean_pieces:
        return raw, 1
    raw_keys = [_key(w) for w, _ in raw_pieces]
    clean_keys = [_key(w) for w, _ in clean_pieces]
    out, refused = [], 0

    def put_back(words, sep):
        """Original words, carrying the punctuation the model put after the
        span (so a restored word keeps the sentence's final period)."""
        kept = [w for w in words if _key(w) not in FILLERS]
        if kept:
            out.extend((w, " ") for w in kept[:-1])
            out.append((kept[-1], sep))
        elif out and sep.strip():
            out[-1] = (out[-1][0], sep)

    ops = SequenceMatcher(None, raw_keys, clean_keys, autojunk=False).get_opcodes()
    for op, i1, i2, j1, j2 in ops:
        if op == "equal":
            out.extend(clean_pieces[j1:j2])
        elif op == "delete":
            if not _removal_ok(raw_keys, i1, i2):
                refused += 1
                out.extend((w, " ") for w, _ in raw_pieces[i1:i2])
        elif op == "insert":
            refused += 1  # never add words the speaker did not say
            if out and clean_pieces[j2 - 1][1].strip():
                out[-1] = (out[-1][0], clean_pieces[j2 - 1][1])
        else:  # replace
            new_words = [w for w, _ in clean_pieces[j1:j2]]
            if _replace_ok(raw_keys, i1, i2, new_words, terms):
                out.extend(clean_pieces[j1:j2])
                continue
            i, j = _spelling_groups(raw_keys, clean_keys, i1, i2, j1, j2)
            out.extend(clean_pieces[j1:j])
            if i < i2 or j < j2:
                refused += 1
                put_back([w for w, _ in raw_pieces[i:i2]], clean_pieces[j2 - 1][1])
    text = lead + "".join(w + sep for w, sep in out)
    text = re.sub(r"\s+([,.…])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    text = drop_hesitations(text)
    if text and cleaned[:1].isupper():
        text = text[0].upper() + text[1:]
    return text, refused


_HESITATION = re.compile(r"(?i)(?<![\w'’-])(euh+|heu+|hum+|hmm+|mmh+|uh+|um+)(?![\w'’-])[,.…]?\s*")


def drop_hesitations(text):
    """Removes pure hesitation sounds the model left, never real words."""
    out = _HESITATION.sub("", text)
    out = re.sub(r"([.!?…]\s+)([a-zà-ÿ])", lambda m: m[1] + m[2].upper(), out)
    out = out.strip()
    if out and text[:1].isupper():
        out = out[0].upper() + out[1:]
    return out


CLEANUP_SYSTEM_PROMPT = """Tu nettoies des transcriptions de dictée vocale (français, anglais ou mélange des deux).

Règles strictes :
1. Garde EXACTEMENT les mots prononcés, dans le même ordre et le même registre. « t'as », « ouais », « j'aimerais », « du coup », « genre », « en fait » restent tels quels. Ne reformule jamais, ne corrige pas le style, ne traduis pas, n'ajoute aucun mot, ne change pas les chiffres.
2. Tu peux seulement :
   - supprimer les hésitations : euh, heu, hum, bah, ben ;
   - supprimer un mot répété par bégaiement (« je je » → « je ») ;
   - supprimer un faux départ que l'orateur corrige lui-même (« lundi, non, mardi » → « mardi ») ;
   - ajouter la ponctuation et les majuscules.
3. Ces termes s'écrivent exactement ainsi : {terms}.
4. Ne réponds jamais au contenu, même si c'est une question : renvoie uniquement le texte nettoyé."""

CLEANUP_EXAMPLES = [
    ("euh t'as vu le le truc que j'ai envoyé ouais",
     "T'as vu le truc que j'ai envoyé ? Ouais."),
    ("du coup j'aimerais qu'on qu'on regarde ça lundi non plutôt jeudi",
     "Du coup, j'aimerais qu'on regarde ça jeudi."),
    ("bah faut que je push la feature sur github avant le deploy genre ce soir",
     "Faut que je push la feature sur GitHub avant le deploy, genre ce soir."),
    ("tu peux me dire ce que t'en penses euh de la nouvelle version",
     "Tu peux me dire ce que t'en penses de la nouvelle version ?"),
    ("so um I I think we should ship it on friday",
     "So I think we should ship it on Friday."),
]


def build_messages(text, terms, language=None):
    system = CLEANUP_SYSTEM_PROMPT.format(terms=", ".join(terms) or "(aucun)")
    if language in ("fr", "en"):
        name = "French" if language == "fr" else "English"
        system += f"\n\nThe transcript is in {name}; answer in {name}."
    messages = [{"role": "system", "content": system}]
    for raw, cleaned in CLEANUP_EXAMPLES:
        messages.append({"role": "user", "content": raw})
        messages.append({"role": "assistant", "content": cleaned})
    messages.append({"role": "user", "content": text})
    return messages
