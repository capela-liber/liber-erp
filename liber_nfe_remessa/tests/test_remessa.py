# -*- coding: utf-8 -*-
"""The REM/ document: a note that never generates payment.

Each test guards one clause of the design agreed on 18/07: same account.move
engine, own journal; fiscal position carries the O15 auto-paid pair; Invoices
stays strictly for real sales.
"""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestNotaRemessa(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': "Livraria Teste"})
        cls.product = cls.env['product.product'].create({
            'name': "Livro Teste", 'type': 'consu', 'list_price': 50.0})
        cls.journal = cls.company._get_remessa_journal()
        cls.mirror = cls.env['account.account'].create({
            'name': "(-) Remessa de Mercadoria (teste)", 'code': 'REMTST',
            'account_type': 'expense', 'company_ids': [(4, cls.company.id)]})
        cls.fpos = cls.env['account.fiscal.position'].create({
            'name': "Remessa (teste)", 'company_id': cls.company.id,
            'auto_invoice_paid': True,
            'auto_invoice_paid_account_id': cls.mirror.id})

    def _note(self, fpos=None, journal=None):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': (journal or self.journal).id,
            'fiscal_position_id': (fpos if fpos is not None else self.fpos).id,
            'invoice_date': '2026-07-18',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id, 'quantity': 2,
                'price_unit': 25.0})],
        })

    def test_journal_created_on_first_use_with_rem_code(self):
        """REM/ belongs to the fiscal document (consignment moved to COM/)."""
        self.assertEqual(self.journal.code, 'REM')
        self.assertEqual(self.journal.type, 'sale')
        self.assertTrue(self.journal.is_remessa)
        # idempotent: asking again returns the same journal
        self.assertEqual(self.company._get_remessa_journal(), self.journal)

    def test_notes_number_contiguously(self):
        """REM/00001, 00002, 00003 -- the baixa books elsewhere."""
        first = self._note(); first.action_post()
        second = self._note(); second.action_post()
        n = lambda name: int(name.rsplit("/", 1)[-1])
        self.assertEqual(n(second.name), n(first.name) + 1,
                         "%s then %s: a hole in the fiscal sequence"
                         % (first.name, second.name))

    def test_note_posts_paid_with_nothing_owed(self):
        """The whole point: a real INV document, and no payment ever due."""
        note = self._note()
        note.action_post()
        self.assertEqual(note.state, 'posted')
        self.assertEqual(note.payment_state, 'paid')
        self.assertEqual(note.amount_residual, 0.0)
        self.assertTrue(note.name.startswith("REM/"),
                        "got %r, wanted the REM/ sequence" % note.name)
        # the settlement pair exists, is posted, and hits the mirror account
        settle = note.remessa_settle_move_id
        self.assertTrue(settle)
        self.assertEqual(settle.state, 'posted')
        self.assertIn(self.mirror, settle.line_ids.account_id)
        # the settlement must not eat REM/ numbers: a fiscal sequence with
        # holes reads as missing notes
        self.assertFalse(settle.name.startswith("REM/"),
                         "the baixa consumed a fiscal number: %s" % settle.name)
        # and the receivable is fully reconciled, not merely zeroed
        term = note.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable')
        self.assertTrue(all(term.mapped('reconciled')))

    def test_remessa_journal_without_auto_paid_refuses(self):
        """A remessa that asks for payment is a contradiction -- say so.

        The failure mode this guards: someone creates a note in the REM
        journal with a half-configured fiscal position, it posts quietly, and
        weeks later a bookseller gets dunned for books that were never sold.
        """
        naked = self.env['account.fiscal.position'].create({
            'name': "Sem auto-paid", 'company_id': self.company.id})
        with self.assertRaises(UserError):
            self._note(fpos=naked).action_post()
        # no fiscal position at all refuses too
        note = self._note()
        note.fiscal_position_id = False
        with self.assertRaises(UserError):
            note.action_post()

    def test_ordinary_invoices_are_untouched(self):
        """The hook must not leak: a normal sale still expects payment."""
        sale_journal = self.env['account.journal'].search(
            [('type', '=', 'sale'), ('is_remessa', '=', False),
             ('company_id', '=', self.company.id)], limit=1)
        inv = self._note(fpos=self.env['account.fiscal.position'],
                         journal=sale_journal)
        inv.fiscal_position_id = False
        inv.action_post()
        self.assertEqual(inv.state, 'posted')
        self.assertNotEqual(inv.payment_state, 'paid')
        self.assertEqual(inv.amount_residual, inv.amount_total)
        self.assertFalse(inv.remessa_settle_move_id)

    def test_invoices_menu_excludes_remessas(self):
        """Faturas fica só com venda de verdade."""
        domain = str(self.env.ref('account.action_move_out_invoice_type').domain)
        self.assertIn('is_remessa', domain)
        # and the Remessas menu shows only remessa documents
        action = self.env.ref('liber_nfe_remessa.action_nfe_remessa')
        self.assertIn('is_remessa', str(action.domain))

    def test_note_cannot_vanish_leaving_its_settlement(self):
        """The pair is one fiscal fact; half of it must not dangle."""
        note = self._note()
        note.action_post()
        note.button_draft()
        with self.assertRaises(UserError):
            note.unlink()
