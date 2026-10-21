"""Internazionalizzazione dell'interfaccia.

L'inglese e' la lingua principale (default); l'italiano e' selezionabile dal
menu a tendina nella toolbar. Le traduzioni sono raccolte in un dizionario e
lette tramite :func:`t`, che accetta le variabili di formato come keyword:

    t("status.forge_path", root="C:/Forge")

La lingua attiva e' uno stato globale del processo: la GUI la imposta all'avvio
(dalle impostazioni) e ad ogni cambio dal menu.
"""

from __future__ import annotations

DEFAULT_LANGUAGE = "en"

# Etichetta mostrata nel menu -> codice interno.
LANGUAGES: dict[str, str] = {
    "en": "English",
    "it": "Italiano",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # --- comune ---
        "common.new_edition": "\u00ab new edition \u00bb",
        "common.none": "\u00abnone\u00bb",
        "common.cancel": "Cancel",
        "common.save": "Save",
        "common.browse": "Browse...",
        "common.error": "Error",
        # --- finestra ---
        "app.title": "Forge Card Importer",
        "app.language_label": "Language:",
        # --- toolbar ---
        "toolbar.add_folder": "Add folder...",
        "toolbar.add_images": "Add images...",
        "toolbar.clear": "Clear",
        "toolbar.edition": "Edition:",
        "toolbar.settings": "Settings",
        # --- barra di stato ---
        "status.starting": "Starting...",
        "status.forge_path": "Forge: {root}",
        "status.loading_db": "Loading Forge card archive...",
        "status.forge_missing": "Forge installation not found: open Settings and pick the folder.",
        "status.storage_access_needed": "Grant full file access in Android settings, then tap Auto-detect again.",
        "status.db_missing": "Card archive not found in res\\cardsfolder.",
        "status.db_ready": "Ready. {cards} cards and {tokens} tokens indexed | Forge: {root}",
        "status.analyzing": "Analyzing {count} images...",
        "status.analyzing_progress": "Analyzing {done}/{total}...",
        "status.analyze_error": "Error on {name}: {error}",
        "status.analyze_done": "Analysis complete: {count} images, {ready} ready to import.",
        "status.importing": "Importing {count} items into {code}...",
        "status.import_done": "Imported {imported} cards and {tokens} tokens into {code}.",
        "status.db_read_error": "Could not read the card archive: {error}",
        "status.import_error": "Error while importing: {error}",
        # --- tabella ---
        "col.image": "Image",
        "col.title": "Read title",
        "col.base": "Base (rules)",
        "col.conf": "Conf.",
        "col.reason": "Reason",
        "col.new": "New name",
        "col.rar": "Rar.",
        "col.status": "Status",
        # --- stato riga ---
        "state.read_error": "read error",
        "state.copy_token": "copy token",
        "state.choose_base": "choose base",
        "state.ready": "ready",
        "state.check": "check",
        # --- valori ---
        "value.copy_of": "copy of {name}",
        # --- motivi ---
        "reason.base_hint": "original name",
        "reason.title": "title",
        "reason.rules": "rules text",
        "reason.token_name": "token name",
        "reason.token_ambiguous": "token name (several tokens share it)",
        "reason.type": "type",
        "reason.basic_land": "basic land",
        "reason.same_name": "same name",
        "reason.copy": "copy {prefix}",
        # --- barra inferiore ---
        "bottom.edit": "Edit selected...",
        "bottom.remove": "Remove selected",
        "bottom.crop": "Crop to 63x88 mm",
        "bottom.move": "Move to cache",
        "bottom.import": "Import all into Forge",
        # --- messaggi ---
        "msg.wait_title": "Please wait",
        "msg.wait_text": "Forge's card archive is not ready yet.",
        "msg.no_images_title": "No images",
        "msg.no_images_text": "The folder contains no supported images.",
        "msg.select_title": "Selection",
        "msg.select_text": "Select a row first.",
        "msg.no_cards_title": "No cards",
        "msg.no_cards_text": "Add some images first.",
        "msg.no_base_title": "Images without a base",
        "msg.no_base_text": "{count} images have no base and will be ignored:\n{names}{more}\n\nContinue with the other {usable}?",
        "msg.and_more": "\n  ... and {count} more",
        "msg.nothing_title": "Nothing to import",
        "msg.nothing_text": "Nothing is ready for import.",
        # --- finestre di scelta file ---
        "dialog.folder_title": "Folder with the card images",
        "dialog.files_title": "Card images",
        "dialog.pick_folder": "Select folder",
        "dialog.filter_images": "Images",
        "dialog.filter_all": "All",
        # --- editor carta ---
        "editor.title": "Edit - {name}",
        "editor.info": "Image: {name}\nRead title: {title}\nPrinted original name: {hint}",
        "editor.new_name": "New name",
        "editor.rarity": "Rarity",
        "editor.artist": "Artist (opt.)",
        "editor.same_name": "Use the base's name (only the image is needed, no new script)",
        "editor.copy_title": "Copy token (Eternalize/Embalm): only the image is needed, no base",
        "editor.token_base_title": "Token base (provides type, P/T and abilities)",
        "editor.card_base_title": "Card base (provides the rules text)",
        "editor.search_token": "Search a token by name...",
        "editor.search_card": "Search a card by name...",
        "editor.search": "Search",
        "editor.base_current": "Current base: {name}",
        "editor.base_current_none": "Current base: \u2014 (none)",
        "editor.base_current_full": "Current base: {name}  ({score}, {reason})",
        "editor.candidate_label": "{name} ({info})",
        "editor.missing_name_title": "Missing name",
        "editor.missing_name_text": "The new name cannot be empty.",
        "editor.missing_base_title": "Missing base",
        "editor.missing_base_text": "Select the base that provides the rules.",
        # --- impostazioni ---
        "settings.title": "Settings",
        "settings.forge_root": "Forge installation",
        "settings.custom_dir": "Custom folder",
        "settings.cache_dir": "Cache folder (LOCALAPPDATA)",
        "settings.hint": "If left empty, the path is detected automatically.",
        "settings.autodetect": "Auto-detect",
        # --- nuova edizione ---
        "edition.title": "New edition",
        "edition.code": "Code (e.g. MHW)",
        "edition.name": "Edition name",
        "edition.create": "Create",
        "edition.missing_title": "Missing data",
        "edition.missing_text": "Enter the edition code and name.",
        # --- riepilogo ---
        "report.title": "Import summary - {code}",
        "report.header": "Edition {code}\n{imported} cards imported  |  {tokens} tokens imported  |  {scripts} scripts created  |  {images} images written  |  {skipped} skipped",
        "report.no_warnings": "No warnings.",
        "report.open_pics": "Open images folder",
        "report.open_tokens": "Open tokens folder",
        "report.close": "Close",
        # --- percorsi (impostazioni) ---
        "paths.forge_missing": "Forge installation not detected: select the folder that contains forge.exe.",
        "paths.no_scripts": "No card script found in {root}\\res\\cardsfolder.",
        "paths.custom_missing": "Custom folder does not exist: {dir}",
        "paths.cache_missing": "Cache folder does not exist: {dir}",
        # --- generazione (log e note) ---
        "gen.skipped_card_name": "SKIPPED {name}: missing card name",
        "gen.skipped_card_base": "SKIPPED {name}: base card not recognized",
        "gen.variant_of": 'Variant of "{base}" (displayed name "{name}").',
        "gen.name_official": "Name already used by an official card: Forge may confuse them.",
        "gen.same_rules": "Same rules and same name: only the image is needed.",
        "gen.variant_of_art": 'Variant of "{base}" (displayed name "{name}", art {index}/{total}).',
        "gen.edition_updated": "Edition updated: {path}",
        "gen.skipped_token_name": "SKIPPED {name}: missing token name",
        "gen.skipped_token_base": "SKIPPED {name}: token base not recognized",
        "gen.token_multi": "NOTE {stem} is created by more than one custom token: cards will use {filestem}",
        "gen.token_created": "Token created by {base}",
        "gen.token_variant": 'Art {index}/{total} of token created by {base}',
        "gen.token_line": "TOKEN {name}: {filestem}.txt (collector {collector})",
        "gen.copy_token": "Copy token {prefix} of {card}",
        "gen.copy_token_line": "COPY TOKEN {prefix} of {card}: collector {collector}",
        "gen.warn_token_script": "WARNING token script not copied for {name}: {error}",
        "gen.warn_token_refs": "WARNING token references not updated in {file}: {error}",
        "gen.token_refs_updated": "Token references updated in {file}",
    },
    "it": {
        # --- comune ---
        "common.new_edition": "\u00ab nuova edizione \u00bb",
        "common.none": "\u00abnessuna\u00bb",
        "common.cancel": "Annulla",
        "common.save": "Salva",
        "common.browse": "Sfoglia...",
        "common.error": "Errore",
        # --- finestra ---
        "app.title": "Importatore Carte Forge",
        "app.language_label": "Lingua:",
        # --- toolbar ---
        "toolbar.add_folder": "Aggiungi cartella...",
        "toolbar.add_images": "Aggiungi immagini...",
        "toolbar.clear": "Svuota",
        "toolbar.edition": "Edizione:",
        "toolbar.settings": "Impostazioni",
        # --- barra di stato ---
        "status.starting": "Avvio in corso...",
        "status.forge_path": "Forge: {root}",
        "status.loading_db": "Caricamento archivio carte di Forge...",
        "status.forge_missing": "Installazione di Forge non trovata: apri Impostazioni e indica la cartella.",
        "status.storage_access_needed": "Concedi l'accesso completo ai file nelle impostazioni Android, poi premi di nuovo Rileva automaticamente.",
        "status.db_missing": "Archivio carte non trovato in res\\cardsfolder.",
        "status.db_ready": "Pronto. {cards} carte e {tokens} token indicizzati | Forge: {root}",
        "status.analyzing": "Analisi di {count} immagini...",
        "status.analyzing_progress": "Analisi {done}/{total}...",
        "status.analyze_error": "Errore su {name}: {error}",
        "status.analyze_done": "Analisi completata: {count} immagini, {ready} pronte da importare.",
        "status.importing": "Importazione di {count} elementi in {code}...",
        "status.import_done": "Importate {imported} carte e {tokens} token in {code}.",
        "status.db_read_error": "Impossibile leggere l'archivio carte: {error}",
        "status.import_error": "Errore durante l'importazione: {error}",
        # --- tabella ---
        "col.image": "Immagine",
        "col.title": "Titolo letto",
        "col.base": "Base (regole)",
        "col.conf": "Conf.",
        "col.reason": "Motivo",
        "col.new": "Nuovo nome",
        "col.rar": "Rar.",
        "col.status": "Stato",
        # --- stato riga ---
        "state.read_error": "errore lettura",
        "state.copy_token": "token copia",
        "state.choose_base": "base da scegliere",
        "state.ready": "pronta",
        "state.check": "controlla",
        # --- valori ---
        "value.copy_of": "copia di {name}",
        # --- motivi ---
        "reason.base_hint": "nome originale",
        "reason.title": "titolo",
        "reason.rules": "testo regole",
        "reason.token_name": "nome token",
        "reason.token_ambiguous": "nome token (piu' token lo condividono)",
        "reason.type": "tipo",
        "reason.basic_land": "terra base",
        "reason.same_name": "stesso nome",
        "reason.copy": "copia {prefix}",
        # --- barra inferiore ---
        "bottom.edit": "Modifica selezionata...",
        "bottom.remove": "Rimuovi selezionate",
        "bottom.crop": "Ritaglia a 63x88 mm",
        "bottom.move": "Sposta nella cache",
        "bottom.import": "Importa tutto in Forge",
        # --- messaggi ---
        "msg.wait_title": "Attendere",
        "msg.wait_text": "L'archivio carte di Forge non e' ancora pronto.",
        "msg.no_images_title": "Nessuna immagine",
        "msg.no_images_text": "Nella cartella non ci sono immagini supportate.",
        "msg.select_title": "Selezione",
        "msg.select_text": "Seleziona prima una riga.",
        "msg.no_cards_title": "Nessuna carta",
        "msg.no_cards_text": "Aggiungi prima delle immagini.",
        "msg.no_base_title": "Immagini senza base",
        "msg.no_base_text": "{count} immagini non hanno una base e verranno ignorate:\n{names}{more}\n\nProseguire con le altre {usable}?",
        "msg.and_more": "\n  ... e altre {count}",
        "msg.nothing_title": "Niente da importare",
        "msg.nothing_text": "Niente pronto per l'importazione.",
        # --- finestre di scelta file ---
        "dialog.folder_title": "Cartella con le immagini delle carte",
        "dialog.files_title": "Immagini delle carte",
        "dialog.pick_folder": "Seleziona cartella",
        "dialog.filter_images": "Immagini",
        "dialog.filter_all": "Tutti",
        # --- editor carta ---
        "editor.title": "Modifica - {name}",
        "editor.info": "Immagine: {name}\nTitolo letto: {title}\nNome originale stampato: {hint}",
        "editor.new_name": "Nuovo nome",
        "editor.rarity": "Rarita'",
        "editor.artist": "Artista (opz.)",
        "editor.same_name": "Usa lo stesso nome della base (serve solo l'immagine, nessun nuovo script)",
        "editor.copy_title": "Token copia (Eternalize/Embalm): serve solo l'immagine, nessuna base",
        "editor.token_base_title": "Token base (fornisce tipo, P/T e abilita')",
        "editor.card_base_title": "Carta base (fornisce il testo delle regole)",
        "editor.search_token": "Cerca un token per nome...",
        "editor.search_card": "Cerca una carta per nome...",
        "editor.search": "Cerca",
        "editor.base_current": "Base attuale: {name}",
        "editor.base_current_none": "Base attuale: \u2014 (nessuna)",
        "editor.base_current_full": "Base attuale: {name}  ({score}, {reason})",
        "editor.candidate_label": "{name} ({info})",
        "editor.missing_name_title": "Nome mancante",
        "editor.missing_name_text": "Il nuovo nome non puo' essere vuoto.",
        "editor.missing_base_title": "Base mancante",
        "editor.missing_base_text": "Seleziona la base che fornisce le regole.",
        # --- impostazioni ---
        "settings.title": "Impostazioni",
        "settings.forge_root": "Installazione Forge",
        "settings.custom_dir": "Cartella custom",
        "settings.cache_dir": "Cartella cache (LOCALAPPDATA)",
        "settings.hint": "Se lasciato vuoto, il percorso viene rilevato automaticamente.",
        "settings.autodetect": "Rileva automaticamente",
        # --- nuova edizione ---
        "edition.title": "Nuova edizione",
        "edition.code": "Codice (es. MHW)",
        "edition.name": "Nome edizione",
        "edition.create": "Crea",
        "edition.missing_title": "Dati mancanti",
        "edition.missing_text": "Inserisci codice e nome dell'edizione.",
        # --- riepilogo ---
        "report.title": "Riepilogo importazione - {code}",
        "report.header": "Edizione {code}\n{imported} carte importate  |  {tokens} token importati  |  {scripts} script creati  |  {images} immagini scritte  |  {skipped} ignorate",
        "report.no_warnings": "Nessun avviso.",
        "report.open_pics": "Apri cartella immagini",
        "report.open_tokens": "Apri cartella token",
        "report.close": "Chiudi",
        # --- percorsi (impostazioni) ---
        "paths.forge_missing": "Installazione di Forge non rilevata: seleziona la cartella che contiene forge.exe.",
        "paths.no_scripts": "Nessun card script trovato in {root}\\res\\cardsfolder.",
        "paths.custom_missing": "Cartella custom inesistente: {dir}",
        "paths.cache_missing": "Cartella cache inesistente: {dir}",
        # --- generazione (log e note) ---
        "gen.skipped_card_name": "IGNORATA {name}: nome carta mancante",
        "gen.skipped_card_base": "IGNORATA {name}: carta base non riconosciuta",
        "gen.variant_of": 'Variante di "{base}" (nome mostrato "{name}").',
        "gen.name_official": "Nome gia' usato da una carta ufficiale: Forge potrebbe confonderli.",
        "gen.same_rules": "Stesse regole e stesso nome: serve solo l'immagine.",
        "gen.variant_of_art": 'Variante di "{base}" (nome mostrato "{name}", arte {index}/{total}).',
        "gen.edition_updated": "Edizione aggiornata: {path}",
        "gen.skipped_token_name": "IGNORATO {name}: nome token mancante",
        "gen.skipped_token_base": "IGNORATO {name}: token base non riconosciuto",
        "gen.token_multi": "NOTA {stem} e' creato da piu' token custom: le carte useranno {filestem}",
        "gen.token_created": "Token creato da {base}",
        "gen.token_variant": 'Arte {index}/{total} del token creato da {base}',
        "gen.token_line": "TOKEN {name}: {filestem}.txt (collector {collector})",
        "gen.copy_token": "Token copia {prefix} di {card}",
        "gen.copy_token_line": "TOKEN copia {prefix} di {card}: collector {collector}",
        "gen.warn_token_script": "ATTENZIONE script token non copiato per {name}: {error}",
        "gen.warn_token_refs": "ATTENZIONE richiami token non aggiornati in {file}: {error}",
        "gen.token_refs_updated": "Richiami token aggiornati in {file}",
    },
}

_current: str = DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    """Imposta la lingua attiva (ignora i codici sconosciuti)."""
    global _current
    _current = code if code in TRANSLATIONS else DEFAULT_LANGUAGE


def get_language() -> str:
    return _current


def language_labels() -> list[str]:
    """Etichette delle lingue, nell'ordine di dichiarazione (inglese per prima)."""
    return list(LANGUAGES.values())


def code_for_label(label: str) -> str:
    for code, name in LANGUAGES.items():
        if name == label:
            return code
    return DEFAULT_LANGUAGE


def label_for_code(code: str) -> str:
    return LANGUAGES.get(code, LANGUAGES[DEFAULT_LANGUAGE])


def t(key: str, **kwargs: object) -> str:
    """Testo tradotto per la lingua attiva (fallback: inglese, poi la chiave)."""
    table = TRANSLATIONS.get(_current, {})
    text = table.get(key) or TRANSLATIONS[DEFAULT_LANGUAGE].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text
