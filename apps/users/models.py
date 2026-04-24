import logging
import os
import uuid

from django.conf import settings
from django.contrib.auth.models import User as UserBase
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


# Create your models here.

def get_file_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = "%s.%s" % (uuid.uuid4(), ext)
    return os.path.join('profile/', filename)


class Profile(models.Model):
    user = models.OneToOneField(UserBase, on_delete=models.CASCADE) # Delete profile when user is deleted
    image = models.ImageField(upload_to=get_file_path)
    address = models.CharField(max_length=100, blank=True, null=True)
    about = models.TextField(max_length=500, blank=True, null=True)
   

    def __str__(self):
        return f'{self.user.username} Profile' #show how we want it to be displayed
    
    class Meta:
        db_table = 'home_profile'
    
class SendUsernamePassword:
    
    email = ""
    username = ""
    password = ""
    url = ""
    site_name = ""
    template = ""

    def __init__(self, email, username, password, request=None,template = "send_username"):
        self.email = email
        self.username = username
        self.password = password
        if request != None:
            current_site = get_current_site(request)
            self.site_name = current_site.name
            domain = current_site.domain
            self.url = domain + self.site_name
        self.template = template

    def send(self):
        data = {
            "username": self.username,
            "password":self.password,
            "url":self.url,
            "site_name ": self.site_name 
        }
        text_body = render_to_string("email/"+self.template+".txt", data)
        html_body = render_to_string("email/"+self.template+".html", data)

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or settings.EMAIL_HOST_USER
        msg = EmailMultiAlternatives(subject="Conta criada", from_email=from_email,
                                    to=[self.email], body=text_body)
        msg.attach_alternative(html_body, "text/html")
        try:
            msg.send()
            return True
        except Exception as exc:
            logger.exception("Failed to send '%s' email to %s: %s", self.template, self.email, exc)
            return False

    class Meta:
        managed = False
        
UserBase.add_to_class('militante_id', models.IntegerField(blank=True,null=True,default=None))