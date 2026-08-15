# -*- coding: utf-8 -*-
"""A cotação — e a linha que o módulo promete não cruzar."""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AmazonVendorCase, amazon_item, amazon_order


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAmazonQuotation(AmazonVendorCase):

    def _imported(self, name, items, **kwargs):
        self._sync([amazon_order(name, items, **kwargs)])
        return self._order(name)

    # ------------------------------------------------------- caminho feliz

    def test_quotation_carries_lines_and_prices(self):
        """A cotação nasce com o NOSSO preço de capa (decisão de
        11/08/2026), não com o Net Cost da Amazon — assim a lista de
        preços aplica o desconto interno e tudo segue pelo padrão. O
        valor da Amazon continua no espelho da PO."""
        order = self._imported('BR-1000', [
            amazon_item('1', '9786551590016', qty=30, net_cost='45.50'),
            amazon_item('2', '9786551590085', qty=12, net_cost='40.00'),
        ])
        order.action_create_quotation()

        quotation = order.sale_order_id
        self.assertEqual(quotation.partner_id, self.partner_amazon)
        self.assertEqual(len(quotation.order_line), 2)
        self.assertEqual(quotation.client_order_ref, 'BR-1000')

        line = quotation.order_line.filtered(
            lambda l: l.product_id == self.book_a)
        self.assertAlmostEqual(line.product_uom_qty, 30, places=2)
        # preço de capa do catálogo, não os 45,50 da Amazon
        self.assertAlmostEqual(line.price_unit, 89.90, places=2)
        self.assertNotAlmostEqual(line.price_unit, 45.50, places=2)
        # e o espelho da PO guarda o valor da Amazon, intacto
        mirror = order.line_ids.filtered(
            lambda l: l.product_id == self.book_a)
        self.assertAlmostEqual(mirror.price_unit, 45.50, places=2)

    def test_quotation_is_never_confirmed(self):
        """
        O coração da restrição. Confirmar assume compromisso de entrega e
        move estoque; isso é decisão de gente. Se algum dia alguém acrescentar
        um `action_confirm` por conveniência, este teste cai.
        """
        order = self._imported('BR-1001', [amazon_item('1', '9786551590016')])
        order.action_create_quotation()

        quotation = order.sale_order_id
        self.assertEqual(quotation.state, 'draft')
        self.assertFalse(quotation.invoice_ids)
        # 'no' é o que o Odoo diz de um pedido que ainda não prometeu nada.
        # Entregas não são checadas aqui porque `stock` pode não estar
        # instalado, e um teste que depende de módulo alheio falha por motivo
        # errado -- mas 'draft' já garante que nenhuma foi gerada.
        self.assertEqual(quotation.invoice_status, 'no')

    def test_order_state_becomes_quoted(self):
        order = self._imported('BR-1002', [amazon_item('1', '9786551590016')])
        self.assertEqual(order.state, 'imported')
        order.action_create_quotation()
        self.assertEqual(order.state, 'quoted')

    def test_quotation_links_back(self):
        order = self._imported('BR-1003', [amazon_item('1', '9786551590016')])
        order.action_create_quotation()
        self.assertIn(order, order.sale_order_id.amazon_order_ids)

    def test_delivery_deadline_becomes_commitment_date(self):
        order = self._imported('BR-1004', [amazon_item('1', '9786551590016')])
        order.action_create_quotation()
        self.assertEqual(str(order.sale_order_id.commitment_date),
                         '2026-07-20 00:00:00')

    # --------------------------------------------------------- recusas

    def test_unmatched_line_is_ignored_not_blocking(self):
        """
        Título sem produto no cadastro não trava o pedido: fica de fora e a
        cotação sai com o resto. Travar seria pior — o pedido inteiro pararia
        por causa de um título que talvez nem seja nosso, e a Amazon não
        espera.
        """
        order = self._imported('BR-1010', [
            amazon_item('1', '9786551590016'),
            amazon_item('2', '9788500000009'),
        ])
        order.action_create_quotation()

        self.assertTrue(order.sale_order_id)
        self.assertEqual(len(order.sale_order_id.order_line), 1)
        self.assertEqual(order.sale_order_id.order_line.product_id, self.book_a)

    def test_what_was_ignored_is_written_down(self):
        """
        Ignorar é a decisão certa; ignorar em silêncio não é. A cotação
        promete menos exemplares do que a Amazon pediu, e a diferença só
        apareceria na entrega.
        """
        order = self._imported('BR-1011', [
            amazon_item('1', '9786551590016'),
            amazon_item('2', '9788500000009'),
        ])
        order.action_create_quotation()

        historico = "\n".join(order.message_ids.mapped('body'))
        self.assertIn('9788500000009', historico)
        self.assertIn(order.sale_order_id.name, historico)
        # e o contador continua visível na lista
        self.assertEqual(order.unmatched_count, 1)

    def test_closed_order_is_refused(self):
        """
        A Amazon fechou: entregue, cancelado ou expirado. Cotar agora criaria
        compromisso comercial para uma janela que não existe mais — e, no
        histórico importado, prometeria de novo o que já saiu pelo portal.
        """
        order = self._imported('BR-1020', [amazon_item('1', '9786551590016')],
                               state='Closed')
        self.assertFalse(order.is_open)
        with self.assertRaises(UserError) as caught:
            order.action_create_quotation()
        self.assertIn('BR-1020', str(caught.exception))
        self.assertFalse(order.sale_order_id)

    def test_closing_after_the_quotation_does_not_undo_it(self):
        """O que já virou cotação continua valendo: o bloqueio é para criar."""
        order = self._imported('BR-1021', [amazon_item('1', '9786551590016')])
        order.action_create_quotation()
        cotacao = order.sale_order_id

        self._sync([amazon_order('BR-1021', [amazon_item('1', '9786551590016')],
                                 state='Closed')])
        self.assertEqual(self._order('BR-1021').sale_order_id, cotacao)

    def test_bulk_skips_closed_orders(self):
        aberto = self._imported('BR-1022', [amazon_item('1', '9786551590016')])
        fechado = self._imported('BR-1023', [amazon_item('1', '9786551590016')],
                                 state='Closed')

        resultado = (aberto | fechado).action_create_quotations_bulk()

        self.assertTrue(aberto.sale_order_id)
        self.assertFalse(fechado.sale_order_id)
        self.assertIn('BR-1023', resultado['params']['message'])

    def test_second_quotation_is_refused(self):
        order = self._imported('BR-1012', [amazon_item('1', '9786551590016')])
        order.action_create_quotation()
        with self.assertRaises(UserError):
            order.action_create_quotation()

    def test_unmapped_unit_is_refused_and_names_the_code(self):
        """
        Cair no cliente da conta seria pior do que recusar: cada galpão da
        Amazon é um estabelecimento fiscal com CNPJ próprio, e a nota sairia
        contra o errado — em silêncio, com número plausível.
        """
        self.unit.unlink()
        order = self._imported('BR-1013', [amazon_item('1', '9786551590016')])
        self.assertFalse(order.unit_mapped)
        self.assertFalse(order.partner_id)

        with self.assertRaises(UserError) as caught:
            order.action_create_quotation()
        self.assertIn('AMZN_BR', str(caught.exception))

    def test_mapping_the_unit_afterwards_fixes_the_order(self):
        """
        O campo do pedido não tem como depender do mapa. Sem o empurrão de
        recálculo, mapear hoje não consertaria o pedido de ontem — ele ficaria
        sem cliente e ninguém entenderia por quê.
        """
        self.unit.unlink()
        order = self._imported('BR-1016', [amazon_item('1', '9786551590016')])
        self.assertFalse(order.partner_id)

        self.env['liber.amazon.unit'].create({
            'account_id': self.account.id,
            'code': 'AMZN_BR',
            'partner_id': self.partner_amazon.id,
        })
        self.assertEqual(order.partner_id, self.partner_amazon)
        order.action_create_quotation()
        self.assertEqual(order.sale_order_id.partner_id, self.partner_amazon)

    def test_the_unit_decides_the_customer_not_the_account(self):
        """Dois galpões, dois clientes — que é o ponto do mapa."""
        outro = self.env['res.partner'].create({'name': 'Amazon GIG1'})
        self.env['liber.amazon.unit'].create({
            'account_id': self.account.id, 'code': 'GIG1',
            'partner_id': outro.id})

        pedido = amazon_order('BR-1017', [amazon_item('1', '9786551590016')])
        pedido['orderDetails']['buyingParty'] = {'partyId': 'GIG1'}
        self._sync([pedido])

        order = self._order('BR-1017')
        self.assertEqual(order.partner_id, outro)
        order.action_create_quotation()
        self.assertEqual(order.sale_order_id.partner_id, outro)

    def test_delivery_address_comes_from_the_unit(self):
        entrega = self.env['res.partner'].create({
            'name': 'CD Cajamar', 'type': 'delivery',
            'parent_id': self.partner_amazon.id})
        self.unit.shipping_partner_id = entrega

        order = self._imported('BR-1018', [amazon_item('1', '9786551590016')])
        order.action_create_quotation()
        self.assertEqual(order.sale_order_id.partner_shipping_id, entrega)

    def test_account_customer_is_only_for_orders_without_a_unit(self):
        pedido = amazon_order('BR-1019', [amazon_item('1', '9786551590016')])
        del pedido['orderDetails']['buyingParty']
        self._sync([pedido])

        order = self._order('BR-1019')
        self.assertTrue(order.unit_mapped, "sem sigla não há o que mapear")
        self.assertEqual(order.partner_id, self.account.partner_id)

    def test_foreign_currency_is_refused(self):
        """
        Converter caladamente seria pior do que falhar: o pedido entraria com
        número plausível e errado, e ninguém procura erro em documento que
        parece certo.
        """
        foreign = 'USD' if self.currency_name != 'USD' else 'EUR'
        order = self._imported('BR-1014', [
            amazon_item('1', '9786551590016', currency=foreign),
        ])
        with self.assertRaises(UserError) as caught:
            order.action_create_quotation()
        self.assertIn(foreign, str(caught.exception))

    def test_order_with_no_usable_line_is_refused(self):
        """
        Aqui ainda se recusa: não há o que cotar. Criar uma cotação vazia
        registraria uma venda de nada.
        """
        order = self._imported('BR-1015', [amazon_item('1', '9788500000009')])
        with self.assertRaises(UserError):
            order.action_create_quotation()


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAmazonBulkQuotation(AmazonVendorCase):
    """A ação em massa: gera o que dá, pula o que não dá, e conta o que houve."""

    def _imported(self, name, items, **kwargs):
        self._sync([amazon_order(name, items, **kwargs)])
        return self._order(name)

    def test_bulk_creates_for_every_ready_order(self):
        ordens = self.env['liber.amazon.order']
        for n in range(3):
            ordens |= self._imported('BR-30%02d' % n, [
                amazon_item('1', '9786551590016', qty=5)])

        ordens.action_create_quotations_bulk()

        self.assertEqual(len(ordens.mapped('sale_order_id')), 3)
        for ordem in ordens:
            self.assertEqual(ordem.sale_order_id.state, 'draft')

    def test_bulk_skips_instead_of_dying_on_the_first_problem(self):
        """
        No formulário, falhar é a resposta certa. Numa seleção de cinquenta,
        levantar exceção no terceiro joga fora o trabalho dos outros
        quarenta e sete -- e não diz o que aconteceu.

        O que ainda pula: pedido que já tem cotação, ou que não tem nenhuma
        linha aproveitável. Linha sem produto, não — essa é ignorada.
        """
        boa = self._imported('BR-3100', [amazon_item('1', '9786551590016')])
        vazia = self._imported('BR-3101', [amazon_item('1', '9788500000009')])
        outra_boa = self._imported('BR-3102', [amazon_item('1', '9786551590085')])

        resultado = (boa | vazia | outra_boa).action_create_quotations_bulk()

        self.assertTrue(boa.sale_order_id)
        self.assertTrue(outra_boa.sale_order_id)
        self.assertFalse(vazia.sale_order_id, "sem linha aproveitável não cota")
        mensagem = resultado['params']['message']
        self.assertIn('BR-3101', mensagem)
        self.assertNotIn('BR-3100', mensagem, "os que deram certo não entram")

    def test_bulk_creates_for_orders_with_some_unmatched_lines(self):
        """Uma linha órfã não pode custar a cotação das outras trinta."""
        mista = self._imported('BR-3150', [
            amazon_item('1', '9786551590016'),
            amazon_item('2', '9788500000009'),
        ])
        resultado = mista.action_create_quotations_bulk()

        self.assertTrue(mista.sale_order_id)
        self.assertEqual(len(mista.sale_order_id.order_line), 1)
        self.assertIn('left out', resultado['params']['message'])

    def test_bulk_skips_what_already_has_a_quotation(self):
        ordem = self._imported('BR-3200', [amazon_item('1', '9786551590016')])
        ordem.action_create_quotation()
        primeira = ordem.sale_order_id

        ordem.action_create_quotations_bulk()

        self.assertEqual(ordem.sale_order_id, primeira,
                         "a cotação existente não pode ser trocada por outra")
        self.assertEqual(self.env['sale.order'].search_count(
            [('client_order_ref', '=', 'BR-3200')]), 1)

    def test_bulk_report_is_sticky_when_something_was_skipped(self):
        """Relatório que some antes de ser lido não é relatório."""
        vazia = self._imported('BR-3300', [amazon_item('1', '9788500000009')])
        resultado = vazia.action_create_quotations_bulk()
        self.assertTrue(resultado['params']['sticky'])
        self.assertEqual(resultado['params']['type'], 'warning')

    def test_bulk_on_a_clean_run_says_nothing_was_confirmed(self):
        ordem = self._imported('BR-3400', [amazon_item('1', '9786551590016')])
        resultado = ordem.action_create_quotations_bulk()
        self.assertEqual(resultado['params']['type'], 'success')
        self.assertFalse(resultado['params']['sticky'])
        self.assertIn('confirmed', resultado['params']['message'].lower())

    def test_bulk_on_empty_selection(self):
        resultado = self.env['liber.amazon.order'].action_create_quotations_bulk()
        self.assertIn('Nothing', resultado['params']['message'])

    def test_blockers_are_the_same_rules_for_both_paths(self):
        """
        A regra vive num lugar só. Se um dia o botão recusar o que a lista
        aceita, este teste cai antes de um pedido sair errado.
        """
        vazia = self._imported('BR-3500', [amazon_item('1', '9788500000009')])
        blockers = vazia._quotation_blockers()
        self.assertTrue(blockers)
        with self.assertRaises(UserError) as caught:
            vazia.action_create_quotation()
        self.assertIn(blockers[0].split('\n')[0], str(caught.exception))
