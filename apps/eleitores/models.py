from django.db import models

from apps.militantes.models import Militantes


class Eleitores(models.Model):
    """Legacy eleitores table — schema mapped from the existing database.

    Kept as ``managed = False`` because the table was created/owned outside
    Django. Add new columns via a SQL migration, then mirror them here.
    """

    nome = models.TextField(blank=True, null=True)
    nominho = models.TextField(blank=True, null=True)
    filiacao = models.TextField(blank=True, null=True)
    data_nascimento = models.DateField(blank=True, null=True)
    idade_eleitor = models.IntegerField(blank=True, null=True)
    contato = models.TextField(blank=True, null=True)
    nacionalidade = models.TextField(blank=True, null=True)
    concelho = models.TextField(blank=True, null=True)
    zona = models.TextField(blank=True, null=True)
    nr_mesa = models.CharField(max_length=40, blank=True, null=True)
    nr_eleitor = models.IntegerField(blank=True, null=True)

    falecido = models.BooleanField(blank=True, null=True, default=False)
    ausente = models.BooleanField(blank=True, null=True, default=False)
    indeciso = models.BooleanField(blank=True, null=True, default=False)
    nao_vai_votar = models.BooleanField(blank=True, null=True, default=False)
    mpd = models.BooleanField(blank=True, null=True, default=False)
    descarga = models.BooleanField(blank=True, null=True, default=False)

    datahora_atualizacao = models.DateTimeField(
        auto_now=True, blank=True, null=True
    )

    militante_id = models.ForeignKey(
        Militantes,
        models.DO_NOTHING,
        db_column='militante_id_id',
        blank=True,
        null=True,
        default=None,
        related_name='eleitores',
    )

    class Meta:
        managed = False
        db_table = 'eleitores'

    def __str__(self):
        return self.nome or f'Eleitor #{self.pk}'


class Votacao(models.Model):
    assembleia_voto_nr = models.CharField(max_length=1, blank=True, null=True)
    nr_eleitor = models.IntegerField()
    votou = models.SmallIntegerField(blank=True, null=True)
    datetime = models.DateTimeField(blank=True, null=True)
    anulado = models.SmallIntegerField(blank=True, null=True)
    nr_bi_eleitor = models.CharField(max_length=30, blank=True, null=True)
    nr_mesa = models.CharField(max_length=150)
    motivo_n_votou = models.CharField(max_length=150, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'votacao'


class EleicaoImport(models.Model):
    """Tracks an Excel import of eleitores tied to a specific eleição."""

    TIPO_LEGISLATIVA = "L"
    TIPO_PRESIDENCIAL = "P"
    TIPO_AUTARQUICA = "A"
    TIPO_CHOICES = [
        (TIPO_LEGISLATIVA, "Legislativa"),
        (TIPO_PRESIDENCIAL, "Presidencial"),
        (TIPO_AUTARQUICA, "Autárquica"),
    ]

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

    tipo_eleicao = models.CharField(max_length=1, choices=TIPO_CHOICES)
    mes_ano = models.CharField(max_length=7, help_text="Formato MM/YYYY")
    arquivo = models.FileField(upload_to="eleicao_imports/", null=True, blank=True)
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
        db_table = "eleicao_import"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.get_tipo_eleicao_display()} {self.mes_ano} ({self.get_status_display()})"

    @property
    def percent(self):
        if not self.total_linhas:
            return 0
        return min(100, round((self.processadas / self.total_linhas) * 100, 1))


class CadernoEleitoral2026(models.Model):
    """Caderno Eleitoral — Eleição dos Titulares de Assembleia Nacional 2026.

    Mirrors the official PDF/CSV layout. The header metadata
    (ILHA / CRE / POSTO / CONCELHO / MESA) is repeated on every row so each
    record is self-contained and filterable.
    """

    # Header metadata
    ilha = models.CharField(max_length=100, blank=True, default="")
    cre = models.CharField(max_length=150, blank=True, default="")
    posto = models.CharField(max_length=150, blank=True, default="")
    concelho = models.CharField(max_length=150, blank=True, default="")
    mesa = models.CharField(max_length=50, blank=True, default="")

    # Per-voter columns
    numero = models.IntegerField(blank=True, null=True)  # 1/384, stored as 1
    nome = models.CharField(max_length=255)
    filiacao = models.TextField(blank=True, default="")
    nome_pai = models.CharField(max_length=255, blank=True, default="")
    nome_mae = models.CharField(max_length=255, blank=True, default="")
    data_nascimento = models.DateField(blank=True, null=True)
    descarga = models.BooleanField(default=False)

    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "caderno_eleitoral_2026"
        ordering = ["mesa", "numero"]
        indexes = [
            models.Index(fields=["mesa"]),
            models.Index(fields=["concelho"]),
            models.Index(fields=["nome"]),
        ]

    def __str__(self):
        return f"{self.numero or '?'} — {self.nome} ({self.mesa})"


class CadernoEleitoral2026Import(models.Model):
    """Tracks a CSV import of caderno eleitoral 2026 rows."""

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

    arquivo = models.FileField(upload_to="caderno_2026_imports/", null=True, blank=True)
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
        db_table = "caderno_eleitoral_2026_import"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.nome_original or 'import'} ({self.get_status_display()})"
