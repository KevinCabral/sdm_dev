from django.shortcuts import render

from .models import UserMesa,Mesa
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404,redirect
from django.contrib.auth.decorators import login_required
import csv
from django.contrib import messages
from django.http import JsonResponse
from django.http import HttpResponse
from django.forms.models import model_to_dict
from .form import UserMesaForm,MesaForm
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.contrib.auth.models import User, Group
from django.db import transaction
import pandas as pd
import io


@login_required
def search_users(request):
    """Lightweight JSON autocomplete for users (Select2 compatible)."""
    q = (request.GET.get("q") or "").strip()
    qs = User.objects.filter(is_active=True)
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )
    qs = qs.order_by("username")[:20]
    results = [{"id": u.pk, "text": u.username} for u in qs]
    return JsonResponse({"results": results})


@login_required
def search_mesas(request):
    """Lightweight JSON autocomplete for mesas (Select2 compatible)."""
    q = (request.GET.get("q") or "").strip()
    qs = Mesa.objects.filter(status=1)
    if q:
        qs = qs.filter(nr_mesa__icontains=q)
    qs = qs.order_by("nr_mesa")[:20]
    results = [{"id": m.pk, "text": m.nr_mesa} for m in qs]
    return JsonResponse({"results": results})

@login_required
def index(request):
    """List Mesa assignments grouped by user.

    Each row in the table represents a user and the set of mesas attached
    to them via ``UserMesa``. Filters work over the username (``nome``)
    and over a specific mesa number (``nr_mesa``).
    """
    nome = request.GET.get("nome", "").strip()
    nr_mesa = request.GET.get("nr_mesa", "").strip()
    circulo = request.GET.get("circulo", "").strip()
    concelho = request.GET.get("concelho", "").strip()
    zona = request.GET.get("zona", "").strip()

    qs = UserMesa.objects.select_related(
        "user", "mesa", "mesa__concelho", "mesa__concelho__circulo", "mesa__zona",
    )
    if nome:
        qs = qs.filter(user__username__icontains=nome)
    if nr_mesa:
        qs = qs.filter(mesa__nr_mesa__icontains=nr_mesa)
    if circulo:
        qs = qs.filter(mesa__concelho__circulo_id=circulo)
    if concelho:
        qs = qs.filter(mesa__concelho_id=concelho)
    if zona:
        qs = qs.filter(mesa__zona_id=zona)

    # Group in Python to keep the query simple. A user_id of ``None``
    # should not happen (user is non-null) but is guarded for safety.
    grouped = {}
    for um in qs.order_by("user__username", "mesa__nr_mesa"):
        if not um.user_id:
            continue
        key = um.user_id
        bucket = grouped.setdefault(key, {
            "user": um.user,
            "mesas": [],
            "row_ids": [],
            "createdAt": um.createdAt,
        })
        if um.mesa_id:
            bucket["mesas"].append(um.mesa)
            bucket["row_ids"].append(um.id)
        if um.createdAt and (not bucket["createdAt"] or um.createdAt < bucket["createdAt"]):
            bucket["createdAt"] = um.createdAt

    rows = list(grouped.values())

    paginator = Paginator(rows, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    form = UserMesaForm()
    breadcrumbs = [{'title': 'Pagina Inicial', 'url': '/'}, {'title': 'Mesas'}]
    return render(
        request,
        "pages/mesa/index.html",
        {'page_obj': page_obj, 'form': form, 'breadcrumbs': breadcrumbs},
    )

@login_required
def createOrUpdate(request):
    """Create or replace the set of mesas assigned to a single user.

    POST fields:
      - user: User pk
      - mesa: one or many Mesa pks (use ``getlist``)
      - id (optional): an existing UserMesa pk used only to resolve the
        target user when editing an existing assignment row.
    """
    if request.method != 'POST':
        return redirect("mesa.index")

    user_id = (request.POST.get('user') or '').strip()
    mesa_ids = [m for m in request.POST.getlist('mesa') if m]
    edit_id = (request.POST.get('id') or '').strip()

    # When editing, allow the user-id to be inferred from the original row.
    if not user_id and edit_id:
        try:
            user_id = str(UserMesa.objects.get(pk=edit_id).user_id)
        except UserMesa.DoesNotExist:
            user_id = ''

    if not user_id or not mesa_ids:
        messages.error(request, 'Selecione utilizador e pelo menos uma mesa')
        return redirect("mesa.index")

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        messages.error(request, 'Utilizador inválido')
        return redirect("mesa.index")

    mesas = list(Mesa.objects.filter(pk__in=mesa_ids))
    if not mesas:
        messages.error(request, 'Mesas inválidas')
        return redirect("mesa.index")

    # Replace this user's assignments with the new selection (idempotent).
    UserMesa.objects.filter(user=user).delete()
    UserMesa.objects.bulk_create([UserMesa(user=user, mesa=m) for m in mesas])

    messages.success(request, f'{len(mesas)} mesa(s) associada(s) a {user.username}')
    return redirect("mesa.index")


@login_required
def remover(request):
    """Remove all mesa assignments for a given user.

    Accepts ``user`` (preferred) or legacy ``id`` (a UserMesa row pk that
    is resolved into the underlying user) and deletes every UserMesa row
    bound to that user.
    """
    if request.method != "POST":
        raise ObjectDoesNotExist()

    user_id = (request.POST.get("user") or "").strip()
    row_id = (request.POST.get("id") or "").strip()
    if not user_id and row_id:
        try:
            user_id = str(UserMesa.objects.get(pk=row_id).user_id)
        except UserMesa.DoesNotExist:
            user_id = ""

    if not user_id:
        messages.error(request, 'Erro em remover Mesa')
        return redirect("mesa.index")

    deleted, _ = UserMesa.objects.filter(user_id=user_id).delete()
    if deleted:
        messages.success(request, 'Associações removidas')
    else:
        messages.error(request, 'Erro em remover Mesa')
    return redirect("mesa.index")


@login_required
def get(request):
    """Return either a single UserMesa row (legacy ``id`` param) or the full
    set of mesas attached to a user when called with ``?user=<id>``.
    """
    user_id = request.GET.get("user", "").strip()
    id = request.GET.get("id", "").strip()

    # Resolve user from row id when only ``id`` was supplied.
    if id and not user_id:
        try:
            user_id = str(UserMesa.objects.get(pk=id).user_id)
        except UserMesa.DoesNotExist:
            return JsonResponse({})

    if user_id:
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return JsonResponse({})
        mesas_qs = (
            UserMesa.objects.filter(user=user, mesa__isnull=False)
            .select_related("mesa")
            .order_by("mesa__nr_mesa")
        )
        return JsonResponse({
            "user": {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
            },
            "mesas": [
                {"id": um.mesa.id, "nr_mesa": um.mesa.nr_mesa}
                for um in mesas_qs
            ],
        })

    return JsonResponse({})

@login_required
def exportExcel(request):
    nome = request.GET.get("nome", "").strip()
    nr_mesa = request.GET.get("nr_mesa", "").strip()
    circulo = request.GET.get("circulo", "").strip()
    concelho = request.GET.get("concelho", "").strip()
    zona = request.GET.get("zona", "").strip()

    qs = UserMesa.objects.select_related(
        "user", "mesa", "mesa__concelho", "mesa__concelho__circulo", "mesa__zona",
    )
    if nome:
        qs = qs.filter(user__username__icontains=nome)
    if nr_mesa:
        qs = qs.filter(mesa__nr_mesa__icontains=nr_mesa)
    if circulo:
        qs = qs.filter(mesa__concelho__circulo_id=circulo)
    if concelho:
        qs = qs.filter(mesa__concelho_id=concelho)
    if zona:
        qs = qs.filter(mesa__zona_id=zona)

    qs = qs.order_by("user__username", "mesa__nr_mesa")

    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="utilizador_mesa.csv"'},
    )
    writer = csv.writer(response)
    writer.writerow(["Username", "Mesa", "Zona", "Concelho", "Circulo", "Password"])
    for um in qs:
        username = um.user.username if um.user_id else ""
        mesa_nr = um.mesa.nr_mesa if um.mesa_id else ""
        zona_nm = um.mesa.zona.nome if (um.mesa_id and um.mesa.zona_id) else ""
        concelho_nm = um.mesa.concelho.nome if (um.mesa_id and um.mesa.concelho_id) else ""
        circulo_nm = (
            um.mesa.concelho.circulo.nome
            if (um.mesa_id and um.mesa.concelho_id and um.mesa.concelho.circulo_id)
            else ""
        )
        password = f"{username}2026" if username else ""
        writer.writerow([username, mesa_nr, zona_nm, concelho_nm, circulo_nm, password])
    return response


