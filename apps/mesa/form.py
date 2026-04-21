from django import forms
from .models import UserMesa,Mesa
from django.contrib.auth.models import User


class MesaForm(forms.ModelForm):
    nr_mesa = forms.CharField(max_length=200, required=True, label="Número de Mesa")

    def __init__(self, *args, **kwargs):
        super(MesaForm, self).__init__(*args, **kwargs)
        for visible in self.visible_fields():
            visible.field.widget.attrs['class'] = 'form-control'
    class Meta:
        model = Mesa
        fields = '__all__'

class UserMesaForm(forms.ModelForm):
    nr_mesas = [(nr_mesas.id, nr_mesas.nr_mesa) for nr_mesas in Mesa.objects.filter(status=1).all()]
    nr_mesas.insert(0, (None, 'Selecione uma Mesa')) 

    mesa =  forms.ChoiceField(choices=nr_mesas,required=True, label="Mesa",initial=None)


    users = [(users.id, users.username) for users in User.objects.filter(is_active=1).all()]
    users.insert(0, (None, 'Selecione um Utilizador')) 

    user =  forms.ChoiceField(choices=users,required=True, label="Utilizador",initial=None)

    def __init__(self, *args, **kwargs):
        super(UserMesaForm, self).__init__(*args, **kwargs)
        for visible in self.visible_fields():
            visible.field.widget.attrs['class'] = 'form-control'
       
    def clean_user(self):
        user = self.cleaned_data['user']
        try:
            user = User.objects.get(id=user)
        except User.DoesNotExist:
            raise forms.ValidationError("Utilizador não encontrado.")
        return user
    
    def clean_mesa(self):
        mesa = self.cleaned_data['mesa']
        try:
            mesa = Mesa.objects.get(id=mesa)
        except Mesa.DoesNotExist:
            raise forms.ValidationError("Mesa não encontrada.")
        return mesa

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
