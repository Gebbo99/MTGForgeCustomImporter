"""GUI desktop per importare carte custom (re-skin) in MTG Forge.

Flusso di lavoro:
  1. si sceglie una cartella (o piu' immagini) contenente le carte proxy;
  2. per ogni immagine il tool legge il testo (OCR) e riconosce la carta (o il
     token) base confrontandola con gli script di Forge;
  3. le proposte vengono mostrate in una tabella e possono essere corrette
     (nuovo nome, rarita', artista, base);
  4. l'importazione scrive immagine, script ed edizione custom; per i token
     aggiorna anche le carte del set che li creano.

Il tool e' un companion esterno: non modifica Forge, scrive soltanto nei
percorsi nativi delle carte custom (%APPDATA%\\Forge\\custom e cache immagini).
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from . import adb
from . import i18n
from . import paths as P
from .carddb import CardDB, CardInfo, faces_of
from .cards import (
    DEFAULT_RARITY,
    custom_name_from_filename,
    detect_basic_land,
    is_basic_land,
    name_from_filename,
    real_name_from_filename,
    same_name_ignoring_spaces,
    token_name,
)
from .generator import (
    RARITIES,
    Edition,
    ImportItem,
    ImportOptions,
    Importer,
    copy_mechanic,
    copy_mechanics_in,
    emblem_base_name,
    emblem_hint,
    scan_images,
)
from .i18n import code_for_label, label_for_code, language_labels, t
from .matcher import Candidate, Matcher, TokenMatcher
from .ocr import OcrUnavailable, is_token, read_image
from .rarity import RarityIndex
from .textutil import has_letters

COLOR_TEXT = "#e6e6e6"
COLOR_OK = "#3fb950"
COLOR_WARN = "#d29922"
COLOR_BAD = "#f85149"


@dataclass
class Row:
    """Una riga della tabella: un'immagine con la sua proposta di importazione."""

    iid: str
    image_path: Path
    reading: object | None = None
    candidates: list[Candidate] = field(default_factory=list)
    base: CardInfo | None = None
    score: float = 0.0
    reason: str = ""
    new_name: str = ""
    rarity: str = DEFAULT_RARITY
    artist: str = ""
    note: str = ""
    is_token: bool = False
    is_copy: bool = False
    copy_card: str = ""
    copy_prefix: str = ""
    is_emblem: bool = False
    # Retro di una carta a due lati collegato a mano: linked_front e' l'iid
    # della riga del fronte a cui appartiene (vuoto = non collegato).
    is_back: bool = False
    linked_front: str = ""

    def status(self) -> tuple[str, str]:
        """(chiave di traduzione dello stato, tag colore) per evidenziare le anomalie."""
        if self.is_back:
            return "state.back_linked" if self.linked_front else "state.back_unlinked", (
                "ok" if self.linked_front else "warn"
            )
        if self.reading is None:
            return "state.read_error", "bad"
        if self.is_emblem:
            return "state.emblem", "ok" if self.base else "bad"
        if self.is_copy:
            return "state.copy_token", "ok"
        if self.base is None:
            return "state.choose_base", "bad"
        # Token omonimi (stesso nome, stesso P/T, colori diversi): il
        # punteggio alto non basta, la base va confermata a mano.
        if self.reason == "reason.token_ambiguous":
            return "state.check", "warn"
        if self.score >= 90:
            return "state.ready", "ok"
        return "state.check", "warn"


