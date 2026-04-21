from django.shortcuts import render

from .models import UserMesa,Mesa
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404,redirect
from django.contrib.auth.decorators import login_required
import csv
from django.contrib import messages
from django.http import JsonResponse
from django.http import HttpResponse
from django.forms.models import model_to_dict
from .form import UserMesaForm,MesaForm
from django.core.exceptions import ObjectDoesNotExist

@login_required
def index(request):
    filtros = {}
    nome = request.GET.get("nome", "")
    nr_mesa = request.GET.get("nr_mesa", "")
    if nome:
        filtros['user__username__icontains'] = nome

    if nr_mesa:
        filtros['nr_mesa'] = nr_mesa
    userMesa = UserMesa.objects.filter(**filtros)
    paginator = Paginator(userMesa, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    form = UserMesaForm()
    breadcrumbs = [{'title': 'Pagina Inicial','url':'/'},{'title': 'Mesas'}]
    return render(request, "pages/mesa/index.html",{'page_obj': page_obj,'form':form,'breadcrumbs':breadcrumbs})

@login_required
def createOrUpdate(request):
    form = UserMesaForm()
    if request.method == 'POST':
        id = request.POST.get("id", "")
        if id != "":
            userMesa = UserMesa.objects.get(pk=id)
            form = UserMesaForm(request.POST,instance=userMesa)
        else:
            form = UserMesaForm(request.POST)
        if form.is_valid():
            userMesa = form.save()
            if id != "":
                messages.success(request, f'Atualizado')
            else:
                messages.success(request, f'Mesa Associada')
            return redirect("mesa.index")
        else:
            if id != "":
                messages.error(request, f'Erro na atualização')
            else:
                messages.error(request, f'Erro na associação de mesa')
    return redirect("mesa.index")


@login_required
def remover(request):
    if request.method == "POST":
        id = request.POST.get("id", "")
        mesa = UserMesa.objects.get(pk=id)
        if mesa:
            mesa.delete()
            messages.success(request, f'Mesa removido')
            return redirect("mesa.index")

        messages.error(request, f'Erro em remover Mesa')
        return redirect("mesa.index")
    raise ObjectDoesNotExist()


@login_required
def get(request):
    id = request.GET.get("id","")
    if id == "":
        return JsonResponse({})
    mesaUser = UserMesa.objects.get(pk=id)
    
    if not(mesaUser):
        messages.error(request, f'Erro na visualização de Mesa')
        data = {}
    else:
        data = {
            "mesa": model_to_dict(mesaUser.mesa),
            "user":model_to_dict(mesaUser.user)
        }
    return JsonResponse(data)

@login_required
def exportExcel(request):
    nome = request.GET.get("nome", "")
    nr_mesa = request.GET.get("nr_mesa", "")
    filtro = {}
    
    if nome:
        filtro['user__username__icontains'] = nome

    if nr_mesa:
        filtro['mesa__nr_mesa'] = nr_mesa

    mesas = UserMesa.objects.filter(**filtro).all()
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="utilizador_mesa.csv"'},
    )

    writer = csv.writer(response)
    if len(mesas) > 0:
        keys = list(model_to_dict(mesas[0]).keys())
        header = []
        keys.append("Username")
        for k in keys: 
            text = k.replace("_", " ")
            header.append(text)
        writer.writerow(header)
        for i in mesas:
            data = list(model_to_dict(i).values())
            data.append(i.user.username)
            writer.writerow(data)
    return response


@login_required
def indexMesa(request):
    filtros = {'status':'1'}
    mesa = Mesa.objects.filter(**filtros)
    paginator = Paginator(mesa, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    form = MesaForm()
    breadcrumbs = [{'title': 'Pagina Inicial','url':'/'},{'title': 'Mesas Associados'}]
    return render(request, "pages/mesa/mesa.html",{'page_obj': page_obj,'form':form,'breadcrumbs':breadcrumbs})

@login_required
def createOrUpdateMesa(request):
    form = MesaForm()
    if request.method == 'POST':
        id = request.POST.get("id", "")
        if id != "":
            userMesa = Mesa.objects.get(pk=id)
            form = MesaForm(request.POST,instance=userMesa)
        else:
            form = MesaForm(request.POST)
        if form.is_valid():
            userMesa = form.save()
            if id != "":
                messages.success(request, f'Mesa Atualizado')
            else:
                messages.success(request, f'Mesa Criado')
            return redirect("mesa.index_mesa")
        else:
            if id != "":
                messages.error(request, f'Erro em atualizar mesa')
            else:
                messages.error(request, f'Erro em criar mesa')
    return redirect("mesa.index_mesa")


@login_required
def removerMesa(request):
    if request.method == "POST":
        id = request.POST.get("id", "")
        eleitor = Mesa.objects.get(pk=id)
        if eleitor:
            eleitor.status = '0'
            eleitor.save()
            messages.success(request, f'Mesa removido')
            return redirect("mesa.index_mesa")

        messages.error(request, f'Erro em remover Mesa')
        return redirect("mesa.index_mesa")
    raise ObjectDoesNotExist()



@login_required
def getMesa(request):
    id = request.GET.get("id","")
    if id == "":
        return JsonResponse({})

    mesa = Mesa.objects.get(pk=id)
    
    if not(mesa):
        messages.error(request, f'Erro na visualização de Mesa')
        data = {}
    else:
        data = model_to_dict(mesa)
    return JsonResponse(data)

@login_required
def exportExcelMesa(request):
    filtro = {'status':'1'}

    mesas = Mesa.objects.filter(**filtro).all()
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="mesa.csv"'},
    )

    writer = csv.writer(response)
    if len(mesas) > 0:
        keys = list(model_to_dict(mesas[0]).keys())
        header = []
        for k in keys: 
            text = k.replace("_", " ")
            header.append(text)
        writer.writerow(header)
        for i in mesas:
            data = list(model_to_dict(i).values())
            writer.writerow(data)
    return response
