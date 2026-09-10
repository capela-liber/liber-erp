# -*- coding: utf-8 -*-
"""O caixa da feira vende a mesa, e a feira enxerga essa venda.

A afirmação que este arquivo defende é uma só, e é a razão de a ponte
existir: a venda do balcão TEM de aparecer como venda da feira. Se não
aparecer, o fechamento diário -- que desconta a diferença entre o esperado e
o contado -- lança a mesma venda de novo, e a mesa fica negativa.
"""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs_pos')
class TestCaixaDaFeira(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.livro = cls.env['product.product'].create({
            'name': 'Título do Balcão', 'type': 'consu',
            'is_storable': True, 'list_price': 40.0, 'standard_price': 20.0,
            'available_in_pos': False,
        })
        cls.env['stock.quant']._update_available_quantity(
            cls.livro, cls.warehouse.lot_stock_id, 100)

    def _feira_na_praca(self, qty=10):
        """Feira planejada, despachada e CONFERIDA: a mesa existe de fato."""
        fair = self.env['event.fair'].create({
            'name': 'Feira do Balcão',
            'date_start': date(2026, 9, 20), 'date_end': date(2026, 9, 20),
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.livro.id, 'qty_planned': qty})]})
        fair.action_plan()
        saida = fair.action_ship()
        saida.action_assign()
        for move in saida.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        saida.button_validate()
        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt' and p.state != 'done')
        chegada.action_fair_check()
        return fair

    def _operadores(self, fair, *nomes):
        """Um operador, um caixa: é assim que o caixa nasce.

        Operador é CONTATO, não texto: digitar o nome à mão produziria três
        pessoas onde há uma.
        """
        linhas = []
        for nome in nomes:
            contato = self.env['res.partner'].search(
                [('name', '=', nome)], limit=1) or \
                self.env['res.partner'].create({'name': nome})
            linhas.append({'fair_id': fair.id, 'partner_id': contato.id})
        return self.env['event.fair.cashier'].create(linhas)

    def _venda(self, fair, qty, sessao=None):
        """Uma venda de balcão pelo caminho real do PDV.

        A sessão se reaproveita: o PDV recusa duas sessões abertas no mesmo
        caixa, e no balcão é assim mesmo -- vende e devolve no mesmo turno.
        """
        if sessao is None:
            sessao = self.env['pos.session'].create({
                'config_id': fair.pos_config_id.id,
                'user_id': self.env.user.id})
            sessao.action_pos_session_open()
        pedido = self.env['pos.order'].create({
            'company_id': self.company.id,
            'session_id': sessao.id,
            'amount_tax': 0.0,
            'amount_total': 40.0 * qty,
            'amount_paid': 40.0 * qty,
            'amount_return': 0.0,
            # PAGO: no balcão o pedido nasce pago, e rascunho é venda
            # começada e não terminada -- ela existe, e é ela que segura o
            # fechamento do caixa.
            'state': 'paid',
            'lines': [(0, 0, {
                'product_id': self.livro.id,
                'qty': qty,
                'price_unit': 40.0,
                'price_subtotal': 40.0 * qty,
                'price_subtotal_incl': 40.0 * qty,
            })],
        })
        # PAGAMENTO DE VERDADE. Sem `pos.payment`, o lançamento que o
        # fechamento do caixa monta não fecha, e o PDV reage dando rollback
        # no cursor -- que dentro de teste é erro de teste, não do módulo.
        metodo = sessao.payment_method_ids.filtered(
            lambda m: m.type == 'cash')[:1] or sessao.payment_method_ids[:1]
        self.env['pos.payment'].create({
            'pos_order_id': pedido.id,
            'payment_method_id': metodo.id,
            'amount': pedido.amount_total,
            'session_id': sessao.id,
        })
        pedido._create_order_picking()
        return sessao, pedido

    # --- o caixa ----------------------------------------------------------
    def test_the_register_sells_the_table_not_the_warehouse(self):
        fair = self._feira_na_praca()
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        config = fair.pos_config_id
        self.assertTrue(config)
        self.assertEqual(
            config.picking_type_id.default_location_src_id,
            fair.stock_location_id,
            "O caixa tem de tirar o livro da MESA, não do armazém")
        self.assertEqual(config.fair_id, fair)
        self.assertEqual(config.picking_type_id.fair_id, fair)

    def test_the_grid_titles_show_up_at_the_counter(self):
        """Livro não marcado para o PDV não aparece no balcão: tela vazia."""
        fair = self._feira_na_praca()
        self._operadores(fair, 'Marta')
        self.assertFalse(self.livro.available_in_pos)
        fair.action_open_pos()
        self.assertTrue(self.livro.available_in_pos)

    def test_the_counter_shows_the_grid_and_not_the_catalogue(self):
        """O balcão é a mesa, não o catálogo da casa."""
        outro = self.env['product.product'].create({
            'name': 'Título que ficou no armazém', 'type': 'consu',
            'is_storable': True, 'available_in_pos': True})
        fair = self._feira_na_praca()
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        config = fair.pos_config_id
        self.assertTrue(config.limit_categories,
                        "Sem recorte, a praça procura a mesa dentro do "
                        "catálogo inteiro")
        categorias = config.iface_available_categ_ids
        self.assertTrue(categorias)
        self.assertIn(categorias, self.livro.pos_categ_ids)
        self.assertNotIn(categorias, outro.pos_categ_ids,
                         "Título fora da grade não entra no balcão")

    def test_the_register_does_not_open_for_a_draft_fair(self):
        fair = self.env['event.fair'].create({
            'name': 'Feira só no papel',
            'date_start': date(2026, 9, 20), 'date_end': date(2026, 9, 20),
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.livro.id, 'qty_planned': 5})]})
        with self.assertRaises(UserError):
            fair.action_open_pos()

    def test_opening_twice_reuses_the_same_register(self):
        fair = self._feira_na_praca()
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        primeiro = fair.pos_config_id
        fair.action_open_pos()
        self.assertEqual(fair.pos_config_id, primeiro,
                         "Duas feiras é que são dois caixas, não dois cliques")

    # --- a venda ----------------------------------------------------------
    def test_a_counter_sale_is_a_fair_sale(self):
        """O carimbo: sem ele a feira contaria a venda duas vezes."""
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        self._venda(fair, 3)

        movimento = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'sale' and p.state == 'done')
        self.assertTrue(movimento, "A venda do balcão tem de ser da feira")
        self.assertEqual(fair.qty_sold, 3)
        self.assertEqual(fair.line_ids.qty_on_shelf, 7,
                         "Dez menos três: a mesa sabe o que o caixa vendeu")

    def test_the_daily_count_does_not_charge_the_sale_twice(self):
        """A prova do pudim: contar a mesa depois do PDV não vende de novo."""
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        self._venda(fair, 3)

        dia = fair.day_ids[0]
        dia.action_fill()
        self.assertEqual(dia.line_ids.qty_expected, 7,
                         "O esperado já desconta o que o caixa vendeu")
        dia.line_ids.qty_counted = 7
        dia.action_close()
        self.assertEqual(dia.qty_sold, 0,
                         "Nada a lançar: o caixa já lançou")
        self.assertEqual(fair.qty_sold, 3, "E a venda continua sendo três")

    def test_a_refund_puts_the_copy_back_on_the_table(self):
        """Cliente desistiu: o exemplar volta para a pilha, não some."""
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        sessao, _pedido = self._venda(fair, 3)
        self._venda(fair, -1, sessao=sessao)

        self.assertEqual(fair.qty_sold, 2,
                         "Três vendidos menos um devolvido")
        self.assertEqual(fair.line_ids.qty_on_shelf, 8)

    def test_two_registers_do_not_collide(self):
        """Duas feiras ao mesmo tempo: séries separadas, nomes separados.

        Escrito depois de a encenação morrer com
        `stock_picking_name_uniq` em WH/FPDV/00001: os dois caixas nasciam com
        o mesmo código de série, dividiam o prefixo do nome da transferência,
        e o segundo colidia com o primeiro. É a mesma doença da série COM/IN.
        """
        uma = self._feira_na_praca(10)
        self._operadores(uma, 'Marta')
        uma.action_open_pos()
        self._venda(uma, 2)

        outra = self._feira_na_praca(10)
        self._operadores(outra, 'Joana')
        outra.action_open_pos()
        self._venda(outra, 2)

        self.assertNotEqual(uma.pos_picking_type_id.sequence_code,
                            outra.pos_picking_type_id.sequence_code)
        nomes = [p.name for p in (uma | outra).picking_ids.filtered(
            lambda p: p.fair_operation == 'sale')]
        self.assertEqual(len(nomes), len(set(nomes)),
                         "Nome de transferência repetido entre feiras: %s"
                         % nomes)
        self.assertEqual(uma.qty_sold, 2)
        self.assertEqual(outra.qty_sold, 2)

    def test_the_day_shows_what_the_register_sold(self):
        """A pergunta dele: "quando eu trago o dia, não deveria ter o vendido?"

        O "Vendido" do fechamento é subtração -- esperado menos contado --, e
        Trazer a mesa preenche a contagem igual ao esperado; por isso ele
        nasce zero, e é assim que tem de ser: quem conta corrige para baixo.
        O que faltava era o OUTRO número, o que o balcão registrou. A
        diferença entre os dois é o que ninguém vê de outro jeito.
        """
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        self._venda(fair, 3)

        # A venda pertence ao DIA DO CALENDÁRIO em que aconteceu; a feira do
        # teste está marcada para setembro, e a venda é de hoje.
        dia = fair.day_ids[0]
        dia.date = date.today()
        dia.action_fill()
        linha = dia.line_ids

        self.assertEqual(linha.qty_pos, 3,
                         "O caixa vendeu três, e o dia tem de dizer isso")
        self.assertEqual(linha.qty_sold, 0,
                         "E o Vendido da contagem nasce zero: ninguém contou "
                         "a mesa ainda")
        self.assertEqual(linha.qty_expected, 7,
                         "O esperado já vem descontado do que o caixa vendeu")
        self.assertEqual(dia.pos_qty, 3)

        # quem conta a mesa acha seis: falta um que o caixa não viu
        linha.qty_counted = 6
        self.assertEqual(linha.qty_sold, 1,
                         "A diferença aparece na coluna da contagem")

    # --- fechar -----------------------------------------------------------
    def test_the_return_closes_the_register(self):
        """Encerrar a feira fecha o caixa, e nessa ordem.

        Sessão aberta ainda registra venda, e venda lançada depois da
        contagem faria o retorno pedir livro que já saiu da mesa.
        """
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        sessao, _pedido = self._venda(fair, 1)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = dia.line_ids.qty_expected
        dia.action_close()

        fair.action_return()

        self.assertEqual(sessao.state, 'closed',
                         "O caixa tem de fechar junto com a feira")
        self.assertFalse(fair.pos_config_ids.filtered('active'),
                         "E sair da lista de quem opera PDV todo dia")

    def test_an_unpaid_order_stops_the_return(self):
        """Venda começada e não paga é decisão de quem está no balcão."""
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        sessao = self.env['pos.session'].create({
            'config_id': fair.pos_config_id.id, 'user_id': self.env.user.id})
        sessao.action_pos_session_open()
        self.env['pos.order'].create({
            'company_id': self.company.id, 'session_id': sessao.id,
            'amount_tax': 0.0, 'amount_total': 40.0, 'amount_paid': 0.0,
            'amount_return': 0.0, 'state': 'draft',
            'lines': [(0, 0, {
                'product_id': self.livro.id, 'qty': 1, 'price_unit': 40.0,
                'price_subtotal': 40.0, 'price_subtotal_incl': 40.0})]})
        with self.assertRaises(UserError):
            fair.action_return()

    # --- quantos caixas ---------------------------------------------------
    def test_one_register_per_operator(self):
        """Fila só é fila que não anda: feira grande tem três operadores."""
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta', 'Joana', 'Rui')
        fair.action_open_pos()
        self.assertEqual(len(fair.pos_config_ids), 3)
        nomes = fair.pos_config_ids.mapped('name')
        self.assertEqual(len(set(nomes)), 3, "Nomes repetidos: %s" % nomes)
        series = fair.pos_picking_type_ids.mapped('sequence_code')
        self.assertEqual(len(set(series)), 3,
                         "Séries repetidas entre caixas da MESMA feira "
                         "colidem no nome da transferência: %s" % series)

    def test_the_register_carries_the_fair_and_the_operator(self):
        """No cartão do PDV: a feira e quem está no balcão."""
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        self.assertEqual(fair.pos_config_id.name,
                         '%s - Marta' % fair.name)

    def test_a_register_needs_somebody_on_it(self):
        """Caixa sem gente é máquina, não caixa."""
        fair = self._feira_na_praca(10)
        with self.assertRaises(UserError):
            fair.action_open_pos()

    def test_opening_again_adds_only_what_is_missing(self):
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        primeiro = fair.pos_config_id
        self._operadores(fair, 'Joana')
        fair.action_open_pos()
        self.assertEqual(len(fair.pos_config_ids), 2)
        self.assertIn(primeiro, fair.pos_config_ids,
                      "O caixa que já existia não se refaz")

    def test_the_register_is_archived_when_the_fair_comes_back(self):
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        config = fair.pos_config_id
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 10
        dia.action_close()
        fair.action_return()
        self.assertFalse(config.active,
                         "Caixa de feira que voltou não fica na tela de quem "
                         "opera PDV todo dia")
        self.assertFalse(fair.pos_picking_type_id.active)


