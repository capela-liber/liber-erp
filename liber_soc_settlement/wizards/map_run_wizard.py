# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class MapRunWizard(models.TransientModel):
    """Controlled batch ("RUN") to email the Consignment Map.

    Unlike a selection-based action (where the operator could pick old COs by
    mistake and mass-mail everyone), this is a closed process: it computes the
    eligible COs itself and asks for a confirmation before sending.

    Eligible = draft COs whose stage is NOT concluded. "Concluded" is a folded
    stage (e.g. the default "Feito" is folded), so those are skipped.
    """
    _name = 'consignment.map.run.wizard'
    _description = 'Send Consignment Maps (RUN)'

    eligible_count = fields.Integer(string='Eligible COs', readonly=True)

    def _eligible_settlements(self):
        cos = self.env['consignment.settlement'].search([
            ('state', '=', 'draft'),
            ('company_id', '=', self.env.company.id),
        ])
        # Skip concluded stages (folded, e.g. "Feito").
        return cos.filtered(lambda co: not co.stage_id.fold)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res['eligible_count'] = len(self._eligible_settlements())
        return res

    def action_confirm(self):
        self.ensure_one()
        template = self.env.ref(
            'liber_soc_settlement.mail_template_consignment_map', raise_if_not_found=False)
        cos = self._eligible_settlements()
        sent = 0
        if template:
            for co in cos:
                template.send_mail(co.id, force_send=False)
                sent += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Consignment Map'),
                'message': _('%s map(s) queued for sending.') % sent,
                'type': 'success',
                'sticky': False,
                # Close the wizard after the toast, so it can't be clicked twice
                # (which would queue a second round of emails).
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
