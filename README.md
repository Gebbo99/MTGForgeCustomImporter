<meta name="google-site-verification" content="655a0b1ee334c602" />
# Forge Custom Card Importer

External companion tool for **MTG Forge**: it imports custom cards (re-skins:
new art and new displayed name, same rules as an existing card) and custom
tokens straight into Forge's own folders, so they show up in the deck editor
without touching the game.

It is a single Windows app. It runs entirely on the PC; when you want the set on
a phone, it can **deploy it over USB** with `adb` (see
[Deploying a set to the phone (adb)](#deploying-a-set-to-the-phone-adb)).

---

## Download

Open the [**Releases**](../../releases) page and grab `ForgeCustomImporter.exe`.
It is a single portable file, no installation needed.

Every push to `main` also publishes the executable as a build artifact.

---

## How it works

1. You add the images of the proxies (a folder or single files).
2. Each image is read with OCR and matched against Forge's card scripts to find
   the **base card** that provides the rules.
3. The proposals are listed and can be corrected by hand (new name, rarity,
   artist, base card).
4. Importing writes into Forge's custom folders:

```
custom/editions/<CODE>.txt        the custom set
custom/cards/<Name>.txt           card scripts (tokens only)
custom/tokens/<stem>.txt          token scripts
Cache/pics/cards/<CODE>/<Name>.fullborder.<ext>
Cache/pics/tokens/<CODE>/<collector>_<stem>.<ext>
```

Re-skins are registered as *variants* of the base card (a `flavorName` entry in
the edition file), so they appear among the art variants of the base card in
Forge's deck editor instead of as standalone cards.

---

## Deploying a set to the phone (adb)

Android blocks ordinary apps from writing inside `Android/obb/forge.app`, so a
phone-side app could not import there on its own. The desktop app can: it does
all the work locally and then uses **adb** to copy the finished set into Forge's
folders on the phone. adb is only the courier — OCR, matching and file
generation all happen on the PC.

Setup (once):

1. Install **Android Platform Tools** (Google) and connect the phone by USB. The
   app finds `adb` automatically in the usual locations, or you can pick
   `adb.exe` by hand.
2. On the phone enable **Developer options → USB debugging** and accept the
   authorization prompt that shows up.
3. In the app open **Settings → Phone (adb)**: press *Find phones*, choose the
   device, then *Detect* the Forge folder (usually
   `/storage/emulated/0/Android/obb/forge.app/Forge`).
4. Set **Destination: Phone** in the bottom bar.

From there you have two ways to copy a set:

- **Import all into Forge** — with destination *Phone*, importing writes the set
  locally *and* copies it to the phone in the same run;
- **Send set to phone** — copies a set you **already imported** earlier, without
  running OCR or importing it again: pick it in the **Edition** box and press
  the button.

Both paths are idempotent: files with the same name are overwritten and stale
variants of the same art are removed, so repeating them never duplicates
anything. The phone only has to be connected (with USB debugging on) while the
copy is running.

---

## Repository layout

```
desktop/                  Windows app (CustomTkinter + PyInstaller)
    forge_importer/       core: OCR, matching, Forge file writing
        gui.py            desktop UI
        adb.py            USB deployment to the phone
    ForgeCustomImporter.spec
.github/workflows/build.yml
```

---

## Building from source

```powershell
cd desktop
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt pyinstaller
.\.venv\Scripts\python main.py                    # run from source
.\.venv\Scripts\python -m PyInstaller --noconfirm --clean ForgeCustomImporter.spec
```

The executable is written to `desktop/dist/ForgeCustomImporter.exe`.
