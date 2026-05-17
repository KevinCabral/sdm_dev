"""One-shot importer for the eleitores_postos.csv file.

Run with:
    source venv/bin/activate
    python manage.py shell < import_eleitores_postos_once.py

CSV expected headers (semicolon-separated):
    Concelho;Código Posto;Posto;Mesa;No Inscritos;Número Eleitor;
    Nome Completo;Filiação;Data Nasc

Mapping:
    Concelho        -> concelho
    Posto           -> zona
    Mesa            -> nr_mesa        (rows with empty Mesa are skipped)
    Número Eleitor  -> nr_eleitor
    Nome Completo   -> nome
    Filiação        -> filiacao
    Data Nasc       -> data_nascimento  (also auto-fills idade_eleitor)
    Código Posto    -> (ignored)
    No Inscritos    -> (ignored)

Throwaway script. Delete after the import is done.
"""

import csv
from datetime import date, datetime

from apps.eleitores.models import Eleitores


CSV_PATH = "/home/mpd_admin/sdm_dev/SAL.csv"


# ----- helpers ---------------------------------------------------------

def s(v):
    """Strip; treat empty string as None."""
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def i(v):
    """Coerce to int; None on blank/invalid."""
    v = s(v)
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def d(v):
    """Parse a date string; None on blank/invalid."""
    v = s(v)
    if v is None:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def age_from(dob):
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ----- main ------------------------------------------------------------

print(f"Reading {CSV_PATH} ...")

# Pre-load existing keys for fast dedupe.
existing_keys = set(
    Eleitores.objects
    .exclude(nr_mesa__isnull=True)
    .exclude(nr_eleitor__isnull=True)
    .values_list("nr_mesa", "nr_eleitor")
)
print(f"Existing (nr_mesa, nr_eleitor) keys in DB: {len(existing_keys)}")

created = 0
skipped_no_mesa = 0
duplicates = 0
errors = 0
seen_in_file = set()
batch = []
BATCH_SIZE = 500

with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as fh:
    reader = csv.DictReader(fh, delimiter=";")
    for lineno, row in enumerate(reader, start=2):
        try:
            nr_mesa = s(row.get("Mesa"))
            if not nr_mesa:
                skipped_no_mesa += 1
                continue

            dob = d(row.get("Data Nasc"))
            nr_eleitor = i(row.get("Número Eleitor"))

            key = (nr_mesa, nr_eleitor) if nr_eleitor is not None else None
            if key is not None:
                if key in seen_in_file or key in existing_keys:
                    duplicates += 1
                    continue
                seen_in_file.add(key)

            obj = Eleitores(
                nome=s(row.get("Nome Completo")),
                filiacao=s(row.get("Filiação")),
                data_nascimento=dob,
                idade_eleitor=age_from(dob),
                concelho=s(row.get("Concelho")),
                zona=s(row.get("Posto")),
                nr_mesa=nr_mesa,
                nr_eleitor=nr_eleitor,
                falecido=False,
            )
            batch.append(obj)

            if len(batch) >= BATCH_SIZE:
                Eleitores.objects.bulk_create(batch, batch_size=BATCH_SIZE)
                created += len(batch)
                batch = []
                print(f"  ... line {lineno}: created so far = {created}")
        except Exception as exc:  # noqa: BLE001
            errors += 1
            if errors <= 10:
                print(f"  ERROR line {lineno}: {exc}")

# Flush remaining batch
if batch:
    Eleitores.objects.bulk_create(batch, batch_size=BATCH_SIZE)
    created += len(batch)

print()
print("=" * 60)
print("Import finished")
print("=" * 60)
print(f"Created          : {created}")
print(f"Skipped (no Mesa): {skipped_no_mesa}")
print(f"Duplicates       : {duplicates}")
print(f"Errors           : {errors}")
