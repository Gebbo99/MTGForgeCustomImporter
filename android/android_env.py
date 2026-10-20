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
    "/storage/emulated/0/Android/obb/forge.app",
    "/storage/emulated/0/Android/data/forge.app/files/Forge",
    "/storage/emulated/0/Android/data/forge.app/files",
    "/storage/emulated/0/Forge",
    "/sdcard/Forge",
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
        if candidate.is_dir():
            return candidate
    return None


def _looks_like_forge(root: Path) -> bool:
    return P.card_db_path(root) is not None


def find_forge_root() -> Path | None:
    """Cerca l'installazione Android di Forge fra i percorsi noti."""
    roots = [Path(p) for p in FORGE_ROOT_CANDIDATES]
    for root in roots:
        if _looks_like_forge(root):
            return root
        # la cartella dati puo' stare in una sottocartella (es. .../files/Forge)
        try:
            for child in root.iterdir():
                if child.is_dir() and _looks_like_forge(child):
                    return child
        except OSError:
            continue
    return None


def _custom_dir(root: Path) -> Path | None:
    """Cartella delle carte custom (contiene editions/ e cards/)."""
    candidates = [root / "data" / "custom", root / "custom", root / "data"]
    for candidate in candidates:
        if (candidate / "editions").is_dir() or (candidate / "cards").is_dir():
            return candidate
    return _first_existing(candidates) or root


def _cache_dir(root: Path) -> Path | None:
    """Cache immagini di Forge (contiene pics/cards/<CODICE>/)."""
    candidates = [root / "cache", root / "Cache", root / "data" / "cache"]
    for candidate in candidates:
        if (candidate / "pics").is_dir():
            return candidate
    return _first_existing(candidates) or root


def default_settings() -> P.Settings:
    """Impostazioni iniziali: percorsi Android rilevati automaticamente."""
    settings = P.Settings()
    root = find_forge_root()
    if root is not None:
        settings.forge_root = str(root)
        settings.custom_dir = str(_custom_dir(root))
        settings.cache_dir = str(_cache_dir(root))
    return settings


def picker_start_dir() -> str:
    """Cartella da cui parte il selettore di file."""
    for candidate in SHARED_DIRS:
        if Path(candidate).is_dir():
            return candidate
    return "/storage/emulated/0" if Path("/storage/emulated/0").is_dir() else str(Path.home())
