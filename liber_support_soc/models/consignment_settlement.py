# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ConsignmentSettlement(models.Model):
    _inherit = 'consignment.settlement'

    support_ticket_ids = fields.One2many(
        'liber.support.ticket', 'settlement_id',
        string='Support Tickets')
    support_ticket_count = fields.Integer(
        compute='_compute_support_ticket_count')

    @api.depends('support_ticket_ids')
    def _compute_support_ticket_count(self):
        """Conta com `sudo`, e o porquê custou um Access Error.

        Este campo é lido ao abrir QUALQUER CO — é ele que acende (ou não) o
        botão dos chamados. Lido com o direito do usuário, ele exige o
        Atendimento de quem só opera consignação, e a ficha inteira morre com
        "You are not allowed to access 'Support Ticket'". Hoje o Comercial tem
        os dois grupos e não sentia; o Visitante, que tem `group_soc_user` e
        não tem atendimento, sentia. Apareceu no tour do "Importar" (01/09),
        logado como comercial pelado — que é exatamente para isso que a regra
        manda o tour rodar no perfil real, e não como admin.

        Contar não vaza nada: o BOTÃO continua atrás do grupo do Atendimento
        (ver a view), e quem não o tem não abre a lista.
        """
        contagem = dict(
            self.env['liber.support.ticket'].sudo()._read_group(
                [('settlement_id', 'in', self.ids)],
                ['settlement_id'], ['__count']))
        for settlement in self:
            settlement.support_ticket_count = contagem.get(settlement, 0)

    def action_view_support_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'liber_support.action_support_ticket')
        action['domain'] = [('settlement_id', '=', self.id)]
        action['context'] = {
            'default_settlement_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_company_id': self.company_id.id,
            'default_kind': 'consignment',
            'default_channel': 'manual',
        }
        return action

    def action_open_co_wizard(self):
        """O mesmo assistente do atendimento, agora partindo da CO.

        O atendimento ativo da consignação anda no sentido inverso do
        reativo: em vez de um e-mail que chega e vira documento, é a pessoa
        que parte da CO da livraria, escreve para ela, e a resposta —
        e-mail, colagem do Excel, planilha, PDF ou XML de NFe — precisa
        voltar para DENTRO daquela CO. O mecanismo de conferência é o
        mesmo, e reaproveitá-lo (em vez de escrever um segundo importador)
        é o ponto: o parser, a checagem de CNPJ das duas pontas da NFe e o
        rascunho que sobrevive à interrupção já estão provados aqui.

        Só em rascunho: depois do Run a CO virou o mapa que a livraria
        recebeu, e somar linha nela mudaria uma apuração já entregue."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_(
                "%(name)s is not a draft any more: it was already run. "
                "Open a new consignment to import into.", name=self.name))
        return self.env['liber.support.co.wizard']._open_for(self)
