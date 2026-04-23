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
    filtros = {}
    nome = request.GET.get("nome", "")
    nr_mesa = request.GET.get("nr_mesa", "")
    if nome:
        filtros['user__username__icontains'] = nome

    if nr_mesa:
        filtros['nr_mesa'] = nr_mesa
    userMesa = UserMesa.objects.filter(**filtros)
    paginator = Paginator(userMesa, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    form = UserMesaForm()
    breadcrumbs = [{'title': 'Pagina Inicial','url':'/'},{'title': 'Mesas'}]
    return render(request, "pages/mesa/index.html",{'page_obj': page_obj,'form':form,'breadcrumbs':breadcrumbs})

@login_required
def createOrUpdate(request):
    form = UserMesaForm()
    if request.method == 'POST':
        id = request.POST.get("id", "")
        if id != "":
            userMesa = UserMesa.objects.get(pk=id)
            form = UserMesaForm(request.POST,instance=userMesa)
        else:
            form = UserMesaForm(request.POST)
        if form.is_valid():
            userMesa = form.save()
            if id != "":
                messages.success(request, f'Atualizado')
            else:
                messages.success(request, f'Mesa Associada')
            return redirect("mesa.index")
        else:
            if id != "":
                messages.error(request, f'Erro na atualização')
            else:
                messages.error(request, f'Erro na associação de mesa')
    return redirect("mesa.index")


@login_required
def remover(request):
    if request.method == "POST":
        id = request.POST.get("id", "")
        mesa = UserMesa.objects.get(pk=id)
        if mesa:
            mesa.delete()
            messages.success(request, f'Mesa removido')
            return redirect("mesa.index")

        messages.error(request, f'Erro em remover Mesa')
        return redirect("mesa.index")
    raise ObjectDoesNotExist()


@login_required
def get(request):
    id = request.GET.get("id","")
    if id == "":
        return JsonResponse({})
    mesaUser = UserMesa.objects.get(pk=id)

    if not(mesaUser):
        messages.error(request, f'Erro na visualização de Mesa')
        data = {}
    else:
        data = {
            "mesa": (
                {"id": mesaUser.mesa.id, "nr_mesa": mesaUser.mesa.nr_mesa}
                if mesaUser.mesa else None
            ),
            "user": (
                {
                    "id": mesaUser.user.id,
                    "username": mesaUser.user.username,
                    "first_name": mesaUser.user.first_name,
                    "last_name": mesaUser.user.last_name,
                    "email": mesaUser.user.email,
                }
                if mesaUser.user else None
            ),
        }
    return JsonResponse(data)

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
