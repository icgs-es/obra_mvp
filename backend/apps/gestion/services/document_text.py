"""
PORTAL INTASA
DOCUMENT_TEXT_CANONICAL_V1

Capa común de adquisición de texto documental.

PDF digital:
    pdftotext -layout

PDF escaneado:
    OCR existente si tiene calidad estructural suficiente
    o rasterización pdftoppm + Tesseract como recuperación.

No contiene lógica de proveedores.
"""

# DOCUMENT_TEXT_CANONICAL_V1

from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def _text_quality_v1(text):
    raw = str(text or "")
    upper = raw.upper()

    anchors = (
        "FACTURA",
        "ALBAR",
        "FECHA",
        "TOTAL",
        "BASE",
        "IVA",
        "CANTIDAD",
        "PRECIO",
        "IMPORTE",
        "DESCRIP",
        "CLIENTE",
        "PROVEEDOR",
        "BRUTO",
        "DESCUENTO",
    )

    hits = sum(
        1
        for token in anchors
        if token in upper
    )

    money = len(
        re.findall(
            r"\d+[.,]\d{2,4}",
            raw,
        )
    )

    rows = len(
        [
            line
            for line in raw.splitlines()
            if line.strip()
        ]
    )

    return (
        min(len(raw), 12000)
        + hits * 250
        + min(money, 100) * 12
        + min(rows, 200) * 3
    )


def _structured_enough_v1(text):
    raw = str(text or "")

    if len(raw.strip()) < 400:
        return False

    upper = raw.upper()

    anchors = (
        "TOTAL",
        "IVA",
        "PRECIO",
        "IMPORTE",
        "CANTIDAD",
        "BASE",
        "BRUTO",
        "DESCRIP",
    )

    return sum(
        1
        for token in anchors
        if token in upper
    ) >= 4


