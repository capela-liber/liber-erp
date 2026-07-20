# -*- coding: utf-8 -*-
"""Regression guards for the DESIGN, not just the code.

Every test here pins a decision that was argued for and agreed (see NOTES.md
and UX.md). If one goes red, the question is not "which line broke" but "did we
change our mind on purpose?".
"""
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBonus(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.press = cls.env.ref('liber_product_bonus.reason_press')
        cls.influencer = cls.env.ref('liber_product_bonus.reason_influencer')
        cls.author = cls.env.ref('liber_product_bonus.reason_author')

        cls.book = cls.env['product.product'].create({
            'name': "Test Title",
            'is_storable': True,
            'type': 'consu',
            'standard_price': 10.0,
            'list_price': 60.0,
        })
        # The history has to be on OTHER titles: 22 copies of the SAME book
        # would unselect him as a duplicate, and the volume guard would never
        # be exercised.
        cls.old_book = cls.env['product.product'].create({
            'name': "Previous Title",
            'is_storable': True,
            'type': 'consu',
            'standard_price': 8.0,
        })
        # With a phone, on purpose. Without one, stock_sms never asks to warn
        # the customer, button_validate sails through, and the chain test goes
        # green over a picking that would stall in real life -- which is exactly
        # what happened: the seed (whose people have phones) left every MOV in
        # 'assigned' while the test swore they were 'done'. A fixture that is
        # tidier than reality is a fixture that tests nothing.
        cls.ana = cls.env['res.partner'].create({
            'name': "Ana", 'street': "R. X, 1", 'zip': "01000-000", 'city': "SP",
            'phone': "+55 11 91234-5678"})
        cls.davi = cls.env['res.partner'].create({
            'name': "Davi", 'street': "R. Y, 2", 'zip': "02000-000", 'city': "RJ",
            'phone': "+55 21 98765-4321"})

    def _bonus(self, partner, reason=None, qty=1, product=None):
        return self.env['product.bonus'].create({
            'partner_id': partner.id,
            'reason_id': (reason or self.press).id,
            'line_ids': [(0, 0, {
                'product_id': (product or self.book).id, 'quantity': qty})],
        })

    def _print_run(self, qty):
        move = self.env['stock.move'].create({
            'product_id': self.book.id,
            'product_uom_qty': qty,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
        })
        move._action_confirm()
        move._action_assign()
        move.quantity = qty
        move.picked = True
        move._action_done()
        return move

    def _dispatch(self, partners=None):
        d = self.env['product.bonus.dispatch'].create({
            'product_id': self.book.id,
            'reason_id': self.press.id,
            'manual_partner_ids': [(6, 0, (partners or (self.ana | self.davi)).ids)],
        })
        d._onchange_source()
        return d

    def _expedite(self, picking):
        """What the warehouse does with a released BON/: pick, pack, ship.

        The module deliberately does NOT do this on send -- a comp copy has to
        be expedited. Tests/seed simulate the warehouse. skip_sms because Ana has
        a phone (real fixture), skip_backorder because we ship the whole line.
        """
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.with_context(
            skip_backorder=True, skip_sms=True).button_validate()

    def _history(self, partner, n, outcome, reason=None):
        """n closed bonus copies of a PREVIOUS title."""
        for _i in range(n):
            b = self._bonus(partner, reason=reason or self.influencer,
                            product=self.old_book)
            b.action_approve()
            b.action_send()
            b.action_arrived()
            b._set_outcome(outcome)

    # --- sequence ---------------------------------------------------------
    def test_sequences_split_dispatch_from_ficha(self):
        """His correction: BO is the DISPATCHER, B000 is the ficha.

        Two letters are for disparadores (D4), so the dispatch is BO/2026/00001
        and follows the house's CR/ CO/ CP/. The ficha is not a disparador: it
        is the package with an address and a nota, and it is B00231.
        """
        b = self._bonus(self.ana)
        self.assertTrue(b.name.startswith('B'), b.name)
        self.assertFalse(b.name.startswith('BO/'),
                         "the ficha must not wear the dispatcher's prefix")
        d = self._dispatch()
        self.assertTrue(d.name.startswith('BO/'), d.name)

    # --- a lista acompanha o envio ----------------------------------------
    def test_send_advances_list_last_shipment(self):
        """"Último envio" existe para responder "quais listas esfriaram" -- um
        envio de verdade TEM de movê-lo. O bug: só o importador escrevia o
        campo, então ele congelava no valor do Odoo 15 e mentia a partir do
        primeiro BO. E é só para frente: nada aqui esfria uma lista."""
        lst = self.env['product.bonus.list'].create({
            'name': "Lista com história",
            'last_shipment_on': date(2024, 1, 1),
        })
        b = self._bonus(self.ana)
        b.list_id = lst
        b.action_approve()
        b.action_send()
        self.assertEqual(lst.last_shipment_on, b.sent_date,
                         "o envio não empurrou a data para a lista")

    # --- cost -------------------------------------------------------------
    def test_cost_freezes_on_send(self):
        """The cost must not be live: a reprint would rewrite 2024's history."""
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        self.assertEqual(b.line_ids.unit_cost, 10.0)
        self.book.standard_price = 99.0
        b.invalidate_recordset()
        self.assertEqual(
            b.line_ids.unit_cost, 10.0,
            "cost must stay frozen at send time, not follow the product")

    def test_cost_is_cost_not_cover_price(self):
        """Two numbers in the same document; the analytic gets COST.

        Using the cover price would inflate a bonus 3-6x and make paid media
        look cheap -- inverting the comparison the module exists to make.
        """
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        self.assertEqual(b.total_cost, 10.0)
        self.assertNotEqual(b.total_cost, self.book.list_price)

    # --- the quota: the net, not the method -------------------------------
    def test_quota_blocks_and_explains(self):
        self._print_run(1000)
        self.env['product.bonus.quota'].create({
            'product_id': self.book.id, 'bucket': 'marketing', 'pct_allowed': 0.1})
        b = self._bonus(self.ana, qty=5)
        b.action_approve()
        with self.assertRaises(UserError) as e:
            b.action_send()
        msg = str(e.exception)
        # A block that only says "no" is the punishment we are avoiding.
        self.assertIn("Marketing", msg)
        self.assertIn("release", msg, "the block must say who can release it")

    def test_quota_override_is_recorded(self):
        """The override is information, not an exception."""
        self._print_run(1000)
        self.env['product.bonus.quota'].create({
            'product_id': self.book.id, 'bucket': 'marketing', 'pct_allowed': 0.0})
        b = self._bonus(self.ana)
        b.action_approve()
        b.with_context(bonus_force_quota=True).action_send()
        self.assertEqual(b.state, 'sent')
        self.assertTrue(
            any('Quota override' in (m.body or '') for m in b.message_ids),
            "a released quota must leave a trace")

    def test_no_print_run_means_no_block(self):
        """A meta of an inexistent print run is UNDEFINED, not zero.

        The launch being planned today has not entered stock yet. Blocking its
        press mailing because 5% of 0 is 0 would fail towards "não mandou
        livro" -- which is the half of the problem everybody forgets.
        """
        self.assertEqual(self.book._bonus_print_run(), 0)
        d = self._triage()
        self.assertTrue(d.fits, "no print run must not block")
        d.action_check()
        d.action_approve()
        self.assertEqual(len(d.bonus_ids), 2)
        d.bonus_ids.action_send()
        self.assertTrue(all(b.state == 'sent' for b in d.bonus_ids))

    def test_quota_is_a_percentage_of_the_print_run(self):
        """"Se fiz 3000 e quero doar x%": the input is a percentage; the copies
        are the consequence."""
        self._print_run(3000)
        q = self.env['product.bonus.quota'].create({
            'product_id': self.book.id, 'bucket': 'marketing', 'pct_allowed': 3.0})
        self.assertEqual(q.print_run, 3000)
        self.assertEqual(q.qty_allowed, 90)
        # a reprint widens the allowance on its own
        self._print_run(2000)
        q.invalidate_recordset()
        self.assertEqual(q.print_run, 5000)
        self.assertEqual(q.qty_allowed, 150)

    def test_the_percentage_is_reachable_from_the_bonus_menu(self):
        """He asked "onde eu coloco a porcentagem da tiragem?" twice.

        The first time it did not exist. The second time it existed, rendered
        correctly, and lived in the global Definições -- which is where the Odoo
        convention puts it and NOT where somebody standing inside the
        Bonificações app will ever look. A setting nobody can find is a setting
        that does not exist, so the path itself is worth a regression test.
        """
        menu = self.env.ref('liber_product_bonus.menu_bonus_config_settings')
        path = []
        node = menu
        while node:
            path.insert(0, node.name)
            node = node.parent_id
        # Rotulava-se "Meta de doação (%)" e a página tem metas, acompanhamento
        # E configuração fiscal — ele foi procurar a fiscal e não abriu a porta.
        self.assertEqual(path, ["Bonificações", "Configuração", "Definições"])
        self.assertEqual(menu.action.res_model, 'res.config.settings')
        self.assertIn('liber_product_bonus', menu.action.context)

        # and the door actually opens onto the three percentages
        from lxml import etree
        arch = etree.fromstring(
            self.env['res.config.settings'].get_view(view_type='form')['arch'].encode())
        app = [a for a in arch.iter('app') if a.get('name') == 'liber_product_bonus']
        self.assertTrue(app, "no Bonificações block in Definições")
        fields = {f.get('name') for f in app[0].iter('field')}
        for f in ('bonus_pct_editorial', 'bonus_pct_marketing', 'bonus_pct_commercial'):
            self.assertIn(f, fields)

    def test_house_default_covers_titles_with_no_quota_row(self):
        """He could not find where to set the percentage -- because it was only
        per title. The house default is the way in; a row is the exception."""
        self._print_run(1000)
        self.env['ir.config_parameter'].sudo().set_param(
            'product_bonus.pct_marketing', '4.0')
        f = self.env['product.bonus.quota']._figures_for(self.book, 'marketing')
        self.assertEqual(f['pct'], 4.0)
        self.assertEqual(f['allowed'], 40, "4% of 1000, with no quota row at all")

    def test_print_run_reads_entries_not_balance(self):
        """Stock is a moving number; a print run of 3000 stays 3000."""
        move = self.env['stock.move'].create({
            'product_id': self.book.id,
            'product_uom_qty': 3000,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
        })
        move._action_confirm()
        move._action_assign()
        move.quantity = 3000
        move.picked = True
        move._action_done()
        self.assertEqual(self.book._bonus_print_run(), 3000)

        # sell half: the balance drops, the print run does NOT
        out = self.env['stock.move'].create({
            'product_id': self.book.id,
            'product_uom_qty': 1500,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })
        out._action_confirm()
        out._action_assign()
        out.quantity = 1500
        out.picked = True
        out._action_done()
        self.assertEqual(
            self.book._bonus_print_run(), 3000,
            "the print run must read entries, never the balance on hand")

    # --- approval ---------------------------------------------------------
    def test_author_copies_skip_approval(self):
        """The contract approved them when it was signed. Asking again is
        theatre."""
        self.assertFalse(self.author.requires_approval)
        b = self._bonus(self.ana, reason=self.author)
        b.action_send()
        self.assertEqual(b.state, 'sent')

    def test_press_needs_approval(self):
        b = self._bonus(self.ana)
        with self.assertRaises(UserError):
            b.action_send()

    # --- the return -------------------------------------------------------
    def test_waiting_is_not_silence(self):
        """Someone who got the book yesterday cannot be a failure today."""
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        self.assertTrue(b.is_waiting)
        self.assertFalse(b.outcome)
        # context_today, não date.today(): o módulo carimba no fuso do usuário
        # e o container roda UTC -- date.today() vira o dia SEGUINTE depois das
        # 21h de Brasília, e o teste quebrava só à noite.
        self.assertEqual(b.deadline,
                         fields.Date.context_today(b) + timedelta(days=120))

    def test_window_is_per_reason(self):
        """A single window would age the newspaper critic into 'silence' and
        the house would stop sending books to the Estadao."""
        self.assertGreater(self.press.return_window_days,
                           self.influencer.return_window_days,
                           "press is slow, influencers are fast -- "
                           "one window cannot serve both")

    def test_lost_does_not_count_against_the_recipient(self):
        """The post office lost it. Punishing the journalist is backwards."""
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        b.action_lost()
        self.assertEqual(b.state, 'lost')
        self.ana.invalidate_recordset()
        self.assertEqual(self.ana.bonus_outcome_rate, "—",
                         "a lost book is not a bad return")
        # and it offers a resend
        res = b.action_resend()
        new = self.env['product.bonus'].browse(res['res_id'])
        self.assertEqual(new.partner_id, self.ana)

    def test_rate_is_raw_never_a_score(self):
        """'5 de 7' is a fact. '68' is a guess with decimal places."""
        for outcome in ('good', 'great', 'good', 'silence', 'weak'):
            b = self._bonus(self.ana, product=self.old_book)
            b.action_approve()
            b.action_send()
            b.action_arrived()
            b._set_outcome(outcome)
        self.ana.invalidate_recordset()
        self.assertEqual(self.ana.bonus_outcome_rate, "3 de 5")

    def test_cold_start_is_a_dash_not_a_zero(self):
        """If no history looked bad, nobody new would ever get a first book --
        and without a first book there is never any history."""
        fresh = self.env['res.partner'].create({'name': "Newcomer"})
        self.assertEqual(fresh.bonus_outcome_rate, "—")
        self.assertNotEqual(fresh.bonus_outcome_rate, "0 de 0")

    # --- the triage: the heart --------------------------------------------
    def _triage(self):
        return self._dispatch()

    def test_triage_columns_are_populated(self):
        """The columns ARE the decision. A triage screen showing everyone as
        '0' is worse than none: it looks like an answer."""
        self._history(self.davi, 22, 'silence')
        wiz = self._triage()
        davi = wiz.line_ids.filtered(lambda l: l.partner_id == self.davi)
        self.assertEqual(davi.received_count, 22)
        self.assertEqual(davi.outcome_rate, "0 de 22")

    def test_triage_never_blocks_on_volume(self):
        """The Davi Reis case, and the whole design in one row.

        22 books and zero coverage: the system shows both numbers and lets the
        human decide. Maybe he is the most influential critic in the country;
        maybe he is somebody's friend. The software does not know which -- the
        person does.
        """
        self._history(self.davi, 22, 'silence')
        wiz = self._triage()
        davi = wiz.line_ids.filtered(lambda l: l.partner_id == self.davi)
        self.assertFalse(davi.has_title, "fixture: the new title must be new")
        self.assertEqual(davi.outcome_rate, "0 de 22")
        self.assertTrue(
            davi.selected,
            "volume must never auto-unselect: show the number, do not decide")

    def test_triage_unselects_only_duplicates(self):
        """A duplicate starts unticked; everyone else starts ticked.

        There is no "do not send" flag to unselect on -- that is an editorial
        call, not bonus bookkeeping (removed on his instruction).
        """
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        wiz = self._triage()
        ana = wiz.line_ids.filtered(lambda l: l.partner_id == self.ana)
        davi = wiz.line_ids.filtered(lambda l: l.partner_id == self.davi)
        self.assertTrue(ana.has_title)
        self.assertFalse(ana.selected, "already has the title -> unticked")
        self.assertTrue(davi.selected, "no reason to unselect -> ticked")

    def test_counter_is_live(self):
        """The brake is a budget, not a permission: it has to move WHILE you
        choose, not appear when you save."""
        self._print_run(3000)
        self.env['product.bonus.quota'].create({
            'product_id': self.book.id, 'bucket': 'marketing', 'pct_allowed': 3.0})
        wiz = self._triage()
        self.assertEqual(wiz.quota_allowed, 90, "3% of 3000")
        n = wiz.selected_count
        wiz.line_ids[0].selected = False
        wiz.invalidate_recordset()
        self.assertEqual(wiz.selected_count, n - 1)

    def test_dispatch_generates_one_ficha_per_person(self):
        """D7, and his correction: one decision, N shipments.

        Each person has their own address, their own package at the warehouse
        and their own nota fiscal -- so the BO fans out into fichas.
        """
        d = self._triage()
        d.action_check()
        d.action_approve()
        self.assertEqual(len(d.bonus_ids), 2)
        self.assertEqual(len(set(d.bonus_ids.mapped('partner_id.id'))), 2)
        self.assertTrue(all(b.dispatch_id == d for b in d.bonus_ids),
                        "every ficha must point back to the dispatch that ordered it")

    def test_dispatch_approves_once_not_per_person(self):
        """Approval hangs off the dispatch: the list's owner says yes once, not
        47 times."""
        d = self._triage()
        d.action_check()
        d.action_approve()
        self.assertEqual(d.state, 'approved')
        self.assertTrue(all(b.state == 'approved' for b in d.bonus_ids))

    def test_dispatch_is_the_media_comparison_unit(self):
        """"40 livros, R$ 480" is the sentence that argues with paid media. A
        single ficha cannot make it."""
        d = self._triage()
        d.action_check()
        d.action_approve()
        self.assertEqual(d.bonus_count, 2)
        self.assertEqual(d.total_cost, 20.0)

    def test_triage_skips_people_without_an_address(self):
        """Better to know now than at the post office."""
        self.davi.write({'zip': False, 'street': False, 'city': False})
        d = self._triage()
        davi = d.line_ids.filtered(lambda l: l.partner_id == self.davi)
        self.assertFalse(davi.address_ok)
        d.action_check()
        d.action_approve()
        self.assertNotIn(self.davi, d.bonus_ids.mapped('partner_id'))

    def test_dispatch_shows_its_campaign_evaluation(self):
        """"Pra que mandar se o fulano fez uma campanha meia boca."

        After a BO ships, its own return has to be visible on the BO, not dug
        out one ficha at a time: 47 books, R$ 580, and this is what came back.
        """
        d = self._dispatch()
        d.action_check()
        d.action_approve()
        d.action_send_all()
        for b, outcome in zip(d.bonus_ids, ('great', 'silence')):
            b.action_arrived()
            b._set_outcome(outcome)
        d.invalidate_recordset()
        self.assertEqual(d.outcome_rate, "1 de 2")
        self.assertIn("arrasou", d.outcome_summary)
        self.assertIn("silêncio", d.outcome_summary)

    def test_reporting_dimensions_are_stored_and_crossable(self):
        """"Como uso os resultados na hora de filtrar e ver relatórios."

        A pivot needs stored dimensions. Investimento (bucket), tipo de parceiro,
        resultado (outcome), título and cost/quantity all have to survive a
        read_group -- if any is a non-stored compute, the pivot cannot slice on
        it. This crosses Investimento × Resultado, the report's spine.
        """
        self.ana.bonus_partner_type = 'journalist'
        self.davi.bonus_partner_type = 'influencer'
        d = self._dispatch()
        d.action_check()
        d.action_approve()
        d.action_send_all()
        for b, outcome in zip(d.bonus_ids, ('great', 'silence')):
            b.action_arrived()
            b._set_outcome(outcome)

        Bonus = self.env['product.bonus']
        # every reporting dimension is stored (read_group would raise otherwise)
        for dim in ('bucket', 'partner_type', 'outcome', 'product_id'):
            self.assertTrue(Bonus._fields[dim].store,
                            "%s must be stored to slice a pivot" % dim)
        # and it actually groups: Investimento × Resultado
        groups = Bonus._read_group(
            [('id', 'in', d.bonus_ids.ids)],
            ['bucket', 'outcome'], ['quantity:sum', 'total_cost:sum'])
        self.assertTrue(groups)
        # partner type carried from the contact
        self.assertEqual(
            d.bonus_ids.filtered(lambda b: b.partner_id == self.ana).partner_type,
            'journalist')

    def test_note_carries_the_configured_fiscal_position(self):
        """The sibling defect the dumb-field test cannot see.

        bonus_fiscal_position_id IS read by code, so test_no_dumb_config_fields
        passes -- and yet every note in the demo carried an empty fiscal
        position, because nothing ever SET the config. "Read" is not "arrives".
        A field that is consumed but never populated fails silently, and on a
        nota a silent wrong fiscal position is a fiscal error, not an annoyance.
        """
        fpos, _mirror = self._wire_fiscal()
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        b.action_generate_note()
        self.assertTrue(b.note_move_id, "sem nota não há o que conferir")
        self.assertEqual(
            b.note_move_id.fiscal_position_id, fpos,
            "a posição fiscal configurada não chegou na nota")

    def test_note_button_answers_even_without_a_note(self):
        """"Não achei o link entre B000 e nota" -- porque ele sumia."""
        self.assertEqual(self._bonus(self.ana).note_label, "A emitir")

    # --- o score do parceiro: nível e direção -----------------------------
    def _pin_rating(self, test_size=3, half_life=12, **points):
        """Fixa os parâmetros do score para este teste.

        Sem isto os testes liam a configuração REAL da base -- e quebraram no
        dia em que ele mexeu no limiar do teste na tela, que é exatamente o que
        a configuração existe para permitir. Teste que proíbe o usuário de
        configurar não está testando, está travando.
        """
        param = self.env['ir.config_parameter'].sudo()
        defaults = {'silence': 0.0, 'weak': 5.0, 'good': 8.0, 'great': 13.0}
        defaults.update(points)
        for key, value in defaults.items():
            param.set_param('product_bonus.points_%s' % key, str(value))
        param.set_param('product_bonus.rating_test_size', str(test_size))
        param.set_param('product_bonus.rating_half_life', str(half_life))

    def _judged(self, partner, outcomes, months_ago=0):
        """Fichas avaliadas, com idade controlada."""
        made = self.env['product.bonus']
        for i, outcome in enumerate(outcomes):
            b = self._bonus(partner, product=self.old_book)
            b.action_approve()
            b.action_send()
            b.action_arrived()
            b._set_outcome(outcome)
            # data manda na recência e na ordem da tendência
            b.date = date.today() - timedelta(days=30 * (months_ago + len(outcomes) - i))
            made |= b
        partner.invalidate_recordset()
        return made

    def test_the_influencer_who_burned_out(self):
        """O caso dele, inteiro.

        "Mandei para um mesmo influencer 10 livros. Ele divulgou dois bem e os
        outros 5 meia boca, e depois silenciou."

        A média crua dá 5,1 e lê como "meia-boca constante" -- e é mentira: a
        pessoa começou ótima e morreu. A nota tem que cair E a seta tem que
        apontar para baixo, senão o próximo envio é cego.
        """
        self._pin_rating()
        self._judged(self.ana, ['great', 'great'] + ['weak'] * 5
                     + ['silence'] * 3)
        self.assertEqual(self.ana.bonus_rating_trend, '↓',
                         "a trajetória caiu e a seta não viu")
        self.assertEqual(self.ana.bonus_rating_band, 'fading')
        # e a nota fica ABAIXO da média crua (5,1), porque o recente pesa mais
        self.assertLess(self.ana.bonus_rating, 5.1,
                        "a recência não puxou a nota para baixo")

    def test_one_book_one_hit_is_not_a_perfect_score(self):
        """"1 de 1" parecia a melhor linha da tela e não informa nada.

        Uma amostra de 1 não é avaliação, é sorte. Enquanto está em teste não
        existe nota -- porque nenhum número seria honesto.
        """
        self._pin_rating()
        self._judged(self.davi, ['great'])
        self.assertIsNotNone(self.davi.bonus_rating_label)
        # Só o ícone e a fração -- sem palavra, por decisão dele.
        self.assertIn("⚗", self.davi.bonus_rating_label)
        self.assertIn("1/3", self.davi.bonus_rating_label)
        self.assertIn("fa-flask", self.davi.bonus_rating_html)
        # na tela, só o ícone: o "1 de 3" vive no title
        self.assertNotIn("1/3", self.davi.bonus_rating_html)
        self.assertIn("1 de 3", self.davi.bonus_rating_html)
        self.assertEqual(self.davi.bonus_rating_band, 'testing')
        self.assertEqual(self.davi.bonus_rating, 0.0,
                         "em teste não pode carregar nota nenhuma")

    def test_zero_of_many_is_the_loudest_line(self):
        """"0 de 22": muitos livros, nada de volta -- o desengajado de verdade."""
        self._pin_rating()
        self._judged(self.davi, ['silence'] * 8)
        self.assertEqual(self.davi.bonus_rating_band, 'cold')
        self.assertLess(self.davi.bonus_rating, 3.0)

    def test_never_judged_is_an_invitation(self):
        """Sem histórico é 'novo', nunca nota zero.

        Se o desconhecido pontuasse zero, ele afundaria junto com o que recebeu
        22 livros e nunca retornou -- e a casa pararia de descobrir gente.
        """
        self._pin_rating()
        fresh = self.env['res.partner'].create({'name': "Desconhecida"})
        self.assertEqual(fresh.bonus_rating_band, 'new')
        self.assertEqual(fresh.bonus_rating_label, "⚘",
                         "o convite é o ícone sozinho, sem palavra")
        # e na tela, o ícone dele (FA 4.7, o que o Odoo empacota) com o
        # tooltip por célula
        self.assertIn("fa-pagelines", fresh.bonus_rating_html)
        self.assertIn("title=", fresh.bonus_rating_html,
                      "sem title não há explicação no foco")
        self.assertEqual(fresh.bonus_rating, 0.0)

    def test_volume_alone_does_not_raise_the_rating(self):
        """O defeito que ELE apontou: soma premiaria quem recebeu mais.

        Dois parceiros com a mesma proporção de resultados e volumes muito
        diferentes têm que ficar próximos -- o volume dá CONFIANÇA (menos
        encolhimento), não nota.
        """
        self._pin_rating()
        self._judged(self.ana, ['good', 'good', 'good'])
        self._judged(self.davi, ['good'] * 12)
        self.assertAlmostEqual(self.ana.bonus_rating, self.davi.bonus_rating,
                               delta=2.0,
                               msg="volume virou nota: %.1f vs %.1f"
                                   % (self.ana.bonus_rating, self.davi.bonus_rating))

    def test_the_house_can_recalibrate_everything(self):
        """"parametriza em definições essas coisas" -- todas elas."""
        param = self.env['ir.config_parameter'].sudo()
        self._pin_rating()
        self._judged(self.ana, ['weak'] * 4)
        before = self.ana.bonus_rating
        param.set_param('product_bonus.points_weak', '11')
        # O score é armazenado (para ser ordenável), então mudar a régua exige
        # recalcular -- é o que Definições faz ao salvar. Sem isto o campo
        # ficaria com o valor velho, que é o modo de falha que o cron e o
        # set_values existem para evitar.
        self.env['res.partner']._cron_recompute_bonus_rating()
        self.assertGreater(self.ana.bonus_rating, before,
                           "mudar os pontos não mudou a nota")
        # o limiar do teste também
        param.set_param('product_bonus.rating_test_size', '9')
        self.env['res.partner']._cron_recompute_bonus_rating()
        self.assertIn("⚗", self.ana.bonus_rating_label,
                      "subir o limiar não devolveu a pessoa para o teste")

    def test_the_rating_travels_to_lists_and_reports(self):
        """"vamos colocar essa informação nas Listas também? e em algum relatório?"

        Na lista: a mesma nota, onde o público é curado. No relatório: a
        situação CONGELADA no envio -- ver a de hoje seria ler o passado com a
        informação que só existe por causa dele.
        """
        self._pin_rating()
        self._judged(self.ana, ['silence'] * 5)
        lst = self.env['product.bonus.list'].create({'name': "Lista teste nota"})
        member = self.env['product.bonus.list.member'].create({
            'list_id': lst.id, 'partner_id': self.ana.id})
        self.assertEqual(member.rating_label, self.ana.bonus_rating_label)
        self.assertEqual(member.rating_band, 'cold')

        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        self.assertEqual(b.partner_band_at_send, 'cold',
                         "a ficha não congelou a situação do envio")
        # e congelada quer dizer congelada: avaliações posteriores não a mexem
        b.action_arrived()
        b._set_outcome('great')
        self._judged(self.ana, ['great'] * 6)
        b.invalidate_recordset()
        self.assertEqual(b.partner_band_at_send, 'cold',
                         "o passado foi reescrito pelo que veio depois")

    def test_list_column_labels_fit(self):
        """"Conferir se os labels estão cabendo nas colunas."

        "Janela de retorno (dias)" e "Consome exemplares do contrato" saíam
        cortados com reticências. Reticências não são um detalhe estético:
        quem chega na tela não sabe o que a coluna mede, e a lista de Motivos
        é onde se decide o que exige aprovação. Rótulo curto na lista, nome
        inteiro no formulário e na dica.
        """
        from lxml import etree
        # Duas armadilhas que a primeira versão deste teste não via:
        #  1. coluna NUMÉRICA (e booleana) encolhe até o conteúdo -- um rótulo
        #     de 12 caracteres sobre um "67" ou um checkbox trunca de qualquer
        #     jeito, mesmo passando num limite geral;
        #  2. a lista EMBUTIDA num formulário (a seleção do BO, justamente a
        #     tela de que ele reclamou) não é a lista padrão do modelo, e
        #     passava inteira despercebida.
        NARROW = ('integer', 'float', 'monetary', 'boolean')

        def check(model, arch, where):
            for node in arch.iter('field'):
                if node.get('widget') == 'handle':
                    continue
                field = self.env[model]._fields.get(node.get('name'))
                label = node.get('string') or (field and field.string) or ''
                limit = 10 if (field and field.type in NARROW) else 22
                self.assertLessEqual(
                    len(label), limit,
                    "%s (%s): a coluna %r tem %d caracteres (limite %d aqui) "
                    "e vai sair cortada" % (model, where, label, len(label), limit))

        env_br = self.env(context=dict(self.env.context, lang='pt_BR'))
        for model in ('product.bonus.reason', 'product.bonus',
                      'product.bonus.list', 'product.bonus.dispatch',
                      'product.bonus.list.member'):
            arch = etree.fromstring(env_br[model].get_view(view_type='list')['arch'])
            check(model, arch, 'lista')

            # e as listas embutidas no formulário deste modelo
            form = etree.fromstring(env_br[model].get_view(view_type='form')['arch'])
            for node in form.iter('field'):
                inner = node.find('list')
                if inner is None:
                    continue
                sub = env_br[model]._fields.get(node.get('name'))
                if not (sub and sub.comodel_name):
                    continue
                check(sub.comodel_name, inner, 'embutida em %s' % model)

    # --- importação de planilha ------------------------------------------
    def _new_list(self, name):
        """O que o "Criar «Nome»" do dropdown faz na tela."""
        return self.env['product.bonus.list'].create({'name': name})

    def _sheet(self, rows, header=None):
        """Uma planilha CSV em base64, como sai do navegador.

        Os e-mails destes testes usam um domínio próprio (.invalid, reservado
        pela RFC 2606) porque a primeira versão colidiu com o seed: havia uma
        "Rita Sales" com rita@exemplo.com, a linha CASOU -- comportamento
        correto -- e o teste acusou o código. Teste que depende do dado que por
        acaso está na base mede o acaso.
        """
        import base64
        import io
        head = header or "Nome;E-mail;Telefone;Tipo;Endereço;Cidade;CEP;Observação"
        body = "\n".join([head] + [";".join(r) for r in rows])
        return base64.b64encode(body.encode('utf-8'))

    def test_import_matches_instead_of_duplicating(self):
        """O buraco mais feio: importar não pode duplicar quem já existe.

        Uma lista de imprensa é quase toda gente que já está na base. Um import
        ingênuo cria um segundo "Ana Prado" e leva junto o histórico, o Score e
        a checagem de quem já recebeu o título -- todos passam a olhar para o
        cadastro errado.
        """
        self.ana.email = "ana@teste-import.invalid"
        wizard = self.env['product.bonus.list.import'].create({
            'filename': 'lista.csv',
            'list_id': self._new_list("Imprensa importada").id,
            'file': self._sheet([
                # mesma pessoa, e-mail com caixa e espaço diferentes
                ["Ana P.", " ANA@Teste-Import.INVALID ", "", "jornalista", "", "", "", ""],
                ["Novato Silva", "novato@teste-import.invalid", "+55 11 90000-0000",
                 "influencer", "R. A, 1", "SP", "01000-000", "booktuber"],
            ]),
        })
        wizard.action_import()
        lst = self.env['product.bonus.list'].search(
            [('name', '=', "Imprensa importada")])
        self.assertEqual(len(lst.member_ids), 2)
        partners = lst.member_ids.mapped('partner_id')
        self.assertIn(self.ana, partners,
                      "não casou pelo e-mail e criou uma Ana duplicada")
        self.assertEqual(
            len(self.env['res.partner'].search([('name', '=', "Ana")])), 1,
            "duplicou o contato existente")
        novato = partners.filtered(lambda p: p.name == "Novato Silva")
        self.assertEqual(novato.bonus_partner_type, 'influencer',
                         "a coluna Tipo não virou o tipo de parceiro")
        self.assertEqual(novato.city, "SP")

    def test_import_preview_does_not_write(self):
        """A prévia é para decidir -- se ela gravar, não é prévia."""
        before = self.env['res.partner'].search_count([])
        lst = self._new_list("Só conferindo")
        wizard = self.env['product.bonus.list.import'].create({
            'filename': 'lista.csv', 'list_id': lst.id,
            'file': self._sheet([["Fulano Novo", "fulano@teste-import.invalid", "", "", "", "", "", ""]]),
        })
        wizard.action_preview()
        self.assertEqual(wizard.state, 'preview')
        self.assertIn("1 contatos novos", wizard.preview_html)
        self.assertEqual(self.env['res.partner'].search_count([]), before,
                         "a prévia criou contato")
        self.assertFalse(lst.member_ids, "a prévia já ligou gente à lista")

    def test_import_survives_a_real_spreadsheet(self):
        """Planilha de verdade: outra ordem, outros títulos, linhas repetidas.

        A planilha que chega do assessor não tem os títulos do modelo nem a
        ordem dele -- e tem a mesma pessoa duas vezes, porque passou por três
        mãos. Se o importador exigir o formato exato, ninguém usa.
        """
        wizard = self.env['product.bonus.list.import'].create({
            'filename': 'assessoria.csv', 'list_id': self._new_list("Assessoria").id,
            'file': self._sheet(
                header="Celular;Contato;Veículo;email",
                rows=[
                    ["11 90000-1111", "Rita Campos Teste", "Blog X", "rita.campos@teste-import.invalid"],
                    ["11 90000-2222", "Rita Campos Teste", "Blog X", "RITA.Campos@teste-import.invalid"],
                    ["", "Sem email", "", ""],
                ]),
        })
        wizard.action_preview()
        self.assertIn("repetidos dentro da planilha", wizard.preview_html)
        wizard.action_import()
        lst = self.env['product.bonus.list'].search([('name', '=', "Assessoria")])
        names = lst.member_ids.mapped('partner_id.name')
        self.assertEqual(names.count("Rita Campos Teste"), 1,
                         "a repetição dentro do arquivo virou dois cadastros")
        self.assertEqual(
            self.env['res.partner'].search_count([('name', '=', "Rita Campos Teste")]), 1)
        self.assertIn("Sem email", names, "a linha sem e-mail sumiu")

    def test_import_can_refuse_to_create(self):
        """Conferir uma planilha sem deixá-la entrar na base."""
        wizard = self.env['product.bonus.list.import'].create({
            'filename': 'lista.csv', 'list_id': self._new_list("Só os conhecidos").id,
            'create_missing': False,
            'file': self._sheet([["Desconhecido Total", "quem@teste-import.invalid",
                                  "", "", "", "", "", ""]]),
        })
        wizard.action_preview()
        self.assertIn("não serão criados", wizard.preview_html)
        wizard.action_import()
        self.assertFalse(self.env['res.partner'].search(
            [('name', '=', "Desconhecido Total")]), "criou mesmo com a trava")

    def test_the_template_can_be_imported_back(self):
        """A prova de verdade do modelo: gerar, subir e ler de volta.

        Comparar constantes provaria pouco -- o que importa é o arquivo real
        atravessar o importador real. Se um dia o gerador mudar uma coluna, ou
        o leitor de xlsx quebrar, isto cai aqui e não na mão de quem tentou
        importar 200 jornalistas numa sexta à noite.
        """
        # O modelo vem anexado ao próprio assistente, pronto para baixar --
        # é um default, então basta abrir a tela.
        blank = self.env['product.bonus.list.import'].new({})
        self.assertTrue(blank.template_file, "o modelo saiu vazio")
        self.assertTrue(blank.template_filename.endswith('.xlsx'))

        back = self.env['product.bonus.list.import'].create({
            'filename': 'modelo-lista-vip.xlsx',
            'list_id': self._new_list("Veio do modelo").id,
            'file': blank.template_file,
        })
        rows = back._read_rows()
        self.assertEqual(len(rows), 4, "as linhas de exemplo do modelo sumiram")
        from odoo.addons.liber_product_bonus.wizard.bonus_list_import import COLUMNS
        for field, _label in COLUMNS:
            self.assertTrue(
                rows[0].get(field),
                "a coluna %r do modelo não foi reconhecida na volta" % field)
        back.action_import()
        # O modelo traz a coluna Lista preenchida, então ele demonstra o caso
        # multi-lista: as linhas vão para as listas que elas nomeiam, e a
        # mesma pessoa aparece em duas sem virar dois cadastros.
        listas = self.env['product.bonus.list'].search(
            [('name', 'in', ("Imprensa literária", "Lançamento Transposição"))])
        self.assertEqual(len(listas), 2, "as listas do modelo não foram criadas")
        # Pelo E-MAIL, não pelo nome: a base do demo já tem uma "Ana Prado"
        # com outro endereço, e ela não é a do modelo. Testar por nome mediria
        # o seed, não o importador.
        ana = self.env['res.partner'].search(
            [('email_normalized', '=', "ana.prado@exemplo.com.br")])
        self.assertEqual(
            len(ana), 1,
            "a mesma pessoa em duas listas virou dois cadastros")
        self.assertEqual(
            len(listas.member_ids.filtered(lambda m: m.partner_id == ana)), 2,
            "Ana devia estar nas duas listas do modelo")
        self.assertEqual(ana.bonus_partner_type, 'journalist',
                         "a coluna Tipo do modelo não virou tipo de parceiro")

    def test_template_uses_the_same_columns_the_parser_reads(self):
        """O modelo não pode ensinar um formato que o importador não lê.

        Modelo escrito à mão envelhece calado: muda-se um cabeçalho aqui e o
        exemplo passa a ensinar errado. Ele é gerado a partir da mesma lista de
        colunas -- este teste garante que continue assim.
        """
        from odoo.addons.liber_product_bonus.wizard.bonus_list_import import (
            ALIASES, COLUMNS)
        for field, label in COLUMNS:
            self.assertIn(
                label.lower(), ALIASES[field],
                "o modelo escreve %r mas o importador não reconhece esse "
                "título" % label)

    def test_bulk_add_from_a_filtered_selection(self):
        """"quero por exemplo fazer filtros e colocar vários na lista."

        Os filtros bons moram em Contatos (busca, etiquetas, agrupamentos que o
        Odoo já dá). Então o caminho é de lá para cá: marca-se o resultado do
        filtro e a ação joga todo mundo na lista.

        Reentrância é o que este teste guarda: rodar de novo com gente repetida
        não pode estourar a restrição de unicidade nem duplicar -- e a segunda
        rodada quase sempre acontece, porque se filtra de novo e a maioria já
        estava lá.
        """
        lst = self.env['product.bonus.list'].create({'name': "Filtrados"})
        wizard = self.env['product.bonus.list.add'].create({
            'list_id': lst.id,
            'partner_ids': [(6, 0, (self.ana | self.davi).ids)],
            'note': "veio do filtro de imprensa",
        })
        wizard.action_add()
        self.assertEqual(len(lst.member_ids), 2)
        self.assertEqual(lst.member_ids[0].note, "veio do filtro de imprensa")

        # de novo, com um repetido e um novo: sem explodir, sem duplicar
        clara = self.env['res.partner'].create({'name': "Clara"})
        self.env['product.bonus.list.add'].create({
            'list_id': lst.id,
            'partner_ids': [(6, 0, (self.ana | clara).ids)],
        }).action_add()
        self.assertEqual(len(lst.member_ids), 3, "duplicou ou perdeu alguém")

        # quem saiu VOLTA em vez de bater na restrição de unicidade
        member = lst.member_ids.filtered(lambda m: m.partner_id == self.davi)
        member.action_leave()
        self.assertFalse(member.active)
        self.assertEqual(member.left_on, fields.Date.context_today(member))
        self.env['product.bonus.list.add'].create({
            'list_id': lst.id,
            'partner_ids': [(6, 0, self.davi.ids)],
        }).action_add()
        member.invalidate_recordset()
        self.assertTrue(member.active, "quem voltou não foi reativado")
        self.assertFalse(member.left_on, "voltou, mas a data de saída ficou")

    def test_the_wizard_only_inherits_a_selection_of_contacts(self):
        """Abrir pela ficha da lista não pode herdar o id DA LISTA.

        `active_ids` não significa "contatos marcados", significa "os registros
        da tela de onde vim" — e uma das telas é a própria ficha da lista, pelo
        botão da aba Membros. De lá o contexto trazia o id da lista, que era
        lido como id de contato: a lista 2074 tentava carregar
        res.partner(2074) e morria com "Registro não existe ou foi apagado".

        O crash era a sorte. Com dezenas de milhares de contatos na base, o id
        costuma existir — e aí o assistente abriria calado com um estranho já
        marcado. Este teste guarda os dois casos, e é o segundo que importa.
        """
        lst = self.env['product.bonus.list'].create({'name': "Herança"})
        Add = self.env['product.bonus.list.add']

        def herdados(**ctx):
            """Os ids que o assistente traria marcados.

            default_get devolve o valor de um m2m como COMANDO -- [(6, 0, [])]
            para "nenhum". A lista de fora é sempre verdadeira, então testar o
            retorno cru passaria com bug e sem bug.
            """
            val = Add.with_context(**ctx).default_get(['partner_ids']) \
                     .get('partner_ids') or []
            if val and isinstance(val[0], (list, tuple)):
                return list(val[0][2] or [])
            return list(val)

        # 1. Pela ficha da lista: o contexto traz a LISTA, não contatos.
        self.assertEqual(
            herdados(active_model='product.bonus.list',
                     active_id=lst.id, active_ids=lst.ids),
            [], "o assistente herdou o id da lista como se fosse contato")

        # 2. O caso perigoso: existe um CONTATO com aquele id. Antes, ele
        #    entrava calado na seleção; ninguém saberia de onde veio.
        intruso = self.env['res.partner'].create({'name': "Intruso"})
        self.assertEqual(
            herdados(active_model='product.bonus.list',
                     active_id=intruso.id, active_ids=intruso.ids),
            [], "id de outro modelo virou contato marcado, sem erro nenhum")

        # 3. Vindo de Contatos, a seleção continua sendo herdada.
        self.assertCountEqual(
            herdados(active_model='res.partner',
                     active_ids=(self.ana | self.davi).ids),
            (self.ana | self.davi).ids,
            "a porta principal (Contatos > Ação) parou de herdar a seleção")

        # 4. As duas portas pedem coisas opostas: da ficha, a lista já está
        #    decidida e vira título; de Contatos, escolhê-la É a pergunta.
        #    Um seletor de lista no topo de um diálogo aberto DENTRO de uma
        #    lista fazia a tela parecer que servia para "incluir lista".
        self.assertTrue(
            Add.with_context(default_list_id=lst.id)
               .default_get(['list_locked'])['list_locked'],
            "aberto pela ficha, a lista ainda aparece como pergunta")
        self.assertFalse(
            Add.with_context(active_model='res.partner',
                             active_ids=self.ana.ids)
               .default_get(['list_locked']).get('list_locked'),
            "vindo de Contatos, sumiu o campo que diz PARA QUAL lista vai")

    def test_leaving_stamps_the_date_by_any_path(self):
        """"o que é esse Saiu em?" — a data da saída, que nunca era gravada.

        Só o botão "Saiu" da tela avulsa a preenchia. Na aba Membros — onde se
        trabalha — tira-se alguém pelo toggle Ativo, e a data se perdia. A
        lista é um modelo e não um m2m justamente para ter essa história.
        """
        lst = self.env['product.bonus.list'].create({'name': "Histórico"})
        member = self.env['product.bonus.list.member'].create({
            'list_id': lst.id, 'partner_id': self.ana.id})
        member.write({'active': False})          # o que o toggle faz
        self.assertEqual(member.left_on, fields.Date.context_today(member))
        member.write({'active': True})
        self.assertFalse(member.left_on)

    def test_numeric_columns_can_be_sorted(self):
        """"PODER alinhar por colunas que tem números."

        Com 132 listas importadas, "quais são as maiores" e "quais nunca
        renderam nada" têm que ser um clique no cabeçalho. Coluna de campo
        calculado não vira ORDER BY, então estes precisam estar armazenados --
        e um dia alguém vai "otimizar" tirando o store sem perceber que
        arrancou a ordenação junto.
        """
        Lista = self.env['product.bonus.list']
        for model, fields_ in (
            (Lista, ('member_count', 'bonus_count', 'spent', 'outcome_pct')),
            (self.env['res.partner'], ('bonus_count', 'bonus_rating',
                                       'bonus_list_count')),
        ):
            for name in fields_:
                self.assertTrue(
                    model._fields[name].store,
                    "%s.%s deixou de ser armazenado: a coluna para de ordenar"
                    % (model._name, name))
                # a prova real: o ORDER BY tem que chegar ao SQL sem estourar
                model.search([], order='%s desc' % name, limit=1)

    def test_the_rate_is_never_sorted_as_text(self):
        """"19 de 58" viria antes de "5 de 7" -- o oposto do que a coluna promete.

        Por isso a fração continua sendo texto (ela mostra o tamanho da
        amostra, que é o que importa ao ler) e quem ordena é o número ao lado.
        """
        lst = self.env['product.bonus.list'].create({'name': "Taxa"})
        self.assertFalse(self.env['product.bonus.list']._fields['outcome_rate'].store,
                         "a fração virou ordenável e vai ordenar errado")
        b = self._bonus(self.ana)
        b.list_id = lst
        b.action_approve()
        b.action_send()
        b.action_arrived()
        b._set_outcome('great')
        lst.invalidate_recordset()
        self.assertEqual(lst.outcome_pct, 100.0)
        self.assertEqual(lst.outcome_rate, "1 de 1")

    def test_narrow_columns_have_a_fixed_width(self):
        """"ESTÁ apertado!" — e o rótulo curto não tinha resolvido.

        O culpado era outro: "De onde veio" carrega nomes de lista concatenados
        e não tem largura máxima, então engolia a tabela e espremia "Tem?" até
        virar "Te…". Encurtar rótulo nunca ia resolver, porque o rótulo não era
        o problema. Colunas de checkbox e de contagem na seleção do BO precisam
        de largura fixa; este teste existe para que ninguém as tire de novo.
        """
        from lxml import etree
        form = etree.fromstring(
            self.env['product.bonus.dispatch'].get_view(view_type='form')['arch'])
        inner = None
        for node in form.iter('field'):
            if node.get('name') == 'line_ids':
                inner = node.find('list')
        self.assertIsNotNone(inner, "a lista de seleção sumiu do formulário")
        needs_width = ('selected', 'has_title', 'address_ok', 'received_count',
                       'origin', 'rating_html')
        for node in inner.iter('field'):
            if node.get('name') in needs_width:
                self.assertTrue(
                    node.get('width'),
                    "a coluna %r ficou sem largura fixa e vai ser espremida"
                    % node.get('name'))

    def test_no_two_menus_open_the_same_thing(self):
        """"O 'Enviar bonificação' não está fazendo sentido. Ele é a mesma
        coisa do disparo."

        E era: o menu (id ainda menu_bonus_triage, resto da triagem que virou
        o disparo) abria o MESMO modelo que Disparos, só que direto no
        formulário novo -- que é o botão Novo da própria lista. Dois caminhos
        para a mesma coisa não são conveniência, são dúvida sobre se fazem
        coisas diferentes.
        """
        menus = self.env['ir.ui.menu'].search(
            [('id', 'child_of', self.env.ref('liber_product_bonus.menu_bonus_root').id)])
        seen = {}
        for menu in menus:
            action = menu.action
            if not action or action._name != 'ir.actions.act_window':
                continue
            key = (action.res_model, str(action.domain or ''))
            if key in seen:
                self.fail(
                    "menus %r e %r abrem a mesma coisa (%s): um deles sobra"
                    % (seen[key], menu.name, action.res_model))
            seen[key] = menu.name

    # --- meta: guard against shipping configuration nobody reads ----------
    def test_no_dumb_config_fields(self):
        """"Um teste que alerte para o fato de termos criado campos burros."

        soc_fiscal_br declares fiscal positions and CFOPs for consignment that
        look like they configure something and are never read by any code --
        settings that lie to whoever fills them in. This guards product_bonus
        against shipping one: every config field it adds to res.company must be
        consumed somewhere in Python, and every config_parameter field must have
        its key read.
        """
        import glob
        import os
        import re
        from odoo.modules import get_module_path

        code = "\n".join(
            open(f, encoding='utf-8').read()
            for f in glob.glob(os.path.join(get_module_path('liber_product_bonus'),
                                            '**', '*.py'), recursive=True))

        dead = []
        # 1. fields this module puts on the company
        company_fields = [
            n for n, f in self.env['res.company']._fields.items()
            if 'liber_product_bonus' in (getattr(f, '_modules', None) or ())]
        for name in company_fields:
            body = [ln for ln in code.split('\n')
                    # Skip the declaration itself and the settings related=
                    # proxy -- and ONLY those. Discarding every line holding
                    # "company_id.<field>" also threw away the legitimate read
                    # (self.company_id.X), so a live field would be reported
                    # dead. A test that cries wolf gets good code deleted.
                    if not re.match(r'\s*%s\s*=\s*fields\.' % re.escape(name), ln)
                    and not re.search(
                        "related=['\"]company_id\\.%s['\"]" % re.escape(name), ln)]
            if not any(name in ln for ln in body):
                dead.append("res.company.%s" % name)

        # 2. config_parameter fields: the KEY is what gets read, not the field
        for name, f in self.env['res.config.settings']._fields.items():
            if 'liber_product_bonus' not in (getattr(f, '_modules', None) or ()):
                continue
            key = getattr(f, 'config_parameter', None)
            if key and key not in code:
                dead.append("%s (param %s)" % (name, key))

        self.assertTrue(company_fields, "found no config fields -- test is vacuous")
        self.assertFalse(
            dead,
            "configuration nobody reads (campos burros): %s\n"
            "Either consume it in code or drop it -- a setting that does "
            "nothing is worse than no setting." % dead)

    # --- the list ---------------------------------------------------------
    def _lists(self):
        a = self.env['product.bonus.list'].create({
            'name': "Imprensa",
            'member_ids': [(0, 0, {'partner_id': p.id})
                           for p in (self.ana | self.davi)]})
        b = self.env['product.bonus.list'].create({
            'name': "SP",
            'member_ids': [(0, 0, {'partner_id': self.ana.id})]})
        return a, b

    def test_dispatch_takes_several_lists_and_dedups(self):
        """The common answer to "hundreds of lists" is NOT a new list.

        Sending one launch to press AND the SP list is a dispatch with two
        lists, not a permanent third list that gets used once. And somebody on
        both gets ONE book: without the dedup the same person would be shipped
        twice, which is the most embarrassing failure this module can have.
        """
        a, b = self._lists()
        d = self.env['product.bonus.dispatch'].create({
            'product_id': self.book.id,
            'reason_id': self.press.id,
            'list_ids': [(6, 0, (a | b).ids)],
        })
        d._onchange_source()
        self.assertEqual(a.member_count + b.member_count, 3)
        self.assertEqual(len(d.line_ids), 2, "Ana is on both: one row, one book")
        pids = d.line_ids.mapped('partner_id.id')
        self.assertEqual(len(pids), len(set(pids)), "nobody twice")

    def test_combine_union_intersection_difference(self):
        a, b = self._lists()
        Comb = self.env['product.bonus.list.combine']

        u = Comb.create({'name': "U", 'mode': 'union',
                         'list_ids': [(6, 0, (a | b).ids)]})
        self.assertEqual(u.result_count, 2, "union dedups Ana")

        i = Comb.create({'name': "I", 'mode': 'intersection',
                         'list_ids': [(6, 0, (a | b).ids)]})
        self.assertEqual(i.result_count, 1, "only Ana is on both")

        d = Comb.create({'name': "D", 'mode': 'difference',
                         'list_ids': [(6, 0, (a | b).ids)]})
        self.assertEqual(d.result_count, 1, "Imprensa minus SP leaves Davi")

    def test_combined_list_remembers_where_it_came_from(self):
        """Provenance: in a year nobody remembers, and it is exactly what makes
        a list trustworthy or suspect."""
        a, b = self._lists()
        w = self.env['product.bonus.list.combine'].create({
            'name': "Imprensa de SP", 'mode': 'intersection',
            'list_ids': [(6, 0, (a | b).ids)]})
        new = self.env['product.bonus.list'].browse(w.action_combine()['res_id'])
        self.assertEqual(len(new.source_list_ids), 2)
        self.assertEqual(new.combine_mode, 'intersection')

    def test_lists_can_be_found_among_hundreds(self):
        """Tags and "never used" are what keep 300 lists navigable."""
        a, b = self._lists()
        # A name the seed does not use -- the tag name is unique, and the seed
        # already ships "imprensa". Same lesson as the phone: do not assume an
        # empty DB.
        tag = self.env['product.bonus.list.tag'].create({'name': "test-tag-xyz"})
        a.tag_ids = [(6, 0, [tag.id])]
        self.assertIn(a, self.env['product.bonus.list'].search(
            [('tag_ids', 'in', tag.ids)]))
        # b never shipped anything: the filter that finds the dead weight
        never = self.env['product.bonus.list'].search([('bonus_count', '=', 0)])
        self.assertIn(b, never)

    def test_navigation_actions_open_models_that_exist(self):
        """The exact hole Odoo does NOT cover.

        Odoo validates <button name="X"> against the model at install time: a
        button naming a missing method refuses to load. So the bug that shipped
        was never the button name -- action_open_triage existed, and the
        validator waved it through. What was dead lived INSIDE the dict the
        method returns: res_model='product.bonus.triage', a model deleted when
        the wizard became the dispatch. Runtime data; no validator can see it.

        Hence this: call every navigational action and check where it points.
        Only action_view_*/action_open_* -- they are read-only by convention,
        while action_send would actually ship books.
        """
        samples = {
            'product.bonus.list': {'name': "X"},
            'product.bonus': {
                'partner_id': self.ana.id, 'reason_id': self.press.id},
            'product.bonus.dispatch': {
                'product_id': self.book.id, 'reason_id': self.press.id},
        }
        checked = 0
        for model_name, vals in samples.items():
            rec = self.env[model_name].create(vals)
            for attr in dir(rec):
                if not (attr.startswith('action_view_')
                        or attr.startswith('action_open_')):
                    continue
                try:
                    act = getattr(rec, attr)()
                except UserError:
                    # Refusing with a clear message is a fine answer -- the bug
                    # this guards is pointing at a model that is not there.
                    continue
                if not isinstance(act, dict) or 'res_model' not in act:
                    continue
                self.assertIn(
                    act['res_model'], self.env,
                    "%s.%s() opens %s, which does not exist"
                    % (model_name, attr, act['res_model']))
                # and every default_ it passes must be a real field of the target
                for key in (act.get('context') or {}):
                    if key.startswith('default_'):
                        self.assertIn(
                            key[len('default_'):],
                            self.env[act['res_model']]._fields,
                            "%s.%s() passes %s to %s, which has no such field"
                            % (model_name, attr, key, act['res_model']))
                checked += 1
        self.assertGreater(checked, 3, "suspiciously few actions checked")

    # --- the NOTA: value, but no payment ---------------------------------
    def _wire_fiscal(self):
        """Configure the bonus fiscal position, like O15 production.

        The operation lives in the fiscal position: auto-paid pair (so the
        note settles itself) + account mapping (so it does not inflate
        revenue) + the CFOP on the company. No journal, no account fields --
        the journal is the shared REM/ one, asked from nfe_remessa.
        """
        company = self.env.company
        Account = self.env['account.account']
        mirror = Account.search([('code', '=', 'BONTST')], limit=1) or Account.create({
            'code': 'BONTST', 'name': "(-) Remessa em Bonificação (fixture)",
            'account_type': 'income_other', 'company_ids': [(4, company.id)]})
        fpos = self.env['account.fiscal.position'].search(
            [('name', '=', 'Bonificação — Simples Remessa (fixture)'),
             ('company_id', '=', company.id)], limit=1)
        if not fpos:
            fpos = self.env['account.fiscal.position'].create({
                'name': 'Bonificação — Simples Remessa (fixture)',
                'company_id': company.id,
                'auto_invoice_paid': True,
                'auto_invoice_paid_account_id': mirror.id})
        cfop = self.env['nfe.cfop'].search([('document_kind', '=', 'bonus')], limit=1)
        company.write({'bonus_fiscal_position_id': fpos.id, 'bonus_cfop_id': cfop.id})
        return fpos, mirror

    def test_the_note_carries_value_but_generates_no_payment(self):
        """"BO gera B000 que gera movimentação E NOTA (que não gera pagamento)."

        The note is now what he asked on 18/07: a real invoice document (the
        O15 shape), in the shared REM/ journal, auto-settled on post by the
        fiscal position's auto-paid pair -- posted, Paid, residual zero,
        nothing ever owed. Not an entry hidden in Miscellaneous: a note a
        person can find.
        """
        fpos, mirror = self._wire_fiscal()
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        self.assertFalse(b.note_move_id, "the note is not created on send")
        b.action_generate_note()  # explicit step, like the S000

        note = b.note_move_id
        self.assertTrue(note, "the note was not created")
        self.assertEqual(note.move_type, 'out_invoice',
                         "an invoice-shaped document, ready for the NF-e")
        self.assertTrue(note.journal_id.is_remessa, "in the REM/ journal")
        self.assertTrue(note.name.startswith("REM/"),
                        "got %r, wanted the REM/ sequence" % note.name)
        self.assertEqual(note.state, 'posted')
        # never a payment: settled on post, nothing owed
        self.assertEqual(note.payment_state, 'paid')
        self.assertEqual(note.amount_residual, 0.0,
                         "nothing to receive, nothing to pay")
        self.assertEqual(note.fiscal_position_id, fpos,
                         "the operation's fiscal position, not the partner's")
        settle = note.remessa_settle_move_id
        self.assertTrue(settle, "the settlement pair exists")
        self.assertIn(mirror, settle.line_ids.account_id)
        # and the CFOP is stamped for the future NF-e
        self.assertEqual(b.cfop_id.document_kind, 'bonus')

    def test_b000_coordinates_the_note_it_does_not_emit_it(self):
        """B000 is homologous to C000/S000: it COORDINATES logistics and note.

        The repo is import-only, like consignment -- the B000 never emits the
        NF-e. After send it has the MOV and the expense entry, but the fiscal
        note is 'A emitir' (awaited). When the emitted NF-e comes back (key set,
        panel matched by key) it is 'Emitida'; when the same key is stamped on
        the entry, the two are one document -- 'Conciliada'.
        """
        self._wire_fiscal()
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        b.action_generate_note()

        # coordinated, not emitted: MOV + entry exist, note is awaited
        self.assertTrue(b.picking_id, "logistics tied")
        self.assertTrue(b.note_move_id, "the note is posted")
        self.assertEqual(b.fiscal_state, 'to_emit', "the NF-e is not emitted here")

        # the NF-e comes back from outside, matched by key -> Emitida
        import base64
        panel = self.env['nfe.xml.panel'].create({
            'key': '1' * 44,
            'file': base64.b64encode(b'<nfe/>'),
            'file_name': 'remessa.xml'})
        b.nfe_key = '1' * 44
        b.invalidate_recordset()
        self.assertEqual(b.nfe_xml_panel_id, panel, "matched by key, like consignment")
        self.assertEqual(b.fiscal_state, 'emitted')

        # reconcile with the entry -> Conciliada
        b.action_reconcile_nfe()
        b.invalidate_recordset()
        self.assertEqual(b.note_move_id.nfe_key, '1' * 44)
        self.assertEqual(b.fiscal_state, 'reconciled')

    def test_the_note_links_back_to_the_bonus(self):
        """"Gerou nota mas não criou vínculo com a nota."

        The vínculo has to be bidirectional: the B000 points to the note
        (note_move_id) and the note points back to the B000 (bonus_id) -- a
        text ref is not a link. From the accounting entry you must be able to
        reach the bonus that generated it.
        """
        self._wire_fiscal()
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        b.action_generate_note()
        self.assertTrue(b.note_move_id, "B000 -> note")
        self.assertEqual(b.note_move_id.bonus_id, b, "note -> B000 (the vínculo)")
        # and it navigates back
        act = b.note_move_id.action_open_bonus()
        self.assertEqual(act['res_id'], b.id)

    def test_generating_the_note_requires_the_fiscal_mapping(self):
        """"Uma nota de simples remessa que tem que estar mapeada."

        The book still ships without fiscal config (the MOV is the physical
        fact), but "Gerar nota" refuses without the mapping and says exactly what
        is missing -- the CFOP (5910) and the accounts.
        """
        self.env.company.write({
            'bonus_fiscal_position_id': False, 'bonus_cfop_id': False,
        })
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        self.assertEqual(b.state, 'sent')
        self.assertTrue(b.picking_id, "the MOV is the physical fact, config or not")
        self.assertFalse(b.note_move_id, "no note yet")
        with self.assertRaises(UserError) as e:
            b.action_generate_note()
        self.assertIn("5910", str(e.exception),
                      "it must name the simples-remessa CFOP that is unmapped")
        # half-mapped is still unmapped: CFOP alone, no auto-paid position
        cfop = self.env['nfe.cfop'].search([('document_kind', '=', 'bonus')], limit=1)
        self.env.company.bonus_cfop_id = cfop
        with self.assertRaises(UserError):
            b.action_generate_note()

    # --- the chain: BO -> approval -> B000 -> MOV ------------------------
    def test_the_whole_chain_from_dispatch_to_movement(self):
        """One decision, N approvals-by-inheritance, N packages that leave.

        The chain end to end: the BO is approved ONCE, every ficha is born
        approved, and sending each one makes the book physically leave through a
        picking. If any link is missing the module lies -- either the books
        never move, or they move without anybody having said yes.
        """
        self._print_run(1000)
        d = self._dispatch()
        self.assertEqual(d.state, 'draft')

        d.action_check()
        d.action_approve()
        self.assertEqual(d.state, 'approved')
        self.assertEqual(len(d.bonus_ids), 2)
        # approved once, on the dispatch -- every ficha inherits it
        self.assertTrue(all(b.state == 'approved' for b in d.bonus_ids),
                        "the list owner says yes once, not once per person")
        self.assertFalse(any(b.picking_id for b in d.bonus_ids),
                         "nothing moves before it is sent")

        d.action_send_all()
        self.assertEqual(d.state, 'sent')
        for b in d.bonus_ids:
            self.assertEqual(b.state, 'sent')
            self.assertTrue(b.picking_id, "%s released without a MOV" % b.name)
            # released, not shipped: the warehouse expedites, the BON does not
            # complete itself.
            self.assertNotEqual(b.picking_id.state, 'done',
                                "the BON cannot auto-complete -- it is expedited")
            self.assertEqual(b.picking_id.origin, b.name,
                             "the MOV must say which ficha ordered it")
        # the warehouse expedites -> the book leaves
        for b in d.bonus_ids:
            self._expedite(b.picking_id)
            self.assertEqual(b.picking_id.state, 'done')

    def test_the_movement_is_specific(self):
        """"Essa movimentação tem que ser específica."

        Its own operation type, BON/, never the warehouse's generic Delivery
        Orders. Not because a bonus is unbilled -- in Brazil every movement
        carries an XML -- but because its note is a different one: a remessa
        (CFOP 5910), no receivable, not a sale's note. Same physical move,
        different fiscal document, and the two must stay tellable apart.
        """
        self._print_run(1000)
        d = self._dispatch()
        d.action_check()
        d.action_approve()
        d.action_send_all()

        picking = d.bonus_ids[0].picking_id
        ptype = picking.picking_type_id
        self.assertEqual(ptype, self.env.company._get_bonus_operation_type())
        self.assertTrue(picking.name.startswith('BON/'),
                        "the MOV must be numbered BON/, not the delivery series")

        # and it must NOT be the warehouse's normal outgoing type
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        self.assertNotEqual(ptype, warehouse.out_type_id,
                            "a bonus must not land in Delivery Orders")

        # the book really left: stock fell
        self.assertEqual(picking.move_ids.product_id, self.book)
        self.assertEqual(
            picking.move_ids.location_dest_id,
            self.env.ref('stock.stock_location_customers'))

    def test_the_bon_is_released_not_completed(self):
        """"O BON não pode ser concluído automaticamente! ele vai ter que ser
        expedido."

        A comp copy is a real shipment out the door. Sending RELEASES it to
        logistics -- confirmed and reserved -- but the warehouse has to pick,
        pack and expedite it. The BON/ picking must NOT jump to done on send, and
        until it is expedited the book has not left.
        """
        self._print_run(1000)
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()
        self.assertEqual(b.state, 'sent')
        self.assertTrue(b.picking_id)
        self.assertNotEqual(b.picking_id.state, 'done',
                            "the BON cannot complete itself -- it is expedited")
        self.assertIn(b.picking_id.state, ('assigned', 'confirmed', 'waiting'))
        # the warehouse expedites -> the book leaves
        self._expedite(b.picking_id)
        self.assertEqual(b.picking_id.state, 'done')

    def test_released_but_not_expedited_the_stock_has_not_left(self):
        """Reserved is not gone: on-hand drops only when the warehouse expedites,
        and only through the picking (never a quant write)."""
        self._print_run(1000)
        before = self.book.qty_available
        d = self._dispatch()
        d.action_check()
        d.action_approve()
        d.action_send_all()
        self.book.invalidate_recordset()
        self.assertEqual(self.book.qty_available, before,
                         "released and reserved -- but the book has not shipped")
        self.assertTrue(all(b.picking_id.move_ids for b in d.bonus_ids))
        # expedite -> on-hand falls, through the two pickings
        for b in d.bonus_ids:
            self._expedite(b.picking_id)
        self.book.invalidate_recordset()
        self.assertEqual(self.book.qty_available, before - 2,
                         "two books left, through two pickings")

    def test_confirm_arrival_in_bulk(self):
        """"Coloca uma ação para confirmar todas ao mesmo tempo."

        After a batch of calls, mark several as arrived at once. Only the sent
        ones move -- a mixed selection does not drag a draft into 'arrived'.
        """
        b1 = self._bonus(self.ana)
        b1.action_approve(); b1.action_send()
        b2 = self._bonus(self.davi)
        b2.action_approve(); b2.action_send()
        draft = self._bonus(self.ana)  # still draft, must NOT be touched

        (b1 | b2 | draft).action_arrived()
        self.assertEqual(b1.state, 'arrived')
        self.assertEqual(b2.state, 'arrived')
        self.assertEqual(draft.state, 'draft', "a draft must not be dragged along")
        self.assertTrue(b1.arrived_date and b2.arrived_date)

    def test_the_call_list_is_gated_by_days_to_call(self):
        """"Vamos usar esse menu para ligar (...) X dias para ligarmos."

        After release, a ficha does not go on the call list immediately -- only
        once the configured X days have passed. Before that it is in transit;
        after, somebody should call and ask whether it arrived.
        """
        self.env['ir.config_parameter'].sudo().set_param(
            'product_bonus.days_to_call', '7')
        Bonus = self.env['product.bonus']
        b = self._bonus(self.ana)
        b.action_approve()
        b.action_send()

        # context_today: o compute conta os dias no fuso do usuário, e à noite
        # date.today() (UTC) já é amanhã -- o teste quebrava depois das 21h.
        today = fields.Date.context_today(b)
        # just sent -> not on the call list yet
        b.write({'sent_date': today})
        self.assertFalse(b.to_call, "still in transit -- do not call yet")
        self.assertNotIn(b, Bonus.search([('to_call', '=', True)]))

        # sent 8 days ago (> 7) -> time to call
        b.write({'sent_date': today - timedelta(days=8)})
        self.assertTrue(b.to_call, "past the window -- call to confirm arrival")
        self.assertEqual(b.call_date, today - timedelta(days=1))
        # the "A ligar" list uses this search
        self.assertIn(b, Bonus.search([('to_call', '=', True)]))

        # once it arrived, it is off the call list
        b.action_arrived()
        self.assertFalse(b.to_call, "arrived -- no reason to call")
        self.assertNotIn(b, Bonus.search([('to_call', '=', True)]))

    # --- the selection: four sources that ADD UP -------------------------
    def test_sources_add_up_they_are_not_a_radio(self):
        """"A lista de imprensa MAIS os jornalistas de SP que não estão nela
        MAIS o Fulano que pediu" is one ordinary request.

        A single-source radio turned it into three dispatches, three approvals
        and three chances to send the same person two books.
        """
        lst = self.env['product.bonus.list'].create({
            'name': "Imprensa",
            'member_ids': [(0, 0, {'partner_id': self.ana.id})]})
        d = self.env['product.bonus.dispatch'].create({
            'product_id': self.book.id, 'reason_id': self.press.id,
            'list_ids': [(6, 0, lst.ids)]})
        d._onchange_source()
        self.assertEqual(len(d.line_ids), 1)

        # the hand-picked one ADDS, it does not replace
        d.manual_partner_ids = [(6, 0, self.davi.ids)]
        d._onchange_source()
        self.assertEqual(len(d.line_ids), 2)

    def test_empty_filter_adds_nobody(self):
        """The booby trap: the old filter fell back to "every bonus recipient"
        when no criteria were set. With the sources adding up, that would
        quietly pour the whole address book on top of your list."""
        d = self.env['product.bonus.dispatch'].create({
            'product_id': self.book.id, 'reason_id': self.press.id})
        d._onchange_source()
        self.assertEqual(len(d.line_ids), 0, "silence must add nothing")

    def test_a_previous_dispatch_is_a_source(self):
        """A BO already IS a curated selection: somebody sat and decided these
        people. "Send this to whoever got the last book" is the most natural
        mailing base a publisher has -- and it means a campaign almost never has
        to be frozen into a permanent list."""
        first = self._dispatch()
        first.action_check()
        first.action_approve()
        got = first.bonus_ids.mapped('partner_id')
        self.assertTrue(got)

        second = self.env['product.bonus.dispatch'].create({
            'product_id': self.old_book.id, 'reason_id': self.press.id,
            'source_dispatch_ids': [(6, 0, first.ids)]})
        second._onchange_source()
        self.assertEqual(set(second.line_ids.mapped('partner_id.id')),
                         set(got.ids))
        self.assertIn(first.name, second.line_ids[0].origin or '')

    def test_sources_dedup_across_kinds(self):
        """Somebody found by a list AND by a previous BO still gets ONE book.
        Shipping the same person twice in one campaign is the cheapest failure
        to avoid and the most expensive to explain."""
        lst = self.env['product.bonus.list'].create({
            'name': "Imprensa",
            'member_ids': [(0, 0, {'partner_id': p.id})
                           for p in (self.ana | self.davi)]})
        first = self._dispatch()
        first.action_check()
        first.action_approve()

        mixed = self.env['product.bonus.dispatch'].create({
            'product_id': self.old_book.id, 'reason_id': self.press.id,
            'list_ids': [(6, 0, lst.ids)],
            'source_dispatch_ids': [(6, 0, first.ids)],
            'manual_partner_ids': [(6, 0, self.ana.ids)]})
        mixed._onchange_source()
        pids = mixed.line_ids.mapped('partner_id.id')
        self.assertEqual(len(pids), len(set(pids)), "nobody twice")
        self.assertEqual(len(pids), 2, "Ana found three ways is still one row")
        ana = mixed.line_ids.filtered(lambda l: l.partner_id == self.ana)
        self.assertIn("+", ana.origin, "origin must show she came from several")

    def test_list_member_keeps_history(self):
        """A model, not an m2m: an m2m only knows who is on the list today."""
        lst = self.env['product.bonus.list'].create({
            'name': "Press",
            'member_ids': [(0, 0, {'partner_id': self.ana.id})],
        })
        member = lst.member_ids
        self.assertTrue(member.joined_on)
        self.assertEqual(member.added_by_id, self.env.user)
        member.action_leave()
        self.assertFalse(member.active)
        self.assertEqual(member.left_on, fields.Date.context_today(member))
        self.assertEqual(lst.member_count, 0)
        self.assertTrue(member.exists(), "leaving must not erase the history")
