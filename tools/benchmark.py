"""Benchmarks speech engines on YOUR validated dictations (local only).

Uses the encrypted history: dictations that kept their audio and that you
validated by hand in the review box (the reference is the text you
validated). Prints aggregate scores only, never any dictated text.

Usage:
    .venv\\Scripts\\python tools\\benchmark.py fw:large-v3-turbo fw:large-v3

Engines: "fw:<model>" = faster-whisper (any CTranslate2 model name or path).
To compare another engine (Parakeet, Canary, Qwen3-ASR...), add an adapter
in ENGINES that turns (audio, sample_rate, hotwords) into text.
"""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main  # noqa: E402
from private_store import PrivateStore  # noqa: E402
from vocab import Vocabulary, plain, words  # noqa: E402


def wer(reference, hypothesis):
    ref = [plain(w) for w in words(reference)]
    hyp = [plain(w) for w in words(hypothesis)]
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1,
                             previous[j - 1] + (r != h))
        previous = current
    return previous[-1], max(len(ref), 1)


def term_misses(reference, hypothesis, terms):
    hyp = " ".join(plain(w) for w in words(hypothesis))
    present = [t for t in terms if plain(t) in " ".join(plain(w) for w in words(reference))]
    return sum(plain(t) not in hyp for t in present), len(present)


def faster_whisper_engine(name):
    from faster_whisper import WhisperModel
    main.add_cuda_dll_dirs()
    model = WhisperModel(name, device="auto", compute_type="float16")

    def run(audio, sample_rate, hotwords):
        text, _ = main.transcribe(model, audio, hotwords, "fr")
        return text
    return run


ENGINES = {"fw": faster_whisper_engine}


def main_cli(specs):
    store = PrivateStore()
    vocabulary = Vocabulary()
    samples = [r for r in store.records()
               if r.get("audio") and r.get("validated_by") == "user"]
    if not samples:
        print("Aucune dictée validée à la main avec audio : active la relecture "
              "et save_audio, puis valide quelques dictées.")
        return
    print(f"{len(samples)} dictées de référence")
    for spec in specs:
        kind, _, name = spec.partition(":")
        engine = ENGINES[kind](name)
        errors = total = missed = present = 0
        latencies = []
        for record in samples:
            audio, rate = store.audio(record["id"])
            start = time.perf_counter()
            hypothesis = engine(audio, rate, vocabulary.hotwords())
            latencies.append(time.perf_counter() - start)
            e, n = wer(record["final"], hypothesis)
            m, p = term_misses(record["final"], hypothesis, vocabulary.terms())
            errors, total, missed, present = errors + e, total + n, missed + m, present + p
        print(f"{spec:28s} WER {errors / total:6.1%}   termes ratés "
              f"{missed}/{present}   latence médiane {statistics.median(latencies):.2f}s")


if __name__ == "__main__":
    main_cli(sys.argv[1:] or ["fw:large-v3-turbo"])
