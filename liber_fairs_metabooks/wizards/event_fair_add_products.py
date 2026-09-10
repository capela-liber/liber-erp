# -*- coding: utf-8 -*-
"""Os filtros que só existem onde existe catálogo da Metabooks."""
from datetime import date

from odoo import fields, models


class EventFairAddProducts(models.TransientModel):
    _inherit = 'event.fair.add.products'

    filter_thema_id = fields.Many2one(
        'metabooks.thema.code', string='Thema subject',
        domain="[('kind', '=', 'category')]",
        help="Thema classification, whole branch. The Y branch is the "
             "children and young adult one.")
    filter_published_from = fields.Date(string='Published from')
    filter_published_to = fields.Date(string='Published to')
    order = fields.Selection(
        selection_add=[('newest', 'Newest first')],
        ondelete={'newest': 'set default'})

    def _filter_domain(self):
        domain = super()._filter_domain()
        if self.filter_thema_id:
            # O galho inteiro sai pelo PREFIXO do código, não por child_of:
            # `metabooks.thema.code.parent_id` é computado e não gravado, e
            # child_of precisa de coluna para descer a árvore em SQL. O Thema
            # é hierárquico no próprio código -- Y é infantojuvenil, YF é
            # ficção infantojuvenil, YFB é um ramo dela -- então "começa com
            # Y" é exatamente "está debaixo de Y", e sem juntar tabela.
            prefixo = (self.filter_thema_id.code or '') + '%'
            domain += ['|',
                       ('product_tmpl_id.metabooks_thema_id.code', '=like',
                        prefixo),
                       ('product_tmpl_id.metabooks_thema_ids.code', '=like',
                        prefixo)]
        if self.filter_published_from:
            domain.append(('product_tmpl_id.metabooks_publish_date', '>=',
                           self.filter_published_from))
        if self.filter_published_to:
            domain.append(('product_tmpl_id.metabooks_publish_date', '<=',
                           self.filter_published_to))
        return domain

    def _ordenar(self, produtos):
        if self.order == 'newest':
            # Título sem data de publicação vai para o fim, não para o
            # começo: "mais novos primeiro" com data vazia no topo mostraria
            # justamente o que ninguém catalogou.
            return produtos.sorted(
                key=lambda p: p.product_tmpl_id.metabooks_publish_date
                or date.min, reverse=True)
        return super()._ordenar(produtos)
