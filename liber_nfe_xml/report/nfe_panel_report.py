# -*- coding: utf-8 -*-
# © 2017 Danimar Ribeiro, Trustcode (o padrão de interceptar o relatório)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""A DANFE desenhada a partir do XML — o documento que a logística imprime.

O renderizador original usava a pytrustnfe, abandonada no PyPI (o tarball nem
instala) e ausente de todos os servidores da casa: o preview de DANFE nunca
funcionou fora do papel. Trocado em 18/08/2026 pela brazilfiscalreport, que é
mantida, roda no Python 3.12 e desenha a DANFE inteira (chave, protocolo,
transportadora, impostos) a partir do nfeProc autorizado.
"""
import base64
import logging
import re

from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools.pdf import merge_pdf

_logger = logging.getLogger(__name__)

# O Olist escreve HTML dentro do texto fiscal: o infCpl das notas dele vem
# com "<br />" literais (escapados no XML). No desenho da DANFE eles viram
# quebra de linha de verdade — o XML arquivado não muda, só a cópia que vai
# ao papel.
BR_HTML = re.compile(r'&lt;br\s*/?\s*&gt;', re.IGNORECASE)

try:
    from brazilfiscalreport.danfe import Danfe, DanfeConfig
except ImportError:
    Danfe = DanfeConfig = None
    _logger.info("brazilfiscalreport is not installed - the Print Danfe "
                 "report will not be available.")


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        if report.report_name != 'liber_nfe_xml.main_template_report_nfe_panel':
            return super()._render_qweb_pdf(
                report_ref, res_ids=res_ids, data=data)

        if Danfe is None:
            raise UserError(_(
                "A biblioteca 'brazilfiscalreport' não está instalada neste "
                "servidor — é ela que desenha a DANFE a partir do XML.\n\n"
                "Instale no ambiente do Odoo: pip install brazilfiscalreport"))

        pdfs = []
        for panel in self.env['nfe.xml.panel'].browse(res_ids):
            if not panel.file:
                raise UserError(_(
                    "%s não tem o XML anexado — sem ele não há DANFE. Traga "
                    "o XML da nota antes de imprimir.", panel.display_name))
            pdfs.append(self._liber_danfe_do_xml(panel))
        return (pdfs[0] if len(pdfs) == 1 else merge_pdf(pdfs)), 'pdf'

    @staticmethod
    def _liber_infcpl_sem_html(xml):
        """'<br />' vindo do Olist vira quebra de linha na DANFE (e nada mais:
        a substituição é global porque o tag escapado só pode viver em texto)."""
        return BR_HTML.sub('&#10;', xml)

    def _liber_danfe_do_xml(self, panel):
        xml = self._liber_infcpl_sem_html(
            base64.b64decode(panel.file).decode('utf-8'))
        config = None
        logo = panel.company_id.logo or panel.company_id.logo_web
        if logo:
            try:
                config = DanfeConfig(logo=base64.b64decode(logo))
            except Exception:
                # Logo que a biblioteca não digere não pode derrubar a DANFE:
                # o documento fiscal vale sem ele.
                config = None
        try:
            danfe_pdf = Danfe(xml=xml, config=config) if config else Danfe(xml=xml)
        except Exception as exc:
            raise UserError(_(
                "O XML de %(painel)s não virou DANFE: %(erro)s\n\n"
                "Confira se o arquivo é um nfeProc autorizado e completo.",
                painel=panel.display_name, erro=exc)) from exc
        return bytes(danfe_pdf.output())


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
