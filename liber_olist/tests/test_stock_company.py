# -*- coding: utf-8 -*-
"""The stock push must respect the company - tests for that alone.

The push writes into a LIVE fiscal account, so "which company's stock did we
just declare?" is not a detail. Three ways it used to leak, each pinned here:

1. on-hand summed across every enabled company, because `with_company()` unions
   the company into env.companies and `qty_available` reads env.companies;
2. one shared `olist_produto_id`, so a second company's push landed on the
   first company's product in Olist;
3. a fallback to "any account" when the current company had none, which sent
   one company's numbers to another company's Olist.

Companies are REUSED from the database rather than created: with `account`
installed, res.company.create trips over fiscalyear_last_day. See
liber_olist/NOTES.md section 10.5.
"""
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client

OK_RESP = ('{"retorno":{"status":"OK","registros":[{"registro":'
           '{"id":9,"saldoEstoque":"42.0000","registroCriado":false}}]}}')


@tagged('post_install', '-at_install')
class TestOlistStockCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})

        # Two companies that actually hold stock. A warehouse is what makes a
        # company able to have on-hand at all, so pick companies by warehouse.
        warehouses = {}
        for wh in cls.env['stock.warehouse'].search([]):
            warehouses.setdefault(wh.company_id, wh)
        if len(warehouses) < 2:
            company_a, wh_a = next(iter(warehouses.items()))
            company_b = cls.env['res.company'].search(
                [('id', '!=', company_a.id)], limit=1)
            wh_b = cls.env['stock.warehouse'].create({
                'name': "Olist Test WH", 'code': 'OLTWH',
                'company_id': company_b.id,
            })
        else:
            (company_a, wh_a), (company_b, wh_b) = list(warehouses.items())[:2]

        cls.company_a, cls.wh_a = company_a, wh_a
        cls.company_b, cls.wh_b = company_b, wh_b

        cls.account_a = cls.env['olist.account'].create({
            'name': "Olist A", 'company_id': company_a.id, 'token': "TOKEN-A", 'read_only': False,
        })
        cls.account_b = cls.env['olist.account'].create({
            'name': "Olist B", 'company_id': company_b.id, 'token': "TOKEN-B", 'read_only': False,
        })

        # A shared book (company_id = False): the realistic case, and the one
        # where a leak is invisible - it exists in both companies at once.
        cls.book = cls.env['product.template'].create({
            'name': "Livro Compartilhado",
            'barcode': "9789999999992",
            'type': 'consu',
            'is_storable': True,
        })
        cls.QTY_A, cls.QTY_B = 10.0, 3.0
        Quant = cls.env['stock.quant'].sudo()
        Quant._update_available_quantity(
            cls.book.product_variant_id, wh_a.lot_stock_id, cls.QTY_A)
        Quant._update_available_quantity(
            cls.book.product_variant_id, wh_b.lot_stock_id, cls.QTY_B)

        # Mapped in A only, so far.
        cls.book.with_context(
            allowed_company_ids=[company_a.id]).olist_produto_id = "111"

    def _capture_push(self):
        """Patch the network call and collect (idProduto, qty) per push."""
        sent = []

        def fake_update(token, id_produto, qty, **kw):
            sent.append({'token': token, 'id': str(id_produto), 'qty': qty})
            return ('{}', OK_RESP)

        return sent, patch.object(olist_client, 'update_estoque',
                                  side_effect=fake_update)

    # -- 1. on-hand is this company's, not the group's -----------------------
    def test_on_hand_is_read_in_the_account_company(self):
        sent, patcher = self._capture_push()
        # The dangerous context: a user (or a cron as root) with BOTH companies
        # enabled. This is where the union in with_company() used to sum them.
        book = self.book.with_context(
            allowed_company_ids=[self.company_a.id, self.company_b.id])
        with patcher:
            book._push_stock_to_olist(self.account_a)

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['qty'], self.QTY_A,
                         "on-hand must be company A's alone, not A+B")
        self.assertNotEqual(sent[0]['qty'], self.QTY_A + self.QTY_B)
        self.assertEqual(sent[0]['id'], "111")
        self.assertEqual(sent[0]['token'], "TOKEN-A")

    def test_bulk_push_reads_on_hand_in_its_own_company(self):
        # Same guarantee through the cron/bulk path, which is the one that runs
        # unattended and where nobody is watching the number.
        sent, patcher = self._capture_push()
        with patcher:
            self.account_a.with_context(
                allowed_company_ids=[self.company_a.id, self.company_b.id]
            )._push_all_stock(interactive=False)

        pushed = [s for s in sent if s['id'] == "111"]
        self.assertEqual(len(pushed), 1)
        self.assertEqual(pushed[0]['qty'], self.QTY_A)

    # -- 2. the Olist id belongs to the company ------------------------------
    def test_olist_id_is_per_company(self):
        in_a = self.book.with_context(allowed_company_ids=[self.company_a.id])
        in_b = self.book.with_context(allowed_company_ids=[self.company_b.id])
        self.assertEqual(in_a.olist_produto_id, "111")
        self.assertFalse(in_b.olist_produto_id,
                         "A's internal id must not be visible as B's")

    def test_push_in_other_company_resolves_its_own_id(self):
        sent, patcher = self._capture_push()
        with patcher, patch.object(olist_client, 'find_produto_id',
                                   return_value="222") as finder:
            self.book._push_stock_to_olist(self.account_b)

        finder.assert_called_once_with("TOKEN-B", "9789999999992")
        self.assertEqual(sent[0]['id'], "222")
        self.assertEqual(sent[0]['qty'], self.QTY_B)
        # each company remembers its own id, and A's is untouched
        in_a = self.book.with_context(allowed_company_ids=[self.company_a.id])
        in_b = self.book.with_context(allowed_company_ids=[self.company_b.id])
        self.assertEqual(in_a.olist_produto_id, "111")
        self.assertEqual(in_b.olist_produto_id, "222")

    def test_bulk_push_ignores_a_book_mapped_only_elsewhere(self):
        # The book is in Olist for A, not for B: B's sweep must not send it.
        sent, patcher = self._capture_push()
        with patcher:
            self.account_b._push_all_stock(interactive=False)

        self.assertFalse([s for s in sent if s['id'] == "111"],
                         "B pushed to A's Olist product id")

    def test_stock_log_is_per_company(self):
        _sent, patcher = self._capture_push()
        with patcher:
            self.book._push_stock_to_olist(self.account_a)

        in_a = self.book.with_context(allowed_company_ids=[self.company_a.id])
        in_b = self.book.with_context(allowed_company_ids=[self.company_b.id])
        self.assertIn("idProduto: 111", in_a.olist_stock_log)
        self.assertIn(self.company_a.name, in_a.olist_stock_log)
        self.assertFalse(in_b.olist_stock_log)

    # -- 3. no silent cross-company account ---------------------------------
    def test_no_account_here_never_falls_back_to_another_company(self):
        self.account_b.unlink()
        book_in_b = self.book.with_context(
            allowed_company_ids=[self.company_b.id])
        with self.assertRaises(UserError):
            book_in_b.action_push_stock_to_olist()

    def test_account_is_picked_by_current_company(self):
        self.assertEqual(
            self.book.with_context(
                allowed_company_ids=[self.company_b.id])._olist_account(),
            self.account_b)

    def test_two_active_accounts_for_one_company_are_refused(self):
        with self.assertRaises(ValidationError):
            self.env['olist.account'].create({
                'name': "Olist A bis",
                'company_id': self.company_a.id,
                'token': "TOKEN-A2", 'read_only': False,
            })

    # -- 4. a product owned by another company is never reported on ----------
    def test_product_of_another_company_is_refused_not_sent(self):
        owned = self.env['product.template'].create({
            'name': "Livro só da B",
            'barcode': "9789999999985",
            'type': 'consu',
            'is_storable': True,
            'company_id': self.company_b.id,
        })
        sent, patcher = self._capture_push()
        with patcher:
            status, _detail = owned._push_stock_to_olist(self.account_a)

        self.assertEqual(status, 'ERR')
        self.assertFalse(sent, "another company's product was sent anyway")
