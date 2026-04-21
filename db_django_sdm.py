# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models








class Contacto(models.Model):
    militante_id = models.IntegerField(blank=True, null=True)
    telefone1 = models.CharField(max_length=20, blank=True, null=True)
    telefone2 = models.CharField(max_length=20, blank=True, null=True)
    telefone_casa = models.CharField(max_length=20, blank=True, null=True)
    email = models.CharField(max_length=100, blank=True, null=True)
    email_trabalho = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True)
    telefone_trabalho = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'contacto'


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.SmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class HistoricoChamadas(models.Model):
    militante_id = models.IntegerField(blank=True, null=True)
    info_chamada = models.SmallIntegerField(blank=True, null=True)
    disponivel = models.SmallIntegerField(blank=True, null=True)
    recetivo = models.SmallIntegerField(blank=True, null=True)
    data_hr_chamada = models.CharField(max_length=20, blank=True, null=True)
    comentario = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'historico_chamadas'





class Recenseamento(models.Model):
    id = models.BigAutoField(primary_key=True)
    militante = models.ForeignKey(Militantes, models.DO_NOTHING, blank=True, null=True)
    resenciado = models.SmallIntegerField(blank=True, null=True)
    n_resenciado = models.SmallIntegerField(blank=True, null=True)
    resenciado_fora_praia = models.SmallIntegerField(blank=True, null=True)
    nr_mesa_voto = models.CharField(max_length=100, blank=True, null=True)
    sigla_mesa_voto = models.CharField(max_length=20, blank=True, null=True)
    telemovel_eleitoral = models.CharField(max_length=20, blank=True, null=True)
    telefone_eleitoral = models.CharField(max_length=20, blank=True, null=True)
    pais_eleitoral = models.CharField(max_length=50, blank=True, null=True)
    regiao_eleitoral = models.CharField(max_length=50, blank=True, null=True)
    concelho_eleitoral = models.CharField(max_length=50, blank=True, null=True)
    zona_eleitoral = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True)
    dt_recenseamento = models.DateField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'recenseamento'


class TblAuthorization(models.Model):
    id = models.BigAutoField(primary_key=True)
    redirect_url = models.CharField(max_length=500, blank=True, null=True)
    state_code = models.CharField(unique=True, max_length=30)

    class Meta:
        managed = False
        db_table = 'tbl_authorization'




class TblUserSession(models.Model):
    id = models.CharField(primary_key=True, max_length=36)
    id_token = models.CharField(unique=True, max_length=5000)
    user_name = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'tbl_user_session'


