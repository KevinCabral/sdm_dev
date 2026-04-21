from django.db import models

# Create your models here.


class CartaConvite(models.Model):
    id = models.AutoField(primary_key=True)
    documentId = models.CharField(max_length=34, blank=True, null=True)
    conteudo = models.TextField(blank=True, null=True)
    tipo = models.CharField(max_length=100, blank=True, null=True)
    imagem_id = models.IntegerField(blank=True, null=True)
    publishedAt = models.DateField(blank=True, null=True)
    active = models.BooleanField()
    class Meta:
        managed = False
