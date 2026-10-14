# -*- coding: utf-8 -*-
"""Meses de fechamento do contrato (14/10/2026): o contrato marca os meses
em que um período de royalties FECHA; a periodicidade é lida deles."""
from datetime import date

from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval, datetime as safe_datetime
from dateutil.relativedelta import relativedelta
from lxml import etree


@tagged("post_install", "-at_install")
class TestSettlementMonths(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Month = cls.env["edlab.contract.month"]
        cls.contract = cls.env["edlab.contract"].create({})

    def _mark(self, *numbers):
        self.contract.settlement_month_ids = self.Month.search([("number", "in", numbers)])

    def test_twelve_months_exist(self):
        self.assertEqual(self.Month.search([]).mapped("number"), list(range(1, 13)))

    def test_periodicity_is_read_from_the_months(self):
        """Caminho feliz: meses espaçados por igual dão o nome certo."""
        for months, expected in (((12,), "annual"), ((6, 12), "semiannual"),
                                 ((3, 6, 9, 12), "quarterly"),
                                 (tuple(range(1, 13)), "monthly"),
                                 ((1, 7), "semiannual")):
            self._mark(*months)
            self.assertEqual(self.contract.settlement_periodicity, expected, months)

    def test_uneven_months_are_custom_and_none_is_empty(self):
        """Edge: espaçamento desigual é personalizado; sem mês, vazio."""
        self._mark(3, 4)
        self.assertEqual(self.contract.settlement_periodicity, "custom")
        self._mark(2, 5, 9, 12)
        self.assertEqual(self.contract.settlement_periodicity, "custom")
        self.contract.settlement_month_ids = False
        self.assertFalse(self.contract.settlement_periodicity)
        self.assertFalse(self.contract.next_closing_date)

    def test_next_closing(self):
        """O próximo fechamento é o último dia do próximo mês marcado,
        este mês incluído, virando o ano quando preciso."""
        self._mark(6, 12)
        self.assertEqual(self.contract._edlab_next_closing(date(2026, 10, 14)), date(2026, 12, 31))
        self.assertEqual(self.contract._edlab_next_closing(date(2026, 6, 30)), date(2026, 6, 30))
        self._mark(2)
        self.assertEqual(self.contract._edlab_next_closing(date(2026, 3, 1)), date(2027, 2, 28))

    def test_month_is_unique(self):
        """Erro: o mês 1 não nasce duas vezes."""
        from psycopg2.errors import UniqueViolation
        from odoo.tools import mute_logger
        with mute_logger("odoo.sql_db"), self.assertRaises(UniqueViolation), self.cr.savepoint():
            self.Month.create({"name": "Jan bis", "number": 1})

    def test_closes_this_month_filter(self):
        """O filtro da busca, lido da própria view, pega o contrato que fecha
        neste mês e deixa de fora o que não fecha."""
        view = self.env.ref("liber_copyright_contracts.view_edlab_contract_search")
        arch = etree.fromstring(self.env["edlab.contract"].get_view(view.id, "search")["arch"])
        domain = arch.xpath("//filter[@name='closes_this_month']")[0].get("domain")
        today = date.today()
        evaluated = safe_eval(domain, {"context_today": lambda: today,
                                       "relativedelta": relativedelta,
                                       "datetime": safe_datetime})
        self._mark(today.month)
        other = self.env["edlab.contract"].create({})
        other.settlement_month_ids = self.Month.search([("number", "!=", today.month)], limit=1)
        found = self.env["edlab.contract"].search(evaluated)
        self.assertIn(self.contract, found)
        self.assertNotIn(other, found)
