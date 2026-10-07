"""Recording session: read prepared sentences to build YOUR benchmark set.

Each take is stored in the encrypted history (text + audio) with the sentence
as its reference, so tools/benchmark.py can compare speech engines on your
own voice right away instead of waiting for weeks of dictations.

Usage: .venv\\Scripts\\python tools\\calibration.py
Hold Space (or the button) while reading the sentence, release to save.
Backspace = redo the previous sentence, Échap = quit (takes are kept).
"""

import sys
import time
import tkinter as tk
from pathlib import Path

import numpy as np
import sounddevice as sd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main  # noqa: E402
from private_store import PrivateStore  # noqa: E402
from review_box import ACCENT, BG, BOLD, DIM, FIELD, TEXT  # noqa: E402

SET_NAME = "calibration-v1"
SENTENCES = [
    "Claude, tu peux relire ce prompt et me dire ce que t'en penses ?",
    "J'ai testé Opus et Sonnet sur le même projet, Opus est clairement meilleur.",
    "Le modèle Qwen tourne sur les deux Spark, mais il ne prend qu'une requête à la fois.",
    "Faut que je push la feature avant le deploy de ce soir.",
    "Tu peux review la pull request et merger si les tests passent ?",
    "Ouais, c'est bon pour moi, on part là-dessus.",
    "Du coup on garde DeepSeek pour le code et Mistral pour le français.",
    "Le build plante quand je lance le script depuis le terminal.",
    "Est-ce que t'as vu la nouvelle version de Gemini ?",
    "On pourrait brancher Hermès sur le serveur local au lieu de passer par l'API.",
    "Rémy doit pouvoir lire mes mails sans rien envoyer sur Internet.",
    "GPT fait des erreurs sur les noms propres, Claude un peu moins.",
    "Je voudrais un benchmark sur ma propre voix avant de changer de modèle.",
    "Le fine-tuning se ferait sur les DGX Spark pendant la nuit.",
    "J'aimerais qu'on regarde ça demain matin, pas ce soir.",
    "C'est pas grave, on refera le commit proprement après.",
    "Envoie-moi le lien du dépôt GitHub quand t'as fini.",
    "La transcription doit rester locale, c'est non négociable.",
    "Il faut que la latence reste sous la seconde, sinon c'est pénible.",
    "On compare Parakeet, Canary et Whisper sur les mêmes phrases.",
    "Le serveur tourne sous Linux avec vLLM et un modèle GLM.",
    "Tu peux me faire un résumé de la réunion de ce matin ?",
    "J'ai déployé le site sur Cloudflare, Vercel coûtait trop cher.",
    "Mets le fichier de config dans le dossier du projet, pas sur le bureau.",
    "Franchement, cette interface est beaucoup plus propre qu'avant.",
    "Ajoute un test pour vérifier que le presse-papier est bien restauré.",
    "Je pense que Mythos est plus fort en raisonnement que Fable.",
    "On a besoin d'un modèle qui comprend le franglais sans tout traduire.",
    "Tu peux renommer la variable, le nom actuel prête à confusion.",
    "Le tokenizer coupe mal les mots composés en français.",
    "J'ai pas compris pourquoi le modèle traduit mes phrases en anglais.",
    "Higgsfield bloque certains modèles vidéo sur l'offre de base.",
    "Bon, je vais faire une pause et je reviens dans dix minutes.",
    "Ollama garde le modèle en mémoire pour que le nettoyage soit rapide.",
    "Hey, can you check the logs and tell me why the deploy failed?",
    "I think we should ship the new prompt on Friday.",
    "The pull request looks good, just fix the typo in the README.",
    "Let's benchmark Parakeet against Whisper on my own voice.",
    "Anthropic a sorti un nouveau modèle, faut qu'on le teste rapidement.",
    "Merci, c'est exactement ce que je voulais.",
]


