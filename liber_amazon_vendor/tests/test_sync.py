# -*- coding: utf-8 -*-
"""A importação: o que grava, o que reescreve e o que se recusa a reescrever."""

from odoo.tests import tagged

from .common import AmazonVendorCase, amazon_item, amazon_order


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAmazonSync(AmazonVendorCase):

    # ------------------------------------------------------- caminho feliz

    def test_import_creates_order_and_lines(self):
        result = self._sync([amazon_order('BR-0001', [
            amazon_item('1', '9786551590016', qty=30, net_cost='45.50'),
            amazon_item('2', '9786551590085', qty=12, net_cost='40.00'),
        ])])

        self.assertEqual(result['created'], 1)
        order = self._order('BR-0001')
        self.assertEqual(order.amazon_state, 'Acknowledged')
        self.assertTrue(order.state_known)
        self.assertTrue(order.is_open)
        self.assertEqual(order.line_count, 2)
        self.assertEqual(order.state, 'imported')
        self.assertFalse(order.sale_order_id)
        # 30 × 45,50 + 12 × 40,00
        self.assertAlmostEqual(order.amount_total, 1845.0, places=2)

    def test_isbn_matches_product_by_barcode(self):
        self._sync([amazon_order('BR-0002', [
            amazon_item('1', '9786551590016'),
        ])])
        line = self._order('BR-0002').line_ids
        self.assertEqual(line.product_id, self.book_a)
        self.assertTrue(line.matched)

    def test_hyphenated_barcode_still_matches(self):
        """O catálogo real tem barcode com hífen. A Amazon manda sem.

        Sem normalizar dos dois lados, o título cadastrado apareceria como
        ausente -- e o relatório mandaria cadastrar o que já existe.
        """
        self._sync([amazon_order('BR-0003', [
            amazon_item('1', '9786551590085'),
        ])])
        self.assertEqual(self._order('BR-0003').line_ids.product_id, self.book_b)

    def test_delivery_window_is_split(self):
        self._sync([amazon_order('BR-0004', [amazon_item('1', '9786551590016')])])
        order = self._order('BR-0004')
        self.assertEqual(str(order.delivery_start), '2026-07-10 00:00:00')
        self.assertEqual(str(order.delivery_end), '2026-07-20 00:00:00')

    def test_net_cost_is_the_price_not_list_price(self):
        """netCost é o que a Amazon paga; listPrice é a etiqueta dela.

        Trocar os dois infla a receita do pedido inteiro e só aparece no
        fechamento do mês.
        """
        self._sync([amazon_order('BR-0005', [
            amazon_item('1', '9786551590016', qty=1,
                        net_cost='45.50', list_price='89.90'),
        ])])
        line = self._order('BR-0005').line_ids
        self.assertAlmostEqual(line.price_unit, 45.50, places=2)
        self.assertAlmostEqual(line.list_price, 89.90, places=2)

    # ----------------------------------------------------------- reimportar

    def test_reimport_does_not_duplicate(self):
        """A janela de leitura recua de propósito: sobreposição é a regra."""
        payload = [amazon_order('BR-0010', [amazon_item('1', '9786551590016')])]
        first = self._sync(payload)
        second = self._sync(payload)

        self.assertEqual(first['created'], 1)
        self.assertEqual(second['created'], 0)
        self.assertEqual(second['updated'], 1)
        self.assertEqual(len(self._order('BR-0010')), 1)
        self.assertEqual(self._order('BR-0010').line_count, 1)

    def test_reimport_updates_state(self):
        """Amazon muda o estado depois de criado; o espelho tem de acompanhar."""
        self._sync([amazon_order('BR-0011', [amazon_item('1', '9786551590016')],
                                 state='New')])
        self.assertEqual(self._order('BR-0011').amazon_state, 'New')

        self._sync([amazon_order('BR-0011', [amazon_item('1', '9786551590016')],
                                 state='Closed')])
        order = self._order('BR-0011')
        self.assertEqual(order.amazon_state, 'Closed')
        self.assertFalse(order.is_open)

    def test_manual_product_survives_reimport(self):
        """Correção humana não pode ser desfeita pela próxima leitura."""
        self._sync([amazon_order('BR-0012', [
            amazon_item('1', '9788500000009'),  # fora do cadastro
        ])])
        line = self._order('BR-0012').line_ids
        self.assertFalse(line.product_id)

        line.product_id = self.book_a          # alguém resolve à mão
        self.assertTrue(line.product_locked)

        self._sync([amazon_order('BR-0012', [amazon_item('1', '9788500000009')])])
        self.assertEqual(self._order('BR-0012').line_ids.product_id, self.book_a)

    # -------------------------------------------------------------- avisos

    def test_unknown_state_is_imported_not_rejected(self):
        """O agregador anterior levantava exceção aqui e perdia o pedido.

        Estado novo na Amazon é notícia, não motivo para descartar uma venda.
        """
        self._sync([amazon_order('BR-0020', [amazon_item('1', '9786551590016')],
                                 state='Rejected')])
        order = self._order('BR-0020')
        self.assertTrue(order, "o pedido tem de existir mesmo com estado novo")
        self.assertEqual(order.amazon_state, 'Rejected')
        self.assertFalse(order.state_known)
        self.assertFalse(order.is_open)

    def test_unmatched_isbn_is_counted_not_fatal(self):
        self._sync([amazon_order('BR-0021', [
            amazon_item('1', '9786551590016'),
            amazon_item('2', '9788500000009'),
        ])])
        order = self._order('BR-0021')
        self.assertEqual(order.line_count, 2)
        self.assertEqual(order.unmatched_count, 1)

    # ---------------------------------------------------------- divergência

    def test_change_after_quotation_is_flagged_not_applied(self):
        """
        A Amazon aceita pedido parcial, e a quantidade confirmada raramente é
        a pedida. Depois que existe cotação, quantidade que muda é problema de
        alguém -- e o módulo avisa em vez de reescrever um documento que uma
        pessoa fez.
        """
        self._sync([amazon_order('BR-0030', [
            amazon_item('1', '9786551590016', qty=100),
        ])])
        order = self._order('BR-0030')
        order.action_create_quotation()
        self.assertTrue(order.sale_order_id)

        self._sync([amazon_order('BR-0030', [
            amazon_item('1', '9786551590016', qty=60),
        ], state='Closed')])

        order = self._order('BR-0030')
        self.assertTrue(order.has_divergence)
        self.assertIn('100', order.divergence_note)
        self.assertIn('60', order.divergence_note)
        # A cotação continua intacta: ninguém reescreveu por baixo.
        self.assertAlmostEqual(
            order.sale_order_id.order_line.product_uom_qty, 100, places=2)

    def test_a_huge_divergence_stays_readable(self):
        """
        Um pedido grande que a Amazon reduz produz um aviso por linha. Sem
        teto, o alerta vira um paredão que ninguém lê — e deixa de avisar
        justamente quando havia mais o que dizer.
        """
        muitas = [amazon_item(str(n), '9786551590016', qty=n + 1)
                  for n in range(1, 60)]
        self._sync([amazon_order('BR-0035', muitas)])
        ordem = self._order('BR-0035')
        ordem.action_create_quotation()

        # a Amazon devolve o pedido com uma linha só
        self._sync([amazon_order('BR-0035', [
            amazon_item('1', '9786551590016', qty=1)])])

        nota = self._order('BR-0035').divergence_note
        self.assertIn('59', nota, "o total precisa aparecer por inteiro")
        self.assertLessEqual(nota.count('\n- '), 21,
                             "a nota passou de vinte itens e ficou ilegível")

    def test_change_before_quotation_is_not_a_divergence(self):
        """Sem cotação, mudança é só notícia: o espelho se atualiza e pronto."""
        self._sync([amazon_order('BR-0031', [
            amazon_item('1', '9786551590016', qty=100)])])
        self._sync([amazon_order('BR-0031', [
            amazon_item('1', '9786551590016', qty=60)])])

        order = self._order('BR-0031')
        self.assertFalse(order.has_divergence)
        self.assertAlmostEqual(order.line_ids.quantity, 60, places=2)

    def test_acknowledging_divergence_clears_the_flag(self):
        self._sync([amazon_order('BR-0032', [
            amazon_item('1', '9786551590016', qty=100)])])
        order = self._order('BR-0032')
        order.action_create_quotation()
        self._sync([amazon_order('BR-0032', [
            amazon_item('1', '9786551590016', qty=60)])])

        order = self._order('BR-0032')
        self.assertTrue(order.has_divergence)
        order.action_clear_divergence()
        self.assertFalse(order.has_divergence)

    # ----------------------------------------------------------- edge cases

    def test_order_without_delivery_window(self):
        """Pedido sem janela ainda é pedido. Não pode derrubar a importação."""
        self._sync([amazon_order('BR-0040', [amazon_item('1', '9786551590016')],
                                 window=None)])
        order = self._order('BR-0040')
        self.assertTrue(order)
        self.assertFalse(order.delivery_start)

    def test_line_without_price(self):
        self._sync([amazon_order('BR-0041', [
            amazon_item('1', '9786551590016', qty=5, net_cost=None),
        ])])
        order = self._order('BR-0041')
        self.assertAlmostEqual(order.amount_total, 0.0, places=2)

    def test_order_without_items(self):
        self._sync([amazon_order('BR-0042', [])])
        order = self._order('BR-0042')
        self.assertTrue(order)
        self.assertEqual(order.line_count, 0)

    def test_order_without_number_is_skipped(self):
        """Sem PO number não há chave: gravar criaria um registro anônimo
        que a próxima leitura duplicaria."""
        result = self._sync([amazon_order('', [amazon_item('1', '9786551590016')])])
        self.assertEqual(result['created'], 0)


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAmazonMenus(AmazonVendorCase):
    """A estrutura do app: onde cada coisa é alcançada."""

    def test_import_button_is_always_visible_on_the_order_list(self):
        """
        Sem `display="always"` o botão cai no bloco de ações de seleção, que o
        Odoo só mostra quando há linhas marcadas — e sumiria justamente na
        primeira importação, com a lista vazia. O erro não daria exceção
        nenhuma: só um botão que ninguém acha.
        """
        from lxml import etree

        view = self.env.ref('liber_amazon_vendor.view_liber_amazon_order_list')
        arch = etree.fromstring(view.arch)
        botoes = arch.xpath('//header/button')

        self.assertEqual(len(botoes), 1, "a lista de Pedidos tem um botão só")
        self.assertEqual(botoes[0].get('display'), 'always')
        self.assertEqual(botoes[0].get('type'), 'action')

    def test_orders_cannot_be_created_by_hand(self):
        """
        O espelho tem uma porta de entrada só: a importação. Um registro
        criado à mão não corresponde a pedido nenhum na Amazon, e a próxima
        releitura não saberia o que fazer com ele.
        """
        from lxml import etree

        for xmlid in ('view_liber_amazon_order_list',
                      'view_liber_amazon_order_form',
                      'view_liber_amazon_schedule_list'):
            view = self.env.ref('liber_amazon_vendor.%s' % xmlid)
            raiz = etree.fromstring(view.arch)
            self.assertEqual(raiz.get('create'), 'false',
                             "%s deixaria criar pedido à mão" % xmlid)

    def test_the_import_menu_entry_is_gone(self):
        """A importação mora na lista de Pedidos, não num menu à parte."""
        self.assertFalse(self.env.ref(
            'liber_amazon_vendor.menu_liber_amazon_import',
            raise_if_not_found=False))

    def test_the_app_has_the_three_entries_and_configuration(self):
        raiz = self.env.ref('liber_amazon_vendor.menu_liber_amazon_root')
        filhos = raiz.child_id.sorted('sequence').mapped('name')
        self.assertEqual(filhos, ['Orders', 'Schedule', 'Report',
                                  'Configuration'])

    def test_action_names_match_the_menus(self):
        """
        O rastro de navegação mostra o nome da AÇÃO, não o do menu. Renomear
        um sem o outro deixa a tela dizendo "Pedidos" no menu e "Pedidos de
        compra da Amazon" na trilha logo acima — dois nomes para o mesmo
        lugar, e nenhum erro para denunciar.
        """
        raiz = self.env.ref('liber_amazon_vendor.menu_liber_amazon_root')
        menus = self.env['ir.ui.menu'].search(
            [('id', 'child_of', raiz.id), ('action', '!=', False)])
        self.assertTrue(menus, "o app precisa ter menus com ação")

        for menu in menus:
            acao = menu.action
            self.assertEqual(
                menu.name, acao.name,
                "menu '%s' e ação '%s' nomeiam o mesmo lugar de dois jeitos"
                % (menu.name, acao.name))

    def test_amazon_state_is_shown_translated_but_kept_raw(self):
        """
        O valor cru precisa sobreviver — é a chave das decorações, dos
        filtros e do agrupamento, e é o que a Amazon de fato disse. O que
        muda é só a exibição.
        """
        self._sync([amazon_order('BR-0050', [amazon_item('1', '9786551590016')],
                                 state='Acknowledged')])
        ordem = self._order('BR-0050')
        self.assertEqual(ordem.amazon_state, 'Acknowledged')
        self.assertEqual(ordem.amazon_state_label, 'Acknowledged')

        # e um estado que a Amazon invente passa adiante como veio
        self._sync([amazon_order('BR-0051', [amazon_item('1', '9786551590016')],
                                 state='PartiallyShipped')])
        outra = self._order('BR-0051')
        self.assertEqual(outra.amazon_state_label, 'PartiallyShipped')

    def test_every_badge_carries_colour(self):
        """
        Badge sem decoração sai cinza — e cinza não diz nada. O widget cai em
        `text-bg-300` quando nenhuma condição casa, então esquecer a decoração
        não dá erro: dá uma tela morta que parece pronta.
        """
        from lxml import etree

        esperado = {
            'view_liber_amazon_order_list': ('state', 'amazon_state_label'),
            'view_liber_amazon_schedule_list': ('state', 'amazon_state_label'),
            'view_liber_amazon_title_list': ('outcome', 'fulfilment_state',
                                             'amazon_state_label'),
        }
        for xmlid, campos in esperado.items():
            arch = etree.fromstring(
                self.env.ref('liber_amazon_vendor.%s' % xmlid).arch)
            for campo in campos:
                no = arch.xpath('//field[@name="%s"][@widget="badge"]' % campo)
                self.assertTrue(no, '%s: %s não é badge' % (xmlid, campo))
                decoracoes = [a for a in no[0].attrib
                              if a.startswith('decoration-')]
                self.assertTrue(
                    decoracoes,
                    '%s: o badge de %s sairia cinza' % (xmlid, campo))