def _normalize_column_name(name):
    return str(name).strip().lower().replace("_", " ")


def _extract_nr_mesa_column(df):
    normalized_map = {_normalize_column_name(col): col for col in df.columns}
    candidates = [
        "nr mesa",
        "nrmesa",
        "numero mesa",
        "n mesa",
        "mesa",
    ]
    for candidate in candidates:
        if candidate in normalized_map:
            return normalized_map[candidate]
    return None


def _read_csv_with_common_separators(raw_bytes):
    for encoding in ('utf-8-sig', 'latin-1'):
        try:
            text = raw_bytes.decode(encoding)
        except Exception:
            continue
        for separator in (',', ';', '\t', '|'):
            try:
                parsed = pd.read_csv(io.StringIO(text), sep=separator)
            except Exception:
                continue
            if not parsed.empty and _extract_nr_mesa_column(parsed):
                return parsed
        try:
            return pd.read_csv(io.StringIO(text))
        except Exception:
            pass
    raise ValueError('invalid csv')


def _load_mesa_dataframe(upload):
    filename = (upload.name or '').lower()
    content = upload.read()

    if filename.endswith('.csv'):
        readers = [_read_csv_with_common_separators, lambda b: pd.read_excel(io.BytesIO(b))]
    elif filename.endswith('.xlsx') or filename.endswith('.xls'):
        readers = [lambda b: pd.read_excel(io.BytesIO(b)), _read_csv_with_common_separators]
    else:
        readers = [lambda b: pd.read_excel(io.BytesIO(b)), _read_csv_with_common_separators]

    for reader in readers:
        try:
            return reader(content)
        except Exception:
            continue
    return None


