# -*- coding: utf-8 -*-
"""A conta a pagar sabe de que EVENTO ela é.

A pergunta que ninguém conseguia responder era simples: o evento deu dinheiro?
O analítico responde, mas ninguém do comercial abre relatório analítico -- e a
resposta chegava semanas depois, quando já não mudava decisão nenhuma.

O elo é DUPLO, de propósito:

  - este campo, direto, é o que faz a aba de Custos existir, filtrar e somar.
    Montar a aba lendo distribuição analítica (um jsonb com peso por conta)
    seria frágil e lento;
  - o ANALÍTICO continua sendo preenchido, porque é ele que a contabilidade
    lê, e é nele que o custo do evento encontra a receita dele.

Gravar o evento numa conta preenche o analítico das linhas que ainda não
tinham um. Linha que já aponta para outro analítico não é tocada: quem
escolheu, escolheu.
"""
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    fair_id = fields.Many2one(
        'event.fair', string='Event', ondelete='set null', index=True,
        copy=False,
        help="The event this cost belongs to. It puts the document in the "
             "event's Costs tab and carries the event's analytic account.")

    @api.model_create_multi
    def create(self, vals_list):
        contas = super().create(vals_list)
        contas.filtered('fair_id')._carimbar_o_analitico_do_evento()
        return contas

    def write(self, vals):
        res = super().write(vals)
        if 'fair_id' in vals:
            self.filtered('fair_id')._carimbar_o_analitico_do_evento()
        return res

    def _carimbar_o_analitico_do_evento(self):
        # O núcleo CALCULA `analytic_distribution` a partir do parceiro e do
        # produto, e esse cálculo roda no flush -- depois do nosso create.
        # Sem esvaziar a fila primeiro, ele passava por cima do carimbo e a
        # linha nascia sem analítico nenhum.
        self.env.flush_all()
        for conta in self:
            # Sem PLANO configurado nas Definições não se inventa analítico --
            # e muito menos se recusa o lançamento do gasto. Ficar sem o
            # carimbo é um problema de cadastro; barrar a conta a pagar por
            # causa dele seria trocar um problema de configuração por um
            # problema de financeiro.
            analitico = (conta.fair_id.analytic_account_id
                         or (conta.fair_id.company_id.fair_analytic_plan_id
                             and conta.fair_id._get_analytic_account()))
            if not analitico:
                continue
            for linha in conta.invoice_line_ids:
                # `display_type` de linha normal é 'product', e não vazio:
                # testar a verdade dele pulava exatamente as linhas que
                # precisavam do carimbo. Seção, nota e linha de imposto é que
                # ficam de fora.
                if linha.display_type not in ('product', False) \
                        or linha.analytic_distribution:
                    continue
                linha.analytic_distribution = {str(analitico.id): 100}
