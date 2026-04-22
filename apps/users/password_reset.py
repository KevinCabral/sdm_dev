"""
Code-based password reset flow (replaces Django's link-based reset).

Flow:
  1. User enters email on /accounts/password-reset/
  2. We generate a 6-digit code, hash & store it (expires in 15 min),
     and email the plain code to the user.
  3. User enters email + code + new password on /accounts/password-reset-confirm/
  4. On success → redirect to /accounts/password-reset-complete/ then login.
"""
import logging
import secrets
import threading
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.generic import FormView, TemplateView

from home.models import PasswordResetCode

logger = logging.getLogger(__name__)
CODE_TTL = timedelta(minutes=15)


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _send_code_email(user: User, code: str) -> None:
    ctx = {"username": user.username, "code": code, "ttl_minutes": int(CODE_TTL.total_seconds() // 60)}
    text_body = render_to_string("email/password_reset_code.txt", ctx)
    html_body = render_to_string("email/password_reset_code.html", ctx)
    msg = EmailMultiAlternatives(
        subject="Código de recuperação de palavra-passe",
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[user.email],
    )
    msg.attach_alternative(html_body, "text/html")
    try:
        msg.send(fail_silently=False)
    except Exception:
        logger.exception("Failed to send password reset code to %s", user.email)


def _send_code_email_async(user: User, code: str) -> None:
    """Fire-and-forget so the HTTP request returns immediately."""
    threading.Thread(target=_send_code_email, args=(user, code), daemon=True).start()


# ---------- Forms ----------

class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "Email da sua conta", "autofocus": True}
        )
    )


class PasswordResetCodeConfirmForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email"})
    )
    code = forms.CharField(
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Código de 6 dígitos",
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
                "autocomplete": "one-time-code",
            }
        ),
    )
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Nova palavra-passe"})
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirmar palavra-passe"})
    )

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if not code.isdigit():
            raise forms.ValidationError("O código deve conter apenas dígitos.")
        return code

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("As palavras-passe não coincidem.")
        if p1:
            password_validation.validate_password(p1)
        return cleaned


# ---------- Views ----------

class PasswordResetRequestView(FormView):
    template_name = "accounts/auth-reset-password.html"
    form_class = PasswordResetRequestForm

    def get_success_url(self):
        return reverse("password_reset_confirm")

    def form_valid(self, form):
        email = form.cleaned_data["email"].strip().lower()
        # Always behave the same way to avoid email enumeration.
        users = list(User.objects.filter(email__iexact=email, is_active=True))
        for user in users:
            code = _generate_code()
            PasswordResetCode.objects.create(
                user=user,
                code_hash=PasswordResetCode.hash_code(code),
                expires_at=timezone.now() + CODE_TTL,
            )
            _send_code_email_async(user, code)
        messages.success(
            self.request,
            "Se a conta existir, enviámos um código de 6 dígitos para o email indicado. "
            "O código é válido por 15 minutos.",
        )
        # Pre-fill email on the next step.
        self.request.session["pwd_reset_email"] = email
        return super().form_valid(form)


class PasswordResetCodeConfirmView(FormView):
    template_name = "accounts/auth-password-reset-confirm.html"
    form_class = PasswordResetCodeConfirmForm

    def get_success_url(self):
        return reverse("password_reset_complete")

    def get_initial(self):
        initial = super().get_initial()
        email = self.request.session.get("pwd_reset_email")
        if email:
            initial["email"] = email
        return initial

    def form_valid(self, form):
        email = form.cleaned_data["email"].strip().lower()
        code = form.cleaned_data["code"]
        new_password = form.cleaned_data["new_password1"]

        users = User.objects.filter(email__iexact=email, is_active=True)
        if not users.exists():
            form.add_error(None, "Email ou código inválido.")
            return self.form_invalid(form)

        # Find the latest unused, unexpired code for any of these users.
        candidate = (
            PasswordResetCode.objects.filter(user__in=users, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if candidate is None or not candidate.is_valid():
            form.add_error(None, "Código expirado ou inválido. Solicite um novo.")
            return self.form_invalid(form)

        candidate.attempts = (candidate.attempts or 0) + 1
        if not candidate.check_code(code):
            candidate.save(update_fields=["attempts"])
            form.add_error("code", "Código incorreto.")
            return self.form_invalid(form)

        # Success: set password, mark code used, invalidate other pending codes.
        user = candidate.user
        user.set_password(new_password)
        user.save(update_fields=["password"])
        candidate.used_at = timezone.now()
        candidate.save(update_fields=["used_at", "attempts"])
        PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(
            used_at=timezone.now()
        )
        self.request.session.pop("pwd_reset_email", None)
        messages.success(self.request, "Palavra-passe alterada com sucesso. Já pode iniciar sessão.")
        return super().form_valid(form)


class PasswordResetCompleteView(TemplateView):
    template_name = "accounts/auth-password-reset-complete.html"