@tagged('post_install', '-at_install', 'liber_fairs_pos')
class TestDescontoDaFeira(TestCaixaDaFeira):
    """O desconto é do EVENTO, e quem digita número é o gerente.

    Duas chaves diferentes no PDV, e a diferença entre elas é a regra: o
    botão com o percentual da feira (qualquer um aperta) e a linha em branco
    onde se digita o que quiser (só gerente). Sem isso, ou ninguém dá
    desconto, ou todo mundo dá o que quiser.
    """

    def test_the_fair_discount_is_already_in_the_price(self):
        """O balcão mostra o preço COM desconto, sem ninguém apertar nada.

        Botão de desconto é outra coisa: alguém aperta, título a título. O
        desconto da feira é o preço que a feira pratica -- o cliente e quem
        vende têm de ver o número certo na tela.
        """
        fair = self._feira_na_praca(10)
        fair.discount_pc = 50.0
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        caixa = fair.pos_config_id

        self.assertTrue(caixa.use_pricelist)
        lista = caixa.pricelist_id
        self.assertTrue(lista, "O caixa tem de abrir com a lista da feira")
        self.assertEqual(lista.fair_id, fair)
        self.assertIn(lista, caixa.available_pricelist_ids)

        regra = lista.item_ids
        self.assertEqual(len(regra), 1)
        self.assertEqual(regra.applied_on, '3_global',
                         "Vale para todo o catálogo da mesa")
        self.assertEqual(regra.compute_price, 'percentage')
        self.assertEqual(regra.percent_price, 50.0)

        # e o preço sai pela metade
        preco = lista._get_product_price(self.livro, 1)
        self.assertEqual(preco, self.livro.list_price / 2)

    def test_changing_the_discount_changes_the_price(self):
        fair = self._feira_na_praca(10)
        fair.discount_pc = 50.0
        self._operadores(fair, 'Marta')
        fair.action_open_pos()

        fair.discount_pc = 20.0

        lista = fair.pos_config_id.pricelist_id
        self.assertEqual(lista.item_ids.percent_price, 20.0)
        self.assertEqual(lista._get_product_price(self.livro, 1),
                         self.livro.list_price * 0.8)

    def test_one_pricelist_per_fair_not_one_per_opening(self):
        fair = self._feira_na_praca(10)
        fair.discount_pc = 30.0
        self._operadores(fair, 'Marta', 'Joana')
        fair.action_open_pos()
        fair.action_open_pos()
        listas = self.env['product.pricelist'].search([('fair_id', '=', fair.id)])
        self.assertEqual(len(listas), 1,
                         "Uma lista por feira, e não uma por clique")
        self.assertEqual(
            set(fair.pos_config_ids.mapped('pricelist_id.id')),
            set(listas.ids),
            "Os dois caixas da feira vendem pela mesma lista")

    def test_the_operator_cannot_type_a_discount(self):
        fair = self._feira_na_praca(10)
        fair.discount_pc = 15.0
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        self.assertFalse(fair.pos_config_id.manual_discount,
                         "Assistente não digita desconto: o preço já vem "
                         "com o da feira")

    def test_the_manager_may_type_one(self):
        fair = self._feira_na_praca(10)
        fair.discount_pc = 15.0
        self._operadores(fair, 'Marta')
        fair.cashier_ids.role = 'manager'
        fair.action_open_pos()
        self.assertTrue(fair.pos_config_id.manual_discount)

    def test_changing_the_role_changes_the_key(self):
        fair = self._feira_na_praca(10)
        fair.discount_pc = 10.0
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        self.assertFalse(fair.pos_config_id.manual_discount)

        fair.cashier_ids.role = 'manager'

        self.assertTrue(fair.pos_config_id.manual_discount,
                        "Promovido, passa a poder digitar")

    def test_changing_the_fair_discount_reaches_the_open_registers(self):
        fair = self._feira_na_praca(10)
        fair.discount_pc = 10.0
        self._operadores(fair, 'Marta')
        fair.action_open_pos()

        fair.discount_pc = 25.0

        self.assertEqual(fair.pos_config_id.pricelist_id.item_ids.percent_price,
                         25.0)

    def test_no_discount_no_pricelist(self):
        """Feira sem desconto vende pelo preço de tabela, e ponto."""
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        self.assertFalse(fair.pos_config_id.use_pricelist)
        self.assertFalse(
            self.env['product.pricelist'].search([('fair_id', '=', fair.id)]))
        self.assertFalse(fair.pos_config_id.manual_discount)


