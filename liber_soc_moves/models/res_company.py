# -*- coding: utf-8 -*-
from odoo import fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Consignment gets its OWN warehouse operation types, separate from the
    # sales delivery types -- a consignment return is a "retorno de mercadoria",
    # not a generic internal transfer, and keeping them apart lets the warehouse
    # prioritise sales over consignment. Auto-created on first use; parametrised
    # in Settings.
    consignment_shipment_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Consignment Shipment Operation',
        domain="[('code', '=', 'internal')]",
        help="Warehouse operation type used for the internal shelf flows "
             "(warehouse -> customer shelf), numbered COM/MOV. Archived so it "
             "does not draw a card on the Inventory Overview: the remessa the "
             "warehouse actually works is the Pedido C's, on COM/OUT.")
    consignment_return_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Consignment Return Operation',
        domain="[('code', '=', 'internal')]",
        help="Warehouse operation type used for consignment returns "
             "(customer shelf -> warehouse). It is a merchandise return, not a "
             "generic internal transfer.")
    consignment_delivery_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Consignment Delivery Operation',
        domain="[('code', '=', 'outgoing')]",
        help="Warehouse operation type for Pedido C deliveries (warehouse -> "
             "customer). A consignment remessa on the generic Delivery Orders "
             "reads as a sale somebody forgot to invoice; it is not. "
             "Numbered COM/OUT/, its own series.")

    def _consignment_warehouse(self):
        self.ensure_one()
        return self.env['stock.warehouse'].search(
            [('company_id', '=', self.id)], limit=1)

    # Os tipos de operação nascem sozinhos, no primeiro uso, e por isso as
    # gravações abaixo são todas em `sudo()` -- a criação do stock.picking.type
    # já era, mas guardar o resultado no res.company não, e escrever em
    # res.company pede base.group_erp_manager. O efeito era que o PRIMEIRO
    # comercial a soltar uma remessa numa empresa recém-configurada levava um
    # AccessError; a partir da segunda vez, com o campo já preenchido, ninguém
    # via nada. Apareceu em 31/07/2026, ao testar a consignação com um usuário
    # que não é administrador (liber_roles/tests/test_logistica.py) -- é
    # exatamente o tipo de defeito que só um teste sem `su=True` acha.
    # Não há escalada de privilégio aqui: o valor gravado é um registro que o
    # próprio método acabou de criar, o usuário não o escolhe.
    def _create_consignment_operation_type(self, name, prefix, seq_name,
                                            code='internal'):
        self.ensure_one()
        warehouse = self._consignment_warehouse()
        seq = self.env['ir.sequence'].sudo().create({
            'name': seq_name,
            'prefix': prefix,
            'padding': 5,
            'company_id': self.id,
        })
        return self.env['stock.picking.type'].sudo().create({
            'name': name,
            'code': code,
            'sequence_id': seq.id,
            # 'COM/OUT/%(year)s/' -> 'COM/OUT' (and 'ACERTO/%(year)s/' ->
            # 'ACERTO'): the sequence_code is the prefix minus the year part.
            'sequence_code': prefix.replace('/%(year)s/', ''),
            'warehouse_id': warehouse.id if warehouse else False,
            'company_id': self.id,
        })

    def _get_consignment_delivery_operation_type(self):
        """The OUTGOING consignment operation -- what a Pedido C ships on.

        He caught it on the screen: C00003's delivery came out WH/OUT, on the
        warehouse's generic "Pedidos de entrega". A consignment remessa is not
        a sale delivery -- it needs its own operation type. Since the
        directional redesign it no longer shares a sequence with the shelf
        flows: the customer-facing remessa is COM/OUT, mirroring the core's
        WH/OUT; the internal shelf flows keep their own COM/MOV series.
        """
        self.ensure_one()
        if not self.consignment_delivery_operation_type_id:
            self.sudo().consignment_delivery_operation_type_id = \
                self._create_consignment_operation_type(
                    _('Consignment Delivery'), 'COM/OUT/%(year)s/',
                    'Consignment Delivery Operation', code='outgoing')
        return self.consignment_delivery_operation_type_id

    def _get_consignment_shipment_operation_type(self):
        """The INTERNAL shelf flow -- off the Overview since 19.0.2.7.0.

        Ele viu dois cartões de consignação lado a lado e perguntou qual era o
        abstrato: "Remessa de Consignação" (COM/MOV) e "Entrega de Consignação"
        (COM/OUT). Os nomes diziam o contrário do que cada um faz -- o que se
        chamava Remessa era o movimento interno de prateleira, e o que se
        chamava Entrega era a remessa física do Pedido C.

        E o COM/MOV não é mais alcançável: a `consignment.move` virou o CR, cuja
        ação tem domínio `move_kind = 'return'` e `create: False`, e a reposição
        disparada pelo acerto nasce como Pedido C. Sobrou um cartão vazio
        pedindo trabalho que ninguém pode criar.

        Mesma saída do ACERTO (13/08/2026, opção A): o tipo continua existindo
        -- o histórico das bases antigas tem número e nome --, mas nasce
        arquivado e some da Visão geral.
        """
        self.ensure_one()
        if not self.consignment_shipment_operation_type_id:
            operation_type = \
                self._create_consignment_operation_type(
                    # COM/MOV/, seguindo o padrão direcional do core (WH/OUT,
                    # WH/IN): a remessa ao cliente é COM/OUT, o retorno é
                    # COM/IN, e os fluxos internos de prateleira ficam em
                    # COM/MOV -- sequence própria, que não divide mais com a
                    # remessa. Como no precedente REM->COM, bases antigas
                    # precisam de UPDATE em ir_sequence + sequence_code: é a
                    # migração 19.0.2.6.0 (só as séries mudam; documento já
                    # emitido NUNCA muda de nome).
                    _('Consignment Shipment'), 'COM/MOV/%(year)s/',
                    'Consignment Shipment Operation')
            operation_type.sudo().active = False
            self.sudo().consignment_shipment_operation_type_id = operation_type
        return self.consignment_shipment_operation_type_id

    def _get_consignment_return_operation_type(self):
        self.ensure_one()
        if not self.consignment_return_operation_type_id:
            self.sudo().consignment_return_operation_type_id = \
                self._create_consignment_operation_type(
                    _('Consignment Return'), 'COM/IN/%(year)s/',
                    'Consignment Return Operation')
        return self.consignment_return_operation_type_id
