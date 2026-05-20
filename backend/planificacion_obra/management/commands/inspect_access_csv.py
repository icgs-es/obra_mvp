from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


EXPECTED_FILES = [
    "tblTareas.csv",
    "tblTareasRecursosInicial.csv",
    "tblTareasRecursos.csv",
    "tblRecursos.csv",
    "tblRecursoAlmacen.csv",
    "tblPartidas.csv",
]

ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
DELIMITERS = [";", ",", "\t", "|"]

DATE_FORMATS = [
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
]


def clean_value(value):
    if value is None:
        return ""
    return str(value).replace("\ufeff", "").strip()


def is_empty(value):
    return clean_value(value) == ""


def parse_date(value):
    value = clean_value(value)
    if not value:
        return None

    # Access a veces exporta fecha y hora con milisegundos o formatos raros.
    value = value.split(".")[0].strip()

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    return None


def looks_like_date_column(name):
    n = name.lower()
    return any(token in n for token in ["fecha", "inicio", "fin", "date"])


def looks_like_key_column(name):
    n = name.lower()
    tokens = [
        "id",
        "cod",
        "codigo",
        "clave",
        "key",
        "tarea",
        "recurso",
        "partida",
        "capitulo",
        "obra",
        "fase",
        "vivienda",
        "planta",
        "orden",
    ]
    return any(token in n for token in tokens)


def detect_encoding_and_sample(path: Path):
    for enc in ENCODINGS:
        try:
            sample = path.read_text(encoding=enc, errors="strict")[:20000]
            return enc, sample
        except UnicodeDecodeError:
            continue

    # Último recurso.
    enc = "latin-1"
    sample = path.read_text(encoding=enc, errors="replace")[:20000]
    return enc, sample


def detect_delimiter(sample):
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(DELIMITERS))
        return dialect.delimiter
    except csv.Error:
        # En Access español lo más habitual es punto y coma.
        return ";"


def find_file_case_insensitive(folder: Path, expected_name: str):
    expected_lower = expected_name.lower()
    for p in folder.iterdir():
        if p.is_file() and p.name.lower() == expected_lower:
            return p
    return None


def analyse_csv(path: Path, sample_rows_limit: int):
    encoding, sample = detect_encoding_and_sample(path)
    delimiter = detect_delimiter(sample)

    total_rows = 0
    empty_counts = Counter()
    date_ranges = {}
    key_candidates = []
    sample_rows = []
    columns = []

    with path.open("r", encoding=encoding, errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)

        columns = [clean_value(c) for c in (reader.fieldnames or [])]

        if not columns:
            return {
                "file": path.name,
                "encoding": encoding,
                "delimiter": delimiter,
                "columns": [],
                "total_rows": 0,
                "sample_rows": [],
                "empty_counts": {},
                "date_ranges": {},
                "key_candidates": [],
                "error": "Sin cabeceras detectadas",
            }

        key_candidates = [c for c in columns if looks_like_key_column(c)]
        date_columns = [c for c in columns if looks_like_date_column(c)]

        for c in date_columns:
            date_ranges[c] = {
                "min": None,
                "max": None,
                "parsed": 0,
            }

        for row in reader:
            total_rows += 1

            clean_row = {clean_value(k): clean_value(v) for k, v in row.items() if k is not None}

            if len(sample_rows) < sample_rows_limit:
                sample_rows.append(clean_row)

            for col in columns:
                value = clean_row.get(col, "")
                if is_empty(value):
                    empty_counts[col] += 1

            for col in date_columns:
                d = parse_date(clean_row.get(col, ""))
                if d:
                    info = date_ranges[col]
                    info["parsed"] += 1
                    if info["min"] is None or d < info["min"]:
                        info["min"] = d
                    if info["max"] is None or d > info["max"]:
                        info["max"] = d

    for col, info in date_ranges.items():
        info["min"] = info["min"].isoformat() if info["min"] else None
        info["max"] = info["max"].isoformat() if info["max"] else None

    return {
        "file": path.name,
        "encoding": encoding,
        "delimiter": delimiter,
        "columns": columns,
        "total_rows": total_rows,
        "sample_rows": sample_rows,
        "empty_counts": dict(empty_counts),
        "date_ranges": date_ranges,
        "key_candidates": key_candidates,
        "error": "",
    }


