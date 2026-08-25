# -*- coding: utf-8 -*-
"""O Pedido C percorrido na tela, nos três desfechos.

A regra de 22/08/2026 diz que fechar um módulo pede tour além do ORM, porque o
ORM mede o que o teste pediu e a tela mede o que a tela pede. Aqui o motivo é
literal: o C000 foi liberado para o Gerente Comercial abrir consignações, e foi
NA TELA que a equipe viu que o estoque não chegava na prateleira -- nenhum
teste de motor estava olhando para aquele caminho.

São três tours porque são três desfechos do mesmo clique (Confirmar):

  - contrato ativo: confirma, a remessa nasce em COM/OUT e o comercial a
    alcança pelo botão de entrega;
  - sem contrato: recusa, com o motivo escrito na caixa de diálogo;
  - contrato suspenso: recusa, e a mensagem diz QUAL contrato e em que estado.

Este arquivo roda como ADMIN, que é o que o módulo consegue sozinho -- ele não
depende do liber_roles. Os mesmos três tours rodam no perfil de verdade em
liber_roles/tests/test_tour_comercial.py: admin passa em tudo e não prova nada
sobre o perfil.

O que a tela NÃO mede fica para depois do tour, aqui embaixo, em asserções de
motor: para onde o movimento foi e quanto a prateleira recebeu. Ler quant na
tela exigiria o "Locais de armazenamento" ligado, que é configuração de cada
base -- o teste ficaria verde ou vermelho por causa de um interruptor.
"""
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "soc_pedido_c_tour")
class TestPedidoCTour(HttpCase):

    def setUp(self):
        super().setUp()
        # A SESSÃO DO TOUR EM INGLÊS, como nos demais tours da casa: dois passos
        # leem a mensagem da recusa na caixa de diálogo, e mensagem é texto
        # traduzido. O `testing` tem o admin em pt_BR -- a primeira rodada deste
        # arquivo morreu por isso. Os outros tours resolvem criando um usuário
        # com `lang` en_US; aqui, que roda como admin, a troca é no próprio
        # admin e desaparece no rollback do teste.
        self.env.ref('base.user_admin').lang = 'en_US'

    def _livro(self, nome, qty):
        product = self.env["product.product"].create({
            "name": nome, "type": "consu",
            "is_storable": True, "list_price": 45.0})
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1)
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": product.id,
            "location_id": warehouse.lot_stock_id.id,
            "inventory_quantity": qty,
        }).action_apply_inventory()
        return product

    def _livraria(self, nome, estado="active"):
        """A livraria como o tour vai encontrá-la. `estado=None` é a que nunca
        teve contrato -- e o Pedido dela é o que tem de ser recusado."""
        partner = self.env["res.partner"].create(
            {"name": nome, "is_company": True})
        if estado is None:
            return partner, self.env["consignment.agreement"]
        agreement = self.env["consignment.agreement"].create(
            {"partner_id": partner.id})
        agreement.action_activate()
        if estado == "suspended":
            agreement.action_suspend()
        return partner, agreement

    def test_pedido_c_prateleira_tour(self):
        """O caminho que a equipe reclamou: o livro tem de chegar à prateleira."""
        self._livro("Livro do Pedido C", 30)
        partner, agreement = self._livraria("Livraria do Pedido C")

        self.start_tour("/odoo", "pedido_c_prateleira_tour", login="admin")

        pedido = self.env["sale.order"].search(
            [("partner_id", "=", partner.id), ("is_consignment", "=", True)],
            limit=1)
        self.assertTrue(pedido, "o tour deve ter criado o Pedido C")
        self.assertEqual(pedido.state, "sale")
        self.assertEqual(pedido.consignment_agreement_id, agreement)

        picking = pedido.picking_ids
        self.assertTrue(picking, "confirmar o Pedido C tem de gerar a remessa")
        self.assertTrue(picking.name.startswith("COM/OUT/"),
                        "a remessa saiu fora da série da consignação: %s"
                        % picking.name)
        self.assertEqual(
            picking.location_dest_id, agreement.location_id,
            "a remessa foi para %s: era para ir para a prateleira do contrato"
            % picking.location_dest_id.complete_name)

        # E o desfecho que a equipe procurava: validada a remessa, a prateleira
        # do contrato tem os livros. Validar é trabalho do depósito, não do
        # comercial -- por isso acontece aqui, no motor, e não no tour.
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()
        agreement.invalidate_recordset()
        self.assertEqual(agreement.on_shelf_qty, 3,
                         "a prateleira continuou vazia depois da remessa")

    def test_pedido_c_sem_contrato_tour(self):
        self._livro("Livro do Pedido C", 30)
        partner, _agr = self._livraria("Livraria sem Contrato", estado=None)

        self.start_tour("/odoo", "pedido_c_sem_contrato_tour", login="admin")

        pedido = self.env["sale.order"].search(
            [("partner_id", "=", partner.id), ("is_consignment", "=", True)],
            limit=1)
        self.assertTrue(pedido, "o tour deve ter criado o Pedido C")
        self.assertFalse(pedido.consignment_agreement_id,
                         "o cliente do caso não podia ter contrato nenhum")
        self.assertEqual(pedido.state, "draft",
                         "o pedido avançou sem contrato de consignação")
        self.assertFalse(pedido.picking_ids,
                         "nasceu remessa para uma prateleira que não existe")

    def test_pedido_c_suspenso_tour(self):
        self._livro("Livro do Pedido C", 30)
        partner, agreement = self._livraria("Livraria Suspensa",
                                            estado="suspended")

        self.start_tour("/odoo", "pedido_c_suspenso_tour", login="admin")

        pedido = self.env["sale.order"].search(
            [("partner_id", "=", partner.id), ("is_consignment", "=", True)],
            limit=1)
        self.assertTrue(pedido)
        self.assertEqual(pedido.state, "draft",
                         "a suspensão não segurou a remessa")
        self.assertEqual(agreement.state, "suspended")
        self.assertEqual(agreement.on_shelf_qty, 0)
