# -*- coding: utf-8 -*-
"""Somar títulos à grade de uma vez, em vez de linha a linha.

Montar grade de feira é escolher dezenas de títulos. Uma linha por vez, com
autocompletar em cada uma, é o jeito mais lento possível de fazer isso: a
tela do produto já sabe filtrar por selo, por coleção e por o que está em
estoque, e é lá que a curadoria acontece.

Este assistente não é o template de curadoria do §3.5 -- aquele tem bloco,
critério dinâmico, mínimo, máximo e prioridade de corte. Este é o que faltava
para a grade ser preenchível hoje.
"""
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EventFairAddProducts(models.TransientModel):
    _name = 'event.fair.add.products'
    _description = 'Add Titles to the Fair Grid'

    # O assistente serve aos DOIS destinos: a grade de uma feira e a grade de
    # um modelo. É a mesma tarefa (escolher muitos títulos entre milhares), e
    # separar em dois assistentes duplicaria os filtros, que é o que dá
    # trabalho aqui.
    fair_id = fields.Many2one(
        'event.fair', string='Fair', ondelete='cascade')
    template_id = fields.Many2one(
        'event.fair.template', string='Template', ondelete='cascade')
    product_ids = fields.Many2many(
        'product.product', string='Titles',
        domain="[('type', '=', 'consu')]")

    # --- o filtro -------------------------------------------------------
    # São 4.633 títulos no catálogo. Escolher um a um numa caixa de busca é
    # o jeito mais lento possível de montar uma grade de feira. O filtro
    # abaixo é a mesma curadoria que a pessoa faria de cabeça -- selo,
    # coleção, assunto, ano, preço, giro -- e o botão Buscar traz o
    # resultado para a lista, onde ela ainda tira e põe à mão antes de somar.
    filter_categ_id = fields.Many2one(
        'product.category', string='Product category',
        help="Takes everything under it. In this catalogue the category tree "
             "is the imprint with its collections below, so picking Editora "
             "Hedra brings Mundo Indígena, Metabiblioteca and the rest along.")
    filter_tag_ids = fields.Many2many(
        'product.tag', string='Tags',
        help="Any of them. The house tags come from the Metabooks subjects.")
    filter_price_min = fields.Float(string='Price from')
    filter_price_max = fields.Float(string='Price to')
    # Era um sim/não ("só o que está no armazém"). Virou número porque a
    # pergunta real da feira não é "tem?", é "tem o bastante?": um título com
    # dois exemplares livres não sustenta uma mesa de três dias, e trazê-lo
    # para a grade só gera ruptura no despacho.
    min_stock = fields.Float(
        string='Minimum free stock', digits='Product Unit', default=1.0,
        help="Only brings titles with at least this many copies free in the "
             "warehouse. Zero brings everything, in stock or not -- which is "
             "the default when building a template, since a template plans "
             "and does not dispatch.")
    # 'newest' entra pela ponte liber_fairs_metabooks: a data de publicação
    # é campo da Metabooks, e este módulo não a exige para existir.
    order = fields.Selection(
        [('name', 'By title'),
         ('bestsellers', 'Best sellers first')],
        string='Order', default='name', required=True)
    months = fields.Integer(
        string='Months of sales', default=6,
        help="How far back the best-seller ranking looks.")
    limit = fields.Integer(
        string='At most', default=40,
        help="Cuts the result after this many titles. Zero brings all.")
    found_count = fields.Integer(string='Found', readonly=True)
    qty_planned = fields.Float(
        string='Copies each', digits='Product Unit', default=1.0,
        required=True,
        help="How many copies of each selected title. Adjust title by title "
             "in the grid afterwards.")
    qty_min = fields.Float(
        string='Minimum', digits='Product Unit',
        help="The minimum each of these titles keeps on the table. The daily "
             "count uses it to suggest the replenishment on its own. Zero "
             "means no minimum.")
    # Mesmo motivo do qty_warehouse na linha da grade: sem amarrar a leitura
    # ao armazém, a coluna "Em mãos" soma o que já está nas mesas das feiras.
    warehouse_location_id = fields.Many2one(
        'stock.location', string='Warehouse Stock',
        compute='_compute_warehouse_location')
    skip_existing = fields.Boolean(
        string='Skip titles already in the grid', default=True,
        help="Off, the quantity of a title already in the grid is raised by "
             "this many copies instead of being left alone.")

    @api.depends('fair_id', 'template_id')
    def _compute_warehouse_location(self):
        for wizard in self:
            company = wizard.fair_id.company_id or wizard.template_id.company_id
            warehouse = company._fair_warehouse() if company else None
            wizard.warehouse_location_id = \
                warehouse.lot_stock_id if warehouse else False

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        modelo = self.env.context.get('active_model')
        ativo = self.env.context.get('active_id')
        if modelo == 'event.fair' and 'fair_id' in fields_list \
                and not vals.get('fair_id'):
            vals['fair_id'] = ativo
        if modelo == 'event.fair.template' and 'template_id' in fields_list \
                and not vals.get('template_id'):
            vals['template_id'] = ativo
        # MODELO NÃO DESPACHA NADA. O estoque livre importa quando se monta a
        # grade de uma feira que vai sair semana que vem; num modelo, que é
        # planejamento (e serve de lista para imprimir e conferir na mesa),
        # exigir estoque esconde justamente o título esgotado que se quer ver.
        if modelo == 'event.fair.template' and 'min_stock' in fields_list:
            vals['min_stock'] = 0.0
        return vals

    @api.constrains('fair_id', 'template_id')
    def _check_destino(self):
        for wizard in self:
            if bool(wizard.fair_id) == bool(wizard.template_id):
                raise UserError(_(
                    "Titles go either into a fair grid or into a template, "
                    "not both and not neither."))

    def _destino(self):
        """(modelo das linhas, campo que aponta o pai, id do pai, linhas)."""
        self.ensure_one()
        if self.fair_id:
            return ('event.fair.line', 'fair_id', self.fair_id.id,
                    self.fair_id.line_ids)
        return ('event.fair.template.line', 'template_id', self.template_id.id,
                self.template_id.line_ids)

    # ------------------------------------------------------------------
    # busca
    # ------------------------------------------------------------------
    def _filter_domain(self):
        self.ensure_one()
        domain = [('type', '=', 'consu'), ('sale_ok', '=', True)]
        if self.filter_categ_id:
            domain.append(('categ_id', 'child_of', self.filter_categ_id.id))
        if self.filter_tag_ids:
            domain.append(
                ('product_tag_ids', 'in', self.filter_tag_ids.ids))
        if self.filter_price_min:
            domain.append(('list_price', '>=', self.filter_price_min))
        if self.filter_price_max:
            domain.append(('list_price', '<=', self.filter_price_max))
        return domain

    def _rank_by_sales(self, products):
        """Giro: exemplares vendidos nos últimos N meses, mais vendido antes.

        Consignação fica FORA da conta, pela mesma regra que o resto da casa
        segue nos relatórios de venda (liber_soc_moves/models/sale_report.py):
        um Pedido C é remessa, não venda, e contá-lo aqui elegeria para a
        feira o título que enche prateleira de livraria.
        """
        self.ensure_one()
        desde = fields.Date.today() - relativedelta(
            months=max(self.months or 6, 1))
        grupos = self.env['sale.order.line']._read_group(
            [('product_id', 'in', products.ids),
             ('order_id.state', 'in', ('sale', 'done')),
             ('order_id.date_order', '>=', desde),
             ('order_id.is_consignment', '!=', True)],
            groupby=['product_id'],
            aggregates=['product_uom_qty:sum'])
        vendidos = {p.id: qty for p, qty in grupos}
        return products.sorted(
            key=lambda p: vendidos.get(p.id, 0.0), reverse=True)

    def _ordenar(self, produtos):
        """Gancho: a ponte da Metabooks acrescenta a ordem por data."""
        self.ensure_one()
        if self.order == 'bestsellers':
            return self._rank_by_sales(produtos)
        return produtos.sorted(key=lambda p: p.display_name)

    def action_search(self):
        """Traz o resultado para a lista, sem somar nada ainda."""
        self.ensure_one()
        produtos = self.env['product.product'].search(self._filter_domain())
        if self.min_stock > 0 and produtos:
            company = self.fair_id.company_id or self.template_id.company_id \
                or self.env.company
            warehouse = company._fair_warehouse()
            if warehouse:
                produtos = produtos.with_context(
                    location=warehouse.lot_stock_id.id,
                    company_id=company.id).filtered(
                        lambda p: p.free_qty >= self.min_stock)
        produtos = self._ordenar(produtos)
        if self.limit:
            produtos = produtos[:self.limit]
        self.product_ids = [(6, 0, produtos.ids)]
        self.found_count = len(produtos)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_add(self):
        self.ensure_one()
        if not self.product_ids:
            raise UserError(_("Pick at least one title."))
        modelo, campo, pai, linhas = self._destino()
        ja_na_grade = {line.product_id: line for line in linhas}
        novas = []
        for product in self.product_ids:
            line = ja_na_grade.get(product)
            if line is not None:
                if not self.skip_existing:
                    line.qty_planned += self.qty_planned
                continue
            novas.append({
                campo: pai,
                'product_id': product.id,
                'qty_planned': self.qty_planned,
                'qty_min': self.qty_min,
            })
        if novas:
            self.env[modelo].create(novas)
        return {'type': 'ir.actions.act_window_close'}


