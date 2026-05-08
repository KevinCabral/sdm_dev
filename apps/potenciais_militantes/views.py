"""Views for the Potenciais Militantes (Call Center) module.

Lists existing ``Militantes`` records so the call-center team can run an
inquérito against each one. Updates write to the existing ``morada`` and
``militantes_call_info`` tables (FKs ``militante_id`` and ``id_militante``
respectively).
"""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.militantes.models import Militantes, Morada, MilitantesCallInfo


def _build_filters(request):
    """Return (Q nome filter, dict of other filters, contactado flag)."""
    nome = request.GET.get("nome", "").strip()
    estado = request.GET.get("estado", "A")
    regiao = request.GET.get("regiao", "").strip()
    concelho = request.GET.get("concelho", "").strip()
    localidade = request.GET.get("localidade", "").strip()

    q_nome = Q()
    if nome:
        q_nome = Q(nome_completo__icontains=nome) | Q(alcunha__icontains=nome)

    extra = {}
    if estado:
        extra["estado_militante"] = estado
    if regiao:
        extra["morada__geografia__ilha__icontains"] = regiao
    if concelho:
        extra["morada__geografia__concelho__icontains"] = concelho
    if localidade:
        extra["morada__geografia__freguesia__icontains"] = localidade

    only_contacted = request.GET.get("contactado", "false") == "true"
    return q_nome, extra, only_contacted


@login_required
def index(request):
    q_nome, extra, only_contacted = _build_filters(request)

    has_call = MilitantesCallInfo.objects.filter(id_militante=OuterRef("pk"))
    qs = (
        Militantes.objects
        .filter(q_nome, **extra)
        .annotate(has_call=Exists(has_call))
        .order_by("nome_completo")
        .distinct()
    )
    # Hide already-contacted militantes by default; the filter switch
    # inverts the behaviour to show only contacted ones.
    if only_contacted:
        qs = qs.filter(has_call=True)
    else:
        qs = qs.filter(has_call=False)

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    breadcrumbs = [
        {"title": "Pagina Inicial", "url": "/"},
        {"title": "Call Center"},
        {"title": "Potenciais Militantes"},
    ]
    return render(
        request,
        "pages/potenciais_militantes/index.html",
        {"page_obj": page_obj, "breadcrumbs": breadcrumbs},
    )


