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
    'concelho':      ('concelho', 'str'),
    'concelhos':     ('concelho', 'str'),
    'municipio':     ('concelho', 'str'),
    'município':     ('concelho', 'str'),
    'programa':      ('programa', 'str'),
    'programas':     ('programa', 'str'),
    'plano':         ('programa', 'str'),
    'assinatura':    ('assinatura', 'bool'),
    'is contactado': ('is_contactado', 'bool'),
    'contactado':    ('is_contactado', 'bool'),
    'contactados':   ('is_contactado', 'bool'),
    'telefone':      ('telefone', 'str'),
    'tel':           ('telefone', 'str'),
    'tel.':          ('telefone', 'str'),
    'telemovel':     ('telefone', 'str'),
    'telemóvel':     ('telefone', 'str'),
    'telm':          ('telefone', 'str'),
    'telm.':         ('telefone', 'str'),
    'celular':       ('telefone', 'str'),
    'cel':           ('telefone', 'str'),
    'cel.':          ('telefone', 'str'),
    'movel':         ('telefone', 'str'),
    'móvel':         ('telefone', 'str'),
    'numero':        ('telefone', 'str'),
    'número':        ('telefone', 'str'),
    'n.':            ('telefone', 'str'),
    'nº':            ('telefone', 'str'),
    'no':            ('telefone', 'str'),
    'no.':           ('telefone', 'str'),
    'n telefone':    ('telefone', 'str'),
    'n. telefone':   ('telefone', 'str'),
    'nº telefone':   ('telefone', 'str'),
    'no telefone':   ('telefone', 'str'),
    'numero telefone': ('telefone', 'str'),
    'número telefone': ('telefone', 'str'),
    'phone':         ('telefone', 'str'),
    'mobile':        ('telefone', 'str'),
    'contato':       ('telefone', 'str'),
    'contacto':      ('telefone', 'str'),
    'contactos':     ('telefone', 'str'),
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
    # pandas sometimes emits "912345678.0" for integer-valued numeric cells
    # even when dtype=str is forced. Drop the trailing ".0" so phone numbers
    # and similar identifiers keep their original form.
    if s.endswith('.0') and s[:-2].lstrip('-').isdigit():
        s = s[:-2]
    return s


def _norm_phone(value):
    """Normalize a phone number for key comparison.

    Strips ALL whitespace so ``"912 345 678"`` and ``"912345678"`` compare
    equal. Returns ``""`` when the input is empty/None.
    """
    if value is None:
        return ''
    return ''.join(str(value).split())


def _row_to_kwargs(row, col_map):
    kwargs = {}
    for col, (field, kind) in col_map.items():
        if col not in row.index:
            continue
        coerced = _coerce_value(row[col], kind)
        if coerced is None:
            continue
        # Telefone often comes in with inconsistent spacing
        # ("912 345 678" vs "912345678"). Strip ALL whitespace so the value
        # is comparable as a key (used for update-by-telefone) and matches
        # cleanly across files.
        if field == 'telefone' and isinstance(coerced, str):
            coerced = _norm_phone(coerced)
            if not coerced:
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
    if programa := request.GET.get("programa", ""):
        filters['programa__icontains'] = programa
    if concelho := request.GET.get("concelho", ""):
        filters['concelho__icontains'] = concelho
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
    """Read Excel/CSV preserving cell text.

    We force dtype=str so phone numbers (often parsed as float by pandas,
    e.g. ``912345678`` → ``912345678.0`` or scientific notation) keep their
    original textual form. NaN cells become the literal string ``"nan"``;
    ``_coerce_value`` already handles that case.
    """
    name = getattr(file_obj, 'name', '') or ''
    if name.lower().endswith('.csv'):
        return pd.read_csv(file_obj, dtype=str, keep_default_na=False)
    return pd.read_excel(file_obj, dtype=str, keep_default_na=False)


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

    # Strip whitespace from phone-mapped columns so the preview shows the
    # exact value that will be persisted (matches _row_to_kwargs behaviour).
    phone_cols = [col for col, (field, _) in col_map.items() if field == 'telefone']
    if phone_cols:
        for row in sample:
            for col in phone_cols:
                if col in row and isinstance(row[col], str):
                    row[col] = _norm_phone(row[col])

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
    update_by_phone = request.POST.get('update_by_phone', '').strip().lower() in ('1', 'true', 'on', 'yes')

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
            kwargs={'overwrite': overwrite, 'update_by_phone': update_by_phone},
            daemon=True,
        ).start()
        jobs.append({'job_id': job.id, 'nome': f.name})

    return JsonResponse({'ok': True, 'jobs': jobs, 'overwrite': overwrite, 'update_by_phone': update_by_phone})


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


