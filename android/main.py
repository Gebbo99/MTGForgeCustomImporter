"""App Android per importare carte custom (re-skin) in MTG Forge.

E' la versione mobile del tool: stessa logica del desktop (OCR, riconoscimento
della carta base, scrittura del set custom), interfaccia pensata per il
telefono. Il core condiviso sta in `forge_importer/` (copia di
`desktop/forge_importer`, sincronizzata durante la build).

Flusso:
  1. si scelgono le immagini delle carte dalla memoria del telefono;
  2. ogni immagine viene letta con l'OCR on-device di ML Kit e confrontata con
     gli script di Forge per trovare la carta base;
  3. le proposte si possono correggere toccandole;
  4. l'importazione scrive immagine, script ed edizione custom nei percorsi di
     Forge, senza modificare l'app di Forge.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Su Android non esiste %LOCALAPPDATA%: impostazioni e indice delle carte
# vanno nella cartella privata dell'app (va fatto prima di importare paths).
os.environ.setdefault(
    "FORGE_IMPORTER_DATA", os.environ.get("ANDROID_PRIVATE") or str(Path.home())
)

from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.metrics import dp  # noqa: E402
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.checkbox import CheckBox  # noqa: E402
from kivy.uix.filechooser import FileChooserListView  # noqa: E402
from kivy.uix.gridlayout import GridLayout  # noqa: E402
from kivy.uix.image import AsyncImage  # noqa: E402
from kivy.uix.label import Label  # noqa: E402
from kivy.uix.popup import Popup  # noqa: E402
from kivy.uix.progressbar import ProgressBar  # noqa: E402
from kivy.uix.scrollview import ScrollView  # noqa: E402
from kivy.uix.spinner import Spinner  # noqa: E402
from kivy.uix.textinput import TextInput  # noqa: E402

from kivymd.app import MDApp  # noqa: E402
from kivymd.uix.button import MDFlatButton, MDRaisedButton  # noqa: E402
from kivymd.uix.card import MDCard  # noqa: E402
from kivymd.uix.label import MDLabel  # noqa: E402
from kivymd.uix.progressbar import MDProgressBar  # noqa: E402
from kivymd.uix.textfield import MDTextField  # noqa: E402
from kivymd.uix.toolbar import MDTopAppBar  # noqa: E402

import android_env  # noqa: E402
import mlkit_ocr  # noqa: E402
from forge_importer import i18n  # noqa: E402
from forge_importer import ocr  # noqa: E402
from forge_importer import paths as P  # noqa: E402
from forge_importer.carddb import CardDB, CardInfo  # noqa: E402
from forge_importer.cards import (  # noqa: E402
    DEFAULT_RARITY,
    detect_basic_land,
    is_basic_land,
    name_from_filename,
    token_name,
)
from forge_importer.generator import (  # noqa: E402
    RARITIES,
    Edition,
    ImportItem,
    ImportOptions,
    Importer,
    copy_mechanic,
    copy_mechanics_in,
    scan_images,
)
from forge_importer.i18n import (  # noqa: E402
    code_for_label,
    label_for_code,
    language_labels,
    t,
)
from forge_importer.matcher import Candidate, Matcher, TokenMatcher  # noqa: E402
from forge_importer.ocr import OcrUnavailable, is_token, read_image  # noqa: E402
from forge_importer.rarity import RarityIndex  # noqa: E402
from forge_importer.textutil import has_letters  # noqa: E402

COLOR_TEXT = (0.90, 0.90, 0.90, 1)
COLOR_DIM = (0.62, 0.62, 0.62, 1)
COLOR_OK = (0.25, 0.72, 0.31, 1)
COLOR_WARN = (0.82, 0.60, 0.13, 1)
COLOR_BAD = (0.97, 0.32, 0.29, 1)
COLOR_BOX = (0.16, 0.16, 0.18, 1)
STATUS_COLORS = {"ok": COLOR_OK, "warn": COLOR_WARN, "bad": COLOR_BAD}

IMAGE_FILTERS = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.tif", "*.tiff"]


@dataclass
class Row:
    """Una immagine con la sua proposta di importazione."""

    key: str
    image_path: Path
    reading: object | None = None
    candidates: list[Candidate] = field(default_factory=list)
    base: CardInfo | None = None
    score: float = 0.0
    reason: str = ""
    new_name: str = ""
    rarity: str = DEFAULT_RARITY
    artist: str = ""
    is_token: bool = False
    is_copy: bool = False
    copy_card: str = ""
    copy_prefix: str = ""

    def status(self) -> tuple[str, str]:
        """(chiave di traduzione dello stato, tag colore) per evidenziare le anomalie."""
        if self.reading is None:
            return "state.read_error", "bad"
        if self.is_copy:
            return "state.copy_token", "ok"
        if self.base is None:
            return "state.choose_base", "bad"
        if self.score >= 90:
            return "state.ready", "ok"
        return "state.check", "warn"

    def base_text(self) -> str:
        if self.is_copy:
            return t("value.copy_of", name=self.copy_card)
        if self.base is not None:
            return self.base.name
        return t("common.none")

    def reason_text(self) -> str:
        if not self.reason:
            return "\u2014"
        if self.reason == "reason.copy":
            return t("reason.copy", prefix=self.copy_prefix)
        return t(self.reason)


# --------------------------------------------------------------------------
# Componenti
# --------------------------------------------------------------------------


class ItemCard(MDCard):
    """Riga della lista: immagine, nomi e stato del riconoscimento."""

    def __init__(self, app: "ImporterAppUI", row: Row, **kwargs) -> None:
        super().__init__(**kwargs)
        self.app = app
        self.row = row
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(96)
        self.padding = dp(8)
        self.spacing = dp(8)
        self.md_bg_color = COLOR_BOX
        self.ripple_behavior = True

        self.thumb = AsyncImage(
            source=str(row.image_path),
            size_hint=(None, None),
            size=(dp(56), dp(78)),
            allow_stretch=True,
            keep_ratio=True,
        )
        self.add_widget(self.thumb)

        self.texts = BoxLayout(orientation="vertical")
        self.name_label = MDLabel(
            text=row.new_name or row.image_path.name,
            bold=True,
            theme_text_color="Custom",
            text_color=COLOR_TEXT,
            size_hint_y=None,
            height=dp(24),
        )
        self.base_label = MDLabel(
            theme_text_color="Custom",
            text_color=COLOR_DIM,
            size_hint_y=None,
            height=dp(22),
        )
        self.status_label = MDLabel(
            theme_text_color="Custom", size_hint_y=None, height=dp(22)
        )
        self.texts.add_widget(self.name_label)
        self.texts.add_widget(self.base_label)
        self.texts.add_widget(self.status_label)
        self.add_widget(self.texts)

        self.bind(on_release=lambda _w: app.edit_row(row))
        self.refresh()

    def refresh(self) -> None:
        row = self.row
        self.name_label.text = row.new_name or row.image_path.name
        self.base_label.text = f"{row.base_text()}  |  {row.reason_text()}"
        status_key, tag = row.status()
        confidence = f"{row.score:.0f}  " if row.base else ""
        self.status_label.text = f"{confidence}{t(status_key)}"
        self.status_label.text_color = STATUS_COLORS[tag]


class SearchablePopup(Popup):
    """Popup con una lista scorrevole di widget."""

    def __init__(self, title: str, **kwargs) -> None:
        kwargs.setdefault("title", title)
        kwargs.setdefault("size_hint", (0.95, 0.95))
        kwargs.setdefault("separator_color", COLOR_BOX)
        super().__init__(**kwargs)
        self.box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        self.add_widget(self.box)

    def list_container(self) -> tuple[ScrollView, GridLayout]:
        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None, padding=dp(4))
        grid.bind(minimum_height=grid.setter("height"))
        scroll.add_widget(grid)
        return scroll, grid


class CardEditorPopup(SearchablePopup):
    """Corregge nome, rarita', artista e carta base di una riga."""

    def __init__(self, app: "ImporterAppUI", row: Row, **kwargs) -> None:
        super().__init__(t("editor.title", name=row.image_path.name), **kwargs)
        self.app = app
        self.row = row
        self.matcher = app.token_matcher if row.is_token else app.matcher
        self.selected_base: CardInfo | None = row.base

        info = MDLabel(
            text=t(
                "editor.info",
                name=row.image_path.name,
                title=getattr(row.reading, "title", "") or "\u2014",
                hint=getattr(row.reading, "base_hint", "") or "\u2014",
            ),
            theme_text_color="Custom",
            text_color=COLOR_DIM,
            size_hint_y=None,
            height=dp(56),
        )
        self.box.add_widget(info)

        self.name_field = MDTextField(text=row.new_name, hint_text=t("editor.new_name"))
        self.box.add_widget(self.name_field)

        self.rarity_row: BoxLayout | None = None
        self.rarity_spinner: Spinner | None = None
        if not row.is_token:
            row_box = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
            row_box.add_widget(
                MDLabel(
                    text=t("editor.rarity"),
                    theme_text_color="Custom",
                    text_color=COLOR_TEXT,
                )
            )
            self.rarity_spinner = Spinner(
                text=row.rarity if row.rarity in RARITIES else DEFAULT_RARITY,
                values=list(RARITIES),
                size_hint=(None, None),
                size=(dp(90), dp(40)),
            )
            row_box.add_widget(self.rarity_spinner)
            self.rarity_row = row_box
            self.box.add_widget(row_box)

        self.artist_field = MDTextField(text=row.artist, hint_text=t("editor.artist"))
        self.box.add_widget(self.artist_field)

        base_title = (
            t("editor.copy_title")
            if row.is_copy
            else t("editor.token_base_title")
            if row.is_token
            else t("editor.card_base_title")
        )
        self.box.add_widget(
            MDLabel(
                text=base_title,
                theme_text_color="Custom",
                text_color=COLOR_DIM,
                size_hint_y=None,
                height=dp(28),
            )
        )

        search_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        placeholder = (
            t("editor.search_token") if row.is_token else t("editor.search_card")
        )
        self.search_field = MDTextField(hint_text=placeholder)
        self.search_field.bind(on_text_validate=self._on_search)
        search_row.add_widget(self.search_field)
        search_row.add_widget(
            MDFlatButton(text=t("editor.search"), on_release=self._on_search)
        )
        self.box.add_widget(search_row)

        scroll, self.results_grid = self.list_container()
        self.box.add_widget(scroll)

        self.base_label = MDLabel(
            text=self._base_text(),
            theme_text_color="Custom",
            text_color=COLOR_TEXT,
            size_hint_y=None,
            height=dp(28),
        )
        self.box.add_widget(self.base_label)

        buttons = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        buttons.add_widget(
            MDFlatButton(text=t("common.cancel"), on_release=lambda _w: self.dismiss())
        )
        buttons.add_widget(
            MDRaisedButton(text=t("common.save"), on_release=lambda _w: self._save())
        )
        self.box.add_widget(buttons)

        self._populate_candidates()

    # ---------------------------------------------------------------- interno

    def _base_text(self) -> str:
        if self.selected_base is None:
            return t("editor.base_current_none")
        return t("editor.base_current", name=self.selected_base.name)

    def _fill_results(self, names: list[str]) -> None:
        self.results_grid.clear_widgets()
        for name in names:
            button = MDFlatButton(
                text=name,
                size_hint_y=None,
                height=dp(44),
                on_release=lambda _w, n=name: self._pick(n),
            )
            self.results_grid.add_widget(button)

    def _populate_candidates(self) -> None:
        self._fill_results([cand.card.name for cand in self.row.candidates])

    def _on_search(self, *_args) -> None:
        query = self.search_field.text.strip()
        if not query or self.matcher is None:
            return
        self._fill_results(self.matcher.search_names(query, 30))

    def _pick(self, name: str) -> None:
        if self.matcher is None:
            return
        card = self.matcher.db.by_name(name)
        if card is None:
            return
        self.selected_base = card
        self.base_label.text = t("editor.base_current", name=card.name)
        if self.rarity_spinner is not None:
            self.rarity_spinner.text = self.app.deduced_rarity(card)

    def _save(self) -> None:
        name = self.name_field.text.strip()
        if not name or (self.selected_base is None and not self.row.is_copy):
            self.box.add_widget(
                MDLabel(
                    text=t("editor.missing_name_text"),
                    theme_text_color="Custom",
                    text_color=COLOR_BAD,
                    size_hint_y=None,
                    height=dp(28),
                )
            )
            return
        self.row.new_name = name
        if self.rarity_spinner is not None:
            self.row.rarity = self.rarity_spinner.text
        self.row.artist = self.artist_field.text.strip()
        self.row.base = self.selected_base
        if self.selected_base is not None and self.selected_base.name.lower() == name.lower():
            self.row.score = 100.0
            self.row.reason = "reason.same_name"
        self.app.refresh_row(self.row)
        self.app.mark_copy_tokens()
        self.dismiss()


