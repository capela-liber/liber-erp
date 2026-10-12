# -*- coding: utf-8 -*-
from odoo import api, models


class StockLocation(models.Model):
    """A prateleira tem código de barras: o próprio código.

    O core deixa `barcode` vazio e, para local novo, sugere o nome completo
    (`EL-VG/Stock/EL-000196`). A etiqueta que se cola na prateleira leva o
    código curto, e é ele que o leitor devolve. Aqui as prateleiras do
    armazém ganham `barcode = name` -- na instalação (gancho) e ao nascer.
    """
    _inherit = 'stock.location'

    def _liber_is_shelf(self):
        """Prateleira: local interno do armazém, abaixo da raiz, sem filhos
        internos. A raiz (`EL-VG/Stock`) e os locais de vista ficam de fora."""
        self.ensure_one()
        return bool(
            self.usage == 'internal' and self.warehouse_id
            and self.location_id
            and self.location_id != self.warehouse_id.view_location_id
            and not self.child_ids.filtered(lambda c: c.usage == 'internal'))

    @api.model
    def _liber_etiquetar_prateleiras(self):
        """Dá `barcode = name` a toda prateleira sem código. Idempotente; pula
        o nome que já é código de barras de outro local da empresa."""
        candidatas = self.with_context(active_test=False).search([
            ('usage', '=', 'internal'), ('warehouse_id', '!=', False),
            ('barcode', '=', False)])
        feitas = self.browse()
        for loc in candidatas:
            if not loc._liber_is_shelf():
                continue
            ocupado = self.with_context(active_test=False).search_count([
                ('barcode', '=', loc.name),
                ('company_id', '=', loc.company_id.id)])
            if ocupado:
                continue
            loc.barcode = loc.name
            feitas |= loc
        return feitas

    @api.model_create_multi
    def create(self, vals_list):
        locais = super().create(vals_list)
        for loc in locais:
            if not loc.barcode and loc._liber_is_shelf():
                loc.barcode = loc.name
        return locais