def _run_import_job(job_id, overwrite=False, update_by_phone=False):
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
        # Set of telefone values currently in DB. Used by update_by_phone mode
        # so we can decide INSERT vs UPDATE per row. The actual update is done
        # via filter(telefone=tel).update(...) so the matching is done by the
        # database, not by an id we cached. This keeps the rule simple:
        #     KEY = telefone -> telefone
        # If somehow several DB rows share the same phone (shouldn't happen
        # after dedupe), they all stay in sync.
        existing_phones = set()
        # Fallback (nome, localidade) keys: only DB rows without a telefone
        # are candidates. We deliberately exclude rows that DO have a phone
        # so we never overwrite a different real person who happens to share
        # nome+localidade.
        existing_no_phone_keys = set()
        if update_by_phone:
            existing_phones = set(
                _norm_phone(t)
                for t in (PotencialVotante.objects
                          .exclude(telefone__isnull=True)
                          .exclude(telefone__exact='')
                          .values_list('telefone', flat=True))
                if _norm_phone(t)
            )
            from django.db.models import Q
            existing_no_phone_keys = set(
                PotencialVotante.objects
                .filter(Q(telefone__isnull=True) | Q(telefone__exact=''))
                .exclude(nome__isnull=True)
                .exclude(nome__exact='')
                .values_list('nome', 'localidade')
            )
        seen_in_file = set()
        seen_phone_in_file = set()
        seen_no_phone_in_file = set()

        for chunk_start in range(0, total, chunk_size):
            chunk = df.iloc[chunk_start:chunk_start + chunk_size]
            inserts = []
            updates = []           # legacy (nome, telefone) overwrite
            phone_updates = []     # telefone-keyed update list (telefone, kwargs)
            no_phone_updates = []  # (nome, localidade)-keyed update list when row has no telefone
            for _, row in chunk.iterrows():
                try:
                    kwargs = _row_to_kwargs(row, col_map)
                    # Skip rows with no name (can't identify them).
                    if not kwargs.get('nome'):
                        continue

                    nome = kwargs.get('nome')
                    telefone = kwargs.get('telefone')

                    # ----- Branch 1: update-by-telefone mode -----
                    if update_by_phone and telefone:
                        if telefone in seen_phone_in_file:
                            duplicates += 1
                            continue
                        seen_phone_in_file.add(telefone)
                        if telefone in existing_phones:
                            phone_updates.append((telefone, kwargs))
                            continue
                        # No existing PV with this phone -> fall through to insert.

                    # ----- Branch 1b: update_by_phone ON but row has no
                    # telefone -> fall back to (nome, localidade) key so we
                    # don't keep duplicating phoneless rows on every import.
                    if update_by_phone and not telefone:
                        localidade = kwargs.get('localidade')
                        np_key = (nome, localidade)
                        if np_key in seen_no_phone_in_file:
                            duplicates += 1
                            continue
                        seen_no_phone_in_file.add(np_key)
                        if np_key in existing_no_phone_keys:
                            no_phone_updates.append((nome, localidade, kwargs))
                            continue
                        # Not in DB yet: insert new and remember the key so
                        # later rows in the same file with the same key are
                        # treated as duplicates instead of inserting again.
                        existing_no_phone_keys.add(np_key)
                        inserts.append(PotencialVotante(**kwargs))
                        continue

                    # ----- Branch 2: legacy (nome, telefone) handling -----
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
                            # Track newly inserted phone so a later row in the
                            # same file with the same phone updates it instead
                            # of creating a duplicate.
                            if update_by_phone and o.telefone:
                                existing_phones.add(o.telefone)
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

            if phone_updates:
                with transaction.atomic():
                    for telefone_key, kwargs in phone_updates:
                        try:
                            update_fields = dict(kwargs)
                            # Telefone IS the key; never rewrite it.
                            update_fields.pop('telefone', None)
                            if not update_fields:
                                continue
                            # Match by telefone (the key). If multiple rows
                            # share the same phone, all of them get the same
                            # update — keeps "duplicates" in sync.
                            n = PotencialVotante.objects.filter(
                                telefone=telefone_key,
                            ).update(**update_fields)
                            if n:
                                updated += n
                        except Exception:
                            errors += 1

            if no_phone_updates:
                from django.db.models import Q
                with transaction.atomic():
                    for nome_key, localidade_key, kwargs in no_phone_updates:
                        try:
                            update_fields = dict(kwargs)
                            # Nome+localidade form the key here; don't rewrite
                            # them. Telefone is empty by definition.
                            update_fields.pop('nome', None)
                            update_fields.pop('localidade', None)
                            update_fields.pop('telefone', None)
                            if not update_fields:
                                continue
                            qs = PotencialVotante.objects.filter(nome=nome_key).filter(
                                Q(telefone__isnull=True) | Q(telefone__exact='')
                            )
                            if localidade_key is None:
                                qs = qs.filter(Q(localidade__isnull=True) | Q(localidade__exact=''))
                            else:
                                qs = qs.filter(localidade=localidade_key)
                            n = qs.update(**update_fields)
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