class SettingsPopup(Popup):
    """Percorsi di Forge e lingua dell'interfaccia."""

    def __init__(self, app: "ImporterAppUI", **kwargs) -> None:
        super().__init__(title=t("settings.title"), size_hint=(0.95, 0.9), **kwargs)
        self.app = app
        self._pending_settings_apply: tuple[str, bool] | None = None
        settings = app.settings

        box = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10))
        self.box = box
        self.add_widget(box)

        self.fields: dict[str, MDTextField] = {}
        for key in ("forge_root", "custom_dir", "cache_dir"):
            row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
            field_ = MDTextField(
                text=getattr(settings, key), hint_text=t(f"settings.{key}")
            )
            row.add_widget(field_)
            row.add_widget(
                MDFlatButton(
                    text=t("common.browse"),
                    on_release=lambda _w, target=key: self._browse_field(target),
                )
            )
            self.fields[key] = field_
            box.add_widget(row)

        box.add_widget(
            MDLabel(
                text=t("settings.hint"),
                theme_text_color="Custom",
                text_color=COLOR_DIM,
                size_hint_y=None,
                height=dp(60),
            )
        )

        if android_env.IS_ANDROID:
            box.add_widget(
                MDLabel(
                    text=t("settings.quick_paths"),
                    theme_text_color="Custom",
                    text_color=COLOR_TEXT,
                    size_hint_y=None,
                    height=dp(28),
                )
            )
            quick_paths = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
            rows = [
                android_env.FORGE_QUICK_CHOICES[index : index + 2]
                for index in range(0, len(android_env.FORGE_QUICK_CHOICES), 2)
            ]
            quick_paths.height = dp(46 * max(1, len(rows)))
            for pair in rows:
                row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
                for label_key, raw_path in pair:
                    row.add_widget(
                        MDFlatButton(
                            text=t(label_key),
                            on_release=lambda _w, target=raw_path: self._apply_quick_root(target),
                        )
                    )
                quick_paths.add_widget(row)
            box.add_widget(quick_paths)

        language_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        language_row.add_widget(
            MDLabel(
                text=t("app.language_label"),
                theme_text_color="Custom",
                text_color=COLOR_TEXT,
            )
        )
        self.language_spinner = Spinner(
            text=label_for_code(i18n.get_language()),
            values=language_labels(),
            size_hint=(None, None),
            size=(dp(140), dp(40)),
        )
        language_row.add_widget(self.language_spinner)
        box.add_widget(language_row)

        buttons = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        buttons.add_widget(
            MDFlatButton(text=t("settings.autodetect"), on_release=self._autodetect)
        )
        buttons.add_widget(
            MDFlatButton(text=t("common.cancel"), on_release=lambda _w: self.dismiss())
        )
        buttons.add_widget(
            MDRaisedButton(text=t("common.save"), on_release=self._save)
        )
        box.add_widget(buttons)

    def _autodetect(self) -> None:
        try:
            if android_env.IS_ANDROID and not android_env.has_all_files_access():
                android_env.request_storage_access()
                self.app._show_status(t("status.storage_access_needed"), COLOR_WARN)
                return
            detected = android_env.default_settings()
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            self.app._show_status(f"{t('status.forge_missing')} ({exc})", COLOR_BAD)
            return

        updated = False
        for key, field_ in self.fields.items():
            value = getattr(detected, key)
            if value:
                field_.text = value
                updated = True
        if not updated:
            self.app._show_status(t("status.forge_missing"), COLOR_WARN)

    def _browse_field(self, key: str) -> None:
        if key == "forge_root" and android_env.IS_ANDROID:
            opened = android_env.pick_android_tree(
                lambda path, target=key: self._set_field(target, path)
            )
            if opened:
                return
        start_path = android_env.settings_start_dir(key, self.fields[key].text.strip())
        FilePickerPopup(
            self.app,
            folder_mode=True,
            on_folder=lambda path, target=key: self._set_field(target, path),
            start_path=start_path,
            title=t(f"settings.{key}"),
        ).open()

    def _set_field(self, key: str, path: Path) -> None:
        if key == "forge_root":
            root = android_env.resolve_forge_root(path) or path
            self.fields[key].text = str(root)
            custom_dir = android_env._custom_dir(root)
            cache_dir = android_env._cache_dir(root)
            if custom_dir is not None:
                self.fields["custom_dir"].text = str(custom_dir)
            if cache_dir is not None:
                self.fields["cache_dir"].text = str(cache_dir)
            return
        self.fields[key].text = str(path)

    def _apply_quick_root(self, raw_path: str) -> None:
        self._set_field("forge_root", Path(raw_path))

    def _save(self) -> None:
        try:
            for key, field_ in self.fields.items():
                setattr(self.app.settings, key, field_.text.strip())
            code = code_for_label(self.language_spinner.text)
            language_changed = code != i18n.get_language()
            self.app.settings.language = code
            P.save_settings(self.app.settings)
            self._pending_settings_apply = (code, language_changed)
            self.dismiss()
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            self.app._show_status(f"{t('common.error')}: {exc}", COLOR_BAD)

    def on_dismiss(self) -> None:
        pending = self._pending_settings_apply
        self._pending_settings_apply = None
        if pending is None:
            return
        Clock.schedule_once(
            lambda _dt, lang=pending[0], changed=pending[1]: self._apply_saved_settings(
                lang, changed
            ),
            0,
        )

    def _apply_saved_settings(self, language_code: str, language_changed: bool) -> None:
        try:
            if language_changed:
                i18n.set_language(language_code)
                self.app.rebuild_ui()
            else:
                self.app.after_settings_changed()
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            self.app._show_status(f"{t('common.error')}: {exc}", COLOR_BAD)


