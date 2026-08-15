# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    nfe_ncm = fields.Char(
        string='NCM (NF-e)', size=8,
        help="Classificação fiscal (8 dígitos). Livro é 4901.99.00. Vazio usa "
             "o NCM padrão da empresa.")
    nfe_origem = fields.Selection(
        selection=[
            ('0', '0 - Nacional'),
            ('1', '1 - Estrangeira, importação direta'),
            ('2', '2 - Estrangeira, adquirida no mercado interno'),
            ('3', '3 - Nacional, conteúdo de importação entre 40% e 70%'),
            ('4', '4 - Nacional, processos produtivos básicos'),
            ('5', '5 - Nacional, conteúdo de importação até 40%'),
            ('6', '6 - Estrangeira, importação direta, sem similar nacional'),
            ('7', '7 - Estrangeira, mercado interno, sem similar nacional'),
            ('8', '8 - Nacional, conteúdo de importação acima de 70%'),
        ],
        string='Origem da Mercadoria', default='0', required=True)

    nfe_codigo_beneficio_fiscal = fields.Char(
        string='Código de Benefício Fiscal (cBenef)', size=10,
        help="Sobrepõe o cBenef da empresa. Só preencha para produtos com "
             "tratamento diferente do padrão — um livro herda o da empresa.")

    nfe_ibs_cbs_cst = fields.Char(
        string='CST do IBS/CBS', size=3,
        help="Sobrepõe o da empresa. Um livro herda; outro produto preenche.")
    nfe_ibs_cbs_classificacao = fields.Char(
        string='Classificação Tributária (cClassTrib)', size=6)

    def _focus_codigo_beneficio_fiscal(self, company):
        self.ensure_one()
        return (self.nfe_codigo_beneficio_fiscal
                or company.focus_codigo_beneficio_fiscal)

    def _focus_ncm(self, company):
        """NCM do produto, caindo para o do Metabooks e depois para o da empresa."""
        self.ensure_one()
        # O `metabooks_ncm` só existe quando o liber_metabooks_integration está
        # instalado; este módulo não depende dele, então perguntamos ao registro.
        metabooks = self._fields.get('metabooks_ncm') and self.metabooks_ncm
        return self.nfe_ncm or metabooks or company.focus_ncm_padrao
