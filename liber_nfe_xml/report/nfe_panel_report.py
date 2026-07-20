# © 2017 Danimar Ribeiro, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import pytz
import base64
import logging
from lxml import etree
from io import BytesIO
from odoo import models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from pytrustnfe.nfe.danfe import danfe
    from pytrustnfe.nfe.danfce import danfce
except ImportError:
    danfe = danfce = None
    _logger.info('pytrustnfe is not installed - the Print Danfe report '
                 'will not be available.')


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        #to generate Danfe from the XML files
        report = self._get_report(report_ref)
        if report.report_name != 'liber_nfe_xml.main_template_report_nfe_panel':
            return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

        panels = self.env['nfe.xml.panel'].search([('id', 'in', res_ids)])
        for panel in panels:
            if not (panel.cfop_id and panel.partner_id):
                _logger.info("==========Might have some issues in %s file ", panel)
            # nfe_xml = base64.decodestring(panel.file)
            nfe_xml = base64.decodebytes(panel.file)

            nfe_xml_element = []
            query = """select id from ir_attachment where res_model = 'nfe.xml.panel' and res_id = %s limit 1""" % panel.id
            self.env.cr.execute(query)
            query_data = self.env.cr.fetchall()

            if query_data:
                for cce in query_data:
                    nfe_attach = self.env['ir.attachment'].search([
                        ('id', '=', cce[0]),
                    ])
                    # cce_xml = base64.decodestring(nfe_attach.datas)
                    cce_xml = base64.decodebytes(nfe_attach.datas)
                    nfe_xml_element.append(etree.fromstring(cce_xml))

            logo = False
            if panel.company_id.logo:
                # logo = base64.decodestring(panel.company_id.logo)
                logo = base64.decodebytes(panel.company_id.logo)
            elif panel.company_id.logo_web:
                # logo = base64.decodestring(panel.company_id.logo_web)
                logo = base64.decodebytes(panel.company_id.logo_web)

            if logo:
                tmpLogo = BytesIO()
                tmpLogo.write(logo)
                tmpLogo.seek(0)
            else:
                tmpLogo = False

            timezone = pytz.timezone(self.env.context.get('tz') or 'UTC')

            xml_element = etree.fromstring(nfe_xml)
            if panel:
                try:
                    oDanfe = danfe(
                        list_xml=[xml_element], logo=tmpLogo, timezone=timezone)
                except Exception:
                    raise UserError(_("Invalid file!\n Unable to Create Danfe.Please check your File"))


            tmpDanfe = BytesIO()
            oDanfe.writeto_pdf(tmpDanfe)
            danfe_file = tmpDanfe.getvalue()
            tmpDanfe.close()

            return danfe_file, 'pdf'


class SOCXmlPanelPdf(models.Model):
    _inherit = 'nfe.xml.panel'

    def _return_nfe_pdf(self, doc):
        return 'liber_nfe_xml.report_nfe_panel'

    def action_preview_nfe(self):

        docs = self.file

        if not docs:
            raise UserError(u'Não existe um E-Doc relacionado à esta fatura')

        return self._action_preview_nfe(docs)

    def _action_preview_nfe(self, doc):

        report = self._return_nfe_pdf(doc)
        if not report:
            raise UserError(
                'Nenhum relatório implementado para este modelo de documento')
        if not isinstance(report, str):
            return report
        action = self.env.ref(report).report_action(self)
        return action