class ForgeImporterApp(ctk.CTk):
    """Finestra principale."""

    def __init__(self) -> None:
        super().__init__()
        self.settings = P.load_settings()
        i18n.set_language(self.settings.language)
        self.title("Forge Custom Card Importer")
        self.geometry("1280x760")
        self.minsize(1040, 620)

        self.db: CardDB | None = None
        self.matcher: Matcher | None = None
        self.token_matcher: TokenMatcher | None = None
        self.rarities: RarityIndex | None = None
        self.rows: dict[str, Row] = {}
        self.editions: list[Edition] = []
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self._row_counter = 0
        self._editions_initialized = False
        # Stato delle caselle, conservato quando la UI viene ricostruita al
        # cambio di lingua.
        self._crop_value = False
        self._move_value = True
        self._token_count = 0

        self._build_layout()
        self._refresh_editions()
        self._show_paths()
        self.after(80, self._poll_queue)
        self._start_db_load()
        if self.settings.uses_phone():
            self.after(200, self._check_phone)

    # ------------------------------------------------------------------ layout

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_toolbar()
        self._build_info_bar()
        self._build_table()
        self._build_bottom()

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self)
        bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        for col in range(8):
            bar.grid_columnconfigure(col, weight=0)
        bar.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(bar, text=t("toolbar.add_folder"), command=self.add_folder).grid(
            row=0, column=0, padx=(10, 6), pady=10
        )
        ctk.CTkButton(bar, text=t("toolbar.add_images"), command=self.add_files).grid(
            row=0, column=1, padx=6, pady=10
        )
        ctk.CTkButton(bar, text=t("toolbar.clear"), width=80, command=self.clear_rows).grid(
            row=0, column=2, padx=6, pady=10
        )

        edition_box = ctk.CTkFrame(bar, fg_color="transparent")
        edition_box.grid(row=0, column=3, sticky="e", padx=6)
        ctk.CTkLabel(edition_box, text=t("toolbar.edition")).pack(side="left", padx=(0, 6))
        self.edition_menu = ctk.CTkOptionMenu(
            edition_box, values=[t("common.new_edition")], width=240, command=lambda _v: None
        )
        self.edition_menu.pack(side="left")

        language_box = ctk.CTkFrame(bar, fg_color="transparent")
        language_box.grid(row=0, column=4, sticky="e", padx=6)
        ctk.CTkLabel(language_box, text=t("app.language_label")).pack(side="left", padx=(0, 6))
        self.language_menu = ctk.CTkOptionMenu(
            language_box,
            values=language_labels(),
            width=110,
            command=self._on_language_change,
        )
        self.language_menu.set(label_for_code(i18n.get_language()))
        self.language_menu.pack(side="left")

        ctk.CTkButton(bar, text=t("toolbar.link_faces"), width=160, command=self.link_faces).grid(
            row=0, column=5, padx=10, pady=10
        )

        ctk.CTkButton(bar, text=t("toolbar.settings"), width=110, command=self.open_settings).grid(
            row=0, column=6, padx=10, pady=10
        )

    def _build_info_bar(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="ew", padx=12)
        frame.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(frame, text=t("status.starting"), anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew")

        self.progress = ctk.CTkProgressBar(frame, width=220)
        self.progress.set(0)
        self.progress.grid(row=0, column=1, sticky="e")

    def _build_table(self) -> None:
        frame = ctk.CTkFrame(self)
        frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=6)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Forge.Treeview",
            background="#2b2b2b",
            fieldbackground="#2b2b2b",
            foreground="#e6e6e6",
            rowheight=26,
            borderwidth=0,
        )
        style.configure(
            "Forge.Treeview.Heading", background="#3a3a3a", foreground="#ffffff"
        )
        style.map("Forge.Treeview", background=[("selected", "#1f6feb")])

        columns = (
            ("image", t("col.image"), 210, "w"),
            ("title", t("col.title"), 160, "w"),
            ("base", t("col.base"), 240, "w"),
            ("conf", t("col.conf"), 60, "center"),
            ("reason", t("col.reason"), 120, "w"),
            ("new", t("col.new"), 190, "w"),
            ("rar", t("col.rar"), 50, "center"),
            ("status", t("col.status"), 130, "w"),
        )
        self.tree = ttk.Treeview(
            frame, columns=[c[0] for c in columns], show="headings", style="Forge.Treeview"
        )
        for key, label, width, anchor in columns:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key in {"base", "new"}))
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns", pady=6)
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.tag_configure("ok", foreground=COLOR_OK)
        self.tree.tag_configure("warn", foreground=COLOR_WARN)
        self.tree.tag_configure("bad", foreground=COLOR_BAD)
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())

    def _build_bottom(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        bar.grid_columnconfigure(2, weight=1)

        ctk.CTkButton(bar, text=t("bottom.edit"), command=self.edit_selected).grid(
            row=0, column=0, padx=(0, 6)
        )
        ctk.CTkButton(bar, text=t("bottom.remove"), command=self.remove_selected).grid(
            row=0, column=1, padx=6
        )

        self.crop_var = tk.BooleanVar(value=self._crop_value)
        self.move_var = tk.BooleanVar(value=self._move_value)
        ctk.CTkCheckBox(
            bar, text=t("bottom.crop"), variable=self.crop_var
        ).grid(row=0, column=2, padx=12, sticky="e")
        ctk.CTkCheckBox(
            bar, text=t("bottom.move"), variable=self.move_var
        ).grid(row=0, column=3, padx=12, sticky="e")

        dest_box = ctk.CTkFrame(bar, fg_color="transparent")
        dest_box.grid(row=0, column=4, padx=(12, 0), sticky="e")
        ctk.CTkLabel(dest_box, text=t("bottom.destination")).pack(side="left", padx=(0, 6))
        self.target_menu = ctk.CTkSegmentedButton(
            dest_box,
            values=[t("target.pc"), t("target.phone")],
            command=self._on_target_change,
        )
        self.target_menu.set(self._target_label())
        self.target_menu.pack(side="left")

        self.import_button = ctk.CTkButton(
            bar,
            text=t("bottom.import"),
            width=170,
            height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.import_all,
        )
        self.import_button.grid(row=0, column=5, padx=(12, 0))

        # Copia di un set gia' importato: utile per allineare il telefono senza
        # ripetere OCR e riconoscimento. Attivo solo con destinazione Telefono.
        self.send_button = ctk.CTkButton(
            bar,
            text=t("bottom.send_phone"),
            width=165,
            height=36,
            command=self.send_to_phone,
        )
        self.send_button.grid(row=0, column=6, padx=(12, 0))
        self._refresh_buttons()

    # -------------------------------------------------------------- telefono

    def _target_label(self) -> str:
        return t("target.phone") if self.settings.uses_phone() else t("target.pc")

    def _on_target_change(self, label: str) -> None:
        """Cambia la destinazione dell'importazione (PC oppure telefono via adb)."""
        self.settings.target = "phone" if label == t("target.phone") else "pc"
        P.save_settings(self.settings)
        self._refresh_buttons()
        if self.settings.uses_phone():
            self._check_phone()
        else:
            self._show_paths()

    def _refresh_buttons(self) -> None:
        """Abilita i pulsanti in base allo stato di lavoro e alla destinazione."""
        self.import_button.configure(state="disabled" if self.busy else "normal")
        can_send = self.settings.uses_phone() and not self.busy
        self.send_button.configure(state="normal" if can_send else "disabled")

    def _check_phone(self) -> None:
        """Individua adb, il telefono e la cartella di Forge, senza bloccare la UI."""
        settings = self.settings
        if not settings.adb_path:
            found = adb.find_adb()
            if found:
                settings.adb_path = found
                P.save_settings(settings)
        if not settings.adb_path:
            self.status_label.configure(text=t("settings.adb_missing"), text_color=COLOR_WARN)
            return
        self.status_label.configure(text=t("status.starting"), text_color=COLOR_TEXT)
        threading.Thread(
            target=self._phone_probe_worker, args=(settings.adb_path,), daemon=True
        ).start()

    def _phone_probe_worker(self, executable: str) -> None:
        try:
            client = adb.Adb(executable, self.settings.adb_serial)
            ready = [d for d in client.devices() if d.ready]
            if not ready:
                self.q.put(("phone_error", t("adb.no_device")))
                return
            device = ready[0]
            client.serial = device.serial
            root = self.settings.adb_forge_root or adb.detect_forge_root(client)
            if not root:
                self.q.put(("phone_error", t("adb.not_detected")))
                return
            self.q.put(("phone_ready", device, root))
        except adb.AdbError as exc:
            self.q.put(("phone_error", str(exc)))

    # ------------------------------------------------------------- impostazioni

    def _on_language_change(self, label: str) -> None:
        """Cambia lingua: salva la scelta e ricostruisce l'interfaccia."""
        code = code_for_label(label)
        if code == i18n.get_language():
            return
        i18n.set_language(code)
        self.settings.language = code
        P.save_settings(self.settings)
        self._rebuild_ui()

    def _rebuild_ui(self) -> None:
        """Ricostruisce i widget dopo un cambio di lingua, conservando lo stato."""
        self._crop_value = self.crop_var.get()
        self._move_value = self.move_var.get()
        edition_choice = self.edition_menu.get()

        for child in self.winfo_children():
            child.destroy()

        self._build_layout()
        self.crop_var.set(self._crop_value)
        self.move_var.set(self._move_value)
        self._refresh_editions()
        if edition_choice in self.edition_menu.cget("values"):
            self.edition_menu.set(edition_choice)

        for iid, row in self.rows.items():
            self.tree.insert(
                "", "end", iid=iid, values=self._values(row), tags=(row.status()[1],)
            )

        if self.db is not None:
            self._show_ready()
        else:
            self._show_paths()

    def _show_ready(self) -> None:
        text = t(
            "status.db_ready",
            cards=len(self.db.cards),
            tokens=self._token_count,
            root=self.settings.forge_root,
        )
        if self.settings.uses_phone():
            text += "  |  " + t(
                "settings.adb_ok",
                device=self.settings.adb_serial,
                root=self.settings.adb_forge_root,
            )
        self.status_label.configure(text=text, text_color=COLOR_OK)

    def _show_paths(self) -> None:
        if self.settings.uses_phone():
            problems = self.settings.phone_problems()
            if problems:
                self.status_label.configure(
                    text="\u26a0 " + "  |  ".join(problems), text_color=COLOR_WARN
                )
            else:
                self.status_label.configure(
                    text=t(
                        "settings.adb_ok",
                        device=self.settings.adb_serial,
                        root=self.settings.adb_forge_root,
                    ),
                    text_color=COLOR_OK,
                )
            return
        problems = self.settings.problems()
        if problems:
            self.status_label.configure(text="\u26a0 " + "  |  ".join(problems), text_color=COLOR_WARN)
        else:
            self.status_label.configure(
                text=t("status.forge_path", root=self.settings.forge_root), text_color=COLOR_OK
            )

    def open_settings(self) -> None:
        SettingsDialog(self, self.settings, self._on_settings_saved)

    def _on_settings_saved(self) -> None:
        P.save_settings(self.settings)
        self._show_paths()
        self._refresh_editions()
        self.db = None
        self.matcher = None
        self.token_matcher = None
        self._start_db_load()
        if self.settings.uses_phone():
            self._check_phone()

    def _refresh_editions(self) -> None:
        editions_dir = self.settings.editions_dir()
        self.editions = []
        if editions_dir.is_dir():
            for file in sorted(editions_dir.glob("*.txt")):
                edition = Edition.load(file)
                if edition.code:
                    self.editions.append(edition)
        values = [f"{e.code} - {e.name}" for e in self.editions] + [t("common.new_edition")]
        self.edition_menu.configure(values=values)
        if self.edition_menu.get() not in values:
            self.edition_menu.set(values[0])
        elif not self._editions_initialized and self.editions:
            self.edition_menu.set(values[0])
        self._editions_initialized = True

    def _target_edition(self) -> tuple[Path, str, str] | None:
        """Restituisce (percorso, codice, nome) dell'edizione di destinazione."""
        choice = self.edition_menu.get()
        for edition in self.editions:
            if f"{edition.code} - {edition.name}" == choice:
                return edition.path, edition.code, edition.name
        dialog = NewEditionDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return None
        code, name = dialog.result
        path = self.settings.editions_dir() / f"{code}.txt"
        return path, code, name

    def _selected_edition(self) -> Edition | None:
        """Edizione scelta nella casella (nessuna se si crea una nuova edizione)."""
        choice = self.edition_menu.get()
        for edition in self.editions:
            if f"{edition.code} - {edition.name}" == choice:
                return edition
        return None

    def _copy_cards(self) -> dict[str, tuple[str, str]]:
        """{nome carta (lower): (prefisso, nome)} per i token-copia del set.

        Eternalize ed Embalm non hanno uno script token: il token e' la copia
        della carta con un'immagine dedicata. Si cercano quindi nel set le
        carte che hanno la keyword, sia fra quelle gia' scritte in
        custom/cards sia fra le righe della tabella non ancora importate.
        """
        names: set[str] = set()
        edition = self._selected_edition()
        if edition is not None:
            names |= edition.names()
        for row in self.rows.values():
            if not row.is_token and row.new_name.strip():
                names.add(row.new_name.strip().lower())

        found = copy_mechanics_in(self.settings.resolved_custom_dir() / "cards", names)
        if self.db is None:
            return found
        for row in self.rows.values():
            key = row.new_name.strip().lower()
            if row.is_token or row.base is None or key in found:
                continue
            try:
                prefix = copy_mechanic(self.db.script_text(row.base))
            except (KeyError, OSError):
                continue
            if prefix:
                found[key] = (prefix, row.new_name.strip())

        # Le varianti (flavorName) non hanno uno script in custom/cards: la
        # keyword va cercata nello script della carta base ufficiale, cosi' il
        # token-copia viene riconosciuto anche quando la carta che lo genera e'
        # gia' registrata nell'edizione e non e' in questo lotto di import.
        if edition is not None:
            for entry in edition.entries:
                key = entry.card_name.strip().lower()
                if not key or key in found:
                    continue
                base = self.db.by_name(entry.name.strip())
                if base is None:
                    continue
                try:
                    prefix = copy_mechanic(self.db.script_text(base))
                except (KeyError, OSError):
                    continue
                if prefix:
                    found[key] = (prefix, entry.card_name.strip())
        return found

    def _mark_copy_tokens(self) -> None:
        """Segnala come token-copia le righe token che copiano una carta del set.

        Eternalize/Embalm non hanno uno script: il token e' una copia della
        carta con un'immagine dedicata in [other]. Il proxy del token puo'
        avere una base riconosciuta (viene scambiato per un token normale),
        quindi non basta guardare le righe senza base: si confronta il nome.
        """
        copies = self._copy_cards()
        for row in self.rows.values():
            if not row.is_token:
                continue
            entry = copies.get(row.new_name.strip().lower())
            if entry is None:
                # Se l'OCR non legge il titolo il proxy del token-copia si
                # chiama come la carta ("<NomeReale> (<Tipo>) (Token)"): il
                # nome reale nel file aggancia comunque la copia.
                real = real_name_from_filename(row.image_path).strip().lower()
                entry = copies.get(real)
            if entry is None:
                if row.is_copy or row.copy_prefix:
                    row.is_copy = False
                    row.copy_card = ""
                    row.copy_prefix = ""
                    self._refresh_row(row)
                continue
            if row.is_copy and row.copy_card == entry[1] and row.copy_prefix == entry[0]:
                continue
            row.is_copy = True
            row.copy_card = entry[1]
            row.copy_prefix = entry[0]
            row.reason = "reason.copy"
            self._refresh_row(row)

    # ------------------------------------------------------------------- dati

    def _start_db_load(self) -> None:
        if not self.settings.forge_root:
            self.status_label.configure(text=t("status.forge_missing"), text_color=COLOR_BAD)
            return
        db_path = P.card_db_path(Path(self.settings.forge_root))
        if db_path is None:
            self.status_label.configure(text=t("status.db_missing"), text_color=COLOR_BAD)
            return
        self.status_label.configure(text=t("status.loading_db"), text_color=COLOR_TEXT)
        editions = P.official_editions_dir(Path(self.settings.forge_root))
        tokens = P.token_scripts_dir(Path(self.settings.forge_root))
        threading.Thread(
            target=self._load_db_worker, args=(db_path, editions, tokens), daemon=True
        ).start()

    def _load_db_worker(self, db_path: Path, editions_dir: Path, tokens_dir: Path) -> None:
        try:
            db = CardDB.load(db_path, P.app_data_dir() / "cardindex.json")
            rarities = RarityIndex.load(editions_dir)
            token_db = CardDB.load_tokens(tokens_dir)
            self.q.put(("db_ready", db, rarities, token_db))
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            self.q.put(("fatal", t("status.db_read_error", error=exc)))

    # ------------------------------------------------------------------ input

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title=t("dialog.folder_title"))
        if not folder:
            return
        images = scan_images(Path(folder))
        if not images:
            messagebox.showinfo(t("msg.no_images_title"), t("msg.no_images_text"))
            return
        self._enqueue(images)

    def add_files(self) -> None:
        files = filedialog.askopenfilenames(
            title=t("dialog.files_title"),
            filetypes=[
                (t("dialog.filter_images"), "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                (t("dialog.filter_all"), "*.*"),
            ],
        )
        if files:
            self._enqueue([Path(f) for f in files])

    def _enqueue(self, images: list[Path]) -> None:
        if self.matcher is None:
            messagebox.showinfo(t("msg.wait_title"), t("msg.wait_text"))
            return
        self._set_busy(True)
        self.progress.set(0)
        self.status_label.configure(
            text=t("status.analyzing", count=len(images)), text_color=COLOR_TEXT
        )
        threading.Thread(target=self._analyze_worker, args=(images,), daemon=True).start()

    def _analyze_worker(self, images: list[Path]) -> None:
        total = len(images)
        for index, path in enumerate(images, start=1):
            try:
                reading = read_image(path)
                candidates = self._match(reading)
                self.q.put(("row", path, reading, candidates))
            except OcrUnavailable as exc:
                self.q.put(("fatal", str(exc)))
                return
            except Exception as exc:
                self.q.put(("row_error", path, str(exc)))
            self.q.put(("progress", index, total))
        self.q.put(("analyze_done",))

    def _match(self, reading) -> list[Candidate]:
        """Carte e token hanno archivi diversi: si sceglie il motore adatto."""
        if is_token(reading):
            return self.token_matcher.match(reading, limit=4) if self.token_matcher else []
        return self.matcher.match(reading, limit=4)

    # --------------------------------------------------------------- tabella

    def _add_row(self, path: Path, reading, candidates: list[Candidate]) -> None:
        self._row_counter += 1
        iid = f"r{self._row_counter}"
        token = reading is not None and is_token(reading)
        best = candidates[0] if candidates else None
        title = (getattr(reading, "title", "") or "").strip()
        if not has_letters(title):
            title = name_from_filename(path)
        base = best.card if best else None
        score = best.score if best else 0.0
        reason = best.reason if best else ""
        if token:
            title = token_name(title)
        else:
            base, title, score, reason = self._resolve_basic_land(
                base, title, path.stem, score, reason
            )
            # Il nome fra parentesi nel file e' scritto dall'utente ed e' uguale
            # per tutte le arti della stessa carta: se il titolo letto dall'OCR
            # coincide a meno di spazi lo si riporta a quella grafia, altrimenti
            # un refuso su una sola immagine spezzerebbe il gruppo di arti.
            custom = custom_name_from_filename(path)
            if custom and same_name_ignoring_spaces(title, custom):
                title = custom
        emblem = not token and emblem_hint(title, path.stem) and (base is None or score < 80)
        if emblem:
            title, base, score, reason = self._resolve_emblem(title, path.stem, base, score, reason)
        if base is None and not token and self.db is not None:
            # Il retro di una carta multi-faccia puo' arrivare senza testo
            # delle regole: se il nome reale nel file e' la faccia di una carta
            # nota la base si ricava da li', cosi' le due immagini vengono
            # abbinate in fase di scrittura.
            lookup = self.db.by_face(real_name_from_filename(path))
            if lookup is not None:
                base, score, reason = lookup[0], 100.0, "reason.face_match"
        row = Row(
            iid=iid,
            image_path=path,
            reading=reading,
            candidates=candidates,
            base=base,
            score=score,
            reason=reason,
            new_name=title,
            rarity=self._deduced_rarity(base),
            is_token=token,
            is_emblem=emblem,
        )
        self.rows[iid] = row
        self.tree.insert("", "end", iid=iid, values=self._values(row), tags=(row.status()[1],))

    def _resolve_basic_land(
        self, base: CardInfo | None, title: str, stem: str, score: float, reason: str
    ) -> tuple[CardInfo | None, str, float, str]:
        """Associa le terre base e normalizza il nome al termine ufficiale.

        Le terre base in arte completa non hanno testo delle regole, quindi il
        riconoscimento fallisce e viene letto il nome dal file ("Forest A").
        In quel caso si usa la terra base ufficiale (Forest) e si riporta il
        nome a quello canonico, cosi' le diverse art diventano stampe della
        stessa terra, giocabile senza limite di copie.
        """
        if base is not None and not is_basic_land(base):
            return base, title, score, reason
        land = detect_basic_land(title) or detect_basic_land(stem)
        if not land or self.db is None:
            return base, title, score, reason
        card = self.db.by_name(land)
        if card is None:
            return base, title, score, reason
        return card, land, 100.0, "reason.basic_land"

    def _resolve_emblem(
        self, title: str, stem: str, base: CardInfo | None, score: float, reason: str
    ) -> tuple[str, CardInfo | None, float, str]:
        """Aggancia un emblema al Planeswalker a cui appartiene.

        Il file o il titolo letto portano il nome dell'emblema ("Emblem —
        Chandra, Torch of Defiance"), mentre la chiave immagine si ricava dal
        nome ufficiale della carta base: si cerca quindi il Planeswalker con il
        nome ripulito dal prefisso, cosi' l'utente lo trova gia' selezionato.
        """
        hint = emblem_base_name(title) or emblem_base_name(stem)
        if not hint:
            return title, base, score, reason
        card, hint_score = self.matcher.match_name(hint) if self.matcher else (None, 0.0)
        if card is None or hint_score < 80:
            return hint, base, score, reason
        return hint, card, hint_score, "reason.emblem"

    def _deduced_rarity(self, base: CardInfo | None) -> str:
        """Rarita' della carta base dedotta dalle edizioni ufficiali di Forge."""
        if base is None or self.rarities is None:
            return DEFAULT_RARITY
        return self.rarities.lookup(base.name) or DEFAULT_RARITY

    def _reason_text(self, row: Row) -> str:
        """Motivo del riconoscimento tradotto (la riga conserva la chiave)."""
        if not row.reason:
            return "\u2014"
        if row.reason == "reason.copy":
            return t("reason.copy", prefix=row.copy_prefix)
        return t(row.reason)

    def _values(self, row: Row) -> tuple:
        status_key, _ = row.status()
        if row.is_copy:
            base_text = t("value.copy_of", name=row.copy_card)
        elif row.is_back:
            front = self.rows.get(row.linked_front)
            base_text = (
                t("value.back_of", name=front.new_name or front.image_path.name)
                if front is not None
                else t("common.none")
            )
        elif row.base:
            base_text = row.base.name
        else:
            base_text = t("common.none")
        return (
            row.image_path.name,
            getattr(row.reading, "title", "") or "\u2014",
            base_text,
            f"{row.score:.0f}" if row.base else "\u2014",
            self._reason_text(row),
            row.new_name,
            "\u2014" if (row.is_token or row.is_emblem or row.is_back) else row.rarity,
            t(status_key),
        )

    def _refresh_row(self, row: Row) -> None:
        self.tree.item(row.iid, values=self._values(row), tags=(row.status()[1],))

    def _selected_rows(self) -> list[Row]:
        return [self.rows[iid] for iid in self.tree.selection() if iid in self.rows]

    def edit_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            messagebox.showinfo(t("msg.select_title"), t("msg.select_text"))
            return
        row = rows[0]
        matcher = self.token_matcher if row.is_token else self.matcher
        if matcher is None:
            return
        dialog = CardEditor(self, matcher, row)
        self.wait_window(dialog)
        if dialog.saved:
            self._refresh_row(row)
            self._mark_copy_tokens()

    def link_faces(self) -> None:
        """Collega a mano il fronte e il retro di una carta a due lati.

        L'abbinamento automatico legge il nome del file: quando non rispetta la
        forma attesa il retro non viene riconosciuto e finisce come carta a se'.
        Da qui si sceglie esplicitamente quale immagine e' il retro di quale
        fronte.
        """
        if not any(not r.is_token and not r.is_emblem for r in self.rows.values()):
            messagebox.showinfo(t("msg.nothing_title"), t("faces.need_rows"))
            return
        dialog = LinkFacesDialog(self, self._selected_rows())
        self.wait_window(dialog)
        for iid in dialog.changed:
            row = self.rows.get(iid)
            if row is not None:
                self._refresh_row(row)

    def _sync_back_links(self, rows: list[Row]) -> None:
        """Propaga ai retro collegati la carta base del fronte scelto a mano.

        Un retro non e' una carta a se': prende la base del fronte, cosi' in
        scrittura la coppia viene trattata come le due facce della stessa carta.
        """
        for row in rows:
            if not row.is_back or not row.linked_front:
                continue
            front = self.rows.get(row.linked_front)
            if front is not None and front.base is not None:
                row.base = front.base

    def remove_selected(self) -> None:
        removed = set(self.tree.selection())
        for iid in list(removed):
            self.rows.pop(iid, None)
            self.tree.delete(iid)
        # Rimuovendo un fronte il suo retro resta senza collegamento: si aggiorna.
        for row in self.rows.values():
            if row.is_back and row.linked_front in removed:
                row.linked_front = ""
                self._refresh_row(row)

    def clear_rows(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.rows.clear()
        self.progress.set(0)

    # ------------------------------------------------------------- importazione

    def import_all(self) -> None:
        if self.busy:
            return
        rows = list(self.rows.values())
        if not rows:
            messagebox.showinfo(t("msg.no_cards_title"), t("msg.no_cards_text"))
            return

        self._mark_copy_tokens()
        self._sync_back_links(rows)
        usable = [
            r for r in rows if r.new_name.strip() and (r.base is not None or r.is_copy)
        ]
        missing = [r for r in rows if r.base is None and not r.is_copy and not r.is_emblem]
        if missing:
            names = "\n".join(f"  - {r.image_path.name}" for r in missing[:12])
            more = (
                t("msg.and_more", count=len(missing) - 12) if len(missing) > 12 else ""
            )
            if not messagebox.askyesno(
                t("msg.no_base_title"),
                t("msg.no_base_text", count=len(missing), names=names, more=more, usable=len(usable)),
            ):
                return

        if not usable:
            messagebox.showwarning(t("msg.nothing_title"), t("msg.nothing_text"))
            return

        target = self._target_edition()
        if target is None:
            return
        edition_path, code, name = target

        phone = None
        if self.settings.uses_phone():
            problems = self.settings.phone_problems()
            if problems:
                messagebox.showwarning(
                    t("msg.phone_title"),
                    t("msg.phone_text") + "\n\n" + "\n".join(problems),
                )
                return
            phone = adb.PhoneTarget(
                self.settings.adb_path,
                self.settings.adb_serial,
                self.settings.adb_forge_root,
            )

        options = ImportOptions(
            crop=self.crop_var.get(), move_within_pics=self.move_var.get()
        )
        items = [
            ImportItem(
                image_path=r.image_path,
                base=r.base,
                new_name=r.new_name.strip(),
                rarity=r.rarity,
                artist=r.artist,
                is_token=r.is_token,
                is_copy=r.is_copy,
                copy_prefix=r.copy_prefix,
                copy_card=r.copy_card,
                is_emblem=r.is_emblem,
                is_back=r.is_back,
            )
            for r in usable
        ]

        custom_dir = self.settings.resolved_custom_dir()
        cache_dir = self.settings.resolved_cache_dir()
        self._set_busy(True)
        self.progress.set(0)
        self.status_label.configure(
            text=t("status.importing", count=len(items), code=code)
        )
        importer = Importer(
            self.db,
            custom_dir,
            self.settings.pics_dir(),
            self.settings.tokens_dir(),
            self.settings.token_pics_dir(),
        )
        threading.Thread(
            target=self._import_worker,
            args=(
                importer,
                items,
                edition_path,
                code,
                name,
                options,
                phone,
                custom_dir,
                cache_dir,
            ),
            daemon=True,
        ).start()

    def _import_worker(
        self, importer, items, edition_path, code, name, options, phone, custom_dir, cache_dir
    ) -> None:
        try:
            report = importer.run(items, edition_path, code, name, options)
            # Destinazione telefono: dopo aver scritto in locale il set viene
            # copiato nella cartella di Forge del telefono via adb.
            if phone is not None:
                self.q.put(("status_text", t("status.phone_pushing", code=code)))
                for line in phone.push_set(code, custom_dir, cache_dir):
                    report.log(line)
                report.log(t("push.done", code=code))
            self.q.put(("import_done", report, code))
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            self.q.put(("fatal", t("status.import_error", error=exc)))

    def send_to_phone(self) -> None:
        """Copia sul telefono un set gia' importato, senza rielaborarlo.

        Usa la stessa copia idempotente dell'importazione (sovrascrive i file
        con lo stesso nome e rimuove le varianti rimaste orfane): serve ad
        allineare il telefono con i set importati in precedenza.
        """
        if self.busy or not self.settings.uses_phone():
            return
        edition = self._selected_edition()
        if edition is None:
            messagebox.showinfo(t("msg.no_edition_title"), t("msg.no_edition_text"))
            return
        problems = self.settings.phone_problems()
        if problems:
            messagebox.showwarning(
                t("msg.phone_title"), t("msg.phone_text") + "\n\n" + "\n".join(problems)
            )
            return
        if not messagebox.askyesno(
            t("msg.send_title"), t("msg.send_text", code=edition.code)
        ):
            return

        phone = adb.PhoneTarget(
            self.settings.adb_path,
            self.settings.adb_serial,
            self.settings.adb_forge_root,
        )
        self._set_busy(True)
        self.status_label.configure(
            text=t("status.phone_pushing", code=edition.code), text_color=COLOR_TEXT
        )
        threading.Thread(
            target=self._send_worker,
            args=(
                phone,
                edition.code,
                self.settings.resolved_custom_dir(),
                self.settings.resolved_cache_dir(),
            ),
            daemon=True,
        ).start()

    def _send_worker(self, phone, code, custom_dir, cache_dir) -> None:
        try:
            self.q.put(("send_done", code, phone.push_set(code, custom_dir, cache_dir)))
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            self.q.put(("fatal", t("status.import_error", error=exc)))

    # ------------------------------------------------------------------- coda

    def _poll_queue(self) -> None:
        try:
            while True:
                message = self.q.get_nowait()
                self._handle_message(message)
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _handle_message(self, message: tuple) -> None:
        kind = message[0]
        if kind == "db_ready":
            self.db = message[1]
            self.matcher = Matcher(self.db)
            self.rarities = message[2]
            token_db = message[3]
            self.token_matcher = TokenMatcher(token_db) if token_db is not None else None
            self._token_count = len(token_db.cards) if token_db is not None else 0
            self._show_ready()
        elif kind == "row":
            _, path, reading, candidates = message
            self._add_row(path, reading, candidates)
        elif kind == "row_error":
            _, path, error = message
            self._add_row(path, None, [])
            self.status_label.configure(
                text=t("status.analyze_error", name=path.name, error=error), text_color=COLOR_BAD
            )
        elif kind == "progress":
            _, done, total = message
            self.progress.set(done / total if total else 0)
            self.status_label.configure(
                text=t("status.analyzing_progress", done=done, total=total), text_color=COLOR_TEXT
            )
        elif kind == "analyze_done":
            self._set_busy(False)
            self._mark_copy_tokens()
            # "Ready" deve rispecchiare il colore/stato reale della riga:
            # prima contava anche i casi "check", creando confusione proprio
            # con token omonimi come quelli di EVA.
            ready = sum(1 for r in self.rows.values() if r.status()[1] == "ok")
            self.status_label.configure(
                text=t("status.analyze_done", count=len(self.rows), ready=ready),
                text_color=COLOR_OK,
            )
        elif kind == "import_done":
            _, report, code = message
            self._set_busy(False)
            if report.emblems:
                status = t(
                    "status.import_done_emblems",
                    imported=report.imported,
                    tokens=report.tokens,
                    emblems=report.emblems,
                    code=code,
                )
            else:
                status = t(
                    "status.import_done",
                    imported=report.imported,
                    tokens=report.tokens,
                    code=code,
                )
            self.status_label.configure(text=status, text_color=COLOR_OK)
            self._refresh_editions()
            self.clear_rows()
            ReportDialog(
                self,
                report,
                code,
                self.settings.pics_dir() / code,
                self.settings.token_pics_dir() / code,
            )
        elif kind == "status_text":
            self.status_label.configure(text=message[1], text_color=COLOR_TEXT)
        elif kind == "phone_ready":
            _, device, root = message
            self.settings.adb_serial = device.serial
            self.settings.adb_forge_root = root
            P.save_settings(self.settings)
            if self.target_menu.get() != t("target.phone"):
                self.target_menu.set(t("target.phone"))
            self.status_label.configure(
                text=t("settings.adb_ok", device=device.label, root=root),
                text_color=COLOR_OK,
            )
        elif kind == "phone_error":
            self.status_label.configure(text=message[1], text_color=COLOR_WARN)
        elif kind == "send_done":
            _, code, log = message
            self._set_busy(False)
            self.status_label.configure(
                text=t("push.done", code=code), text_color=COLOR_OK
            )
            messagebox.showinfo(
                t("msg.sent_title"), "\n".join(log) or t("push.done", code=code)
            )
        elif kind == "fatal":
            self._set_busy(False)
            messagebox.showerror(t("common.error"), message[1])
            self.status_label.configure(text=message[1], text_color=COLOR_BAD)

    def _set_busy(self, value: bool) -> None:
        self.busy = value
        self._refresh_buttons()


# --------------------------------------------------------------------- dialoghi


class CardEditor(ctk.CTkToplevel):
    """Modifica i dati di una riga e la carta base associata."""

    def __init__(
        self, master: ForgeImporterApp, matcher: Matcher | TokenMatcher, row: Row
    ) -> None:
        super().__init__(master)
        self.title(t("editor.title", name=row.image_path.name))
        self.geometry("720x620")
        self.matcher = matcher
        self.row = row
        self.saved = False
        self.selected_base: CardInfo | None = row.base

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        info = ctk.CTkLabel(
            self,
            text=t(
                "editor.info",
                name=row.image_path.name,
                title=getattr(row.reading, "title", "") or "\u2014",
                hint=getattr(row.reading, "base_hint", "") or "\u2014",
            ),
            justify="left",
            anchor="w",
        )
        info.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=1, column=0, sticky="ew", padx=16)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text=t("editor.new_name")).grid(row=0, column=0, sticky="w", pady=6)
        self.name_entry = ctk.CTkEntry(form)
        self.name_entry.insert(0, row.new_name)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=6)

        self.rarity_menu: ctk.CTkOptionMenu | None = None
        if not row.is_token:
            ctk.CTkLabel(form, text=t("editor.rarity")).grid(row=1, column=0, sticky="w", pady=6)
            self.rarity_menu = ctk.CTkOptionMenu(form, values=list(RARITIES), width=90)
            self.rarity_menu.set(row.rarity if row.rarity in RARITIES else DEFAULT_RARITY)
            self.rarity_menu.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=6)

        ctk.CTkLabel(form, text=t("editor.artist")).grid(row=2, column=0, sticky="w", pady=6)
        self.artist_entry = ctk.CTkEntry(form)
        self.artist_entry.insert(0, row.artist)
        self.artist_entry.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=6)

        self.same_name_var = tk.BooleanVar(value=False)
        if not row.is_token and not row.is_emblem:
            ctk.CTkCheckBox(
                form,
                text=t("editor.same_name"),
                variable=self.same_name_var,
                command=self._apply_same_name,
            ).grid(row=3, column=1, sticky="w", padx=(10, 0), pady=6)

        self.emblem_var = tk.BooleanVar(value=row.is_emblem)
        if not row.is_token:
            ctk.CTkCheckBox(
                form,
                text=t("editor.emblem"),
                variable=self.emblem_var,
                command=self._apply_emblem,
            ).grid(row=4, column=1, sticky="w", padx=(10, 0), pady=6)

        base_frame = ctk.CTkFrame(self)
        base_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=10)
        base_frame.grid_columnconfigure(0, weight=1)
        base_frame.grid_rowconfigure(2, weight=1)

        self.base_title_label = ctk.CTkLabel(base_frame, text=self._base_title(), anchor="w")
        self.base_title_label.grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 4)
        )

        placeholder = (
            t("editor.search_token") if row.is_token else t("editor.search_card")
        )
        self.search_entry = ctk.CTkEntry(base_frame, placeholder_text=placeholder)
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=(10, 0), pady=4)
        self.search_entry.bind("<KeyRelease>", self._on_search)
        ctk.CTkButton(base_frame, text=t("editor.search"), width=80, command=self._on_search).grid(
            row=1, column=1, padx=10, pady=4
        )

        list_frame = ctk.CTkFrame(base_frame, fg_color="transparent")
        list_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 6))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        self.results = tk.Listbox(
            list_frame, height=8, bg="#2b2b2b", fg="#e6e6e6",
            selectbackground="#1f6feb", borderwidth=0, highlightthickness=0,
        )
        self.results.grid(row=0, column=0, sticky="nsew")
        self.results.bind("<<ListboxSelect>>", self._on_pick)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.results.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.results.configure(yscrollcommand=sb.set)
        self._search_results: list[CardInfo] = []

        self.base_label = ctk.CTkLabel(base_frame, text=self._base_text(), anchor="w")
        self.base_label.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 14))
        buttons.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(buttons, text=t("common.cancel"), command=self.destroy, fg_color="#555").grid(
            row=0, column=0, sticky="e", padx=(0, 8)
        )
        ctk.CTkButton(buttons, text=t("common.save"), command=self._save).grid(row=0, column=1, sticky="e")

        self._populate_candidates()
        self.transient(master)
        self.grab_set()

    def _populate_candidates(self) -> None:
        for cand in self.row.candidates:
            if self.selected_base and cand.card.entry == self.selected_base.entry:
                self.base_label.configure(
                    text=t(
                        "editor.base_current_full",
                        name=cand.card.name,
                        score=f"{cand.score:.0f}",
                        reason=t(cand.reason),
                    )
                )
        self._show_cards([cand.card for cand in self.row.candidates])

    def _show_cards(self, cards: list[CardInfo]) -> None:
        """Riempe la lista dei candidati.

        Se piu' carte hanno lo stesso nome l'etichetta porta anche P/T, tipo e
        file: in Forge tre script si chiamano "Citizen Token" (2/2 e 1/1) e dal
        solo nome non si capisce quale base si sta scegliendo.
        """
        self._search_results = list(cards)
        duplicates = Counter(card.name for card in cards)
        self.results.delete(0, "end")
        for card in cards:
            label = (
                self._card_label(card) if duplicates[card.name] > 1 else card.name
            )
            self.results.insert("end", label)

    @staticmethod
    def _card_label(card: CardInfo) -> str:
        """Nome con i dettagli che distinguono le carte omonime."""
        info = ", ".join(
            part
            for part in (card.pt.strip(), card.types.strip(), Path(card.entry).name)
            if part
        )
        if not info:
            return card.name
        return t("editor.candidate_label", name=card.name, info=info)

    def _base_text(self) -> str:
        if self.selected_base is None:
            return t("editor.base_current_none")
        return t("editor.base_current", name=self.selected_base.name)

    def _base_title(self) -> str:
        """Titolo della sezione di scelta della base, secondo il tipo di riga."""
        if self.emblem_var.get():
            return t("editor.emblem_title")
        if self.row.is_copy:
            return t("editor.copy_title")
        if self.row.is_token:
            return t("editor.token_base_title")
        return t("editor.card_base_title")

    def _apply_emblem(self) -> None:
        self.base_title_label.configure(text=self._base_title())

    def _on_search(self, _event=None) -> None:
        query = self.search_entry.get().strip()
        if not query:
            return
        self._show_cards(self.matcher.search_candidates(query, 30))

    def _on_pick(self, _event=None) -> None:
        selection = self.results.curselection()
        if not selection:
            return
        card = self._search_results[selection[0]]
        self.selected_base = card
        duplicated = sum(1 for c in self._search_results if c.name == card.name) > 1
        shown = self._card_label(card) if duplicated else card.name
        self.base_label.configure(text=t("editor.base_current", name=shown))
        if self.rarity_menu is not None:
            self.rarity_menu.set(self.master._deduced_rarity(card))
        if self.same_name_var.get():
            self._set_name(card.name)

    def _apply_same_name(self) -> None:
        if self.same_name_var.get() and self.selected_base is not None:
            self._set_name(self.selected_base.name)

    def _set_name(self, value: str) -> None:
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, value)

    def _save(self) -> None:
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning(t("editor.missing_name_title"), t("editor.missing_name_text"))
            return
        self.row.is_emblem = self.emblem_var.get()
        if self.selected_base is None and not self.row.is_copy and not self.row.is_emblem:
            messagebox.showwarning(t("editor.missing_base_title"), t("editor.missing_base_text"))
            return
        self.row.new_name = name
        if self.rarity_menu is not None:
            self.row.rarity = self.rarity_menu.get()
        self.row.artist = self.artist_entry.get().strip()
        self.row.base = self.selected_base
        if self.selected_base is not None and self.selected_base.name.lower() == name.lower():
            self.row.score = 100.0
            self.row.reason = "reason.same_name"
        self.saved = True
        self.destroy()


