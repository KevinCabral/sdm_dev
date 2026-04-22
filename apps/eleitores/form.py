from django import forms

from apps.militantes.models import Militantes
from .models import Eleitores


class EleitoresForm(forms.ModelForm):
    """Form for the legacy ``eleitores`` table.

    Only fields that actually exist in the database are exposed. Boolean
    flags use checkboxes; ``militante_id`` is a select populated with active
    militantes.
    """

    nome = forms.CharField(max_length=200, required=True, label="Nome Completo")
    nominho = forms.CharField(max_length=200, required=False, label="Alcunha / Apelido")
    filiacao = forms.CharField(max_length=255, required=False, label="Filiação")
    data_nascimento = forms.DateField(required=False, label="Data de Nascimento")
    idade_eleitor = forms.IntegerField(required=False, label="Idade")
    contato = forms.CharField(max_length=100, required=False, label="Contacto")
    nacionalidade = forms.CharField(max_length=100, required=False, label="Nacionalidade")
    concelho = forms.CharField(max_length=100, required=False, label="Concelho")
    zona = forms.CharField(max_length=100, required=False, label="Zona")
    nr_mesa = forms.CharField(max_length=40, required=False, label="Número de Mesa")
    nr_eleitor = forms.IntegerField(required=False, label="Número de Eleitor")

    falecido = forms.BooleanField(required=False, label="Falecido")
    ausente = forms.BooleanField(required=False, label="Ausente")
    indeciso = forms.BooleanField(required=False, label="Indeciso")
    nao_vai_votar = forms.BooleanField(required=False, label="Não vai votar")
    mpd = forms.BooleanField(required=False, label="Apoiante MPD")
    descarga = forms.BooleanField(required=False, label="Descarga")

    militante_id = forms.ModelChoiceField(
        queryset=Militantes.objects.none(),
        required=False,
        empty_label="Selecione um Militante",
        label="Militante",
    )

    class Meta:
        model = Eleitores
        fields = (
            'nome', 'nominho', 'filiacao', 'data_nascimento', 'idade_eleitor',
            'contato', 'nacionalidade', 'concelho', 'zona', 'nr_mesa', 'nr_eleitor',
            'falecido', 'ausente', 'indeciso', 'nao_vai_votar', 'mpd', 'descarga',
            'militante_id',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only include the currently selected militante in the queryset to
        # keep the rendered <select> tiny. Select2 + AJAX endpoint
        # (/militantes/search) handles searching the rest.
        militante_qs = Militantes.objects.none()
        selected_id = None
        if self.instance and self.instance.pk and self.instance.militante_id_id:
            selected_id = self.instance.militante_id_id
        elif self.is_bound:
            selected_id = self.data.get(self.add_prefix('militante_id'))
        if selected_id:
            try:
                militante_qs = Militantes.objects.filter(pk=selected_id)
            except (ValueError, TypeError):
                militante_qs = Militantes.objects.none()
        self.fields['militante_id'].queryset = militante_qs

        for visible in self.visible_fields():
            widget = visible.field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = 'form-check-input'
            else:
                widget.attrs.setdefault('class', 'form-control')
        self.fields['data_nascimento'].widget = forms.DateInput(
            attrs={'type': 'date', 'class': 'form-control'}
        )
        self.fields['militante_id'].widget.attrs.update({
            'class': 'form-control militante-select',
            'data-search-url': '/militantes/search',
        })
