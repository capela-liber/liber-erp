# -*- coding: utf-8 -*-
"""O modelo de grade: a curadoria que se repete não se remonta.

Feira recorrente tem grade parecida todo ano, e perfil de evento se repete
entre praças: a mesa de uma feira literária de interior não é a de um
lançamento na capital. Guardar a grade como modelo e aplicá-la na feira nova
é o ganho operacional imediato do §3.5.

O que este modelo AINDA NÃO é: o §3.5 completo. Falta o bloco (Vitrine, Fundo
de catálogo, Lançamentos), o critério dinâmico (coleção, selo, ano, giro nos
últimos N meses), o mínimo/máximo, a obrigatoriedade e a prioridade de corte
quando o total estoura a capacidade da caixa. Falta também o confronto com o
saldo real na hora de aplicar, que hoje é o olho de quem monta.

O que ele já é: uma grade nomeada, reutilizável, que se aplica somando ou
substituindo, e que se cria a partir de uma feira que deu certo.
"""
from odoo import _, api, fields, models


class EventFairTemplate(models.Model):
    _name = 'event.fair.template'
    _description = 'Fair Grid Template'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)
    note = fields.Text(
        string='Notes',
        help="What this grid is for, and what it learned from the last time.")
    line_ids = fields.One2many(
        'event.fair.template.line', 'template_id', string='Titles', copy=True)
    line_count = fields.Integer(compute='_compute_totals')
    qty_total = fields.Float(
        string='Copies', digits='Product Unit', compute='_compute_totals')

    _name_company_uniq = models.Constraint(
        'unique(name, company_id)',
        'There is already a grid template with this name.')

    @api.depends('line_ids.qty_planned')
    def _compute_totals(self):
        for template in self:
            template.line_count = len(template.line_ids)
            template.qty_total = sum(template.line_ids.mapped('qty_planned'))


class EventFairTemplateLine(models.Model):
    _name = 'event.fair.template.line'
    _description = 'Fair Grid Template Line'
    _order = 'template_id, id'

    template_id = fields.Many2one(
        'event.fair.template', string='Template', required=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one(related='template_id.company_id', store=True)
    product_id = fields.Many2one(
        'product.product', string='Title', required=True,
        domain="[('type', '=', 'consu')]")
    qty_planned = fields.Float(
        string='Copies', digits='Product Unit', default=1.0, required=True)
    qty_min = fields.Float(
        string='Minimum', digits='Product Unit',
        help="How few copies of this title may be left on the table before "
             "it has to be replenished. Decided here, once, by whoever runs "
             "the grid; the daily count then suggests the replenishment on "
             "its own. Zero means no minimum.")

    _template_product_uniq = models.Constraint(
        'unique(template_id, product_id)',
        'A title can only appear once in a template.')

    # Sem trava de mínimo, pelo mesmo motivo da grade: o mínimo diz o que a
    # mesa precisa ter, e pedir mais do que existe é como a casa descobre o
    # que precisa reimprimir.
