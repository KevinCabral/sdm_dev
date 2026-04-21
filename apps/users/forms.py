from django import forms
from django.contrib.auth.models import User
from .models import Profile
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.forms import UserCreationForm

class UserUpdateForm(forms.ModelForm):
    # password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super(UserUpdateForm, self).__init__(*args, **kwargs)
        for visible in self.visible_fields():
            visible.field.widget.attrs['class'] = 'form-control'
        
        
    class Meta:
        model = User
        fields = [ 'email', 'first_name', 'last_name']


class ProfileUpdateForm(forms.ModelForm):
    image = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-control-file'}),required=False)
    about = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),label="Sobre mi",required=False)
    address = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control' }),required=False, label="Endereços")


    class Meta:
        model = Profile
        fields = ['image', 'about','address']

class SetPasswordForm(forms.Form):
    """
    A form that lets a user change set their password without entering the old
    password
    """

    error_messages = {
        "password_mismatch": _("Os dois campos de palavra-passe não correspondiam."),
    }
    new_password1 = forms.CharField(
        label=_("New password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        strip=False,
        help_text=password_validation.password_validators_help_text_html(),
    )
    new_password2 = forms.CharField(
        label=_("New password confirmation"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        for visible in self.visible_fields():
            visible.field.widget.attrs['class'] = 'form-control'

    def clean_new_password2(self):
        password1 = self.cleaned_data.get("new_password1")
        password2 = self.cleaned_data.get("new_password2")
        if password1 and password2:
            if password1 != password2:
                raise ValidationError(
                    self.error_messages["password_mismatch"],
                    code="password_mismatch",
                )
        password_validation.validate_password(password2, self.user)
        return password2

    def save(self, commit=True):
        password = self.cleaned_data["new_password1"]
        self.user.set_password(password)
        if commit:
            self.user.save()
        return self.user


class CreateUserForm(UserCreationForm):
    email = forms.EmailField(max_length=254, help_text='Informe um email válido.')
    class Meta:
        model = User
        fields = ['username', 'email']