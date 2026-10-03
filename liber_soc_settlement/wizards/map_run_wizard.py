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
        """Carimba a fila e devolve a tela na hora -- quem manda de verdade é
        o cron de fundo (`consignment.settlement._cron_process_map_run_queue`).

        Centenas de PDFs a ~1s cada travariam o navegador de quem clicou por
        minutos: o clique não pode esperar o envio, só pedir ele. Por isso o
        aviso diz que vai demorar e roda em segundo plano -- sem isso, quem
        clica e não vê nada em segundos clica de novo, e dobra a fila.
        """
        self.ensure_one()
        cos = self._eligible_settlements()
        cos.write({'map_run_requested_at': fields.Datetime.now()})
        cron = self.env.ref(
            'liber_soc_settlement.cron_process_map_run_queue',
            raise_if_not_found=False)
        if cron and cos:
            cron.sudo()._trigger()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Consignment Map'),
                'message': _(
                    '%s map(s) queued. This runs in the background and can '
                    'take a while -- no need to wait here.') % len(cos),
                'type': 'success',
                'sticky': False,
                # Close the wizard after the toast, so it can't be clicked twice
                # (which would queue a second round of emails).
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
