"""
Serializers for Mesa / UserMesa / Eleitores resources.

Kept separate from `serializers.py` (which is auth-focused) to avoid clutter.
"""
from django.contrib.auth.models import User
from rest_framework import serializers

from apps.eleitores.models import Eleitores
from apps.mesa.models import Mesa, UserMesa


# ---------- Mesa ----------

class MesaSerializer(serializers.ModelSerializer):
    eleitores_count = serializers.SerializerMethodField()

    class Meta:
        model = Mesa
        fields = ["id", "nr_mesa", "status", "eleitores_count", "createdAt", "updatedAt"]
        read_only_fields = ["id", "createdAt", "updatedAt", "eleitores_count"]

    def get_eleitores_count(self, obj):
        return Eleitores.objects.filter(nr_mesa=obj.nr_mesa, falecido=False).count()


# ---------- UserMesa (delegado assignment) ----------

class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]
        read_only_fields = fields


class UserMesaSerializer(serializers.ModelSerializer):
    user_detail = UserMiniSerializer(source="user", read_only=True)
    mesa_detail = MesaSerializer(source="mesa", read_only=True)

    class Meta:
        model = UserMesa
        fields = [
            "id",
            "user",
            "mesa",
            "user_detail",
            "mesa_detail",
            "createdAt",
            "updatedAt",
        ]
        read_only_fields = ["id", "createdAt", "updatedAt", "user_detail", "mesa_detail"]


class UserMesaBulkAssignSerializer(serializers.Serializer):
    """Assign a user to a list of mesas at once (replaces existing assignments)."""

    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    mesas = serializers.PrimaryKeyRelatedField(
        queryset=Mesa.objects.all(), many=True
    )


# ---------- Eleitores ----------

class EleitorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Eleitores
        fields = [
            "id",
            "nome",
            "nominho",
            "filiacao",
            "data_nascimento",
            "idade_eleitor",
            "contato",
            "nacionalidade",
            "concelho",
            "zona",
            "nr_mesa",
            "nr_eleitor",
            "ausente",
            "indeciso",
            "nao_vai_votar",
            "mpd",
            "descarga",
            "datahora_atualizacao",
        ]
        read_only_fields = ["id", "datahora_atualizacao"]


class EleitorListSerializer(serializers.ModelSerializer):
    """Lighter payload for list endpoints."""

    class Meta:
        model = Eleitores
        fields = [
            "id",
            "nome",
            "nominho",
            "concelho",
            "zona",
            "nr_mesa",
            "nr_eleitor",
            "mpd",
            "indeciso",
            "nao_vai_votar",
            "descarga",
        ]
        read_only_fields = fields


class EleitorMarkSerializer(serializers.Serializer):
    """Payload for the `descarga` action — mark/unmark an eleitor as voted."""

    descarga = serializers.BooleanField()
