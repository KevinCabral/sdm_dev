"""Territorio app — Circulo / Concelho / Zona hierarchy and CSV importer.

Provides:
  * GET  /territorio/circulos/search       (Select2)
  * GET  /territorio/concelhos/search      (Select2; ?circulo=)
  * GET  /territorio/zonas/search          (Select2; ?concelho=)
  * POST /territorio/import/preview        (file upload → counts + sample)
  * POST /territorio/import/execute        (file upload + mode → applies)
"""
import io
import unicodedata

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .models import Circulo, Concelho, Zona
# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _norm(s):
    """Case- and accent-insensitive normalization for name matching."""
    if s is None:
        return ""
    s = str(s).strip()
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def _coerce_int(v):
    if v is None:
        return None
    try:
        s = str(v).strip()
        if not s or s.lower() in ("nan", "none", "null"):
            return None
        if s.endswith(".0"):
            s = s[:-2]
        return int(s)
    except (TypeError, ValueError):
        return None


def _coerce_bool(v, default=True):
    if v is None:
        return default
    s = str(v).strip().lower()
    if not s:
        return default
    if s in ("sim", "s", "true", "1", "x", "✓", "yes", "y"):
        return True
    if s in ("nao", "não", "n", "false", "0", "no"):
        return False
    return default