class NewEditionPopup(Popup):
    """Codice e nome di una nuova edizione custom."""

    def __init__(self, app: "ImporterAppUI", on_create, **kwargs) -> None:
        super().__init__(title=t("edition.title"), size_hint=(0.9, None), **kwargs)
        self.height = dp(300)
        self.on_create = on_create

        box = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10))
        self.code_field = MDTextField(hint_text=t("edition.code"))
        self.name_field = MDTextField(hint_text=t("edition.name"))
        self.error_label = Label(text="", color=COLOR_BAD, size_hint_y=None, height=dp(24))
        buttons = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        buttons.add_widget(
            MDFlatButton(text=t("common.cancel"), on_release=lambda _w: self.dismiss())
        )
        buttons.add_widget(
            MDRaisedButton(text=t("edition.create"), on_release=self._create)
        )
        box.add_widget(self.code_field)
        box.add_widget(self.name_field)
        box.add_widget(self.error_label)
        box.add_widget(buttons)
        self.add_widget(box)

    def _create(self, *_args) -> None:
        code = self.code_field.text.strip().upper()
        name = self.name_field.text.strip()
        if not code or not name:
            self.error_label.text = t("edition.missing_text")
            return
        self.dismiss()
        self.on_create(code, name)


class ReportPopup(Popup):
    """Riepilogo dell'importazione, scorrevole."""

    def __init__(self, report, code: str, **kwargs) -> None:
        super().__init__(title=t("report.title", code=code), size_hint=(0.95, 0.9), **kwargs)
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        box.add_widget(
            MDLabel(
                text=t(
                    "report.header",
                    code=code,
                    imported=report.imported,
                    tokens=report.tokens,
                    scripts=report.scripts_written,
                    images=report.images_written,
                    skipped=report.skipped,
                ),
                theme_text_color="Custom",
                text_color=COLOR_TEXT,
                size_hint_y=None,
                height=dp(84),
            )
        )
        scroll = ScrollView()
        messages = "\n".join(report.messages) if report.messages else t("report.no_warnings")
        scroll.add_widget(
            Label(
                text=messages,
                size_hint_y=None,
                halign="left",
                valign="top",
                color=COLOR_DIM,
            )
        )
        scroll.children[0].bind(width=lambda _w, val: setattr(_w, "text_size", (_w.width, None)))
        box.add_widget(scroll)
        box.add_widget(
            MDRaisedButton(
                text=t("report.close"), size_hint_y=None, height=dp(48),
                on_release=lambda _w: self.dismiss(),
            )
        )
        self.add_widget(box)


