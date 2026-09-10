# -*- coding: utf-8 -*-
"""Montar a grade: vários títulos de uma vez, e o modelo que se repete.

A regra que este arquivo defende é uma só, e vale para os dois caminhos:
linha que JÁ SAIU para a feira não se apaga nem se rebaixa. O movimento já
existe; mexer nela faria a grade mentir sobre o que foi despachado.
"""
from datetime import date, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs')
class TestGradeEModelo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.livros = cls.env['product.product'].create([
            {'name': 'Título %d' % i, 'type': 'consu', 'is_storable': True}
            for i in range(1, 5)
        ])
        cls.env['stock.quant']._update_available_quantity(
            cls.livros[0], cls.warehouse.lot_stock_id, 100)
        cls.today = date(2026, 9, 20)

    def _fair(self, linhas=None):
        return self.env['event.fair'].create({
            'name': 'Feira da Grade',
            'date_start': self.today,
            'date_end': self.today + timedelta(days=1),
            'company_id': self.company.id,
            'line_ids': linhas or [],
        })

    def _receber(self, fair):
        """Segunda perna da ida: quem está na praça confere a chegada."""
        for picking in fair.picking_ids.filtered(
                lambda p: p.fair_operation == 'receipt'
                and p.state not in ('done', 'cancel')):
            picking.action_assign()
            # NÃO se força a quantidade: recebe-se o que o trânsito tem de
            # verdade. Forçar aqui faria o teste receber nove exemplares de
            # um título que saiu zero do armazém -- exatamente a mentira que
            # a segunda perna existe para impedir.
            picking.move_ids.picked = True
            picking.with_context(
                skip_backorder=True,
                picking_ids_not_to_backorder=picking.ids).button_validate()
        return True

    def _add(self, fair, produtos, qty=2, skip=True):
        wizard = self.env['event.fair.add.products'].with_context(
            active_model='event.fair', active_id=fair.id).create({
                'fair_id': fair.id,
                'product_ids': [(6, 0, produtos.ids)],
                'qty_planned': qty,
                'skip_existing': skip,
            })
        wizard.action_add()
        return wizard

    # --- vários de uma vez ------------------------------------------------
    def test_adding_several_titles_at_once(self):
        fair = self._fair()
        self._add(fair, self.livros, qty=3)
        self.assertEqual(len(fair.line_ids), 4)
        self.assertEqual(set(fair.line_ids.mapped('qty_planned')), {3.0})
        self.assertEqual(fair.qty_planned, 12)

    def test_a_title_already_in_the_grid_is_skipped(self):
        fair = self._fair()
        self._add(fair, self.livros[0], qty=5)
        self._add(fair, self.livros, qty=2, skip=True)
        self.assertEqual(len(fair.line_ids), 4)
        linha = fair.line_ids.filtered(
            lambda l: l.product_id == self.livros[0])
        self.assertEqual(linha.qty_planned, 5,
                         "Pular quer dizer não mexer no que já estava")

    def test_not_skipping_raises_the_existing_quantity(self):
        fair = self._fair()
        self._add(fair, self.livros[0], qty=5)
        self._add(fair, self.livros[0], qty=2, skip=False)
        self.assertEqual(fair.line_ids.qty_planned, 7)

    def test_adding_nothing_is_refused(self):
        fair = self._fair()
        wizard = self.env['event.fair.add.products'].create({
            'fair_id': fair.id, 'qty_planned': 1})
        with self.assertRaises(UserError):
            wizard.action_add()

    # --- modelo -----------------------------------------------------------
    def _template(self, nome='Perfil geral'):
        return self.env['event.fair.template'].create({
            'name': nome,
            'company_id': self.company.id,
            'line_ids': [
                (0, 0, {'product_id': self.livros[0].id, 'qty_planned': 4}),
                (0, 0, {'product_id': self.livros[1].id, 'qty_planned': 2}),
            ],
        })

    def _apply(self, fair, template, mode='add'):
        wizard = self.env['event.fair.apply.template'].with_context(
            active_model='event.fair', active_id=fair.id).create({
                'fair_id': fair.id, 'template_id': template.id, 'mode': mode})
        wizard.action_apply()
        return wizard

    def test_applying_a_template_fills_the_grid(self):
        fair = self._fair()
        self._apply(fair, self._template())
        self.assertEqual(len(fair.line_ids), 2)
        self.assertEqual(fair.qty_planned, 6)

    def test_the_template_carries_the_minimum_to_the_grid(self):
        """O mínimo de mesa é decisão de quem monta a grade, e viaja com ela."""
        template = self._template()
        # a primeira linha do modelo pede 4 exemplares: o mínimo cabe nela
        template.line_ids[0].qty_min = 3
        fair = self._fair()
        self._apply(fair, template)
        linha = fair.line_ids.filtered(
            lambda l: l.product_id == template.line_ids[0].product_id)
        self.assertEqual(linha.qty_min, 3)

    def test_saving_a_template_keeps_the_minimum(self):
        fair = self._fair()
        self._add(fair, self.livros[0], qty=5)
        fair.line_ids.qty_min = 4
        wizard = self.env['event.fair.save.template'].create({
            'fair_id': fair.id, 'name': 'Com mínimo'})
        wizard.action_save()
        template = self.env['event.fair.template'].search(
            [('name', '=', 'Com mínimo')])
        self.assertEqual(template.line_ids.qty_min, 4)
        self.assertEqual(template.line_ids.qty_planned, 5)

    def test_applying_the_same_template_twice_does_not_double_it(self):
        """O modelo é aplicado, não somado: duas vezes dá a mesma grade."""
        fair = self._fair()
        template = self._template()
        self._apply(fair, template)
        self._apply(fair, template)
        self.assertEqual(fair.qty_planned, 6)

    def test_replacing_keeps_what_already_shipped(self):
        """Substituir limpa o que não saiu; o que já foi fica."""
        fair = self._fair()
        self._add(fair, self.livros[0], qty=3)   # este vai sair
        self._add(fair, self.livros[3], qty=9)   # este só está no papel
        fair.action_plan()
        picking = fair.action_ship()
        picking.action_assign()
        for move in picking.move_ids:
            if move.product_id == self.livros[0]:
                move.quantity = 3
                move.picked = True
            else:
                move.quantity = 0
        # Pelo caminho da tela, com a regra da casa: feira não cria pedido em
        # espera. Chamar `_action_done()` cru deixava a linha de zero num
        # pedido em espera, e a chegada ficava encadeada a uma carga que
        # nunca saiu.
        picking.with_context(
            skip_backorder=True,
            picking_ids_not_to_backorder=picking.ids).button_validate()
        self._receber(fair)
        self.assertEqual(
            fair.line_ids.filtered(
                lambda l: l.product_id == self.livros[0]).qty_sent, 3)
        self._apply(fair, self._template(), mode='replace')
        produtos = fair.line_ids.mapped('product_id')
        self.assertIn(self.livros[0], produtos,
                      "Título já despachado não pode sumir da grade")
        self.assertNotIn(self.livros[3], produtos,
                         "O que só estava no papel devia ter saído")
        linha = fair.line_ids.filtered(
            lambda l: l.product_id == self.livros[0])
        self.assertEqual(linha.qty_planned, 4,
                         "O modelo pede 4, e 3 já saíram: sobe para 4")

    # --- guardar como modelo ---------------------------------------------
    def test_saving_the_grid_as_a_template(self):
        fair = self._fair()
        self._add(fair, self.livros, qty=2)
        wizard = self.env['event.fair.save.template'].with_context(
            active_model='event.fair', active_id=fair.id).create({
                'fair_id': fair.id, 'name': 'Grade de Paraty'})
        wizard.action_save()
        template = self.env['event.fair.template'].search(
            [('name', '=', 'Grade de Paraty')])
        self.assertEqual(len(template), 1)
        self.assertEqual(template.line_count, 4)
        self.assertEqual(template.qty_total, 8)

    def test_saving_an_empty_grid_is_refused(self):
        fair = self._fair()
        wizard = self.env['event.fair.save.template'].create({
            'fair_id': fair.id, 'name': 'Vazia'})
        with self.assertRaises(UserError):
            wizard.action_save()


