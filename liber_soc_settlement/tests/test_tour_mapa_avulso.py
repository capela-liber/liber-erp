# -*- coding: utf-8 -*-
"""O mapa mensal na TELA, disparado à mão da ficha do contrato.

O botão percorre o mesmo caminho do cron: abre a operação do mês (ou reaproveita
a que já está sendo trabalhada), lê a prateleira dentro dela e manda o mapa
DAQUELA CO. O teste ORM (test_map_schedule.py) mede a régua; ele mede o que o
teste pediu. O clique, porém, não é um write: renderiza um relatório QWeb, cria
um `ir.attachment` e enfileira um `mail.mail` -- três modelos que o teste ORM
não pergunta porque não pediu.

Aqui o tour roda como admin, como o `soc_acerto_tour` do mesmo módulo: o que se
prova é o CAMINHO. O mesmo tour rodando no PERFIL do comercial está em
`liber_roles/tests/test_tour_comercial.py`, que é onde moram os tours de perfil
-- e foi lá que ele encontrou o Access Error de `sale.order` que um
`group_soc_user` pelado leva ao abrir a ficha do contrato.
"""
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestMapaAvulsoTour(HttpCase):

    def _place_on_shelf(self, partner, product, qty):
        """Coloca livro na prateleira pelo motor (remessa liberada e validada),
        e não escrevendo quant: o mapa tem de falar de uma prateleira que
        chegou lá do jeito que uma prateleira chega."""
        shipment = self.env["consignment.move"].create({
            "partner_id": partner.id,
            "move_kind": "shipment",
            "line_ids": [(0, 0, {
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom": product.uom_id.id,
            })],
        })
        shipment.action_confirm()
        shipment.action_release()
        shipment.picking_id.move_ids.picked = True
        shipment.picking_id.button_validate()

    def _book(self, name, warehouse_qty):
        product = self.env["product.product"].create({
            "name": name, "type": "consu", "is_storable": True,
            "list_price": 50.0})
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1)
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": product.id,
            "location_id": warehouse.lot_stock_id.id,
            "inventory_quantity": warehouse_qty,
        }).action_apply_inventory()
        return product

    def test_mapa_avulso_tour(self):
        partner = self.env["res.partner"].create({
            "name": "Livraria do Mapa", "is_company": True,
            "email": "geral.do.mapa@teste.com.br"})
        # O mapa vai para o contato de ACERTOS, não para a caixa geral.
        self.env["res.partner"].create({
            "name": "Acertos da Livraria do Mapa", "type": "settlement",
            "email": "acertos.do.mapa@teste.com.br",
            "parent_id": partner.id})
        agreement = self.env["consignment.agreement"].create({
            "partner_id": partner.id})
        agreement.action_activate()
        self._place_on_shelf(partner, self._book("Livro do Mapa", 40), 12)
        self.assertEqual(agreement.on_shelf_qty, 12,
                         "a semente tem de deixar 12 exemplares na prateleira")

        self.start_tour("/odoo", "soc_mapa_avulso_tour", login="admin")

        # O que o clique produziu, e não só que o toast apareceu.
        co = self.env["consignment.settlement"].search(
            [("partner_id", "=", partner.id)])
        self.assertEqual(len(co), 1, "o clique não abriu a operação do mês")
        self.assertEqual(co.line_ids.product_id.display_name, "Livro do Mapa")
        self.assertEqual(co.line_ids.qty_on_shelf, 12,
                         "a CO saiu sem a prateleira lida")
        # Pelo assunto: a CO nasce com dono, e a atribuição gera a sua própria
        # notificação por e-mail na mesma CO.
        mail = self.env["mail.mail"].sudo().search([
            ("model", "=", "consignment.settlement"), ("res_id", "=", co.id),
            ("subject", "like", "Mapa de Consignação")])
        self.assertEqual(len(mail), 1, "o clique não enfileirou o mapa")
        self.assertEqual(mail.recipient_ids.type, "settlement",
                         "o mapa não foi para o contato de Acertos")
        self.assertTrue(mail.attachment_ids, "o e-mail saiu sem o PDF do mapa")
        self.assertNotIn("mensagem automática", mail.body_html,
                         "o clique humano saiu marcado como automático")
        self.assertTrue(agreement.map_last_sent_date,
                        "o envio pela tela não carimbou o contrato")