class Session:
    def __init__(self, root):
        self.root = root
        self.config = main.load_config()
        self.rate = self.config["sample_rate"]
        self.device = main.resolve_microphone(self.config)
        self.store = PrivateStore()
        done = {r.get("reference") for r in self.store.records()
                if r.get("set") == SET_NAME}
        self.index = next((i for i, s in enumerate(SENTENCES) if s not in done),
                          len(SENTENCES))
        self.takes = []  # (index, record id) of this run, for "redo"
        self.chunks, self.stream = [], None

        root.title("Dictée locale — séance d'enregistrement")
        root.configure(bg=BG)
        root.geometry("820x330")
        self.progress = tk.Label(root, bg=BG, fg=DIM, font=BOLD)
        self.progress.pack(pady=(18, 6))
        self.sentence = tk.Label(root, bg=FIELD, fg=TEXT, font=("Segoe UI", 17),
                                 wraplength=740, justify="center", padx=20, pady=24)
        self.sentence.pack(fill="x", padx=30)
        self.button = tk.Label(root, text="● Maintiens Espace (ou ce bouton) et lis",
                               bg=ACCENT, fg="white", font=BOLD, padx=16, pady=8,
                               cursor="hand2")
        self.button.pack(pady=16)
        self.status = tk.Label(root, bg=BG, fg=DIM, font=("Segoe UI", 9),
                               text="Lis naturellement, comme quand tu dictes. "
                                    "Retour arrière : refaire la précédente · "
                                    "Échap : quitter")
        self.status.pack()

        root.bind("<KeyPress-space>", self.start)
        root.bind("<KeyRelease-space>", self.stop)
        self.button.bind("<ButtonPress-1>", self.start)
        self.button.bind("<ButtonRelease-1>", self.stop)
        root.bind("<BackSpace>", self.redo)
        root.bind("<Escape>", self.quit)
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.show()

    def show(self):
        if self.index >= len(SENTENCES):
            repaired = self.verify()
            self.progress.config(text=f"{len(SENTENCES)}/{len(SENTENCES)} — terminé")
            self.sentence.config(text="Merci ! Le banc d'essai peut tourner "
                                      "sur ta voix.")
            if repaired:
                self.status.config(text=f"✓ Enregistrée ({repaired} fiche(s) réparée(s))")
            return
        self.progress.config(text=f"Phrase {self.index + 1}/{len(SENTENCES)}")
        self.sentence.config(text=SENTENCES[self.index])

    def _callback(self, indata, frames, time_info, status):
        self.chunks.append(indata.copy())

    def start(self, _event=None):
        if self.stream is not None or self.index >= len(SENTENCES):
            return
        self.chunks = []
        self.stream = sd.InputStream(samplerate=self.rate, channels=1,
                                     dtype="float32", device=self.device,
                                     callback=self._callback)
        self.stream.start()
        self.button.config(bg="#FF5C7A", text="● Enregistrement…")

    def stop(self, _event=None):
        if self.stream is None:
            return
        time.sleep(0.25)  # keep the end of the last word
        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.button.config(bg=ACCENT, text="● Maintiens Espace (ou ce bouton) et lis")
        audio = np.concatenate(self.chunks).flatten() if self.chunks else np.zeros(0)
        if len(audio) < self.rate * 0.8:
            self.status.config(text="Trop court, recommence.")
            return
        record_id = self.store.add(self._record(self.index, len(audio) / self.rate),
                                   audio.astype(np.float32), self.rate)
        self.takes.append((self.index, record_id))
        self.status.config(text="✓ Enregistrée")
        self.index += 1
        self.show()

    @staticmethod
    def _record(index, seconds, **extra):
        sentence = SENTENCES[index]
        return {"calibration": True, "set": SET_NAME, "reference": sentence,
                "final": sentence, "validated_by": "user",
                "duration": round(seconds, 1), **extra}

    def verify(self):
        """Re-adds the records of this run missing from the history (their
        audio is kept), so a session is never lost silently."""
        if not self.takes:
            return 0
        present = {r.get("id") for r in self.store.records()}
        repaired = 0
        for index, record_id in self.takes:
            got = None if record_id in present else self.store.audio(record_id)
            if got is None:
                continue
            audio, rate = got
            self.store.add(self._record(index, len(audio) / rate, id=record_id,
                                        audio=True, rebuilt=True))
            repaired += 1
        return repaired

    def quit(self, _event=None):
        self.verify()
        self.root.destroy()

    def redo(self, _event=None):
        if not self.takes:
            return
        index, record_id = self.takes.pop()
        self.store.remove([record_id])
        self.index = index
        self.status.config(text="Phrase précédente effacée, relis-la.")
        self.show()


if __name__ == "__main__":
    root = tk.Tk()
    Session(root)
    root.mainloop()
