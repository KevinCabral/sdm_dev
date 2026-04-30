"""Serializers for the Quotas mobile API."""
from rest_framework import serializers

from apps.quotas.models import PagamentoQuotas, ValorPagamento


class ValorPagamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValorPagamento
        fields = ("id", "valor", "status", "createdat", "updatedat")
        read_only_fields = ("createdat", "updatedat")

    def validate_valor(self, value):
        if value is None:
            raise serializers.ValidationError("O valor é obrigatório.")
        if value <= 0:
            raise serializers.ValidationError("O valor deve ser maior que zero.")
        return value


class PagamentoQuotasSerializer(serializers.ModelSerializer):
    """Read serializer used both by the militant and admin endpoints."""

    valor = ValorPagamentoSerializer(read_only=True)
    valor_id = serializers.PrimaryKeyRelatedField(
        queryset=ValorPagamento.objects.all(),
        source="valor",
        write_only=True,
        required=False,
        allow_null=True,
    )
    anexo_url = serializers.SerializerMethodField()
    militante_id = serializers.IntegerField(source="militante.id", read_only=True)
    militante_nome = serializers.CharField(
        source="militante.nome_completo", read_only=True
    )

    class Meta:
        model = PagamentoQuotas
        fields = (
            "id",
            "valor",
            "valor_id",
            "data_pagamento",
            "anexo_id",
            "anexo_url",
            "militante_id",
            "militante_nome",
            "createdat",
            "updatedat",
        )
        read_only_fields = ("createdat", "updatedat")
        extra_kwargs = {
            "anexo_id": {"write_only": True, "required": True},
            "data_pagamento": {"required": True},
        }

    def get_anexo_url(self, obj):
        if obj.anexo_id:
            try:
                return obj.anexo_id.url
            except Exception:
                return None
        return None
