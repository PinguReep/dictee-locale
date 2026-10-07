"""Background analysis of the user's corrections by an LLM on the LAN.

Sends only the corrected word spans with a few words of context (never whole
dictations) to an OpenAI-compatible endpoint on the local network (the DGX
Sparks), and asks for general rules ("cloud" -> "Claude" when talking about
AI). Proposals go into the vocabulary inactive, unless the user's own
corrections already showed the same fix.

The endpoint must resolve to a private or loopback address: dictation data
never leaves the local network.
"""

import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import requests

from vocab import plain, words
from review_box import diff_spans

CONTEXT_WORDS = 4
MAX_PAIRS = 80

SYSTEM_PROMPT = """Tu analyses les corrections qu'un utilisateur a faites sur sa dictée vocale (reconnaissance vocale Whisper, français avec du jargon tech anglais).

Chaque correction donne ce que la reconnaissance a écrit (« entendu »), ce que l'utilisateur voulait (« voulu ») et quelques mots de contexte.

Propose des règles de remplacement générales UNIQUEMENT pour les erreurs de reconnaissance de noms propres, de noms de produits ou de modèles d'IA et de jargon. Ignore les corrections de fond, de style ou de grammaire.

Pour une règle ambiguë (« cloud » peut être légitime), ajoute "context" : une liste de mots dont l'un doit apparaître dans la dictée pour appliquer la règle.

Réponds UNIQUEMENT avec un tableau JSON, sans texte autour :
[{"from": "mot entendu", "to": "mot voulu", "context": ["mot", "..."]}]
Tableau vide [] si rien n'est généralisable."""


def is_lan(url):
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        address = ipaddress.ip_address(socket.gethostbyname(host))
    except (OSError, ValueError):
        return False
    return address.is_private or address.is_loopback


def correction_pairs(records):
    """Corrected spans with a small context window, from reviewed records."""
    pairs = []
    for record in records:
        proposed, final = record.get("proposed"), record.get("final")
        if not record.get("edited") or not proposed or not final:
            continue
        final_words = words(final)
        changes, _ = diff_spans(proposed, final)
        for wanted, heard in changes:
            keys = [plain(w) for w in final_words]
            first = plain(words(wanted)[0]) if words(wanted) else ""
            at = keys.index(first) if first in keys else 0
            context = " ".join(final_words[max(0, at - CONTEXT_WORDS):at + CONTEXT_WORDS + 1])
            pairs.append({"entendu": heard, "voulu": wanted, "contexte": context})
    return pairs[-MAX_PAIRS:]


def _model(url, session):
    response = session.get(url.rstrip("/") + "/models", timeout=5)
    response.raise_for_status()
    return response.json()["data"][0]["id"]


def analyse(store, vocabulary, url, model=None, timeout=240):
    """Returns the number of rules proposed (0 if nothing to analyse)."""
    if not is_lan(url):
        raise ValueError(f"refusing to send dictation data outside the LAN: {url}")
    pairs = correction_pairs(store.records())
    if not pairs:
        return 0
    session = requests.Session()
    session.trust_env = False  # never through a proxy
    model = model or _model(url, session)
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 2000,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(pairs, ensure_ascii=False)},
        ],
    }
    response = session.post(url.rstrip("/") + "/chat/completions",
                            json=payload, timeout=timeout)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"] or ""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
    match = re.search(r"\[.*\]", content, flags=re.S)
    if not match:
        return 0
    try:
        proposals = json.loads(match.group())
    except ValueError:
        return 0
    proposals = [p for p in proposals if isinstance(p, dict)]
    return vocabulary.add_proposals(proposals, source=f"spark:{model}")
