# -*- coding: utf-8 -*-
"""Tests for the accountant's export: months in, one ZIP out.

What is pinned down here is the SHAPE of the package, because that is what the
accountant receives and what nobody can check by reading the code: which XML
lands in which folder, that a month nobody ticked stays out, and that the
relacao.csv lists every file that is inside.
"""
import base64
import csv
import io
import zipfile

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .test_nfe_xml import KEY_1, KEY_2, NS, nfe_xml
from .test_import_wizard import KEY_3, cancel_event_xml

KEY_4 = "35260111222333000181550010000009991000009990"


def correction_xml(key, seq=1, text="Transportadora correta: LLS"):
    """A CC-e (tpEvento 110110) for ``key``."""
    return ("""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe xmlns="%(ns)s" versao="1.00">
  <evento versao="1.00">
    <infEvento Id="ID110110%(key)s0%(seq)s">
      <chNFe>%(key)s</chNFe>
      <tpEvento>110110</tpEvento>
      <nSeqEvento>%(seq)s</nSeqEvento>
      <dhEvento>2026-03-20T10:00:00-03:00</dhEvento>
      <detEvento><descEvento>Carta de Correcao</descEvento>
        <xCorrecao>%(text)s</xCorrecao></detEvento>
    </infEvento>
  </evento>
  <retEvento versao="1.00">
    <infEvento><nProt>135260000000123</nProt></infEvento>
  </retEvento>
</procEventoNFe>""" % {"ns": NS, "key": key, "seq": seq, "text": text}).encode()


@tagged("post_install", "-at_install")
class TestExportXmlWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Panel = cls.env["nfe.xml.panel"]
        cls.Wizard = cls.env["nfe.xml.export"]
        cls.company = cls.env.company

    def _note(self, key, date, direction="out", cancelled=False, name=None):
        return self.Panel.create({
            "key": key,
            "file": base64.b64encode(nfe_xml(key)),
            "file_name": name or ("%s-nfe.xml" % key),
            "file_create_date": date,
            "nfe_direction": direction,
            "is_cancelled": cancelled,
            "company_id": self.company.id,
            "status": "cancelled" if cancelled else "valid",
        })

    def _wizard(self, **extra):
        """O create já aplica o default_get, que é quem monta os meses.

        Repreencher aqui DUPLICAVA cada mês (comando (0,0) acrescenta, não
        substitui) e todo teste passava a exportar tudo em dobro.
        """
        return self.Wizard.create(dict({"company_id": self.company.id}, **extra))

    @staticmethod
    def _open(wizard):
        return zipfile.ZipFile(io.BytesIO(base64.b64decode(wizard.file)))

    @staticmethod
    def _csv_rows(archive):
        raw = archive.read("relacao.csv").decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(raw), delimiter=";"))

    # -- caminho feliz -------------------------------------------------
    def test_dois_meses_salteados_e_o_do_meio_fica_fora(self):
        """O pedido era marcar meses avulsos: março e maio, sem abril."""
        self._note(KEY_1, "2026-03-10")
        self._note(KEY_2, "2026-04-10")          # não marcado
        self._note(KEY_3, "2026-05-10", direction="in")
        wizard = self._wizard()

        for month in wizard.month_ids:
            month.selected = month.name in ("2026-03", "2026-05")
        wizard.action_export()

        self.assertEqual(wizard.state, "done")
        names = self._open(wizard).namelist()
        self.assertTrue(any("2026-03/saidas/" in n for n in names))
        self.assertTrue(any("2026-05/entradas/" in n for n in names))
        self.assertFalse([n for n in names if "2026-04" in n],
                         "o mês que ninguém marcou não pode entrar")
        self.assertIn("relacao.csv", names)

    def test_a_planilha_lista_todo_arquivo_que_esta_dentro(self):
        self._note(KEY_1, "2026-03-10")
        self._note(KEY_2, "2026-03-11", cancelled=True)
        wizard = self._wizard()
        wizard.month_ids.filtered(lambda m: m.name == "2026-03").selected = True
        wizard.action_export()

        archive = self._open(wizard)
        rows = self._csv_rows(archive)
        listados = {r["arquivo"] for r in rows}
        dentro = {n for n in archive.namelist() if n != "relacao.csv"}
        self.assertEqual(listados, dentro,
                         "a planilha e o ZIP têm de dizer a mesma coisa")
        self.assertIn(KEY_1, {r["chave"] for r in rows})

    def test_cancelada_vai_para_a_sua_pasta_com_o_evento(self):
        note = self._note(KEY_1, "2026-03-10", cancelled=True)
        self.Panel.register_nfe_event(cancel_event_xml(KEY_1))
        wizard = self._wizard()
        wizard.month_ids.filtered(lambda m: m.name == "2026-03").selected = True
        wizard.action_export()

        names = self._open(wizard).namelist()
        self.assertTrue(any("/canceladas/" in n for n in names))
        self.assertTrue(any("/eventos/" in n for n in names))
        self.assertTrue(note.is_cancelled)

    def test_carta_de_correcao_entra_no_pacote(self):
        """O que motivou a frente inteira: a carta é documento fiscal e tem de
        chegar ao contador junto com a nota."""
        self._note(KEY_1, "2026-03-10")
        self.Panel.register_nfe_event(correction_xml(KEY_1))
        wizard = self._wizard()
        wizard.month_ids.filtered(lambda m: m.name == "2026-03").selected = True
        wizard.action_export()

        archive = self._open(wizard)
        self.assertTrue(any("/eventos/" in n for n in archive.namelist()))
        obs = [r["observacao"] for r in self._csv_rows(archive) if r["observacao"]]
        self.assertTrue(any("LLS" in o for o in obs),
                        "o texto da carta tem de aparecer na planilha")

    # -- bordas --------------------------------------------------------
    def test_nota_sem_data_nao_some_calada(self):
        """Sem a linha 'sem data' estas notas ficariam fora de todo mês, e
        ninguém teria como notar."""
        self._note(KEY_1, False)
        wizard = self._wizard()

        sem_data = wizard.month_ids.filtered("no_date")
        self.assertEqual(len(sem_data), 1)
        self.assertEqual(sem_data.n_notes, 1)

        sem_data.selected = True
        wizard.action_export()
        self.assertTrue(any(n.endswith(".xml")
                            for n in self._open(wizard).namelist()))

    def test_tipo_desmarcado_fica_de_fora(self):
        self._note(KEY_1, "2026-03-10", direction="out")
        self._note(KEY_2, "2026-03-11", direction="in")
        wizard = self._wizard(include_in=False, include_internal=False)
        wizard.month_ids.filtered(lambda m: m.name == "2026-03").selected = True
        wizard.action_export()

        rows = self._csv_rows(self._open(wizard))
        self.assertEqual({r["chave"] for r in rows if r["documento"] == "NFe"},
                         {KEY_1})

    # -- erros ---------------------------------------------------------
    def test_sem_mes_marcado_diz_o_que_falta(self):
        self._note(KEY_1, "2026-03-10")
        wizard = self._wizard()
        with self.assertRaises(UserError) as erro:
            wizard.action_export()
        self.assertIn("month", str(erro.exception).lower())

    def test_sem_nenhum_tipo_marcado_diz_o_que_falta(self):
        self._note(KEY_1, "2026-03-10")
        wizard = self._wizard(include_out=False, include_in=False,
                              include_internal=False)
        wizard.month_ids.filtered(lambda m: m.name == "2026-03").selected = True
        with self.assertRaises(UserError):
            wizard.action_export()

    def test_dois_xml_de_mesmo_nome_nao_se_sobrescrevem(self):
        self._note(KEY_1, "2026-03-10", name="nota.xml")
        self._note(KEY_2, "2026-03-11", name="nota.xml")
        wizard = self._wizard()
        wizard.month_ids.filtered(lambda m: m.name == "2026-03").selected = True
        wizard.action_export()

        names = [n for n in self._open(wizard).namelist() if n != "relacao.csv"]
        self.assertEqual(len(names), 2, "um não pode engolir o outro")
        self.assertEqual(len(set(names)), 2)


