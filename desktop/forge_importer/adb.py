"""Ponte verso un telefono Android tramite adb.

Forge su Android tiene i suoi file in
``/storage/emulated/0/Android/obb/forge.app/Forge``, una cartella protetta dai
permessi POSIX del kernel: il proprietario (l'app Forge, uid ``u0_a929``) ha
``rwx``, il gruppo ``ext_obb_rw`` ha ``rws``, tutti gli altri non hanno alcun
accesso. Per questo l'app Android non puo' scriverci mentre adb si': adb non e'
una app, e' un client che parla con il demone sul telefono ed esegue i comandi
come utente ``shell``, che appartiene proprio a ``ext_obb_rw``.

Questo modulo e' quindi l'unico punto in cui il tool desktop tocca il telefono:
individua adb, i dispositivi collegati e la cartella di Forge, poi copia i file
generati (edizione, script dei token, immagini della cache) al posto giusto.

La copia e' additiva e idempotente: i file con lo stesso nome vengono
sovrascritti e vengono rimossi solo i file rimasti orfani (le varianti numerate
di un'arte non piu' presente), cosi' un re-import non lascia immagini vecchie.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .i18n import t

# Percorsi in cui Forge tiene i suoi dati, dal piu' probabile.
REMOTE_ROOTS = (
    "/storage/emulated/0/Android/obb/forge.app/Forge",
    "/storage/emulated/0/Android/obb/forge.app/forge",
    "/storage/emulated/0/Android/data/forge.app/files/Forge",
    "/storage/emulated/0/Android/data/forge.app/files/forge",
)

VERIFY_TIMEOUT = 60
COPY_TIMEOUT = 900
_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# "Nome1.fullborder.jpg" -> "Nome.fullborder": individua le varianti numerate
# della stessa arte (numero ed estensione vengono ignorati di proposito).
_NUMBERED_RE = re.compile(r"^(?P<base>.+?)\d*\.fullborder\.[^.]+$", re.IGNORECASE)
# "12_angel_token.jpg" -> "angel_token": individua i collector di uno stesso token.
_TOKEN_RE = re.compile(r"^\d+_(?P<stem>.+?)\.[^.]+$")


class AdbError(RuntimeError):
    """Errore di comunicazione con adb o con il telefono."""


def _quote(path: str) -> str:
    """Racchiude un percorso remoto fra apici per la shell del telefono."""
    return "'" + path.replace("'", "'\\''") + "'"


def find_adb(explicit: str = "") -> str | None:
    """Percorso di adb.exe: quello indicato, poi PATH, poi le installazioni note."""
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return str(candidate)

    found: list[Path] = []
    which = shutil.which("adb")
    if which:
        found.append(Path(which))

    bases: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        bases.append(Path(local))
    bases.append(Path.home() / "AppData" / "Local")
    for base in bases:
        found.append(base / "Android" / "platform-tools" / "adb.exe")
        found.append(base / "Android" / "Sdk" / "platform-tools" / "adb.exe")
    found.append(Path("C:/Program Files/Android/platform-tools/adb.exe"))
    found.append(Path("C:/platform-tools/adb.exe"))

    for candidate in found:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


@dataclass(frozen=True)
class Device:
    """Un telefono visto da ``adb devices``."""

    serial: str
    state: str
    model: str = ""

    @property
    def ready(self) -> bool:
        return self.state == "device"

    @property
    def label(self) -> str:
        if self.model:
            return f"{self.model} ({self.serial})"
        return f"{self.serial} [{self.state}]"


class Adb:
    """Esecuzione dei comandi adb verso un dispositivo (o verso nessuno)."""

    def __init__(self, executable: str, serial: str = "") -> None:
        self.executable = executable
        self.serial = serial.strip()

    def _prefix(self) -> list[str]:
        command = [self.executable]
        if self.serial:
            command += ["-s", self.serial]
        return command

    def _run(self, args: list[str], timeout: int) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                self._prefix() + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                creationflags=_CREATION_FLAGS,
            )
        except FileNotFoundError as exc:
            raise AdbError(t("adb.not_found", path=self.executable)) from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError(t("adb.timeout", seconds=timeout)) from exc
        except OSError as exc:
            raise AdbError(t("adb.failed", error=exc)) from exc
        return (
            proc.returncode,
            proc.stdout.decode("utf-8", errors="replace"),
            proc.stderr.decode("utf-8", errors="replace"),
        )

    def check(self, args: list[str], timeout: int = VERIFY_TIMEOUT) -> str:
        """Esegue un comando e solleva AdbError se adb esce con errore."""
        code, out, err = self._run(args, timeout)
        if code != 0:
            message = (err.strip() or out.strip() or t("adb.exit_code", code=code))
            raise AdbError(t("adb.failed", error=message))
        return out

    # ------------------------------------------------------------- dispositivi

    def devices(self) -> list[Device]:
        """Elenca i dispositivi collegati (il filtro -s non si applica qui)."""
        saved, self.serial = self.serial, ""
        try:
            out = self.check(["devices", "-l"])
        finally:
            self.serial = saved
        result: list[Device] = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            info = dict(
                token.split(":", 1) for token in parts[2:] if ":" in token
            )
            result.append(
                Device(
                    serial=parts[0],
                    state=parts[1],
                    model=info.get("model", ""),
                )
            )
        return result

    def ready_device(self) -> Device | None:
        for device in self.devices():
            if device.ready:
                return device
        return None

    # ------------------------------------------------------------------- file

    def shell(self, command: str, timeout: int = VERIFY_TIMEOUT) -> str:
        return self.check(["shell", command], timeout)

    def exists(self, remote: str) -> bool:
        out = self.shell(f"[ -e {_quote(remote)} ] && echo 1 || echo 0")
        return out.strip() == "1"

    def listdir(self, remote: str) -> list[str]:
        """Nomi dei file contenuti in una cartella remota (vuoto se assente)."""
        out = self.shell(f"ls -1 {_quote(remote)} 2>/dev/null || true")
        return [line.strip() for line in out.splitlines() if line.strip()]

    def mkdirs(self, remote: str) -> None:
        self.shell(f"mkdir -p {_quote(remote)}")

    def pull(self, remote: str, local: Path, timeout: int = COPY_TIMEOUT) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        self.check(["pull", remote, str(local)], timeout)

    def push(self, local: Path, remote: str, timeout: int = COPY_TIMEOUT) -> None:
        self.check(["push", str(local), remote], timeout)

    def remove(self, remotes: list[str], chunk: int = 40) -> None:
        """Cancella file remoti, in blocchi per non allungare troppo il comando."""
        for start in range(0, len(remotes), chunk):
            block = remotes[start : start + chunk]
            args = " ".join(_quote(path) for path in block)
            self.shell(f"rm -f {args}")


@dataclass(frozen=True)
class RemoteForge:
    """Struttura di Forge sul telefono (solo i percorsi che ci servono)."""

    root: str

    @property
    def data_dir(self) -> str:
        return f"{self.root}/data"

    @property
    def custom_dir(self) -> str:
        return f"{self.data_dir}/custom"

    @property
    def editions_dir(self) -> str:
        return f"{self.custom_dir}/editions"

    @property
    def tokens_dir(self) -> str:
        return f"{self.custom_dir}/tokens"

    @property
    def cards_dir(self) -> str:
        return f"{self.custom_dir}/cards"

    @property
    def cache_dir(self) -> str:
        return f"{self.root}/cache"

    @property
    def pics_dir(self) -> str:
        return f"{self.cache_dir}/pics/cards"

    @property
    def token_pics_dir(self) -> str:
        return f"{self.cache_dir}/pics/tokens"

    @property
    def card_scripts_dir(self) -> str:
        return f"{self.root}/res/cardsfolder"


def detect_forge_root(adb: Adb) -> str | None:
    """Cerca la cartella di Forge fra i percorsi noti di Android."""
    for candidate in REMOTE_ROOTS:
        try:
            if adb.exists(f"{candidate}/data") and adb.exists(f"{candidate}/res"):
                return candidate
        except AdbError:
            return None
    return None


def _numbered_key(name: str) -> str:
    """Chiave dell'arte di una carta: ignora numero di variante ed estensione."""
    match = _NUMBERED_RE.match(name)
    if not match:
        return name
    return f"{match.group('base')}.fullborder"


