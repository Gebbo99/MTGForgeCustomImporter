# Forge Custom Card Importer

External companion tool for **MTG Forge**: it imports custom cards (re-skins:
new art and new displayed name, same rules as an existing card) and custom
tokens straight into Forge's own folders, so they show up in the deck editor
without touching the game.

The repo ships two distinct apps built from the same core:

| Version | Folder | What you download | Runs on |
| --- | --- | --- | --- |
| **Desktop** | [`desktop/`](desktop/) | `ForgeCustomImporter.exe` | Windows |
| **Android** | [`android/`](android/) | `forgecustomimporter-*-debug.apk` | Android 7+ (phone) |

The Windows app can also **deploy a set to the phone over USB** with `adb`,
without using the Android app at all: see
[Deploying a set to the phone (adb)](#deploying-a-set-to-the-phone-adb).

---

## Download

Open the [**Releases**](../../releases) page and grab the file for your device:

- **Android** – the `.apk` file. Enable "Install unknown apps" for your
  browser/file manager, open the APK and install it. On first start the app asks
  for **All files access** (`MANAGE_EXTERNAL_STORAGE`): it is required to read
  Forge's folders outside the app sandbox.
- **Windows** – `ForgeCustomImporter.exe`. It is a single portable file, no
  installation needed.

Both apps are also published as build artifacts on every push to `main`.

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

On Android the Forge folders are detected automatically among the known
locations (`Android/obb/forge.app/Forge`, `Android/data/forge.app/files/Forge`,
`/storage/emulated/0/Forge`, ...); they can be overridden in **Settings**.

---

## Deploying a set to the phone (adb)

Android blocks ordinary apps from writing inside `Android/obb/forge.app`, so the
Android app cannot import there on its own. The **desktop** app can: it does all
the work locally and then uses **adb** to copy the finished set into Forge's
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
    forge_importer/       shared core: OCR, matching, Forge file writing
        gui.py            desktop UI (not shared)
        adb.py            USB deployment to the phone (not shared)
    ForgeCustomImporter.spec
android/                  Android app (Kivy + KivyMD, built with Buildozer)
    main.py               UI and app flow
    android_env.py        storage permission and Forge paths on Android
    mlkit_ocr.py          on-device OCR (Google ML Kit, via pyjnius)
    buildozer.spec
tools/sync_core.py        copies the shared core into android/ before a build
.github/workflows/build.yml
```

The core (`carddb`, `matcher`, `generator`, `textutil`, `rarity`, ...) is shared
by both apps and lives in `desktop/forge_importer`, which is the single source
of truth. The Android app works on a copy that `tools/sync_core.py` regenerates
right before the build, so the two versions can never drift apart. `gui.py` and
`adb.py` are desktop-only and are never copied to the Android app.

The differences between the two versions are only the UI toolkit and the OCR
engine: the desktop uses RapidOCR (onnxruntime) and Tkinter, Android uses ML Kit
and Kivy.

---

## Building from source

### Desktop (Windows)

```powershell
cd desktop
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt pyinstaller
.\.venv\Scripts\python main.py                    # run from source
.\.venv\Scripts\python -m PyInstaller --noconfirm --clean ForgeCustomImporter.spec
```

The executable is written to `desktop/dist/ForgeCustomImporter.exe`.

### Android

Buildozer needs Linux (Android SDK/NDK and python-for-android do not run on
Windows), so the APK is compiled by GitHub Actions — push a tag and the
workflow attaches the APK to the release.

To build locally on Linux:

```bash
python -m pip install buildozer cython
python tools/sync_core.py
cd android && buildozer -v android debug
```

The APK is written to `android/bin/`.
