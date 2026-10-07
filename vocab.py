"""Personal vocabulary: terms to favour, learned "heard -> wanted" rules.

- Terms (proper nouns, AI model names...) bias Whisper via `hotwords`
  (re-applied to every 30 s window, unlike `initial_prompt`) and are
  protected during the cleanup pass.
- Rules fix recurring mishearings right after transcription ("cloud" ->
  "Claude"); a rule may require a context word somewhere in the dictation.
- Corrections made in the review box are learned: a rule becomes active
  after it has been seen `ACTIVATE_AFTER` times.

Stored as plain JSON (word pairs only, no dictated text):
    %LOCALAPPDATA%\\DicteeLocale\\vocabulaire.json
"""

import json
import os
import re
import threading
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

ACTIVATE_AFTER = 2
MAX_HOTWORDS_CHARS = 600  # faster-whisper truncates hotwords to ~223 tokens

AI_CONTEXT = [
    "ia", "ai", "modele", "modeles", "model", "llm", "prompt", "agent",
    "anthropic", "openai", "opus", "sonnet", "haiku", "fable", "mythos",
    "claude", "gpt", "gemini", "qwen", "mistral", "deepseek", "llama",
    "ollama", "token", "tokens", "api", "chatbot", "assistant", "spark",
    "code", "session", "contexte", "fine-tuning", "inference",
]

SEED_TERMS = [
    "Claude", "Claude Code", "Anthropic", "Opus", "Sonnet", "Haiku", "Fable",
    "Mythos", "Qwen", "GLM", "DeepSeek", "Llama", "Ollama", "Mistral",
    "Voxtral", "Gemini", "GPT", "OpenAI", "Whisper", "Wispr Flow", "Parakeet",
    "Canary", "DGX Spark", "Hermès", "Rémy", "GitHub", "Vercel", "Cloudflare",
    "Higgsfield",
]

SEED_RULES = [
    {"from": "cloud", "to": "Claude", "context": AI_CONTEXT},
    {"from": "clode", "to": "Claude"},
    {"from": "quen", "to": "Qwen"},
    {"from": "kwen", "to": "Qwen"},
    {"from": "kouen", "to": "Qwen"},
    {"from": "gwen", "to": "Qwen", "context": AI_CONTEXT},
    {"from": "sonnette", "to": "Sonnet", "context": AI_CONTEXT},
    {"from": "jemini", "to": "Gemini"},
    {"from": "deep seek", "to": "DeepSeek"},
    {"from": "olama", "to": "Ollama"},
]


def plain(text):
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def words(text):
    return re.findall(r"[\w'’-]+", text)


def default_path():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "DicteeLocale" / "vocabulaire.json"


class Vocabulary:
    def __init__(self, path=None, extra_terms=()):
        self.path = Path(path) if path else default_path()
        self._lock = threading.Lock()
        self.data = {"terms": [], "rules": []}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                print(f"[warn] Could not read vocabulary ({exc}), starting fresh.")
        if not self.data.get("seeded"):
            self._seed()
        self.extra_terms = [t for t in extra_terms if t]

    # -- storage --------------------------------------------------------
    def _seed(self):
        for term in SEED_TERMS:
            self.add_term(term, save=False)
        for rule in SEED_RULES:
            self._upsert(rule["from"], rule["to"], rule.get("context"),
                         source="seed", active=True)
        self.data["seeded"] = True
        self.save()

    def save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            os.replace(tmp, self.path)

    def add_term(self, term, save=True):
        if term and plain(term) not in {plain(t) for t in self.data["terms"]}:
            self.data["terms"].append(term)
            if save:
                self.save()

    def _upsert(self, heard, wanted, context=None, source="learned",
                active=False):
        heard_key = " ".join(words(plain(heard)))
        for rule in self.data["rules"]:
            if rule["from"] == heard_key and rule["to"] == wanted:
                rule["count"] = rule.get("count", 0) + 1
                rule["last"] = time.time()
                if rule["count"] >= ACTIVATE_AFTER or active:
                    rule["active"] = True
                return rule
        rule = {"from": heard_key, "to": wanted, "count": 1, "source": source,
                "active": active, "last": time.time()}
        if context:
            rule["context"] = list(context)
        self.data["rules"].append(rule)
        return rule

    # -- use ------------------------------------------------------------
    def terms(self):
        return list(dict.fromkeys(self.data["terms"] + self.extra_terms))

    def hotwords(self):
        """Comma-separated terms for faster-whisper, most recent first."""
        out, size = [], 0
        for term in reversed(self.terms()):
            if size + len(term) + 2 > MAX_HOTWORDS_CHARS:
                break
            out.append(term)
            size += len(term) + 2
        return ", ".join(reversed(out)) or None

    def apply_rules(self, text):
        """Applies active rules; returns (text, number of replacements)."""
        keys = set(words(plain(text)))
        total = 0
        for rule in self.data["rules"]:
            if not rule.get("active"):
                continue
            context = rule.get("context")
            if context and not keys & {plain(c) for c in context}:
                continue
            pattern = (r"(?<![\w'’-])"
                       + r"[\s-]+".join(re.escape(w) for w in rule["from"].split())
                       + r"(?![\w'’-])")
            text, n = re.subn(pattern, rule["to"], text, flags=re.IGNORECASE)
            total += n
        return text, total

    # -- learning -------------------------------------------------------
    def learn(self, proposed, final):
        """Learns word substitutions the user made in the review box.

        Returns the list of (heard, wanted) pairs recorded. Large rewrites
        (more than half the words changed) are ignored: they are edits of
        content, not mishearings.
        """
        a, b = words(proposed), words(final)
        ka, kb = [plain(w) for w in a], [plain(w) for w in b]
        matcher = SequenceMatcher(None, ka, kb, autojunk=False)
        if a and matcher.ratio() < 0.5:
            return []
        learned = []
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op != "replace" or i2 - i1 > 3 or j2 - j1 > 3:
                continue
            heard, wanted = " ".join(a[i1:i2]), " ".join(b[j1:j2])
            if plain(heard) == plain(wanted):
                continue  # case or accent only: not a mishearing
            similarity = SequenceMatcher(None, plain(heard), plain(wanted)).ratio()
            looks_like_name = any(w[:1].isupper() or any(c.isdigit() for c in w)
                                  for w in b[j1:j2])
            if similarity < 0.35 and not looks_like_name:
                continue  # a content edit, not something misheard
            rule = self._upsert(heard, wanted)
            if rule.get("active") and looks_like_name:
                self.add_term(wanted, save=False)
            learned.append((heard, wanted))
        if learned:
            self.save()
        return learned

    def add_proposals(self, proposals, source="spark"):
        """Adds rules proposed by the LAN model; active only once also seen
        in the user's own corrections."""
        added = 0
        for p in proposals:
            heard, wanted = p.get("from", "").strip(), p.get("to", "").strip()
            if not heard or not wanted or plain(heard) == plain(wanted):
                continue
            known = any(r["from"] == " ".join(words(plain(heard)))
                        and r["to"] == wanted for r in self.data["rules"])
            rule = self._upsert(heard, wanted, p.get("context"), source=source)
            if not known:
                rule["count"] = 0
                rule["active"] = False
            added += 1
        if added:
            self.save()
        return added
