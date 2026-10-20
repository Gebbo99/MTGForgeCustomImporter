"""Avvio di Forge Custom Card Importer.

Uso:
    python main.py            avvia la GUI
    python main.py --check    diagnostica di avvio; scrive il risultato in
                              %LOCALAPPDATA%\\ForgeCustomImporter\\check.log
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _self_check() -> int:
    """Verifica che i componenti principali funzionino (usato anche per l'exe)."""
    from forge_importer import paths as P
    from forge_importer.carddb import CardDB
    from forge_importer.matcher import Matcher
    from forge_importer.ocr import read_image
    from forge_importer.rarity import RarityIndex

    lines: list[str] = []
    ok = True

    settings = P.load_settings()
    lines.append(f"Installazione Forge: {settings.forge_root or '(non rilevata)'}")

    db_path = P.card_db_path(Path(settings.forge_root)) if settings.forge_root else None
    lines.append(f"Archivio carte: {db_path or '(non trovato)'}")
    if db_path is None:
        ok = False
    else:
        db = CardDB.load(db_path, P.app_data_dir() / "cardindex.json")
        matcher = Matcher(db)
        lines.append(f"Carte indicizzate: {len(db.cards)}")
        lines.append(f"Ricerca 'vandalb': {matcher.search_names('vandalb', 3)}")

    if settings.forge_root:
        rarities = RarityIndex.load(P.official_editions_dir(Path(settings.forge_root)))
        lines.append(f"Rarita' 'Sol Ring': {rarities.lookup('Sol Ring') or '(non trovata)'}")

    pics = settings.pics_dir()
    sample = None
    if pics.is_dir():
        sample = next(
            (p for p in pics.rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg"}),
            None,
        )
    if sample is not None:
        reading = read_image(sample)
        lines.append(
            f"OCR su {sample.name}: titolo={reading.title!r}, "
            f"regole={len(reading.rules_text)} caratteri"
        )
    else:
        lines.append("OCR: nessuna immagine di prova disponibile (saltato)")

    lines.append("ESITO: OK" if ok else "ESITO: PROBLEMI")
    log = P.app_data_dir() / "check.log"
    log.write_text("\n".join(lines), encoding="utf-8")
    return 0 if ok else 1


def main() -> None:
    if "--check" in sys.argv:
        raise SystemExit(_self_check())

    from forge_importer.gui import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
