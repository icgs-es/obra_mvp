"""Análisis neutral y conservador de partes de una factura.

No identifica un proveedor por posición textual. Devuelve candidatos y evidencia
para que el modelo no convierta automáticamente al destinatario en emisor.
"""
from __future__ import annotations

import re


COMPANY_RE = re.compile(
    r"(?im)^\s*([A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9 .,&'/-]{3,}(?:S\.?L\.?|S\.?A\.?|S\.?L\.U\.?|COOP\.?)\s*)$"
)
CIF_RE = re.compile(r"\b[ABCDEFGHJNPQRSUVW]\d{7,8}\b", re.I)
DATE_RE = re.compile(r"\b([0-3]?\d/[01]?\d/(?:20)?\d{2})\b")
INVOICE_RE = re.compile(r"\b(?!3314\b)\d{1,8}/20\d{2}\b")
MONEY_RE = re.compile(r"\b\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\b")


def _norm(value):
    return " ".join(str(value or "").split())


def _company_candidates(lines):
    results = []
    for index, line in enumerate(lines):
        match = COMPANY_RE.match(line)
        if not match:
            continue
        name = _norm(match.group(1)).strip()
        if not name or any(item["name"].casefold() == name.casefold() for item in results):
            continue
        nearby = " ".join(lines[max(0, index - 2): min(len(lines), index + 5)])
        cif_matches = []
        for line_index in range(max(0, index - 8), min(len(lines), index + 9)):
            match_cif = CIF_RE.search(lines[line_index])
            if match_cif:
                cif_matches.append((abs(line_index - index), 0 if line_index >= index else 1, match_cif.group(0).upper()))
        cif = min(cif_matches, default=(0, 0, None), key=lambda item: (item[0], item[1]))[2]
        results.append({
            "name": name,
            "line": index,
            "tax_id": cif,
            "nearby": nearby[:500],
            "supplier_score": 0,
            "customer_score": 0,
            "evidence": [],
        })
    return results


def analyze_invoice_text(text):
    lines = [_norm(line) for line in str(text or "").splitlines() if _norm(line)]
    candidates = _company_candidates(lines)
    lower = " ".join(lines).casefold()
    email_domains = re.findall(r"[\w.+-]+@([\w.-]+)", lower)
    for candidate in candidates:
        nearby = candidate["nearby"].casefold()
        compact_candidate = re.sub(r"[^a-z0-9]", "", candidate["name"].casefold())
        # Los dominios suelen omitir la forma societaria (p.ej. ``s.l.``).
        name_core = re.sub(r"\s+s\.?l\.?u?\.?$|\s+s\.?a\.?$|\s+coop\.?$", "", candidate["name"].casefold()).strip()
        compact_core = re.sub(r"[^a-z0-9]", "", name_core)
        if any((compact_candidate or compact_core) and (compact_candidate in re.sub(r"[^a-z0-9]", "", domain) or compact_core in re.sub(r"[^a-z0-9]", "", domain)) for domain in email_domains):
            candidate["supplier_score"] += 8
            candidate["evidence"].append("dominio de contacto coincide con la razón social")
        if any(token in nearby for token in ("iban", "cuenta", "banco", "transfer", "email", "@")):
            candidate["supplier_score"] += 5
            candidate["evidence"].append("datos de cobro/contacto junto a la entidad")
        if any(token in nearby for token in ("cliente", "facturar a", "destinatario", "comprador")):
            candidate["customer_score"] += 5
            candidate["evidence"].append("etiqueta de destinatario cercana")
        if any(token in nearby for token in ("emisor", "proveedor", "vendedor")):
            candidate["supplier_score"] += 5
            candidate["evidence"].append("etiqueta de emisor cercana")

    # Si una entidad tiene evidencia fuerte de cobro y solo hay otra entidad,
    # la segunda se presenta como cliente, nunca como proveedor por visibilidad.
    strong_suppliers = [item for item in candidates if item["supplier_score"] >= 4]
    if len(strong_suppliers) == 1 and len(candidates) == 2:
        supplier = strong_suppliers[0]
        for candidate in candidates:
            if candidate is not supplier:
                candidate["customer_score"] += 2
                candidate["evidence"].append("entidad restante frente a emisor con datos de cobro")

    supplier = max(candidates, key=lambda item: item["supplier_score"], default=None)
    customer = max(candidates, key=lambda item: item["customer_score"], default=None)
    if not supplier or supplier["supplier_score"] < 4:
        supplier = None
    if not customer or customer["customer_score"] < 2 or (supplier and customer["name"] == supplier["name"]):
        customer = next((item for item in candidates if not supplier or item["name"] != supplier["name"]), None)
    analysis = {
        "document_type": "invoice" if any(token in lower for token in ("factura", "total factura")) else "unknown",
        "supplier_name": supplier["name"] if supplier else None,
        "supplier_tax_id": supplier["tax_id"] if supplier else None,
        "supplier_address": None,
        "customer_name": customer["name"] if customer else None,
        "customer_tax_id": customer["tax_id"] if customer else None,
        "customer_address": None,
        "invoice_number": (INVOICE_RE.search(" ".join(lines)) or [None])[0],
        "invoice_date": (DATE_RE.search(" ".join(lines)) or [None])[0],
        "taxable_base": None,
        "vat_rate": None,
        "vat_amount": None,
        "withholding": None,
        "total": None,
        "currency": "EUR" if "EUR" in text.upper() else None,
        "confidence": {
            "supplier_name": "high" if supplier and supplier["supplier_score"] >= 5 else "unknown",
            "customer_name": "medium" if customer else "unknown",
        },
        "evidence": {
            "supplier": supplier["evidence"] if supplier else [],
            "customer": customer["evidence"] if customer else [],
        },
        "warnings": [],
    }
    amounts = [float(value.replace(".", "").replace(",", ".")) for value in MONEY_RE.findall(text)]
    if amounts:
        total = max(amounts)
        base_candidates = [value for value in amounts if total * 0.5 <= value < total]
        analysis["total"] = total
        analysis["taxable_base"] = base_candidates[0] if base_candidates else None
        if analysis["taxable_base"] is not None:
            vat = round(total - analysis["taxable_base"], 2)
            analysis["vat_amount"] = vat
            analysis["vat_rate"] = round(vat / analysis["taxable_base"] * 100, 2) if analysis["taxable_base"] else None
    if not analysis["supplier_name"]:
        analysis["warnings"].append("Proveedor/emisor no identificado con suficiente certeza")
    return analysis
