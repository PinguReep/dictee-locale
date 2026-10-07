"""Benchmarks speech engines on YOUR voice (local only, aggregate output only).

References come from the encrypted history: the recording session
(tools/calibration.py). Real dictations validated by hand in the review box
(audio kept) are added only with --avec-dictees. Never prints any dictated
text.

Run it with the benchmark environment (engines are heavy, kept apart from
the app):
    .venv-bench\\Scripts\\python tools\\benchmark.py
    .venv-bench\\Scripts\\python tools\\benchmark.py fw:large-v3-turbo onnx:nemo-parakeet-tdt-0.6b-v3
    .venv-bench\\Scripts\\python tools\\benchmark.py --avec-dictees

Engines:
    fw:<model>     faster-whisper, same decoding options and vocabulary
                   hotwords as the app
    onnx:<model>   onnx-asr (NVIDIA Parakeet / Canary in ONNX)
    qwen3:<model>  Qwen3-ASR via qwen-asr
"""

import gc
import statistics
from collections import Counter
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from private_store import PrivateStore  # noqa: E402
from vocab import Vocabulary, plain, words  # noqa: E402

DEFAULT_ENGINES = [
    "fw:large-v3-turbo",
    "fw:large-v3",
    "onnx:nemo-parakeet-tdt-0.6b-v3",
    "onnx:nemo-canary-1b-v2",
    "qwen3:Qwen/Qwen3-ASR-1.7B",
]


def _norm(text):
    return [plain(w).replace("’", "'").strip("-'") for w in words(text)]


def wer(reference, hypothesis):
    ref, hyp = _norm(reference), _norm(hypothesis)
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1,
                             previous[j - 1] + (r != h))
        previous = current
    return previous[-1], max(len(ref), 1)


def term_misses(reference, hypothesis, terms):
    """(terms of the reference missing from the hypothesis, number present)."""
    ref = " " + " ".join(_norm(reference)) + " "
    hyp = " " + " ".join(_norm(hypothesis)) + " "
    present = [t for t in terms if f" {' '.join(_norm(t))} " in ref]
    return [t for t in present if f" {' '.join(_norm(t))} " not in hyp], len(present)


# -- engines ------------------------------------------------------------------
def _cuda_dlls():
    try:
        import torch  # noqa: F401  (loads the CUDA runtime DLLs it ships)
    except ImportError:
        pass


def faster_whisper_engine(name):
    _cuda_dlls()
    from faster_whisper import WhisperModel
    model = WhisperModel(name, device="cuda", compute_type="float16")
    options = {"vad_filter": True,
               "vad_parameters": {"min_silence_duration_ms": 500, "speech_pad_ms": 300},
               "condition_on_previous_text": False, "word_timestamps": True,
               "hallucination_silence_threshold": 2.0}

    def run(audio, rate, hotwords):
        segments, _ = model.transcribe(audio, language="fr", hotwords=hotwords, **options)
        return " ".join(s.text.strip() for s in segments)
    return run, model


def onnx_asr_engine(name):
    _cuda_dlls()
    import onnx_asr
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    try:
        model = onnx_asr.load_model(name, providers=providers)
    except TypeError:
        model = onnx_asr.load_model(name)
    is_canary = "canary" in name

    def run(audio, rate, hotwords):
        if is_canary:
            return model.recognize(audio, sample_rate=rate, language="fr",
                                   target_language="fr", pnc=True)
        return model.recognize(audio, sample_rate=rate)
    return run, model


def qwen3_engine(name):
    import torch
    from qwen_asr import Qwen3ASRModel
    model = Qwen3ASRModel.from_pretrained(name, dtype=torch.bfloat16,
                                          device_map="cuda:0",
                                          max_new_tokens=512)

    def run(audio, rate, hotwords):
        result = model.transcribe(audio=(audio, rate), language="French",
                                  context=hotwords or "")
        return result[0].text
    return run, model


ENGINES = {"fw": faster_whisper_engine, "onnx": onnx_asr_engine,
           "qwen3": qwen3_engine}


def load_samples(store, with_dictations=False):
    """Recording-session takes; real dictations only when asked explicitly."""
    return [r for r in store.records()
            if r.get("audio") and r.get("final")
            and (r.get("calibration")
                 or (with_dictations and r.get("validated_by") == "user"))]


def evaluate(spec, samples, audio_of, vocabulary):
    kind, _, name = spec.partition(":")
    start = time.perf_counter()
    run, handle = ENGINES[kind](name)
    load = time.perf_counter() - start
    errors = fixed_errors = total = present = 0
    missed, fixed_missed, latencies = [], [], []
    terms = vocabulary.terms()
    run(*audio_of(samples[0]), vocabulary.hotwords())  # warm-up
    for record in samples:
        audio, rate = audio_of(record)
        start = time.perf_counter()
        hypothesis = run(audio, rate, vocabulary.hotwords())
        latencies.append(time.perf_counter() - start)
        fixed = vocabulary.apply_rules(hypothesis)[0]  # as the app does next
        e, n = wer(record["final"], hypothesis)
        f, _ = wer(record["final"], fixed)
        m, p = term_misses(record["final"], hypothesis, terms)
        fm, _ = term_misses(record["final"], fixed, terms)
        errors, fixed_errors, total, present = errors + e, fixed_errors + f, total + n, present + p
        missed, fixed_missed = missed + m, fixed_missed + fm
    del run, handle
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except ImportError:
        pass
    return {"engine": spec, "wer": errors / total, "wer_rules": fixed_errors / total,
            "terms": f"{len(missed)}/{present}",
            "terms_rules": f"{len(fixed_missed)}/{present}", "missed": fixed_missed,
            "latency": statistics.median(latencies), "load": load}


def main(args):
    with_dictations = "--avec-dictees" in args
    specs = [a for a in args if not a.startswith("--")] or DEFAULT_ENGINES
    store = PrivateStore()
    samples = load_samples(store, with_dictations)
    if not samples:
        print("Aucune référence : lance d'abord tools\\calibration.py (séance "
              "d'enregistrement).")
        return
    vocabulary = Vocabulary()
    cache = {}

    def audio_of(record):
        if record["id"] not in cache:
            cache[record["id"]] = store.audio(record["id"])
        return cache[record["id"]]

    seconds = sum(len(audio_of(r)[0]) / audio_of(r)[1] for r in samples)
    print(f"{len(samples)} enregistrements de référence ({seconds / 60:.1f} min)\n")
    print("WER = mots faux ; « + règles » = après les règles de vocabulaire, "
          "comme dans l'app\n")
    print(f"{'moteur':36s} {'WER':>6s} {'+règles':>8s}  {'termes ratés':>12s} "
          f"{'+règles':>8s}  {'latence':>8s}")
    missed = {}
    for spec in specs:
        try:
            r = evaluate(spec, samples, audio_of, vocabulary)
        except Exception as exc:
            print(f"{spec:36s} échec : {type(exc).__name__}: {str(exc)[:80]}")
            continue
        missed[spec] = r["missed"]
        print(f"{r['engine']:36s} {r['wer']:6.1%} {r['wer_rules']:8.1%}  "
              f"{r['terms']:>12s} {r['terms_rules']:>8s}  {r['latency']:7.2f}s",
              flush=True)
    if not with_dictations:  # names from the vocabulary, read from fixed sentences
        print("\nTermes encore ratés après les règles :")
        for spec, terms in missed.items():
            counts = Counter(terms).most_common()
            print(f"  {spec} : " + (", ".join(f"{t} ×{n}" if n > 1 else t
                                              for t, n in counts) or "aucun"))


if __name__ == "__main__":
    main(sys.argv[1:])
