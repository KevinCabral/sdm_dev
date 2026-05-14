from django import forms
from .models import UserMesa,Mesa
from django.contrib.auth.models import User


class MesaForm(forms.ModelForm):
    nr_mesa = forms.CharField(max_length=200, required=True, label="Número de Mesa")

    def __init__(self, *args, **kwargs):
        super(MesaForm, self).__init__(*args, **kwargs)
        for visible in self.visible_fields():
            visible.field.widget.attrs.setdefault('class', 'form-control')

    class Meta:
        model = Mesa
        fields = ('nr_mesa',)

class UserMesaForm(forms.ModelForm):
    mesa = forms.IntegerField(
        required=True,
        label="Mesa",
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'data-ajax': 'mesa', 'multiple': 'multiple'}),
    )
    user = forms.IntegerField(
        required=True,
        label="Utilizador",
        widget=forms.Select(attrs={'class': 'form-control', 'data-ajax': 'user'}),
    )

    def __init__(self, *args, **kwargs):
        super(UserMesaForm, self).__init__(*args, **kwargs)
        # Pre-populate options only for the bound instance (edit) so Select2 has a label.
        instance = kwargs.get('instance') or getattr(self, 'instance', None)
        if instance and instance.pk:
            if instance.mesa_id:
                self.fields['mesa'].widget.choices = [
                    (instance.mesa_id, instance.mesa.nr_mesa if instance.mesa else str(instance.mesa_id))
                ]
                self.fields['mesa'].initial = instance.mesa_id
            if instance.user_id:
                self.fields['user'].widget.choices = [
                    (instance.user_id, instance.user.username if instance.user else str(instance.user_id))
                ]
                self.fields['user'].initial = instance.user_id
        else:
            self.fields['mesa'].widget.choices = [('', 'Selecione uma Mesa')]
            self.fields['user'].widget.choices = [('', 'Selecione um Utilizador')]

    def clean_user(self):
        user_id = self.cleaned_data.get('user')
        if not user_id:
            raise forms.ValidationError("Utilizador é obrigatório.")
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise forms.ValidationError("Utilizador não encontrado.")

    def clean_mesa(self):
        mesa_id = self.cleaned_data.get('mesa')
        if not mesa_id:
            raise forms.ValidationError("Mesa é obrigatória.")
        try:
            return Mesa.objects.get(pk=mesa_id)
        except Mesa.DoesNotExist:
            raise forms.ValidationError("Mesa não encontrada.")

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get('user')
        mesa = cleaned_data.get('mesa')
        if user:
            self.instance.user = user
        if mesa:
            self.instance.mesa = mesa
        return cleaned_data

    class Meta:
        model = UserMesa
        fields = '__all__'
