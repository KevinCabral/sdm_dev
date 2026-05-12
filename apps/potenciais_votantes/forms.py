from django import forms

from .models import PotencialVotante


class PotencialVotanteForm(forms.ModelForm):
    nome = forms.CharField(max_length=255, required=True, label="Nome Completo")
    localidade = forms.CharField(max_length=255, required=False, label="Localidade")
    telefone = forms.CharField(max_length=64, required=False, label="Telefone")
    programa = forms.CharField(max_length=255, required=False, label="Programa")
    concelho = forms.CharField(max_length=255, required=False, label="Concelho")
    assinatura = forms.BooleanField(required=False, label="Assinatura recolhida")
    is_contactado = forms.BooleanField(required=False, label="Contactado")
    observacao = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Observação",
    )

    class Meta:
        model = PotencialVotante
        fields = (
            'nome', 'localidade', 'telefone', 'programa', 'concelho',
            'assinatura', 'is_contactado', 'observacao',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.visible_fields():
            widget = visible.field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = 'form-check-input'
            else:
                widget.attrs.setdefault('class', 'form-control')
