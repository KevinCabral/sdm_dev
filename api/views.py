from rest_framework import status
from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny

from django.contrib.auth.models import Group, User
from rest_framework import permissions, viewsets

from api.serializers import UserSerializer,ChangePasswordSerializer
from django.contrib.auth.hashers import check_password
from django.contrib.auth import authenticate
import string
import random

from apps.users.models import SendUsernamePassword

class UserRegistration(APIView):
    queryset = User.objects.all()  # Defina um queryset
    serializer_class = UserSerializer
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            # Criar um token de acesso para o novo usuário
            token, created = Token.objects.get_or_create(user=user)
            return Response({'username': user.username, 'email': user.email, 'token': token.key}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    
    queryset = User.objects.all()  # Defina um queryset
    serializer_class = ChangePasswordSerializer
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            old_password = serializer.data.get("old_password")
            new_password = serializer.data.get("new_password")
            if not check_password(old_password, user.password):
                return Response({"message": "Password antiga incorreta"}, status=status.HTTP_400_BAD_REQUEST)
            user.set_password(new_password)
            user.save()
            return Response({"message": "Password alterada com sucesso"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    permission_classes = (AllowAny,)
    queryset = User.objects.all() 

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        user = authenticate(username=username, password=password)
        if user:
            token, _ = Token.objects.get_or_create(user=user)
            return Response({'token': token.key})
        else:
            return Response({'error': 'Username ou password incorretos'}, status=400)


class RecoverPasswordView(APIView):
    permission_classes = (AllowAny,)
    queryset = User.objects.all() 

    def post(self, request):
        email = request.data.get('email')
        try:
            letters = string.ascii_letters + string.digits
            password = ''.join(random.choice(letters) for _ in range(12))
            user = User.objects.filter(email=email).first()

            if user.email == "" or user.email == None:
                return Response({"message": "Este user não possui email"}, status=status.HTTP_200_OK)

            user.set_password(password)

            sendEmail = SendUsernamePassword(email=user.email, username=user.username, password=password, request=None, template="gerar_password")
            sendEmail.send()
            user.save()
            return Response({"message": "Password alterada com sucesso, e foi enviado para seu email"}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"message": "Email não encontrado"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(e)
            return Response({"message": "Erro em gerar palavra-passe"}, status=status.HTTP_403_FORBIDDEN)
