from django.conf import settings
from django.db import models

from apps.eleitores.models import Eleitores
from apps.militantes.models import Militantes


class EleitorMilitanteMatch(models.Model):
    """Link table between an `Eleitores` row and a `Militantes` row.

    A match is created either by the automatic matcher (with a confidence
    score) or manually from the UI. Confirming a match also persists the
    relation back to ``eleitores.militante_id_id`` so the rest of the app
    keeps working unchanged.
    """

    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendente"),
        (STATUS_CONFIRMED, "Confirmado"),
        (STATUS_REJECTED, "Rejeitado"),
    ]

    SOURCE_AUTO = "auto"
    SOURCE_MANUAL = "manual"
    SOURCE_CHOICES = [
        (SOURCE_AUTO, "Automático"),
        (SOURCE_MANUAL, "Manual"),
    ]

    eleitor = models.ForeignKey(
        Eleitores,
        on_delete=models.CASCADE,
        related_name="militante_matches",
    )
    militante = models.ForeignKey(
        Militantes,
        on_delete=models.CASCADE,
        related_name="eleitor_matches",
    )

    score = models.FloatField(default=0.0, help_text="Pontuação 0-100")
    score_nome = models.FloatField(default=0.0)
    score_pai = models.FloatField(default=0.0)
    score_mae = models.FloatField(default=0.0)
    dt_nascimento_match = models.BooleanField(default=False)

    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    source = models.CharField(
        max_length=10, choices=SOURCE_CHOICES, default=SOURCE_AUTO
    )
    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_militante_matches",
    )

    class Meta:
        db_table = "militante_match"
        constraints = [
            models.UniqueConstraint(
                fields=["eleitor", "militante"],
                name="uniq_eleitor_militante_match",
            ),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["eleitor", "status"]),
            models.Index(fields=["score"]),
        ]
        ordering = ["-score", "-created_at"]

    def __str__(self):
        return f"Eleitor #{self.eleitor_id} ↔ Militante #{self.militante_id} ({self.score:.1f})"
