# -*- coding: utf-8 -*-
"""O Pedido C entrega NA PRATELEIRA, e só entrega se houver contrato ativo.

Os dois defeitos que estes testes seguram foram achados juntos, em 24/08/2026,
depois que o C000 foi liberado para o Gerente Comercial abrir consignações:

  - A remessa do Pedido C ia para "Clientes", a localização de saída do core --
    onde o livro deixa de ser nosso. Consignação é o contrário disso: o livro
    continua nosso, parado na prateleira do cliente, até o acerto. Validada a
    remessa, o livro sumia do estoque e não entrava em prateleira nenhuma; a
    prateleira ficava zerada, o mapa mensal saía vazio e o acerto não tinha o
    que cobrar. No prod eram 64 movimentos já validados assim.
  - O Pedido C confirmava para cliente SEM contrato e para contrato SUSPENSO.
    A Movimentação (CR/CO) sempre recusou os dois; o Pedido era a porta sem
    porteiro -- e a porta por onde a casa manda a maior parte do livro.

O que se prova aqui é o motor: destino do movimento e as duas recusas. A tela
tem o `pedido_c_tour`, que é o que pega ACL e botão faltando.
"""
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_moves", "soc_pedido_c")
class TestPedidoCPrateleira(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1)
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.product = cls.env["product.product"].create({
            "name": "Vidas Secas", "type": "consu",
            "is_storable": True, "list_price": 40.0})

    # -- fixtures -----------------------------------------------------------
    def _livraria(self, nome, com_contrato=True, estado="active"):
        partner = self.env["res.partner"].create(
            {"name": nome, "is_company": True})
        agreement = self.env["consignment.agreement"]
        if com_contrato:
            agreement = self.env["consignment.agreement"].create({
                "partner_id": partner.id, "company_id": self.company.id,
                "date_start": fields.Date.today(),
            })
            # A prateleira nasce na ativação: mesmo um contrato que se quer
            # suspenso passa por 'active' antes, senão não haveria prateleira
            # para comparar -- e é assim que acontece na casa.
            agreement.action_activate()
            if estado == "suspended":
                agreement.action_suspend()
            elif estado == "closed":
                agreement.action_close()
            elif estado == "draft":
                agreement.action_draft()
        return partner, agreement

    def _no_estoque(self, qty=50):
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.stock_loc, qty)

    def _pedido_c(self, partner, qty=10):
        return self.env["sale.order"].create({
            "partner_id": partner.id, "company_id": self.company.id,
            "is_consignment": True, "consignment_type": "opening",
            "order_line": [(0, 0, {
                "product_id": self.product.id, "product_uom_qty": qty})],
        })

    # -- caminho feliz ------------------------------------------------------
    def test_a_remessa_vai_para_a_prateleira_do_contrato(self):
        """O destino do movimento é a prateleira, não "Clientes"."""
        self._no_estoque()
        partner, agreement = self._livraria("Livraria da Prateleira")
        pedido = self._pedido_c(partner, qty=10)
        pedido.action_confirm()

        picking = pedido.picking_ids
        self.assertTrue(picking, "o Pedido C tem de gerar a remessa")
        self.assertEqual(
            picking.picking_type_id,
            self.company.consignment_delivery_operation_type_id,
            "a remessa saiu no tipo de operação genérico do armazém")
        self.assertTrue(picking.name.startswith("COM/OUT/"),
                        "a série da remessa é COM/OUT: %s" % picking.name)
        self.assertEqual(
            picking.location_dest_id, agreement.location_id,
            "a remessa foi para %s em vez da prateleira do contrato"
            % picking.location_dest_id.complete_name)
        for move in picking.move_ids:
            self.assertEqual(move.location_dest_id, agreement.location_id)
            self.assertFalse(
                move.location_dest_id.usage == "customer",
                "o livro saiu do nosso estoque: em consignação ele continua "
                "nosso até o acerto")

    def test_validada_a_remessa_a_prateleira_enche(self):
        """A prova que a equipe procurava: depois de validar, o livro APARECE
        na prateleira do cliente -- é isso que o mapa e o acerto leem."""
        self._no_estoque()
        partner, agreement = self._livraria("Livraria que Recebe")
        pedido = self._pedido_c(partner, qty=7)
        pedido.action_confirm()
        picking = pedido.picking_ids
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()

        self.assertEqual(picking.state, "done")
        agreement.invalidate_recordset()
        self.assertEqual(agreement.on_shelf_qty, 7,
                         "a prateleira continuou vazia depois da remessa")
        quant = self.env["stock.quant"].search([
            ("location_id", "=", agreement.location_id.id),
            ("product_id", "=", self.product.id)])
        self.assertEqual(sum(quant.mapped("quantity")), 7)

    def test_a_quantidade_entregue_conta_a_prateleira(self):
        """ENTREGUE, na consignação, é "chegou na prateleira".

        O core só conta como entregue o que termina em localização de cliente,
        e a prateleira é interna. Sem o ajuste do `_get_outgoing_incoming_moves`
        a `qty_delivered` de todo Pedido C ficava em zero -- e não é número de
        enfeite: é ela que a NOTA DE REMESSA lê para declarar o que vai dentro
        da caixa. Foi assim que o desvio quebrou dez testes do fiscal de uma vez.
        """
        self._no_estoque()
        partner, _agr = self._livraria("Livraria da Entrega")
        pedido = self._pedido_c(partner, qty=5)
        pedido.action_confirm()
        linha = pedido.order_line
        self.assertEqual(linha.qty_delivered, 0,
                         "nada saiu ainda: entregue tem de ser zero")

        picking = pedido.picking_ids
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()

        pedido.invalidate_recordset()
        self.assertEqual(linha.qty_delivered, 5,
                         "a remessa foi validada e a linha diz que não entregou")

    def test_o_movimento_conta_para_o_razao_da_consignacao(self):
        """Chegando pela prateleira, o movimento entra no razão do cliente --
        que é o que soma o saldo consignado livro a livro."""
        self._no_estoque()
        partner, agreement = self._livraria("Livraria do Razao")
        pedido = self._pedido_c(partner, qty=4)
        pedido.action_confirm()
        picking = pedido.picking_ids
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()

        move = picking.move_ids
        self.assertEqual(move.consignment_partner_id, partner,
                         "o movimento não foi reconhecido como de consignação")
        self.assertEqual(move.consignment_qty, 4,
                         "a prateleira do cliente devia ter subido 4")

    # -- as duas recusas ----------------------------------------------------
    def test_sem_contrato_nao_confirma(self):
        self._no_estoque()
        partner, _agr = self._livraria("Livraria sem Contrato",
                                       com_contrato=False)
        pedido = self._pedido_c(partner)
        with self.assertRaises(UserError) as erro:
            pedido.action_confirm()
        self.assertIn("no consignment agreement", str(erro.exception))
        self.assertEqual(pedido.state, "draft",
                         "o pedido não pode avançar sem contrato")
        self.assertFalse(pedido.picking_ids,
                         "nasceu remessa para uma prateleira que não existe")

    def test_contrato_suspenso_nao_confirma(self):
        self._no_estoque()
        partner, agreement = self._livraria("Livraria Suspensa",
                                            estado="suspended")
        pedido = self._pedido_c(partner)
        with self.assertRaises(UserError) as erro:
            pedido.action_confirm()
        self.assertIn(agreement.name, str(erro.exception),
                      "a mensagem tem de dizer QUAL contrato está barrando")
        self.assertEqual(pedido.state, "draft")

    def test_contrato_fechado_nao_confirma(self):
        """Fechado cai na mesma recusa do suspenso: `_resolve_for` acha o
        contrato encerrado do cliente, e o estado dele explica o não."""
        self._no_estoque()
        partner, _agr = self._livraria("Livraria Encerrada", estado="closed")
        pedido = self._pedido_c(partner)
        with self.assertRaises(UserError):
            pedido.action_confirm()
        self.assertEqual(pedido.state, "draft")

    def test_contrato_em_rascunho_nao_confirma(self):
        """Rascunho tem prateleira (nasceu na ativação) e mesmo assim não
        recebe: o contrato voltou para rascunho porque alguém o tirou do ar."""
        self._no_estoque()
        partner, agreement = self._livraria("Livraria em Rascunho",
                                            estado="draft")
        self.assertTrue(agreement.location_id,
                        "o cenário exige um contrato COM prateleira")
        pedido = self._pedido_c(partner)
        with self.assertRaises(UserError):
            pedido.action_confirm()
        self.assertEqual(pedido.state, "draft")

    def test_o_contato_da_livraria_usa_o_contrato_da_matriz(self):
        """O comercial escolhe a pessoa de compras, não o CNPJ. O contrato é da
        LIVRARIA, e a remessa tem de achar a prateleira dela mesmo assim --
        senão o pedido feito pelo contato certo seria recusado por engano."""
        self._no_estoque()
        partner, agreement = self._livraria("Livraria Matriz")
        comprador = self.env["res.partner"].create({
            "name": "Compras da Matriz", "parent_id": partner.id})
        pedido = self.env["sale.order"].create({
            "partner_id": comprador.id, "company_id": self.company.id,
            "is_consignment": True, "consignment_type": "opening",
            "order_line": [(0, 0, {
                "product_id": self.product.id, "product_uom_qty": 2})],
        })
        self.assertEqual(pedido.consignment_agreement_id, agreement,
                         "o contato não alcançou o contrato da livraria")
        pedido.action_confirm()
        self.assertEqual(pedido.picking_ids.location_dest_id,
                         agreement.location_id)

    def test_contrato_reativado_volta_a_confirmar(self):
        """A recusa é da situação, não do cliente: reativado o contrato, o
        mesmo pedido confirma e vai para a prateleira."""
        self._no_estoque()
        partner, agreement = self._livraria("Livraria Reativada",
                                            estado="suspended")
        pedido = self._pedido_c(partner)
        with self.assertRaises(UserError):
            pedido.action_confirm()
        agreement.action_reactivate()
        pedido.action_confirm()
        self.assertEqual(pedido.state, "sale")
        self.assertEqual(pedido.picking_ids.location_dest_id,
                         agreement.location_id)

    # -- o que NÃO pode mudar -----------------------------------------------
    def test_a_venda_comum_continua_indo_para_o_cliente(self):
        """A trava e o desvio são do Pedido C. Uma venda de verdade entrega ao
        cliente, no tipo de operação do armazém, e não pede contrato nenhum --
        senão o conserto da consignação teria parado a casa inteira."""
        self._no_estoque()
        partner = self.env["res.partner"].create(
            {"name": "Livraria que Compra", "is_company": True})
        venda = self.env["sale.order"].create({
            "partner_id": partner.id, "company_id": self.company.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id, "product_uom_qty": 3})],
        })
        venda.action_confirm()
        self.assertEqual(venda.state, "sale")
        picking = venda.picking_ids
        self.assertTrue(picking)
        self.assertEqual(picking.location_dest_id.usage, "customer",
                         "a venda comum foi desviada para uma prateleira")
        self.assertNotEqual(
            picking.picking_type_id,
            self.company.consignment_delivery_operation_type_id)

    def test_cada_cliente_na_sua_transferencia(self):
        """Duas remessas simultâneas não podem cair na mesma transferência: o
        destino é a prateleira, e prateleira é de um cliente só."""
        self._no_estoque(qty=100)
        p1, a1 = self._livraria("Livraria Um")
        p2, a2 = self._livraria("Livraria Dois")
        ped1, ped2 = self._pedido_c(p1, 5), self._pedido_c(p2, 5)
        ped1.action_confirm()
        ped2.action_confirm()

        self.assertNotEqual(ped1.picking_ids, ped2.picking_ids,
                            "as duas livrarias dividiram a mesma remessa")
        self.assertEqual(ped1.picking_ids.location_dest_id, a1.location_id)
        self.assertEqual(ped2.picking_ids.location_dest_id, a2.location_id)

    def test_a_reposicao_do_acerto_tambem_vai_para_a_prateleira(self):
        """A reposição nasce como Pedido C (`consignment_type` de reposição) e
        percorre o mesmo caminho: se o desvio valesse só para a abertura,
        metade das remessas continuaria errada."""
        self._no_estoque()
        partner, agreement = self._livraria("Livraria da Reposicao")
        pedido = self._pedido_c(partner, qty=6)
        pedido.consignment_type = "replenishment"
        pedido.action_confirm()
        self.assertEqual(pedido.picking_ids.location_dest_id,
                         agreement.location_id)
