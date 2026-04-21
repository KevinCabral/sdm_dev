from django import forms


class CartaConviteForm(forms.ModelForm):   
    conteudo = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control' }),required=False, label="Conteudo")
    tipo = forms.CharField(max_length=20, required=True,label="Tipo")
    image = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-control-file'}),required=False)
    publishedAt = forms.CharField(required=False, label="Data Emissão de Documento Identificação")