@tagged("post_install", "-at_install")
class TestNfeEvents(TransactionCase):
    """A tabela de eventos deixou de ser só de cancelamento."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Panel = cls.env["nfe.xml.panel"]
        cls.Event = cls.env["nfe.xml.cancel.event"]

    def test_cartas_com_sequencias_diferentes_convivem(self):
        """A trava antiga era unique(key): a segunda carta derrubava a
        primeira, e a nota ficava sem metade da sua história."""
        self.Panel.register_nfe_event(correction_xml(KEY_1, seq=1, text="Primeira"))
        self.Panel.register_nfe_event(correction_xml(KEY_1, seq=2, text="Segunda"))

        eventos = self.Event.search([("key", "=", KEY_1)], order="n_seq_evento")
        self.assertEqual(len(eventos), 2)
        self.assertEqual(eventos.mapped("correction_text"), ["Primeira", "Segunda"])

    def test_a_mesma_carta_duas_vezes_nao_duplica(self):
        self.Panel.register_nfe_event(correction_xml(KEY_1, seq=1))
        self.Panel.register_nfe_event(correction_xml(KEY_1, seq=1))
        self.assertEqual(self.Event.search_count([("key", "=", KEY_1)]), 1)

    def test_carta_nao_cancela_a_nota(self):
        note = self.Panel.create({
            "key": KEY_4, "file": base64.b64encode(nfe_xml(KEY_4)),
            "file_name": "n.xml", "status": "valid",
        })
        self.Panel.register_nfe_event(correction_xml(KEY_4))

        self.assertFalse(note.is_cancelled)
        self.assertEqual(note.status, "valid")

    def test_cancelamento_continua_cancelando(self):
        note = self.Panel.create({
            "key": KEY_4, "file": base64.b64encode(nfe_xml(KEY_4)),
            "file_name": "n.xml", "status": "valid",
        })
        event = self.Panel.register_nfe_event(cancel_event_xml(KEY_4))

        self.assertEqual(event.event_kind, "cancel")
        self.assertTrue(note.is_cancelled)
        self.assertEqual(note.status, "cancelled")

    def test_register_cancellation_event_ignora_carta(self):
        """Quem chama o nome antigo quer cancelamento, e conta cancelamentos."""
        self.assertFalse(self.Panel.register_cancellation_event(correction_xml(KEY_1)))
