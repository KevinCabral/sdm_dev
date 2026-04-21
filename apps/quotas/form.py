from django import forms
from .models import PagamentoQuotas,ValorPagamento
from apps.militantes.models import Militantes

class PagamentoQuotasForm(forms.ModelForm):
    data_pagamento = forms.CharField(max_length=20, required=True, label="Data de Pagamento")
    anexo_id = forms.FileField(widget=forms.FileInput(attrs={'class': 'form-control-file'}),label="Anexos")
    militantes_all = [(militantes.id, militantes.nome_completo) for militantes in Militantes.objects.filter(estado_militante='A').all()]
    militantes_all.insert(0, (None, 'Selecione um Militante')) 
    militante =  forms.ChoiceField(choices=militantes_all,required=True, label="Militante",initial=None)

    valor_all = [(valores.id, valores.valor) for valores in ValorPagamento.objects.all()]
    valor_all.insert(0, (None, 'Selecione um VAlor a pagar')) 
    valor =  forms.ChoiceField(choices=valor_all,required=True, label="Valor",initial=None)

    def __init__(self, *args, **kwargs):
        super(PagamentoQuotasForm, self).__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['anexo_id'].required = True
        for visible in self.visible_fields():
            visible.field.widget.attrs['class'] = 'form-control'
        self.fields['data_pagamento'].widget = forms.widgets.DateInput(
            # format="yyyy-mm-dd",
            
            attrs={
                'type': 'date', 'placeholder': 'yyyy-mm-dd',
                'class': 'form-control',
                }
            )
    
    def clean_militante(self):
        militante = self.cleaned_data['militante']

        if militante == "":
            return None
        try:
            militante = Militantes.objects.get(id=militante)
        except Militantes.DoesNotExist:
            raise forms.ValidationError("Militante não encontrado.")
        return militante
    
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
