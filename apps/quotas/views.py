from django.shortcuts import render
import requests
from django.shortcuts import render, get_object_or_404,redirect
from .models import PagamentoQuotas,SendComprovativo, ValorPagamento
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import csv
from django.http import JsonResponse
from django.http import HttpResponse
from django.forms.models import model_to_dict
from .form import PagamentoQuotasForm
from django.core.exceptions import ObjectDoesNotExist
from django.views.decorators.http import require_POST
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone


@login_required
def createOrUpdate(request):
    form = PagamentoQuotasForm()
    if request.method == 'POST':
        id = request.POST.get("id", "")
        if id != "":
            pagamento = PagamentoQuotas.objects.get(pk=id)
            form = PagamentoQuotasForm(request.POST, request.FILES,instance=pagamento)
        else:
            form = PagamentoQuotasForm(request.POST, request.FILES)
        if form.is_valid():
            pagamento = form.save()
            if id != "":
                messages.success(request, f'Pagamento Atualizado')
            else:
                try:
                    if pagamento.militante and pagamento.militante.email_pessoal and pagamento.anexo_id:
                        email = SendComprovativo(
                            request=request,
                            email=pagamento.militante.email_pessoal,
                            nome=pagamento.militante.nome_completo,
                            text="O seu pagamento foi confirmado, no valor: " + str(pagamento.valor.valor) + ".",
                            anexo=pagamento.anexo_id.path,
                        )
                        email.send()
                except Exception as exc:
                    # Don't fail the whole transaction just because the SMTP server
                    # isn't reachable in dev / has bad credentials.
                    print(f"[quotas] Falha ao enviar comprovativo: {exc}")
                messages.success(request, f'Pagamento feito')
            return redirect("quotas.pagamento")
        else:
            print(form)
            if id != "":
                messages.error(request, f'Erro em atualizar pagamento')
            else:
                messages.error(request, f'Erro em fazer pagamento')
    return redirect("quotas.pagamento")


@login_required
def remover(request):
    if request.method == "POST":
        id = request.POST.get("id", "")
        pagamento = PagamentoQuotas.objects.get(pk=id)
        if pagamento:
            pagamento.status = 0
            pagamento.save()
            messages.success(request, f'Pagamento removido')
            return redirect("quotas.pagamento")

        messages.error(request, f'Erro em remover Pagamento')
        return redirect("quotas.pagamento")
    raise ObjectDoesNotExist()

@login_required
def pagamento(request):
    nome = request.GET.get("nome", "")
    data_inicio = request.GET.get("data_inicio", "")
    data_fim = request.GET.get("data_fim", "")
    filtro = {}
    
    if nome:
        filtro['militante__nome_completo__icontains'] = nome

    if data_inicio and data_fim:
        filtro['data_pagamento__range'] = (data_inicio, data_fim)

    pagamento = PagamentoQuotas.objects.filter(**filtro)
    paginator = Paginator(pagamento, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    breadcrumbs = [{'title': 'Pagina Inicial','url':'/'},{'title': 'Pagamentos de Quotas'}]
    return render(request, "pages/quotas/pagamento.html", {"page_obj":page_obj,'form':PagamentoQuotasForm,'breadcrumbs':breadcrumbs})


@login_required
def get(request):
    id = request.GET.get("id","")
    if id == "":
        return JsonResponse({})
    
    pagamento = PagamentoQuotas.objects.get(pk=id)
    
    
    if not(pagamento):
        messages.error(request, f'Erro na visualização de Pagamento')
        data = {}
    else:
        militante_dict = model_to_dict(pagamento.militante)
        # Convert any FieldFile / ImageFieldFile to its URL (or None) so JsonResponse can serialize it.
        from django.db.models.fields.files import FieldFile
        for k, v in list(militante_dict.items()):
            if isinstance(v, FieldFile):
                militante_dict[k] = v.url if v else None

        valor_dict = model_to_dict(pagamento.valor) if pagamento.valor else {}

        data = {
            "militante": militante_dict,
            "valor": valor_dict,
            "data_pagamento": pagamento.data_pagamento,
        }

        if  pagamento.anexo_id:
            data["anexo"] = pagamento.anexo_id.url
        else:
            data["anexo"] = ""
    return JsonResponse(data)

@login_required
def exportExcel(request):
    nome = request.GET.get("nome", "")
    data_inicio = request.GET.get("data_inicio", "")
    data_fim = request.GET.get("data_fim", "")
    filtro = {}
    
    if nome:
        filtro['militante__nome_completo__icontains'] = nome

    if data_inicio and data_fim:
        filtro['data__range'] = (data_inicio, data_fim)

    pagamento = PagamentoQuotas.objects(filtro).all()
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pagamento_quotas.csv"'},
    )

    writer = csv.writer(response)
    if len(pagamento) > 0:
        keys = list(model_to_dict(pagamento[0]).keys())
        header = []
        for k in keys: 
            text = k.replace("_", " ")
            header.append(text)
        writer.writerow(header)
        for i in pagamento:
            writer.writerow(list(model_to_dict(i).values()))
    return response


