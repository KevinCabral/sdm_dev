from django.db import models
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.utils import timezone

# Create your models here.

class Product(models.Model):
    id    = models.AutoField(primary_key=True)
    name  = models.CharField(max_length = 100) 
    info  = models.CharField(max_length = 100, default = '')
    price = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return self.name


class PasswordResetCode(models.Model):
    """Short-lived 6-digit code used to reset a user's password by email."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reset_codes")
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "used_at"])]

    def is_valid(self) -> bool:
        return self.used_at is None and timezone.now() < self.expires_at and self.attempts < 5

    def check_code(self, raw_code: str) -> bool:
        return check_password(raw_code, self.code_hash)

    @staticmethod
    def hash_code(raw_code: str) -> str:
        return make_password(raw_code)
