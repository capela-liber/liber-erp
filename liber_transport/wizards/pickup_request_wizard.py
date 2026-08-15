# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class PickupRequestWizard(models.TransientModel):
    """Solicitar coleta às transportadoras das entregas selecionadas.

    O agrupamento é a razão de ser do wizard: catorze entregas da Transpo
    são UM e-mail com uma tabela, não catorze e-mails. Cada linha do wizard
    é um grupo (transportadora, empresa) e é ela — não o picking — que o
    mail.template renderiza; é isso que dá um e-mail com N entregas.
    """
    _name = 'liber.transport.pickup.wizard'
    _description = 'Request Pickup from Carriers'

    line_ids = fields.One2many(
        'liber.transport.pickup.line', 'wizard_id', string='Pickup Requests')
    # Aviso, não bloqueio: uma entrega sem transportadora na seleção não pode
    # segurar a coleta das outras — ela aparece aqui e fica de fora do envio.
    no_carrier_picking_ids = fields.Many2many(
        'stock.picking', 'liber_transport_pickup_no_carrier_rel',
        string='Deliveries Without Carrier', readonly=True)

    @api.model
    def _pickup_groups(self):
        """Agrupa os pickings do contexto por (transportadora, empresa).

        Devolve (groups, no_carrier). É a única fonte da verdade: o
        default_get usa para MOSTRAR e o create usa para GRAVAR — o que o
        cliente mandar em line_ids é descartado, porque lista somente-leitura
        volta do navegador sem os valores (foi o "Valor obrigatório ausente
        para 'Transportadora'" em produção de teste).
        """
        pickings = self.env['stock.picking'].browse(
            self.env.context.get('active_ids', []))
        eligible = pickings.filtered(
            lambda p: p.picking_type_code == 'outgoing'
            and p.state != 'cancel')
        if not eligible:
            raise UserError(_(
                "Select at least one delivery order (outgoing transfer, "
                "not cancelled)."))
        no_carrier = eligible.filtered(lambda p: not p.carrier_id)
        groups = {}
        for picking in eligible - no_carrier:
            key = (picking.carrier_id, picking.company_id)
            groups.setdefault(key, self.env['stock.picking'])
            groups[key] |= picking
        return groups, no_carrier

    def _pickup_group_commands(self):
        groups, no_carrier = self._pickup_groups()
        return {
            'line_ids': [
                Command.create({
                    'carrier_id': carrier.id,
                    'company_id': company.id,
                    'picking_ids': [Command.set(group.ids)],
                })
                for (carrier, company), group in groups.items()
            ],
            'no_carrier_picking_ids': [Command.set(no_carrier.ids)],
        }

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        commands = self._pickup_group_commands()
        for field, value in commands.items():
            if field in fields_list:
                res[field] = value
        return res

    @api.model_create_multi
    def create(self, vals_list):
        commands = self._pickup_group_commands()
        for vals in vals_list:
            vals.pop('line_ids', None)
            vals.pop('no_carrier_picking_ids', None)
            vals.update(commands)
        return super().create(vals_list)

    def action_send(self):
        """Cria um lote (COL/) por transportadora e envia os que têm e-mail.

        O lote é registro de verdade: é nele que o e-mail fica, é para ele
        que a transportadora responde, e é ele que a logística acompanha
        depois. Transportadora sem e-mail também ganha lote — em rascunho,
        para não perder o trabalho de agrupar: completa-se o e-mail no
        contato e clica-se Enviar na ficha do lote.
        """
        self.ensure_one()
        Request = self.env['liber.transport.pickup.request']
        requests = Request
        sent = 0
        drafts = Request
        for line in self.line_ids:
            request = Request.create({
                'carrier_id': line.carrier_id.id,
                'company_id': line.company_id.id,
                'picking_ids': [Command.set(line.picking_ids.ids)],
            })
            requests |= request
            if line.email:
                request.action_send()
                sent += 1
            else:
                drafts |= request
        # Devolve o próprio lote (não um aviso): o assistente fecha e o
        # operador cai onde a solicitação passou a morar — que é o ponto
        # de ter lote. Rascunho aparece com o estado na cara, sem precisar
        # de toast para explicar que ficou faltando o e-mail.
        if len(requests) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': Request._name,
                'res_id': requests.id,
                'view_mode': 'form',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pickup Requests'),
            'res_model': Request._name,
            'view_mode': 'list,form',
            'domain': [('id', 'in', requests.ids)],
        }


class PickupRequestLine(models.TransientModel):
    _name = 'liber.transport.pickup.line'
    _description = 'Pickup Request per Carrier'

    wizard_id = fields.Many2one(
        'liber.transport.pickup.wizard', required=True, ondelete='cascade')
    carrier_id = fields.Many2one(
        'delivery.carrier', string='Carrier', required=True, readonly=True)
    partner_id = fields.Many2one(
        related='carrier_id.partner_id', string='Carrier Company')
    # O mesmo desvio do lote: quem recebe é a mesa de coletas quando existe.
    # Calculado aqui também para o operador ver o endereço ANTES de enviar.
    contact_id = fields.Many2one(
        'res.partner', string='Pickup Contact', compute='_compute_contact_id')
    email = fields.Char(related='contact_id.email', string='E-mail')
    company_id = fields.Many2one('res.company', required=True, readonly=True)
    picking_ids = fields.Many2many(
        'stock.picking', 'liber_transport_pickup_line_picking_rel',
        string='Delivery Orders', readonly=True)
    # O tamanho da carga, visível antes do envio: é por ele que a
    # transportadora escolhe o veículo.
    box_count = fields.Integer(string='Boxes', compute='_compute_totals')
    weight = fields.Float(
        string='Weight', digits='Stock Weight', compute='_compute_totals')

    @api.depends('carrier_id')
    def _compute_contact_id(self):
        for line in self:
            line.contact_id = line.carrier_id._pickup_contact()

    @api.depends('picking_ids.box_count', 'picking_ids.shipping_weight',
                 'picking_ids.weight')
    def _compute_totals(self):
        for line in self:
            line.box_count = sum(line.picking_ids.mapped('box_count'))
            line.weight = sum(
                p._liber_peso_para_transporte() for p in line.picking_ids)