class LinkFacesDialog(ctk.CTkToplevel):
    """Collega a mano fronte e retro di una carta a due lati.

    L'abbinamento automatico si basa sul nome del file: quando il nome non
    rispetta la forma attesa ("<NomeReale> (<NomeCustom>) <n>.ext") il retro non
    viene riconosciuto e finisce come carta a se' stante (o viene scartato).
    Qui l'utente sceglie esplicitamente quale immagine e' il retro di quale
    fronte, con l'anteprima delle due immagini per riconoscerle a vista.
    """

    PREVIEW = (240, 330)

    def __init__(self, master: ForgeImporterApp, selected: list[Row]) -> None:
        super().__init__(master)
        self.title(t("faces.title"))
        self.geometry("840x660")
        self.changed: set[str] = set()
        # Riferimenti alle anteprime correnti: senza di essi Tk le scarterebbe.
        self._images: list = []

        rows = [r for r in master.rows.values() if not r.is_token and not r.is_emblem]
        self._by_iid = {r.iid: r for r in rows}
        self.front_map = self._labels([r for r in rows if not r.is_back])
        self.back_map = self._labels(rows)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self, text=t("faces.hint"), anchor="w", justify="left", wraplength=790
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))

        selectors = ctk.CTkFrame(self, fg_color="transparent")
        selectors.grid(row=1, column=0, sticky="ew", padx=16)
        selectors.grid_columnconfigure(1, weight=1)
        selectors.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(selectors, text=t("faces.front")).grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=6
        )
        self.front_menu = ctk.CTkOptionMenu(
            selectors,
            values=list(self.front_map) or [t("common.none")],
            width=290,
            command=lambda _v: self._update(),
        )
        self.front_menu.grid(row=0, column=1, sticky="w", pady=6)
        ctk.CTkLabel(selectors, text=t("faces.back")).grid(
            row=0, column=2, sticky="w", padx=(16, 8), pady=6
        )
        self.back_menu = ctk.CTkOptionMenu(
            selectors,
            values=list(self.back_map) or [t("common.none")],
            width=290,
            command=lambda _v: self._update(),
        )
        self.back_menu.grid(row=0, column=3, sticky="w", pady=6)

        previews = ctk.CTkFrame(self, fg_color="transparent")
        previews.grid(row=2, column=0, sticky="nsew", padx=16, pady=8)
        previews.grid_columnconfigure(0, weight=1)
        previews.grid_columnconfigure(1, weight=1)
        self.front_preview = ctk.CTkLabel(previews, text="\u2014", height=340)
        self.front_preview.grid(row=0, column=0, padx=10, pady=6)
        self.back_preview = ctk.CTkLabel(previews, text="\u2014", height=340)
        self.back_preview.grid(row=0, column=1, padx=10, pady=6)

        self.status_label = ctk.CTkLabel(self, text="", anchor="w")
        self.status_label.grid(row=3, column=0, sticky="ew", padx=16)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=4, column=0, sticky="ew", padx=16, pady=(6, 14))
        buttons.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            buttons, text=t("faces.unlink"), fg_color="#555", command=self._unlink
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(buttons, text=t("faces.link"), command=self._link).grid(
            row=0, column=1, padx=8
        )
        ctk.CTkButton(
            buttons, text=t("common.close"), fg_color="#555", command=self.destroy
        ).grid(row=0, column=2)

        self._preselect(selected)
        self._update()
        self.transient(master)
        self.grab_set()

    @staticmethod
    def _labels(rows: list[Row]) -> dict[str, str]:
        """Etichetta del menu -> iid della riga (il nome file e' unico)."""
        out: dict[str, str] = {}
        for row in rows:
            name = row.new_name.strip()
            label = f"{row.image_path.name}  \u2192  {name}" if name else row.image_path.name
            if label in out:
                label = f"{label}  [{row.iid}]"
            out[label] = row.iid
        return out

    def _preselect(self, selected: list[Row]) -> None:
        """Parte dalla riga selezionata in tabella, se ne e' stata scelta una."""
        if not selected:
            return
        row = selected[0]
        self._select(self.back_menu, self.back_map, row.iid)
        if row.is_back and row.linked_front:
            self._select(self.front_menu, self.front_map, row.linked_front)

    @staticmethod
    def _select(menu: ctk.CTkOptionMenu, mapping: dict[str, str], iid: str) -> None:
        for label, value in mapping.items():
            if value == iid:
                menu.set(label)
                return

    def _row_of(self, menu: ctk.CTkOptionMenu, mapping: dict[str, str]) -> Row | None:
        iid = mapping.get(menu.get())
        return self._by_iid.get(iid) if iid else None

    def _update(self) -> None:
        front = self._row_of(self.front_menu, self.front_map)
        back = self._row_of(self.back_menu, self.back_map)
        self._images = []
        self._show(self.front_preview, front)
        self._show(self.back_preview, back)
        if back is not None and back.is_back and back.linked_front:
            linked = self._by_iid.get(back.linked_front)
            name = (linked.new_name or linked.image_path.name) if linked else "\u2014"
            self.status_label.configure(text=t("faces.status_linked", name=name))
        else:
            self.status_label.configure(text=t("faces.status_free"))

    def _show(self, label: ctk.CTkLabel, row: Row | None) -> None:
        photo = self._thumbnail(row.image_path) if row is not None else None
        if photo is None:
            label.configure(image=None, text=row.image_path.name if row else "\u2014")
            return
        self._images.append(photo)
        label.configure(image=photo, text="")

    def _thumbnail(self, path: Path):
        """Miniatura dell'immagine (None se non e' leggibile)."""
        try:
            from PIL import Image, ImageTk

            image = Image.open(path)
            image.thumbnail(self.PREVIEW)
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _link(self) -> None:
        front = self._row_of(self.front_menu, self.front_map)
        back = self._row_of(self.back_menu, self.back_map)
        if front is None or back is None or front is back:
            messagebox.showwarning(t("faces.bad_title"), t("faces.bad_text"), parent=self)
            return
        if front.is_back:
            messagebox.showwarning(t("faces.bad_title"), t("faces.front_is_back"), parent=self)
            return
        if front.base is None:
            messagebox.showwarning(
                t("faces.bad_title"), t("faces.front_no_base"), parent=self
            )
            return
        if not faces_of(front.base):
            messagebox.showwarning(
                t("faces.bad_title"), t("faces.front_single_face"), parent=self
            )
            return
        # Il retro prende la base del fronte: in scrittura la coppia viene
        # trattata come le due facce della stessa carta.
        back.is_back = True
        back.linked_front = front.iid
        back.base = front.base
        if not back.new_name.strip():
            back.new_name = name_from_filename(back.image_path)
        self.changed.update({front.iid, back.iid})
        self._update()

    def _unlink(self) -> None:
        back = self._row_of(self.back_menu, self.back_map)
        if back is None or not back.is_back:
            return
        back.is_back = False
        back.linked_front = ""
        self.changed.add(back.iid)
        self._update()


