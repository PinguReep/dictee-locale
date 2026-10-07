"""Compares cleanup models on synthetic transcripts (no real dictation).

Usage: .venv\\Scripts\\python tools\\eval_cleanup.py qwen2.5:7b qwen3:8b
Prints, per model: median latency, rewrites refused by the fidelity check,
and the final text of each sample.
"""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main  # noqa: E402
from vocab import SEED_TERMS  # noqa: E402

SAMPLES = [
    "euh du coup t'as vu le mail de Claude sur le projet ouais je pense qu'on peut le faire",
    "j'aimerais qu'on qu'on regarde les infos demain non plutôt jeudi",
    "bah faut que je push la feature avant le deploy genre ce soir",
    "est ce que ya moyen de lancer Qwen sur les deux sparks en même temps",
    "en fait j'ai testé opus et sonnet hier et euh le premier est bien meilleur",
    "tu peux me dire ce que t'en penses franchement",
    "ok donc on part sur 3 versions et on garde la deuxième",
    "j'ai pas compris pourquoi le build plante quand je lance le script",
    "euh je je voulais dire que c'est pas grave quoi",
    "so um I I think we should ship it on friday with the new prompt",
    "c'est pas ce que je voulais dire mais bon on verra",
    "il faut que tu review la pull request avant demain midi",
]


def run(model_name):
    config = main.load_config()
    config["ollama_model"] = model_name
    latencies, refused_total, outputs = [], 0, []
    for text in SAMPLES:
        start = time.perf_counter()
        result = main.clean_with_ollama(text, config, "fr", SEED_TERMS)
        latencies.append(time.perf_counter() - start)
        cleaned, refused = result if result else (text, 0)
        refused_total += refused
        outputs.append(cleaned)
    return statistics.median(latencies), refused_total, outputs


if __name__ == "__main__":
    for name in sys.argv[1:] or ["qwen2.5:7b"]:
        run(name)  # warm-up (model load)
        latency, refused, outputs = run(name)
        print(f"=== {name}: médiane {latency:.2f}s, {refused} réécriture(s) refusée(s)")
        for out in outputs:
            print("   ", out)
