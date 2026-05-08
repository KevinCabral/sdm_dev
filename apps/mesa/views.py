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
from django.contrib.auth.models import User
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

    qs = UserMesa.objects.select_related("user", "mesa")
    if nome:
        qs = qs.filter(user__username__icontains=nome)
    if nr_mesa:
        qs = qs.filter(mesa__nr_mesa__icontains=nr_mesa)

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
    nome = request.GET.get("nome", "")
    nr_mesa = request.GET.get("nr_mesa", "")
    filtro = {}
    
    if nome:
        filtro['user__username__icontains'] = nome

    if nr_mesa:
        filtro['mesa__nr_mesa'] = nr_mesa

    mesas = UserMesa.objects.filter(**filtro).all()
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="utilizador_mesa.csv"'},
    )

    writer = csv.writer(response)
    if len(mesas) > 0:
        keys = list(model_to_dict(mesas[0]).keys())
        header = []
        keys.append("Username")
        for k in keys: 
            text = k.replace("_", " ")
            header.append(text)
        writer.writerow(header)
        for i in mesas:
            data = list(model_to_dict(i).values())
            data.append(i.user.username)
            writer.writerow(data)
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

    mesa = Mesa.objects.filter(**filtros)
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
            userMesa = form.save()
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

    mesa = Mesa.objects.get(pk=id)
    
    if not(mesa):
        messages.error(request, f'Erro na visualização de Mesa')
        data = {}
    else:
        data = model_to_dict(mesa)
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
