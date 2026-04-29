from django.test import SimpleTestCase

from .matching import name_score, parse_filiacao, normalize_name


class FiliacaoParseTests(SimpleTestCase):
    def test_pai_e_mae(self):
        self.assertEqual(
            parse_filiacao("ANTONIO CARLOS***MARIA DA FELICIDADE"),
            ("ANTONIO CARLOS", "MARIA DA FELICIDADE"),
        )

    def test_so_mae(self):
        self.assertEqual(parse_filiacao("***FATOUMATA SAMA"), ("", "FATOUMATA SAMA"))

    def test_so_pai(self):
        self.assertEqual(parse_filiacao("JOAO SILVA***"), ("JOAO SILVA", ""))

    def test_vazio(self):
        self.assertEqual(parse_filiacao(None), ("", ""))
        self.assertEqual(parse_filiacao(""), ("", ""))


class NormalizeTests(SimpleTestCase):
    def test_accents_and_case(self):
        self.assertEqual(normalize_name("José da Conceição"), "JOSE DA CONCEICAO")

    def test_collapse_spaces(self):
        self.assertEqual(normalize_name("  ANA   MARIA  "), "ANA MARIA")


class NameScoreTests(SimpleTestCase):
    def test_identical(self):
        self.assertEqual(name_score("Joao Silva", "JOAO SILVA"), 100.0)

    def test_partial(self):
        s = name_score("Joao Carlos Silva", "Joao Silva")
        self.assertGreater(s, 60)
        self.assertLess(s, 100)
