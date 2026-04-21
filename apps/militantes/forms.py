from django import forms
from apps.militantes.models import Militantes

from django.forms.widgets import DateInput # need to import


class MilitantesForm(forms.ModelForm):
    
    GENERO = (("M" , "M"), ("F" ,"F"))
    ESTADO_CIVIL = (("Soleiro" , "Soleiro"), ("Casado" ,"Casado"))
    TIPO_IDENTIFICACAO = (("BI", "BI"), ("CNI", "CNI"))

    nome_completo = forms.CharField(max_length=200, required=True,label="Nome Completo")
    tp_associado = forms.CharField(max_length=20, required=True,label="Tipo Associado")
    alcunha = forms.CharField(max_length=20, label="Alcunha")
    nm_pai = forms.CharField(max_length=100, required=True, label="Nome de Pai")
    nm_mae = forms.CharField(max_length=100, required=True, label="Nome de Mãe")
    dt_nascimento = forms.CharField(max_length=20, required=True, label="Data de Nascimento")
    genero = forms.ChoiceField(choices=GENERO, required=True, label="Genero")
    estado_civil = forms.ChoiceField(choices=ESTADO_CIVIL, required=True, label="Estado Civil")
    agregado_familiar = forms.IntegerField( label="Número de Agregado Familiar")
    profissao_atual = forms.CharField(max_length=50, label="Profissão Actual")
    local_trabalho = forms.CharField(max_length=50,  label="Local de Trabalho")
    sector = forms.CharField(max_length=50,label="Sector")
    empresa = forms.CharField(max_length=50, label="Empresa")
    funcao = forms.CharField(max_length=50, label="Função")
    grau_academica = forms.CharField(max_length=50, required=True,label="Grau Academica")
    area_atuacao = forms.CharField(max_length=255,label="Area de Atuacao")
    curso = forms.CharField(required=False,max_length=50, label="Curso")
    dt_emissao_doc = forms.CharField(required=False, label="Data Emissão de Documento Identificação")
    nr_documento = forms.CharField(required=False,max_length=20, label="Número Documento Identificação")
    dt_validade_doc = forms.CharField(required=False,label="Data de Validação de Documento Identificação")
    tp_documento = forms.ChoiceField(choices=TIPO_IDENTIFICACAO, required=True, label="Tipo de Documento de Identificação")

    estado_militante = forms.CharField(max_length=100, required=False)
    
    nr_telemovel1 = forms.CharField(max_length=7, required=True,label="Telefone 1")
    nr_telemovel2 = forms.CharField(required=False,max_length=7,label="Telefone 2")
    nr_telefone_casa = forms.CharField(required=False,max_length=7,label="Telefone Casa")
    email_pessoal = forms.EmailField( required=True,label="Email")
    email_trabalho = forms.EmailField(required=False,label="Email de Trabalho")
    pais = forms.CharField(max_length=20, required=True,label="País")
    regiao = forms.CharField( required=True,label="Ilha")
    concelho = forms.CharField(required=True,label="Concelho")
    localidade = forms.CharField(max_length=20, required=True,label="Freguesia")
    zona = forms.CharField(max_length=20, required=True,label="Zona")
    morada_atual = forms.CharField(max_length=20, required=True,label="Morada Atual")
    perto_de = forms.CharField(required=False, max_length=20, label="Perto de")
    image = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-control-file'}),required=False)
    
    def __init__(self, *args, **kwargs):
        super(MilitantesForm, self).__init__(*args, **kwargs)
        for visible in self.visible_fields():
            visible.field.widget.attrs['class'] = 'form-control'
        self.fields['dt_validade_doc'].widget = forms.widgets.DateInput(
            # format="yyyy-mm-dd",
            
            attrs={
                'type': 'date', 'placeholder': 'yyyy-mm-dd',
                'class': 'form-control',
                }
            )
        self.fields['dt_emissao_doc'].widget = forms.widgets.DateInput(
            # format="yyyy-mm-dd",
            attrs={
                'type': 'date', 'placeholder': 'yyyy-mm-dd',
                'class': 'form-control'
                }
            )
        self.fields['dt_nascimento'].widget = forms.widgets.DateInput(
            # format="yyyy-mm-dd",
            attrs={
                'type': 'date', 'placeholder': 'yyyy-mm-dd',
                'class': 'form-control'
                }
            )
    class Meta:
        model = Militantes
        fields = '__all__'
        
            

