# -*- coding: utf-8 -*-
"""Thema — a classificação temática internacional da EDItEUR.

A lista embarcada é a **v1.6 em português do Brasil**, publicada pela EDItEUR
(9.187 códigos: 3.422 categorias e 5.765 qualificadores). Ela não é da casa e
não se edita à mão: sobe inteira em `data/metabooks.thema.code.csv`, gerada
pelo `scripts/gerar_listas_classificacao.py` a partir do JSON oficial.

Duas famílias no mesmo modelo, separadas por `kind`, porque é assim que o Thema
se usa e é assim que a planilha da Metabooks pede:

* **categoria** (A–Y) — do que o livro trata. Uma é a principal;
* **qualificador** (1–6) — lugar, idioma, período, finalidade educacional,
  público/interesse e estilo. Só qualificam uma categoria, nunca vão sozinhos.
"""

from odoo import api, fields, models

# Os seis grupos de qualificador, pela raiz do código. O nome curto é o que
# aparece na etiqueta -- "1 Lugar" lê melhor do que o rótulo inteiro da EDItEUR.
GRUPOS_QUALIFICADOR = {
    '1': 'place',
    '2': 'language',
    '3': 'time',
    '4': 'educational',
    '5': 'interest',
    '6': 'style',
}


class MetabooksThemaCode(models.Model):
    _name = 'metabooks.thema.code'
    _description = 'Thema Subject Code'
    _order = 'code'
    _rec_names_search = ['code', 'name']

    code = fields.Char('Code', required=True, index=True)
    name = fields.Char('Heading', required=True, translate=True)
    note = fields.Text(
        'Usage Note',
        help="A nota de uso da EDItEUR: com o que combinar, o que preferir, "
             "o que não usar. É o que separa o código certo do parecido.")
    parent_code = fields.Char(
        'Parent Code', index=True,
        help="O código do pai como a EDItEUR o escreve. É ele que a lista traz "
             "-- e é por isso que o vínculo se resolve na leitura, e não por "
             "referência no CSV: as 9.187 linhas entram numa ordem em que o "
             "pai nem sempre já existe.")
    parent_id = fields.Many2one(
        'metabooks.thema.code', 'Parent', compute='_compute_parent_id')
    kind = fields.Selection(
        [('category', 'Category'), ('qualifier', 'Qualifier')],
        required=True, index=True, default='category')
    qualifier_kind = fields.Selection(
        [('place', 'Place'), ('language', 'Language'), ('time', 'Time Period'),
         ('educational', 'Educational Purpose'), ('interest', 'Interest'),
         ('style', 'Style')],
        string='Qualifier Group', index=True)
    version = fields.Char('Thema Version', default='1.6')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Cada código Thema aparece uma vez só.'),
    ]

    @api.depends('parent_code')
    def _compute_parent_id(self):
        codigos = [r.parent_code for r in self if r.parent_code]
        achados = self.search([('code', 'in', codigos)]) if codigos else self.browse()
        por_codigo = {r.code: r.id for r in achados}
        for rec in self:
            rec.parent_id = por_codigo.get(rec.parent_code, False)

    @api.depends('code', 'name')
    def _compute_display_name(self):
        # "[NHK] História das Américas" -- é como a Metabooks mostra, e quem
        # escolhe procura tanto pelo código quanto pela ementa.
        for rec in self:
            rec.display_name = '[%s] %s' % (rec.code or '', rec.name or '')
