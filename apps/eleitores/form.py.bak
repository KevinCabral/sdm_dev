from django import forms
from .models import Eleitores
from apps.militantes.models import Militantes


class EleitoresForm(forms.ModelForm):

    GENERO = (("M" , "M"), ("F" ,"F"))

    observacoes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5}), label="Observacoes", required=False)
    nome = forms.CharField(max_length=200, required=True, label="Nome Completo")
    nr_identificacao = forms.CharField(max_length=200, required=True, label="Número de identificação")
    pai = forms.CharField(max_length=100, required=True, label="Nome de Pai")
    mae = forms.CharField(max_length=100, required=True, label="Nome de Mãe")
    data_nascimento = forms.CharField(max_length=20, required=True, label="Data de Nascimento")
    genero = forms.ChoiceField(choices=GENERO, required=True, label="Genero")
    pais = forms.CharField(max_length=100, required=True, label="Pais")
    ilha = forms.CharField(max_length=50, required=True, label="Ilha")
    conc_pais_res = forms.CharField(max_length=100, required=True, label="Concelho de Residencia")
    local_cidade_res = forms.CharField(max_length=100, required=True, label="Local")
    morada = forms.CharField(max_length=100, required=True, label="Morada")
    telefone = forms.IntegerField(required=True, label="Telefone")
    telemovel = forms.IntegerField(required=True, label="Telemovel")
    status = forms.IntegerField(required=False,label="Status",initial='1')
    id_obito = forms.IntegerField(required=True, label="ID Obitido")
    partido_voto = forms.CharField(max_length=20, required=True, label="Partido Voto")
    acompanhamento = forms.IntegerField(required=True, label="Acompanhamento")
    transporte = forms.IntegerField(required=True, label="Transporte")
    tp_associado = forms.CharField(max_length=20, required=True, label="Tipo de Associado")
    desloca_outro_concelho = forms.CharField(max_length=100, required=True, label="Deslocação para Concelho")
    gv = forms.CharField(max_length=100, required=True, label="GV")
    desloca_de = forms.CharField(max_length=255, required=True, label="Desloca de")
    desloca_para = forms.CharField(max_length=255, required=True, label="Desloca para")
    estado_sensibilidade = forms.IntegerField(required=True, label="Estado de sensibilidade")
    code_regiao = forms.CharField(max_length=5, required=True, label="Codigo Região")
    observacoes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),max_length=500, required=True, label="Observações")
    # datahora_atualizacao = forms.CharField(max_length=20, required=True, label="Data e hora de atualização")
    nr_eleitor = forms.IntegerField(required=True, label="Número Eleitor")
    nr_mesa = forms.CharField(max_length=40, required=True, label="Número de mesa")

    militantes = [(militantes.id, militantes.nome_completo) for militantes in Militantes.objects.filter(estado_militante='A').all()]
    militantes.insert(0, (None, 'Selecione um Militante')) 

    militante_id =  forms.ChoiceField(choices=militantes,required=False, label="Militante",initial=None)


    def __init__(self, *args, **kwargs):
        super(EleitoresForm, self).__init__(*args, **kwargs)
        for visible in self.visible_fields():
            visible.field.widget.attrs['class'] = 'form-control'
        self.fields['data_nascimento'].widget = forms.widgets.DateInput(
            # format="yyyy-mm-dd",
            attrs={
                'type': 'date', 'placeholder': 'yyyy-mm-dd',
                'class': 'form-control'
                }
            )
    
    def clean_militante_id(self):
        militante_id = self.cleaned_data['militante_id']

        if militante_id == "":
            return None
        try:
            militante = Militantes.objects.get(id=militante_id)
        except Militantes.DoesNotExist:
            raise forms.ValidationError("Militante não encontrado.")
        # Retorna o objeto Militantes para ser atribuído ao campo 'militante' de Eleitores
        return militante

    def clean(self):
        cleaned_data = super().clean()
        militante = cleaned_data.get('militante_id')
        if militante == "":
            return None
        
        if militante:
            # Se o campo militante_id estiver presente e válido,
            # atribua o objeto Militantes ao campo 'militante' de Eleitores
            self.instance.militante = militante
        return cleaned_data
    
    class Meta:
        model = Eleitores
        fields = '__all__'
