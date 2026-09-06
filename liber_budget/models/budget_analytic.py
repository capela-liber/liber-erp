# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class BudgetAnalytic(models.Model):
    _name = 'budget.analytic'
    _description = "Budget"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char(required=True, tracking=True)
    user_id = fields.Many2one(
        'res.users', string="Responsible",
        default=lambda self: self.env.user, tracking=True)
    date_from = fields.Date(string="Start Date", required=True, tracking=True)
    date_to = fields.Date(string="End Date", required=True, tracking=True)
    state = fields.Selection(
        selection=[
            ('draft', "Draft"),
            ('confirmed', "Open"),
            ('revised', "Revised"),
            ('done', "Done"),
            ('canceled', "Canceled"),
        ],
        string="Status", required=True, default='draft',
        readonly=True, copy=False, tracking=True)
    company_id = fields.Many2one(
        'res.company', string="Company", required=True,
        default=lambda self: self.env.company)
    # A CONSOLIDAÇÃO. O orçamento pertence a UMA empresa (`company_id`), que
    # é quem o assina; `company_ids` diz de quais empresas ele SOMA o realizado.
    #
    # Por que existe: a casa monta orçamentos consolidados -- "A-Z: EL+HE" na
    # EdLab Participações, "A-Z: SA+LO" -- pondo o orçamento na holding e
    # puxando as posições das operadoras. O practical dava ZERO em 114 linhas,
    # porque o realizado era procurado nos livros da holding, onde as contas
    # das filhas não têm movimento.
    #
    # A saída natural seria empresa-pai, e ela está FECHADA: o Odoo recusa
    # (`res_company.write`: "The company hierarchy cannot be changed"), a
    # hierarquia só se define na criação, e no 19 `parent_id` significa FILIAL
    # -- estabelecimento da mesma pessoa jurídica --, o que estas cinco não
    # são: são CNPJs distintos, cada um emitindo a sua NFe.
    #
    # A própria empresa entra SEMPRE, sem precisar ser listada: aqui vão só as
    # OUTRAS. Vazio = só a própria, que é o padrão, e por isso os orçamentos
    # que já existem não mudam de comportamento.
    company_ids = fields.Many2many(
        'res.company', string="Also Consolidate",
        help="Other companies whose entries also feed the Practical column. "
             "This budget's own company is always included.")
    # O NOME das empresas consolidadas, legível por quem lê o orçamento.
    #
    # `company_ids` é many2one para `res.company`, e a regra de registro do
    # Odoo esconde empresa que a pessoa não tem no seletor -- então quem está
    # só na holding via a lista VAZIA, enquanto o practical já somava as
    # filhas. Um total que agrega o que o leitor não consegue nomear é pior do
    # que um total errado: ele não dá nem como conferir.
    #
    # Um Char computado com `sudo` resolve sem conceder acesso a registro
    # nenhum: mostra-se o NOME, não se abre a empresa.
    company_names = fields.Char(
        string="Consolidated From", compute='_compute_company_names',
        compute_sudo=True,
        help="Names of the companies whose entries feed the Practical column.")
    group_id = fields.Many2one('budget.group', string="Group")
    tag_ids = fields.Many2many('budget.tag', string="Tags")
    parent_id = fields.Many2one(
        'budget.analytic', string="Revision Of",
        index=True, ondelete='cascade', copy=False)
    children_ids = fields.One2many(
        'budget.analytic', 'parent_id', string="Revisions")
    revision_count = fields.Integer(compute='_compute_revision_count')

    budget_line_ids = fields.One2many(
        'budget.line', 'budget_analytic_id', string="Budget Lines", copy=True)

    # ----------------------------------------------------------------
    # Computes / constraints
    # ----------------------------------------------------------------
    @api.depends('children_ids')
    def _compute_revision_count(self):
        for budget in self:
            budget.revision_count = len(budget.children_ids)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for budget in self:
            if budget.date_from and budget.date_to and budget.date_from > budget.date_to:
                raise ValidationError(_("The end date cannot be earlier than the start date."))

    @api.depends('company_id', 'company_ids')
    def _compute_company_names(self):
        """Lê a relação DO BANCO, não do ORM -- e a razão é uma armadilha.

        `company_ids` aponta para `res.company`, que tem regra de registro: a
        leitura devolve só as empresas do seletor de quem lê. E o valor
        filtrado FICA NO CACHE. Como o formulário lê os dois campos no mesmo
        `web_read`, e a ordem entre eles não é garantida, um `compute_sudo`
        que dependa de `company_ids` pode computar em cima do valor já
        filtrado -- e aí mostra só a própria empresa, que é justamente o que
        este campo existe para evitar.

        Não é hipótese: foi o que aconteceu no teste de 31/08, e só apareceu
        porque o teste lia `company_ids` antes.

        Consultar a tabela do many2many é imune a isso: o cache do ORM não
        entra na conta.
        """
        self.env.flush_all()
        nomes = {}
        if self.ids:
            self.env.cr.execute("""
                SELECT rel.budget_analytic_id, c.name
                  FROM budget_analytic_res_company_rel rel
                  JOIN res_company c ON c.id = rel.res_company_id
                 WHERE rel.budget_analytic_id IN %s
              ORDER BY c.name
            """, (tuple(self.ids),))
            for bid, nome in self.env.cr.fetchall():
                nomes.setdefault(bid, []).append(nome)
        for budget in self:
            todos = [budget.company_id.name] + [
                n for n in nomes.get(budget.id, [])
                if n != budget.company_id.name]
            budget.company_names = ", ".join(t for t in todos if t) or False

    def _companies_for_actuals(self):
        """As empresas de onde vem o realizado: a própria, MAIS as listadas.

        A própria entra sempre. Exigir que ela fosse repetida na lista era
        cerimônia sem ganho -- quem monta um "EL+HE" na holding quer dizer
        "além de mim, some EL e HE", e não "some EP, EL e HE".
        """
        self.ensure_one()
        return self.company_id | self.company_ids

    @api.constrains('parent_id')
    def _check_parent_cycle(self):
        if self._has_cycle():
            raise ValidationError(_("You cannot create a recursive budget revision."))

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft_canceled(self):
        if any(budget.state not in ('draft', 'canceled') for budget in self):
            raise UserError(_("You can only delete budgets in Draft or Canceled state."))

    # ----------------------------------------------------------------
    # State actions
    # ----------------------------------------------------------------
    def action_confirm(self):
        for budget in self:
            budget.state = 'revised' if budget.children_ids else 'confirmed'

    def action_set_draft(self):
        self.state = 'draft'

    def action_cancel(self):
        self.state = 'canceled'

    def action_done(self):
        self.state = 'done'

    def action_create_revision(self):
        revisions = self.env['budget.analytic']
        for budget in self:
            revision = budget.copy({
                'name': _("%s (revision)", budget.name),
                'parent_id': budget.id,
            })
            budget.state = 'revised'
            revisions |= revision
        return {
            'type': 'ir.actions.act_window',
            'name': _("Budget Revision"),
            'res_model': 'budget.analytic',
            'view_mode': 'form',
            'res_id': revisions[:1].id,
            'target': 'current',
        }

    def action_open_revisions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Revisions"),
            'res_model': 'budget.analytic',
            'view_mode': 'list,form',
            'domain': [('parent_id', '=', self.id)],
        }

    @api.model
    def _demo_post_moves(self, move_xmlids):
        """Helper p/ a demo data postar os lançamentos de exemplo."""
        for xmlid in move_xmlids:
            move = self.env.ref(xmlid, raise_if_not_found=False)
            if move and move.state == 'draft':
                move.action_post()
