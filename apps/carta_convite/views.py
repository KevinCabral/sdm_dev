from django.shortcuts import render
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
import json
from django.http import HttpResponse
import requests
import os
from django.contrib import messages
from datetime import datetime

# Create your views here.
urlApi = os.getenv('URL_API'   , "")
urlApps = "cms/api/carta-convites"

auth = {"apikey":"e6d2d89c1837c6f03b5c93efe181a5df2466551f27cd1062e08341754f44e5fa997b453691928ddc387ebdf7946bb5e3f78df98781eb524962ce41f28f931a7a18c139d8711749af18d6121325de2ada8f7f132e8ff90f9f5a15a189571cf6948b2b86234a942f310e5f3b60a8a54582b3284c32a189774fdccdfc938d295f3c"}

@login_required
def index(request):
    url = urlApi + urlApps
    params = {
        "populate":"*",
        "publicationState":"preview"
    }
    response = requests.get(url,headers=auth,params=params)
    data = response.json()
    if response.status_code == 200 :
        cartas = data["results"]
    else:
        cartas = []
    breadcrumbs = [{'title': 'Pagina Inicial','url':'/'},{'title': 'Carta de Convite'}]
    return render(request, "pages/carta_convite/index.html", {"cartas": cartas,"urlImage":"https://militantes.mpd.cv:8080/appgwt/cms/images/",'breadcrumbs':breadcrumbs})

def uploadImagem(imagem):
    # Envie a imagem para a API externa
    url = urlApi + "cms/api/upload"
    headers=auth
    files = {'files': imagem}
    response = requests.post(url, headers=headers, files=files, data={"field":"imagem"})
    data = response.json()
    if response.status_code == 200 and data["info"]["status"] == 200:
        # Sucesso ao enviar para a API externa
        return data["results"][0]["formats"]["medium"]["url"]
    else:
        return None

@login_required
def create(request):
    if request.method == "POST":
        tipo = request.POST.get("tipo", "")
        conteudo = request.POST.get("conteudo", "")
        isPublish = request.POST.get("isPublish", "")
        data = {
            "data": {
                "conteudo": conteudo ,
                "tipo": tipo,
                "active": True
            }
        }
        imagem = request.FILES.get('imagem',None)
       
        if imagem:
            idFile = uploadImagem(imagem)
            data["data"]["imagem"] = idFile

        if isPublish == "false":
            data["data"]["publishedAt"] = None
        
        url = urlApi + urlApps
        headers=auth
        headers["Content-Type"] = "application/json"
        response = requests.post(url,headers=headers,data=json.dumps(data))
        data = response.json()
        print(data)
        if response.status_code == 200 and data["info"]["status"] == 200:
            messages.success(request, f'Carta de convite criado')
            return redirect("carta_convite.index")
        else:
            messages.error(request, f'Erro em criar carta de convite, tente mais tarde')
            return redirect("carta_convite.index")
    raise ObjectDoesNotExist()

@login_required
def update(request):
    if request.method == "POST":
        tipo = request.POST.get("tipo", "")
        id = request.POST.get("id", "")
        conteudo = request.POST.get("conteudo", "")

        data = {
            "data": {
                "conteudo": conteudo,
                "tipo": tipo,
            }
        }
        
        imagem = request.FILES.get('imagem',None)
        
        if imagem:
            idFile = uploadImagem(imagem)
            data["data"]["imagem"] = idFile

        url = urlApi + urlApps + "/"+id
        headers=auth
        headers["Content-Type"] = "application/json"
        print(data)
        response = requests.put(url,headers=headers,data=json.dumps(data))
        data = response.json()
        print(data)
        if response.status_code == 200 and data["info"]["status"] == 200:
            messages.success(request, f'Carta de convite atualizado')
            return redirect("carta_convite.index")
        else:
            messages.error(request, f'Erro em atualizado carta de convite, tente mais tarde')
            return redirect("carta_convite.index")
    raise ObjectDoesNotExist()

@login_required
def notPublications(request):
    if request.method == "POST":
        id = request.POST.get("id", "")
        url = urlApi + urlApps + "/" + id
        
        dataForms = {
            "data": {
                "active":False
            }
        }

        headers=auth
        headers["Content-Type"] = "application/json"
        response = requests.put(url,headers=headers,data=json.dumps(dataForms))
        data = response.json()
  
        if response.status_code == 200 and data["info"]["status"] == 200:
            messages.success(request, f'Carta de convite Despublicado')
            return redirect("carta_convite.index")
        else:
            messages.error(request, f'Erro em despublicar carta de convite, tente mais tarde')
            return redirect("carta_convite.index")
    raise ObjectDoesNotExist()

@login_required
def publications(request):
    if request.method == "POST":
        id = request.POST.get("id", "")
        url = urlApi + urlApps + "/"+id
        headers=auth
        headers["Content-Type"] = "application/json"
        data_hora_atual = datetime.now()

        dataForms = {
            "data": {
                "publishedAt":data_hora_atual.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "active":True
            }
        }
        response = requests.put(url,headers=headers,data=json.dumps(dataForms))
        data = response.json()
 
        if response.status_code == 200 and data["info"]["status"] == 200:
            messages.success(request, f'Carta de convite Publicado')
            return redirect("carta_convite.index")
        else:
            messages.error(request, f'Erro em publicar carta de convite, tente mais tarde')
            return redirect("carta_convite.index")
    raise ObjectDoesNotExist()




