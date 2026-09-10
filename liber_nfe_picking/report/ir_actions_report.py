# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.pdf import merge_pdf


class IrActionsReport(models.Model):
    """O "Imprimir > Notas fiscais" da lista de transferências.

    Não renderiza nada: a DANFE já existe em PDF, baixada da Focus e postada
    no chatter do mov. Este relatório só a devolve — uma por transferência,
    emendadas num PDF só quando a seleção tem várias. É o mesmo padrão do
    ``liber_nfe_xml``: interceptar o ``_render_qweb_pdf`` pelo nome.
    """
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        if report.report_name != 'liber_nfe_picking.report_picking_danfe':
            return super()._render_qweb_pdf(
                report_ref, res_ids=res_ids, data=data)

        pickings = self.env['stock.picking'].browse(res_ids)
        # Segunda chance antes de barrar: a nota nascida de XML (Olist e
        # afins) não passa pela Focus e pode ainda não ter sido carimbada
        # aqui -- resolve pelo pedido -> fatura -> painel agora.
        for picking in pickings.filtered(lambda p: not p.nfe_move_id):
            picking._liber_carimbar_nota_de_xml()
        # Quem não tem nota não imprime — e a caixa não viaja sem documento.
        # Barrar a seleção inteira é de propósito: melhor um aviso agora do
        # que metade das DANFEs na bandeja e ninguém sabendo qual faltou.
        sem_nota = pickings.filtered(lambda p: not p.nfe_move_id)
        if sem_nota:
            raise UserError(_(
                "Sem nota fiscal: %(pickings)s.\n\n"
                "A DANFE chega à transferência quando a SEFAZ autoriza a "
                "NFe. O filtro \"Sem nota fiscal\" lista tudo o que ainda "
                "espera emissão.",
                pickings=", ".join(sem_nota.mapped('name'))))

        # sudo de propósito, e só no que toca a fatura: a Logística imprime
        # sem grupo contábil nenhum (liber_roles: Assistente = stock_user), e
        # ler o focus_ref ou o anexo da fatura como o usuário seria
        # AccessError exatamente para quem este módulo existe. A porteira é o
        # picking: quem pode abrir a transferência recebe a DANFE dela.
        Attachment = self.env['ir.attachment'].sudo()
        pdfs, sem_pdf = [], []
        for picking in pickings:
            nota = picking.nfe_move_id.sudo()
            anexo = False
            if nota.focus_ref:
                nome = '%s.pdf' % nota.focus_ref
                anexo = Attachment.search([
                    ('res_model', '=', 'stock.picking'),
                    ('res_id', '=', picking.id), ('name', '=', nome)], limit=1)
                if not anexo:
                    # A nota existe mas o PDF ainda não chegou ao mov (download
                    # pendente na Focus): a fatura é a segunda chance.
                    anexo = Attachment.search([
                        ('res_model', '=', 'account.move'),
                        ('res_id', '=', nota.id), ('name', '=', nome)], limit=1)
            if anexo:
                pdfs.append(anexo.raw)
                continue
            # Nota nascida de XML (Olist e afins): não há PDF da Focus, mas há
            # o XML autorizado no painel -- a DANFE renderiza dele, pelo mesmo
            # caminho do preview do liber_nfe_xml. sudo pela mesma porteira.
            painel = nota.nfe_xml_panel_id.sudo()
            if painel and painel.file:
                pdf, _tipo = self.sudo()._render_qweb_pdf(
                    'liber_nfe_xml.main_template_report_nfe_panel',
                    res_ids=[painel.id])
                pdfs.append(pdf)
            else:
                sem_pdf.append(picking.name)
        if sem_pdf:
            raise UserError(_(
                "A NFe está autorizada, mas a DANFE ainda não baixou da "
                "Focus: %(pickings)s. A próxima consulta do cron a traz.",
                pickings=", ".join(sem_pdf)))
        return (pdfs[0] if len(pdfs) == 1 else merge_pdf(pdfs)), 'pdf'