def _analyze_mesa_rows(df):
    nr_mesa_column = _extract_nr_mesa_column(df)
    if not nr_mesa_column:
        return None

    rows = []
    for _, row in df.iterrows():
        raw_value = row.get(nr_mesa_column)
        if pd.isna(raw_value):
            rows.append(None)
            continue
        nr_mesa = str(raw_value).strip()
        rows.append(nr_mesa if nr_mesa and nr_mesa.lower() != 'nan' else None)
    return rows


def _summarize_mesa_import(rows, preview_limit=10):
    seen = set()
    ordered_unique = []
    skipped = 0

    for nr_mesa in rows:
        if not nr_mesa:
            skipped += 1
            continue
        if nr_mesa in seen:
            skipped += 1
            continue
        seen.add(nr_mesa)
        ordered_unique.append(nr_mesa)

    existing = {
        nr: status
        for nr, status in Mesa.objects.filter(nr_mesa__in=ordered_unique).values_list('nr_mesa', 'status')
    }

    created = 0
    reactivated = 0
    preview = []

    for nr_mesa in ordered_unique:
        status = existing.get(nr_mesa)
        if status is None:
            created += 1
            action = 'Criar'
        elif str(status) != '1':
            reactivated += 1
            action = 'Reativar'
        else:
            skipped += 1
            action = 'Ignorar'

        if len(preview) < preview_limit:
            preview.append({'nr_mesa': nr_mesa, 'action': action})

    return {
        'created': created,
        'reactivated': reactivated,
        'skipped': skipped,
        'preview': preview,
        'total_rows': len(rows),
    }


