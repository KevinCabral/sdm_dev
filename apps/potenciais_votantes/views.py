"""Views for the Potenciais Votantes (Call Center) module.

Mirrors the structure of ``apps.eleitores.views`` but trimmed to the
fields exposed by the Call Center spreadsheet:
    NOME · LOCALIDADE · ASSINATURA · TELEFONE
"""
import csv

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.forms.models import model_to_dict
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import PotencialVotanteForm
from .models import PotencialVotante, PotencialVotanteImport
from apps.militantes.models import Militantes, Morada, MilitantesCallInfo


# ----------------------------------------------------------------------
# Spreadsheet column → model field map (NOME · LOCALIDADE · ASSINATURA ·
# TELEFONE). Headers are normalized (lowercase, trim, _ → space).
# ----------------------------------------------------------------------
FIELD_MAP = {
    'nome':          ('nome', 'str'),
    'nome completo': ('nome', 'str'),
    'localidade':    ('localidade', 'str'),
    'local':         ('localidade', 'str'),
    'zona':          ('localidade', 'str'),
    'assinatura':    ('assinatura', 'bool'),
    'is contactado': ('is_contactado', 'bool'),
    'contactado':    ('is_contactado', 'bool'),
    'contactados':   ('is_contactado', 'bool'),
    'telefone':      ('telefone', 'str'),
    'tel':           ('telefone', 'str'),
    'contato':       ('telefone', 'str'),
    'contacto':      ('telefone', 'str'),
    'observacao':    ('observacao', 'str'),
    'observação':    ('observacao', 'str'),
    'observacoes':   ('observacao', 'str'),
    'observações':   ('observacao', 'str'),
}


def _norm_header(s):
    return ' '.join(
        str(s).strip().lower().replace('_', ' ').replace('-', ' ').split()
    )


def _build_column_map(df_columns):
    mapping = {}
    for col in df_columns:
        spec = FIELD_MAP.get(_norm_header(col))
        if spec:
            mapping[col] = spec
    return mapping


def _coerce_value(value, kind):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None

    if kind == 'bool':
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in ('true', '1', 'sim', 'yes', 'y', 's', 'verdadeiro', 'x', '✓'):
            return True
        if s in ('false', '0', 'nao', 'não', 'no', 'n', 'falso', ''):
            return False
        # Any other non-empty value (e.g. a written name in the ASSINATURA
        # column) counts as "signed".
        return True

    s = str(value).strip()
    if not s or s.lower() in ('nan', 'none', 'null'):
        return None
    return s


def _row_to_kwargs(row, col_map):
    kwargs = {}
    for col, (field, kind) in col_map.items():
        if col not in row.index:
            continue
        coerced = _coerce_value(row[col], kind)
        if coerced is None:
            continue
        # For bool fields we still want to record explicit False values, but
        # _coerce_value already returns False above. Skip only None.
        kwargs[field] = coerced
    # Default booleans absent from the file
    kwargs.setdefault('assinatura', False)
    return kwargs


def _build_filters(request):
    filters = {"ativo": True}
    if nome := request.GET.get("nome", ""):
        filters['nome__icontains'] = nome
    if localidade := request.GET.get("localidade", ""):
        filters['localidade__icontains'] = localidade
    if telefone := request.GET.get("telefone", ""):
        filters['telefone__icontains'] = telefone
    if request.GET.get("assinatura", "false") == "true":
        filters['assinatura'] = True
    if request.GET.get("is_contactado", "false") == "true":
        # Only show contacted records when the filter is explicitly toggled on.
        filters['is_contactado'] = True
    else:
        # Default listing hides already-contacted potenciais votantes.
        filters['is_contactado'] = False
    return filters


# ──────────────────────────────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────────────────────────────

@login_required
def index(request):
    qs = PotencialVotante.objects.filter(**_build_filters(request))
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    breadcrumbs = [
        {'title': 'Pagina Inicial', 'url': '/'},
        {'title': 'Call Center'},
        {'title': 'Potenciais Votantes'},
    ]
    return render(
        request,
        "pages/potenciais_votantes/index.html",
        {'page_obj': page_obj, 'breadcrumbs': breadcrumbs},
    )


