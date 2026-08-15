# -*- coding: utf-8 -*-
from odoo import fields, models, tools

# Os tipos de conta de resultado, na ordem em que se lê um demonstrativo:
# receita, custo do que se vendeu, e o resto da despesa. O par é
# (valor nesta view, valor em `account.account.account_type`).
#
# O prefixo numérico não é enfeite: o pivot ordena os grupos pela própria coluna
# do GROUP BY (`models._read_group_orderby`, ramo `else`), então a ordem das
# linhas *é* a ordem alfabética do valor. Sem o prefixo, `expense` viria antes de
# `income` e o demonstrativo abriria de cabeça para baixo -- com a despesa no
# topo e a receita no meio. Nem `group_expand=True` nem `_order_field_to_sql`
# alcançam esse ponto no 19; foram testados.
PNL_ACCOUNT_TYPES = [
    ('1_income', 'income'),
    ('2_income_other', 'income_other'),
    ('3_expense_direct_cost', 'expense_direct_cost'),
    ('4_expense', 'expense'),
    ('5_expense_other', 'expense_other'),
    ('6_expense_depreciation', 'expense_depreciation'),
]


def _pnl_account_type_selection(self):
    """Os mesmos rótulos do core -- inclusive as traduções dele."""
    do_core = dict(self.env['account.account']._fields[
        'account_type']._description_selection(self.env))
    return [(valor, do_core.get(cru, cru)) for valor, cru in PNL_ACCOUNT_TYPES]


class BudgetPnlReport(models.Model):
    """Demonstrativo de Resultado (P&L) como view SQL, uma linha por item do
    Razão em conta de resultado.

    O Odoo 19 Community traz o *motor* de relatórios (`account.report`) mas
    nenhum demonstrativo montado nem tela para abri-lo -- só os três relatórios
    de imposto em `account/data/account_reports_data.xml`. Este modelo preenche
    a lacuna pelo caminho barato: uma view SQL somada num pivot nativo, com
    exportação e drill-down de graça.

    Convenção de sinal igual à do resto do módulo (P&L): receita **+**,
    despesa **-**, e portanto o total geral já é o resultado do período.
    """
    _name = 'budget.pnl.report'
    _description = "Profit & Loss"
    _auto = False
    _order = 'date desc, code'

    # --- dimensões -------------------------------------------------------
    date = fields.Date(string="Date", readonly=True)
    account_id = fields.Many2one(
        'account.account', string="Account", readonly=True)
    code = fields.Char(string="Code", readonly=True)
    group_id = fields.Many2one(
        'account.group', string="Account Group", readonly=True,
        help="Group of the chart of accounts that matches the account code "
             "prefix. Empty while no account groups are configured.")
    account_type = fields.Selection(
        selection=_pnl_account_type_selection,
        string="Account Type", readonly=True,
        help="The account type, as the Odoo chart defines it. Only the six "
             "P&L types occur here. Careful: the stored value carries an "
             "ordering prefix ('1_income', not 'income') so the statement "
             "reads top-down -- use the Income / Cost of Revenue / Expenses "
             "filters instead of writing the raw value in a domain.")
    journal_id = fields.Many2one(
        'account.journal', string="Journal", readonly=True)
    partner_id = fields.Many2one('res.partner', string="Partner", readonly=True)
    move_id = fields.Many2one('account.move', string="Journal Entry", readonly=True)
    company_id = fields.Many2one('res.company', string="Company", readonly=True)
    currency_id = fields.Many2one('res.currency', string="Currency", readonly=True)
    state = fields.Selection(
        selection=[('draft', "Draft"), ('posted', "Posted")],
        string="Status", readonly=True)

    # --- medida ----------------------------------------------------------
    amount = fields.Monetary(
        string="Amount", readonly=True,
        help="Balance with the P&L sign: income positive, expense negative. "
             "The grand total is the net result.")

    def init(self):
        """Monta a view.

        Dois detalhes do 19 que obrigam a mão pesada aqui:

        * o código da conta não é mais coluna -- virou `code_store`, um jsonb
          company-dependent chaveado pela empresa **raiz** (ver
          `account_account._compute_code`);
        * `account_account.group_id` é compute **sem store**, então não há o que
          juntar: a resolução por prefixo de código (`account_group`) precisa
          ser refeita em SQL, na mesma regra do core -- casa o prefixo mais
          longo, desempata pelo id.

        A CTE `acc` resolve código e grupo uma vez por (conta × empresa), em vez
        de uma vez por lançamento.
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW %s AS (
                WITH acc AS (
                    SELECT
                        aa.id      AS account_id,
                        c.id       AS company_id,
                        code.value AS code,
                        (
                            SELECT ag.id
                              FROM account_group ag
                             WHERE ag.company_id = raiz.id
                               AND code.value IS NOT NULL
                               AND ag.code_prefix_start
                                   <= LEFT(code.value, char_length(ag.code_prefix_start))
                               AND ag.code_prefix_end
                                   >= LEFT(code.value, char_length(ag.code_prefix_end))
                             ORDER BY char_length(ag.code_prefix_start) DESC, ag.id
                             LIMIT 1
                        ) AS group_id
                      FROM account_account aa
                      CROSS JOIN res_company c
                      CROSS JOIN LATERAL (
                          SELECT COALESCE(
                              NULLIF(split_part(c.parent_path, '/', 1), '')::int,
                              c.id
                          ) AS id
                      ) raiz
                      CROSS JOIN LATERAL (
                          SELECT COALESCE(
                              aa.code_store ->> raiz.id::text,
                              aa.code_store ->> c.id::text
                          ) AS value
                      ) code
                     WHERE split_part(aa.account_type, '_', 1) IN ('income', 'expense')
                )
                SELECT
                    aml.id           AS id,
                    aml.date         AS date,
                    aml.account_id   AS account_id,
                    acc.code         AS code,
                    acc.group_id     AS group_id,
                    CASE aa.account_type
                        WHEN 'income'               THEN '1_income'
                        WHEN 'income_other'         THEN '2_income_other'
                        WHEN 'expense_direct_cost'  THEN '3_expense_direct_cost'
                        WHEN 'expense'              THEN '4_expense'
                        WHEN 'expense_other'        THEN '5_expense_other'
                        WHEN 'expense_depreciation' THEN '6_expense_depreciation'
                        -- um tipo de resultado que o Odoo inventar depois cai
                        -- em "Outras", do lado certo -- nunca no lado errado
                        ELSE CASE split_part(aa.account_type, '_', 1)
                            WHEN 'income' THEN '2_income_other'
                            ELSE '5_expense_other'
                        END
                    END              AS account_type,
                    aml.journal_id   AS journal_id,
                    aml.partner_id   AS partner_id,
                    aml.move_id      AS move_id,
                    aml.company_id   AS company_id,
                    comp.currency_id AS currency_id,
                    aml.parent_state AS state,
                    -aml.balance     AS amount
                  FROM account_move_line aml
                  JOIN account_account aa ON aa.id = aml.account_id
                  JOIN res_company comp   ON comp.id = aml.company_id
                  JOIN acc ON acc.account_id = aml.account_id
                          AND acc.company_id = aml.company_id
                 WHERE aml.parent_state IN ('draft', 'posted')
            )
        """ % self._table)
