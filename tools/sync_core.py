"""Allinea il core condiviso dentro la cartella dell'app Android.

Il core (OCR, riconoscimento, scrittura dei file di Forge) vive in
`desktop/forge_importer` ed e' la sola fonte di verita'. L'app Android ne usa
una copia in `android/forge_importer`, che non e' versionata: viene ricreata da
questo script (e dal workflow GitHub Actions) prima della build.

Vanno copiati solo i moduli realmente multipiattaforma: `gui.py` (usa Tkinter,
che su Android non esiste) e `adb.py` (ponte verso adb pilotato dal PC) restano
esclusivi del desktop.

Uso, dalla radice del repo:

    python tools/sync_core.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "desktop" / "forge_importer"
TARGET = ROOT / "android" / "forge_importer"

# Moduli condivisi: esclude gui.py e adb.py, che sono solo per il desktop.
MODULES = (
    "__init__.py",
    "_fuzzshim.py",
    "carddb.py",
    "cards.py",
    "generator.py",
    "i18n.py",
    "matcher.py",
    "ocr.py",
    "paths.py",
    "rarity.py",
    "textutil.py",
)


def main() -> int:
    if not SOURCE.is_dir():
        print(f"cartella di origine non trovata: {SOURCE}", file=sys.stderr)
        return 1

    TARGET.mkdir(parents=True, exist_ok=True)
    for name in MODULES:
        source = SOURCE / name
        if not source.is_file():
            print(f"modulo mancante: {source}", file=sys.stderr)
            return 1
        shutil.copy2(source, TARGET / name)

    # Rimuove eventuali residui di copie precedenti.
    for stale in TARGET.glob("*.py"):
        if stale.name not in MODULES:
            stale.unlink()

    shutil.rmtree(TARGET / "__pycache__", ignore_errors=True)
    print(f"sincronizzati {len(MODULES)} moduli in {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