def _read_csv(file_obj):
    """Read territorio.csv (semicolon-separated, Tipo;Nome;Codigo;...)."""
    raw = file_obj.read()
    last_err = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError as e:
            last_err = e
    else:
        raise last_err
    df = pd.read_csv(io.StringIO(text), sep=";", dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    return df


def _required_cols_present(df):
    needed = {"Tipo", "Nome"}
    return needed.issubset(set(df.columns))


# ──────────────────────────────────────────────────────────────────────
# Plan builder — single pass over the CSV → in-memory plan
# ──────────────────────────────────────────────────────────────────────
def _build_plan(df, mode="update"):
    """Return a plan dict describing what would be created/updated/skipped.

    mode ∈ {"skip", "update", "overwrite"} controls how existing rows are
    treated. New rows are always created.
    """
    plan = {
        "mode": mode,
        "circulos":  {"create": [], "update": [], "skip": []},
        "concelhos": {"create": [], "update": [], "skip": []},
        "zonas":     {"create": [], "update": [], "skip": []},
        "mesas":     {"create": [], "update": [], "skip": []},
        "mesas_in_csv": 0,
        "errors": [],
    }

    # Existing rows indexed by normalized name(s)
    existing_circulos = {_norm(c.nome): c for c in Circulo.objects.all()}
    existing_concelhos = {
        (_norm(c.nome), c.circulo_id): c for c in Concelho.objects.all()
    }
    existing_zonas = {
        (_norm(z.nome), z.concelho_id): z for z in Zona.objects.all()
    }
    # Local import to avoid circular dependency at module load
    from apps.mesa.models import Mesa
    existing_mesas = {_norm(m.nr_mesa): m for m in Mesa.objects.all()}

    # Track in-memory creations so subsequent rows can resolve parents
    # without hitting the DB again.
    pending_circulos = {}   # norm(nome) -> dict
    pending_concelhos = {}  # (norm(nome), circulo_norm) -> dict
    pending_zonas = {}      # (norm(nome), concelho_norm, circulo_norm) -> dict

    # ── Pass 1: Circulos ──────────────────────────────────────────────
    for idx, row in df.iterrows():
        if (row.get("Tipo") or "").strip().lower() != "circulo":
            continue
        nome = (row.get("Nome") or "").strip()
        if not nome:
            plan["errors"].append({"row": idx + 2, "reason": "Círculo sem nome"})
            continue
        key = _norm(nome)
        new_data = {
            "nome": nome,
            "codigo": (row.get("Codigo") or "").strip() or None,
            "ativo": _coerce_bool(row.get("Ativo")),
            "meta": _coerce_int(row.get("Meta")),
        }
        if key in existing_circulos:
            existing = existing_circulos[key]
            changes = _diff_circulo(existing, new_data)
            if not changes or mode == "skip":
                plan["circulos"]["skip"].append({"nome": nome, "id": existing.id})
            else:
                plan["circulos"]["update"].append({
                    "nome": nome, "id": existing.id, "changes": changes,
                })
        else:
            plan["circulos"]["create"].append(new_data)
            pending_circulos[key] = new_data

    # Lookup: circulo norm-name → id (for resolved Concelhos)
    def _circulo_lookup(norm_key):
        if norm_key in existing_circulos:
            return existing_circulos[norm_key].id
        return None  # will be created in execute → linked by name later

    # ── Pass 2: Concelhos ─────────────────────────────────────────────
    for idx, row in df.iterrows():
        if (row.get("Tipo") or "").strip().lower() != "concelho":
            continue
        nome = (row.get("Nome") or "").strip()
        circulo_nome = (row.get("Circulo") or "").strip()
        if not nome:
            plan["errors"].append({"row": idx + 2, "reason": "Concelho sem nome"})
            continue
        circulo_key = _norm(circulo_nome)
        circulo_id = _circulo_lookup(circulo_key)
        if circulo_nome and circulo_key not in existing_circulos and circulo_key not in pending_circulos:
            plan["errors"].append({
                "row": idx + 2,
                "reason": f"Concelho '{nome}' refere círculo desconhecido '{circulo_nome}'",
            })

        new_data = {
            "nome": nome,
            "codigo": (row.get("Codigo") or "").strip() or None,
            "circulo_nome": circulo_nome or None,
            "ativo": _coerce_bool(row.get("Ativo")),
            "meta": _coerce_int(row.get("Meta")),
        }
        ekey = (_norm(nome), circulo_id)
        if ekey in existing_concelhos:
            existing = existing_concelhos[ekey]
            changes = _diff_concelho(existing, new_data)
            if not changes or mode == "skip":
                plan["concelhos"]["skip"].append({"nome": nome, "id": existing.id})
            else:
                plan["concelhos"]["update"].append({
                    "nome": nome, "id": existing.id, "changes": changes,
                })
        else:
            plan["concelhos"]["create"].append(new_data)
            pending_concelhos[(_norm(nome), circulo_key)] = new_data

    # Concelho lookup combining existing+pending
    def _concelho_lookup(concelho_norm, circulo_hint_norm=None):
        # Try to match existing concelho — prefer one whose circulo matches the hint
        matches = [c for k, c in existing_concelhos.items() if k[0] == concelho_norm]
        if circulo_hint_norm:
            for c in matches:
                if c.circulo_id and _norm(c.circulo.nome) == circulo_hint_norm:
                    return c.id
        if len(matches) == 1:
            return matches[0].id
        return None

    # ── Pass 3: Zonas ─────────────────────────────────────────────────
    for idx, row in df.iterrows():
        if (row.get("Tipo") or "").strip().lower() != "zona":
            continue
        nome = (row.get("Nome") or "").strip()
        concelho_nome = (row.get("Concelho") or "").strip()
        if not nome:
            plan["errors"].append({"row": idx + 2, "reason": "Zona sem nome"})
            continue
        concelho_key = _norm(concelho_nome)
        concelho_id = _concelho_lookup(concelho_key)
        if concelho_nome and concelho_id is None and (concelho_key, _norm(row.get("Circulo") or "")) not in pending_concelhos:
            # Search pending_concelhos by name only as a fallback
            pending_match = [k for k in pending_concelhos if k[0] == concelho_key]
            if not pending_match:
                plan["errors"].append({
                    "row": idx + 2,
                    "reason": f"Zona '{nome}' refere concelho desconhecido '{concelho_nome}'",
                })

        new_data = {
            "nome": nome,
            "codigo": (row.get("Codigo") or "").strip() or None,
            "concelho_nome": concelho_nome or None,
            "ativo": _coerce_bool(row.get("Ativo")),
            "meta": _coerce_int(row.get("Meta")),
        }
        ekey = (_norm(nome), concelho_id)
        if concelho_id and ekey in existing_zonas:
            existing = existing_zonas[ekey]
            changes = _diff_zona(existing, new_data)
            if not changes or mode == "skip":
                plan["zonas"]["skip"].append({"nome": nome, "id": existing.id})
            else:
                plan["zonas"]["update"].append({
                    "nome": nome, "id": existing.id, "changes": changes,
                })
        else:
            plan["zonas"]["create"].append(new_data)
            pending_zonas[(_norm(nome), concelho_key, _norm(row.get("Circulo") or ""))] = new_data

    # ── Pass 4: Count Mesa rows (handled by mesa app) ─────────────────
    for idx, row in df.iterrows():
        if (row.get("Tipo") or "").strip().lower() != "mesa":
            continue
        plan["mesas_in_csv"] += 1
        nr_mesa = (row.get("Nome") or "").strip()
        if not nr_mesa:
            plan["errors"].append({"row": idx + 2, "reason": "Mesa sem número (Nome)"})
            continue
        zona_nome = (row.get("Zona") or "").strip()
        concelho_nome = (row.get("Concelho") or "").strip()
        circulo_nome = (row.get("Circulo") or "").strip()

        # Resolve concelho id (existing only — pending concelhos have no id yet)
        concelho_id = None
        if concelho_nome:
            ckey = _norm(concelho_nome)
            cir_key = _norm(circulo_nome) if circulo_nome else None
            matches = [c for k, c in existing_concelhos.items() if k[0] == ckey]
            if cir_key:
                pref = [c for c in matches if c.circulo_id and _norm(c.circulo.nome) == cir_key]
                if pref:
                    matches = pref
            if len(matches) >= 1:
                concelho_id = matches[0].id

        zona_id = None
        if zona_nome:
            zkey = _norm(zona_nome)
            zmatches = [z for k, z in existing_zonas.items() if k[0] == zkey]
            if concelho_id:
                pref = [z for z in zmatches if z.concelho_id == concelho_id]
                if pref:
                    zmatches = pref
            if len(zmatches) >= 1:
                zona_id = zmatches[0].id

        new_data = {
            "nr_mesa": nr_mesa,
            "concelho_nome": concelho_nome or None,
            "circulo_nome": circulo_nome or None,
            "zona_nome": zona_nome or None,
        }

        existing_mesa = existing_mesas.get(_norm(nr_mesa))
        if existing_mesa:
            changed = False
            if zona_id and existing_mesa.zona_id != zona_id:
                changed = True
            if concelho_id and existing_mesa.concelho_id != concelho_id:
                changed = True
            if not changed or mode == "skip":
                plan["mesas"]["skip"].append({"nr_mesa": nr_mesa, "id": existing_mesa.id})
            else:
                plan["mesas"]["update"].append({
                    "nr_mesa": nr_mesa, "id": existing_mesa.id,
                    "concelho_id": concelho_id, "zona_id": zona_id,
                })
        else:
            plan["mesas"]["create"].append(new_data)

    return plan


def _diff_circulo(existing, new_data):
    diff = {}
    if (existing.codigo or "") != (new_data["codigo"] or ""):
        diff["codigo"] = (existing.codigo, new_data["codigo"])
    if existing.ativo != new_data["ativo"]:
        diff["ativo"] = (existing.ativo, new_data["ativo"])
    if existing.meta != new_data["meta"]:
        diff["meta"] = (existing.meta, new_data["meta"])
    return diff


def _diff_concelho(existing, new_data):
    diff = _diff_circulo(existing, new_data)
    new_circ = (new_data.get("circulo_nome") or "").strip()
    cur_circ = existing.circulo.nome if existing.circulo else ""
    if _norm(new_circ) and _norm(cur_circ) != _norm(new_circ):
        diff["circulo"] = (cur_circ or None, new_circ)
    return diff


def _diff_zona(existing, new_data):
    diff = _diff_circulo(existing, new_data)
    new_conc = (new_data.get("concelho_nome") or "").strip()
    cur_conc = existing.concelho.nome if existing.concelho else ""
    if _norm(new_conc) and _norm(cur_conc) != _norm(new_conc):
        diff["concelho"] = (cur_conc or None, new_conc)
    return diff


# ──────────────────────────────────────────────────────────────────────
# Plan summary (counts only — safe to send to client)
# ──────────────────────────────────────────────────────────────────────
def _summary(plan):
    return {
        "mode": plan["mode"],
        "circulos":  {k: len(v) for k, v in plan["circulos"].items()},
        "concelhos": {k: len(v) for k, v in plan["concelhos"].items()},
        "zonas":     {k: len(v) for k, v in plan["zonas"].items()},
        "mesas":     {k: len(v) for k, v in plan["mesas"].items()},
        "mesas_in_csv": plan["mesas_in_csv"],
        "errors": plan["errors"][:50],
        "errors_total": len(plan["errors"]),
        "sample": {
            "circulos_create":  plan["circulos"]["create"][:5],
            "concelhos_create": plan["concelhos"]["create"][:5],
            "zonas_create":     plan["zonas"]["create"][:5],
            "mesas_create":     plan["mesas"]["create"][:5],
            "circulos_update":  plan["circulos"]["update"][:5],
            "concelhos_update": plan["concelhos"]["update"][:5],
            "zonas_update":     plan["zonas"]["update"][:5],
            "mesas_update":     plan["mesas"]["update"][:5],
        },
    }


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────
@login_required
@require_POST
def import_preview(request):
    f = request.FILES.get("arquivo")
    if not f:
        return JsonResponse({"ok": False, "error": "Ficheiro não enviado"}, status=400)
    mode = (request.POST.get("mode") or "update").lower()
    if mode not in ("skip", "update", "overwrite"):
        mode = "update"
    try:
        df = _read_csv(f)
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Erro ao ler CSV: {e}"}, status=400)
    if not _required_cols_present(df):
        return JsonResponse({
            "ok": False,
            "error": "CSV inválido — colunas obrigatórias: Tipo, Nome",
        }, status=400)

    plan = _build_plan(df, mode=mode)
    return JsonResponse({"ok": True, "summary": _summary(plan)})


@login_required
@require_POST
def import_execute(request):
    f = request.FILES.get("arquivo")
    if not f:
        return JsonResponse({"ok": False, "error": "Ficheiro não enviado"}, status=400)
    mode = (request.POST.get("mode") or "update").lower()
    if mode not in ("skip", "update", "overwrite"):
        mode = "update"
    try:
        df = _read_csv(f)
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Erro ao ler CSV: {e}"}, status=400)
    if not _required_cols_present(df):
        return JsonResponse({
            "ok": False,
            "error": "CSV inválido — colunas obrigatórias: Tipo, Nome",
        }, status=400)

    plan = _build_plan(df, mode=mode)
    applied = _apply_plan(plan)
    messages.success(
        request,
        f"Território importado: "
        f"círculos +{applied['circulos_created']}/~{applied['circulos_updated']} · "
        f"concelhos +{applied['concelhos_created']}/~{applied['concelhos_updated']} · "
        f"zonas +{applied['zonas_created']}/~{applied['zonas_updated']} · "
        f"mesas +{applied['mesas_created']}/~{applied['mesas_updated']}",
    )
    return JsonResponse({"ok": True, "applied": applied, "summary": _summary(plan)})


@transaction.atomic
def _apply_plan(plan):
    counts = {
        "circulos_created": 0, "circulos_updated": 0,
        "concelhos_created": 0, "concelhos_updated": 0,
        "zonas_created": 0, "zonas_updated": 0,
        "mesas_created": 0, "mesas_updated": 0,
    }

    # Circulos
    for d in plan["circulos"]["create"]:
        Circulo.objects.create(
            nome=d["nome"], codigo=d["codigo"],
            ativo=d["ativo"], meta=d["meta"],
        )
        counts["circulos_created"] += 1
    for d in plan["circulos"]["update"]:
        c = Circulo.objects.get(pk=d["id"])
        for field, (_old, new) in d["changes"].items():
            setattr(c, field, new)
        c.save()
        counts["circulos_updated"] += 1

    circulos_by_name = {_norm(c.nome): c for c in Circulo.objects.all()}

    # Concelhos
    for d in plan["concelhos"]["create"]:
        circulo = circulos_by_name.get(_norm(d.get("circulo_nome") or ""))
        Concelho.objects.create(
            nome=d["nome"], codigo=d["codigo"], circulo=circulo,
            ativo=d["ativo"], meta=d["meta"],
        )
        counts["concelhos_created"] += 1
    for d in plan["concelhos"]["update"]:
        c = Concelho.objects.get(pk=d["id"])
        for field, (_old, new) in d["changes"].items():
            if field == "circulo":
                c.circulo = circulos_by_name.get(_norm(new or ""))
            else:
                setattr(c, field, new)
        c.save()
        counts["concelhos_updated"] += 1

    concelhos_by_name = {}
    for c in Concelho.objects.all():
        concelhos_by_name.setdefault(_norm(c.nome), []).append(c)

    def _resolve_concelho(nome):
        matches = concelhos_by_name.get(_norm(nome or ""), [])
        return matches[0] if matches else None

    # Zonas
    for d in plan["zonas"]["create"]:
        concelho = _resolve_concelho(d.get("concelho_nome"))
        if not concelho:
            continue  # orphan — skip silently (already in plan["errors"])
        Zona.objects.create(
            nome=d["nome"], codigo=d["codigo"], concelho=concelho,
            ativo=d["ativo"], meta=d["meta"],
        )
        counts["zonas_created"] += 1
    for d in plan["zonas"]["update"]:
        z = Zona.objects.get(pk=d["id"])
        for field, (_old, new) in d["changes"].items():
            if field == "concelho":
                z.concelho = _resolve_concelho(new)
            else:
                setattr(z, field, new)
        z.save()
        counts["zonas_updated"] += 1

    # Mesas
    from apps.mesa.models import Mesa
    # Rebuild lookups including any newly-created concelho/zona
    concelhos_by_name_post = {}
    for c in Concelho.objects.select_related("circulo").all():
        concelhos_by_name_post.setdefault(_norm(c.nome), []).append(c)
    zonas_by_name_post = {}
    for z in Zona.objects.select_related("concelho").all():
        zonas_by_name_post.setdefault(_norm(z.nome), []).append(z)

    def _resolve_mesa_links(d):
        concelho = None
        circ_norm = _norm(d.get("circulo_nome") or "")
        c_matches = concelhos_by_name_post.get(_norm(d.get("concelho_nome") or ""), [])
        if circ_norm:
            pref = [c for c in c_matches if c.circulo and _norm(c.circulo.nome) == circ_norm]
            if pref:
                c_matches = pref
        if c_matches:
            concelho = c_matches[0]

        zona = None
        z_matches = zonas_by_name_post.get(_norm(d.get("zona_nome") or ""), [])
        if concelho:
            pref = [z for z in z_matches if z.concelho_id == concelho.id]
            if pref:
                z_matches = pref
        if z_matches:
            zona = z_matches[0]
        return concelho, zona

    for d in plan["mesas"]["create"]:
        concelho, zona = _resolve_mesa_links(d)
        Mesa.objects.create(
            nr_mesa=d["nr_mesa"], status=1,
            concelho=concelho, zona=zona,
        )
        counts["mesas_created"] += 1
    for d in plan["mesas"]["update"]:
        m = Mesa.objects.get(pk=d["id"])
        if d.get("concelho_id"):
            m.concelho_id = d["concelho_id"]
        if d.get("zona_id"):
            m.zona_id = d["zona_id"]
        m.save()
        counts["mesas_updated"] += 1

    return counts


# ──────────────────────────────────────────────────────────────────────
# Select2 search endpoints
# ──────────────────────────────────────────────────────────────────────
@login_required
@require_GET
def search_circulos(request):
    q = (request.GET.get("q") or "").strip()
    qs = Circulo.objects.filter(ativo=True)
    if q:
        qs = qs.filter(nome__icontains=q)
    return JsonResponse({
        "results": [{"id": c.id, "text": c.nome} for c in qs[:30]],
    })


@login_required
@require_GET
def search_concelhos(request):
    q = (request.GET.get("q") or "").strip()
    circulo = request.GET.get("circulo")
    qs = Concelho.objects.filter(ativo=True).select_related("circulo")
    if circulo:
        qs = qs.filter(circulo_id=circulo)
    if q:
        qs = qs.filter(nome__icontains=q)
    return JsonResponse({
        "results": [
            {"id": c.id, "text": c.nome, "circulo": c.circulo.nome if c.circulo else None}
            for c in qs[:30]
        ],
    })


@login_required
@require_GET
def search_zonas(request):
    q = (request.GET.get("q") or "").strip()
    concelho = request.GET.get("concelho")
    qs = Zona.objects.filter(ativo=True).select_related("concelho")
    if concelho:
        qs = qs.filter(concelho_id=concelho)
    if q:
        qs = qs.filter(nome__icontains=q)
    return JsonResponse({
        "results": [
            {"id": z.id, "text": z.nome, "concelho": z.concelho.nome if z.concelho else None}
            for z in qs[:30]
        ],
    })