class SettingsDialog(ctk.CTkToplevel):
    """Percorsi di Forge (rilevati automaticamente, con override manuale)."""

    def __init__(self, master: ForgeImporterApp, settings: P.Settings, on_save) -> None:
        super().__init__(master)
        self.title(t("settings.title"))
        self.geometry("780x620")
        self.settings = settings
        self.on_save = on_save
        self.devices: list[adb.Device] = []

        self.grid_columnconfigure(0, weight=1)

        body = ctk.CTkFrame(self)
        body.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        body.grid_columnconfigure(1, weight=1)

        self.entries: dict[str, ctk.CTkEntry] = {}
        fields = (
            ("forge_root", t("settings.forge_root")),
            ("custom_dir", t("settings.custom_dir")),
            ("cache_dir", t("settings.cache_dir")),
        )
        for index, (key, label) in enumerate(fields):
            ctk.CTkLabel(body, text=label).grid(row=index, column=0, sticky="w", padx=10, pady=10)
            entry = ctk.CTkEntry(body)
            entry.insert(0, getattr(settings, key))
            entry.grid(row=index, column=1, sticky="ew", padx=(10, 6), pady=10)
            ctk.CTkButton(
                body, text=t("common.browse"), width=80,
                command=lambda k=key: self._browse(k),
            ).grid(row=index, column=2, padx=(0, 10), pady=10)
            self.entries[key] = entry

        ctk.CTkLabel(
            body,
            text=t("settings.hint"),
            text_color="#999999",
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 10))

        self._build_phone_section(body, start_row=4)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        buttons.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(buttons, text=t("settings.autodetect"), command=self._autodetect).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkButton(buttons, text=t("common.cancel"), command=self.destroy, fg_color="#555").grid(
            row=0, column=1, sticky="e", padx=(0, 8)
        )
        ctk.CTkButton(buttons, text=t("common.save"), command=self._save).grid(row=0, column=2, sticky="e")

        self.transient(master)
        self.grab_set()

    # ------------------------------------------------------------- telefono

    def _build_phone_section(self, body: ctk.CTkFrame, start_row: int) -> None:
        """Campi per raggiungere Forge sul telefono tramite adb."""
        ctk.CTkLabel(
            body,
            text=t("settings.phone_section"),
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=start_row, column=0, columnspan=3, sticky="w", padx=10, pady=(14, 4))

        # adb.exe: se non e' indicato si prova a individuarlo da soli, cosi'
        # l'utente non deve cercarlo a mano.
        executable = self.settings.adb_path or (adb.find_adb() or "")
        ctk.CTkLabel(body, text=t("settings.adb_path")).grid(
            row=start_row + 1, column=0, sticky="w", padx=10, pady=10
        )
        self.entries["adb_path"] = ctk.CTkEntry(body)
        self.entries["adb_path"].insert(0, executable)
        self.entries["adb_path"].grid(
            row=start_row + 1, column=1, sticky="ew", padx=(10, 6), pady=10
        )
        ctk.CTkButton(
            body, text=t("common.browse"), width=80, command=self._browse_adb
        ).grid(row=start_row + 1, column=2, padx=(0, 10), pady=10)

        ctk.CTkLabel(body, text=t("settings.adb_device")).grid(
            row=start_row + 2, column=0, sticky="w", padx=10, pady=10
        )
        initial = self.settings.adb_serial or t("settings.adb_none")
        self.device_menu = ctk.CTkOptionMenu(body, values=[initial], width=320)
        self.device_menu.set(initial)
        self.device_menu.grid(row=start_row + 2, column=1, sticky="w", padx=(10, 6), pady=10)
        ctk.CTkButton(
            body, text=t("settings.adb_devices"), width=120, command=self._find_devices
        ).grid(row=start_row + 2, column=2, padx=(0, 10), pady=10)

        ctk.CTkLabel(body, text=t("settings.adb_forge_root")).grid(
            row=start_row + 3, column=0, sticky="w", padx=10, pady=10
        )
        self.entries["adb_forge_root"] = ctk.CTkEntry(body)
        self.entries["adb_forge_root"].insert(0, self.settings.adb_forge_root)
        self.entries["adb_forge_root"].grid(
            row=start_row + 3, column=1, sticky="ew", padx=(10, 6), pady=10
        )
        ctk.CTkButton(
            body, text=t("settings.adb_detect"), width=80, command=self._detect_forge
        ).grid(row=start_row + 3, column=2, padx=(0, 10), pady=10)

        ctk.CTkLabel(
            body, text=t("settings.adb_hint"), text_color="#999999", wraplength=680, justify="left"
        ).grid(row=start_row + 4, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 6))

        self.adb_status = ctk.CTkLabel(body, text="", anchor="w", wraplength=680, justify="left")
        self.adb_status.grid(row=start_row + 5, column=0, columnspan=3, sticky="ew", padx=10)

    def _browse_adb(self) -> None:
        path = filedialog.askopenfilename(
            title=t("dialog.adb_title"),
            filetypes=[(t("dialog.filter_exe"), "*.exe"), (t("dialog.filter_all"), "*.*")],
        )
        if path:
            self.entries["adb_path"].delete(0, "end")
            self.entries["adb_path"].insert(0, path)

    def _find_devices(self) -> None:
        """Elenca i telefoni collegati (in background: adb puo' essere lento)."""
        executable = adb.find_adb(self.entries["adb_path"].get().strip())
        if not executable:
            self.adb_status.configure(text=t("settings.adb_missing"), text_color=COLOR_WARN)
            return
        self.entries["adb_path"].delete(0, "end")
        self.entries["adb_path"].insert(0, executable)
        self.adb_status.configure(text=t("status.starting"), text_color=COLOR_TEXT)
        threading.Thread(
            target=self._device_worker, args=(executable,), daemon=True
        ).start()

    def _device_worker(self, executable: str) -> None:
        try:
            devices = [d for d in adb.Adb(executable).devices() if d.ready]
            error = ""
        except adb.AdbError as exc:
            devices, error = [], str(exc)
        self.after(0, lambda: self._show_devices(devices, error))

    def _show_devices(self, devices: list[adb.Device], error: str) -> None:
        self.devices = devices
        labels = [d.label for d in devices] or [t("settings.adb_none")]
        self.device_menu.configure(values=labels)
        self.device_menu.set(labels[0])
        if error:
            self.adb_status.configure(text=error, text_color=COLOR_WARN)
        elif devices:
            self.adb_status.configure(
                text=t("adb.devices_found", count=len(devices)), text_color=COLOR_OK
            )
        else:
            self.adb_status.configure(text=t("adb.no_devices"), text_color=COLOR_WARN)

    def _detect_forge(self) -> None:
        executable = self.entries["adb_path"].get().strip()
        device = self._selected_device()
        if not executable or device is None:
            self.adb_status.configure(text=t("adb.no_device"), text_color=COLOR_WARN)
            return
        self.adb_status.configure(text=t("status.starting"), text_color=COLOR_TEXT)
        threading.Thread(
            target=self._forge_worker, args=(executable, device.serial), daemon=True
        ).start()

    def _forge_worker(self, executable: str, serial: str) -> None:
        try:
            root = adb.detect_forge_root(adb.Adb(executable, serial))
            error = ""
        except adb.AdbError as exc:
            root, error = None, str(exc)
        self.after(0, lambda: self._show_forge(root, error))

    def _show_forge(self, root: str | None, error: str) -> None:
        if root:
            self.entries["adb_forge_root"].delete(0, "end")
            self.entries["adb_forge_root"].insert(0, root)
            self.adb_status.configure(text=t("adb.detected", root=root), text_color=COLOR_OK)
        else:
            self.adb_status.configure(
                text=error or t("adb.not_detected"), text_color=COLOR_WARN
            )

    def _selected_device(self) -> adb.Device | None:
        label = self.device_menu.get()
        for device in self.devices:
            if device.label == label:
                return device
        return None

    def _browse(self, key: str) -> None:
        folder = filedialog.askdirectory(title=t("dialog.pick_folder"))
        if folder:
            self.entries[key].delete(0, "end")
            self.entries[key].insert(0, folder)

    def _autodetect(self) -> None:
        root = P.find_forge_root()
        if root:
            self.entries["forge_root"].delete(0, "end")
            self.entries["forge_root"].insert(0, str(root))
        if P.DEFAULT_CUSTOM_DIR.is_dir():
            self.entries["custom_dir"].delete(0, "end")
            self.entries["custom_dir"].insert(0, str(P.DEFAULT_CUSTOM_DIR))
        if P.DEFAULT_CACHE_DIR.is_dir():
            self.entries["cache_dir"].delete(0, "end")
            self.entries["cache_dir"].insert(0, str(P.DEFAULT_CACHE_DIR))

    def _save(self) -> None:
        for key, entry in self.entries.items():
            setattr(self.settings, key, entry.get().strip())
        device = self._selected_device()
        if device is not None:
            self.settings.adb_serial = device.serial
        self.on_save()
        self.destroy()


