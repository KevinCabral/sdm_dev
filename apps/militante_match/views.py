"""Views for the eleitor ↔ militante matching workflow."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.eleitores.models import Eleitores
from apps.militantes.models import Militantes

from .matching import (
    AUTO_CONFIRM_SCORE,
    MIN_SCORE,
    MilitanteIndex,
    find_best_matches,
    parse_filiacao,
    score_pair,
)
from .models import EleitorMilitanteMatch


def _breadcrumbs(*extra):
    bc = [
        {"title": "Pagina Inicial", "url": "/"},
        {"title": "Correspondências", "url": "/militante-match/"},
    ]
    bc.extend(extra)
    return bc


@login_required
def dashboard(request):
    """Overview + entry point to launch matching."""
    stats = EleitorMilitanteMatch.objects.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=EleitorMilitanteMatch.STATUS_PENDING)),
        confirmed=Count("id", filter=Q(status=EleitorMilitanteMatch.STATUS_CONFIRMED)),
        rejected=Count("id", filter=Q(status=EleitorMilitanteMatch.STATUS_REJECTED)),
    )
    eleitores_total = Eleitores.objects.filter(falecido=False).count()
    eleitores_linked = (
        Eleitores.objects.filter(falecido=False)
        .exclude(militante_id__isnull=True)
        .count()
    )
    militantes_total = Militantes.objects.count()

    ctx = {
        "stats": stats,
        "eleitores_total": eleitores_total,
        "eleitores_linked": eleitores_linked,
        "eleitores_pending": eleitores_total - eleitores_linked,
        "militantes_total": militantes_total,
        "min_score": MIN_SCORE,
        "auto_confirm_score": AUTO_CONFIRM_SCORE,
        "breadcrumbs": _breadcrumbs({"title": "Dashboard"}),
    }
    return render(request, "pages/militante_match/dashboard.html", ctx)


@login_required
def index(request):
    """Listagem de matches (com filtros)."""
    status = request.GET.get("status", EleitorMilitanteMatch.STATUS_PENDING)
    search = request.GET.get("q", "").strip()
    min_score_q = request.GET.get("min_score")

    qs = (
        EleitorMilitanteMatch.objects
        .select_related("eleitor", "militante")
    )
    if status in dict(EleitorMilitanteMatch.STATUS_CHOICES):
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(
            Q(eleitor__nome__icontains=search)
            | Q(militante__nome_completo__icontains=search)
        )
    if min_score_q:
        try:
            qs = qs.filter(score__gte=float(min_score_q))
        except ValueError:
            pass

    paginator = Paginator(qs.order_by("-score", "-created_at"), 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    ctx = {
        "page_obj": page_obj,
        "status": status,
        "search": search,
        "min_score": min_score_q or "",
        "statuses": EleitorMilitanteMatch.STATUS_CHOICES,
        "breadcrumbs": _breadcrumbs({"title": "Lista"}),
    }
    return render(request, "pages/militante_match/index.html", ctx)


@login_required
@require_POST
def confirm(request, match_id):
    match = get_object_or_404(EleitorMilitanteMatch, pk=match_id)
    with transaction.atomic():
        match.status = EleitorMilitanteMatch.STATUS_CONFIRMED
        match.confirmed_at = timezone.now()
        match.confirmed_by = request.user if request.user.is_authenticated else None
        match.save(update_fields=["status", "confirmed_at", "confirmed_by"])
        # Reflect on the legacy FK column for the rest of the app.
        Eleitores.objects.filter(pk=match.eleitor_id).update(
            militante_id_id=match.militante_id,
        )
        # Mark sibling candidates for the same eleitor as rejected.
        EleitorMilitanteMatch.objects.filter(
            eleitor_id=match.eleitor_id,
        ).exclude(pk=match.pk).update(
            status=EleitorMilitanteMatch.STATUS_REJECTED,
        )
    messages.success(request, "Correspondência confirmada.")
    return redirect(request.META.get("HTTP_REFERER") or "militante_match.index")


@login_required
@require_POST
def reject(request, match_id):
    match = get_object_or_404(EleitorMilitanteMatch, pk=match_id)
    match.status = EleitorMilitanteMatch.STATUS_REJECTED
    match.save(update_fields=["status"])
    messages.info(request, "Correspondência rejeitada.")
    return redirect(request.META.get("HTTP_REFERER") or "militante_match.index")


@login_required
@require_POST
def reset(request, match_id):
    """Re-open a previously confirmed/rejected match."""
    match = get_object_or_404(EleitorMilitanteMatch, pk=match_id)
    was_confirmed = match.status == EleitorMilitanteMatch.STATUS_CONFIRMED
    match.status = EleitorMilitanteMatch.STATUS_PENDING
    match.confirmed_at = None
    match.confirmed_by = None
    match.save(update_fields=["status", "confirmed_at", "confirmed_by"])
    if was_confirmed:
        # Clear the legacy FK only if it currently points to this militante.
        Eleitores.objects.filter(
            pk=match.eleitor_id, militante_id_id=match.militante_id,
        ).update(militante_id_id=None)
    messages.info(request, "Correspondência reaberta.")
    return redirect(request.META.get("HTTP_REFERER") or "militante_match.index")


@login_required
def manual_match(request, eleitor_id):
    """Manual matching screen for a given eleitor.

    Shows top automatic candidates plus a free-text search to pick any
    militante.
    """
    eleitor = get_object_or_404(Eleitores, pk=eleitor_id)
    pai, mae = parse_filiacao(eleitor.filiacao)

    # Top auto-suggestions (computed on the fly, no need to be persisted).
    index = MilitanteIndex()
    suggestions_raw = find_best_matches(eleitor, index, limit=10, min_score=0)

    # Persist suggestions so the list view stays in sync.
    suggestions = []
    for militante, sc in suggestions_raw:
        match, _ = EleitorMilitanteMatch.objects.get_or_create(
            eleitor=eleitor, militante=militante,
            defaults={
                "score": sc.score,
                "score_nome": sc.score_nome,
                "score_pai": sc.score_pai,
                "score_mae": sc.score_mae,
                "dt_nascimento_match": sc.dt_match,
                "source": EleitorMilitanteMatch.SOURCE_AUTO,
            },
        )
        suggestions.append((militante, sc, match))

    # Free-text search for an arbitrary militante.
    search = request.GET.get("q", "").strip()
    extra_results = []
    if search:
        extra_results = list(
            Militantes.objects.filter(
                Q(nome_completo__icontains=search)
                | Q(nm_pai__icontains=search)
                | Q(nm_mae__icontains=search)
            )[:25]
        )

    ctx = {
        "eleitor": eleitor,
        "pai": pai,
        "mae": mae,
        "suggestions": suggestions,
        "search": search,
        "extra_results": extra_results,
        "breadcrumbs": _breadcrumbs(
            {"title": "Lista", "url": "/militante-match/"},
            {"title": eleitor.nome or f"Eleitor #{eleitor.pk}"},
        ),
    }
    return render(request, "pages/militante_match/manual.html", ctx)


@login_required
@require_POST
def manual_link(request, eleitor_id):
    """Link a chosen militante to the eleitor (creates or updates a match)."""
    eleitor = get_object_or_404(Eleitores, pk=eleitor_id)
    militante_id = request.POST.get("militante_id")
    if not militante_id:
        messages.error(request, "Militante não informado.")
        return redirect("militante_match.manual_match", eleitor_id=eleitor.id)

    militante = get_object_or_404(Militantes, pk=militante_id)
    sc = score_pair(eleitor, militante)

    with transaction.atomic():
        match, _ = EleitorMilitanteMatch.objects.update_or_create(
            eleitor=eleitor, militante=militante,
            defaults={
                "score": sc.score,
                "score_nome": sc.score_nome,
                "score_pai": sc.score_pai,
                "score_mae": sc.score_mae,
                "dt_nascimento_match": sc.dt_match,
                "source": EleitorMilitanteMatch.SOURCE_MANUAL,
                "status": EleitorMilitanteMatch.STATUS_CONFIRMED,
                "confirmed_at": timezone.now(),
                "confirmed_by": request.user if request.user.is_authenticated else None,
            },
        )
        Eleitores.objects.filter(pk=eleitor.pk).update(
            militante_id_id=militante.id,
        )
        EleitorMilitanteMatch.objects.filter(
            eleitor_id=eleitor.pk,
        ).exclude(pk=match.pk).update(
            status=EleitorMilitanteMatch.STATUS_REJECTED,
        )
    messages.success(request, "Militante associado ao eleitor.")
    return redirect("militante_match.manual_match", eleitor_id=eleitor.id)


@login_required
@require_POST
def run_batch(request):
    """Trigger a synchronous batch matching run.

    Suitable for moderate datasets. For large databases prefer the
    ``match_eleitores`` management command via cron / async worker.
    """
    only_unmatched = request.POST.get("only_unmatched", "1") == "1"
    try:
        limit = int(request.POST.get("limit") or 0)
    except ValueError:
        limit = 0

    index = MilitanteIndex()
    qs = Eleitores.objects.filter(falecido=False)
    if only_unmatched:
        qs = qs.filter(militante_id__isnull=True)
    if limit > 0:
        qs = qs[:limit]

    created = updated = confirmed = scanned = 0
    now = timezone.now()
    for eleitor in qs.iterator(chunk_size=500):
        scanned += 1
        results = find_best_matches(eleitor, index, limit=3, min_score=MIN_SCORE)
        if not results:
            continue
        with transaction.atomic():
            for cand, sc in results:
                _, was_created = EleitorMilitanteMatch.objects.update_or_create(
                    eleitor=eleitor, militante=cand,
                    defaults={
                        "score": sc.score,
                        "score_nome": sc.score_nome,
                        "score_pai": sc.score_pai,
                        "score_mae": sc.score_mae,
                        "dt_nascimento_match": sc.dt_match,
                        "source": EleitorMilitanteMatch.SOURCE_AUTO,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            best_militante, best_score = results[0]
            runner_up = results[1][1].score if len(results) > 1 else 0.0
            if (
                best_score.score >= AUTO_CONFIRM_SCORE
                and best_score.score - runner_up >= 5.0
                and not eleitor.militante_id_id
            ):
                EleitorMilitanteMatch.objects.filter(
                    eleitor=eleitor, militante=best_militante,
                ).update(
                    status=EleitorMilitanteMatch.STATUS_CONFIRMED,
                    confirmed_at=now,
                )
                Eleitores.objects.filter(pk=eleitor.pk).update(
                    militante_id_id=best_militante.id,
                )
                confirmed += 1

    messages.success(
        request,
        f"Análise concluída: {scanned} eleitores analisados, "
        f"{created} novos matches, {updated} atualizados, "
        f"{confirmed} auto-confirmados.",
    )
    return redirect("militante_match.dashboard")


@login_required
def militante_search_json(request):
    """JSON endpoint for the manual matching page (live search)."""
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    qs = Militantes.objects.filter(
        Q(nome_completo__icontains=q)
        | Q(nm_pai__icontains=q)
        | Q(nm_mae__icontains=q)
    )[:20]
    return JsonResponse({
        "results": [
            {
                "id": m.id,
                "nome_completo": m.nome_completo,
                "nm_pai": m.nm_pai,
                "nm_mae": m.nm_mae,
                "dt_nascimento": m.dt_nascimento.isoformat() if m.dt_nascimento else None,
            }
            for m in qs
        ]
    })
