# -*- coding: utf-8 -*-
"""O dinheiro dos caixas de feira: decidido UMA VEZ por empresa.

Antes disso o caixa deixava as formas de pagamento por conta do PDV, e o PDV
faz três coisas que numa feira dão errado (30/10/2026, n-1):

  - só o PRIMEIRO caixa da empresa ganha Dinheiro. O núcleo entrega a cada
    caixa novo uma forma de dinheiro que nenhum outro use, e o primeiro caixa
    a segura mesmo arquivado: na Edlab, 31 de 32 caixas de feira nasceram sem
    gaveta;
  - o diário desse Dinheiro nasce sem conta de sobra e de falta (os padrões
    da empresa estavam vazios), e o caixa recusa abrir: "Você precisa de uma
    conta de perdas e lucros em seu diário de caixa";
  - o cartão cai no primeiro diário de banco que o núcleo acha -- na Edlab,
    "Ajustes (acertos e baixas manuais)".

O núcleo também não deixa dois caixas ATIVOS dividirem um Dinheiro, nem duas
formas de dinheiro dividirem um diário. Por isso o que se configura aqui são
as CONTAS, e os diários são GAVETAS emprestadas: "Dinheiro de feira 01",
"02"... O caixa novo pega uma gaveta livre, e quando a feira volta o caixa
arquivado a devolve. A empresa fica com tantos diários quantos caixas já
abriu AO MESMO TEMPO, e não um por caixa que existiu.

Sobra e falta moram nos campos do próprio núcleo
(`default_cash_difference_*`), e não em campos nossos: são eles que o Odoo
usa para preencher QUALQUER diário de dinheiro novo da empresa, de feira ou
não.

O FECHAMENTO pede mais três contas, e o primeiro caixa da n-1 no staging
(03/11/2026, EV/2026/00004) tropeçou nas três, uma depois da outra:

  - a RECEITA da venda, que o PDV busca no produto, na categoria e, por
    último, no diário de vendas do PDV ("Ponto de Venda", POSS) -- que o
    núcleo cria sem conta;
  - a TRANSITÓRIA do diário da gaveta, sem a qual o dinheiro contado não
    vira linha de extrato. O núcleo a copia da empresa
    (`account_journal_suspense_account_id`), que no plano migrado é vazia;
  - a conta A RECEBER do PDV (`account_default_pos_receivable_account_id`),
    onde o pagamento espera o fechamento. Vazia nas seis empresas: "Conta
    necessária ausente na linha contábil".

As duas últimas também são campos do núcleo, pelo mesmo motivo de sobra e
falta. A receita é campo nosso, porque o núcleo não tem um: ela se escreve no
diário de vendas dos caixas de feira quando ele está vazio.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    fair_cash_account_id = fields.Many2one(
        'account.account', string='Fair registers cash account',
        domain="[('account_type', '=', 'asset_cash')]",
        help="Where the money in the drawer of every fair register is "
             "kept. Without it, each register would create an account of "
             "its own in the chart.")
    fair_income_account_id = fields.Many2one(
        'account.account', string='Fair registers sales account',
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        help="Revenue of a counter sale whose product and category have no "
             "revenue account. It goes on the registers' sales journal, "
             "which the point of sale creates without one.")
    fair_payment_method_ids = fields.Many2many(
        'pos.payment.method', 'res_company_fair_pos_payment_method_rel',
        'company_id', 'payment_method_id',
        string='Fair registers other payment methods',
        domain="[('is_cash_count', '=', False)]",
        help="Card machine, PIX: what every fair register takes besides "
             "cash.")

    @api.constrains('fair_payment_method_ids')
    def _check_fair_payment_method_ids(self):
        for company in self:
            if company.fair_payment_method_ids.filtered('is_cash_count'):
                raise ValidationError(_(
                    "Cash is not chosen here: each fair register gets a cash "
                    "drawer of its own. Pick only card, PIX and the like."))

    def _fair_register_missing(self):
        """O que falta para esta empresa criar um caixa de feira."""
        self.ensure_one()
        faltando = []
        if not self.fair_cash_account_id:
            faltando.append(_('Cash account'))
        if not self.default_cash_difference_income_account_id:
            faltando.append(_('Cash surplus account'))
        if not self.default_cash_difference_expense_account_id:
            faltando.append(_('Cash shortage account'))
        if not self.account_journal_suspense_account_id:
            faltando.append(_('Transit account'))
        if not self.account_default_pos_receivable_account_id:
            faltando.append(_('Register receivable account'))
        if not self.fair_income_account_id:
            faltando.append(_('Sales account'))
        return faltando

    def _fair_free_drawer(self):
        """Uma gaveta que nenhum caixa ativo usa; a próxima, se não houver."""
        self.ensure_one()
        Metodo = self.env['pos.payment.method'].sudo()
        gavetas = Metodo.with_context(active_test=False).search([
            ('fair_drawer', '=', True), ('company_id', '=', self.id)],
            order='id')
        ocupadas = self.env['pos.config'].sudo().search([
            ('payment_method_ids', 'in', gavetas.ids)]).payment_method_ids
        livres = gavetas.filtered('active') - ocupadas
        if livres:
            return livres[0]
        diario = self.env['account.journal'].sudo().create({
            'name': _('Fair cash %s', '%02d' % (len(gavetas) + 1)),
            'type': 'cash',
            'company_id': self.id,
            'default_account_id': self.fair_cash_account_id.id,
            'profit_account_id':
                self.default_cash_difference_income_account_id.id,
            'loss_account_id':
                self.default_cash_difference_expense_account_id.id,
            'suspense_account_id':
                self.account_journal_suspense_account_id.id,
            'show_on_dashboard': False,
        })
        return Metodo.create({
            'name': _('Cash'),
            'journal_id': diario.id,
            'company_id': self.id,
            'fair_drawer': True,
        })

    def _fair_drawers(self):
        return self.env['pos.payment.method'].sudo().search([
            ('fair_drawer', '=', True), ('company_id', 'in', self.ids)])

    def _fair_ensure_drawer(self):
        """A gaveta 01 nasce com a configuração, e não com o primeiro caixa.

        Assim ela aparece na Contabilidade antes da primeira feira, e quem
        quiser ajustar o diário ajusta com calma, e não no balcão.
        """
        for company in self:
            if not company._fair_register_missing() \
                    and not company._fair_drawers():
                company._fair_free_drawer()

    def _fair_fill_cash_journals(self):
        """Completa as contas vazias dos caixas de feira que já existiam.

        Sobra, falta e transitória nas gavetas; receita no diário de vendas.

        O diário copia as contas no dia em que nasce: configurar a empresa
        depois não alcança o caixa já criado. Só se preenche o que está
        VAZIO -- conta escolhida à mão num diário não se troca por baixo.
        """
        for company in self:
            caixas = self.env['pos.config'].sudo().with_context(
                active_test=False).search([
                    ('company_id', '=', company.id),
                    ('fair_id', '!=', False)])
            gavetas = self.env['pos.payment.method'].sudo().search([
                ('fair_drawer', '=', True), ('company_id', '=', company.id)])
            diarios = (caixas.payment_method_ids.filtered('is_cash_count')
                       | gavetas).journal_id
            lucro = company.default_cash_difference_income_account_id
            perda = company.default_cash_difference_expense_account_id
            transito = company.account_journal_suspense_account_id
            receita = company.fair_income_account_id
            if transito:
                diarios.filtered(lambda d: not d.suspense_account_id).write(
                    {'suspense_account_id': transito.id})
            if receita:
                caixas.journal_id.filtered(
                    lambda d: not d.default_account_id).write(
                        {'default_account_id': receita.id})
            if lucro:
                diarios.filtered(lambda d: not d.profit_account_id).write(
                    {'profit_account_id': lucro.id})
            if perda:
                diarios.filtered(lambda d: not d.loss_account_id).write(
                    {'loss_account_id': perda.id})
