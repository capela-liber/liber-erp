# -*- coding: utf-8 -*-
import base64
import logging
import re
import time

from odoo import api, fields, models

from . import sefaz_dfe_client as dfe

_logger = logging.getLogger(__name__)

# Politeness limits per company per run (mirrors the standalone client that
# was tested against production SEFAZ): the service rate-limits aggressive
# sweepers with cStat 656.
MAX_CALLS = 20
DELAY_SECONDS = 3.0


class ResCompany(models.Model):
    _inherit = 'res.company'

    sefaz_dfe_enabled = fields.Boolean(
        string="SEFAZ DFe Sync",
        help="Include this company in the daily SEFAZ document sweep "
             "(NFeDistribuicaoDFe). Requires the A1 certificate below.")
    sefaz_cert_pfx = fields.Binary(
        string="A1 Certificate (.pfx)", attachment=True,
        help="A1 digital certificate of this company's CNPJ, used for the "
             "mutual-TLS authentication against SEFAZ.")
    sefaz_cert_pfx_name = fields.Char(string="Certificate File Name")
    sefaz_cert_password = fields.Char(
        string="Certificate Password",
        help="Password of the .pfx file. Stored in the database; restrict "
             "access to company settings accordingly.")
    sefaz_last_nsu = fields.Char(
        string="Last NSU", default='0',
        help="Sweep cursor: last NSU already received from SEFAZ for this "
             "company. Reset to 0 to re-download the full window (~90 days).")


class NfeXmlPanelSefaz(models.Model):
    _inherit = 'nfe.xml.panel'

    source = fields.Selection(
        selection_add=[('sefaz', 'SEFAZ DFe')],
        ondelete={'sefaz': 'set default'})


