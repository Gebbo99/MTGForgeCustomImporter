"""Motore OCR basato su Google ML Kit, eseguito on-device dall'APK.

Su Android non si puo' usare RapidOCR (dipende da onnxruntime, non compilabile
per il telefono). Al suo posto si usa ML Kit Text Recognition, che e' incluso
nell'APK e funziona anche senza rete.

Il backend restituisce le righe nello stesso formato di RapidOCR, cioe' una
lista di `(box, testo, punteggio)` dove `box` sono i quattro vertici in pixel:
cosi' il resto della pipeline OCR resta identico a quello del desktop.
"""

from __future__ import annotations

_recognizer = None


def _classes() -> dict:
    """Classi Java usate, risolte solo quando servono (cosi' il modulo si
    importa anche su desktop, dove pyjnius non c'e')."""
    from jnius import autoclass

    return {
        "InputImage": autoclass("com.google.mlkit.vision.common.InputImage"),
        "TextRecognition": autoclass("com.google.mlkit.vision.text.TextRecognition"),
        "Options": autoclass(
            "com.google.mlkit.vision.text.latin.TextRecognizerOptions"
        ),
        "Tasks": autoclass("com.google.android.gms.tasks.Tasks"),
        "File": autoclass("java.io.File"),
        "Uri": autoclass("android.net.Uri"),
        "Activity": autoclass("org.kivy.android.PythonActivity"),
    }


def _get_recognizer():
    global _recognizer
    if _recognizer is None:
        classes = _classes()
        _recognizer = classes["TextRecognition"].getClient(
            classes["Options"].DEFAULT_OPTIONS
        )
    return _recognizer


def _box_of(line):
    """Vertici del riquadro come [(x, y), ...]; ripiega sul bounding box."""
    points = line.getCornerPoints()
    if points is not None:
        return [(point.x, point.y) for point in points]
    box = line.getBoundingBox()
    if box is None:
        return None
    return [
        (box.left, box.top),
        (box.right, box.top),
        (box.right, box.bottom),
        (box.left, box.bottom),
    ]


def _score_of(line) -> float:
    confidence = line.getConfidence()
    # ML Kit restituisce -1 quando il punteggio non e' disponibile.
    return float(confidence) if confidence is not None and confidence >= 0 else 1.0


def read_text(image_file: str) -> list:
    """Riconosce il testo di una immagine con ML Kit (chiamata bloccante).

    Va invocata da un thread di lavoro, non dal thread dell'interfaccia.
    """
    classes = _classes()
    activity = classes["Activity"].mActivity
    uri = classes["Uri"].fromFile(classes["File"](image_file))
    image = classes["InputImage"].fromFilePath(activity, uri)

    task = _get_recognizer().process(image)
    # `Tasks.await` e' una parola riservata in Python: va preso con getattr.
    result = getattr(classes["Tasks"], "await")(task)

    rows: list = []
    blocks = result.getTextBlocks()
    for block_index in range(blocks.size()):
        lines = blocks.get(block_index).getLines()
        for line_index in range(lines.size()):
            line = lines.get(line_index)
            text = line.getText()
            box = _box_of(line)
            if not text or box is None:
                continue
            rows.append((box, text, _score_of(line)))
    return rows
