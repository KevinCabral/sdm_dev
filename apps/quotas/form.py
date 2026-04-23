from django import forms
from .models import PagamentoQuotas, ValorPagamento
from apps.militantes.models import Militantes


class PagamentoQuotasForm(forms.ModelForm):
    data_pagamento = forms.CharField(max_length=20, required=True, label="Data de Pagamento")
    anexo_id = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control-file'}),
        label="Anexos",
    )

    # Militante: no preloaded choices (89k+ rows). The widget is a plain <select>
    # populated client-side by Select2 via AJAX (/militantes/search).
    militante = forms.IntegerField(
        required=True,
        label="Militante",
        widget=forms.Select(attrs={'class': 'form-control', 'data-ajax': 'militante'}),
    )

    valor_all = [(v.id, v.valor) for v in ValorPagamento.objects.all()]
    valor_all.insert(0, (None, 'Selecione um valor a pagar'))
    valor = forms.ChoiceField(
        choices=valor_all,
        required=True,
        label="Valor",
        initial=None,
    )

    def __init__(self, *args, **kwargs):
        super(PagamentoQuotasForm, self).__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['anexo_id'].required = True
        for visible in self.visible_fields():
            visible.field.widget.attrs.setdefault('class', 'form-control')
        self.fields['data_pagamento'].widget = forms.widgets.DateInput(
            attrs={
                'type': 'date',
                'placeholder': 'yyyy-mm-dd',
                'class': 'form-control',
            }
        )
        # When editing, render the currently selected militante as the only
        # initial option so Select2 can display it before AJAX kicks in.
        if self.instance and self.instance.pk and self.instance.militante_id:
            m = self.instance.militante
            self.fields['militante'].widget.choices = [
                (m.id, m.nome_completo or f'Militante #{m.id}')
            ]
            self.fields['militante'].initial = m.id
        else:
            self.fields['militante'].widget.choices = [('', 'Selecione um militante')]

    def clean_militante(self):
        militante = self.cleaned_data.get('militante')
        if not militante:
            raise forms.ValidationError("Militante é obrigatório.")
        try:
            return Militantes.objects.get(id=militante)
        except Militantes.DoesNotExist:
            raise forms.ValidationError("Militante não encontrado.")

    def clean_valor(self):
        valor = self.cleaned_data['valor']

        if valor == "":
            return None
        try:
            valor = ValorPagamento.objects.get(id=valor)
        except ValorPagamento.DoesNotExist:
            raise forms.ValidationError("Valor não encontrado.")
        return valor

    def clean(self):
        cleaned_data = super().clean()
        militante = cleaned_data.get('militante')
        valor = cleaned_data.get('valor')
        if militante == "":
            self.instance.militante = None

        if valor == "":
            self.instance.valor = None
        
        if militante:
            self.instance.militante = militante

        if valor:
            self.instance.valor = valor
        return cleaned_data
    
    class Meta:
        model = PagamentoQuotas
        fields = '__all__'
