# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    is_fair_root = fields.Boolean(
        string='Fair Root',
        help="Parent (view) location grouping every fair location of the company.")
    is_fair_location = fields.Boolean(
        string='Fair Location',
        help="Internal location holding our stock physically at a fair.")
    fair_id = fields.Many2one(
        'event.fair', string='Fair', ondelete='set null',
        help="The event this location represents.")

    @api.model
    def _fair_root(self, company):
        """A raiz FEIRAS: localização de visão de topo, FORA do armazém.

        Mesmo raciocínio da raiz CO da consignação
        (liber_soc_agreements/models/stock_location.py): o que está na feira
        continua sendo nosso -- fica em localização interna, e por isso mantém
        valor no balanço --, mas não está na nossa mão: está na praça, a
        seiscentos quilômetros, sob a guarda de outra pessoa. O "Em mãos" e o
        "Previsto" do Odoo somam tudo que pende da localização de visão do
        armazém; uma feira pendurada sob WH inflaria calado o Em mãos com
        exemplar que não se pode vender pelo site nem despachar para livraria.

        Manter a raiz fora da árvore do armazém é o que exclui esse estoque
        sem precisar reescrever o cálculo do núcleo, e faz a remessa da feira
        ler como saída do armazém -- que é exatamente o que ela é.
        """
        root = self.search([
            ('is_fair_root', '=', True),
            ('company_id', '=', company.id),
        ], limit=1)
        if not root:
            # sudo DELIBERADO, como na consignação: criar stock.location é
            # direito de Inventário/Administrador, e quem abre uma feira é do
            # Comercial. A raiz não é uma gaveta que alguém abriu no
            # Inventário -- é infraestrutura deste módulo, de nome e forma
            # fixos aqui, nascida como consequência de planejar o evento.
            root = self.sudo().create({
                'name': 'FEIRAS',
                'usage': 'view',
                'location_id': False,
                'company_id': company.id,
                'is_fair_root': True,
            })
            return root.sudo(False)
        if root.location_id:
            root.sudo().location_id = False
            # warehouse_id é gravado e depende da corrente de pais, e o Odoo
            # não cascateia o recompute para os filhos: deixadas assim, as
            # feiras continuariam dizendo pertencer ao armazém que acabaram
            # de deixar.
            self.search([('id', 'child_of', root.id)]).sudo()._compute_warehouse_id()
        return root
