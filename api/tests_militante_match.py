"""API tests for the eleitor-militante endpoints + voting pace."""
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.eleitores.models import Eleitores, Votacao
from apps.militante_match.models import EleitorMilitanteMatch
from apps.militantes.models import Militantes


class EleitorMilitanteApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Group.objects.get_or_create(name="gestor_militantes")
        Group.objects.get_or_create(name="admin")

        cls.gestor = User.objects.create_user("gestor", password="x")
        cls.gestor.groups.add(Group.objects.get(name="gestor_militantes"))

        cls.outsider = User.objects.create_user("outsider", password="x")

        cls.militante = Militantes.objects.create(
            nome_completo="JOAO SILVA",
            nr_telemovel1=2389991111,
            latitude="14.917",
            longitude="-23.508",
        )
        cls.eleitor = Eleitores.objects.create(
            nome="Joao Silva", nr_eleitor=1, nr_mesa="1",
            data_nascimento="1980-01-01",
        )
        EleitorMilitanteMatch.objects.create(
            eleitor=cls.eleitor, militante=cls.militante,
            score=99, status=EleitorMilitanteMatch.STATUS_CONFIRMED,
        )

    def test_outsider_forbidden(self):
        self.client.force_authenticate(self.outsider)
        r = self.client.get("/api/eleitores-militantes/")
        self.assertEqual(r.status_code, 403)

    def test_gestor_can_list_with_contacts(self):
        self.client.force_authenticate(self.gestor)
        r = self.client.get("/api/eleitores-militantes/")
        self.assertEqual(r.status_code, 200)
        data = r.json()["results"]
        self.assertEqual(len(data), 1)
        m = data[0]["militante"]
        self.assertEqual(m["nr_telemovel1"], 2389991111)
        self.assertEqual(str(m["latitude"]), "14.917000")

    def test_gestor_cannot_post(self):
        self.client.force_authenticate(self.gestor)
        r = self.client.post("/api/eleitores-militantes/", {})
        self.assertIn(r.status_code, (403, 405))


class VotingPaceTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Group.objects.get_or_create(name="gestor_militantes")
        cls.gestor = User.objects.create_user("g2", password="x")
        cls.gestor.groups.add(Group.objects.get(name="gestor_militantes"))

        # 10 militantes, all with confirmed matches
        for i in range(10):
            mil = Militantes.objects.create(nome_completo=f"M{i}")
            el = Eleitores.objects.create(
                nome=f"E{i}", nr_eleitor=1000 + i, nr_mesa="1",
            )
            EleitorMilitanteMatch.objects.create(
                eleitor=el, militante=mil,
                score=99, status=EleitorMilitanteMatch.STATUS_CONFIRMED,
            )

        # Election started 2h ago, 4 militantes already voted
        cls.start_at = timezone.now() - timedelta(hours=2)
        for i in range(4):
            Votacao.objects.create(
                nr_eleitor=1000 + i,
                votou=1,
                anulado=0,
                nr_mesa="1",
                datetime=cls.start_at + timedelta(minutes=30 * (i + 1)),
            )

    def test_voting_pace_payload(self):
        self.client.force_authenticate(self.gestor)
        r = self.client.get(
            "/api/eleitores-militantes/voting-pace/",
            {"start_at": self.start_at.isoformat(), "duration_hours": 8},
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["total_militantes"], 10)
        self.assertEqual(body["voted"], 4)
        self.assertEqual(body["pending"], 6)
        # 2h / 8h = 25% expected → 2.5 → rounded 2 or 3 depending on rounding
        self.assertIn(body["expected_now"], (2, 3))
        self.assertEqual(len(body["by_hour"]), 8)
