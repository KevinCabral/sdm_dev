from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from rest_framework import serializers


def user_payload(user):
    """Serialize a user with groups + permissions for the frontend."""
    groups = list(user.groups.values_list("name", flat=True))
    permissions = ["*"] if user.is_superuser else sorted(user.get_all_permissions())
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "groups": groups,
        "permissions": permissions,
        "militante_id": getattr(user, "militante_id", None),
    }


class UserSerializer(serializers.ModelSerializer):
    """Used by the (optional) registration endpoint."""

    class Meta:
        model = User
        fields = ("username", "password", "email")
        extra_kwargs = {"password": {"write_only": True}}

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    required_role = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional. Restrict login to users in this group (e.g. 'admin').",
    )

    def validate(self, attrs):
        user = authenticate(
            username=attrs.get("username"),
            password=attrs.get("password"),
        )
        if not user:
            raise serializers.ValidationError(
                {"detail": "Username ou password incorretos."}
            )
        if not user.is_active:
            raise serializers.ValidationError({"detail": "Conta desactivada."})

        required_role = (attrs.get("required_role") or "").strip()
        if required_role:
            allowed = (
                user.is_superuser
                or user.groups.filter(name__iexact=required_role).exists()
            )
            if not allowed:
                raise serializers.ValidationError(
                    {"detail": f"Utilizador sem permissão '{required_role}'."}
                )

        attrs["user"] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Password antiga incorreta.")
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": "UID inválido."})

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "Token inválido ou expirado."})

        attrs["user"] = user
        return attrs


def make_uid_token(user):
    return {
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": default_token_generator.make_token(user),
    }
