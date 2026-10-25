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
        "common.close": "Close",
        "common.browse": "Browse...",
        "common.error": "Error",
        # --- finestra ---
        "app.language_label": "Language:",
        # --- toolbar ---
        "toolbar.add_folder": "Add folder...",
        "toolbar.add_images": "Add images...",
        "toolbar.clear": "Clear",
        "toolbar.edition": "Edition:",
        "toolbar.settings": "Settings",
        "toolbar.link_faces": "Link front/back...",
        # --- barra di stato ---
        "status.starting": "Starting...",
        "status.forge_path": "Forge: {root}",
        "status.loading_db": "Loading Forge card archive...",
        "status.forge_missing": "Forge installation not found: open Settings and pick the folder.",
        "status.db_missing": "Card archive not found in res\\cardsfolder.",
        "status.db_ready": "Ready. {cards} cards and {tokens} tokens indexed | Forge: {root}",
        "status.analyzing": "Analyzing {count} images...",
        "status.analyzing_progress": "Analyzing {done}/{total}...",
        "status.analyze_error": "Error on {name}: {error}",
        "status.analyze_done": "Analysis complete: {count} images, {ready} ready to import.",
        "status.importing": "Importing {count} items into {code}...",
        "status.import_done": "Imported {imported} cards and {tokens} tokens into {code}.",
        "status.import_done_emblems": "Imported {imported} cards, {tokens} tokens and {emblems} emblems into {code}.",
        "status.db_read_error": "Could not read the card archive: {error}",
        "status.import_error": "Error while importing: {error}",
        "status.phone_pushing": "Copying set {code} to the phone...",
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
        "state.emblem": "emblem",
        "state.choose_base": "choose base",
        "state.ready": "ready",
        "state.check": "check",
        "state.back_linked": "back (linked)",
        "state.back_unlinked": "back (not linked)",
        # --- valori ---
        "value.copy_of": "copy of {name}",
        "value.back_of": "back of {name}",
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
        "reason.emblem": "emblem of the base card",
        "reason.face_match": "multi-faced card (face name in the file)",
        # --- collegamento fronte/retro a mano ---
        "faces.title": "Link front and back",
        "faces.hint": "Pick the front and the back, then press Link. Repeat to link several backs to the same front.",
        "faces.front": "Front (base card)",
        "faces.back": "Back (image to link)",
        "faces.link": "Link",
        "faces.unlink": "Remove link",
        "faces.status_linked": "Back linked to: {name}",
        "faces.status_free": "Back not linked yet.",
        "faces.bad_title": "Cannot link",
        "faces.bad_text": "Choose two different images.",
        "faces.front_is_back": "The front cannot be an image already linked as a back.",
        "faces.front_no_base": "The chosen front has no recognised base card: set it first in the editor.",
        "faces.front_single_face": "The chosen front is not a multi-faced card: pick a card with front and back.",
        "faces.need_rows": "No card images available: add the images first.",
        # --- barra inferiore ---
        "bottom.edit": "Edit selected...",
        "bottom.remove": "Remove selected",
        "bottom.crop": "Crop to 63x88 mm",
        "bottom.move": "Move to cache",
        "bottom.destination": "Destination:",
        "target.pc": "PC",
        "target.phone": "Phone",
        "bottom.import": "Import all into Forge",
        "bottom.send_phone": "Send set to phone",
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
        "msg.phone_title": "Phone not ready",
        "msg.phone_text": "Open Settings and set adb, the phone and the Forge folder before importing to the phone.",
        "msg.send_title": "Send set to phone",
        "msg.send_text": "Copy set {code} to the phone? The files are taken as they already are locally, without importing again.",
        "msg.no_edition_title": "No set selected",
        "msg.no_edition_text": "Choose a previously imported set in the Edition box, then send it to the phone.",
        "msg.sent_title": "Set sent",
        # --- finestre di scelta file ---
        "dialog.folder_title": "Folder with the card images",
        "dialog.files_title": "Card images",
        "dialog.pick_folder": "Select folder",
        "dialog.adb_title": "adb executable (adb.exe)",
        "dialog.filter_exe": "Executable",
        "dialog.filter_images": "Images",
        "dialog.filter_all": "All",
        # --- editor carta ---
        "editor.title": "Edit - {name}",
        "editor.info": "Image: {name}\nRead title: {title}\nPrinted original name: {hint}",
        "editor.new_name": "New name",
        "editor.rarity": "Rarity",
        "editor.artist": "Artist (opt.)",
        "editor.same_name": "Use the base's name (only the image is needed, no new script)",
        "editor.emblem": "Custom emblem (the image of the base card's emblem)",
        "editor.copy_title": "Copy token (Eternalize/Embalm): only the image is needed, no base",
        "editor.emblem_title": "Emblem host: the Planeswalker that creates it (provides the image key)",
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
        # --- telefono (adb) ---
        "settings.phone_section": "Phone (adb)",
        "settings.adb_path": "adb executable",
        "settings.adb_device": "Connected phone",
        "settings.adb_forge_root": "Forge folder on the phone",
        "settings.adb_devices": "Find phones",
        "settings.adb_detect": "Detect",
        "settings.adb_none": "\u00abno phone\u00bb",
        "settings.adb_hint": "Import writes on this PC, then copies the set to the phone over the USB cable (adb).",
        "settings.adb_ok": "Phone ready: {device} | Forge: {root}",
        "settings.adb_missing": "adb not found: download Android Platform Tools or pick adb.exe by hand.",
        # --- telefono (messaggi) ---
        "adb.not_found": "adb not found at {path}",
        "adb.timeout": "adb did not answer within {seconds} seconds.",
        "adb.failed": "adb error: {error}",
        "adb.exit_code": "exit code {code}",
        "adb.no_device": "No phone connected: plug in the USB cable, enable USB debugging and accept the prompt on the phone.",
        "adb.no_forge": "Forge folder not reachable on the phone: {root}",
        "adb.devices_found": "{count} phone(s) found.",
        "adb.no_devices": "No phone found.",
        "adb.detected": "Forge found: {root}",
        "adb.not_detected": "Forge folder not found on the phone.",
        # --- copia sul telefono ---
        "push.edition": "Edition sent: {name}",
        "push.no_edition": "Edition file missing, not sent: {name}",
        "push.tokens": "{count} token script(s) sent",
        "push.cards": "{count} card script(s) sent",
        "push.images": "{count} card image(s) sent to {code}",
        "push.token_images": "{count} token image(s) sent to {code}",
        "push.done": "Set {code} copied to the phone.",
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
        "report.header_emblems": "Edition {code}\n{imported} cards imported  |  {tokens} tokens imported  |  {emblems} emblems imported  |  {scripts} scripts created  |  {images} images written  |  {skipped} skipped",
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
        "gen.skipped_multiface": "SKIPPED {name}: {base} is a multi-faced card, use ' // ' to give both face names",
        "gen.skipped_back_only": "SKIPPED {name}: back face of {base} without the matching front image",
        "gen.face_pair": 'Back face paired with this image: "{back}".',
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
        "gen.copy_token_variant": 'Art {index}/{total} of copy token {prefix} of {card}',
        "gen.copy_token_line": "COPY TOKEN {prefix} of {card}: collector {collector}",
        "gen.emblem": "Emblem of {card}",
        "gen.emblem_line": "EMBLEM of {card}: collector {collector}",
        "gen.skipped_emblem_base": "SKIPPED {name}: emblem host not recognized",
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
        "common.close": "Chiudi",
        "common.browse": "Sfoglia...",
        "common.error": "Errore",
        # --- finestra ---
        "app.language_label": "Lingua:",
        # --- toolbar ---
        "toolbar.add_folder": "Aggiungi cartella...",
        "toolbar.add_images": "Aggiungi immagini...",
        "toolbar.clear": "Svuota",
        "toolbar.edition": "Edizione:",
        "toolbar.settings": "Impostazioni",
        "toolbar.link_faces": "Collega fronte/retro...",
        # --- barra di stato ---
        "status.starting": "Avvio in corso...",
        "status.forge_path": "Forge: {root}",
        "status.loading_db": "Caricamento archivio carte di Forge...",
        "status.forge_missing": "Installazione di Forge non trovata: apri Impostazioni e indica la cartella.",
        "status.db_missing": "Archivio carte non trovato in res\\cardsfolder.",
        "status.db_ready": "Pronto. {cards} carte e {tokens} token indicizzati | Forge: {root}",
        "status.analyzing": "Analisi di {count} immagini...",
        "status.analyzing_progress": "Analisi {done}/{total}...",
        "status.analyze_error": "Errore su {name}: {error}",
        "status.analyze_done": "Analisi completata: {count} immagini, {ready} pronte da importare.",
        "status.importing": "Importazione di {count} elementi in {code}...",
        "status.import_done": "Importate {imported} carte e {tokens} token in {code}.",
        "status.import_done_emblems": "Importate {imported} carte, {tokens} token e {emblems} emblemi in {code}.",
        "status.db_read_error": "Impossibile leggere l'archivio carte: {error}",
        "status.import_error": "Errore durante l'importazione: {error}",
        "status.phone_pushing": "Copia del set {code} sul telefono...",
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
        "state.emblem": "emblema",
        "state.choose_base": "base da scegliere",
        "state.ready": "pronta",
        "state.check": "controlla",
        "state.back_linked": "retro (collegato)",
        "state.back_unlinked": "retro (non collegato)",
        # --- valori ---
        "value.copy_of": "copia di {name}",
        "value.back_of": "retro di {name}",
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
        "reason.emblem": "emblema della carta base",
        "reason.face_match": "carta multi-faccia (nome della faccia nel file)",
        # --- collegamento fronte/retro a mano ---
        "faces.title": "Collega fronte e retro",
        "faces.hint": "Scegli il fronte e il retro, poi premi Collega. Ripeti per collegare piu' retro allo stesso fronte.",
        "faces.front": "Fronte (carta base)",
        "faces.back": "Retro (immagine da collegare)",
        "faces.link": "Collega",
        "faces.unlink": "Rimuovi collegamento",
        "faces.status_linked": "Retro collegato a: {name}",
        "faces.status_free": "Retro non ancora collegato.",
        "faces.bad_title": "Collegamento non possibile",
        "faces.bad_text": "Scegli due immagini diverse.",
        "faces.front_is_back": "Il fronte non puo' essere un'immagine gia' collegata come retro.",
        "faces.front_no_base": "Il fronte scelto non ha una carta base riconosciuta: impostala prima nell'editor.",
        "faces.front_single_face": "Il fronte scelto non e' una carta a due lati: scegli una carta con fronte e retro.",
        "faces.need_rows": "Nessuna immagine di carta disponibile: aggiungi prima le immagini.",
        # --- barra inferiore ---
        "bottom.edit": "Modifica selezionata...",
        "bottom.remove": "Rimuovi selezionate",
        "bottom.crop": "Ritaglia a 63x88 mm",
        "bottom.move": "Sposta nella cache",
        "bottom.destination": "Destinazione:",
        "target.pc": "PC",
        "target.phone": "Telefono",
        "bottom.import": "Importa tutto in Forge",
        "bottom.send_phone": "Invia set al telefono",
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
        "msg.phone_title": "Telefono non pronto",
        "msg.phone_text": "Apri Impostazioni e configura adb, il telefono e la cartella di Forge prima di importare sul telefono.",
        "msg.send_title": "Invia set al telefono",
        "msg.send_text": "Copiare il set {code} sul telefono? I file vengono presi cosi' come sono in locale, senza reimportare.",
        "msg.no_edition_title": "Nessun set selezionato",
        "msg.no_edition_text": "Scegli nella casella Edition un set gia' importato, poi invialo al telefono.",
        "msg.sent_title": "Set inviato",
        # --- finestre di scelta file ---
        "dialog.folder_title": "Cartella con le immagini delle carte",
        "dialog.files_title": "Immagini delle carte",
        "dialog.pick_folder": "Seleziona cartella",
        "dialog.adb_title": "Eseguibile adb (adb.exe)",
        "dialog.filter_exe": "Eseguibile",
        "dialog.filter_images": "Immagini",
        "dialog.filter_all": "Tutti",
        # --- editor carta ---
        "editor.title": "Modifica - {name}",
        "editor.info": "Immagine: {name}\nTitolo letto: {title}\nNome originale stampato: {hint}",
        "editor.new_name": "Nuovo nome",
        "editor.rarity": "Rarita'",
        "editor.artist": "Artista (opz.)",
        "editor.same_name": "Usa lo stesso nome della base (serve solo l'immagine, nessun nuovo script)",
        "editor.emblem": "Emblema custom (l'immagine dell'emblema della carta base)",
        "editor.copy_title": "Token copia (Eternalize/Embalm): serve solo l'immagine, nessuna base",
        "editor.emblem_title": "Carta dell'emblema: il Planeswalker che lo crea (fornisce la chiave immagine)",
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
        # --- telefono (adb) ---
        "settings.phone_section": "Telefono (adb)",
        "settings.adb_path": "Eseguibile adb",
        "settings.adb_device": "Telefono collegato",
        "settings.adb_forge_root": "Cartella Forge sul telefono",
        "settings.adb_devices": "Cerca telefoni",
        "settings.adb_detect": "Rileva",
        "settings.adb_none": "\u00abnessun telefono\u00bb",
        "settings.adb_hint": "L'importazione scrive su questo PC, poi copia il set sul telefono via cavo USB (adb).",
        "settings.adb_ok": "Telefono pronto: {device} | Forge: {root}",
        "settings.adb_missing": "adb non trovato: scarica Android Platform Tools oppure indica adb.exe a mano.",
        # --- telefono (messaggi) ---
        "adb.not_found": "adb non trovato in {path}",
        "adb.timeout": "adb non ha risposto entro {seconds} secondi.",
        "adb.failed": "Errore adb: {error}",
        "adb.exit_code": "codice di uscita {code}",
        "adb.no_device": "Nessun telefono collegato: inserisci il cavo USB, attiva il debug USB e accetta la richiesta sul telefono.",
        "adb.no_forge": "Cartella di Forge non raggiungibile sul telefono: {root}",
        "adb.devices_found": "Trovati {count} telefoni.",
        "adb.no_devices": "Nessun telefono trovato.",
        "adb.detected": "Forge trovato: {root}",
        "adb.not_detected": "Cartella di Forge non trovata sul telefono.",
        # --- copia sul telefono ---
        "push.edition": "Edizione inviata: {name}",
        "push.no_edition": "File edizione assente, non inviato: {name}",
        "push.tokens": "Inviati {count} script di token",
        "push.cards": "Inviati {count} script di carte",
        "push.images": "Inviate {count} immagini carte in {code}",
        "push.token_images": "Inviate {count} immagini token in {code}",
        "push.done": "Set {code} copiato sul telefono.",
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
        "report.header_emblems": "Edizione {code}\n{imported} carte importate  |  {tokens} token importati  |  {emblems} emblemi importati  |  {scripts} script creati  |  {images} immagini scritte  |  {skipped} ignorate",
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
        "gen.skipped_multiface": "IGNORATA {name}: {base} e' una carta multi-faccia, usa ' // ' per indicare entrambi i nomi",
        "gen.skipped_back_only": "IGNORATA {name}: faccia posteriore di {base} senza il fronte corrispondente",
        "gen.face_pair": 'Faccia posteriore abbinata a questa immagine: "{back}".',
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
        "gen.copy_token_variant": 'Arte {index}/{total} del token copia {prefix} di {card}',
        "gen.copy_token_line": "TOKEN copia {prefix} di {card}: collector {collector}",
        "gen.emblem": "Emblema di {card}",
        "gen.emblem_line": "EMBLEMA di {card}: collector {collector}",
        "gen.skipped_emblem_base": "IGNORATO {name}: carta dell'emblema non riconosciuta",
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