@tagged('post_install', '-at_install', 'liber_fairs')
class TestEstoqueNaGrade(TransactionCase):
    """A coluna de estoque da grade mede o ARMAZÉM.

    O livro na mesa da feira continua sendo nosso, em localização interna. O
    que o impede de aparecer como disponível é a raiz FEIRAS ficar FORA da
    árvore do armazém: por isso o próprio "Em mãos" do núcleo já não o conta.
    Este arquivo prende esse comportamento. No dia em que alguém pendurar a
    raiz sob WH, o número volta a somar exemplar que está a seiscentos
    quilômetros, e é aqui que se descobre.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.livro = cls.env['product.product'].create({
            'name': 'Título do Estoque', 'type': 'consu', 'is_storable': True})
        cls.env['stock.quant']._update_available_quantity(
            cls.livro, cls.warehouse.lot_stock_id, 30)
        cls.today = date(2026, 9, 20)

    def _receber(self, fair):
        """Segunda perna da ida: quem está na praça confere a chegada."""
        for picking in fair.picking_ids.filtered(
                lambda p: p.fair_operation == 'receipt'
                and p.state not in ('done', 'cancel')):
            picking.action_assign()
            # NÃO se força a quantidade: recebe-se o que o trânsito tem de
            # verdade. Forçar aqui faria o teste receber nove exemplares de
            # um título que saiu zero do armazém -- exatamente a mentira que
            # a segunda perna existe para impedir.
            picking.move_ids.picked = True
            picking.with_context(
                skip_backorder=True,
                picking_ids_not_to_backorder=picking.ids).button_validate()
        return True

    def _fair(self, qty):
        return self.env['event.fair'].create({
            'name': 'Feira do Estoque',
            'date_start': self.today, 'date_end': self.today,
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.livro.id, 'qty_planned': qty})],
        })

    def test_the_grid_shows_the_warehouse_not_the_company(self):
        fair = self._fair(10)
        self.assertEqual(fair.line_ids.qty_warehouse, 30)
        fair.action_plan()
        picking = fair.action_ship()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()
        self._receber(fair)
        # Dez foram para a mesa: o armazém tem vinte, e é o que a grade mostra.
        self.assertEqual(fair.line_ids.qty_warehouse, 20,
                         "A grade tem de mostrar o armazém")
        self.assertEqual(fair.line_ids.qty_on_shelf, 10)
        # E o "Em mãos" geral também dá vinte, porque a raiz FEIRAS está fora
        # do armazém. Se um dia der trinta, alguém a pendurou sob WH.
        self.assertEqual(
            self.livro.with_context(company_id=self.company.id).qty_available,
            20,
            "A raiz FEIRAS saiu de baixo do armazém? O Em mãos voltou a "
            "somar o que está na praça")
        quant = self.env['stock.quant'].search([
            ('location_id', '=', fair.stock_location_id.id),
            ('product_id', '=', self.livro.id)])
        self.assertEqual(sum(quant.mapped('quantity')), 10,
                         "Os dez não sumiram: estão na localização da feira")

    def test_short_is_flagged_when_the_warehouse_cannot_cover_the_grid(self):
        fair = self._fair(45)
        self.assertTrue(fair.line_ids.is_short,
                        "Planejar 45 com 30 no armazém é ruptura")
        fair.line_ids.qty_planned = 20
        self.assertFalse(fair.line_ids.is_short)


@tagged('post_install', '-at_install', 'liber_fairs')
class TestFiltroDoCatalogo(TransactionCase):
    """Escolher entre milhares: o filtro do assistente.

    O catálogo da casa tem quatro mil e seiscentos títulos. O que este
    arquivo defende é que o filtro devolve o que se pediu e NADA além, e que
    o "só o que está no armazém" mede o armazém, não a empresa.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.selo = cls.env['product.category'].create({'name': 'Selo do Teste'})
        cls.colecao = cls.env['product.category'].create(
            {'name': 'Coleção do Teste', 'parent_id': cls.selo.id})
        cls.outro = cls.env['product.category'].create({'name': 'Outro Selo'})
        cls.tag = cls.env['product.tag'].create({'name': 'filosofia-teste'})
        cls.caro = cls.env['product.product'].create({
            'name': 'Caro da Coleção', 'type': 'consu', 'is_storable': True,
            'categ_id': cls.colecao.id, 'list_price': 120.0,
            'product_tag_ids': [(4, cls.tag.id)]})
        cls.barato = cls.env['product.product'].create({
            'name': 'Barato do Selo', 'type': 'consu', 'is_storable': True,
            'categ_id': cls.selo.id, 'list_price': 30.0})
        cls.forasteiro = cls.env['product.product'].create({
            'name': 'De Outro Selo', 'type': 'consu', 'is_storable': True,
            'categ_id': cls.outro.id, 'list_price': 50.0})
        for p in (cls.caro, cls.barato, cls.forasteiro):
            cls.env['stock.quant']._update_available_quantity(
                p, cls.warehouse.lot_stock_id, 5)
        cls.sem_estoque = cls.env['product.product'].create({
            'name': 'Esgotado do Selo', 'type': 'consu', 'is_storable': True,
            'categ_id': cls.selo.id, 'list_price': 40.0})
        # Dois exemplares livres não sustentam uma mesa de três dias.
        cls.raspa_de_tacho = cls.env['product.product'].create({
            'name': 'Quase Esgotado do Selo', 'type': 'consu',
            'is_storable': True, 'categ_id': cls.selo.id, 'list_price': 45.0})
        cls.env['stock.quant']._update_available_quantity(
            cls.raspa_de_tacho, cls.warehouse.lot_stock_id, 2)
        cls.fair = cls.env['event.fair'].create({
            'name': 'Feira do Filtro',
            'date_start': date(2026, 9, 20), 'date_end': date(2026, 9, 20),
            'company_id': cls.company.id})

    def _wizard(self, **vals):
        base = {'fair_id': self.fair.id, 'qty_planned': 2, 'limit': 0}
        base.update(vals)
        return self.env['event.fair.add.products'].create(base)

    def test_the_imprint_brings_its_collections_along(self):
        w = self._wizard(filter_categ_id=self.selo.id, min_stock=0)
        w.action_search()
        encontrados = w.product_ids
        self.assertIn(self.caro, encontrados,
                      "O selo tem de trazer os títulos da coleção abaixo dele")
        self.assertIn(self.barato, encontrados)
        self.assertNotIn(self.forasteiro, encontrados,
                         "Título de outro selo não devia ter vindo")

    def test_filtering_by_tag(self):
        w = self._wizard(filter_tag_ids=[(6, 0, [self.tag.id])],
                         min_stock=0)
        w.action_search()
        self.assertEqual(w.product_ids, self.caro)

    def test_filtering_by_price(self):
        w = self._wizard(filter_categ_id=self.selo.id, filter_price_max=50.0,
                         min_stock=0)
        w.action_search()
        self.assertIn(self.barato, w.product_ids)
        self.assertNotIn(self.caro, w.product_ids)

    def test_a_minimum_of_one_drops_what_cannot_be_shipped(self):
        w = self._wizard(filter_categ_id=self.selo.id, min_stock=1)
        w.action_search()
        self.assertNotIn(self.sem_estoque, w.product_ids,
                         "Grade cheia do que não temos é grade que ninguém "
                         "consegue despachar")
        self.assertIn(self.barato, w.product_ids)

    def test_the_minimum_is_a_threshold_not_a_yes_or_no(self):
        """A pergunta da feira não é "tem?", é "tem o bastante?"."""
        w = self._wizard(filter_categ_id=self.selo.id, min_stock=5)
        w.action_search()
        self.assertIn(self.barato, w.product_ids,
                      "Cinco livres atende o mínimo de cinco")
        self.assertNotIn(self.raspa_de_tacho, w.product_ids,
                         "Dois livres não sustentam uma mesa: fora da grade")

    def test_a_minimum_of_zero_brings_everything(self):
        w = self._wizard(filter_categ_id=self.selo.id, min_stock=0)
        w.action_search()
        self.assertIn(self.sem_estoque, w.product_ids,
                      "Zero traz tudo, com estoque ou sem")

    def test_the_limit_cuts_the_result(self):
        w = self._wizard(filter_categ_id=self.selo.id, min_stock=0,
                         limit=1)
        w.action_search()
        self.assertEqual(len(w.product_ids), 1)
        self.assertEqual(w.found_count, 1)

    def test_the_search_feeds_the_grid(self):
        w = self._wizard(filter_categ_id=self.selo.id, min_stock=0)
        w.action_search()
        w.action_add()
        # o selo tem quatro títulos, e min_stock=0 traz todos
        self.assertEqual(len(self.fair.line_ids), 4)
        self.assertEqual(set(self.fair.line_ids.mapped('qty_planned')), {2.0})

    def test_the_same_wizard_fills_a_template(self):
        template = self.env['event.fair.template'].create(
            {'name': 'Modelo pelo filtro', 'company_id': self.company.id})
        w = self.env['event.fair.add.products'].create({
            'template_id': template.id, 'qty_planned': 4, 'limit': 0,
            'filter_categ_id': self.selo.id, 'min_stock': 0})
        w.action_search()
        w.action_add()
        self.assertEqual(template.line_count, 4)
        self.assertEqual(template.qty_total, 16)

    def test_a_template_does_not_hide_what_is_out_of_stock(self):
        """Modelo é planejamento, e planejamento inclui o esgotado.

        Na grade de uma feira que sai semana que vem, o estoque livre é
        pergunta legítima. No modelo, não: ele serve de lista para o ano que
        vem e para imprimir e conferir na mesa, e esconder o título esgotado
        esconde justamente o que se quer ver.
        """
        template = self.env['event.fair.template'].create(
            {'name': 'Modelo que planeja', 'company_id': self.company.id})
        campos = self.env['event.fair.add.products'].with_context(
            active_model='event.fair.template',
            active_id=template.id).default_get(
                ['template_id', 'fair_id', 'min_stock'])
        self.assertEqual(campos.get('min_stock'), 0.0,
                         "O modelo não filtra por estoque")

        w = self.env['event.fair.add.products'].create({
            'template_id': template.id, 'qty_planned': 3, 'limit': 0,
            'filter_categ_id': self.selo.id,
            'min_stock': campos.get('min_stock')})
        w.action_search()
        self.assertIn(self.sem_estoque, w.product_ids,
                      "O esgotado tem de aparecer no modelo")

    def test_the_fair_grid_still_asks_for_stock(self):
        """O contrário do teste acima: a grade da feira continua exigindo."""
        campos = self.env['event.fair.add.products'].with_context(
            active_model='event.fair',
            active_id=self.fair.id).default_get(['fair_id', 'min_stock'])
        self.assertEqual(campos.get('min_stock'), 1.0)

    def test_titles_go_to_a_fair_or_to_a_template_never_to_both(self):
        template = self.env['event.fair.template'].create(
            {'name': 'Modelo confuso', 'company_id': self.company.id})
        with self.assertRaises(UserError):
            self.env['event.fair.add.products'].create({
                'fair_id': self.fair.id, 'template_id': template.id,
                'qty_planned': 1})


