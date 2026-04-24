"""
Serializers for Mesa / UserMesa / Eleitores resources.

Kept separate from `serializers.py` (which is auth-focused) to avoid clutter.
"""
from django.contrib.auth.models import User
from rest_framework import serializers

from apps.eleitores.models import Eleitores
from apps.eleitores.models import Votacao
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


class EleitorFlagsSerializer(serializers.Serializer):
    """
    Payload for the `mark-flags` action.

    Any combination of the boolean flags below may be provided. Only the
    fields present in the request are updated. At least one flag is required.
    """

    nao_vai_votar = serializers.BooleanField(required=False)
    ausente = serializers.BooleanField(required=False)
    indeciso = serializers.BooleanField(required=False)
    mpd = serializers.BooleanField(required=False)
    descarga = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Forneça pelo menos um dos campos: nao_vai_votar, ausente, indeciso, mpd, descarga."
            )
        return attrs


# ---------- Votacao ----------

class VotacaoSerializer(serializers.ModelSerializer):
    """Full votacao record with optional enriched eleitor info."""

    eleitor_nome = serializers.SerializerMethodField()
    eleitor_id = serializers.SerializerMethodField()

    class Meta:
        model = Votacao
        fields = [
            "id",
            "assembleia_voto_nr",
            "nr_eleitor",
            "nr_bi_eleitor",
            "nr_mesa",
            "votou",
            "anulado",
            "motivo_n_votou",
            "datetime",
            "eleitor_id",
            "eleitor_nome",
        ]
        read_only_fields = ["id", "datetime", "eleitor_id", "eleitor_nome"]

    def _eleitor(self, obj):
        # Resolve the eleitor lazily (no FK on the legacy table).
        if not getattr(self, "_eleitor_cache", None):
            self._eleitor_cache = {}
        key = (obj.nr_eleitor, obj.nr_mesa)
        if key not in self._eleitor_cache:
            self._eleitor_cache[key] = (
                Eleitores.objects.filter(
                    nr_eleitor=obj.nr_eleitor, nr_mesa=obj.nr_mesa
                ).first()
                or Eleitores.objects.filter(nr_eleitor=obj.nr_eleitor).first()
            )
        return self._eleitor_cache[key]

    def get_eleitor_nome(self, obj):
        e = self._eleitor(obj)
        return e.nome if e else None

    def get_eleitor_id(self, obj):
        e = self._eleitor(obj)
        return e.id if e else None


class VotacaoRegisterSerializer(serializers.Serializer):
    """Register a new vote for a given eleitor.

    Either `nr_eleitor` + `nr_mesa` OR an `eleitor_id` is required.
    """

    nr_eleitor = serializers.IntegerField(required=False)
    nr_mesa = serializers.CharField(required=False, allow_blank=True)
    eleitor_id = serializers.IntegerField(required=False)
    assembleia_voto_nr = serializers.CharField(required=False, allow_blank=True, max_length=1)
    nr_bi_eleitor = serializers.CharField(required=False, allow_blank=True, max_length=30)
    anulado = serializers.BooleanField(required=False, default=False)
    motivo_n_votou = serializers.CharField(required=False, allow_blank=True, max_length=150)

    def validate(self, attrs):
        eleitor = None
        if attrs.get("eleitor_id"):
            eleitor = Eleitores.objects.filter(pk=attrs["eleitor_id"]).first()
            if not eleitor:
                raise serializers.ValidationError({"eleitor_id": "Eleitor não encontrado."})
        elif attrs.get("nr_eleitor"):
            qs = Eleitores.objects.filter(nr_eleitor=attrs["nr_eleitor"])
            if attrs.get("nr_mesa"):
                qs = qs.filter(nr_mesa=attrs["nr_mesa"])
            eleitor = qs.first()
            if not eleitor:
                raise serializers.ValidationError(
                    {"nr_eleitor": "Eleitor não encontrado para os dados fornecidos."}
                )
        else:
            raise serializers.ValidationError(
                "Indique 'eleitor_id' ou 'nr_eleitor' (com 'nr_mesa' opcional)."
            )

        if not eleitor.nr_mesa:
            raise serializers.ValidationError(
                {"nr_mesa": "Eleitor não tem mesa associada."}
            )

        attrs["eleitor"] = eleitor
        return attrs


class VotacaoUnregisterSerializer(serializers.Serializer):
    """Cancel/anular a vote — by votacao id or by nr_eleitor."""

    votacao_id = serializers.IntegerField(required=False)
    nr_eleitor = serializers.IntegerField(required=False)
    nr_mesa = serializers.CharField(required=False, allow_blank=True)
    motivo = serializers.CharField(required=False, allow_blank=True, max_length=150)

    def validate(self, attrs):
        if not attrs.get("votacao_id") and not attrs.get("nr_eleitor"):
            raise serializers.ValidationError(
                "Indique 'votacao_id' ou 'nr_eleitor'."
            )
        return attrs
