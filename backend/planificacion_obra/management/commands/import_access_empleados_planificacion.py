from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


class Command(BaseCommand):
    help = "Importa empleados de obra desde tblPersonalObra.xlsx."

    def add_arguments(self, parser):
        parser.add_argument("base_path", type=str)
        parser.add_argument("--team-id", type=int, default=1)
        parser.add_argument("--commit", action="store_true")

    def col_letters(self, cell_ref):
        return "".join(ch for ch in cell_ref if ch.isalpha())

    def col_sort_key(self, col):
        value = 0
        for ch in col:
            value = value * 26 + (ord(ch.upper()) - ord("A") + 1)
        return value

    def read_shared_strings(self, z):
        try:
            xml = z.read("xl/sharedStrings.xml")
        except KeyError:
            return []

        root = ET.fromstring(xml)
        strings = []
        for si in root.findall("main:si", NS):
            parts = []
            for t in si.findall(".//main:t", NS):
                parts.append(t.text or "")
            strings.append("".join(parts))
        return strings

    def cell_value(self, cell, shared_strings):
        cell_type = cell.attrib.get("t")
        v = cell.find("main:v", NS)

        if v is None:
            inline = cell.find("main:is/main:t", NS)
            return inline.text if inline is not None else ""

        raw = v.text or ""

        if cell_type == "s":
            try:
                return shared_strings[int(raw)]
            except Exception:
                return raw

        return raw

    def read_rows_safe(self, path):
        with ZipFile(path) as z:
            shared_strings = self.read_shared_strings(z)

            workbook = ET.fromstring(z.read("xl/workbook.xml"))
            sheets = workbook.find("main:sheets", NS)
            first_sheet = sheets[0]

            rel_id = first_sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))

            target = None
            for rel in rels:
                if rel.attrib.get("Id") == rel_id:
                    target = rel.attrib.get("Target")
                    break

            if not target:
                raise CommandError("No se pudo localizar la hoja del Excel.")

            sheet_path = "xl/" + target.lstrip("/")
            root = ET.fromstring(z.read(sheet_path))
            rows = root.findall(".//main:sheetData/main:row", NS)

            parsed = []
            for row in rows:
                values_by_col = {}
                for c in row.findall("main:c", NS):
                    ref = c.attrib.get("r", "")
                    values_by_col[self.col_letters(ref)] = self.cell_value(c, shared_strings)
                parsed.append(values_by_col)

            if not parsed:
                return []

            header_row = parsed[0]
            ordered_cols = sorted(header_row.keys(), key=self.col_sort_key)
            headers = [str(header_row.get(c, "")).strip() for c in ordered_cols]

            result = []
            for row in parsed[1:]:
                data = {headers[i]: row.get(col, "") for i, col in enumerate(ordered_cols)}
                if any(v not in ("", None) for v in data.values()):
                    result.append(data)

            return result

    def txt(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def clean_int(self, value):
        value = self.txt(value)
        if not value:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def clean_decimal(self, value):
        value = self.txt(value)
        if not value:
            return None
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError, TypeError):
            return None

    def clean_date(self, value):
        value = self.txt(value)
        if not value:
            return None

        # Excel serial date.
        try:
            numeric = float(value)
            if numeric > 20000:
                return date(1899, 12, 30) + timedelta(days=int(numeric))
        except ValueError:
            pass

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

        return None

    def map_tipo(self, tipo, subcontrata):
        tipo_txt = self.txt(tipo).upper()
        subcontrata_txt = self.txt(subcontrata)

        if subcontrata_txt in ("1", "-1", "true", "True", "SI", "SÍ"):
            return "CONTRATADO"

        if "CONT" in tipo_txt or "SUB" in tipo_txt:
            return "CONTRATADO"

        return "ADMINISTRADA"

    def map_categoria(self, cargo):
        cargo = self.txt(cargo).upper()

        if "JEFE" in cargo:
            return "JEFE_OBRA"
        if "ENCARG" in cargo:
            return "ENCARGADO"
        if "OFICIAL 1" in cargo or "OFICIAL 1ª" in cargo or "OFICIAL PRIMERA" in cargo:
            return "OFICIAL_1"
        if "OFICIAL 2" in cargo or "OFICIAL 2ª" in cargo or "OFICIAL SEGUNDA" in cargo:
            return "OFICIAL_2"
        if "PEON" in cargo or "PEÓN" in cargo:
            return "PEON"

        return "OTRO"

    def map_situacion(self, estado):
        estado = self.txt(estado).upper()

        if "VAC" in estado:
            return "VACACIONES"
        if "BAJA" in estado:
            return "BAJA"

        return "ACTIVO"

    def build_observaciones(self, row):
        parts = []

        cargo = self.txt(row.get("CARGO"))
        oficio = self.txt(row.get("OFICIO"))
        equipo = self.txt(row.get("Equipo"))
        horas = self.txt(row.get("Horasxdia"))

        if cargo:
            parts.append(f"Cargo: {cargo}")
        if oficio:
            parts.append(f"Oficio: {oficio}")
        if equipo:
            parts.append(f"Equipo: {equipo}")
        if horas:
            parts.append(f"Horas/día: {horas}")

        return " | ".join(parts)[:256]

    def handle(self, *args, **options):
        base_path = Path(options["base_path"])
        team_id = options["team_id"]
        commit = options["commit"]

        empleados_file = base_path / "tblPersonalObra.xlsx"
        if not empleados_file.exists():
            raise CommandError(f"No existe: {empleados_file}")

        Team = apps.get_model("usuarios", "Team")
        EmpleadoObra = apps.get_model("planificacion_obra", "EmpleadoObra")

        team = Team.objects.filter(id=team_id).first()
        if not team:
            raise CommandError(f"No existe Team con id={team_id}")

        modo = "COMMIT REAL" if commit else "SIMULACION"
        self.stdout.write(self.style.WARNING(f"Modo: {modo}"))
        self.stdout.write(f"Team destino: {team.id} · {team.name}")
        self.stdout.write("CodObra será ignorado como relación estructural.")

        rows = self.read_rows_safe(empleados_file)

        crear = actualizar = sin_cambios = sin_id = sin_nombre = 0

        with transaction.atomic():
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=== EMPLEADOS OBRA ==="))

            for row in rows:
                legacy_id = self.clean_int(row.get("IdPersonal"))
                nombre = self.txt(row.get("NOMBRE"))

                if legacy_id is None:
                    sin_id += 1
                    continue

                if not nombre:
                    sin_nombre += 1
                    continue

                empresa = self.txt(row.get("EMPRESA")) or self.txt(row.get("EMPRESA_OLD"))

                obj = EmpleadoObra.objects.filter(
                    team=team,
                    legacy_id=legacy_id,
                ).first()

                defaults = {
                    "nombre": nombre,
                    "tipo": self.map_tipo(row.get("Tipo"), row.get("SUBCONTRATA")),
                    "categoria": self.map_categoria(row.get("CARGO")),
                    "situacion": self.map_situacion(row.get("ESTADO")),
                    "fecha_alta": self.clean_date(row.get("Altadesde")),
                    "fecha_baja": self.clean_date(row.get("Bajadesde")),
                    "precio_hora": self.clean_decimal(row.get("PRECIO_HORA")),
                    "empresa_origen": empresa,
                    "observaciones": self.build_observaciones(row),
                    "raw_data": row,
                }

                if obj is None:
                    crear += 1
                    if crear <= 40:
                        self.stdout.write(f"CREAR Empleado {legacy_id} => {nombre} · {defaults['categoria']} · {defaults['situacion']}")
                    EmpleadoObra.objects.create(
                        team=team,
                        legacy_id=legacy_id,
                        **defaults,
                    )
                else:
                    changed = any(getattr(obj, k) != v for k, v in defaults.items())
                    if changed:
                        actualizar += 1
                        if actualizar <= 40:
                            self.stdout.write(f"ACTUALIZAR Empleado {legacy_id} => {nombre}")
                        for k, v in defaults.items():
                            setattr(obj, k, v)
                        obj.save()
                    else:
                        sin_cambios += 1

            if not commit:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== RESUMEN EMPLEADOS ==="))
        self.stdout.write(f"Filas leídas: {len(rows)}")
        self.stdout.write(f"Crear: {crear}")
        self.stdout.write(f"Actualizar: {actualizar}")
        self.stdout.write(f"Sin cambios: {sin_cambios}")
        self.stdout.write(f"Sin IdPersonal: {sin_id}")
        self.stdout.write(f"Sin nombre: {sin_nombre}")

        if not commit:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("SIMULACION: no se ha guardado nada."))
        else:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("IMPORTACION APLICADA."))