@login_required
def uploadMesaPreview(request):
    if request.method != 'POST' or 'arquivo_mesa' not in request.FILES:
        return JsonResponse({'message': 'Selecione um ficheiro para pré-visualizar'}, status=400)

    upload = request.FILES['arquivo_mesa']
    df = _load_mesa_dataframe(upload)
    if df is None:
        return JsonResponse({'message': 'Não foi possível ler o ficheiro. Use CSV, XLS ou XLSX'}, status=400)
    if df.empty:
        return JsonResponse({'message': 'Ficheiro sem dados para importar'}, status=400)

    rows = _analyze_mesa_rows(df)
    if rows is None:
        return JsonResponse({'message': 'Coluna de mesa não encontrada. Use: nr_mesa, Numero Mesa ou Mesa'}, status=400)

    summary = _summarize_mesa_import(rows)
    return JsonResponse({
        'filename': upload.name,
        'created': summary['created'],
        'reactivated': summary['reactivated'],
        'skipped': summary['skipped'],
        'total_rows': summary['total_rows'],
        'preview': summary['preview'],
    })


@login_required
def uploadMesa(request):
    if request.method != 'POST' or 'arquivo_mesa' not in request.FILES:
        messages.error(request, 'Selecione um ficheiro para carregar')
        return redirect('mesa.index_mesa')

    upload = request.FILES['arquivo_mesa']
    df = _load_mesa_dataframe(upload)

    if df is None:
        messages.error(request, 'Não foi possível ler o ficheiro. Use CSV, XLS ou XLSX')
        return redirect('mesa.index_mesa')

    if df.empty:
        messages.warning(request, 'Ficheiro sem dados para importar')
        return redirect('mesa.index_mesa')

    rows = _analyze_mesa_rows(df)
    if rows is None:
        messages.error(request, 'Coluna de mesa não encontrada. Use: nr_mesa, Numero Mesa ou Mesa')
        return redirect('mesa.index_mesa')

    summary = _summarize_mesa_import(rows)
    created = 0
    reactivated = 0
    seen = set()

    for nr_mesa in rows:
        if not nr_mesa or nr_mesa in seen:
            continue
        seen.add(nr_mesa)

        mesa, is_created = Mesa.objects.get_or_create(
            nr_mesa=nr_mesa,
            defaults={'status': 1}
        )

        if is_created:
            created += 1
            continue

        if str(mesa.status) != '1':
            mesa.status = 1
            mesa.save()
            reactivated += 1
    messages.success(
        request,
        f"Importação concluída. Criadas: {created}, Reativadas: {reactivated}, Ignoradas: {summary['skipped']}"
    )
    return redirect('mesa.index_mesa')