@login_required
def create(request):
    form = PotencialVotanteForm()
    if request.method == 'POST':
        form = PotencialVotanteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Potencial votante criado')
            return redirect("potenciais_votantes.index")
        messages.error(request, 'Erro em criar potencial votante')
    breadcrumbs = [
        {'title': 'Pagina Inicial', 'url': '/'},
        {'title': 'Potenciais Votantes', 'url': '../potenciais-votantes/index'},
        {'title': 'Criar'},
    ]
    return render(
        request,
        "pages/potenciais_votantes/create.html",
        {'form': form, 'breadcrumbs': breadcrumbs},
    )


@login_required
def update(request, id):
    obj = get_object_or_404(PotencialVotante, pk=id)
    form = PotencialVotanteForm(instance=obj)
    if request.method == 'POST':
        form = PotencialVotanteForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Potencial votante atualizado')
            return redirect("potenciais_votantes.index")
        messages.error(request, 'Erro em atualizar potencial votante')
    breadcrumbs = [
        {'title': 'Pagina Inicial', 'url': '/'},
        {'title': 'Potenciais Votantes', 'url': '../../potenciais-votantes/index'},
        {'title': 'Atualizar'},
    ]
    return render(
        request,
        "pages/potenciais_votantes/update.html",
        {'form': form, 'id': id, 'obj': obj, 'breadcrumbs': breadcrumbs},
    )


@login_required
def view(request, id):
    obj = get_object_or_404(PotencialVotante, pk=id)
    form = PotencialVotanteForm(instance=obj)
    breadcrumbs = [
        {'title': 'Pagina Inicial', 'url': '/'},
        {'title': 'Potenciais Votantes', 'url': '../../potenciais-votantes/index'},
        {'title': obj.nome or f'Potencial Votante #{obj.pk}'},
    ]
    return render(
        request,
        "pages/potenciais_votantes/view.html",
        {'form': form, 'id': id, 'obj': obj, 'breadcrumbs': breadcrumbs},
    )


@login_required
def detail_json(request, id):
    obj = get_object_or_404(PotencialVotante, pk=id)
    return JsonResponse({
        'id': obj.id,
        'nome': obj.nome,
        'localidade': obj.localidade,
        'telefone': obj.telefone,
        'assinatura': bool(obj.assinatura),
        'is_contactado': bool(obj.is_contactado),
        'observacao': obj.observacao,
        'criado_em': obj.criado_em.isoformat() if obj.criado_em else None,
    })


@login_required
def remover(request):
    if request.method != "POST":
        raise ObjectDoesNotExist()
    obj = PotencialVotante.objects.filter(pk=request.POST.get("id", "")).first()
    if obj:
        obj.ativo = False
        obj.save(update_fields=['ativo'])
        messages.success(request, 'Potencial votante removido')
        return redirect("potenciais_votantes.index")
    messages.error(request, 'Erro em remover')
    return redirect("potenciais_votantes.index")