def _pdftotext_layout_v1(
    pdf_path,
    max_pages=3,
):
    exe = shutil.which("pdftotext")

    if not exe:
        return ""

    try:
        proc = subprocess.run(
            [
                exe,
                "-layout",
                "-f",
                "1",
                "-l",
                str(max(1, int(max_pages or 3))),
                str(pdf_path),
                "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except Exception:
        return ""

    if proc.returncode != 0:
        return ""

    return proc.stdout or ""


def _tesseract_language_v1():
    exe = shutil.which("tesseract")

    if not exe:
        return ""

    try:
        proc = subprocess.run(
            [exe, "--list-langs"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )

        langs = {
            line.strip()
            for line in proc.stdout.splitlines()
            if line.strip()
        }

    except Exception:
        langs = set()

    if "spa" in langs and "eng" in langs:
        return "spa+eng"

    if "spa" in langs:
        return "spa"

    if "eng" in langs:
        return "eng"

    return ""


def _scan_ocr_v1(
    pdf_path,
    max_pages=3,
):
    pdftoppm = shutil.which("pdftoppm")
    tesseract = shutil.which("tesseract")

    if not pdftoppm or not tesseract:
        return {
            "text": "",
            "method": "",
            "error": "pdftoppm/tesseract no disponible",
        }

    lang = _tesseract_language_v1()

    if not lang:
        return {
            "text": "",
            "method": "",
            "error": "No hay idioma OCR utilizable",
        }

    with tempfile.TemporaryDirectory(
        prefix="portal_document_ocr_v1_"
    ) as tmp:

        tmp = Path(tmp)
        output = tmp / "page"

        try:
            render = subprocess.run(
                [
                    pdftoppm,
                    "-f",
                    "1",
                    "-l",
                    str(max(1, int(max_pages or 3))),
                    "-r",
                    "300",
                    "-png",
                    str(pdf_path),
                    str(output),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
        except Exception as exc:
            return {
                "text": "",
                "method": "",
                "error": f"pdftoppm: {type(exc).__name__}: {exc}",
            }

        if render.returncode != 0:
            return {
                "text": "",
                "method": "",
                "error": (
                    render.stderr.decode(
                        errors="ignore"
                    )[:500]
                ),
            }

        pages = sorted(
            tmp.glob("page-*.png"),
            key=lambda p: p.name,
        )

        if not pages:
            one = tmp / "page.png"

            if one.exists():
                pages = [one]

        chunks = []
        errors = []

        for page in pages:

            try:
                proc = subprocess.run(
                    [
                        tesseract,
                        str(page),
                        "stdout",
                        "-l",
                        lang,
                        "--psm",
                        "6",
                        "-c",
                        "preserve_interword_spaces=1",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                    check=False,
                )

                if proc.returncode == 0:
                    chunks.append(
                        proc.stdout or ""
                    )
                else:
                    errors.append(
                        proc.stderr[:300]
                    )

            except Exception as exc:
                errors.append(
                    f"{type(exc).__name__}: {exc}"
                )

        return {
            "text": "\n".join(chunks),
            "method": "pdftoppm_300_tesseract_psm6",
            "error": " | ".join(errors),
        }


def extract_document_text_v1(
    pdf_path,
    *,
    legacy_result=None,
    max_pages=3,
):
    """
    Selecciona la mejor representación textual sin alterar
    el extractor legacy.

    La función es independiente del proveedor.
    """

    pdf_path = Path(pdf_path)

    if legacy_result is None:
        from apps.gestion.services.pdf_extractor import (
            extract_pdf_text,
        )

        legacy_result = extract_pdf_text(
            str(pdf_path),
            max_pages=max_pages,
        )

    if not isinstance(legacy_result, dict):
        legacy_result = {}

    legacy_text = str(
        legacy_result.get("text")
        or ""
    )

    legacy_method = str(
        legacy_result.get("method")
        or ""
    )

    legacy_ocr = bool(
        legacy_result.get("ocr_used")
    )

    candidates = []

    if legacy_text.strip():
        candidates.append({
            "method": (
                "legacy_ocr"
                if legacy_ocr
                else "legacy_text"
            ),
            "text": legacy_text,
            "ocr_used": legacy_ocr,
            "score": _text_quality_v1(
                legacy_text
            ),
            "error": "",
        })

    # Documento digital: el layout de Poppler tiene prioridad.
    if not legacy_ocr:
        layout = _pdftotext_layout_v1(
            pdf_path,
            max_pages=max_pages,
        )

        if layout.strip():
            candidates.append({
                "method": "pdftotext_layout",
                "text": layout,
                "ocr_used": False,
                "score": _text_quality_v1(
                    layout
                ),
                "error": "",
            })

    # Escaneado con OCR poco estructurado:
    # recuperación genérica con Tesseract.
    if (
        legacy_ocr
        and not _structured_enough_v1(
            legacy_text
        )
    ):
        enhanced = _scan_ocr_v1(
            pdf_path,
            max_pages=max_pages,
        )

        if enhanced.get("text", "").strip():
            candidates.append({
                "method": enhanced["method"],
                "text": enhanced["text"],
                "ocr_used": True,
                "score": _text_quality_v1(
                    enhanced["text"]
                ),
                "error": enhanced.get(
                    "error",
                    "",
                ),
            })

    if not candidates:
        return {
            "ok": False,
            "exists": pdf_path.exists(),
            "text": legacy_text,
            "method": legacy_method,
            "ocr_used": legacy_ocr,
            "pages": legacy_result.get(
                "pages",
                0,
            ),
            "page_lengths": legacy_result.get(
                "page_lengths",
                [],
            ),
            "direct_text_len": legacy_result.get(
                "direct_text_len",
                0,
            ),
            "error": (
                legacy_result.get("error")
                or "Sin texto utilizable"
            ),
            "canonical_v1": True,
            "candidate_scores": [],
        }

    best = max(
        candidates,
        key=lambda item: item["score"],
    )

    return {
        "ok": True,
        "exists": pdf_path.exists(),
        "text": best["text"],
        "method": (
            "canonical_"
            + best["method"]
        ),
        "ocr_used": best["ocr_used"],
        "pages": legacy_result.get(
            "pages",
            0,
        ),
        "page_lengths": legacy_result.get(
            "page_lengths",
            [],
        ),
        "direct_text_len": legacy_result.get(
            "direct_text_len",
            0,
        ),
        "error": best.get("error", ""),
        "canonical_v1": True,
        "candidate_scores": [
            {
                "method": item["method"],
                "score": item["score"],
                "length": len(
                    item["text"]
                ),
            }
            for item in candidates
        ],
    }
