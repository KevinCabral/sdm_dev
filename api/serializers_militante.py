"""
Serializers for the Militantes mobile API.

Three flavours:
- `MilitantePublicRegisterSerializer` → self-registration (anonymous).
- `MilitanteSelfSerializer`           → read/update own profile (auth militante).
- `MilitanteAdminSerializer`          → full read/write for admin.
- `MilitanteApproveSerializer`        → admin approval payload (group, send_email).
- `MilitanteRejectSerializer`         → admin rejection payload (motivo).
"""
from rest_framework import serializers

from apps.militantes.models import Militantes


# Fields the militant can fill in on self-registration / self-update.
SELF_EDITABLE_FIELDS = (
    "nome_completo",
    "alcunha",
    "nm_pai",
    "nm_mae",
    "genero",
    "estado_civil",
    "agregado_familiar",
    "profissao_atual",
    "local_trabalho",
    "sector",
    "empresa",
    "funcao",
    "grau_academica",
    "area_atuacao",
    "curso",
    "dt_emissao_doc",
    "dt_validade_doc",
    "email_pessoal",
    "email_trabalho",
    "nr_documento",
    "nr_telefone_casa",
    "nr_telemovel1",
    "nr_telemovel2",
    "tp_documento",
    "dt_nascimento",
    "image",
    "latitude",
    "longitude",
)

# Read-only metadata exposed to the militant (admin-managed lifecycle fields).
READ_ONLY_LIFECYCLE_FIELDS = (
    "id",
    "estado_militante",
    "estado_ficha",
    "tp_associado",
    "motivo_rejeicao",
    "status",
    "is_mobile",
)


class MilitantePublicRegisterSerializer(serializers.ModelSerializer):
    """Public self-registration. Creates a `Militantes` row in 'P' (Pendente)."""

    class Meta:
        model = Militantes
        fields = SELF_EDITABLE_FIELDS
        # Image is required at the DB level — keep it required here too.
        extra_kwargs = {
            "nome_completo": {"required": True, "allow_blank": False},
            "email_pessoal": {"required": True, "allow_blank": False},
            "nr_documento": {"required": True, "allow_blank": False},
        }

    def validate_email_pessoal(self, value):
        # Soft duplicate check on the unique-ish business field.
        qs = Militantes.objects.filter(email_pessoal__iexact=value).exclude(
            estado_militante="D"
        )
        if qs.exists():
            raise serializers.ValidationError(
                "Já existe um militante registado com este email."
            )
        return value

    def validate_nr_documento(self, value):
        qs = Militantes.objects.filter(nr_documento=value).exclude(
            estado_militante="D"
        )
        if qs.exists():
            raise serializers.ValidationError(
                "Já existe um militante com este número de documento."
            )
        return value

    def create(self, validated_data):
        validated_data["estado_militante"] = "P"
        validated_data["is_mobile"] = True
        return super().create(validated_data)


class MilitanteSelfSerializer(serializers.ModelSerializer):
    """Own profile read + update. Lifecycle fields are read-only."""

    class Meta:
        model = Militantes
        fields = SELF_EDITABLE_FIELDS + READ_ONLY_LIFECYCLE_FIELDS
        read_only_fields = READ_ONLY_LIFECYCLE_FIELDS


class MilitanteAdminSerializer(serializers.ModelSerializer):
    """Full read/write for admin endpoints."""

    class Meta:
        model = Militantes
        fields = "__all__"


class MilitanteApproveSerializer(serializers.Serializer):
    username = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional. Defaults to email_pessoal local-part or 'militante_<id>'.",
    )
    group = serializers.CharField(
        required=False,
        allow_blank=True,
        default="militante",
        help_text="Group to assign on approval (e.g. 'militante', 'delegado').",
    )
    send_email = serializers.BooleanField(required=False, default=True)


class MilitanteRejectSerializer(serializers.Serializer):
    motivo = serializers.CharField(required=True, allow_blank=False, max_length=1000)
