# -*- coding: utf-8 -*-
"""A sigla da unidade que vai na nota.

O `uCom` da NFe tem de 1 a 6 caracteres e é o que a livraria lê no DANFE. O nome
da unidade no Odoo não serve: sai "Units", em inglês, porque é o rótulo da
interface e não uma sigla fiscal.
"""

from odoo import fields, models


class UomUom(models.Model):
    _inherit = 'uom.uom'

    nfe_unidade = fields.Char(
        string='Sigla na NFe', size=6,
        help="Sigla que vai no campo uCom da nota — UN, CX, KG, MT. Vazio usa "
             "UN, que é o caso de quase tudo que se vende em unidade.")

    def _nfe_sigla(self):
        """A sigla desta unidade, com UN como padrão honesto."""
        self.ensure_one() if self else None
        return (self[:1].nfe_unidade or 'UN')[:6].upper()