@login_required
def inquerito(request, id):
    """Inquérito modal endpoint for a Militante.

    GET  → returns militante / morada / latest call-info data so the form
           can be pre-filled.
    POST → upserts the Morada bound to the militante and inserts a new
           MilitantesCallInfo row (FK id_militante).
    """
    militante = get_object_or_404(Militantes, pk=id)

    if request.method == "GET":
        morada = Morada.objects.filter(militante=militante).first()
        last_call = MilitantesCallInfo.objects.filter(id_militante=militante.id).first()

        def _date(d):
            return d.isoformat() if d else None

        return JsonResponse({
            "ok": True,
            "militante": {
                "id": militante.id,
                "nome_completo": militante.nome_completo,
                "estado_ficha": militante.estado_ficha or "Validado",
                "tp_associado": militante.tp_associado or "Militantes",
                "estado_militante": militante.estado_militante or "A",
                "nm_pai": militante.nm_pai,
                "nm_mae": militante.nm_mae,
                "genero": militante.genero,
                "agregado_familiar": militante.agregado_familiar,
                "nr_telefone_casa": militante.nr_telefone_casa,
                "nr_telemovel1": militante.nr_telemovel1,
                "nr_telemovel2": militante.nr_telemovel2,
                "dt_nascimento": _date(militante.dt_nascimento),
                "motivo_rejeicao": militante.motivo_rejeicao,
            },
            "morada": {
                "morada_atual": morada.morada_atual if morada else None,
                "perto_de": morada.perto_de if morada else None,
            },
            "call_info": {
                "resenciado_fora_praia": bool(last_call.resenciado_fora_praia) if last_call else False,
                "resenciado": bool(last_call.resenciado) if last_call else False,
                "recetivo": bool(last_call.recetivo) if last_call else False,
                "precisa_transporte_vota": (str(last_call.precisa_transporte_vota) in ("1", "true", "sim", "Sim")) if last_call else False,
                "comentario": last_call.comentario if last_call else "",
            },
        })

    # POST
    p = request.POST

    def _bool(name):
        return p.get(name, "").strip().lower() in ("1", "true", "on", "yes", "sim")

    def _str(name):
        v = p.get(name, "").strip()
        return v or None

    def _int(name):
        v = p.get(name, "").strip()
        try:
            return int(v) if v else None
        except (TypeError, ValueError):
            return None

    # Update editable Militante fields
    militante.nome_completo = _str("nome_completo") or militante.nome_completo
    militante.estado_ficha = _str("estado_ficha") or militante.estado_ficha or "Validado"
    militante.tp_associado = _str("tp_associado") or militante.tp_associado or "Militantes"
    militante.estado_militante = _str("estado_militante") or militante.estado_militante or "A"
    militante.nm_pai = _str("nm_pai")
    militante.nm_mae = _str("nm_mae")
    militante.genero = _str("genero")
    militante.agregado_familiar = _int("agregado_familiar")
    militante.dt_nascimento = _str("dt_nascimento")
    militante.motivo_rejeicao = _str("motivo_rejeicao")
    militante.nr_telefone_casa = _int("nr_telefone_casa")
    militante.nr_telemovel1 = _int("nr_telemovel1")
    militante.nr_telemovel2 = _int("nr_telemovel2")
    militante.save()

    # Update Morada (1 per militante)
    morada = Morada.objects.filter(militante=militante).first()
    if not morada:
        morada = Morada(militante=militante)
    morada.morada_atual = _str("morada_atual")
    morada.perto_de = _str("perto_de")
    if not morada.status:
        morada.status = "A"
    morada.save()

    # CallInfo: append a new record per submission
    MilitantesCallInfo.objects.create(
        resenciado_fora_praia=1 if _bool("resenciado_fora_praia") else 0,
        resenciado=1 if _bool("resenciado") else 0,
        recetivo=1 if _bool("recetivo") else 0,
        username=((getattr(request.user, "email", "") or request.user.get_username()) or "")[:50],
        data_hr_chamada=timezone.now().strftime("%Y-%m-%d %H:%M"),
        comentario=(p.get("comentario", "").strip() or None),
        precisa_transporte_vota=("1" if _bool("precisa_transporte_vota") else "0"),
        id_militante=militante.id,
    )

    return JsonResponse({"ok": True, "message": "Inquérito guardado."})


REJECT_REASONS = {"nao_atendeu", "nao_recetivo", "nao_encontrado"}


@login_required
def reject_call(request, id):
    """Register a 'rejected' call outcome for a militante.

    Reasons:
      - nao_atendeu     → n_atendeu = 1
      - nao_encontrado  → n_encontrado = 1
      - nao_recetivo    → recetivo = -1 (and free-text comentário)
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método inválido"}, status=400)

    militante = get_object_or_404(Militantes, pk=id)
    reason = (request.POST.get("reason") or "").strip()
    if reason not in REJECT_REASONS:
        return JsonResponse({"ok": False, "error": "Motivo inválido"}, status=400)

    comentario = (request.POST.get("comentario") or "").strip() or None

    kwargs = {
        "id_militante": militante.id,
        "username": ((getattr(request.user, "email", "") or request.user.get_username()) or "")[:50],
        "data_hr_chamada": timezone.now().strftime("%Y-%m-%d %H:%M"),
        "comentario": comentario,
    }
    if reason == "nao_atendeu":
        kwargs["n_atendeu"] = 1
    elif reason == "nao_encontrado":
        kwargs["n_encontrado"] = 1
    elif reason == "nao_recetivo":
        kwargs["recetivo"] = -1

    MilitantesCallInfo.objects.create(**kwargs)
    return JsonResponse({"ok": True, "message": "Chamada registada."})
