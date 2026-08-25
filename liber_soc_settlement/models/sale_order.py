# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    """The stamp that makes a campaign measurable.

    Placement is a live calculation -- target of the running campaign against
    today's shelf -- and needs no trace. A SALE is not: it happens later, on
    another document, and no live calculation can attribute it back to the
    campaign that put the book on the shelf.

    So the campaigns that drove an operation are stamped on the orders it fires,
    at the moment it fires them. This costs nothing today. Without it, whatever
    goes out unstamped can never be attributed to anything, ever.
    """
    _inherit = 'sale.order'

    campaign_ids = fields.Many2many(
        'consignment.template', 'sale_order_campaign_rel', 'order_id', 'campaign_id',
        string='Campaigns', copy=False, readonly=True,
        help="The campaigns of the consignment operation that generated this "
             "order. On a replenishment (C) they are the reason it went out; on a "
             "sale (S) they were running on the shelf that sold.")

    # ------------------------------------------------------------------
    # O aviso do Pedido C avulso
    # ------------------------------------------------------------------
    consignment_recipient_ids = fields.Many2many(
        'res.partner', 'sale_order_soc_recipient_rel', 'order_id', 'partner_id',
        string='Consignment Recipients',
        compute='_compute_consignment_recipient_ids',
        help="Who gets the consignment order by e-mail: the customer's Buyer "
             "contacts, who authorise incoming goods.")

    @api.depends('partner_id', 'is_consignment')
    def _compute_consignment_recipient_ids(self):
        """O COMPRADOR da livraria: quem autoriza a entrada de mercadoria.

        Num campo pelo mesmo motivo do mapa: o modelo de e-mail não consegue
        chamar método que começa com `_`, e endereço escrito à mão no template
        é endereço que ninguém encontra quando a regra muda.
        """
        for order in self:
            order.consignment_recipient_ids = (
                order.partner_id._soc_contacts('buyer')
                if order.is_consignment and order.partner_id
                else self.env['res.partner'])

    def _is_standalone_consignment_order(self):
        """Pedido C de ABERTURA: consignação que não nasceu de um acerto.

        A reposição que sai de uma CO não passa por aqui: ela já é anunciada
        pelo mapa daquela CO, que nesse caso vai também para o Comprador. Dois
        e-mails para a mesma pessoa sobre a mesma remessa é treinar o Comprador
        a não ler.
        """
        self.ensure_one()
        return self.is_consignment and not self.consignment_operation_id

    def _soc_order_responsible(self):
        return self.env['res.partner']._soc_first_person(
            self.user_id, self.partner_id.user_id,
            self.company_id.return_escalation_manager_id)

    def _notify_consignment_order(self):
        """Manda o pedido ao Comprador; sem Comprador, abre tarefa.

        Mesma régua do mapa, e de propósito: papel que não tem para quem ir
        vira trabalho de cadastro para quem cuida da conta, e não silêncio.
        """
        self.ensure_one()
        template = self.env.ref(
            'liber_soc_settlement.mail_template_consignment_order',
            raise_if_not_found=False)
        if not template:
            return False
        if any(p.email for p in self.consignment_recipient_ids):
            template.with_company(self.company_id).send_mail(
                self.id, force_send=False)
            return True
        responsavel = self._soc_order_responsible()
        if not responsavel:
            _logger.warning(
                "Pedido de consignação %s (%s): sem Comprador e sem "
                "responsável. Ninguém foi avisado.",
                self.name, self.partner_id.display_name)
            return False
        pedido = self.with_context(lang=responsavel.lang or self.env.lang)
        resumo = pedido._missing_buyer_summary()
        if self.env['mail.activity'].sudo().search_count([
                ('res_model', '=', self._name), ('res_id', '=', self.id),
                ('summary', '=', resumo)]):
            return False
        pedido.sudo().activity_schedule(
            'mail.mail_activity_data_todo',
            summary=resumo,
            note=_("The consignment order %(order)s of %(customer)s was "
                   "confirmed but not e-mailed: they have no Buyer contact "
                   "with an e-mail address. Please add a contact of type Buyer "
                   "on the customer, with the e-mail of whoever authorises "
                   "incoming goods.",
                   order=self.name, customer=self.partner_id.display_name),
            user_id=responsavel.id)
        return False

    def _missing_buyer_summary(self):
        return _("Consignment order: no Buyer contact with e-mail")

    def action_confirm(self):
        """Confirmar o Pedido C avulso avisa o Comprador, com o PDF junto."""
        res = super().action_confirm()
        for order in self:
            if not order._is_standalone_consignment_order():
                continue
            try:
                with self.env.cr.savepoint():
                    order._notify_consignment_order()
            except Exception:
                # O aviso não pode derrubar a confirmação: o pedido é o ato,
                # o e-mail é o recado.
                _logger.exception(
                    "Pedido de consignação %s: falha ao avisar o Comprador",
                    order.name)
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        """The acerto's revenue sale never delivers from the warehouse.

        The physical baixa already happened off the customer's shelf -- the
        ACERTO picking the operation (CO) validated. Letting this sale confirm
        its own WH/OUT delivery would move the same books a second time and drag
        the acerto back into the warehouse, which is exactly what an acerto must
        not do: it only draws down the customer's shelf. The sale exists to
        invoice (invoice_policy 'order'), not to deliver.

        Only the acerto's *revenue* sale is held back (consignment_operation_id
        set, is_consignment False). The consignment Pedidos (C) still deliver
        normally -- they physically refill the shelf.
        """
        deliverable = self.filtered(
            lambda l: not (l.order_id.consignment_operation_id
                           and not l.order_id.is_consignment))
        return super(SaleOrderLine, deliverable)._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty)
