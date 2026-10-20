"""Rilevamento dei percorsi di Forge e gestione delle impostazioni.

Forge (desktop) usa due cartelle distinte:
  - dati utente:  %APPDATA%\\Forge        -> contiene custom/ (cards, editions, tokens)
  - cache locale: %LOCALAPPDATA%\\Forge   -> contiene Cache/pics/cards/<CODICE>/
I card script ufficiali stanno nella cartella di installazione, in
res/cardsfolder/ (cartella sciolta o archivio cardsfolder.zip).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .i18n import DEFAULT_LANGUAGE, t

APP_DIR_NAME = "ForgeCustomImporter"


def _base_dirs() -> tuple[Path, Path]:
    roaming = os.environ.get("APPDATA")
    local = os.environ.get("LOCALAPPDATA")
    home = Path.home()
    roaming_dir = Path(roaming) if roaming else home / "AppData" / "Roaming"
    local_dir = Path(local) if local else home / "AppData" / "Local"
    return roaming_dir / "Forge", local_dir / "Forge"


FORGE_USER_DIR, FORGE_LOCAL_DIR = _base_dirs()
DEFAULT_CUSTOM_DIR = FORGE_USER_DIR / "custom"
DEFAULT_CACHE_DIR = FORGE_LOCAL_DIR / "Cache"


def app_data_dir() -> Path:
    """Cartella di lavoro del tool (cache indice, impostazioni).

    Su Android non esiste %LOCALAPPDATA%: l'app imposta FORGE_IMPORTER_DATA
    sulla propria cartella privata prima di importare questo modulo.
    """
    root = (
        os.environ.get("FORGE_IMPORTER_DATA")
        or os.environ.get("LOCALAPPDATA")
        or str(Path.home() / "AppData" / "Local")
    )
    d = Path(root) / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _candidate_roots() -> list[Path]:
    """Percorsi in cui cercare l'installazione di Forge, dal piu' probabile."""
    candidates: list[Path] = []
    for env in ("FORGE_HOME", "FORGE_DIR"):
        value = os.environ.get(env)
        if value:
            candidates.append(Path(value))

    for drive in _drive_roots():
        candidates += [
            drive / "GAME" / "Forge",
            drive / "Games" / "Forge",
            drive / "Forge",
            drive / "Program Files" / "Forge",
            drive / "Program Files (x86)" / "Forge",
        ]

    home = Path.home()
    candidates += [
        home / "AppData" / "Local" / "Programs" / "Forge",
        home / "Desktop" / "Forge",
        home / "Desktop" / "Desktop" / "Forge",
        home / "Downloads" / "Forge",
        home / "Documents" / "Forge",
    ]
    seen: set[str] = set()
    ordered: list[Path] = []
    for c in candidates:
        key = str(c).lower()
        if key not in seen:
            seen.add(key)
            ordered.append(c)
    return ordered


def _drive_roots() -> list[Path]:
    roots: list[Path] = []
    for letter in "CDEFGH":
        root = Path(f"{letter}:\\")
        if root.exists():
            roots.append(root)
    return roots


def card_db_path(forge_root: Path) -> Path | None:
    """Restituisce la cartella o l'archivio dei card script ufficiali."""
    folder = forge_root / "res" / "cardsfolder"
    if not folder.is_dir():
        return None
    archive = folder / "cardsfolder.zip"
    if archive.is_file():
        return archive
    if any(folder.glob("**/*.txt")):
        return folder
    return None


def official_editions_dir(forge_root: Path) -> Path:
    """Cartella delle edizioni ufficiali (contengono le rarita' delle carte)."""
    return forge_root / "res" / "editions"


def token_scripts_dir(forge_root: Path) -> Path:
    """Cartella degli script dei token ufficiali (res/tokenscripts)."""
    return forge_root / "res" / "tokenscripts"


def find_forge_root() -> Path | None:
    """Cerca automaticamente l'installazione di Forge."""
    for candidate in _candidate_roots():
        if card_db_path(candidate):
            return candidate

    # scansione superficiale: <disco>/<qualsiasi cartella>/Forge
    for drive in _drive_roots():
        try:
            for child in drive.iterdir():
                if not child.is_dir():
                    continue
                if card_db_path(child):
                    return child
                if child.name.lower() in {"game", "games", "giochi", "programmi", "programs"}:
                    for sub in child.iterdir():
                        if sub.is_dir() and card_db_path(sub):
                            return sub
        except (PermissionError, OSError):
            continue
    return None


def settings_file() -> Path:
    return app_data_dir() / "settings.json"


@dataclass
class Settings:
    """Percorsi configurabili dall'utente (con rilevamento automatico)."""

    forge_root: str = ""
    custom_dir: str = ""
    cache_dir: str = ""
    language: str = DEFAULT_LANGUAGE

    def resolved_forge_root(self) -> Path:
        return Path(self.forge_root) if self.forge_root else Path("")

    def resolved_custom_dir(self) -> Path:
        return Path(self.custom_dir) if self.custom_dir else DEFAULT_CUSTOM_DIR

    def resolved_cache_dir(self) -> Path:
        return Path(self.cache_dir) if self.cache_dir else DEFAULT_CACHE_DIR

    def editions_dir(self) -> Path:
        return self.resolved_custom_dir() / "editions"

    def cards_dir(self) -> Path:
        return self.resolved_custom_dir() / "cards"

    def tokens_dir(self) -> Path:
        """Script dei token custom (custom/tokens)."""
        return self.resolved_custom_dir() / "tokens"

    def pics_dir(self) -> Path:
        return self.resolved_cache_dir() / "pics" / "cards"

    def token_pics_dir(self) -> Path:
        """Immagini dei token custom (Cache/pics/tokens)."""
        return self.resolved_cache_dir() / "pics" / "tokens"

    def autodetect(self) -> bool:
        """Riempe i campi vuoti rilevando automaticamente Forge."""
        changed = False
        if not self.forge_root:
            root = find_forge_root()
            if root:
                self.forge_root = str(root)
                changed = True
        if not self.custom_dir and DEFAULT_CUSTOM_DIR.is_dir():
            self.custom_dir = str(DEFAULT_CUSTOM_DIR)
            changed = True
        if not self.cache_dir and DEFAULT_CACHE_DIR.is_dir():
            self.cache_dir = str(DEFAULT_CACHE_DIR)
            changed = True
        return changed

    def problems(self) -> list[str]:
        issues: list[str] = []
        root = self.resolved_forge_root()
        if not self.forge_root:
            issues.append(t("paths.forge_missing"))
        elif card_db_path(root) is None:
            issues.append(t("paths.no_scripts", root=root))
        if not self.resolved_custom_dir().is_dir():
            issues.append(t("paths.custom_missing", dir=self.resolved_custom_dir()))
        if not self.resolved_cache_dir().is_dir():
            issues.append(t("paths.cache_missing", dir=self.resolved_cache_dir()))
        return issues


def load_settings() -> Settings:
    path = settings_file()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            settings = Settings(
                forge_root=data.get("forge_root", ""),
                custom_dir=data.get("custom_dir", ""),
                cache_dir=data.get("cache_dir", ""),
                language=data.get("language", DEFAULT_LANGUAGE) or DEFAULT_LANGUAGE,
            )
        except (json.JSONDecodeError, OSError):
            settings = Settings()
    else:
        settings = Settings()
    settings.autodetect()
    return settings


def save_settings(settings: Settings) -> None:
    settings_file().write_text(
        json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8"
    )
