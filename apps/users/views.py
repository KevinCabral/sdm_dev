from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.contrib.auth.forms import  PasswordResetForm
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import UserUpdateForm, ProfileUpdateForm,SetPasswordForm
from django.contrib import messages
import random
import string
from .models import *
from django.contrib.auth import update_session_auth_hash



@login_required
def users(request):
    is_active = request.GET.get("is_active","")
    if is_active != "":
        users = User.objects.filter(is_active=is_active)
    else:
        users = User.objects.all()
    return render(request, "pages/users/index.html", {"users": users})

@login_required
def bloquear(request):
    if request.method == "POST":
        id = request.POST.get("user-id", "")
        user = User.objects.get(pk=id)
        user.is_active = 0
        user.save()
        return HttpResponse("Success")
    raise ObjectDoesNotExist()

@login_required
def ativar(request):
    if request.method == "POST":
        id = request.POST.get("id", "")
        user = User.objects.get(pk=id)
        user.is_active = 1
        user.save()
        reset = PasswordResetForm(request.POST)
        if reset.is_valid():
            reset.save(request=request)
            return HttpResponse("Success")
    raise ObjectDoesNotExist()

@login_required
def updateProfile(request):
  userForm = UserUpdateForm
  profileUpdateForm = ProfileUpdateForm
  
  try:
    profile = Profile.objects.get(user_id=request.user.id)
  except:
    profile = None

  userForm = UserUpdateForm(instance=request.user)
  profileUpdateForm = ProfileUpdateForm(instance=profile)
  
  if request.method == 'POST':
        userForm = UserUpdateForm(request.POST, instance=request.user)
        profileUpdateForm = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if userForm.is_valid() and profileUpdateForm.is_valid():
          userForm.save()
          profileSave = profileUpdateForm.save(commit=False)
          profileSave.user_id = request.user.id
          profileSave.save()
          return redirect('users.profile') # Redirect back to profile page
        
  context = {
    'userForm': userForm,
    'profileUpdateForm': profileUpdateForm
  }
  return render(request, "pages/profile/update.html", context)

@login_required
def viewProfile(request):
  user = request.user
  try:
    profile = Profile.objects.get(user_id=request.user.id)
  except:
    profile = Profile
  context = {
    'user': user,
    'profile': profile
  }
  return render(request, "pages/profile/view.html", context)

@login_required
def generantePassword(request, id):
  try:
        letters = string.ascii_letters + string.digits
        password = ''.join(random.choice(letters) for _ in range(12))
        user = User.objects.get(pk=id)
        user.set_password(password)

        sendEmail = SendUsernamePassword(email=user.email, username=user.username, password=password, request=request, template="gerar_password")
        sendEmail.send()
        user.save()
        messages.success(request, f'Palavra-passe gerado!')
  except User.DoesNotExist:
      messages.error(request, f'Utilizador não encontrado')
  except Exception as e:
      print(e)
      messages.error(request, f'Erro em gerar palavra-passe')
  return redirect("/admin/auth/user/")

@login_required
def change_password(request,user_id):
    user = User.objects.get(id=user_id)
    if request.method == 'POST':
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'O palavra-passe de {user.username} foi alterado com sucesso!')
            return redirect('admin:auth_user_changelist')
        else:
            for field in form.errors:
                for error in form.errors[field]:
                    messages.error(request, error)
    else:
        form = SetPasswordForm(user)
    return render(request, "pages/users/password_change.html", {'form': form, "user":user})