@login_required
def indexMesa(request):
    filtros = {'status': '1'}
    nr_mesa = request.GET.get("nr_mesa", "")
    if nr_mesa:
        filtros['nr_mesa__icontains'] = nr_mesa
    circulo = request.GET.get("circulo", "")
    if circulo:
        filtros['concelho__circulo_id'] = circulo
    concelho = request.GET.get("concelho", "")
    if concelho:
        filtros['concelho_id'] = concelho
    zona = request.GET.get("zona", "")
    if zona:
        filtros['zona_id'] = zona

    mesa = Mesa.objects.filter(**filtros).select_related(
        "concelho", "concelho__circulo", "zona",
    )
    paginator = Paginator(mesa, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    form = MesaForm()
    breadcrumbs = [{'title': 'Pagina Inicial','url':'/'},{'title': 'Mesas Associados'}]
    return render(request, "pages/mesa/mesa.html",{'page_obj': page_obj,'form':form,'breadcrumbs':breadcrumbs})

@login_required
def createOrUpdateMesa(request):
    form = MesaForm()
    if request.method == 'POST':
        id = request.POST.get("id", "")
        if id != "":
            userMesa = Mesa.objects.get(pk=id)
            form = MesaForm(request.POST,instance=userMesa)
        else:
            form = MesaForm(request.POST)
        if form.is_valid():
            userMesa = form.save(commit=False)
            # Territorial FKs (sent as plain integers via Select2 hidden inputs)
            concelho_id = (request.POST.get("concelho") or "").strip()
            zona_id = (request.POST.get("zona") or "").strip()
            userMesa.concelho_id = int(concelho_id) if concelho_id.isdigit() else None
            userMesa.zona_id = int(zona_id) if zona_id.isdigit() else None
            userMesa.save()
            if id != "":
                messages.success(request, f'Mesa Atualizado')
            else:
                messages.success(request, f'Mesa Criado')
            return redirect("mesa.index_mesa")
        else:
            if id != "":
                messages.error(request, f'Erro em atualizar mesa')
            else:
                messages.error(request, f'Erro em criar mesa')
    return redirect("mesa.index_mesa")


@login_required
def removerMesa(request):
    if request.method == "POST":
        id = request.POST.get("id", "")
        eleitor = Mesa.objects.get(pk=id)
        if eleitor:
            eleitor.status = '0'
            eleitor.save()
            messages.success(request, f'Mesa removido')
            return redirect("mesa.index_mesa")

        messages.error(request, f'Erro em remover Mesa')
        return redirect("mesa.index_mesa")
    raise ObjectDoesNotExist()


@login_required
def removerMesaMassa(request):
    if request.method != "POST":
        return JsonResponse({"message": "Método inválido"}, status=405)

    ids = request.POST.getlist("ids[]")
    if not ids:
        ids_csv = request.POST.get("ids", "")
        if ids_csv:
            ids = [x.strip() for x in ids_csv.split(",") if x.strip()]

    if not ids:
        return JsonResponse({"message": "Nenhuma mesa selecionada"}, status=400)

    removed = Mesa.objects.filter(id__in=ids, status='1').update(status='0')
    return JsonResponse({"removed": removed})



@login_required
def getMesa(request):
    id = request.GET.get("id","")
    if id == "":
        return JsonResponse({})

    mesa = Mesa.objects.select_related(
        "concelho", "concelho__circulo", "zona",
    ).filter(pk=id).first()

    if not mesa:
        messages.error(request, f'Erro na visualização de Mesa')
        return JsonResponse({})

    data = {
        'id': mesa.id,
        'nr_mesa': mesa.nr_mesa,
        'status': mesa.status,
        'concelho_id': mesa.concelho_id,
        'concelho_nome': mesa.concelho.nome if mesa.concelho else None,
        'zona_id': mesa.zona_id,
        'zona_nome': mesa.zona.nome if mesa.zona else None,
        'circulo_id': mesa.concelho.circulo_id if mesa.concelho and mesa.concelho.circulo_id else None,
        'circulo_nome': mesa.concelho.circulo.nome if mesa.concelho and mesa.concelho.circulo else None,
    }
    return JsonResponse(data)

@login_required
def exportExcelMesa(request):
    filtro = {'status': '1'}
    nr_mesa = request.GET.get("nr_mesa", "")
    if nr_mesa:
        filtro['nr_mesa__icontains'] = nr_mesa

    mesas = Mesa.objects.filter(**filtro).all()
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="mesa.csv"'},
    )

    writer = csv.writer(response)
    if len(mesas) > 0:
        keys = list(model_to_dict(mesas[0]).keys())
        header = []
        for k in keys: 
            text = k.replace("_", " ")
            header.append(text)
        writer.writerow(header)
        for i in mesas:
            data = list(model_to_dict(i).values())
            writer.writerow(data)
    return response


# --------------------------------------------------------------------------- #
# Importação de Delegados (MESA · NOMES · CONTACTO)
# --------------------------------------------------------------------------- #

DELEGADO_GROUP_NAME = "delegado"
DELEGADO_PASSWORD_SUFFIX = "2026"
DELEGADO_EMAIL_DOMAIN = "@mpd.cv"


def _find_column(df, candidates):
    normalized_map = {_normalize_column_name(col): col for col in df.columns}
    for cand in candidates:
        if cand in normalized_map:
            return normalized_map[cand]
    return None


def _delegado_username_from_mesa(nr_mesa):
    """saa01 from 'SA-A-01' (strip '-', spaces, lowercase)."""
    cleaned = "".join(str(nr_mesa).split()).replace("-", "").lower()
    return cleaned