class NewEditionDialog(ctk.CTkToplevel):
    """Chiede codice e nome di una nuova edizione custom."""

    def __init__(self, master: ForgeImporterApp) -> None:
        super().__init__(master)
        self.title(t("edition.title"))
        self.geometry("420x220")
        self.result: tuple[str, str] | None = None

        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=t("edition.code")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(20, 8)
        )
        self.code_entry = ctk.CTkEntry(self)
        self.code_entry.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=(20, 8))

        ctk.CTkLabel(self, text=t("edition.name")).grid(row=1, column=0, sticky="w", padx=16, pady=8)
        self.name_entry = ctk.CTkEntry(self)
        self.name_entry.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=8)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=16)
        buttons.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(buttons, text=t("common.cancel"), command=self.destroy, fg_color="#555").grid(
            row=0, column=0, sticky="e", padx=(0, 8)
        )
        ctk.CTkButton(buttons, text=t("edition.create"), command=self._save).grid(row=0, column=1, sticky="e")

        self.transient(master)
        self.grab_set()

    def _save(self) -> None:
        code = self.code_entry.get().strip().upper()
        name = self.name_entry.get().strip()
        if not code or not name:
            messagebox.showwarning(t("edition.missing_title"), t("edition.missing_text"))
            return
        self.result = (code, name)
        self.destroy()


