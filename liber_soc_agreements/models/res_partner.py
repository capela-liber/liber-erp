# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    allow_consignment = fields.Boolean(string='Allows Consignment')
    consignment_location_id = fields.Many2one(
        'stock.location', string='Consignment Shelf',
        help="Internal location holding our stock placed at this customer.")
    # OS DOIS CAMPOS SÃO DO GRUPO, E NÃO DA FICHA (20/08/2026). Eles LEEM
    # `consignment.agreement`, cujo ACL é dos grupos da consignação -- e a
    # ficha de contato é de todo mundo. Sem o `groups=` aqui, o cartão de
    # Consignação entrava no formulário de qualquer um e o compute estourava
    # `You are not allowed to access 'Consignment Agreement'` ANTES de a tela
    # abrir: dez das treze funções da casa (todas menos o Comercial, a Direção
    # e o Visitante) não conseguiam abrir contato nenhum.
    #
    # Com `groups=`, o ORM tira o campo do arch e nunca chama o compute para
    # quem não é da consignação. O botão no XML repete a marca -- ver
    # views/res_partner_views.xml, e o porquê de serem os dois.
    #
    # A saída alternativa seria `compute_sudo=True`, e ela está errada: faria
    # o número aparecer para quem não tem o app. O cartão é informação de
    # consignação, não do cadastro.
    consignment_agreement_ids = fields.One2many(
        'consignment.agreement', 'partner_id', string='Consignment Agreements',
        groups='liber_soc_agreements.group_soc_user')
    consignment_agreement_count = fields.Integer(
        string='# Consignment Agreements',
        compute='_compute_consignment_agreement_count',
        groups='liber_soc_agreements.group_soc_user')

    def _soc_sales_channel(self, company=None):
        """The customer's sales channel, read in the DOCUMENT's company.

        The channel lives on `res.partner.team_id`, which the
        `liber_partner_commercial` module puts back (Odoo 19 removed it). This
        stack does NOT depend on that module -- a house that only consigns
        should not be forced to install it -- so the read is guarded, the same
        way `liber_nfe_xml` guards it.

        The field is `company_dependent`: the same customer may be of one
        channel in one publisher and another elsewhere, so the company matters
        and is never guessed.

        Falls back UP THE TREE, and not through `commercial_partner_id`: a
        branch with its own tax ID is `is_company`, so it is its own commercial
        partner and the shortcut would never reach the head office. The channel
        is a property of the ACCOUNT, so a branch with an empty card inherits
        from whoever it hangs from.
        """
        self.ensure_one()
        if 'team_id' not in self._fields:
            return self.env['crm.team']
        empresa = company or self.env.company
        no = self
        while no:
            canal = no.with_company(empresa).team_id
            if canal:
                return canal
            no = no.parent_id
        return self.env['crm.team']

    def _compute_consignment_agreement_count(self):
        groups = self.env['consignment.agreement']._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count'])
        counts = {partner.id: count for partner, count in groups}
        for partner in self:
            partner.consignment_agreement_count = counts.get(partner.id, 0)

    def action_view_consignment_agreements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consignment Agreements'),
            'res_model': 'consignment.agreement',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
