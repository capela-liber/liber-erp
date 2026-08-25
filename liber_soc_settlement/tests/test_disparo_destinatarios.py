# -*- coding: utf-8 -*-
"""Quem recebe o quê, na consignação.

São duas pessoas diferentes na mesma livraria, e até 25/08/2026 a casa não
tinha onde dizer quem era quem: tudo ia para a caixa geral. Agora há dois
papéis na ficha de endereço — Acertos e Comprador — e o papel vai para quem
tem o que fazer com ele:

    CO só com a prateleira (o disparo mensal)     -> Acertos
    CO com acerto e/ou devolução                  -> Acertos
    CO só com reposição                           -> Comprador
    CO mista                                      -> os dois
    Pedido C avulso, ao confirmar                 -> Comprador, com o PDF

Quem confere prateleira não autoriza compra, e quem autoriza compra não quer o
extrato do que não girou. Mandar tudo para os dois seria treinar os dois a não
ler — que é o mesmo que não mandar.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'soc_map_schedule')
class TestDisparoDestinatarios(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.product = cls.env['product.product'].create({
            'name': 'Livro do Disparo', 'type': 'consu',
            'is_storable': True, 'list_price': 80.0})
        cls.vendedora = cls.env['res.users'].create({
            'name': 'Vendedora do Disparo',
            'login': 'vendedora.disparo@teste.com'})

    def _livraria(self, nome, com_acertos=True, com_comprador=True):
        partner = self.env['res.partner'].create({
            'name': nome, 'is_company': True,
            'email': 'geral@%s.com.br' % nome.replace(' ', ''),
            'user_id': self.vendedora.id})
        if com_acertos:
            self.env['res.partner'].create({
                'name': 'Acertos %s' % nome, 'type': 'settlement',
                'email': 'acertos@%s.com.br' % nome.replace(' ', ''),
                'parent_id': partner.id})
        if com_comprador:
            self.env['res.partner'].create({
                'name': 'Compras %s' % nome, 'type': 'buyer',
                'email': 'compras@%s.com.br' % nome.replace(' ', ''),
                'parent_id': partner.id})
        agr = self.env['consignment.agreement'].create({
            'partner_id': partner.id, 'company_id': self.company.id})
        agr.action_activate()
        self.env['stock.quant']._update_available_quantity(
            self.product, agr.location_id, 10)
        return agr

    def _co(self, agr):
        return agr._settlement_for_map()

    def _venda(self, agr):
        return self.env['sale.order'].create({'partner_id': agr.partner_id.id})

    # -- os dois papéis existem na ficha ------------------------------------
    def test_os_dois_papeis_entram_entre_entregas_e_outro(self):
        """A ordem da tela é a ordem da lista, e ela foi escolhida: os dois
        papéis novos ficam depois de Entregas e antes de Outro."""
        valores = [v for v, _rotulo
                   in self.env['res.partner']._fields['type'].selection]
        self.assertIn('settlement', valores)
        self.assertIn('buyer', valores)
        self.assertLess(valores.index('delivery'), valores.index('settlement'))
        self.assertLess(valores.index('buyer'), valores.index('other'))

    # -- a tabela de destinatários ------------------------------------------
    def test_so_prateleira_vai_para_acertos(self):
        """O disparo mensal: a CO acabou de nascer e só tem a prateleira."""
        agr = self._livraria('Livraria Mensal')
        co = self._co(agr)
        self.assertEqual(co.map_recipient_ids, agr._settlement_contacts())

    def test_acerto_e_devolucao_vao_para_acertos(self):
        agr = self._livraria('Livraria de Acerto')
        co = self._co(agr)
        co.sale_order_id = self._venda(agr)
        self.assertEqual(co.map_recipient_ids, agr._settlement_contacts())

    def test_so_reposicao_vai_para_o_comprador(self):
        """Quem confere prateleira não autoriza compra: um pedido sem acerto
        não é assunto dele."""
        agr = self._livraria('Livraria de Reposicao')
        co = self._co(agr)
        co.replenishment_order_id = self._venda(agr)
        self.assertEqual(co.map_recipient_ids, agr._buyer_contacts())

    def test_co_mista_vai_para_os_dois(self):
        agr = self._livraria('Livraria Mista')
        co = self._co(agr)
        co.sale_order_id = self._venda(agr)
        co.replenishment_order_id = self._venda(agr)
        self.assertEqual(
            co.map_recipient_ids,
            agr._settlement_contacts() | agr._buyer_contacts())

    def test_os_contatos_do_contrato_entram_sempre(self):
        agr = self._livraria('Livraria com Extra')
        extra = self.env['res.partner'].create({
            'name': 'Diretoria', 'email': 'diretoria@teste.com.br'})
        agr.report_contact_ids = [(4, extra.id)]
        self.assertIn(extra, self._co(agr).map_recipient_ids)

    # -- o Pedido C avulso ---------------------------------------------------
    def _pedido_c(self, agr):
        return self.env['sale.order'].create({
            'partner_id': agr.partner_id.id,
            'is_consignment': True,
            'order_line': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': 4})],
        })

    def _mails(self, pedido):
        return self.env['mail.mail'].sudo().search([
            ('model', '=', 'sale.order'), ('res_id', '=', pedido.id),
            ('subject', 'like', 'Pedido de Consignação')])

    def test_confirmar_o_pedido_avisa_o_comprador_com_o_pdf(self):
        agr = self._livraria('Livraria do Pedido')
        pedido = self._pedido_c(agr)

        pedido.action_confirm()

        mails = self._mails(pedido)
        self.assertEqual(len(mails), 1, 'confirmar o Pedido C não avisou ninguém')
        self.assertEqual(mails.recipient_ids, agr._buyer_contacts(),
                         'o pedido não foi para o Comprador')
        self.assertTrue(mails.attachment_ids, 'o e-mail saiu sem o PDF do pedido')

    def test_o_acerto_nao_recebe_o_pedido(self):
        """O Acertos tem o mapa; o pedido é do Comprador."""
        agr = self._livraria('Livraria Separada')
        pedido = self._pedido_c(agr)
        pedido.action_confirm()
        self.assertNotIn(agr._settlement_contacts(),
                         self._mails(pedido).recipient_ids)

    def test_a_reposicao_da_co_nao_manda_o_pedido_de_novo(self):
        """A reposição nascida de um acerto já é anunciada pelo mapa daquela
        CO. Mandar o Pedido também seria o segundo e-mail para a mesma pessoa
        sobre a mesma remessa."""
        agr = self._livraria('Livraria da Reposicao CO')
        co = self._co(agr)
        pedido = self._pedido_c(agr)
        pedido.consignment_operation_id = co

        pedido.action_confirm()

        self.assertFalse(self._mails(pedido),
                         'a reposição da CO mandou o Pedido por fora do mapa')

    def test_sem_comprador_abre_tarefa(self):
        """Caso de erro: pedido confirmado sem Comprador cadastrado. O pedido
        vale — o e-mail é o recado, não o ato — e o cadastro vira tarefa."""
        agr = self._livraria('Livraria Sem Comprador', com_comprador=False)
        pedido = self._pedido_c(agr)

        pedido.action_confirm()

        self.assertEqual(pedido.state, 'sale', 'o aviso derrubou a confirmação')
        self.assertFalse(self._mails(pedido))
        tarefas = self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'sale.order'), ('res_id', '=', pedido.id)])
        self.assertEqual(len(tarefas), 1, 'o cadastro sem Comprador passou batido')
        self.assertEqual(tarefas.user_id, self.vendedora)

    def test_pedido_que_nao_e_consignacao_nao_dispara(self):
        agr = self._livraria('Livraria de Venda')
        venda = self.env['sale.order'].create({
            'partner_id': agr.partner_id.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': 1})],
        })
        venda.action_confirm()
        self.assertFalse(self._mails(venda))
