import logging

from django.contrib.auth.models import User

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer
from rest_framework import serializers as drf_serializers

from apps.users.models import SendUsernamePassword

from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    UserSerializer,
    make_uid_token,
    user_payload,
)

logger = logging.getLogger(__name__)


def _tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "token_type": "Bearer",
    }


class LoginView(APIView):
    """POST /api/auth/login/ — Bearer JWT login.

    Body: {"username", "password", "required_role"?}
    Returns: {access, refresh, token_type, user}
    """
    permission_classes = (AllowAny,)
    serializer_class = LoginSerializer

    @extend_schema(
        request=LoginSerializer,
        responses={200: inline_serializer(
            name='LoginResponse',
            fields={
                'access': drf_serializers.CharField(),
                'refresh': drf_serializers.CharField(),
                'token_type': drf_serializers.CharField(),
                'user': drf_serializers.DictField(),
            },
        )},
        tags=['Auth'],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        return Response({
            **_tokens_for_user(user),
            "user": user_payload(user),
        })


class LogoutView(APIView):
    """POST /api/auth/logout/ — invalidate the refresh token.

    Body: {"refresh": "..."}
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = inline_serializer(
        name='LogoutRequest',
        fields={'refresh': drf_serializers.CharField()},
    )

    @extend_schema(
        request=serializer_class,
        responses={205: OpenApiResponse(description='Logged out')},
        tags=['Auth'],
    )
    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"detail": "Refresh token obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh)
            # Requires 'token_blacklist' app to be installed and migrated.
            token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Token inválido ou já expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except AttributeError:
            # Blacklist app not installed — accept logout client-side anyway.
            pass
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(APIView):
    """GET /api/auth/me/ — current user info, groups and permissions."""
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        responses={200: inline_serializer(
            name='MeResponse',
            fields={
                'id': drf_serializers.IntegerField(),
                'username': drf_serializers.CharField(),
                'email': drf_serializers.EmailField(),
                'is_superuser': drf_serializers.BooleanField(),
                'is_staff': drf_serializers.BooleanField(),
                'groups': drf_serializers.ListField(child=drf_serializers.CharField()),
                'permissions': drf_serializers.ListField(child=drf_serializers.CharField()),
            },
        )},
        tags=['Auth'],
    )
    def get(self, request):
        return Response(user_payload(request.user))


class ChangePasswordView(APIView):
    """POST /api/auth/password/change/ — change current user's password."""
    permission_classes = (IsAuthenticated,)
    serializer_class = ChangePasswordSerializer

    @extend_schema(request=ChangePasswordSerializer, tags=['Auth'])
    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password alterada com sucesso."})


class PasswordResetRequestView(APIView):
    """POST /api/auth/password/reset/ — request a reset link by email.

    Always returns 200 to avoid leaking whether the email exists.
    """
    permission_classes = (AllowAny,)
    serializer_class = PasswordResetRequestSerializer

    @extend_schema(request=PasswordResetRequestSerializer, tags=['Auth'])
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        generic_response = Response(
            {"detail": "Se o email existir, foi enviado um link de recuperação."}
        )

        user = User.objects.filter(email__iexact=email).first()
        if not user or not user.email:
            return generic_response

        creds = make_uid_token(user)
        try:
            mailer = SendUsernamePassword(
                email=user.email,
                username=user.username,
                # Reuse existing template; password field carries the reset payload.
                password=f"uid={creds['uid']}&token={creds['token']}",
                request=request,
                template="gerar_password",
            )
            mailer.send()
        except Exception:
            logger.exception("Failed to send password reset email")
            return Response(
                {"detail": "Falha ao enviar email."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return generic_response


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password/reset/confirm/

    Body: {"uid", "token", "new_password"}
    """
    permission_classes = (AllowAny,)
    serializer_class = PasswordResetConfirmSerializer

    @extend_schema(request=PasswordResetConfirmSerializer, tags=['Auth'])
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password redefinida com sucesso."})


class UserRegistration(APIView):
    """POST /api/auth/register/ — optional self-registration."""
    permission_classes = (AllowAny,)
    serializer_class = UserSerializer

    @extend_schema(request=UserSerializer, tags=['Auth'])
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {**_tokens_for_user(user), "user": user_payload(user)},
            status=status.HTTP_201_CREATED,
        )
