from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Case, Count, IntegerField, Q, Sum, When
from django.shortcuts import render
from django.utils import timezone

from apps.eleitores.models import Eleitores, Votacao
from apps.militantes.models import Militantes


def _pct(num, den):
    return round((num / den) * 100, 1) if den else 0.0


def _safe(callable_):
    try:
        return callable_()
    except Exception:
        return 0


@login_required
def index(request):
    """Aggregate KPIs for the home dashboard."""
    # ── Militantes ──────────────────────────────────────
    mil_agg = Militantes.objects.aggregate(
        total=Count('id'),
        aprovados=Sum(Case(When(estado_militante='A', then=1), default=0, output_field=IntegerField())),
        pendentes=Sum(Case(When(estado_militante='P', then=1), default=0, output_field=IntegerField())),
        rejeitados=Sum(Case(When(estado_militante='R', then=1), default=0, output_field=IntegerField())),
    )
    total_militantes = mil_agg['total'] or 0
    novos_30d = _safe(lambda: Militantes.objects.filter(
        createdat__gte=timezone.now() - timedelta(days=30)
    ).count())

    # ── Eleitores ──────────────────────────────────────
    el_agg = Eleitores.objects.filter(falecido=False).aggregate(
        total=Count('id'),
        mpd=Sum(Case(When(mpd=True, then=1), default=0, output_field=IntegerField())),
        descarga=Sum(Case(When(descarga=True, then=1), default=0, output_field=IntegerField())),
        indecisos=Sum(Case(When(indeciso=True, then=1), default=0, output_field=IntegerField())),
    )
    total_eleitores = el_agg['total'] or 0

    voted_ids = (
        Votacao.objects.filter(votou=1).exclude(anulado=1)
        .filter(nr_eleitor__gt=0)
        .values_list('nr_eleitor', flat=True).distinct()
    )
    total_votaram = Eleitores.objects.filter(
        falecido=False, nr_eleitor__in=voted_ids
    ).count()
    total_votos = Votacao.objects.filter(votou=1).exclude(anulado=1).count()
    total_anuladas = Votacao.objects.filter(anulado=1).count()
    pct_comparecimento = _pct(total_votaram, total_eleitores)

    # ── Quotas (best effort) ───────────────────────────
    pagamentos_30d, valor_30d = 0, 0
    try:
        from apps.quotas.models import PagamentoQuotas
        cutoff_date = (timezone.now() - timedelta(days=30)).date()
        pagamentos_30d = PagamentoQuotas.objects.filter(
            data_pagamento__gte=cutoff_date
        ).count()
        valor_30d = PagamentoQuotas.objects.filter(
            data_pagamento__gte=cutoff_date
        ).aggregate(t=Sum('valor__valor'))['t'] or 0
    except Exception:
        pass

    # ── Top 5 mesas ────────────────────────────────────
    top_mesas = []
    try:
        rows = (
            Eleitores.objects.filter(falecido=False)
            .exclude(nr_mesa__isnull=True).exclude(nr_mesa__exact='')
            .values('nr_mesa')
            .annotate(
                total=Count('id'),
                votaram=Count('id', filter=Q(nr_eleitor__in=voted_ids)),
            )
        )
        for r in rows:
            t, v = r['total'] or 0, r['votaram'] or 0
            top_mesas.append({'nr_mesa': r['nr_mesa'], 'total': t, 'votaram': v, 'pct': _pct(v, t)})
        top_mesas.sort(key=lambda x: (-x['pct'], -x['total']))
        top_mesas = top_mesas[:5]
    except Exception:
        top_mesas = []

    # ── Activity per day (last 14d) ────────────────────
    per_day = []
    try:
        from django.db.models.functions import TruncDate
        cutoff = timezone.now() - timedelta(days=14)
        per_day = list(
            Votacao.objects.exclude(anulado=1).filter(votou=1, datetime__gte=cutoff)
            .annotate(d=TruncDate('datetime'))
            .values('d').annotate(total=Count('id')).order_by('d')
        )
        per_day = [{'d': r['d'].isoformat() if r['d'] else None, 'total': r['total']} for r in per_day]
    except Exception:
        per_day = []

    # ── Report: militantes novos por mês (últimos 6m) ──
    novos_por_mes = []
    try:
        from django.db.models.functions import TruncMonth
        cutoff_m = timezone.now() - timedelta(days=180)
        rows = (
            Militantes.objects.filter(createdat__gte=cutoff_m)
            .annotate(m=TruncMonth('createdat'))
            .values('m').annotate(total=Count('id')).order_by('m')
        )
        novos_por_mes = [{'m': r['m'].strftime('%b/%y') if r['m'] else '', 'total': r['total']} for r in rows]
    except Exception:
        novos_por_mes = []

    # ── Report: ranking concelhos por nº eleitores ─────
    rank_concelhos = []
    try:
        rows = (
            Eleitores.objects.filter(falecido=False)
            .exclude(concelho__isnull=True).exclude(concelho__exact='')
            .values('concelho')
            .annotate(
                total=Count('id'),
                votaram=Count('id', filter=Q(nr_eleitor__in=voted_ids)),
                mpd=Sum(Case(When(mpd=True, then=1), default=0, output_field=IntegerField())),
            )
            .order_by('-total')[:8]
        )
        for r in rows:
            t, v, m = r['total'] or 0, r['votaram'] or 0, r['mpd'] or 0
            rank_concelhos.append({
                'concelho': r['concelho'], 'total': t, 'votaram': v, 'mpd': m,
                'pctVotos': _pct(v, t), 'pctMpd': _pct(m, t),
            })
    except Exception:
        rank_concelhos = []

    # ── Report: arrecadação quotas últimos 6m ──────────
    quotas_por_mes = []
    try:
        from apps.quotas.models import PagamentoQuotas
        from django.db.models.functions import TruncMonth
        cutoff_m = (timezone.now() - timedelta(days=180)).date()
        rows = (
            PagamentoQuotas.objects.filter(data_pagamento__gte=cutoff_m)
            .annotate(m=TruncMonth('data_pagamento'))
            .values('m')
            .annotate(total=Count('id'), valor=Sum('valor__valor'))
            .order_by('m')
        )
        quotas_por_mes = [{
            'm': r['m'].strftime('%b/%y') if r['m'] else '',
            'total': r['total'], 'valor': round(r['valor'] or 0, 2),
        } for r in rows]
    except Exception:
        quotas_por_mes = []

    context = {
        'segment': 'index',
        'milTotal': total_militantes,
        'milAprovados': mil_agg['aprovados'] or 0,
        'milPendentes': mil_agg['pendentes'] or 0,
        'milRejeitados': mil_agg['rejeitados'] or 0,
        'milNovos30d': novos_30d,
        'pctMilAprovados': _pct(mil_agg['aprovados'] or 0, total_militantes),
        'elTotal': total_eleitores,
        'elMpd': el_agg['mpd'] or 0,
        'elIndecisos': el_agg['indecisos'] or 0,
        'elDescarga': el_agg['descarga'] or 0,
        'elVotaram': total_votaram,
        'elNaoVotaram': max(total_eleitores - total_votaram, 0),
        'pctComparecimento': pct_comparecimento,
        'pctMpd': _pct(el_agg['mpd'] or 0, total_eleitores),
        'votosTotal': total_votos,
        'votosAnuladas': total_anuladas,
        'pagamentos30d': pagamentos_30d,
        'valor30d': round(valor_30d, 2),
        'topMesas': top_mesas,
        'perDay': per_day,
        'novosPorMes': novos_por_mes,
        'rankConcelhos': rank_concelhos,
        'quotasPorMes': quotas_por_mes,
    }
    return render(request, "pages/index.html", context)


def tables(request):
    return render(request, "pages/dynamic-tables.html", {'segment': 'tables'})