@login_required
def inquerito(request, id):
    """Inquérito (call-center survey) modal endpoint.

    GET  → returns existing Militante / Morada / last CallInfo data (if any)
           for the given PotencialVotante so the form can be pre-filled.
    POST → creates/updates the Militante and Morada bound to this
           PotencialVotante and inserts a new MilitantesCallInfo row.
    """
    pv = get_object_or_404(PotencialVotante, pk=id)

    if request.method == 'GET':
        militante = Militantes.objects.filter(potencial_votante_id=pv.id).first()
        morada = None
        if militante:
            morada = Morada.objects.filter(militante=militante).first()
        if not morada:
            morada = Morada.objects.filter(potencial_votante_id=pv.id).first()
        last_call = MilitantesCallInfo.objects.filter(potencial_votante_id=pv.id).first()

        def _date(d):
            return d.isoformat() if d else None

        return JsonResponse({
            'ok': True,
            'pv': {'id': pv.id, 'nome': pv.nome, 'telefone': pv.telefone, 'localidade': pv.localidade},
            'militante': {
                'nome_completo': (militante.nome_completo if militante else None) or pv.nome,
                'estado_ficha': (militante.estado_ficha if militante else None) or 'Validado',
                'tp_associado': (militante.tp_associado if militante else None) or 'Militantes',
                'estado_militante': (militante.estado_militante if militante else None) or 'A',
                'nm_pai': militante.nm_pai if militante else None,
                'nm_mae': militante.nm_mae if militante else None,
                'genero': militante.genero if militante else None,
                'agregado_familiar': militante.agregado_familiar if militante else None,
                'nr_telefone_casa': militante.nr_telefone_casa if militante else None,
                'nr_telemovel1': militante.nr_telemovel1 if militante else None,
                'nr_telemovel2': militante.nr_telemovel2 if militante else None,
                'dt_nascimento': _date(militante.dt_nascimento) if militante else None,
                'motivo_rejeicao': militante.motivo_rejeicao if militante else None,
            },
            'morada': {
                'morada_atual': morada.morada_atual if morada else None,
                'perto_de': morada.perto_de if morada else None,
            },
            'call_info': {
                'resenciado_fora_praia': bool(last_call.resenciado_fora_praia) if last_call else False,
                'resenciado': bool(last_call.resenciado) if last_call else False,
                'recetivo': bool(last_call.recetivo) if last_call else False,
                'precisa_transporte_vota': (str(last_call.precisa_transporte_vota) in ('1', 'true', 'sim', 'Sim')) if last_call else False,
                'comentario': last_call.comentario if last_call else '',
            },
        })

    # POST
    p = request.POST

    def _bool(name):
        return p.get(name, '').strip().lower() in ('1', 'true', 'on', 'yes', 'sim')

    def _int(name):
        v = p.get(name, '').strip()
        try:
            return int(v) if v else None
        except (TypeError, ValueError):
            return None

    def _str(name):
        v = p.get(name, '').strip()
        return v or None

    def _date(name):
        v = p.get(name, '').strip()
        return v or None  # Django will parse ISO string for DateField

    militante = Militantes.objects.filter(potencial_votante_id=pv.id).first()
    if not militante:
        militante = Militantes(potencial_votante_id=pv.id)

    militante.nome_completo = _str('nome_completo') or pv.nome
    militante.estado_ficha = _str('estado_ficha') or 'Validado'
    militante.tp_associado = _str('tp_associado') or 'Militantes'
    militante.estado_militante = _str('estado_militante') or 'A'
    militante.nm_pai = _str('nm_pai')
    militante.nm_mae = _str('nm_mae')
    militante.genero = _str('genero')
    militante.agregado_familiar = _int('agregado_familiar')
    militante.nr_telefone_casa = _int('nr_telefone_casa')
    militante.nr_telemovel1 = _int('nr_telemovel1')
    militante.nr_telemovel2 = _int('nr_telemovel2')
    militante.dt_nascimento = _date('dt_nascimento')
    militante.motivo_rejeicao = _str('motivo_rejeicao')
    if not militante.status:
        militante.status = 'A'
    militante.save()

    # Morada (1:1 bound to militante for this PV)
    morada = Morada.objects.filter(militante=militante).first()
    if not morada:
        morada = Morada(militante=militante, potencial_votante_id=pv.id)
    morada.morada_atual = _str('morada_atual')
    morada.perto_de = _str('perto_de')
    if not morada.status:
        morada.status = 'A'
    morada.potencial_votante_id = pv.id
    morada.save()

    # CallInfo: append a new record per submission
    from django.utils import timezone
    MilitantesCallInfo.objects.create(
        resenciado_fora_praia=1 if _bool('resenciado_fora_praia') else 0,
        resenciado=1 if _bool('resenciado') else 0,
        recetivo=1 if _bool('recetivo') else 0,
        username=((getattr(request.user, 'email', '') or request.user.get_username()) or '')[:50],
        data_hr_chamada=timezone.now().strftime('%Y-%m-%d %H:%M'),
        comentario=(p.get('comentario', '').strip() or None),
        precisa_transporte_vota=('1' if _bool('precisa_transporte_vota') else '0'),
        id_militante=militante.id,
        potencial_votante_id=pv.id,
    )

    # Mark the PV as contacted automatically
    if not pv.is_contactado:
        pv.is_contactado = True
        pv.save(update_fields=['is_contactado'])

    return JsonResponse({'ok': True, 'message': 'Inquérito guardado.'})


