from django.db import models


class PotencialVotante(models.Model):
    """A potential voter contacted by the Call Center.

    Schema mirrors the upload spreadsheet columns:
      NOME · LOCALIDADE · ASSINATURA · TELEFONE
    plus a few operational fields (notes, soft-delete, audit timestamps).
    """

    nome = models.CharField(max_length=255, blank=True, null=True)
    localidade = models.CharField(max_length=255, blank=True, null=True)
    telefone = models.CharField(max_length=64, blank=True, null=True)

    # Optional contextual data (added later — see migration 0003).
    programa = models.CharField(max_length=255, blank=True, null=True)
    concelho = models.CharField(max_length=255, blank=True, null=True)

    # ASSINATURA in the source sheet is "did the contact sign?". Stored as a
    # boolean so it can drive filters/badges; True when the cell is non-empty
    # or contains an affirmative value.
    assinatura = models.BooleanField(default=False)

    # Whether the call-center has already reached this person.
    # Stored as boolean; spreadsheet uses 0/1, displayed as Não/Sim.
    is_contactado = models.BooleanField(default=False)

    observacao = models.TextField(blank=True, default="")

    # Soft-delete flag (kept hidden from the listing).
    ativo = models.BooleanField(default=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "potencial_votante"
        ordering = ["-criado_em"]

    def __str__(self):
        return self.nome or f"Potencial Votante #{self.pk}"


class PotencialVotanteImport(models.Model):
    """Tracks an Excel/CSV import of potenciais votantes (Call Center)."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendente"),
        (STATUS_RUNNING, "Em curso"),
        (STATUS_DONE, "Concluído"),
        (STATUS_ERROR, "Erro"),
    ]

    arquivo = models.FileField(upload_to="potenciais_votantes_imports/", null=True, blank=True)
    nome_original = models.CharField(max_length=255, blank=True, default="")

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    total_linhas = models.IntegerField(default=0)
    processadas = models.IntegerField(default=0)
    criadas = models.IntegerField(default=0)
    duplicadas = models.IntegerField(default=0)
    atualizadas = models.IntegerField(default=0)
    erros = models.IntegerField(default=0)
    mensagem = models.TextField(blank=True, default="")

    criado_por = models.IntegerField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "potencial_votante_import"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.nome_original or 'import'} ({self.get_status_display()})"

    @property
    def percent(self):
        if not self.total_linhas:
            return 0
        return min(100, round((self.processadas / self.total_linhas) * 100, 1))
