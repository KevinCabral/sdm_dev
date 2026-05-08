from django.db import models
import os
import uuid

# Create your models here.

def get_file_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = "%s.%s" % (uuid.uuid4(), ext)
    return os.path.join('militantes/', filename)

class Militantes(models.Model):
    nome_completo = models.CharField(max_length=200, blank=True, null=True)
    estado_ficha = models.CharField(max_length=20, blank=True, null=True)
    tp_associado = models.CharField(max_length=20, blank=True, null=True)
    estado_militante = models.CharField(max_length=20, blank=True, null=True, default="P")
    alcunha = models.CharField(max_length=20, blank=True, null=True)
    nm_pai = models.CharField(max_length=100, blank=True, null=True)
    nm_mae = models.CharField(max_length=100, blank=True, null=True)
    genero = models.CharField(max_length=20, blank=True, null=True)
    estado_civil = models.CharField(max_length=20, blank=True, null=True)
    agregado_familiar = models.SmallIntegerField(blank=True, null=True)
    profissao_atual = models.CharField(max_length=50, blank=True, null=True)
    local_trabalho = models.CharField(max_length=50, blank=True, null=True)
    sector = models.CharField(max_length=50, blank=True, null=True)
    empresa = models.CharField(max_length=50, blank=True, null=True)
    funcao = models.CharField(max_length=50, blank=True, null=True)
    grau_academica = models.CharField(max_length=50, blank=True, null=True)
    area_atuacao = models.CharField(max_length=255, blank=True, null=True)
    curso = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True)
    dt_emissao_doc = models.DateField(blank=True, null=True)
    dt_validade_doc = models.DateField(blank=True, null=True)
    email_pessoal = models.CharField(max_length=100, blank=True, null=True)
    email_trabalho = models.CharField(max_length=100, blank=True, null=True)
    nr_documento = models.CharField(max_length=20, blank=True, null=True)
    nr_telefone_casa = models.IntegerField(blank=True, null=True)
    nr_telemovel1 = models.IntegerField(blank=True, null=True)
    nr_telemovel2 = models.IntegerField(blank=True, null=True)
    tp_documento = models.CharField(max_length=20, blank=True, null=True)
    dt_nascimento = models.DateField(blank=True, null=True)
    is_mobile = models.BooleanField(blank=True, null=True)
    motivo_rejeicao = models.CharField(max_length=1000, null=True,blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    image = models.ImageField(upload_to=get_file_path)
    # Reference to apps.potenciais_votantes.PotencialVotante (kept as a plain
    # BigIntegerField to avoid a hard cross-app FK constraint).
    potencial_votante_id = models.BigIntegerField(blank=True, null=True, db_index=True)

    class Meta:
        db_table = 'militantes'

    def __str__(self):
        return self.nome_completo or f'Militante #{self.pk}'

class Geografia(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    pais = models.CharField(max_length=50, blank=True, null=True)
    ilha = models.CharField(max_length=50, blank=True, null=True)
    concelho = models.CharField(max_length=50, blank=True, null=True)
    freguesia = models.CharField(max_length=50, blank=True, null=True)
    zona = models.CharField(max_length=50, blank=True, null=True)
    lugar = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'geografia'
        managed = False

class Morada(models.Model):
    id = models.BigAutoField(primary_key=True)
    morada_atual = models.CharField(max_length=250, blank=True, null=True)
    perto_de = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=1, blank=True, null=True)
    geografia = models.ForeignKey(Geografia, models.DO_NOTHING, blank=True, null=True)
    militante = models.ForeignKey(Militantes, models.DO_NOTHING, blank=True, null=True)
    # Reference to apps.potenciais_votantes.PotencialVotante.
    potencial_votante_id = models.BigIntegerField(blank=True, null=True, db_index=True)

    class Meta:
        db_table = 'morada'


class MilitantesCallInfo(models.Model):
    """Information collected by the Call Center during a phone inquérito.

    The underlying ``militantes_call_info`` table pre-exists in Postgres
    with a fixed schema, so this model is unmanaged. The new
    ``potencial_votante_id`` column is added by a RunSQL migration.
    """

    id = models.AutoField(primary_key=True)
    # 0 / 1 flags (smallint in DB)
    resenciado_fora_praia = models.SmallIntegerField(blank=True, null=True)
    resenciado = models.SmallIntegerField(blank=True, null=True)
    recetivo = models.SmallIntegerField(blank=True, null=True)
    n_encontrado = models.SmallIntegerField(blank=True, null=True)
    n_atendeu = models.SmallIntegerField(blank=True, null=True)
    precisa_transporte_vota = models.CharField(max_length=20, blank=True, null=True)

    username = models.CharField(max_length=50, blank=True, null=True)
    data_hr_chamada = models.CharField(max_length=20, blank=True, null=True)
    comentario = models.CharField(max_length=255, blank=True, null=True)

    id_militante = models.IntegerField(blank=True, null=True)
    potencial_votante_id = models.BigIntegerField(blank=True, null=True, db_index=True)

    class Meta:
        db_table = 'militantes_call_info'
        managed = False

    def __str__(self):
        return f'CallInfo #{self.pk} (PV {self.potencial_votante_id})'