def _clean_cell(value):
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    # pandas may turn integer contacts into "9943769.0"
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _analyze_delegado_rows(df):
    mesa_col = _find_column(df, ["mesa", "nr mesa", "nrmesa", "numero mesa", "n mesa"])
    nome_col = _find_column(df, ["nomes", "nome", "primeiro nome"])
    contacto_col = _find_column(df, ["contacto", "contato", "telefone", "telemovel", "telemóvel", "phone"])

    if not mesa_col or not nome_col:
        return None, None, None, None

    rows = []
    for _, row in df.iterrows():
        mesa = _clean_cell(row.get(mesa_col))
        nome = _clean_cell(row.get(nome_col))
        contacto = _clean_cell(row.get(contacto_col)) if contacto_col else ""
        if not mesa or not nome:
            rows.append(None)
            continue
        rows.append({"mesa": mesa, "nome": nome, "contacto": contacto})
    return rows, mesa_col, nome_col, contacto_col


def _summarize_delegado_import(rows, preview_limit=10):
    """Plan import without writing anything."""
    skipped = 0
    seen_users = set()
    seen_mesas = set()
    plan = []  # list of dicts: {mesa, username, nome, contacto, mesa_action, user_action, assoc_action}

    valid = [r for r in rows if r]
    skipped += sum(1 for r in rows if not r)

    mesa_values = list({r["mesa"] for r in valid})
    existing_mesas = {
        m.nr_mesa: m
        for m in Mesa.objects.filter(nr_mesa__in=mesa_values)
    }

    usernames = list({_delegado_username_from_mesa(r["mesa"]) for r in valid})
    existing_users = {u.username: u for u in User.objects.filter(username__in=usernames)}

    existing_assocs = set()
    if existing_users and existing_mesas:
        for um in UserMesa.objects.filter(
            user_id__in=[u.id for u in existing_users.values()],
            mesa_id__in=[m.id for m in existing_mesas.values()],
        ).values_list("user_id", "mesa_id"):
            existing_assocs.add(um)

    created_users = 0
    reactivated_users = 0
    skipped_users = 0
    created_mesas = 0
    reactivated_mesas = 0
    skipped_mesas = 0
    created_assocs = 0
    skipped_assocs = 0

    for r in valid:
        mesa = r["mesa"]
        username = _delegado_username_from_mesa(mesa)
        if not username:
            skipped += 1
            continue

        # Mesa
        m = existing_mesas.get(mesa)
        if m is None:
            mesa_action = "Criar"
            if mesa not in seen_mesas:
                created_mesas += 1
        elif str(m.status) != "1":
            mesa_action = "Reativar"
            if mesa not in seen_mesas:
                reactivated_mesas += 1
        else:
            mesa_action = "Existe"
            if mesa not in seen_mesas:
                skipped_mesas += 1
        seen_mesas.add(mesa)

        # User
        u = existing_users.get(username)
        if u is None:
            user_action = "Criar"
            if username not in seen_users:
                created_users += 1
        else:
            user_action = "Existe"
            if username not in seen_users:
                skipped_users += 1
        seen_users.add(username)

        # Association
        if u is not None and m is not None and (u.id, m.id) in existing_assocs:
            assoc_action = "Existe"
            skipped_assocs += 1
        else:
            assoc_action = "Criar"
            created_assocs += 1

        if len(plan) < preview_limit:
            plan.append({
                "mesa": mesa,
                "username": username,
                "email": username + DELEGADO_EMAIL_DOMAIN,
                "password": username + DELEGADO_PASSWORD_SUFFIX,
                "nome": r["nome"],
                "contacto": r["contacto"],
                "mesa_action": mesa_action,
                "user_action": user_action,
                "assoc_action": assoc_action,
            })

    return {
        "total_rows": len(rows),
        "skipped_rows": skipped,
        "created_mesas": created_mesas,
        "reactivated_mesas": reactivated_mesas,
        "skipped_mesas": skipped_mesas,
        "created_users": created_users,
        "skipped_users": skipped_users,
        "created_assocs": created_assocs,
        "skipped_assocs": skipped_assocs,
        "preview": plan,
    }


