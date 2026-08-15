# -*- coding: utf-8 -*-
"""O que estes testes guardam:

- a saída nasce com a transportadora do cliente (property), com o fallback
  ao commercial_partner quando o endereço de entrega filho não tem a sua;
- o hook nunca sobrescreve carrier que veio nos vals, nem vaza para
  entradas, pickings sem parceiro ou carriers de outra empresa;
- o wizard de coleta agrupa por transportadora (um e-mail com N entregas,
  nunca N e-mails), pula transportadora sem e-mail contando o skip, avisa
  das entregas sem transportadora sem bloquear as demais, e carimba
  pickup_request_date + nota no chatter de cada movimento.

Regra da casa: nunca criar res.company em teste (quebra no NOT NULL de
fiscalyear_last_day com account instalado) — reaproveitar env.company.
"""
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests.common import TransactionCase


class TestLiberTransport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # O testing é cópia do prod e traz um ir.default global de
        # property_delivery_carrier_id ("Entrega local"): todo parceiro novo
        # já "tem" transportadora, e o cliente-sem-carrier destes testes não
        # existiria. Remover o default dentro da transação (o rollback do
        # TransactionCase devolve) deixa o mundo determinístico.
        cls.env['ir.default'].search([
            ('field_id.model', '=', 'res.partner'),
            ('field_id.name', '=', 'property_delivery_carrier_id'),
        ]).unlink()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.out_type = cls.warehouse.out_type_id
        cls.in_type = cls.warehouse.in_type_id
        cls.customer_location = cls.env.ref('stock.stock_location_customers')

        cls.delivery_product = cls.env['product.product'].create({
            'name': 'Test Freight', 'type': 'service', 'sale_ok': False})

        # Transpo: transportadora completa, com e-mail — o caminho feliz.
        cls.transpo_partner = cls.env['res.partner'].create({
            'name': 'Transpo Express',
            'email': 'coletas@transpoexpress.com.br'})
        cls.carrier_transpo = cls.env['delivery.carrier'].create({
            'name': 'Transpo', 'delivery_type': 'fixed',
            'product_id': cls.delivery_product.id,
            'partner_id': cls.transpo_partner.id})

        # Beta: segunda transportadora com e-mail, para o agrupamento.
        cls.beta_partner = cls.env['res.partner'].create({
            'name': 'Beta Logística', 'email': 'coleta@betalog.com.br'})
        cls.carrier_beta = cls.env['delivery.carrier'].create({
            'name': 'Beta', 'delivery_type': 'fixed',
            'product_id': cls.delivery_product.id,
            'partner_id': cls.beta_partner.id})

        # Mudo: transportadora cujo contato não tem e-mail — o skip.
        cls.mudo_partner = cls.env['res.partner'].create({
            'name': 'Carreto Mudo'})
        cls.carrier_mudo = cls.env['delivery.carrier'].create({
            'name': 'Mudo', 'delivery_type': 'fixed',
            'product_id': cls.delivery_product.id,
            'partner_id': cls.mudo_partner.id})

        # Gama: transportadora com mesa de coletas (contato de Entregas
        # DENTRO da transportadora, com e-mail próprio).
        cls.gama_partner = cls.env['res.partner'].create({
            'name': 'Rodo Gama', 'is_company': True,
            'email': 'faleconosco@rodogama.com.br'})
        cls.gama_coletas = cls.env['res.partner'].create({
            'name': 'Rodo Gama — Coletas', 'type': 'delivery',
            'parent_id': cls.gama_partner.id,
            'email': 'coletas@rodogama.com.br'})
        cls.carrier_gama = cls.env['delivery.carrier'].create({
            'name': 'Gama', 'delivery_type': 'fixed',
            'product_id': cls.delivery_product.id,
            'partner_id': cls.gama_partner.id})

        cls.customer = cls.env['res.partner'].create({
            'name': 'Livraria Catavento', 'city': 'São Paulo'})
        cls.customer.property_delivery_carrier_id = cls.carrier_transpo
        cls.shipping_child = cls.env['res.partner'].create({
            'name': 'Catavento Depósito', 'type': 'delivery',
            'parent_id': cls.customer.id})
        # Cliente sem transportadora nenhuma.
        cls.plain_customer = cls.env['res.partner'].create({
            'name': 'Banca Avulsa'})

    def _make_outgoing(self, partner, **vals):
        return self.env['stock.picking'].create({
            'picking_type_id': self.out_type.id,
            'partner_id': partner.id if partner else False,
            'location_id': self.out_type.default_location_src_id.id,
            'location_dest_id': self.customer_location.id,
            **vals,
        })

    def _make_wizard(self, pickings):
        return self.env['liber.transport.pickup.wizard'].with_context(
            active_model='stock.picking', active_ids=pickings.ids).create({})

    def _pickup_mails(self):
        return self.env['mail.mail'].search(
            [('model', '=', 'liber.transport.pickup.request')])

    def _requests(self):
        return self.env['liber.transport.pickup.request'].search([])

    # --- autofill do carrier na criação do picking -----------------------

    def test_autofill_from_customer(self):
        picking = self._make_outgoing(self.customer)
        self.assertEqual(picking.carrier_id, self.carrier_transpo)

    def test_autofill_fallback_commercial_partner(self):
        # O endereço de entrega filho não tem property própria: vale a da mãe.
        picking = self._make_outgoing(self.shipping_child)
        self.assertEqual(picking.carrier_id, self.carrier_transpo)

    def test_autofill_does_not_override_or_leak(self):
        explicit = self._make_outgoing(
            self.customer, carrier_id=self.carrier_beta.id)
        self.assertEqual(explicit.carrier_id, self.carrier_beta,
                         "carrier vindo nos vals não pode ser sobrescrito")
        incoming = self.env['stock.picking'].create({
            'picking_type_id': self.in_type.id,
            'partner_id': self.customer.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.in_type.default_location_dest_id.id,
        })
        self.assertFalse(incoming.carrier_id,
                         "entrada não ganha transportadora")
        no_partner = self._make_outgoing(None)
        self.assertFalse(no_partner.carrier_id)
        no_property = self._make_outgoing(self.plain_customer)
        self.assertFalse(no_property.carrier_id)

    def test_autofill_respects_company(self):
        other = self.env['res.company'].search(
            [('id', '!=', self.company.id)], limit=1)
        if not other:
            self.skipTest("banco de teste com uma empresa só")
        foreign_product = self.env['product.product'].create({
            'name': 'Foreign Freight', 'type': 'service',
            'company_id': other.id})
        foreign_carrier = self.env['delivery.carrier'].create({
            'name': 'Foreign', 'delivery_type': 'fixed',
            'product_id': foreign_product.id})
        self.customer.property_delivery_carrier_id = foreign_carrier
        picking = self._make_outgoing(self.customer)
        self.assertFalse(picking.carrier_id,
                         "carrier de outra empresa não pode ser aplicado")

    def test_so_flow_picking_gets_carrier(self):
        product = self.env['product.product'].create({
            'name': 'Livro de Teste', 'type': 'consu'})
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({
                'product_id': product.id, 'product_uom_qty': 1})],
        })
        order.action_confirm()
        self.assertTrue(order.picking_ids)
        self.assertEqual(order.picking_ids.carrier_id, self.carrier_transpo)

    # --- wizard de coleta -------------------------------------------------

    def test_wizard_groups_one_mail_per_carrier(self):
        transpo_pickings = (self._make_outgoing(self.customer)
                            | self._make_outgoing(self.customer)
                            | self._make_outgoing(self.customer))
        beta_pickings = (
            self._make_outgoing(self.plain_customer,
                                carrier_id=self.carrier_beta.id)
            | self._make_outgoing(self.plain_customer,
                                  carrier_id=self.carrier_beta.id))
        all_pickings = transpo_pickings | beta_pickings
        messages_before = {p.id: len(p.message_ids) for p in all_pickings}

        wizard = self._make_wizard(all_pickings)
        self.assertEqual(len(wizard.line_ids), 2,
                         "uma linha por transportadora, não por picking")
        self.assertFalse(wizard.no_carrier_picking_ids)

        mails_before = self._pickup_mails()
        requests_before = self._requests()
        result = wizard.action_send()
        new_mails = self._pickup_mails() - mails_before
        new_requests = self._requests() - requests_before

        self.assertEqual(len(new_requests), 2,
                         "um lote por transportadora, não por entrega")
        self.assertEqual(len(new_mails), 2,
                         "um e-mail por transportadora, nunca por entrega")
        transpo_request = new_requests.filtered(
            lambda r: r.carrier_id == self.carrier_transpo)
        self.assertEqual(len(transpo_request), 1)
        self.assertEqual(transpo_request.picking_ids, transpo_pickings)
        self.assertEqual(transpo_request.state, 'sent')
        self.assertTrue(transpo_request.request_date)
        self.assertTrue(transpo_request.name.startswith('COL/'),
                        "o lote nasce numerado: %s" % transpo_request.name)

        # o e-mail fica no histórico do lote, com a tabela das entregas
        corpo = transpo_request.message_ids.filtered(
            lambda m: m.message_type == 'comment').body
        for picking in transpo_pickings:
            self.assertIn(picking.name, corpo,
                          "a tabela lista cada entrega do lote")
        transpo_mail = new_mails.filtered(
            lambda m: self.transpo_partner in m.recipient_ids)
        self.assertEqual(len(transpo_mail), 1)

        for picking in all_pickings:
            self.assertTrue(picking.pickup_request_date)
            self.assertEqual(len(picking.pickup_request_ids), 1,
                             "a entrega aponta para o lote que a pediu")
            self.assertEqual(len(picking.message_ids),
                             messages_before[picking.id] + 1,
                             "o pedido de coleta fica no chatter da entrega")
            nota = picking.message_ids.sorted('id')[-1].body
            self.assertIn(picking.pickup_request_ids.name, nota,
                          "a nota cita o lote")
        self.assertEqual(result['res_model'], 'liber.transport.pickup.request',
                         "o assistente entrega os lotes criados")

    def test_wizard_leaves_draft_when_carrier_has_no_email(self):
        picking = self._make_outgoing(self.plain_customer,
                                      carrier_id=self.carrier_mudo.id)
        wizard = self._make_wizard(picking)
        mails_before = self._pickup_mails()
        requests_before = self._requests()
        result = wizard.action_send()
        new_requests = self._requests() - requests_before
        self.assertEqual(self._pickup_mails(), mails_before,
                         "transportadora sem e-mail não gera mail")
        self.assertEqual(len(new_requests), 1,
                         "o agrupamento não se perde: vira lote em rascunho")
        self.assertEqual(new_requests.state, 'draft')
        self.assertFalse(picking.pickup_request_date)
        self.assertEqual(result.get('res_id'), new_requests.id,
                         "cai na ficha do rascunho, que mostra o que falta")

    def test_request_send_without_email_raises(self):
        picking = self._make_outgoing(self.plain_customer,
                                      carrier_id=self.carrier_mudo.id)
        request = self.env['liber.transport.pickup.request'].create({
            'carrier_id': self.carrier_mudo.id,
            'company_id': self.company.id,
            'picking_ids': [Command.set(picking.ids)],
        })
        with self.assertRaises(UserError):
            request.action_send()

    def test_request_lifecycle(self):
        picking = self._make_outgoing(self.customer)
        request = self.env['liber.transport.pickup.request'].create({
            'carrier_id': self.carrier_transpo.id,
            'company_id': self.company.id,
            'picking_ids': [Command.set(picking.ids)],
        })
        self.assertEqual(request.state, 'draft')
        self.assertEqual(request.picking_count, 1)
        request.action_send()
        self.assertEqual(request.state, 'sent')
        primeira_data = request.request_date
        request.action_done()
        self.assertEqual(request.state, 'done')
        request.action_cancel()
        self.assertEqual(request.state, 'cancel')
        with self.assertRaises(UserError):
            request.action_send()
        request.action_draft()
        request.action_send()
        self.assertEqual(request.state, 'sent')
        self.assertGreaterEqual(request.request_date, primeira_data,
                                "reenvio atualiza a data do pedido")

    def test_wizard_warns_no_carrier_without_blocking(self):
        with_carrier = self._make_outgoing(self.customer)
        without_carrier = self._make_outgoing(self.plain_customer)
        wizard = self._make_wizard(with_carrier | without_carrier)
        self.assertEqual(wizard.no_carrier_picking_ids, without_carrier)
        self.assertEqual(len(wizard.line_ids), 1)
        wizard.action_send()
        self.assertTrue(with_carrier.pickup_request_date)
        self.assertFalse(without_carrier.pickup_request_date,
                         "quem ficou de fora não ganha carimbo")

    def test_wizard_nothing_eligible_raises(self):
        incoming = self.env['stock.picking'].create({
            'picking_type_id': self.in_type.id,
            'partner_id': self.customer.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.in_type.default_location_dest_id.id,
        })
        with self.assertRaises(UserError):
            self._make_wizard(incoming)

    # --- a quem se escreve na transportadora ------------------------------

    def test_pickup_contact_prefers_delivery_desk(self):
        picking = self._make_outgoing(self.plain_customer,
                                      carrier_id=self.carrier_gama.id)
        wizard = self._make_wizard(picking)
        self.assertEqual(wizard.line_ids.contact_id, self.gama_coletas,
                         "a mesa de coletas ganha do e-mail geral da empresa")
        self.assertEqual(wizard.line_ids.email, 'coletas@rodogama.com.br')
        requests = self.env['liber.transport.pickup.request'].search([])
        wizard.action_send()
        novo = self.env['liber.transport.pickup.request'].search([]) - requests
        self.assertEqual(novo.contact_id, self.gama_coletas)
        mail = self._pickup_mails().sorted('id')[-1]
        self.assertIn(self.gama_coletas, mail.recipient_ids,
                      "o e-mail vai para a mesa de coletas")

    def test_pickup_contact_falls_back_to_company(self):
        request = self.env['liber.transport.pickup.request'].create({
            'carrier_id': self.carrier_transpo.id,
            'company_id': self.company.id,
        })
        self.assertEqual(request.contact_id, self.transpo_partner,
                         "sem mesa de coletas, escreve-se à empresa")

    def test_pickup_contact_ignores_delivery_desk_without_email(self):
        mudo_desk = self.env['res.partner'].create({
            'name': 'Carreto Mudo — Coletas', 'type': 'delivery',
            'parent_id': self.mudo_partner.id})
        self.mudo_partner.email = 'contato@carretomudo.com.br'
        request = self.env['liber.transport.pickup.request'].create({
            'carrier_id': self.carrier_mudo.id,
            'company_id': self.company.id,
        })
        self.assertNotEqual(request.contact_id, mudo_desk)
        self.assertEqual(request.contact_id, self.mudo_partner,
                         "mesa de coletas sem e-mail não serve de destino")

    def test_email_from_is_the_house_not_the_clerk(self):
        picking = self._make_outgoing(self.customer)
        request = self.env['liber.transport.pickup.request'].create({
            'carrier_id': self.carrier_transpo.id,
            'company_id': self.company.id,
            'picking_ids': [Command.set(picking.ids)],
        })
        request.action_send()
        mail = self._pickup_mails().sorted('id')[-1]
        esperado = self.company.email_formatted or self.env.user.email_formatted
        self.assertEqual(mail.email_from, esperado,
                         "a coleta sai pelo endereço da casa, não do usuário")

    # --- caixas e peso na coleta ------------------------------------------

    def test_lote_soma_caixas_e_peso_das_entregas(self):
        um = self._make_outgoing(self.customer)
        outro = self._make_outgoing(self.customer)
        um.box_count = 3
        outro.box_count = 2
        um.shipping_weight = 4.5
        outro.shipping_weight = 1.25
        request = self.env['liber.transport.pickup.request'].create({
            'carrier_id': self.carrier_transpo.id,
            'company_id': self.company.id,
            'picking_ids': [Command.set((um | outro).ids)],
        })
        self.assertEqual(request.total_box_count, 5)
        self.assertAlmostEqual(request.total_weight, 5.75, places=3)

    def test_email_da_coleta_leva_caixas_e_peso(self):
        picking = self._make_outgoing(self.customer)
        picking.box_count = 7
        picking.shipping_weight = 12.5
        request = self.env['liber.transport.pickup.request'].create({
            'carrier_id': self.carrier_transpo.id,
            'company_id': self.company.id,
            'picking_ids': [Command.set(picking.ids)],
        })
        request.action_send()
        corpo = request.message_ids.filtered(
            lambda m: m.message_type == 'comment').body
        self.assertIn('Caixas', corpo)
        self.assertIn('>7<', corpo, "a contagem de caixas vai na tabela")
        self.assertIn('12.500', corpo, "o peso vai com três casas")

    def test_wizard_mostra_o_tamanho_da_carga(self):
        um = self._make_outgoing(self.customer)
        outro = self._make_outgoing(self.customer)
        um.box_count = 2
        outro.box_count = 1
        um.shipping_weight = 3.0
        wizard = self._make_wizard(um | outro)
        self.assertEqual(wizard.line_ids.box_count, 3)
        self.assertAlmostEqual(wizard.line_ids.weight, 3.0, places=3)

    def test_cadastrar_peso_alcanca_a_entrega_que_nao_saiu(self):
        """O peso do movimento é armazenado: sem isto, cadastrar o peso do
        livro depois deixava a transferência marcando zero na tela."""
        produto = self.env['product.product'].create({
            'name': 'Livro Sem Peso Ainda', 'type': 'consu'})
        picking = self._make_outgoing(self.customer)
        self.env['stock.move'].create({
            'picking_id': picking.id,
            'product_id': produto.id, 'product_uom_qty': 4,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
        })
        self.assertEqual(picking.weight, 0.0)

        produto.weight = 0.25

        self.assertAlmostEqual(picking.weight, 1.0, places=3,
                               msg="4 livros de 0,25 kg")
        self.assertAlmostEqual(picking._liber_peso_para_transporte(), 1.0,
                               places=3)

    def test_entrega_ja_concluida_guarda_o_peso_da_epoca(self):
        """O que saiu pesou o que pesava: história não se reescreve."""
        produto = self.env['product.product'].create({
            'name': 'Livro Despachado', 'type': 'consu', 'weight': 0.2})
        picking = self._make_outgoing(self.customer)
        move = self.env['stock.move'].create({
            'picking_id': picking.id,
            'product_id': produto.id, 'product_uom_qty': 2,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
        })
        self.assertAlmostEqual(move.weight, 0.4, places=3)
        move.state = 'done'

        produto.weight = 5.0

        self.assertAlmostEqual(move.weight, 0.4, places=3,
                               msg="movimento concluído não é recalculado")

