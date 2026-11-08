# -*- coding: utf-8 -*-
from odoo import _, fields, models


# O texto padrão do e-mail do mapa mensal, o mesmo do `t-else` do template
# `mail_template_consignment_map` (variante da prateleira). Mora aqui para nascer
# no campo e ser editado a partir dele; o do template é a rede do campo vazio.
# Sem o número da CO no corpo: ele já vai no assunto.
MAP_EMAIL_SUBJECT_DEFAULT = 'Mapa de Consignação'
MAP_EMAIL_TEXT_DEFAULT = (
    '<p>Prezados,</p>'
    '<p>Segue em anexo o <strong>Mapa de Consignação</strong>, com a posição '
    'atual da mercadoria que temos em consignação na sua loja.</p>'
    '<p>Confira com a sua prateleira. Encontrando diferença, ou querendo '
    '<strong>devolver</strong> o que não girou ou <strong>repor</strong> o '
    'que vendeu, basta <strong>responder este e-mail</strong>.</p>')


class ResCompany(models.Model):
    _inherit = 'res.company'

    # The settlement baixa (customer shelf -> customer) is the acerto sale
    # leaving the shelf. It is NOT a warehouse delivery: it does not pick from
    # our stock, it only draws down the customer's shelf. Giving it its own
    # operation type + sequence (ACERTO/, not WH/OUT/) keeps it out of the
    # warehouse's Delivery Orders and stops it reading as a pending WH job.
    # Auto-created on first use, like the shipment/return types in soc_moves.
    #
    # And created ARCHIVED (13/08/2026). Keeping it out of WH/OUT was only half
    # the job: the type still drew its own card on the Inventory Overview, and
    # the commercial team read "Acerto de Consignação" there as a warehouse job
    # somebody had to confirm. There is no job. The picking is created and
    # validated inside the same Run click; nobody picks, packs or confirms it.
    #
    # Archiving takes the card off the warehouse's screen and costs nothing:
    # a stock.picking created against an archived type is created, confirmed
    # and validated normally (only *searches* drop it, which is precisely the
    # Overview), the ACERTO/ numbering is untouched and the shelf is still
    # debited. The alternative -- dropping the picking for a bare stock.move --
    # would have taken the baixa's name and document with it (option B, refused
    # 13/08/2026).
    consignment_settlement_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Consignment Settlement Operation',
        domain="[('code', '=', 'outgoing')]",
        help="Warehouse operation type used for the settlement baixa (customer "
             "shelf -> customer): the acerto sale leaving the shelf. Kept apart "
             "from the generic delivery orders (WH/OUT), and archived so it does "
             "not show as a job on the Inventory Overview.")

    def _get_consignment_settlement_operation_type(self):
        self.ensure_one()
        if not self.consignment_settlement_operation_type_id:
            operation_type = self._create_consignment_operation_type(
                _('Consignment Settlement'), 'ACERTO/%(year)s/',
                'Consignment Settlement Operation', code='outgoing')
            operation_type.sudo().active = False
            self.sudo().consignment_settlement_operation_type_id = operation_type
        return self.consignment_settlement_operation_type_id

    consignment_map_text = fields.Html(
        string='Consignment Map Text',
        help="Standard text printed at the top of the consignment map (CO) that "
             "is printed or e-mailed to the customer. Editable in the Consignment "
             "settings.")
    # O texto do E-MAIL do disparo mensal (o de cima é o do PDF). Vale só no
    # automático e só no mapa da prateleira (CO sem operação): o clique humano
    # -- botão, lote, compositor -- e a CO com acerto seguem com o texto do
    # template. Nasce preenchido com o padrão, para se editar a partir dele.
    consignment_map_email_subject = fields.Char(
        string='Monthly Map E-mail Subject', default=MAP_EMAIL_SUBJECT_DEFAULT,
        help="Subject of the monthly map e-mail sent by the scheduled dispatch. "
             "The operation number (CO) is always appended. Leave empty to use "
             "the built-in default.")
    consignment_map_email_text = fields.Html(
        string='Monthly Map E-mail Text', default=MAP_EMAIL_TEXT_DEFAULT,
        help="Body of the monthly map e-mail sent by the scheduled dispatch, "
             "replacing the built-in opening text. The signature and the "
             "automatic-message notice are still added. Leave empty to use the "
             "built-in default.")
    return_escalation_manager_id = fields.Many2one(
        'res.users', string='Return Escalation Manager',
        help="Who gets notified when a consignment return (CR) blows past its "
             "tolerable window (the last rung of the dunning ladder). Editable in "
             "the Consignment settings.")
    return_request_text = fields.Html(
        string='Return Request Text',
        help="Standard intro text of the return-request e-mail (CR) sent to the "
             "customer when a return is overdue. Editable in the Consignment "
             "settings.")
