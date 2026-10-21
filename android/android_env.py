"""Adattamenti Android: permessi di accesso ai file e percorsi di Forge.

Su Android il tool gira dentro l'APK e legge le cartelle di Forge dalla memoria
condivisa. Da Android 11 serve il permesso speciale "Accesso a tutti i file"
(MANAGE_EXTERNAL_STORAGE), che non si concede con un semplice popup: va aperta
la schermata di sistema dedicata.
"""

from __future__ import annotations

import os
from pathlib import Path

from forge_importer import paths as P

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ

# Cartelle di accesso condiviso, in ordine di preferenza per i file chooser.
SHARED_DIRS = (
    "/storage/emulated/0/Pictures",
    "/storage/emulated/0/Download",
    "/storage/emulated/0/Documents",
    "/storage/emulated/0",
)

# Installazioni note dell'app Android di Forge (obb e data).
FORGE_ROOT_CANDIDATES = (
    "/storage/emulated/0/Android/obb/forge.app/Forge",
    "/storage/emulated/0/Android/obb/forge.app/forge",
    "/storage/emulated/0/Android/obb/forge.app",
    "/storage/emulated/0/Android/data/forge.app/files/Forge",
    "/storage/emulated/0/Android/data/forge.app/files/forge",
    "/storage/emulated/0/Android/data/forge.app/files",
    "/storage/emulated/0/Forge",
    "/storage/emulated/0/forge",
    "/sdcard/Forge",
    "/sdcard/forge",
)

FORGE_SCAN_BASES = (
    "/storage/emulated/0/Android/obb",
    "/storage/emulated/0/Android/data",
    "/sdcard/Android/obb",
    "/sdcard/Android/data",
)


def has_all_files_access() -> bool:
    """Vero se il permesso "Accesso a tutti i file" e' gia' concesso."""
    if not IS_ANDROID:
        return True
    try:
        from jnius import autoclass

        return bool(autoclass("android.os.Environment").isExternalStorageManager())
    except Exception:  # pragma: no cover - dipende dalla versione di Android
        return True


def request_storage_access() -> None:
    """Chiede l'accesso alla memoria condivisa.

    Prima i permessi classici (Android 6-10), poi, se serve, apre la schermata
    di sistema "Accesso a tutti i file" (Android 11+).
    """
    if not IS_ANDROID:
        return
    try:
        from android.permissions import Permission, request_permissions

        request_permissions(
            [
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
                "android.permission.MANAGE_EXTERNAL_STORAGE",
            ]
        )
    except Exception:  # pragma: no cover - dipende dall'ambiente
        pass

    if has_all_files_access():
        return
    try:
        from jnius import autoclass

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")
        intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
        intent.setData(Uri.parse("package:" + activity.getPackageName()))
        activity.startActivity(intent)
    except Exception:  # pragma: no cover - dipende dall'ambiente
        pass


def _first_existing(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            continue
    return None


def _looks_like_forge(root: Path) -> bool:
    try:
        return P.card_db_path(root) is not None
    except OSError:
        return False


def _iter_forge_candidates() -> list[Path]:
    """Percorsi plausibili di Forge su Android, inclusi package name variabili."""
    seen: set[str] = set()
    ordered: list[Path] = []

    def add(path: Path) -> None:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            ordered.append(path)

    for raw in FORGE_ROOT_CANDIDATES:
        add(Path(raw))

    for raw in FORGE_SCAN_BASES:
        base = Path(raw)
        try:
            for package_dir in base.iterdir():
                if not package_dir.is_dir():
                    continue
                add(package_dir / "Forge")
                add(package_dir / "forge")
                add(package_dir / "files" / "Forge")
                add(package_dir / "files" / "forge")
                add(package_dir / "files")
                add(package_dir)
        except OSError:
            continue
    return ordered


def find_forge_root() -> Path | None:
    """Cerca l'installazione Android di Forge fra i percorsi noti."""
    for root in _iter_forge_candidates():
        if _looks_like_forge(root):
            return root
        # la cartella dati puo' stare in una sottocartella (es. .../files/Forge)
        try:
            for child in root.iterdir():
                if child.is_dir() and _looks_like_forge(child):
                    return child
                if child.is_dir() and child.name.lower() == "forge" and _looks_like_forge(child):
                    return child
        except OSError:
            continue
    return None


def _custom_dir(root: Path) -> Path | None:
    """Cartella delle carte custom (contiene editions/ e cards/)."""
    candidates = [root / "data" / "custom", root / "custom", root / "data"]
    for candidate in candidates:
        try:
            if (candidate / "editions").is_dir() or (candidate / "cards").is_dir():
                return candidate
        except OSError:
            continue
    return _first_existing(candidates) or root


def _cache_dir(root: Path) -> Path | None:
    """Cache immagini di Forge (contiene pics/cards/<CODICE>/)."""
    candidates = [root / "cache", root / "Cache", root / "data" / "cache"]
    for candidate in candidates:
        try:
            if (candidate / "pics").is_dir():
                return candidate
        except OSError:
            continue
    return _first_existing(candidates) or root


def default_settings() -> P.Settings:
    """Impostazioni iniziali: percorsi Android rilevati automaticamente."""
    settings = P.Settings()
    try:
        root = find_forge_root()
        if root is not None:
            settings.forge_root = str(root)
            custom_dir = _custom_dir(root)
            cache_dir = _cache_dir(root)
            if custom_dir is not None:
                settings.custom_dir = str(custom_dir)
            if cache_dir is not None:
                settings.cache_dir = str(cache_dir)
    except OSError:
        pass
    return settings


def picker_start_dir() -> str:
    """Cartella da cui parte il selettore di file."""
    for candidate in SHARED_DIRS:
        if Path(candidate).is_dir():
            return candidate
    return "/storage/emulated/0" if Path("/storage/emulated/0").is_dir() else str(Path.home())