REJECT_REASONS = {"nao_atendeu", "nao_recetivo", "nao_encontrado"}


@login_required
def reject_call(request, id):
    """Register a 'rejected' call outcome for a potencial votante."""
    if request.method != "POST":
        return JsonResponse({'ok': False, 'error': 'Método inválido'}, status=400)

    pv = get_object_or_404(PotencialVotante, pk=id)
    reason = (request.POST.get('reason') or '').strip()
    if reason not in REJECT_REASONS:
        return JsonResponse({'ok': False, 'error': 'Motivo inválido'}, status=400)

    from django.utils import timezone
    militante = Militantes.objects.filter(potencial_votante_id=pv.id).first()
    comentario = (request.POST.get('comentario') or '').strip() or None

    kwargs = {
        'id_militante': militante.id if militante else None,
        'potencial_votante_id': pv.id,
        'username': ((getattr(request.user, 'email', '') or request.user.get_username()) or '')[:50],
        'data_hr_chamada': timezone.now().strftime('%Y-%m-%d %H:%M'),
        'comentario': comentario,
    }
    if reason == 'nao_atendeu':
        kwargs['n_atendeu'] = 1
    elif reason == 'nao_encontrado':
        kwargs['n_encontrado'] = 1
    elif reason == 'nao_recetivo':
        kwargs['recetivo'] = -1

    MilitantesCallInfo.objects.create(**kwargs)

    # Mark PV as contacted so it falls out of the default listing.
    if not pv.is_contactado:
        pv.is_contactado = True
        pv.save(update_fields=['is_contactado'])

    return JsonResponse({'ok': True, 'message': 'Chamada registada.'})


@login_required
def exportExcel(request):
    qs = PotencialVotante.objects.filter(**_build_filters(request))
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="potenciais_votantes.csv"'},
    )
    writer = csv.writer(response)
    if qs.exists():
        keys = list(model_to_dict(qs[0]).keys())
        writer.writerow([k.replace("_", " ") for k in keys])
        for i in qs:
            writer.writerow(list(model_to_dict(i).values()))
    return response


# ──────────────────────────────────────────────────────────────────────
# Async upload flow: preview → start → poll status (per file)
# ──────────────────────────────────────────────────────────────────────

def _read_excel_safe(file_obj):
    name = getattr(file_obj, 'name', '') or ''
    if name.lower().endswith('.csv'):
        return pd.read_csv(file_obj)
    return pd.read_excel(file_obj)


@login_required
@require_POST
def import_preview(request):
    f = request.FILES.get('arquivo_excel')
    if not f:
        return JsonResponse({'ok': False, 'error': 'Ficheiro não enviado.'}, status=400)
    try:
        df = _read_excel_safe(f)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': f'Não foi possível ler o ficheiro: {exc}'}, status=400)

    columns = list(df.columns)
    col_map = _build_column_map(columns)
    detected = list(col_map.keys())
    mapped_fields = {field for field, _ in col_map.values()}
    required_fields = ['nome']
    missing = [f for f in required_fields if f not in mapped_fields]
    sample = df.head(20).fillna('').astype(str).to_dict(orient='records')

    return JsonResponse({
        'ok': True,
        'total': int(len(df)),
        'columns': columns,
        'detected': detected,
        'missing': missing,
        'sample': sample,
    })


@login_required
@require_POST
def import_start(request):
    """Save one or more uploaded files and kick off background processing.

    Accepts ``arquivo_excel`` as either a single file or a list of files
    (multi-upload). Returns a list of created job ids so the frontend can
    poll each one independently.
    """
    import threading

    files = request.FILES.getlist('arquivo_excel')
    if not files:
        return JsonResponse({'ok': False, 'error': 'Ficheiro obrigatório.'}, status=400)

    overwrite = request.POST.get('overwrite', '').strip().lower() in ('1', 'true', 'on', 'yes')

    jobs = []
    for f in files:
        job = PotencialVotanteImport.objects.create(
            arquivo=f,
            nome_original=f.name,
            status=PotencialVotanteImport.STATUS_PENDING,
            criado_por=getattr(request.user, 'id', None),
        )
        job.arquivo.close()
        threading.Thread(
            target=_run_import_job,
            args=(job.id,),
            kwargs={'overwrite': overwrite},
            daemon=True,
        ).start()
        jobs.append({'job_id': job.id, 'nome': f.name})

    return JsonResponse({'ok': True, 'jobs': jobs, 'overwrite': overwrite})


