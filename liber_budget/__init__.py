from . import models


def post_init_hook(env):
    """Cria as colunas dinamicas de plano analitico (x_planN_id) nos nossos
    modelos que herdam analytic.plan.fields.mixin (budget.line), para os planos
    que ja existiam antes da instalacao."""
    env['account.analytic.plan'].search([])._sync_all_plan_column()
