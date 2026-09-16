# Dictée Locale

Dictée vocale pour Windows, **100 % locale**. Maintiens **Ctrl+Alt** dans
n'importe quelle application, parle en **français ou en anglais**, relâche :
ta voix est transcrite sur ton PC, nettoyée (plus de « euh », de
bafouillages, ponctuation ajoutée), puis collée là où se trouve ton curseur.

Rien ne part sur Internet : pas de compte, pas d'abonnement, pas de cloud.

## Fonctionnalités

- **Dictée partout** : Word, Gmail, Discord, VS Code, le navigateur… tout
  champ où tu peux taper du texte.
- **Nettoyage intelligent** : un modèle d'IA local retire les « euh »,
  « du coup », « genre », les mots répétés et les faux départs, ajoute la
  ponctuation et applique tes corrections (« lundi, non attends, mardi » →
  « mardi »). Les anglicismes (« push », « deploy »…) sont conservés.
- **Français, anglais ou mélange** : 🇫🇷, 🇬🇧 ou 🇫🇷+🇬🇧 (détection
  automatique limitée à ces deux langues).
- **Ton presse-papier est préservé** : ce que tu avais copié est restauré
  après le collage.
- **Pilule flottante** en bas de l'écran pendant la dictée : forme d'onde de
  ton micro en direct, drapeau de la langue active.
- **Réglages en un clic** : clique sur le drapeau de la pilule pour changer de
  langue ou de micro, sans redémarrer l'app et même en pleine dictée.
- **Mode mains libres (cadenas 🔒)** : Ctrl+Alt démarre la dictée, tu te
  balades entre les fenêtres, Ctrl+Alt à nouveau et le texte est collé là où
  tu es.
- **Renvoi du dernier texte (↺)** : si le collage est parti dans le vide (pas
  de champ de texte sélectionné), un clic le recolle aussitôt, pendant
  20 secondes. Le texte est gardé uniquement en mémoire vive, puis effacé.
- **Annulation (✕)** : tu as commencé à parler et finalement non ? Un clic et
  rien n'est collé.
- **Commandes vocales** : termine par « Colibri, colle. » pour coller sans
  toucher au clavier, ou « Colibri, envoie. » pour coller et appuyer sur
  Entrée.
- **Sons discrets** : petit clic de bois quand le texte est collé, clic
  puis courte rafale de vent quand le message est envoyé.
- **Icône près de l'horloge** : bleue = prête, rouge = enregistrement,
  orange = traitement. Clic droit → langue ou Quitter.

## Ce qu'il faut