@login_required
def import_status(request, job_id):
    job = get_object_or_404(PotencialVotanteImport, pk=job_id)
    return JsonResponse({
        'ok': True,
        'job_id': job.id,
        'nome_original': job.nome_original,
        'status': job.status,
        'total': job.total_linhas,
        'processed': job.processadas,
        'created': job.criadas,
        'duplicates': job.duplicadas,
        'updated': job.atualizadas,
        'errors': job.erros,
        'percent': job.percent,
        'message': job.mensagem,
    })


def _run_import_job(job_id, overwrite=False):
    from django.db import close_old_connections, transaction

    try:
        job = PotencialVotanteImport.objects.get(pk=job_id)
    except PotencialVotanteImport.DoesNotExist:
        return

    try:
        job.status = PotencialVotanteImport.STATUS_RUNNING
        job.save(update_fields=['status', 'atualizado_em'])

        with job.arquivo.open('rb') as fh:
            df = _read_excel_safe(fh)

        total = len(df)
        job.total_linhas = total
        job.save(update_fields=['total_linhas', 'atualizado_em'])

        chunk_size = 500
        created = 0
        updated = 0
        errors = 0
        duplicates = 0
        col_map = _build_column_map(df.columns)

        # Natural key for duplicate detection: (nome, telefone). Either may
        # be missing, so we only dedupe rows where both are present.
        existing_keys = set(
            PotencialVotante.objects
            .exclude(nome__isnull=True)
            .exclude(telefone__isnull=True)
            .values_list('nome', 'telefone')
        )
        seen_in_file = set()

        for chunk_start in range(0, total, chunk_size):
            chunk = df.iloc[chunk_start:chunk_start + chunk_size]
            inserts = []
            updates = []
            for _, row in chunk.iterrows():
                try:
                    kwargs = _row_to_kwargs(row, col_map)
                    # Skip rows with no name (can't identify them).
                    if not kwargs.get('nome'):
                        continue

                    nome = kwargs.get('nome')
                    telefone = kwargs.get('telefone')
                    has_key = nome is not None and telefone is not None
                    key = (nome, telefone) if has_key else None

                    if has_key and key in seen_in_file:
                        duplicates += 1
                        continue
                    if has_key and key in existing_keys:
                        if overwrite:
                            updates.append((key, kwargs))
                            seen_in_file.add(key)
                        else:
                            duplicates += 1
                        continue

                    if has_key:
                        seen_in_file.add(key)
                    inserts.append(PotencialVotante(**kwargs))
                except Exception:
                    errors += 1

            if inserts:
                with transaction.atomic():
                    for o in inserts:
                        try:
                            o.save()
                            created += 1
                        except Exception:
                            errors += 1

            if updates:
                with transaction.atomic():
                    for key, kwargs in updates:
                        try:
                            update_fields = dict(kwargs)
                            update_fields.pop('nome', None)
                            update_fields.pop('telefone', None)
                            n = PotencialVotante.objects.filter(
                                nome=key[0], telefone=key[1],
                            ).update(**update_fields) if update_fields else 0
                            if n:
                                updated += n
                        except Exception:
                            errors += 1

            job.processadas = min(chunk_start + len(chunk), total)
            job.criadas = created
            job.duplicadas = duplicates
            job.atualizadas = updated
            job.erros = errors
            job.save(update_fields=[
                'processadas', 'criadas', 'duplicadas', 'atualizadas',
                'erros', 'atualizado_em',
            ])

        job.status = PotencialVotanteImport.STATUS_DONE
        job.mensagem = (
            f'{created} criados, {updated} atualizados, '
            f'{duplicates} duplicados ignorados, {errors} erros (de {total} linhas).'
        )
        job.save(update_fields=['status', 'mensagem', 'atualizado_em'])
    except Exception as exc:
        job.status = PotencialVotanteImport.STATUS_ERROR
        job.mensagem = str(exc)[:500]
        job.save(update_fields=['status', 'mensagem', 'atualizado_em'])
    finally:
        close_old_connections()
