# Buildozer: genera l'APK della versione Android di Forge Card Importer.
#
# L'APK si compila solo su Linux (Android SDK/NDK + python-for-android non
# girano su Windows): si usa quindi il workflow GitHub Actions in
# ../.github/workflows/android.yml, che sincronizza prima il core condiviso
# da ../desktop/forge_importer.
#
# Per provare in locale su Linux (dalla radice del repo):
#     python -m pip install buildozer
#     python tools/sync_core.py           (allinea android/forge_importer)
#     cd android && buildozer -v android debug

[app]

title = Forge Card Importer
package.name = forgecustomimporter
package.domain = org.forgeimporter

source.dir = .
source.include_exts = py,png,jpg,jpeg,webp,ttf,json
source.exclude_dirs = bin, .buildozer, __pycache__
source.exclude_patterns = forge_importer/__pycache__/*

version = 1.0.0

# rapidfuzz, opencv, onnxruntime e customtkinter non sono compilabili o utili
# su Android: l'OCR e' ML Kit (sotto), il fuzzy matching usa il fallback puro
# Python in forge_importer/_fuzzshim.py.
requirements = python3, kivy==2.3.0, kivymd==1.2.0, pyjnius, pillow, android

orientation = portrait
fullscreen = 0

# --- Android ---
android.api = 34
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.enable_androidx = True
android.allow_backup = True
android.release_artifact = apk

# "Accesso a tutti i file": serve per leggere e scrivere nelle cartelle di
# Forge fuori dalla sandbox dell'app (Android 11+). I permessi classici
# coprono Android 6-10.
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, MANAGE_EXTERNAL_STORAGE, READ_MEDIA_IMAGES

# ML Kit Text Recognition (modello latino incluso nell'APK, funziona offline).
android.gradle_dependencies = com.google.android.gms:play-services-mlkit-text-recognition:19.0.0

# --- python-for-android ---
p4a.branch = master