@tagged('post_install', '-at_install', 'liber_fairs_pos')
class TestCaixaDeCadaUm(TestCaixaDaFeira):
    """Cada um abre o caixa DELE, e o balcão mostra a mesa.

    Duas coisas que a pessoa contratada para três dias precisa: não abrir a
    tela numa lista de caixas que não são dela, e ver quantos exemplares
    ainda há na mesa sem ter de contar a pilha com fila na frente.
    """

    def _com_conta(self, fair, nome, role='operator'):
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': nome, 'login': nome.lower().replace(' ', '_'),
                'password': nome.lower().replace(' ', '_'),
                'company_id': self.company.id,
                'company_ids': [(6, 0, [self.company.id])],
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        linha = self.env['event.fair.cashier'].create({
            'fair_id': fair.id, 'partner_id': usuario.partner_id.id,
            'role': role})
        return usuario, linha

    def test_each_operator_only_sees_their_own_register(self):
        fair = self._feira_na_praca(10)
        marta, linha_marta = self._com_conta(fair, 'Marta Balcao')
        joana, _l = self._com_conta(fair, 'Joana Balcao')
        fair.action_plan() if fair.state == 'draft' else None
        fair.action_open_pos()
        self.env.invalidate_all()

        visiveis = self.env['pos.config'].with_user(marta).search([])
        self.assertEqual(len(visiveis), 1,
                         "Ela abre o caixa DELA, e só. Veio: %s"
                         % visiveis.mapped('name'))
        self.assertEqual(visiveis, linha_marta.pos_config_id)
        self.assertEqual(visiveis.fair_cashier_id, linha_marta)

    def test_the_house_registers_are_not_hers(self):
        """Quem foi contratado para a feira não vê a loja da casa."""
        loja = self.env['pos.config'].create({
            'name': 'Loja da casa', 'company_id': self.company.id})
        fair = self._feira_na_praca(10)
        marta, _l = self._com_conta(fair, 'Marta Só Feira')
        fair.action_open_pos()
        self.env.invalidate_all()
        visiveis = self.env['pos.config'].with_user(marta).search([])
        self.assertNotIn(loja, visiveis)

    def test_the_counter_knows_what_is_on_the_table(self):
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        local = fair.stock_location_id

        template = self.livro.product_tmpl_id.with_context(
            fair_location_id=local.id)
        self.assertEqual(template.fair_qty, 10,
                         "Dez exemplares chegaram na mesa")

        self._venda(fair, 3)
        template.invalidate_recordset()
        self.assertEqual(template.fair_qty, 7,
                         "Vendeu três: a mesa tem sete")

    def test_outside_a_fair_the_number_does_not_exist(self):
        """O balcão da loja da casa não ganha etiqueta nenhuma."""
        template = self.livro.product_tmpl_id
        self.assertEqual(template.fair_qty, 0.0)

    def test_the_field_travels_with_the_products(self):
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        campos = self.env['product.template']._load_pos_data_fields(
            fair.pos_config_id)
        self.assertIn('fair_qty', campos,
                      "Sem viajar no carregamento, o balcão não tem o número")

    def test_the_table_is_read_live(self):
        """A MESA AO VIVO, que é o que o cartão mostra.

        O número não pode vir só no carregamento do produto: o balcão guarda
        produto no navegador e só rebusca quando o produto muda -- e mover
        caixa de livro não escreve nada no produto. Quem abriu o caixa antes
        de a mercadoria chegar ficava com zero para sempre.
        """
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        sessao = self.env['pos.session'].create({
            'config_id': fair.pos_config_id.id, 'user_id': self.env.user.id})
        sessao.action_pos_session_open()
        modelo = self.livro.product_tmpl_id.id

        mesa = sessao.get_fair_shelf_qty()
        self.assertEqual(mesa.get(modelo), 10,
                         "Dez exemplares chegaram na mesa")

        self._venda(fair, 3, sessao=sessao)
        mesa = sessao.get_fair_shelf_qty()
        self.assertEqual(mesa.get(modelo), 7,
                         "Vendeu tres: a leitura seguinte tem de dizer sete")

    def test_the_house_register_has_no_table(self):
        """Caixa que nao e de feira nao tem mesa nenhuma -- e nao da erro."""
        loja = self.env['pos.config'].create({
            'name': 'Loja da casa', 'company_id': self.company.id})
        sessao = self.env['pos.session'].create({
            'config_id': loja.id, 'user_id': self.env.user.id})
        self.assertEqual(sessao.get_fair_shelf_qty(), {})

    def test_the_register_actually_loads(self):
        """O CARREGAMENTO INTEIRO, e não só a lista de campos.

        Escrito depois de o balcão morrer na abertura com "load_data() got an
        unexpected keyword argument": a sobrescrita do carregamento tinha
        inventado um parâmetro que o núcleo não tem, e a suíte inteira passou
        verde porque ninguém CHAMAVA o carregamento. Conferir a lista de
        campos não é conferir que o caixa abre.
        """
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        sessao = self.env['pos.session'].create({
            'config_id': fair.pos_config_id.id, 'user_id': self.env.user.id})
        sessao.action_pos_session_open()

        dados = sessao.load_data([])

        self.assertTrue(dados, "O balcão não carregou nada")
        self.assertIn('pos.config', dados,
                      "Sem a configuração o cliente morre lendo currency_id")
        produtos = dados.get('product.template') or []
        self.assertTrue(produtos, "Nenhum título chegou ao balcão")
        self.assertIn('fair_qty', produtos[0],
                      "E a quantidade da mesa tem de vir junto")

        # E a configuração inteira, que é de onde o cliente lê a moeda e o
        # desconto. Pedir "só este campo" aqui derruba o balcão no
        # `use_pricelist` que o próprio núcleo lê depois.
        config = dados['pos.config'][0]
        self.assertIn('use_pricelist', config,
                      "A configuração tem de vir inteira")
        self.assertIn('fair_discount_pc', config,
                      "Inclusive o desconto, que o cartão usa para o de-por")

    def test_deleting_a_fair_does_not_blow_up_on_the_register(self):
        """Apagar uma feira não pode dar erro de banco na cara de ninguém.

        O caixa, a lista de preços e o tipo de operação apontam para a feira
        para o histórico não morrer com ela. A chave estrangeira, porém,
        nasceu sem SET NULL, e apagar dava "violates foreign key constraint".
        """
        fair = self._feira_na_praca(10)
        fair.discount_pc = 20.0
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        caixa = fair.pos_config_id
        lista = caixa.pricelist_id
        self.assertTrue(caixa and lista)

        fair.picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel')).action_cancel()
        fair.day_ids.unlink()
        fair.unlink()

        self.assertTrue(caixa.exists(), "O caixa sobrevive, com a venda dele")
        self.assertFalse(caixa.fair_id)
        self.assertFalse(caixa.fair_cashier_id)
        self.assertFalse(lista.fair_id)
