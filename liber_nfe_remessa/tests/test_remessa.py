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
        """REM/ belongs to the fiscal document (consignment moved to COM/*)."""
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


@tagged('post_install', '-at_install')
class TestRemessaJournalAccount(TransactionCase):
    """One journal per kind, born carrying the operation's account.

    Discovered from staging on 21/08: a C000 note refused to post with "Conta
    necessária ausente na linha contábil". Odoo looks for the line's account
    in three places -- product, category, journal -- and in the house all
    three were empty: 6.137 products and 243 categories carry no account (the
    sales journals have always carried it), and the REM journal was created by
    code with none.

    The account is not invented here: it is read from the map the accountant
    already filled on the fiscal position ("revenue X becomes Y for this
    operation"). One journal per kind because that map differs by operation
    and a journal can only carry one account.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.product = cls.env['product.product'].create({
            'name': "Livro do Diário", 'type': 'consu', 'list_price': 30.0})
        cls.receita = cls.product.product_tmpl_id.get_product_accounts()['income']
        cls.destino = cls.env['account.account'].create({
            'name': "(+) Remessa (teste diário)", 'code': 'REMDST',
            'account_type': 'asset_current', 'company_ids': [(4, cls.company.id)]})
        cls.fpos = cls.env['account.fiscal.position'].create({
            'name': "Remessa com mapa (teste)", 'company_id': cls.company.id,
            'account_ids': [(0, 0, {'account_src_id': cls.receita.id,
                                    'account_dest_id': cls.destino.id})],
        })
        # A base de testes pode já ter um diário de remessa genérico de uma
        # rodada anterior, e ele venceria a busca antes de qualquer criação.
        # Tirar a marca (dentro da transação, desfeita no fim) é o que deixa
        # este teste medir o nascimento do diário, e não o histórico do banco.
        cls.env['account.journal'].search([
            ('company_id', '=', cls.company.id),
            ('is_remessa', '=', True),
        ]).is_remessa = False

    def test_o_diario_nasce_com_a_conta_do_mapa(self):
        journal = self.company._get_remessa_journal(
            kind='other', fiscal_position=self.fpos,
            name="Remessas (teste)", code='REMT')
        self.assertEqual(journal.default_account_id, self.destino,
                         "the journal must carry the operation's account")
        self.assertTrue(journal.is_remessa)
        # idempotente: pedir de novo devolve o mesmo, sem recriar
        self.assertEqual(
            self.company._get_remessa_journal(
                kind='other', fiscal_position=self.fpos), journal)

    def test_sem_mapa_de_receita_recusa_dizendo_o_que_falta(self):
        vazia = self.env['account.fiscal.position'].create({
            'name': "Remessa sem mapa (teste)", 'company_id': self.company.id})
        with self.assertRaises(UserError) as e:
            self.company._get_remessa_journal(
                kind='other', fiscal_position=vazia, code='REMT3')
        self.assertIn("revenue account", str(e.exception))

    def test_mapa_ambiguo_tambem_recusa(self):
        """Two revenue mappings and nobody can say which one rules."""
        segunda_receita = self.env['account.account'].create({
            'name': "Receita 2 (teste)", 'code': 'RECT2',
            'account_type': 'income', 'company_ids': [(4, self.company.id)]})
        self.env['account.fiscal.position.account'].create({
            'position_id': self.fpos.id,
            'account_src_id': segunda_receita.id,
            'account_dest_id': self.destino.id,
        })
        with self.assertRaises(UserError) as e:
            self.company._get_remessa_journal(
                kind='other', fiscal_position=self.fpos, code='REMT4')
        self.assertIn("exactly one", str(e.exception))


@tagged('post_install', '-at_install')
class TestRemessaCancelamento(TransactionCase):
    """Cancelar a nota não pode deixar meia contabilidade em pé.

    A nota e a baixa que a quita nascem do mesmo fato. O `unlink` já era
    guardado; o cancelamento, que é o caminho de verdade quando a NF-e é
    cancelada na SEFAZ, não era -- e a baixa ficava lançada sozinha.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': "Livraria do Cancelamento"})
        cls.product = cls.env['product.product'].create({
            'name': "Livro do Cancelamento", 'type': 'consu', 'list_price': 40.0})
        cls.mirror = cls.env['account.account'].create({
            'name': "(-) Remessa (teste cancelamento)", 'code': 'REMCAN',
            'account_type': 'asset_current', 'company_ids': [(4, cls.company.id)]})
        cls.fpos = cls.env['account.fiscal.position'].create({
            'name': "Remessa (teste cancelamento)", 'company_id': cls.company.id,
            'auto_invoice_paid': True,
            'auto_invoice_paid_account_id': cls.mirror.id})
        cls.journal = cls.company._get_remessa_journal()

    def _nota(self):
        nota = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'fiscal_position_id': self.fpos.id,
            'invoice_date': '2026-08-21',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id, 'quantity': 2,
                'price_unit': 20.0})],
        })
        nota.action_post()
        return nota

    def test_cancelar_a_nota_cancela_a_baixa(self):
        nota = self._nota()
        baixa = nota.remessa_settle_move_id
        self.assertTrue(baixa, "a baixa automática não foi criada")
        self.assertEqual(baixa.state, 'posted')
        nota.button_draft()
        nota.button_cancel()
        self.assertEqual(nota.state, 'cancel')
        self.assertEqual(baixa.state, 'cancel',
                         "a baixa ficou lançada sozinha: meia contabilidade")
