from django.db import models
from apps.militantes.models import Militantes


class Eleitores(models.Model):
    nome = models.CharField(max_length=200, blank=True, null=True)
    alcunha = models.CharField(max_length=50, blank=True, null=True)
    nr_identificacao = models.CharField(max_length=50, blank=True, null=True)
    data_nascimento = models.DateField(blank=True, null=True)
    genero = models.CharField(max_length=20, blank=True, null=True)
    pai = models.CharField(max_length=200, blank=True, null=True)
    mae = models.CharField(max_length=200, blank=True, null=True)
    pais = models.CharField(max_length=100, blank=True, null=True)
    ilha = models.CharField(max_length=50, blank=True, null=True)
    conc_pais_res = models.CharField(max_length=100, blank=True, null=True)
    local_cidade_res = models.CharField(max_length=100, blank=True, null=True)
    morada = models.CharField(max_length=100, blank=True, null=True)
    telefone = models.BigIntegerField(blank=True, null=True)
    telemovel = models.BigIntegerField(blank=True, null=True)
    status = models.BigIntegerField(blank=True, null=True,default="1")
    id_obito = models.BigIntegerField(blank=True, null=True)
    partido_voto = models.CharField(max_length=20, blank=True, null=True)
    acompanhamento = models.SmallIntegerField(blank=True, null=True)
    transporte = models.SmallIntegerField(blank=True, null=True)
    tp_associado = models.CharField(max_length=20, blank=True, null=True)
    desloca_outro_concelho = models.CharField(max_length=100, blank=True, null=True)
    gv = models.CharField(max_length=100, blank=True, null=True)
    desloca_de = models.CharField(max_length=255, blank=True, null=True)
    desloca_para = models.CharField(max_length=255, blank=True, null=True)
    estado_sensibilidade = models.SmallIntegerField(blank=True, null=True)
    code_regiao = models.CharField(max_length=5, blank=True, null=True)
    observacoes = models.CharField(max_length=500, blank=True, null=True)
    nr_eleitor = models.IntegerField(blank=True, null=True)
    nr_mesa = models.CharField(max_length=40, blank=True, null=True)
    militante_id = models.ForeignKey(Militantes, models.DO_NOTHING, blank=True, null=True, default=None)
    datahora_atualizacao = models.DateTimeField(auto_now=True, auto_now_add=False,null=True)

    def save(self, *args, **kwargs):
        print(self.datahora_atualizacao)
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'eleitores'

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
        db_table = 'votacao'

