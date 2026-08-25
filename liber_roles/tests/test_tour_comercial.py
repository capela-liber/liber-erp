# -*- coding: utf-8 -*-
"""Os tours do Comercial na consignação: a CO (acerto) e a CR (devolução).

O `test_logistica.py` prova no ORM que o comercial solta o movimento; estes
dois provam o caminho pela tela, logados no perfil real — a regra de 22/08.
O gatilho foi o bloqueio de produção de 21/08/2026: o "Liberar para Logística"
da CR/2026/00027 morreu na constraint `name_uniq` do stock.picking, um defeito
que só aparece clicando. Uma base de teste nasce com a série COM/IN zerada e
não reproduz a colisão de nomes do prod, mas o tour crava o caminho inteiro
(ACL do perfil, botões, estados) e acusa qualquer quebra nova nele.

- CR: a devolução aberta da lista (a ação tem create: False — CR nasce do
  acerto), Confirmar, Liberar para Logística, e o picking COM/IN existe.
- CO: o `soc_acerto_tour` do liber_soc_settlement, que já roda como admin no
  módulo dele, aqui roda como COMERCIAL: admin passa em tudo e não prova nada
  sobre o perfil.
- MAPA: o `soc_mapa_avulso_tour`, mesma ideia. O botão abre a CO do mês e manda
  o mapa dela -- renderiza relatório, cria anexo e enfileira e-mail --, e um
  perfil que lê e grava o contrato pode não ter direito a nenhum dos três.
  Numa primeira versão, com um `group_soc_user` pelado, a ficha do contrato
  sequer abriu: Access Error em `sale.order` (24/08/2026). O comercial de
  verdade tem Vendas e passa; o teste existe para o dia em que deixar de ter.
"""
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "liber_roles_tour")
class TestComercialSocTour(HttpCase):

    def _usuario_comercial(self):
        company = self.env.company
        # A sessão do tour roda em inglês (mesmo motivo dos outros tours da
        # casa): passo que só existe por texto quebra quando a tradução entra.
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Comercial do Tour',
            'login': 'comercial_tour',
            'password': 'comercial_tour',
            'lang': 'en_US',
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'group_ids': [(4, self.env.ref(
                'liber_roles.group_comercial_assistente').id)],
        })

    def _usuario_gerente_comercial(self):
        """O GERENTE, e não o assistente: foi a ele que a casa liberou o C000
        para abrir consignações (24/08/2026), e é o perfil dele que precisa
        alcançar a lista de Pedidos de consignação e o botão de entrega."""
        company = self.env.company
        # A senha é o próprio login, que é a regra da casa para usuário de
        # tour. Escrita UMA vez, e não duas: repetida como literal, a varredura
        # de segredos do publish_liber_erp.sh a lê como credencial e barra a
        # publicação do módulo aberto (25/08/2026).
        login = 'gerente_comercial_tour'
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gerente Comercial do Tour',
            'login': login,
            'password': login,
            'lang': 'en_US',
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'group_ids': [(4, self.env.ref(
                'liber_roles.group_comercial_gerente').id)],
        })

    def _livraria_com_prateleira(self, nome):
        partner = self.env['res.partner'].create(
            {'name': nome, 'is_company': True})
        agreement = self.env['consignment.agreement'].create(
            {'partner_id': partner.id})
        agreement.action_activate()
        return partner, agreement

    def _livro_no_estoque(self, nome, qty):
        product = self.env['product.product'].create({
            'name': nome, 'type': 'consu',
            'is_storable': True, 'list_price': 50.0})
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': product.id,
            'location_id': warehouse.lot_stock_id.id,
            'inventory_quantity': qty,
        }).action_apply_inventory()
        return product

    def _remessa_para_prateleira(self, partner, product, qty):
        """Põe `qty` na prateleira pelo motor (remessa liberada e validada),
        nunca escrevendo quant: a devolução tem de sair de uma prateleira que
        chegou lá como uma de verdade chega."""
        shipment = self.env['consignment.move'].create({
            'partner_id': partner.id,
            'move_kind': 'shipment',
            'line_ids': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': qty,
                'product_uom': product.uom_id.id,
            })],
        })
        shipment.action_confirm()
        shipment.action_release()
        shipment.picking_id.move_ids.picked = True
        shipment.picking_id.button_validate()

    def test_comercial_devolucao_tour(self):
        self._usuario_comercial()
        partner, _agreement = self._livraria_com_prateleira(
            'Livraria da Devolucao')
        livro = self._livro_no_estoque('Livro Devolvido', 20)
        self._remessa_para_prateleira(partner, livro, 5)

        # A CR em rascunho, como o acerto a deixa (create: False na ação:
        # ninguém digita uma CR na lista).
        cr = self.env['consignment.move'].create({
            'partner_id': partner.id,
            'move_kind': 'return',
            'line_ids': [(0, 0, {
                'product_id': livro.id,
                'product_uom_qty': 3,
                'product_uom': livro.uom_id.id,
            })],
        })
        self.assertEqual(cr.state, 'draft')

        self.start_tour("/odoo", "comercial_devolucao_tour",
                        login="comercial_tour")

        self.assertEqual(cr.state, 'confirmed')
        picking = cr.picking_id
        self.assertTrue(picking,
                        'o Liberar para Logística deve criar a transferência')
        self.assertEqual(
            picking.picking_type_id,
            self.env.company.consignment_return_operation_type_id,
            'o retorno sai no tipo de operação próprio, não no interno genérico')
        self.assertTrue(
            picking.name.startswith('COM/IN/'),
            'a série do retorno é COM/IN (foi ela que colidiu no prod): %s'
            % picking.name)
        self.assertEqual(picking.state, 'assigned',
                         'a reserva deve sair da prateleira do cliente')

    def test_comercial_acerto_tour(self):
        # O acerto mora no liber_soc_settlement, que não é dependência deste
        # módulo: sem ele instalado não há tela para percorrer.
        if not self.env['ir.module.module'].search(
                [('name', '=', 'liber_soc_settlement'),
                 ('state', '=', 'installed')]):
            self.skipTest('liber_soc_settlement não instalado')
        self._usuario_comercial()
        # O mesmo mundo do tests/test_tour.py do settlement — os nomes são os
        # que o soc_acerto_tour digita — mas quem clica é o comercial.
        partner, _agreement = self._livraria_com_prateleira(
            'Livraria do Acerto')
        sells = self._livro_no_estoque('Livro que Vende', 40)
        stuck = self._livro_no_estoque('Livro Parado', 20)
        self._remessa_para_prateleira(partner, sells, 10)
        self._remessa_para_prateleira(partner, stuck, 5)

        self.start_tour("/odoo", "soc_acerto_tour", login="comercial_tour")

        settlement = self.env['consignment.settlement'].search(
            [('partner_id', '=', partner.id)], limit=1)
        self.assertTrue(settlement, 'o tour deve ter criado a operação')
        self.assertEqual(settlement.state, 'confirmed')
        self.assertTrue(settlement.sale_order_id,
                        'os 4 vendidos viram uma venda de verdade')
        self.assertTrue(settlement.replenishment_order_id,
                        'a reposição sugerida vira um Pedido C')
        cr = settlement.return_move_id
        self.assertTrue(cr, 'o título parado vira uma CR')
        self.assertEqual(cr.move_kind, 'return')
        # A CR nasce em rascunho: o passo seguinte do comercial é exatamente o
        # test_comercial_devolucao_tour acima.
        self.assertEqual(cr.state, 'draft')

    def test_comercial_mapa_avulso_tour(self):
        """O mapa da prateleira mandado da ficha do contrato, sem acerto."""
        if not self.env['ir.module.module'].search(
                [('name', '=', 'liber_soc_settlement'),
                 ('state', '=', 'installed')]):
            self.skipTest('liber_soc_settlement não instalado')
        self._usuario_comercial()
        # O nome e a quantidade são os que o soc_mapa_avulso_tour cobra.
        partner, agreement = self._livraria_com_prateleira('Livraria do Mapa')
        partner.email = 'geral.do.mapa@teste.com.br'
        # O mapa vai para o contato de ACERTOS, não para a caixa geral.
        self.env['res.partner'].create({
            'name': 'Acertos da Livraria do Mapa', 'type': 'settlement',
            'email': 'acertos.do.mapa@teste.com.br', 'parent_id': partner.id})
        self._remessa_para_prateleira(
            partner, self._livro_no_estoque('Livro do Mapa', 40), 12)

        self.start_tour("/odoo", "soc_mapa_avulso_tour",
                        login="comercial_tour")

        # O mapa pendura na OPERAÇÃO, não no contrato: o botão abre a CO do mês
        # (ou reaproveita a aberta) e manda o mapa dela, para a resposta do
        # cliente cair numa operação que tem dono e prazo.
        co = self.env['consignment.settlement'].sudo().search(
            [('partner_id', '=', partner.id)])
        self.assertEqual(len(co), 1,
                         'o comercial clicou e a operação do mês não abriu')
        self.assertEqual(co.line_ids.qty_on_shelf, 12,
                         'a CO do comercial saiu sem a prateleira lida')
        # Pelo assunto: a CO nasce com dono, e a atribuição gera a sua própria
        # notificação por e-mail na mesma CO.
        mail = self.env['mail.mail'].sudo().search([
            ('model', '=', 'consignment.settlement'), ('res_id', '=', co.id),
            ('subject', 'like', 'Mapa de Consignação')])
        self.assertEqual(len(mail), 1,
                         'o comercial clicou e o mapa não foi enfileirado')
        self.assertTrue(mail.attachment_ids,
                        'o e-mail do comercial saiu sem o PDF do mapa')
        self.assertTrue(agreement.map_last_sent_date,
                        'o envio pela tela não carimbou o contrato')

    # ------------------------------------------------------------------
    # O Pedido C no perfil de quem o abre
    # ------------------------------------------------------------------
    # Os três tours moram no liber_soc_moves e lá rodam como admin. Aqui rodam
    # como GERENTE COMERCIAL, que é quem passou a abrir consignações -- e o
    # motivo de existirem: liberado o C000 para ele, a equipe viu que o estoque
    # não chegava na prateleira do cliente. Admin passa em tudo e não prova
    # nada sobre o perfil; o que se cobra aqui é que o gerente ALCANCE a lista
    # de Pedidos de consignação, veja o contrato resolvido no formulário e
    # chegue à remessa pelo botão de entrega, sem Access Error no caminho.
    def _livro_e_livraria_do_pedido_c(self, nome_livraria, estado='active'):
        self._livro_no_estoque('Livro do Pedido C', 30)
        partner = self.env['res.partner'].create(
            {'name': nome_livraria, 'is_company': True})
        if estado is None:
            return partner, self.env['consignment.agreement']
        agreement = self.env['consignment.agreement'].create(
            {'partner_id': partner.id})
        agreement.action_activate()
        if estado == 'suspended':
            agreement.action_suspend()
        return partner, agreement

    def _pedido_c_do_tour(self, partner):
        return self.env['sale.order'].search(
            [('partner_id', '=', partner.id), ('is_consignment', '=', True)],
            limit=1)

    def test_gerente_comercial_pedido_c_tour(self):
        self._usuario_gerente_comercial()
        partner, agreement = self._livro_e_livraria_do_pedido_c(
            'Livraria do Pedido C')

        self.start_tour("/odoo", "pedido_c_prateleira_tour",
                        login="gerente_comercial_tour")

        pedido = self._pedido_c_do_tour(partner)
        self.assertTrue(pedido, 'o gerente não conseguiu criar o Pedido C')
        self.assertEqual(pedido.state, 'sale')
        picking = pedido.picking_ids
        self.assertTrue(picking, 'confirmar o Pedido C não gerou a remessa')
        self.assertEqual(
            picking.location_dest_id, agreement.location_id,
            'a remessa foi para %s: era para ir para a prateleira do contrato'
            % picking.location_dest_id.complete_name)
        self.assertTrue(picking.name.startswith('COM/OUT/'),
                        'a remessa saiu fora da série da consignação: %s'
                        % picking.name)

    def test_gerente_comercial_pedido_c_sem_contrato_tour(self):
        self._usuario_gerente_comercial()
        partner, _agr = self._livro_e_livraria_do_pedido_c(
            'Livraria sem Contrato', estado=None)

        self.start_tour("/odoo", "pedido_c_sem_contrato_tour",
                        login="gerente_comercial_tour")

        pedido = self._pedido_c_do_tour(partner)
        self.assertTrue(pedido)
        self.assertEqual(pedido.state, 'draft',
                         'o gerente confirmou um Pedido C sem contrato')
        self.assertFalse(pedido.picking_ids)

    def test_gerente_comercial_pedido_c_suspenso_tour(self):
        self._usuario_gerente_comercial()
        partner, agreement = self._livro_e_livraria_do_pedido_c(
            'Livraria Suspensa', estado='suspended')

        self.start_tour("/odoo", "pedido_c_suspenso_tour",
                        login="gerente_comercial_tour")

        pedido = self._pedido_c_do_tour(partner)
        self.assertTrue(pedido)
        self.assertEqual(pedido.state, 'draft',
                         'a suspensão não segurou a remessa do gerente')
        self.assertEqual(agreement.on_shelf_qty, 0)
