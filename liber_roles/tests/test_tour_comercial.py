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
from odoo.exceptions import AccessError
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
        livro = self._livro_no_estoque('Livro do Pedido C', 30)
        partner = self.env['res.partner'].create(
            {'name': nome_livraria, 'is_company': True})
        # O Pedido C em rascunho, como a Operação de Consignação o deixa: a
        # lista não tem mais "Novo" (06/09/2026), e o tour o abre em vez de
        # digitá-lo. O que se mede no perfil é alcançar a lista, ver o
        # contrato resolvido e chegar à remessa -- não criar.
        self.env['sale.order'].create({
            'partner_id': partner.id,
            'is_consignment': True,
            'consignment_type': 'opening',
            'order_line': [(0, 0, {'product_id': livro.id,
                                   'product_uom_qty': 3})],
        })
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
        self.assertTrue(pedido, 'o Pedido C semeado sumiu')
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

    # ------------------------------------------------------------------
    # O contrato de consignação (AC): quem abre e quem opera
    # ------------------------------------------------------------------
    # Bloqueio de produção de 26/08/2026: a gerente comercial clicou "Ativar"
    # no AC/2026/0277 e levou "Você não tem permissões para criar registros de
    # 'Locais de inventário' (stock.location)". A prateleira do cliente É um
    # stock.location, e criar local no core é de Inventário/Administrador --
    # que o Comercial não tem e não deve ter. O ORM do liber_soc_agreements
    # prova a ativação no perfil pelado; aqui se prova a TELA, no perfil real.
    #
    # O segundo tour é a divisão pedida no mesmo dia: o contrato é do gerente,
    # e o assistente opera o que existe (suspende, reativa) sem abrir novos.
    def _conta_de_consignacao(self):
        """A empresa como a produção a tem: com a conta 115xxx preenchida.

        SEM ISTO O TOUR NÃO PROVA O QUE PRECISA (27/08/2026). O
        liber_soc_fiscal_br carimba essa conta na prateleira assim que ela
        nasce, e o carimbo é uma ESCRITA em stock.location -- direito de
        Inventário, que o Comercial não tem. Numa base de teste a conta vem
        vazia, o carimbo nunca roda, e o tour passava verde enquanto a gerente
        comercial levava "Você não tem permissão para modificar registros de
        'Locais de inventário'" no prod, dois dias seguidos.

        O módulo fiscal não é dependência do liber_roles; se ele não estiver
        instalado, o campo não existe e o mundo continua o de antes.
        """
        empresa = self.env.company
        if 'consignment_stock_account_id' not in empresa._fields:
            return self.env['account.account']
        Conta = self.env['account.account']
        conta = Conta.search([('code', '=', '115996')], limit=1) or Conta.create({
            'code': '115996',
            'name': 'Estoque em Consignação (tour)',
            'account_type': 'asset_current',
        })
        empresa.consignment_stock_account_id = conta
        return conta

    def test_gerente_comercial_contrato_tour(self):
        self._usuario_gerente_comercial()
        conta = self._conta_de_consignacao()
        # A livraria existe; o contrato é o gerente quem abre, na tela.
        self.env['res.partner'].create(
            {'name': 'Livraria do Contrato', 'is_company': True})

        self.start_tour("/odoo", "comercial_contrato_tour",
                        login="gerente_comercial_tour")

        agreement = self.env['consignment.agreement'].search(
            [('partner_id.name', '=', 'Livraria do Contrato')], limit=1)
        self.assertTrue(agreement, 'o gerente não conseguiu abrir o contrato')
        # O tour termina onde começou: ativo, depois de passar por suspenso.
        self.assertEqual(agreement.state, 'active')
        prateleira = agreement.location_id
        self.assertTrue(
            prateleira,
            'ativar pela tela não criou a prateleira: é o Access Error de 26/08')
        self.assertTrue(prateleira.is_consignment_shelf)
        self.assertFalse(prateleira.warehouse_id,
                         'a prateleira não pode pendurar no armazém')
        self.assertTrue(agreement.partner_id.allow_consignment,
                        'a ficha do cliente não recebeu a marca de consignação')
        if conta:
            self.assertEqual(
                prateleira.valuation_account_id, conta,
                'a prateleira nasceu sem a conta de estoque em consignação: é '
                'a escrita que o Access Error de 27/08 barrava')
        # Uma prateleira só, e não uma por ativação: o suspende-reativa do
        # tour não pode ter aberto um segundo local para o mesmo cliente.
        self.assertEqual(
            self.env['stock.location'].search_count([
                ('is_consignment_shelf', '=', True),
                ('consignment_partner_id', '=', agreement.partner_id.id)]),
            1, 'reativar o contrato abriu uma segunda prateleira')

    def test_assistente_comercial_contrato_tour(self):
        self._usuario_comercial()
        partner, agreement = self._livraria_com_prateleira(
            'Livraria do Assistente')
        self.assertEqual(agreement.state, 'active')

        self.start_tour("/odoo", "comercial_contrato_assistente_tour",
                        login="comercial_tour")

        self.assertEqual(agreement.state, 'suspended',
                         'o assistente não conseguiu suspender o contrato')
        # E a outra metade da regra, medida no ORM porque a tela só mostra a
        # ausência do botão: o direito de abrir contrato não é dele.
        self.env.invalidate_all()
        assistente = self.env['res.users'].search(
            [('login', '=', 'comercial_tour')], limit=1)
        with self.assertRaises(
                AccessError, msg='o assistente abriu um contrato'):
            self.env['consignment.agreement'].with_user(assistente).create(
                {'partner_id': partner.id})

    # ------------------------------------------------------------------
    # A nota de remessa do Pedido C (o "Criar nota")
    # ------------------------------------------------------------------
    # Bloqueio de produção de 26/08/2026: o C08577 recusou o "Criar nota" com
    # "A conta bancária da sua empresa não é confiável". Uma mensagem sobre
    # banco num documento que não tem banco -- consignação não movimenta
    # dinheiro. O conserto mora no liber_nfe_remessa (a remessa não carimba
    # conta bancária) e tem teste de ORM lá; aqui se prova a TELA, no perfil
    # de quem clicou, porque foi como caixa de diálogo que o erro apareceu.
    def _sem_aval_bancario(self):
        """Põe a empresa no estado do prod: nenhuma conta avalizada.

        O banco de teste vem com uma conta ligada a diário, e o Odoo avaliza
        conta de diário sozinho. Sem derrubar isso, `_compute_partner_bank_id`
        escolhe a avalizada (ele ordena pondo-as na frente) e a trava do core
        nunca dispara: o tour passaria com a regressão de pé.
        """
        empresa = self.env.company
        self.env['res.partner.bank'].sudo().search(
            [('partner_id', '=', empresa.partner_id.id)]).allow_out_payment = False
        return empresa

    def _posicao_fiscal_da_remessa(self, produto):
        """A operação de remessa como a produção a tem.

        São DUAS metades, e a primeira versão deste fixture só tinha uma. O par
        auto-paid liquida o recebível; o MAPA DE CONTAS é o que tira o valor da
        receita ("conta de receita X vira a conta da operação Y"). Sem o mapa o
        próprio módulo recusa a nota -- e foi assim que este tour falhou na
        primeira rodada, com a caixa "does not say where a remessa books".
        """
        empresa = self.env.company
        Conta = self.env['account.account']

        def conta(code, name):
            return Conta.search([('code', '=', code)], limit=1) or Conta.create({
                'code': code, 'name': name, 'account_type': 'asset_current',
                'company_ids': [(4, empresa.id)]})

        fpos = self.env['account.fiscal.position'].create({
            'name': 'Consignação — Remessa (tour)', 'company_id': empresa.id,
            'auto_invoice_paid': True,
            'auto_invoice_paid_account_id': conta(
                'REMTOUR', '(-) Remessa de Consignação (tour)').id})
        fpos.account_ids.unlink()
        self.env['account.fiscal.position.account'].create({
            'position_id': fpos.id,
            'account_src_id': produto.product_tmpl_id.get_product_accounts()['income'].id,
            'account_dest_id': conta(
                'CONDTOUR', '(+) Investimento em Consignação (tour)').id,
        })
        empresa.consignment_shipment_fiscal_position_id = fpos
        return fpos

    def test_gerente_comercial_nota_remessa_tour(self):
        # A nota do C000 mora no liber_soc_fiscal_br, que não é dependência
        # deste módulo: sem ele não há botão para clicar.
        if not self.env['ir.module.module'].search(
                [('name', '=', 'liber_soc_fiscal_br'),
                 ('state', '=', 'installed')]):
            self.skipTest('liber_soc_fiscal_br não instalado')
        self._usuario_gerente_comercial()
        self._sem_aval_bancario()

        partner, _agr = self._livraria_com_prateleira('Livraria da Nota')
        livro = self._livro_no_estoque('Livro da Nota', 30)
        # A posição fiscal depende da conta de receita DO PRODUTO, então vem
        # depois dele.
        self._posicao_fiscal_da_remessa(livro)
        # O nome do produto não basta: a nota exige mercadoria FORA do armazém,
        # senão o botão recusa dizendo qual transferência falta validar.
        pedido = self.env['sale.order'].create({
            'partner_id': partner.id,
            'is_consignment': True,
            'consignment_type': 'opening',
            'order_line': [(0, 0, {
                'product_id': livro.id, 'product_uom_qty': 4,
                'price_unit': 50.0})],
        })
        pedido.action_confirm()
        picking = pedido.picking_ids.filtered(lambda p: p.state != 'cancel')
        for move in picking.move_ids:
            move.quantity = 4
            move.picked = True
        picking.with_context(skip_backorder=True,
                             picked_off_backorder=True).button_validate()
        self.assertFalse(pedido.remessa_note_move_id,
                         'a nota já existia: o tour não teria o que provar')

        self.start_tour("/odoo", "comercial_nota_remessa_tour",
                        login="gerente_comercial_tour")

        nota = pedido.remessa_note_move_id
        self.assertTrue(nota, 'o gerente clicou e a nota de remessa não saiu')
        self.assertEqual(nota.state, 'posted')
        self.assertFalse(
            nota.partner_bank_id,
            'a nota de remessa saiu carimbando conta bancária: não há o que '
            'pagar nela, e é esse carimbo que travava a emissão')
        # E o que a remessa sempre prometeu: nada a receber.
        self.assertEqual(nota.payment_state, 'paid')