class FilePickerPopup(Popup):
    """Selettore di immagini o cartelle dalla memoria del telefono."""

    def __init__(
        self,
        app: "ImporterAppUI",
        folder_mode: bool,
        on_folder=None,
        start_path: str = "",
        **kwargs,
    ) -> None:
        title = kwargs.pop(
            "title", t("dialog.folder_title") if folder_mode else t("dialog.files_title")
        )
        super().__init__(title=title, size_hint=(0.98, 0.98), **kwargs)
        self.app = app
        self.folder_mode = folder_mode
        self.on_folder = on_folder

        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        initial_path = start_path.strip() or android_env.picker_start_dir()
        if not Path(initial_path).is_dir():
            initial_path = android_env.picker_start_dir()
        self.chooser = FileChooserListView(
            path=initial_path,
            dirselect=folder_mode,
            multiselect=not folder_mode,
            filters=[] if folder_mode else IMAGE_FILTERS,
        )
        box.add_widget(self.chooser)

        buttons = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        buttons.add_widget(
            MDFlatButton(text=t("common.cancel"), on_release=lambda _w: self.dismiss())
        )
        buttons.add_widget(
            MDRaisedButton(text=t("common.save"), on_release=self._confirm)
        )
        box.add_widget(buttons)
        self.add_widget(box)

    def _confirm(self, *_args) -> None:
        selection = list(self.chooser.selection)
        current = Path(self.chooser.path)
        self.dismiss()
        if self.folder_mode:
            target = current if not selection else Path(selection[0])
            if target.is_dir():
                if self.on_folder is not None:
                    self.on_folder(target)
                else:
                    self.app.add_folder(target)
            return
        files = [Path(item) for item in selection if Path(item).is_file()]
        if files:
            self.app.add_images(files)