@login_required
def uploadDelegadosPreview(request):
    if request.method != "POST" or "arquivo_delegados" not in request.FILES:
        return JsonResponse({"message": "Selecione um ficheiro para pré-visualizar"}, status=400)

    upload = request.FILES["arquivo_delegados"]
    df = _load_mesa_dataframe(upload)
    if df is None:
        return JsonResponse({"message": "Não foi possível ler o ficheiro. Use CSV, XLS ou XLSX"}, status=400)
    if df.empty:
        return JsonResponse({"message": "Ficheiro sem dados para importar"}, status=400)

    rows, mesa_col, nome_col, contacto_col = _analyze_delegado_rows(df)
    if rows is None:
        return JsonResponse({
            "message": "Colunas em falta. O ficheiro deve conter: MESA, NOMES (CONTACTO opcional)"
        }, status=400)

    summary = _summarize_delegado_import(rows)
    summary["filename"] = upload.name
    summary["columns"] = {
        "mesa": mesa_col,
        "nomes": nome_col,
        "contacto": contacto_col,
    }
    return JsonResponse(summary)


@login_required
def uploadDelegados(request):
    if request.method != "POST" or "arquivo_delegados" not in request.FILES:
        messages.error(request, "Selecione um ficheiro para carregar")
        return redirect("mesa.index")

    upload = request.FILES["arquivo_delegados"]
    df = _load_mesa_dataframe(upload)
    if df is None:
        messages.error(request, "Não foi possível ler o ficheiro. Use CSV, XLS ou XLSX")
        return redirect("mesa.index")
    if df.empty:
        messages.warning(request, "Ficheiro sem dados para importar")
        return redirect("mesa.index")

    rows, _mesa_col, _nome_col, _contacto_col = _analyze_delegado_rows(df)
    if rows is None:
        messages.error(request, "Colunas em falta. O ficheiro deve conter: MESA, NOMES (CONTACTO opcional)")
        return redirect("mesa.index")

    delegado_group, _ = Group.objects.get_or_create(name=DELEGADO_GROUP_NAME)

    created_users = 0
    updated_users = 0
    created_mesas = 0
    reactivated_mesas = 0
    created_assocs = 0
    skipped_assocs = 0
    errors = 0

    seen_usernames = set()
    seen_mesas = set()

    with transaction.atomic():
        for r in rows:
            if not r:
                continue
            try:
                mesa_value = r["mesa"]
                nome = r["nome"]
                username = _delegado_username_from_mesa(mesa_value)
                if not username:
                    errors += 1
                    continue

                # Mesa
                mesa_obj, mesa_created = Mesa.objects.get_or_create(
                    nr_mesa=mesa_value, defaults={"status": 1}
                )
                if mesa_value not in seen_mesas:
                    seen_mesas.add(mesa_value)
                    if mesa_created:
                        created_mesas += 1
                    elif str(mesa_obj.status) != "1":
                        mesa_obj.status = 1
                        mesa_obj.save(update_fields=["status"])
                        reactivated_mesas += 1

                # User
                email = username + DELEGADO_EMAIL_DOMAIN
                password = username + DELEGADO_PASSWORD_SUFFIX

                user_obj, user_created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "first_name": nome[:150],
                        "email": email,
                        "is_active": True,
                    },
                )
                if user_created:
                    user_obj.set_password(password)
                    user_obj.save()
                    created_users += 1
                else:
                    changed = False
                    if not user_obj.first_name:
                        user_obj.first_name = nome[:150]
                        changed = True
                    if not user_obj.email:
                        user_obj.email = email
                        changed = True
                    if changed:
                        user_obj.save(update_fields=["first_name", "email"])
                        updated_users += 1

                if username not in seen_usernames:
                    seen_usernames.add(username)
                    user_obj.groups.add(delegado_group)

                # Association
                assoc, assoc_created = UserMesa.objects.get_or_create(
                    user=user_obj, mesa=mesa_obj
                )
                if assoc_created:
                    created_assocs += 1
                else:
                    skipped_assocs += 1
            except Exception:
                errors += 1
                continue

    messages.success(
        request,
        (
            f"Importação concluída. "
            f"Mesas criadas: {created_mesas}, reativadas: {reactivated_mesas}. "
            f"Utilizadores criados: {created_users}, atualizados: {updated_users}. "
            f"Associações criadas: {created_assocs}, existentes: {skipped_assocs}. "
            f"Erros: {errors}."
        ),
    )
    return redirect("mesa.index")
