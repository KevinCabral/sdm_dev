"""Serializers for the eleitor ↔ militante matched dataset (mobile API)."""
from rest_framework import serializers

from apps.eleitores.models import Eleitores
from apps.militante_match.models import EleitorMilitanteMatch
from apps.militantes.models import Militantes


class MilitanteContactSerializer(serializers.ModelSerializer):
    """Minimal militante payload used inside the matched-eleitor list.

    Exposes the contact numbers and geographic coordinates the field team
    needs to call/locate the militante on election day.
    """

    class Meta:
        model = Militantes
        fields = [
            "id",
            "nome_completo",
            "alcunha",
            "dt_nascimento",
            "nr_telefone_casa",
            "nr_telemovel1",
            "nr_telemovel2",
            "email_pessoal",
            "latitude",
            "longitude",
        ]
        read_only_fields = fields


class EleitorMilitanteSerializer(serializers.ModelSerializer):
    """Read-only view of an eleitor confirmed as a militante."""

    militante = MilitanteContactSerializer(source="militante_id", read_only=True)
    ja_votou = serializers.SerializerMethodField()

    class Meta:
        model = Eleitores
        fields = [
            "id",
            "nome",
            "nominho",
            "data_nascimento",
            "concelho",
            "zona",
            "nr_mesa",
            "nr_eleitor",
            "descarga",
            "ja_votou",
            "militante",
        ]
        read_only_fields = fields

    def get_ja_votou(self, obj):
        # `descarga` is the field actively maintained by delegados during
        # the election; fall back to it for a fast yes/no signal.
        return bool(obj.descarga)


class VotingPaceBucketSerializer(serializers.Serializer):
    hour = serializers.IntegerField()  # 0..7 since election start
    label = serializers.CharField()    # e.g. "08:00–09:00"
    expected_cumulative = serializers.IntegerField()
    actual_cumulative = serializers.IntegerField()
    delta = serializers.IntegerField()
    is_slow = serializers.BooleanField()


class VotingPaceResponseSerializer(serializers.Serializer):
    total_militantes = serializers.IntegerField()
    voted = serializers.IntegerField()
    pending = serializers.IntegerField()
    percent_voted = serializers.FloatField()
    expected_now = serializers.IntegerField()
    delta_now = serializers.IntegerField()
    is_slow = serializers.BooleanField()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    duration_hours = serializers.FloatField()
    elapsed_hours = serializers.FloatField()
    threshold_pct = serializers.FloatField()
    by_hour = VotingPaceBucketSerializer(many=True)
    nr_mesa = serializers.CharField(allow_null=True, required=False)