def _token_key(name: str) -> str:
    """Chiave di un token: ignora il collector e l'estensione."""
    match = _TOKEN_RE.match(name)
    return match.group("stem") if match else name


class PhoneTarget:
    """Copia sul telefono i file generati dal tool.

    Edition e immagini vivono in cartelle diverse (``data/custom`` e
    ``cache/pics``): un set viene riversato in blocco e poi ripulito dai file
    che non fanno piu' parte dell'edizione locale.
    """

    def __init__(self, executable: str, serial: str, forge_root: str) -> None:
        self.adb = Adb(executable, serial)
        self.forge = RemoteForge(forge_root)

    def verify(self) -> Device | None:
        """Controlla telefono collegato e cartella di Forge raggiungibile."""
        device = self.adb.ready_device()
        if device is None:
            raise AdbError(t("adb.no_device"))
        if not self.adb.exists(f"{self.forge.root}/data"):
            raise AdbError(t("adb.no_forge", root=self.forge.root))
        return device

    # ------------------------------------------------------------------ invio

    def push_set(self, code: str, custom_dir: Path, cache_dir: Path) -> list[str]:
        """Copia edizione, script dei token e immagini del set; ritorna il log."""
        self.verify()
        messages: list[str] = []
        self.adb.mkdirs(self.forge.editions_dir)
        self.adb.mkdirs(self.forge.tokens_dir)

        edition = custom_dir / "editions" / f"{code}.txt"
        if edition.is_file():
            self.adb.push(edition, f"{self.forge.editions_dir}/")
            messages.append(t("push.edition", name=edition.name))
        else:
            messages.append(t("push.no_edition", name=edition.name))

        token_scripts = custom_dir / "tokens"
        if token_scripts.is_dir():
            pushed = self._push_folder(token_scripts, self.forge.tokens_dir, ".txt")
            if pushed:
                messages.append(t("push.tokens", count=pushed))

        # Gli override delle carte (es. carte che creano i token custom) vivono
        # in ``custom/cards``: senza di essi Forge usa gli script ufficiali e i
        # token custom non compaiono. La cartella e' annidata (a/, b/, ...),
        # quindi la copiamo ricorsivamente nella sua destinazione.
        card_scripts = custom_dir / "cards"
        if card_scripts.is_dir():
            self.adb.mkdirs(self.forge.custom_dir)
            self.adb.push(card_scripts, f"{self.forge.custom_dir}/")
            count = sum(1 for _ in card_scripts.rglob("*.txt"))
            if count:
                messages.append(t("push.cards", count=count))

        images = cache_dir / "pics" / "cards" / code
        if images.is_dir():
            count = self._push_images(images, self.forge.pics_dir, code, _numbered_key)
            messages.append(t("push.images", count=count, code=code))

        token_images = cache_dir / "pics" / "tokens" / code
        if token_images.is_dir():
            count = self._push_images(
                token_images, self.forge.token_pics_dir, code, _token_key
            )
            messages.append(t("push.token_images", count=count, code=code))

        return messages

    # ---------------------------------------------------------------- helper

    def _push_folder(self, local_dir: Path, remote_dir: str, suffix: str) -> int:
        """Copia i file con una certa estensione (gli script dei token)."""
        files = [p for p in sorted(local_dir.iterdir()) if p.is_file() and p.suffix == suffix]
        if not files:
            return 0
        self.adb.mkdirs(remote_dir)
        for path in files:
            self.adb.push(path, f"{remote_dir}/")
        return len(files)

    def _push_images(
        self, local_dir: Path, remote_parent: str, code: str, key_of
    ) -> int:
        """Riversa una cartella di immagini e rimuove le varianti rimaste orfane."""
        local_names = {p.name for p in local_dir.iterdir() if p.is_file()}
        if not local_names:
            return 0
        self.adb.mkdirs(remote_parent)
        # adb push di una cartella dentro una cartella esistente crea
        # <destinazione>/<nome cartella>, cioe' <remote>/<CODE>.
        self.adb.push(local_dir, f"{remote_parent}/")

        remote_dir = f"{remote_parent}/{code}"
        stale = self._stale_files(remote_dir, local_names, key_of)
        if stale:
            self.adb.remove([f"{remote_dir}/{name}" for name in stale])
        return len(local_names)

    def _stale_files(self, remote_dir: str, local_names: set[str], key_of) -> list[str]:
        """File remoti della stessa arte ma non piu' presenti in locale.

        Serve a non lasciare sul telefono le varianti numerate di un'arte
        rimossa (``Nome2.fullborder.jpg`` quando resta solo ``Nome``): la
        chiave e' il nome senza numero, quindi i file di altre carte o di
        edizioni ufficiali nello stesso codice non vengono toccati.
        """
        try:
            remote_names = self.adb.listdir(remote_dir)
        except AdbError:
            return []
        known = {key_of(name) for name in local_names}
        return [
            name
            for name in remote_names
            if name not in local_names and key_of(name) in known
        ]