class NfeSefazSweep(models.Model):
    """One SEFAZ DFe sweep of one company: the sync log the SEFAZ menu shows.

    The XMLs themselves land in nfe.xml.panel like any other source (dedup
    by access key in _ingest_xml); this record only tells whether the sync
    is alive and what it brought.
    """
    _name = 'nfe.sefaz.sweep'
    _description = "SEFAZ DFe Sweep"
    _order = 'id desc'

    company_id = fields.Many2one('res.company', string="Company", required=True)
    date_start = fields.Datetime(string="Started At", default=fields.Datetime.now)
    status = fields.Selection([
        ('running', 'Running'),
        ('done', 'Done'),
        ('rate_limited', 'Rate Limited'),
        ('error', 'Error'),
    ], string="Status", default='running')
    nsu_start = fields.Char(string="NSU From")
    nsu_end = fields.Char(string="NSU To")
    max_nsu = fields.Char(string="Max NSU (SEFAZ)")
    n_calls = fields.Integer(string="Calls")
    n_docs = fields.Integer(string="Documents")
    n_nfe = fields.Integer(string="NFe Imported",
                           help="Full NFe XMLs that became new NFe XML panel records.")
    n_events = fields.Integer(string="Cancellations",
                              help="Cancellation events registered (110111/110112).")
    n_other = fields.Integer(string="Summaries/Other",
                             help="Summaries (resNFe/resEvento) and non-cancellation "
                                  "events: nothing to import, kept for the tally.")
    n_skipped = fields.Integer(string="Skipped (Duplicates)")
    message = fields.Text(string="Message")
    panel_ids = fields.Many2many(
        'nfe.xml.panel', 'nfe_sefaz_sweep_panel_rel', 'sweep_id', 'panel_id',
        string="Imported NFes")

    @api.depends('company_id', 'date_start')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s — %s' % (
                rec.company_id.name or '?', rec.date_start or '')

    # -- entry points -----------------------------------------------------

    @api.model
    def run_sweeps(self):
        """Daily cron: sweep every company with SEFAZ sync enabled."""
        companies = self.env['res.company'].sudo().search([('sefaz_dfe_enabled', '=', True)])
        if not companies:
            _logger.info('SEFAZ DFe: no company with sync enabled, nothing to do.')
        sweeps = self.browse()
        for company in companies:
            sweeps |= self._run_company(company)
        return sweeps

    def action_sync_now(self):
        """List-header button: same as the daily cron, on demand."""
        self.run_sweeps()

    # -- one company ------------------------------------------------------

    @api.model
    def _make_client(self, company):
        return dfe.DfeClient(
            base64.b64decode(company.sefaz_cert_pfx),
            company.sefaz_cert_password or '')

    @api.model
    def _fetch(self, client, cnpj, ult_nsu):
        # Separate hook so tests can stub the network out.
        return client.fetch(cnpj, ult_nsu)

    @api.model
    def _run_company(self, company):
        sweep = self.create({
            'company_id': company.id,
            'nsu_start': company.sefaz_last_nsu or '0',
        })
        cnpj = re.sub(r'\D', '', company.partner_id.vat or '')
        if len(cnpj) != 14:
            sweep.write({'status': 'error',
                         'message': 'Company has no valid CNPJ (partner VAT).'})
            return sweep
        if not company.sefaz_cert_pfx:
            sweep.write({'status': 'error',
                         'message': 'No A1 certificate (.pfx) configured on the company.'})
            return sweep
        try:
            client = self._make_client(company)
        except Exception as e:
            sweep.write({'status': 'error',
                         'message': 'Could not open the A1 certificate: %s' % e})
            return sweep

        Panel = self.env['nfe.xml.panel']
        ult = int(company.sefaz_last_nsu or 0)
        counts = dict.fromkeys(('calls', 'docs', 'nfe', 'events', 'other', 'skipped'), 0)
        panels = Panel.browse()
        status, message, max_nsu = 'done', '', ''
        try:
            for it in range(MAX_CALLS):
                ret = self._fetch(client, cnpj, ult)
                counts['calls'] += 1
                cstat, max_nsu = ret.get('cStat'), ret.get('maxNSU') or ''
                for doc in ret['docs']:
                    counts['docs'] += 1
                    fam = dfe.doc_family(doc)
                    if fam in ('procNFe', 'nfeProc'):
                        panel = Panel._ingest_xml(
                            doc['xml'], 'sefaz-%s.xml' % doc['nsu'], source='sefaz')
                        if panel:
                            counts['nfe'] += 1
                            panels |= panel
                        else:
                            counts['skipped'] += 1
                    elif fam == 'procEventoNFe':
                        event = Panel.register_cancellation_event(
                            doc['xml'], file_name='sefaz-%s.xml' % doc['nsu'],
                            company_id=company.id)
                        if event:
                            counts['events'] += 1
                        else:
                            counts['other'] += 1
                    else:
                        counts['other'] += 1
                if ret.get('ultNSU'):
                    ult = int(ret['ultNSU'])
                    company.sudo().write({'sefaz_last_nsu': str(ult)})
                if cstat == dfe.CSTAT_RATE_LIMITED:
                    status, message = 'rate_limited', ret.get('xMotivo') or ''
                    break
                if cstat == dfe.CSTAT_NO_DOCS:
                    message = ret.get('xMotivo') or ''
                    break
                if max_nsu and ult >= int(max_nsu):
                    break
                time.sleep(DELAY_SECONDS)
        except Exception as e:
            _logger.exception('SEFAZ DFe sweep failed for %s', company.name)
            status, message = 'error', str(e)[:2000]
        sweep.write({
            'status': status,
            'message': message,
            'nsu_end': str(ult),
            'max_nsu': max_nsu,
            'n_calls': counts['calls'],
            'n_docs': counts['docs'],
            'n_nfe': counts['nfe'],
            'n_events': counts['events'],
            'n_other': counts['other'],
            'n_skipped': counts['skipped'],
            'panel_ids': [(6, 0, panels.ids)],
        })
        _logger.info(
            'SEFAZ DFe sweep %s: %s — NSU %s→%s, %s docs (%s NFe, %s cancel, %s other, %s dup)',
            company.name, status, sweep.nsu_start, ult, counts['docs'],
            counts['nfe'], counts['events'], counts['other'], counts['skipped'])
        return sweep