# ---------- ValorPagamento CRUD (web) ----------

def _parse_valor(raw):
    """Parse '1.234,50' / '1234,50' / '1234.50' / '1234' into a float."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Accept both 1234,50 and 1234.50
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(",") and s.count("."):
        # Assume comma is thousands sep
        s = s.replace(",", "")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _can_manage_valores(user):
    return user.is_superuser or user.has_perm("quotas.change_valorpagamento") or user.has_perm("quotas.add_valorpagamento")


@login_required
def valor_pagamento_index(request):
    """List page for ValorPagamento with search + status filter."""
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()

    qs = ValorPagamento.objects.all().order_by("-id")
    if q:
        valor_num = _parse_valor(q)
        if valor_num is not None:
            qs = qs.filter(valor=valor_num)
        else:
            qs = qs.filter(status__icontains=q)
    if status_filter:
        qs = qs.filter(status__iexact=status_filter)

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    breadcrumbs = [
        {"title": "Pagina Inicial", "url": "/"},
        {"title": "Valores de Pagamento"},
    ]
    return render(
        request,
        "pages/quotas/valor_pagamento.html",
        {
            "page_obj": page_obj,
            "q": q,
            "status_filter": status_filter,
            "breadcrumbs": breadcrumbs,
            "can_manage": _can_manage_valores(request.user),
        },
    )


def _valor_payload(request):
    valor = _parse_valor(request.POST.get("valor"))
    status = (request.POST.get("status") or "").strip() or None
    errors = {}
    if valor is None:
        errors["valor"] = "O valor é obrigatório e deve ser numérico."
    elif valor <= 0:
        errors["valor"] = "O valor deve ser maior que zero."
    return valor, status, errors


@login_required
@require_POST
def valor_pagamento_create_ajax(request):
    if not _can_manage_valores(request.user):
        return JsonResponse({"success": False, "error": "Sem permissão."}, status=403)

    valor, status, errors = _valor_payload(request)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    if ValorPagamento.objects.filter(valor=valor).exists():
        return JsonResponse(
            {"success": False, "errors": {"valor": "Já existe um valor igual."}},
            status=400,
        )

    now = timezone.now()
    obj = ValorPagamento.objects.create(
        valor=valor, status=status, createdat=now, updatedat=now
    )
    return JsonResponse(
        {
            "success": True,
            "message": f'Valor "{obj.valor}" criado com sucesso.',
            "valor": {"id": obj.id, "valor": obj.valor, "status": obj.status},
        }
    )


@login_required
def valor_pagamento_update_ajax(request, valor_id):
    """GET → return JSON with the row. POST → update."""
    if not _can_manage_valores(request.user):
        return JsonResponse({"success": False, "error": "Sem permissão."}, status=403)

    try:
        obj = ValorPagamento.objects.get(pk=valor_id)
    except ValorPagamento.DoesNotExist:
        return JsonResponse({"success": False, "error": "Não encontrado."}, status=404)

    if request.method == "GET":
        return JsonResponse(
            {
                "success": True,
                "valor": {
                    "id": obj.id,
                    "valor": obj.valor,
                    "status": obj.status or "",
                },
            }
        )

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método não permitido."}, status=405)

    valor, status, errors = _valor_payload(request)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    if ValorPagamento.objects.filter(valor=valor).exclude(pk=obj.pk).exists():
        return JsonResponse(
            {"success": False, "errors": {"valor": "Já existe um valor igual."}},
            status=400,
        )

    obj.valor = valor
    obj.status = status
    obj.updatedat = timezone.now()
    obj.save()
    return JsonResponse(
        {
            "success": True,
            "message": f'Valor "{obj.valor}" atualizado com sucesso.',
            "valor": {"id": obj.id, "valor": obj.valor, "status": obj.status},
        }
    )


@login_required
@require_POST
def valor_pagamento_delete_ajax(request, valor_id):
    if not _can_manage_valores(request.user):
        return JsonResponse({"success": False, "error": "Sem permissão."}, status=403)

    try:
        obj = ValorPagamento.objects.get(pk=valor_id)
    except ValorPagamento.DoesNotExist:
        return JsonResponse({"success": False, "error": "Não encontrado."}, status=404)

    label = obj.valor
    try:
        with transaction.atomic():
            obj.delete()
    except ProtectedError:
        return JsonResponse(
            {
                "success": False,
                "error": "Não é possível eliminar: existem pagamentos associados a este valor.",
            },
            status=400,
        )
    except IntegrityError:
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Não é possível eliminar este valor porque já existem pagamentos "
                    "associados. Reatribua-os ou desative o registo."
                ),
            },
            status=400,
        )
    except Exception as exc:
        return JsonResponse({"success": False, "error": f"Erro ao eliminar: {exc}"}, status=400)

    return JsonResponse(
        {"success": True, "message": f'Valor "{label}" eliminado com sucesso.'}
    )
