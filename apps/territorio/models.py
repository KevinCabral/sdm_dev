from django.db import models


class Circulo(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    codigo = models.CharField(max_length=20, blank=True, null=True)
    ativo = models.BooleanField(default=True)
    meta = models.IntegerField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "territorio_circulo"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Concelho(models.Model):
    nome = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, blank=True, null=True)
    circulo = models.ForeignKey(
        Circulo, on_delete=models.PROTECT, related_name="concelhos",
        blank=True, null=True,
    )
    ativo = models.BooleanField(default=True)
    meta = models.IntegerField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "territorio_concelho"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["nome", "circulo"], name="uniq_concelho_nome_circulo"
            ),
        ]

    def __str__(self):
        return self.nome


class Zona(models.Model):
    nome = models.CharField(max_length=150)
    codigo = models.CharField(max_length=20, blank=True, null=True)
    concelho = models.ForeignKey(
        Concelho, on_delete=models.PROTECT, related_name="zonas",
        blank=True, null=True,
    )
    ativo = models.BooleanField(default=True)
    meta = models.IntegerField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "territorio_zona"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["nome", "concelho"], name="uniq_zona_nome_concelho"
            ),
        ]

    def __str__(self):
        return self.nome
