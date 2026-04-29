"""Run the eleitor ↔ militante matcher in batch.

Usage::

    python manage.py match_eleitores [--min-score 65] [--auto-confirm 92]
                                     [--only-unmatched] [--limit N]
                                     [--dry-run]
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.eleitores.models import Eleitores

from ...matching import (
    AUTO_CONFIRM_SCORE,
    MIN_SCORE,
    MilitanteIndex,
    find_best_matches,
)
from ...models import EleitorMilitanteMatch


class Command(BaseCommand):
    help = "Compute fuzzy matches between Eleitores and Militantes."

    def add_arguments(self, parser):
        parser.add_argument("--min-score", type=float, default=MIN_SCORE)
        parser.add_argument("--auto-confirm", type=float, default=AUTO_CONFIRM_SCORE)
        parser.add_argument(
            "--only-unmatched", action="store_true",
            help="Skip eleitores already linked to a militante.",
        )
        parser.add_argument(
            "--limit", type=int, default=0,
            help="Process at most N eleitores (0 = no limit).",
        )
        parser.add_argument(
            "--top", type=int, default=3,
            help="Persist at most this many candidates per eleitor.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        min_score = opts["min_score"]
        auto_confirm = opts["auto_confirm"]
        only_unmatched = opts["only_unmatched"]
        limit = opts["limit"]
        top = opts["top"]
        dry_run = opts["dry_run"]

        self.stdout.write("Carregando militantes…")
        index = MilitanteIndex()
        self.stdout.write(f"  → {len(index.by_id)} militantes indexados")

        qs = Eleitores.objects.all()
        if only_unmatched:
            qs = qs.filter(militante_id__isnull=True)
        if limit:
            qs = qs[:limit]

        total = qs.count() if not limit else min(limit, qs.count())
        self.stdout.write(f"Processando {total} eleitores…")

        created = 0
        updated = 0
        confirmed = 0
        scanned = 0
        now = timezone.now()

        for eleitor in qs.iterator(chunk_size=500):
            scanned += 1
            results = find_best_matches(
                eleitor, index, limit=top, min_score=min_score,
            )
            if not results:
                continue

            best_militante, best_score = results[0]

            if dry_run:
                self.stdout.write(
                    f"  [{eleitor.id}] {eleitor.nome!r} → "
                    f"{best_militante.nome_completo!r} ({best_score.score})"
                )
                continue

            with transaction.atomic():
                for cand, sc in results:
                    obj, was_created = EleitorMilitanteMatch.objects.update_or_create(
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

                # Auto-confirm only if best score is very high AND clearly
                # better than the runner-up (delta ≥ 5) to avoid ambiguity.
                runner_up = results[1][1].score if len(results) > 1 else 0.0
                if (
                    best_score.score >= auto_confirm
                    and best_score.score - runner_up >= 5.0
                    and not eleitor.militante_id_id
                ):
                    match = EleitorMilitanteMatch.objects.get(
                        eleitor=eleitor, militante=best_militante,
                    )
                    if match.status != EleitorMilitanteMatch.STATUS_CONFIRMED:
                        match.status = EleitorMilitanteMatch.STATUS_CONFIRMED
                        match.confirmed_at = now
                        match.save(update_fields=["status", "confirmed_at"])
                    Eleitores.objects.filter(pk=eleitor.pk).update(
                        militante_id_id=best_militante.id,
                    )
                    confirmed += 1

            if scanned % 500 == 0:
                self.stdout.write(
                    f"  …{scanned}/{total} (criados={created}, "
                    f"atualizados={updated}, confirmados={confirmed})"
                )

        self.stdout.write(self.style.SUCCESS(
            f"Concluído. Eleitores analisados={scanned}, "
            f"matches criados={created}, atualizados={updated}, "
            f"auto-confirmados={confirmed}."
        ))