class Command(BaseCommand):
    help = "Inspecciona CSV exportados desde MS-Access para preparar sincronización Access -> Portal INTASA."

    def add_arguments(self, parser):
        parser.add_argument(
            "--folder",
            required=True,
            help="Carpeta que contiene los CSV exportados desde Access.",
        )
        parser.add_argument(
            "--only",
            nargs="*",
            default=None,
            help="Limita la inspección a uno o varios nombres de archivo. Ej: --only tblTareas.csv tblTareasRecursos.csv",
        )
        parser.add_argument(
            "--sample",
            type=int,
            default=3,
            help="Número de filas de muestra por archivo.",
        )
        parser.add_argument(
            "--json-out",
            default="",
            help="Ruta opcional para guardar informe JSON.",
        )

    def handle(self, *args, **options):
        folder = Path(options["folder"])

        if not folder.exists() or not folder.is_dir():
            raise CommandError(f"No existe la carpeta: {folder}")

        requested = options["only"] or EXPECTED_FILES
        sample_rows_limit = max(0, int(options["sample"] or 0))

        self.stdout.write("")
        self.stdout.write("=== ACCESS SYNC · INSPECCIÓN CSV ===")
        self.stdout.write(f"Carpeta: {folder}")
        self.stdout.write("")

        report = {
            "folder": str(folder),
            "expected_files": EXPECTED_FILES,
            "files": [],
            "missing": [],
            "extra_csv": [],
        }

        existing_csv = {p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".csv"}
        expected_lower = {x.lower() for x in EXPECTED_FILES}

        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix.lower() == ".csv" and p.name.lower() not in expected_lower:
                report["extra_csv"].append(p.name)

        for expected_name in requested:
            path = find_file_case_insensitive(folder, expected_name)

            if not path:
                report["missing"].append(expected_name)
                self.stdout.write(self.style.WARNING(f"[FALTA] {expected_name}"))
                continue

            self.stdout.write("")
            self.stdout.write(f"--- {path.name} ---")

            info = analyse_csv(path, sample_rows_limit)
            report["files"].append(info)

            self.stdout.write(f"Encoding: {info['encoding']}")
            self.stdout.write(f"Delimitador: {repr(info['delimiter'])}")
            self.stdout.write(f"Filas: {info['total_rows']}")
            self.stdout.write(f"Columnas ({len(info['columns'])}): {', '.join(info['columns'])}")

            if info["key_candidates"]:
                self.stdout.write(f"Claves candidatas: {', '.join(info['key_candidates'])}")
            else:
                self.stdout.write(self.style.WARNING("Claves candidatas: no detectadas"))

            if info["date_ranges"]:
                self.stdout.write("Rangos de fechas:")
                for col, rng in info["date_ranges"].items():
                    if rng["parsed"]:
                        self.stdout.write(f"  - {col}: {rng['min']} -> {rng['max']} ({rng['parsed']} valores)")
                    else:
                        self.stdout.write(f"  - {col}: sin fechas parseables")

            if info["sample_rows"]:
                self.stdout.write("Muestra:")
                for row in info["sample_rows"]:
                    self.stdout.write(json.dumps(row, ensure_ascii=False))

            # Mostrar columnas muy vacías para detectar problemas de exportación.
            if info["total_rows"]:
                very_empty = []
                for col, count in info["empty_counts"].items():
                    pct = (count / info["total_rows"]) * 100
                    if pct >= 95:
                        very_empty.append(f"{col} ({pct:.1f}%)")
                if very_empty:
                    self.stdout.write(self.style.WARNING("Columnas casi vacías: " + ", ".join(very_empty[:20])))

        self.stdout.write("")
        self.stdout.write("=== RESUMEN ===")
        self.stdout.write(f"Archivos esperados: {len(requested)}")
        self.stdout.write(f"Archivos analizados: {len(report['files'])}")
        self.stdout.write(f"Archivos faltantes: {len(report['missing'])}")

        if report["missing"]:
            self.stdout.write(self.style.WARNING("Faltan: " + ", ".join(report["missing"])))

        if report["extra_csv"]:
            self.stdout.write("CSV extra detectados: " + ", ".join(report["extra_csv"]))

        if options["json_out"]:
            out = Path(options["json_out"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(f"Informe JSON guardado en: {out}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("OK: inspección finalizada. No se modificó la base de datos."))