@tagged('post_install', '-at_install', 'liber_fairs')
class TestMinimoDeMesa(TransactionCase):
    """O mínimo é um patamar DENTRO da grade, não um desejo ao lado dela.

    Pedir dez exemplares e exigir quinze na mesa é uma mesa que nasce abaixo
    do próprio mínimo: no primeiro fechamento o sistema sugeriria repor cinco
    de um título que ninguém comprou.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.livro = cls.env['product.product'].create({
            'name': 'Título do Mínimo', 'type': 'consu', 'is_storable': True})
        cls.fair = cls.env['event.fair'].create({
            'name': 'Feira do Mínimo',
            'date_start': date(2026, 9, 20), 'date_end': date(2026, 9, 20),
            'company_id': cls.company.id})

    def test_the_minimum_may_exceed_the_copies_sent(self):
        """Pedir mais do que existe é DIZER QUE FALTA, não errar de digitar.

        Havia trava aqui, e ela apagava a informação que interessa: se a mesa
        precisa de quinze e a casa só tem dez, o que a grade está dizendo é
        que faltam cinco -- e é assim que alguém descobre o que precisa de
        reimpressão. "Pode liberar tudo que a equipe vai ter que correr atrás
        de reimpressão."
        """
        linha = self.env['event.fair.line'].create({
            'fair_id': self.fair.id, 'product_id': self.livro.id,
            'qty_planned': 10, 'qty_min': 15})
        self.assertEqual(linha.qty_min, 15)
        self.assertEqual(linha.qty_planned, 10)

    def test_raising_the_minimum_over_the_grid_is_allowed(self):
        linha = self.env['event.fair.line'].create({
            'fair_id': self.fair.id, 'product_id': self.livro.id,
            'qty_planned': 10, 'qty_min': 5})
        linha.qty_min = 12
        self.assertEqual(linha.qty_min, 12)

    def test_the_minimum_may_equal_the_copies_sent(self):
        """Mandar dez e querer dez na mesa é grade que repõe tudo que vende."""
        linha = self.env['event.fair.line'].create({
            'fair_id': self.fair.id, 'product_id': self.livro.id,
            'qty_planned': 10, 'qty_min': 10})
        self.assertEqual(linha.qty_min, 10)

    def test_the_template_takes_a_minimum_above_the_grid_too(self):
        template = self.env['event.fair.template'].create(
            {'name': 'Modelo do Mínimo', 'company_id': self.company.id})
        linha = self.env['event.fair.template.line'].create({
            'template_id': template.id, 'product_id': self.livro.id,
            'qty_planned': 4, 'qty_min': 9})
        self.assertEqual(linha.qty_min, 9)