# --------------------------------------------------------------------------
# Applicazione
# --------------------------------------------------------------------------


class ImporterAppUI(MDApp):
    """Interfaccia e logica dell'app Android."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.settings = self._load_settings()
        i18n.set_language(self.settings.language)
        self.db: CardDB | None = None
        self.matcher: Matcher | None = None
        self.token_matcher: TokenMatcher | None = None
        self.rarities: RarityIndex | None = None
        self.rows: dict[str, Row] = {}
        self.cards: dict[str, ItemCard] = {}
        self.editions: list[Edition] = []
        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self._row_counter = 0
        self._token_count = 0
        self._crop_value = False
        self._move_value = True

    # ------------------------------------------------------------ impostazioni

    @staticmethod
    def _load_settings() -> P.Settings:
        settings = P.load_settings()
        if not settings.forge_root:
            detected = android_env.default_settings()
            if detected.forge_root:
                settings.forge_root = detected.forge_root
                settings.custom_dir = detected.custom_dir
                settings.cache_dir = detected.cache_dir
                P.save_settings(settings)
        return settings

    # ------------------------------------------------------------------ UI

    def build(self):
        if android_env.IS_ANDROID:
            ocr.set_backend(mlkit_ocr.read_text)
            android_env.request_storage_access()

        self.title = t("app.title")
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        Window.clearcolor = (0.09, 0.09, 0.10, 1)

        root = BoxLayout(orientation="vertical")
        self.root_box = root
        self._build_ui(root)

        Clock.schedule_interval(self._poll_queue, 0.1)
        self.refresh_editions()
        self.show_paths()
        self.start_db_load()
        return root

    def _build_ui(self, root: BoxLayout) -> None:
        self.toolbar = MDTopAppBar(
            title=t("app.title"),
            elevation=2,
            right_action_items=[
                ["cog", lambda _w: self.open_settings()],
            ],
        )
        self.toolbar.size_hint_y = None
        self.toolbar.height = dp(56)
        root.add_widget(self.toolbar)

        self.status_label = Label(
            text="",
            size_hint_y=None,
            height=dp(44),
            color=COLOR_DIM,
            halign="left",
            valign="middle",
        )
        self.status_label.bind(
            width=lambda widget, value: setattr(
                widget, "text_size", (value - dp(16), None)
            ),
            texture_size=lambda widget, value: setattr(
                widget, "height", max(dp(40), value[1] + dp(8))
            ),
        )
        root.add_widget(self.status_label)

        self.progress = MDProgressBar(size_hint_y=None, height=dp(8))
        root.add_widget(self.progress)

        scroll = ScrollView()
        self.list_grid = GridLayout(cols=1, spacing=dp(8), size_hint_y=None, padding=dp(8))
        self.list_grid.bind(minimum_height=self.list_grid.setter("height"))
        scroll.add_widget(self.list_grid)
        root.add_widget(scroll)

        root.add_widget(self._build_controls())

    def _build_controls(self) -> BoxLayout:
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=dp(8))
        box.bind(minimum_height=box.setter("height"))

        first = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        first.add_widget(
            MDRaisedButton(text=t("toolbar.add_images"), on_release=lambda _w: self.pick_files())
        )
        first.add_widget(
            MDFlatButton(text=t("toolbar.add_folder"), on_release=lambda _w: self.pick_folder())
        )
        first.add_widget(
            MDFlatButton(text=t("toolbar.clear"), on_release=lambda _w: self.clear_rows())
        )
        box.add_widget(first)

        self.edition_spinner = Spinner(
            text=t("common.new_edition"),
            values=[t("common.new_edition")],
            size_hint_y=None,
            height=dp(44),
        )
        box.add_widget(self.edition_spinner)

        second = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self.crop_check = CheckBox(size_hint_x=None, width=dp(40))
        self.move_check = CheckBox(size_hint_x=None, width=dp(40), active=self._move_value)
        crop_label = MDLabel(
            text=t("bottom.crop"), theme_text_color="Custom",
            text_color=COLOR_TEXT, size_hint_x=None, width=dp(120),
        )
        move_label = MDLabel(
            text=t("bottom.move"), theme_text_color="Custom",
            text_color=COLOR_TEXT, size_hint_x=None, width=dp(130),
        )
        second.add_widget(self.crop_check)
        second.add_widget(crop_label)
        second.add_widget(self.move_check)
        second.add_widget(move_label)
        box.add_widget(second)

        self.import_button = MDRaisedButton(
            text=t("bottom.import"), size_hint_y=None, height=dp(52),
            on_release=lambda _w: self.import_all(),
        )
        box.add_widget(self.import_button)
        return box

    def rebuild_ui(self) -> None:
        """Ricostruisce l'interfaccia dopo un cambio di lingua."""
        try:
            self.title = t("app.title")
            self._crop_value = self.crop_check.active
            self._move_value = self.move_check.active
            selected_edition = self._selected_edition()
            selected_path = str(selected_edition.path) if selected_edition is not None else ""
            edition_choice = self.edition_spinner.text

            self.root_box.clear_widgets()
            self.list_grid.clear_widgets()
            self.cards.clear()
            self._build_ui(self.root_box)

            self.crop_check.active = self._crop_value
            self.move_check.active = self._move_value
            self.refresh_editions()

            if selected_path:
                for edition in self.editions:
                    if str(edition.path) == selected_path:
                        self.edition_spinner.text = f"{edition.code} - {edition.name}"
                        break
                else:
                    if edition_choice in self.edition_spinner.values:
                        self.edition_spinner.text = edition_choice
            elif edition_choice in self.edition_spinner.values:
                self.edition_spinner.text = edition_choice

            for row in self.rows.values():
                self._render_row(row)
            if self.db is not None:
                self.show_ready()
            else:
                self.show_paths()
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            self._show_status(f"{t('common.error')}: {exc}", COLOR_BAD)

    def after_settings_changed(self) -> None:
        try:
            self.show_paths()
            self.refresh_editions()
            self.db = None
            self.matcher = None
            self.token_matcher = None
            self.start_db_load()
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            self._show_status(f"{t('common.error')}: {exc}", COLOR_BAD)

    # -------------------------------------------------------------- stato

    def _show_status(self, message: str, color=COLOR_DIM) -> None:
        self.status_label.text = message
        self.status_label.color = color

    def show_ready(self) -> None:
        self._show_status(
            t(
                "status.db_ready",
                cards=len(self.db.cards),
                tokens=self._token_count,
                root=self.settings.forge_root,
            ),
            COLOR_OK,
        )

    def show_paths(self) -> None:
        try:
            problems = self.settings.problems()
            if problems:
                self._show_status("\u26a0 " + "  |  ".join(problems), COLOR_WARN)
            else:
                self._show_status(
                    t("status.forge_path", root=self.settings.forge_root), COLOR_OK
                )
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            self._show_status(f"{t('common.error')}: {exc}", COLOR_BAD)

    def _set_busy(self, value: bool) -> None:
        self.busy = value
        self.import_button.disabled = value

    # --------------------------------------------------------------- edizioni

    def refresh_editions(self) -> None:
        editions_dir = self.settings.editions_dir()
        self.editions = []
        try:
            if editions_dir.is_dir():
                for file in sorted(editions_dir.glob("*.txt")):
                    edition = Edition.load(file)
                    if edition.code:
                        self.editions.append(edition)
        except OSError:
            self.editions = []
        values = [f"{e.code} - {e.name}" for e in self.editions] + [t("common.new_edition")]
        self.edition_spinner.values = values
        if self.edition_spinner.text not in values:
            self.edition_spinner.text = values[0]

    def _selected_edition(self) -> Edition | None:
        for edition in self.editions:
            if f"{edition.code} - {edition.name}" == self.edition_spinner.text:
                return edition
        return None

    def _target_edition(self):
        """(percorso, codice, nome) dell'edizione scelta, o None se annullato."""
        edition = self._selected_edition()
        if edition is not None:
            return edition.path, edition.code, edition.name
        target: list = []

        def created(code: str, name: str) -> None:
            target.append((self.settings.editions_dir() / f"{code}.txt", code, name))

        popup = NewEditionPopup(self, created)
        popup.open()
        deadline = Clock.schedule_interval(lambda _dt: self._await_choice(popup, target), 0.2)
        self._choice_timer = deadline
        self._choice_target = target
        return None

    def _await_choice(self, popup, target: list) -> None:
        # Il dialogo e' bloccante solo dal punto di vista dell'utente: quando si
        # chiude si riprende il flusso dell'importazione.
        if popup.parent is None:
            Clock.unschedule(self._choice_timer)
            if target:
                self._start_import(target[0])

    # ------------------------------------------------------------------- dati

    def start_db_load(self) -> None:
        if not self.settings.forge_root:
            self._show_status(t("status.forge_missing"), COLOR_BAD)
            return
        db_path = P.card_db_path(Path(self.settings.forge_root))
        if db_path is None:
            self._show_status(t("status.db_missing"), COLOR_BAD)
            return
        self._show_status(t("status.loading_db"))
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
            self.queue.put(("db_ready", db, rarities, token_db))
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            self.queue.put(("fatal", t("status.db_read_error", error=exc)))

    # ------------------------------------------------------------------ input

    def pick_files(self) -> None:
        FilePickerPopup(self, folder_mode=False).open()

    def pick_folder(self) -> None:
        FilePickerPopup(self, folder_mode=True).open()

    def add_images(self, images: list[Path]) -> None:
        self._enqueue(images)

    def add_folder(self, folder: Path) -> None:
        images = scan_images(folder)
        if not images:
            self._show_status(t("msg.no_images_text"), COLOR_WARN)
            return
        self._enqueue(images)

    def _enqueue(self, images: list[Path]) -> None:
        if self.matcher is None:
            self._show_status(t("msg.wait_text"), COLOR_WARN)
            return
        self._set_busy(True)
        self.progress.value = 0
        self._show_status(t("status.analyzing", count=len(images)))
        threading.Thread(target=self._analyze_worker, args=(images,), daemon=True).start()

    def _analyze_worker(self, images: list[Path]) -> None:
        total = len(images)
        for index, path in enumerate(images, start=1):
            try:
                reading = read_image(path)
                candidates = self._match(reading)
                self.queue.put(("row", path, reading, candidates))
            except OcrUnavailable as exc:
                self.queue.put(("fatal", str(exc)))
                return
            except Exception as exc:  # pragma: no cover - dipende dall'ambiente
                self.queue.put(("row_error", path, str(exc)))
            self.queue.put(("progress", index, total))
        self.queue.put(("analyze_done",))

    def _match(self, reading) -> list[Candidate]:
        if is_token(reading):
            return self.token_matcher.match(reading, limit=4) if self.token_matcher else []
        return self.matcher.match(reading, limit=4)

    # ---------------------------------------------------------------- tabella

    def _render_row(self, row: Row) -> None:
        card = ItemCard(self, row)
        self.cards[row.key] = card
        self.list_grid.add_widget(card)

    def refresh_row(self, row: Row) -> None:
        card = self.cards.get(row.key)
        if card is not None:
            card.refresh()

    def _add_row(self, path: Path, reading, candidates: list[Candidate]) -> None:
        self._row_counter += 1
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
        row = Row(
            key=f"r{self._row_counter}",
            image_path=path,
            reading=reading,
            candidates=candidates,
            base=base,
            score=score,
            reason=reason,
            new_name=title,
            rarity=self.deduced_rarity(base),
            is_token=token,
        )
        self.rows[row.key] = row
        self._render_row(row)

    def _resolve_basic_land(self, base, title, stem, score, reason):
        """Associa le terre base e normalizza il nome al termine ufficiale."""
        if base is not None and not is_basic_land(base):
            return base, title, score, reason
        land = detect_basic_land(title) or detect_basic_land(stem)
        if not land or self.db is None:
            return base, title, score, reason
        card = self.db.by_name(land)
        if card is None:
            return base, title, score, reason
        return card, land, 100.0, "reason.basic_land"

    def deduced_rarity(self, base: CardInfo | None) -> str:
        if base is None or self.rarities is None:
            return DEFAULT_RARITY
        return self.rarities.lookup(base.name) or DEFAULT_RARITY

    def edit_row(self, row: Row) -> None:
        CardEditorPopup(self, row).open()

    def clear_rows(self) -> None:
        self.list_grid.clear_widgets()
        self.rows.clear()
        self.cards.clear()
        self.progress.value = 0

    # -------------------------------------------------------- token copia

    def _copy_cards(self) -> dict[str, tuple[str, str]]:
        """{nome carta (lower): (prefisso, nome)} per i token-copia del set."""
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

    def mark_copy_tokens(self) -> None:
        """Segnala come token-copia le righe token che copiano una carta del set."""
        copies = self._copy_cards()
        for row in self.rows.values():
            if not row.is_token:
                continue
            entry = copies.get(row.new_name.strip().lower())
            if entry is None:
                if row.is_copy or row.copy_prefix:
                    row.is_copy = False
                    row.copy_card = ""
                    row.copy_prefix = ""
                    self.refresh_row(row)
                continue
            if row.is_copy and row.copy_card == entry[1] and row.copy_prefix == entry[0]:
                continue
            row.is_copy = True
            row.copy_card = entry[1]
            row.copy_prefix = entry[0]
            row.reason = "reason.copy"
            self.refresh_row(row)

    # ----------------------------------------------------------- importazione

    def import_all(self) -> None:
        if self.busy:
            return
        rows = list(self.rows.values())
        if not rows:
            self._show_status(t("msg.no_cards_text"), COLOR_WARN)
            return

        self.mark_copy_tokens()
        usable = [
            r for r in rows if r.new_name.strip() and (r.base is not None or r.is_copy)
        ]
        if not usable:
            self._show_status(t("msg.nothing_text"), COLOR_BAD)
            return
        self._pending_items = usable
        self._target_edition()

    def _start_import(self, target) -> None:
        edition_path, code, name = target
        options = ImportOptions(
            crop=self.crop_check.active, move_within_pics=self.move_check.active
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
            )
            for r in self._pending_items
        ]

        self._set_busy(True)
        self.progress.value = 0
        self._show_status(t("status.importing", count=len(items), code=code))
        importer = Importer(
            self.db,
            self.settings.resolved_custom_dir(),
            self.settings.pics_dir(),
            self.settings.tokens_dir(),
            self.settings.token_pics_dir(),
        )
        threading.Thread(
            target=self._import_worker,
            args=(importer, items, edition_path, code, name, options),
            daemon=True,
        ).start()

    def _import_worker(self, importer, items, edition_path, code, name, options) -> None:
        try:
            report = importer.run(items, edition_path, code, name, options)
            self.queue.put(("import_done", report, code))
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            self.queue.put(("fatal", t("status.import_error", error=exc)))

    # ------------------------------------------------------------------- coda

    def _poll_queue(self, _dt) -> None:
        try:
            while True:
                self._handle_message(self.queue.get_nowait())
        except queue.Empty:
            pass

    def _handle_message(self, message: tuple) -> None:
        kind = message[0]
        if kind == "db_ready":
            self.db = message[1]
            self.matcher = Matcher(self.db)
            self.rarities = message[2]
            token_db = message[3]
            self.token_matcher = TokenMatcher(token_db) if token_db is not None else None
            self._token_count = len(token_db.cards) if token_db is not None else 0
            self.show_ready()
        elif kind == "row":
            _, path, reading, candidates = message
            self._add_row(path, reading, candidates)
        elif kind == "row_error":
            _, path, error = message
            self._add_row(path, None, [])
            self._show_status(t("status.analyze_error", name=path.name, error=error), COLOR_BAD)
        elif kind == "progress":
            _, done, total = message
            self.progress.value = 100.0 * done / total if total else 0
            self._show_status(t("status.analyzing_progress", done=done, total=total))
        elif kind == "analyze_done":
            self._set_busy(False)
            self.mark_copy_tokens()
            ready = sum(
                1 for r in self.rows.values() if r.new_name.strip() and (r.base or r.is_copy)
            )
            self._show_status(
                t("status.analyze_done", count=len(self.rows), ready=ready), COLOR_OK
            )
        elif kind == "import_done":
            _, report, code = message
            self._set_busy(False)
            self._show_status(
                t(
                    "status.import_done",
                    imported=report.imported,
                    tokens=report.tokens,
                    code=code,
                ),
                COLOR_OK,
            )
            self.clear_rows()
            self.refresh_editions()
            ReportPopup(report, code).open()
        elif kind == "fatal":
            self._set_busy(False)
            self._show_status(message[1], COLOR_BAD)

    # ------------------------------------------------------------- dialoghi

    def open_settings(self) -> None:
        SettingsPopup(self).open()


def run() -> None:
    ImporterAppUI().run()


if __name__ == "__main__":
    run()
