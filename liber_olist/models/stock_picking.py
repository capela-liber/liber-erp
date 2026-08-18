# -*- coding: utf-8 -*-

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    """A nota do Olist chega à transferência assim que ela nasce.

    O carimbo em `nfe_move_id` acontecia uma vez só, no instante em que a
    fatura era criada — e transferência criada DEPOIS ficava sem nota. É o
    caso normal, não a exceção: o pedido entra em rascunho (sem corte de
    estoque configurado), alguém confirma o S mais tarde, e o picking nasce
    quando a fatura já existe há horas.

    Foi o que a logística viu em 17/08/2026: "Sem nota fiscal:
    EL-VG/OUT/01888", com a NFe arquivada e a fatura paga do outro lado.
    """
    _inherit = 'stock.picking'

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        pickings._liber_olist_carimbar_nota()
        return pickings

    def _liber_olist_carimbar_nota(self):
        """Carimba a nota das transferências cujo pedido veio do Olist."""
        if 'nfe_move_id' not in self._fields:
            # Sem o liber_nfe_picking instalado não há onde carimbar, e isso
            # não é erro: o liber_olist não depende dele.
            return False
        candidatas = self.filtered(
            lambda p: p.sale_id and not p.nfe_move_id)
        if not candidatas:
            return False
        espelhos = self.env['olist.order'].search([
            ('sale_order_id', 'in', candidatas.sale_id.ids),
            ('invoice_id', '!=', False),
        ])
        # Guarda o ESPELHO, não só a fatura: é ele que sabe qual painel é o
        # desta venda. Chegar ao painel pela chave da fatura falha justamente
        # quando a nota ainda não tem chave gravada.
        por_pedido = {e.sale_order_id.id: e for e in espelhos}
        marcadas = 0
        for picking in candidatas:
            espelho = por_pedido.get(picking.sale_id.id)
            if espelho:
                picking.nfe_move_id = espelho.invoice_id
                picking._liber_olist_anexar_xml(espelho.nfe_panel_id)
                marcadas += 1
        if marcadas:
            _logger.info("Olist: nota carimbada em %s transferência(s).",
                         marcadas)
        return marcadas

    def _liber_olist_anexar_xml(self, painel):
        """Pendura o XML da nota na transferência.

        A logística precisa do arquivo, não de um link para outra tela: quem
        separa a caixa confere a nota ali, e mandar a pessoa navegar até o
        painel de NFe no meio da expedição é pedir que ela não confira.
        """
        self.ensure_one()
        if not painel or not painel.file:
            return False
        Anexo = self.env['ir.attachment']
        nome = painel.file_name or ("nfe-%s.xml" % (painel.danfe_no or painel.id))
        ja_tem = Anexo.search_count([
            ('res_model', '=', 'stock.picking'), ('res_id', '=', self.id),
            ('name', '=', nome)])
        if ja_tem:
            return False
        Anexo.create({
            'name': nome,
            'datas': painel.file,
            'res_model': 'stock.picking',
            'res_id': self.id,
            'mimetype': 'application/xml',
        })
        return True