class EventFairApplyTemplate(models.TransientModel):
    _name = 'event.fair.apply.template'
    _description = 'Apply a Grid Template to the Fair'

    fair_id = fields.Many2one(
        'event.fair', string='Fair', required=True, ondelete='cascade')
    template_id = fields.Many2one(
        'event.fair.template', string='Template', required=True)
    mode = fields.Selection(
        [('add', 'Add to what is already there'),
         ('replace', 'Replace the grid')],
        string='How', default='add', required=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if 'fair_id' in fields_list and not vals.get('fair_id'):
            if self.env.context.get('active_model') == 'event.fair':
                vals['fair_id'] = self.env.context.get('active_id')
        return vals

    def action_apply(self):
        """O modelo é APLICADO, não copiado.

        Linha que já saiu para a feira não se apaga nem se rebaixa: o
        movimento já existe, e mexer nela faria a grade mentir sobre o que
        foi despachado. Substituir só limpa o que ainda não saiu.
        """
        self.ensure_one()
        fair = self.fair_id
        if self.mode == 'replace':
            fair.line_ids.filtered(lambda l: not l.qty_sent).unlink()
        ja_na_grade = {line.product_id: line for line in fair.line_ids}
        novas = []
        for line in self.template_id.line_ids:
            existente = ja_na_grade.get(line.product_id)
            if existente is not None:
                # Já despachado fica onde está; o resto sobe para o que o
                # modelo pede, sem somar duas aplicações do mesmo modelo.
                if existente.qty_planned < line.qty_planned:
                    existente.qty_planned = line.qty_planned
                # O mínimo do modelo vale mesmo para linha que já existia:
                # é a decisão de quem monta a grade, e não uma quantidade
                # que a feira já consumiu.
                if line.qty_min:
                    existente.qty_min = line.qty_min
                continue
            novas.append({
                'fair_id': fair.id,
                'product_id': line.product_id.id,
                'qty_planned': line.qty_planned,
                'qty_min': line.qty_min,
            })
        if novas:
            self.env['event.fair.line'].create(novas)
        return {'type': 'ir.actions.act_window_close'}


class EventFairSaveTemplate(models.TransientModel):
    _name = 'event.fair.save.template'
    _description = 'Save the Fair Grid as a Template'

    fair_id = fields.Many2one(
        'event.fair', string='Fair', required=True, ondelete='cascade')
    name = fields.Char(string='Name', required=True)
    use_sent = fields.Boolean(
        string='Record what actually went', default=False,
        help="Off, the template keeps the planned quantities. On, it keeps "
             "what was actually shipped, replenishment included, which is "
             "the grid the fair really had.")

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        fair = None
        if self.env.context.get('active_model') == 'event.fair':
            fair = self.env['event.fair'].browse(
                self.env.context.get('active_id'))
        if fair:
            if 'fair_id' in fields_list:
                vals['fair_id'] = fair.id
            if 'name' in fields_list and not vals.get('name'):
                vals['name'] = fair.name
        return vals

    def action_save(self):
        self.ensure_one()
        fair = self.fair_id
        linhas = []
        for line in fair.line_ids:
            qty = line.qty_sent if self.use_sent else line.qty_planned
            if qty <= 0:
                continue
            linhas.append((0, 0, {
                'product_id': line.product_id.id,
                'qty_planned': qty,
                'qty_min': line.qty_min,
            }))
        if not linhas:
            raise UserError(_("There is nothing in this grid to save."))
        template = self.env['event.fair.template'].create({
            'name': self.name,
            'company_id': fair.company_id.id,
            'line_ids': linhas,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'event.fair.template',
            'res_id': template.id,
            'view_mode': 'form',
            'target': 'current',
        }
