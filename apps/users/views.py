from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.models import User
from django.contrib.auth.models import Group
from django.contrib.auth.forms import  PasswordResetForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .forms import UserUpdateForm, ProfileUpdateForm,SetPasswordForm
from django.contrib import messages
import random
import string
from .models import *
from django.contrib.auth import update_session_auth_hash


@login_required
@require_POST
def create_ajax(request):
    """Create a new auth.User via JSON/AJAX. Returns JSON with success or field errors."""
    if not request.user.is_superuser and not request.user.has_perm('auth.add_user'):
        return JsonResponse({'success': False, 'error': 'Sem permissão.'}, status=403)

    username = (request.POST.get('username') or '').strip()
    email = (request.POST.get('email') or '').strip()
    first_name = (request.POST.get('first_name') or '').strip()
    last_name = (request.POST.get('last_name') or '').strip()
    password1 = request.POST.get('password1') or ''
    password2 = request.POST.get('password2') or ''
    is_staff = request.POST.get('is_staff') in ('on', 'true', '1')
    is_superuser = request.POST.get('is_superuser') in ('on', 'true', '1')
    is_active = request.POST.get('is_active', 'on') in ('on', 'true', '1')

    errors = {}
    if not username:
        errors['username'] = 'O nome de utilizador é obrigatório.'
    elif User.objects.filter(username__iexact=username).exists():
        errors['username'] = 'Já existe um utilizador com este nome.'
    if email and User.objects.filter(email__iexact=email).exists():
        errors['email'] = 'Já existe um utilizador com este email.'
    if not password1 or not password2:
        errors['password1'] = 'A palavra-passe é obrigatória.'
    elif password1 != password2:
        errors['password2'] = 'As palavras-passe não coincidem.'
    else:
        try:
            validate_password(password1)
        except ValidationError as e:
            errors['password1'] = ' '.join(e.messages)

    if errors:
        return JsonResponse({'success': False, 'errors': errors}, status=400)

    user = User.objects.create_user(
        username=username, email=email, password=password1,
        first_name=first_name, last_name=last_name,
    )
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    user.is_active = is_active
    user.save()
    group_ids = request.POST.getlist('groups')
    if group_ids:
        user.groups.set(Group.objects.filter(pk__in=group_ids))
    return JsonResponse({
        'success': True,
        'message': f'Utilizador "{user.username}" criado com sucesso.',
        'user': {'id': user.id, 'username': user.username, 'email': user.email},
    })


@login_required
def update_ajax(request, user_id):
    """GET → return user data as JSON. POST → update user. Password is optional on update."""
    if not request.user.is_superuser and not request.user.has_perm('auth.change_user'):
        return JsonResponse({'success': False, 'error': 'Sem permissão.'}, status=403)

    try:
        target = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Utilizador não encontrado.'}, status=404)

    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'user': {
                'id': target.id,
                'username': target.username,
                'email': target.email,
                'first_name': target.first_name,
                'last_name': target.last_name,
                'is_active': target.is_active,
                'is_staff': target.is_staff,
                'is_superuser': target.is_superuser,
                'groups': list(target.groups.values_list('id', flat=True)),
            },
        })

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método não permitido.'}, status=405)

    username = (request.POST.get('username') or '').strip()
    email = (request.POST.get('email') or '').strip()
    first_name = (request.POST.get('first_name') or '').strip()
    last_name = (request.POST.get('last_name') or '').strip()
    password1 = request.POST.get('password1') or ''
    password2 = request.POST.get('password2') or ''
    is_staff = request.POST.get('is_staff') in ('on', 'true', '1')
    is_superuser = request.POST.get('is_superuser') in ('on', 'true', '1')
    is_active = request.POST.get('is_active') in ('on', 'true', '1')

    errors = {}
    if not username:
        errors['username'] = 'O nome de utilizador é obrigatório.'
    elif User.objects.filter(username__iexact=username).exclude(pk=target.pk).exists():
        errors['username'] = 'Já existe um utilizador com este nome.'
    if email and User.objects.filter(email__iexact=email).exclude(pk=target.pk).exists():
        errors['email'] = 'Já existe um utilizador com este email.'

    if password1 or password2:
        if password1 != password2:
            errors['password2'] = 'As palavras-passe não coincidem.'
        else:
            try:
                validate_password(password1, user=target)
            except ValidationError as e:
                errors['password1'] = ' '.join(e.messages)

    # Prevent a user from removing their own superuser/active flags accidentally
    if target.pk == request.user.pk and (not is_active or not is_superuser and request.user.is_superuser):
        # Soft guard: keep current user's active flag, allow other changes
        if not is_active:
            errors['is_active'] = 'Não pode desativar a sua própria conta.'

    if errors:
        return JsonResponse({'success': False, 'errors': errors}, status=400)

    target.username = username
    target.email = email
    target.first_name = first_name
    target.last_name = last_name
    target.is_active = is_active
    target.is_staff = is_staff
    target.is_superuser = is_superuser
    if password1:
        target.set_password(password1)
    target.save()
    target.groups.set(Group.objects.filter(pk__in=request.POST.getlist('groups')))

    if password1 and target.pk == request.user.pk:
        update_session_auth_hash(request, target)

    return JsonResponse({
        'success': True,
        'message': f'Utilizador "{target.username}" atualizado com sucesso.',
        'user': {'id': target.id, 'username': target.username, 'email': target.email},
    })


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