class ReportDialog(ctk.CTkToplevel):
    """Riepilogo dell'importazione, scorrevole e ridimensionabile."""

    def __init__(
        self,
        master: ForgeImporterApp,
        report,
        code: str,
        pics_dir: Path,
        token_pics_dir: Path | None = None,
    ) -> None:
        super().__init__(master)
        self.title(t("report.title", code=code))
        self.geometry("820x560")
        self.minsize(640, 400)
        self.pics_dir = pics_dir
        self.token_pics_dir = token_pics_dir

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkLabel(
            self,
            text=t(
                "report.header_emblems" if report.emblems else "report.header",
                code=code,
                imported=report.imported,
                tokens=report.tokens,
                emblems=report.emblems,
                scripts=report.scripts_written,
                images=report.images_written,
                skipped=report.skipped,
            ),
            justify="left",
            anchor="w",
        )
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        self.text = ctk.CTkTextbox(self, wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        self.text.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
        self.text.insert(
            "end", "\n".join(report.messages) if report.messages else t("report.no_warnings")
        )
        self.text.configure(state="disabled")

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 14))
        buttons.grid_columnconfigure(2, weight=1)
        ctk.CTkButton(buttons, text=t("report.open_pics"), command=self._open_pics).grid(
            row=0, column=0, sticky="w"
        )
        if self.token_pics_dir is not None:
            ctk.CTkButton(
                buttons, text=t("report.open_tokens"), command=self._open_tokens
            ).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ctk.CTkButton(buttons, text=t("report.close"), command=self.destroy).grid(row=0, column=3, sticky="e")

        self.transient(master)

    def _open_pics(self) -> None:
        self._open(self.pics_dir)

    def _open_tokens(self) -> None:
        self._open(self.token_pics_dir)

    @staticmethod
    def _open(target: Path | None) -> None:
        if target is not None and target.is_dir():
            os.startfile(target)  # noqa: S606 - apertura esplora risorse


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = ForgeImporterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
