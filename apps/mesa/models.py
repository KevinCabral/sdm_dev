from django.db import models
from django.contrib.auth.models import User


class Mesa(models.Model):
    nr_mesa = models.CharField(max_length=150, null=False, blank=False)
    status = models.BigIntegerField(blank=True, null=True, default="1")
    updatedAt = models.DateTimeField(auto_now=True, auto_now_add=False, null=True)
    createdAt = models.DateTimeField(auto_now=True, auto_now_add=False,null=True)
    
    class Meta:
        db_table = 'mesa'

class UserMesa(models.Model):
    user = models.ForeignKey(User, models.DO_NOTHING,null=False, blank=False)
    mesa = models.ForeignKey(Mesa, models.DO_NOTHING, blank=True, null=True, default=None)
    updatedAt = models.DateTimeField(auto_now=True, auto_now_add=False, null=True)
    createdAt = models.DateTimeField(auto_now=True, auto_now_add=False,null=True)

    class Meta:
        db_table = 'user_mesa'
