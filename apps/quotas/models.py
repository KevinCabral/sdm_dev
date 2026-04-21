from django.db import models
from apps.militantes.models import Militantes
import os
import uuid
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site

def get_file_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = "%s.%s" % (uuid.uuid4(), ext)
    return os.path.join('anexos/', filename)

class ValorPagamento(models.Model):
    valor = models.FloatField(blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    createdat = models.DateTimeField(blank=True, null=True)
    updatedat = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'valor_pagamento'

class PagamentoQuotas(models.Model):
    valor = models.ForeignKey(ValorPagamento, models.DO_NOTHING, blank=True, null=True)
    data_pagamento = models.DateField(blank=True, null=True)
    anexo_id = models.FileField(upload_to=get_file_path,blank=False)
    militante = models.ForeignKey(Militantes, models.DO_NOTHING, blank=True, null=True)
    createdat = models.DateTimeField(auto_now=False, auto_now_add=True)
    updatedat = models.DateTimeField(auto_now=True, auto_now_add=False,null=True)

    class Meta:
        db_table = 'pagamento_quotas'


class SendComprovativo:
    
    email = ""
    text = ""
    anexo = ""
    url = ""
    site_name = ""
    template = ""
    nome = ""

    def __init__(self, email,nome, text, anexo, request,template="comprovativo_pagamento"):
        self.email = "jixahe1460@evimzo.com"
        self.text = text
        self.anexo = anexo
        current_site = get_current_site(request)
        self.site_name = current_site.name
        domain = current_site.domain
        self.url = domain + self.site_name
        self.template = template
        self.nome = nome

    def send(self):
        data = {
            "text": self.text,
            "nome":self.nome,
            "url":self.url,
            "site_name ": self.site_name 
        }
        text_body = render_to_string("email/"+self.template+".txt", data)
        html_body = render_to_string("email/"+self.template+".html", data)

        msg = EmailMultiAlternatives(subject="comorivartivo de Pagamento", from_email="assasa@assa.com",
                                    to=[self.email], body=text_body)
        msg.attach_alternative(html_body, "text/html")
        msg.attach_file(self.anexo)  
        msg.send()

    class Meta:
        managed = False   


