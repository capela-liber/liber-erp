# -*- coding: utf-8 -*-
from odoo import models


class IrActionsReport(models.Model):
    """A folha do passeio não é de entrega nenhuma — e o Odoo corta por entrega.

    O motor de PDF renderiza as páginas todas de uma vez e depois FATIA o
    arquivo por registro, para poder anexar cada pedaço no seu (é o que faz o
    "1 página = 1 registro" do core). A folha "Picking" é do lote, não de uma
    entrega: no corte ela não tem dono, e o Odoo a descartava em silêncio —
    saíam as três folhas dos pedidos e nada do passeio.

    Aqui o corte não acontece: o HTML vira PDF inteiro e volta inteiro. Nada
    se anexa a registro nenhum, que é exatamente o que se quer de uma folha
    que se imprime, se risca a caneta e se joga fora no fim do dia.

    Mesmo padrão do ``liber_nfe_picking``: interceptar pelo nome do relatório
    e deixar todo o resto seguir para o ``super()``.
    """
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        if report.report_name != 'liber_transport.report_picking_sheet':
            return super()._render_qweb_pdf(
                report_ref, res_ids=res_ids, data=data)

        data = dict(data or {}, debug=False)
        # debug=False no contexto: o assets debug enfia <script> na página e o
        # wkhtmltopdf tropeça neles (é a mesma precaução do core).
        rendered = self.with_context(debug=False)
        html = rendered._render_qweb_html(report_ref, res_ids, data=data)[0]
        report_sudo = report.sudo().with_context(debug=False)
        bodies, _html_ids, header, footer, paperformat_args = \
            report_sudo._prepare_html(html, report_model=report_sudo.model)
        pdf = self._run_wkhtmltopdf(
            bodies,
            report_ref=report_ref,
            header=header,
            footer=footer,
            landscape=self.env.context.get('landscape'),
            specific_paperformat_args=paperformat_args,
            set_viewport_size=self.env.context.get('set_viewport_size'),
        )
        return pdf, 'pdf'
