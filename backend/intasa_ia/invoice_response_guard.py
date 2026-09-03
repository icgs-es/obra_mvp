import re


def enforce_invoice_role_safety(content, analyses):
    """Corrige una respuesta del modelo si contradice evidencia local fuerte."""
    result = str(content or "")
    for analysis in analyses:
        supplier = analysis.get("supplier_name")
        customer = analysis.get("customer_name")
        if not customer:
            continue
        if supplier and supplier.casefold() != customer.casefold():
            result = re.sub(
                r"(?im)^(\s*(?:[-*]\s*)?(?:Proveedor(?:\s*/\s*emisor)?|Emisor)\s*:\s*).*$",
                rf"\1{supplier}", result, count=1,
            )
            if analysis.get("supplier_tax_id"):
                result = re.sub(
                    r"(?im)^(\s*(?:[-*]\s*)?CIF\s+del\s+proveedor\s*:\s*).*$",
                    rf"\1{analysis['supplier_tax_id']}", result, count=1,
                )
                # No permitir que una evidencia narrativa conserve el CIF del
                # destinatario bajo el bloque del emisor.
                result = re.sub(
                    r"(?im)^\s*Evidencia:.*\bCIF\b.*$",
                    "  Evidencia: datos de cobro/contacto asociados al emisor; CIF verificado por proximidad estructural.",
                    result,
                )
                if not re.search(r"(?im)^\s*(?:[-*]\s*)?CIF\s+del\s+proveedor\s*:", result):
                    result = result.rstrip() + f"\n- CIF del proveedor: {analysis['supplier_tax_id']}"
        else:
            result = re.sub(
                r"(?im)^(\s*(?:[-*]\s*)?(?:Proveedor(?:\s*/\s*emisor)?|Emisor)\s*:\s*).*$",
                r"\1Proveedor/emisor no identificado con suficiente certeza",
                result, count=1,
            )
            result = re.sub(
                r"(?im)^\s*(?:Evidencia|Justificación)\s*:\s*.*(?:ADRI|cliente|destinatario).*$\n?",
                "", result,
            )
        customer_line = f"Cliente/destinatario: {customer}"
        if not re.search(r"(?im)^\s*(?:[-*]\s*)?Cliente(?:\s*/\s*destinatario)?\s*:", result):
            result = result.rstrip() + "\n- " + customer_line
        if analysis.get("customer_tax_id") and not re.search(r"(?im)^\s*(?:[-*]\s*)?CIF\s+del\s+cliente\s*:", result):
            result = result.rstrip() + f"\n- CIF del cliente: {analysis['customer_tax_id']}"
        if "DOCUMENTO_NO_CONFIABLE" in result:
            result = result.replace(
                "DOCUMENTO_NO_CONFIABLE",
                "contenido documental no confiable",
            ).replace("FIN_DOCUMENTO_NO_CONFIABLE", "fin del contenido documental")
    return result