- Windows 10 ou 11.
- Une carte graphique **NVIDIA** de préférence (la transcription est alors
  quasi instantanée). Sans elle, ça marche sur le processeur mais plus
  lentement : voir [Réglages](#réglages-configjson) pour passer à un modèle
  plus léger.
- **Ollama** pour le nettoyage du texte (facultatif mais conseillé) :
  1. Installe-le depuis <https://ollama.com>.
  2. Dans un terminal : `ollama pull qwen2.5:7b` (≈ 4,7 Go).

  Sans Ollama, l'app colle le texte brut de la transcription.

## Démarrage rapide (exe)

1. Dézippe `DicteeLocale-windows.zip` où tu veux (garde tout le dossier).
2. Lance `DicteeLocale\DicteeLocale.exe`.
3. **Premier lancement : patience.** L'app télécharge le modèle de
   reconnaissance vocale (≈ 1,6 Go) et rien ne s'affiche pendant ce temps.
   Quand c'est prêt, l'icône bleue apparaît en bas à droite, près de
   l'horloge (parfois cachée dans le tiroir ˄).
4. Clique dans un champ de texte, maintiens **Ctrl+Alt**, parle, relâche.

Pour lancer l'app au démarrage de Windows : `Win+R` → `shell:startup` →
mets-y un raccourci vers l'exe.

## Utilisation

**Dictée classique** : maintiens Ctrl+Alt, parle, relâche. Le texte arrive en
moins d'une seconde.

**Pendant la dictée**, les boutons de la pilule s'éclairent au survol et sont
cliquables (ton curseur ne perd jamais le focus) :

| Élément | Action |
|---|---|
| Drapeau | Ouvre les réglages : langue et micro. Tout se ferme quand tu relâches |
| 🔒 Cadenas | Active/désactive le mode mains libres (reste activé jusqu'au prochain clic) |
| ↺ | Recolle le dernier texte au curseur et ferme la pilule (visible 20 s après une dictée). Si tu maintiens Ctrl+Alt, le collage se fait dès que tu relâches |
| ✕ | Annule la dictée en cours : rien n'est collé |

**Mode mains libres** : maintiens Ctrl+Alt, clique sur le cadenas, relâche.
L'enregistrement continue ; change de fenêtre, place ton curseur, puis appuie
et relâche Ctrl+Alt pour envoyer. Taper `@`, `#` ou `€` (AltGr) pendant la
dictée ne l'interrompt pas.

## Commandes vocales

Termine ta dictée par l'une de ces phrases, **en dernier**, puis marque une
courte pause :

| Tu dis | Effet |
|---|---|
| « Colibri, colle. » | Colle le texte (comme Ctrl+Alt) |
| « Colibri, envoie. » | Colle le texte puis appuie sur **Entrée** |

- En **mode mains libres**, la commande est détectée en direct : pas besoin
  de toucher au clavier, pratique avec un casque sans fil.
- En mode maintenu, elle est appliquée quand tu relâches Ctrl+Alt.
- « Colibri, envoie. » dite seule envoie un message déjà collé.
- La commande n'est jamais collée dans ton texte et ne compte qu'à la toute
  fin : « colibri » ou « envoie » au milieu d'une phrase ne déclenchent rien,
  les longs silences non plus. « Colibri » a été choisi car aucun mot courant
  ne lui ressemble.
- En anglais : « Colibri, paste. » / « Colibri, send. ».
- Pour désactiver : `"voice_commands": false`.

## Réglages (`config.json`)

Le fichier est à côté de l'exe. Il est créé dès que tu changes un réglage
depuis la pilule ; tu peux aussi copier celui du dépôt.

| Clé | Défaut | Rôle |
|-----|--------|------|
| `hotkey` | `ctrl+alt` | Raccourci de dictée (ex. `ctrl+shift`, `f9`) |
| `language` | `mix` | `fr`, `en` ou `mix` |
| `whisper_model` | `large-v3-turbo` | Modèle de transcription. Sans carte NVIDIA : `small` |
| `whisper_compute_type` | `float16` | `float16` sur NVIDIA, `int8` sur processeur |
| `ollama_enabled` | `true` | `false` pour coller le texte brut |
| `ollama_model` | `qwen2.5:7b` | Modèle de nettoyage (`qwen2.5:3b` = plus léger) |
| `ollama_url` | `http://127.0.0.1:11434` | Adresse d'Ollama. Garde `127.0.0.1` : `localhost` ajoute ~2 s par requête sous Windows |
| `dictionary` | termes tech | Mots et noms propres à bien orthographier (prénoms, marques, jargon) |
| `microphone_device` | `null` | `null` = micro par défaut (changeable depuis la pilule) |
| `hands_free_lock` | `false` | Mode mains libres |
| `transcript_ttl_seconds` | `20` | Durée de disponibilité du renvoi ↺ |
| `voice_commands` | `true` | Commandes « Colibri, colle. » / « Colibri, envoie. » |
| `ollama_keep_alive` | `-1` | Garde le modèle de nettoyage chargé (`-1` = toujours, ou par ex. `"30m"`) |
| `sounds` | `true` | Clic au collage, clic + rafale de vent à chaque envoi |
| `paste_delay_ms` | `300` | Attente avant de restaurer ton presse-papier |
| `sample_rate` | `16000` | Ne pas modifier |

## Dépannage

Un fichier `dictation.log` à côté de l'exe détaille ce qui se passe. Il
contient aussi le texte dicté : ne le partage pas.

**Rien ne se passe avec Ctrl+Alt**
- L'icône bleue est-elle affichée près de l'horloge ? Sinon l'app charge
  encore (ou a planté : regarde `dictation.log`).
- Un autre logiciel utilise peut-être déjà Ctrl+Alt : change `hotkey`.
- Les fenêtres lancées en administrateur ne reçoivent pas la dictée.

**La pilule reste affichée / Ctrl+Alt ne répond plus**
- Clique sur ✕ pour annuler. Si Ollama tarde à répondre, l'app colle le texte
  brut au bout d'une dizaine de secondes au lieu de rester bloquée.
- Le journal `dictation.log` est horodaté : il montre l'étape qui a traîné.

**Le texte n'est pas nettoyé (« euh » conservés)**
- Ollama n'est pas lancé ou le modèle manque : `ollama pull qwen2.5:7b`.
  Le log indique `Ollama cleanup failed` ou `not found in Ollama`.

**`GPU unusable` dans le log / transcription lente**
- Pas de carte NVIDIA utilisable : passe `whisper_model` à `small` et
  `whisper_compute_type` à `int8`.

**Phrases fantômes (« Merci d'avoir regardé cette vidéo ! »)**
- Whisper en invente parfois sur les longs silences. Les plus connues sont
  filtrées ; si une nouvelle apparaît, ajoute un morceau de la phrase à
  `HALLUCINATION_PATTERNS` dans `main.py`.

**Mauvais micro**
- Clique sur la pilule pendant la dictée et choisis le bon micro.

## Depuis le code source

Python 3.11+ :

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Ou double-clique `run.bat`. Options utiles : `run.bat --debug-keys` affiche
chaque touche détectée (pratique si le raccourci ne réagit pas).

Sur une carte NVIDIA, installe aussi les bibliothèques CUDA dans le venv :
`pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` (chargées
automatiquement).

**Recompiler l'exe** (nécessite `pip install pyinstaller`) :

```powershell
.\build.ps1
```

Le script arrête l'app, recompile, conserve le `config.json` et le
`dictation.log` de l'exe, puis relance `dist\DicteeLocale\DicteeLocale.exe`.

### Fonctionnement

Micro (sounddevice, 16 kHz) → transcription locale **faster-whisper**
(`large-v3-turbo`, filtre de silences + anti-hallucinations) → nettoyage par
**Ollama** (`qwen2.5:7b`, prompt avec exemples FR/EN) → collage via
presse-papier + Ctrl+V, puis restauration du presse-papier. Interface :
tkinter (pilule et réglages, fenêtres qui ne prennent jamais le focus) et
pystray (icône).
