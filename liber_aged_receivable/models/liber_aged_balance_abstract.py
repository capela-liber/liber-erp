# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class LiberAgedBalanceAbstract(models.AbstractModel):
    """O motor comum do Aged Receivable e do Aged Payable.

    As duas telas são a mesma conta olhada de lados opostos: uma soma o que
    entra, a outra o que sai. Manter a lógica das faixas em dois lugares
    garantiria que um conserto chegasse só num deles, então ela mora aqui e
    cada modelo concreto diz apenas de que tipo de conta lê e com que sinal
    apresenta o saldo.
    """

    _name = 'liber.aged.balance.abstract'
    _description = 'Aged Balance (shared engine)'
    _order = 'date_maturity, id'
    _rec_name = 'move_name'

    # Cada concreto sobrescreve: tipo de conta e o sinal em que o saldo é
    # apresentado. A pagar vive a crédito no razão, e o contador quer ver a
    # dívida positiva -- é a mesma convenção do Odoo.
    _aged_account_type = 'asset_receivable'
    _aged_sign = 1
    # Os documentos que ESTE lado emite. Servem para separar quem é de fato
    # cliente (ou fornecedor) de quem só foi parar aqui.
    _aged_doc_types = ('out_invoice', 'out_refund', 'out_receipt')

    line_id = fields.Many2one('account.move.line', string='Journal Item',
                              readonly=True)
    move_id = fields.Many2one('account.move', string='Document', readonly=True)
    move_name = fields.Char(string='Number', readonly=True)
    move_type = fields.Char(string='Type', readonly=True)
    # O financeiro da casa PROVISIONA EM RASCUNHO: no prod ha 966 linhas de
    # rascunho no a pagar, somando R$ 4.080.175,51 que o relatorio nao via.
    # Rascunho nao e divida ainda -- nao tem numero, nao foi lancado -- mas e
    # compromisso conhecido, e quem planeja pagamento precisa ve-lo. Por isso
    # entra na view e fica FORA por padrao, atras de um filtro.
    move_state = fields.Char(string='Document Status', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    # O mesmo cliente compra de mais de uma empresa da casa, e várias razões
    # sociais distintas são o MESMO devedor -- as lojas de uma rede, as filiais
    # de uma distribuidora. Cobrar por razão social é cobrar a mesma dívida em
    # pedaços; por isso o grupo econômico é campo do relatório, e não uma
    # planilha à parte.
    #
    # É o `commercial_group_display` do `liber_partner_group`, e não o
    # `partner_group_id`, porque a REGRA DA CASA é: quem não é rede é ele
    # mesmo. Agrupar pelo many2one jogava 4.265 clientes num balde "Nenhum",
    # que é o maior grupo da tela e não diz nada. O Char stored já resolve
    # isso na origem, e ainda sobe o contato-pessoa para a loja que o atende.
    partner_group = fields.Char(string='Economic Group', readonly=True)
    # O canal por onde a venda entrou. Mora no `account.move` (o `crm.team`),
    # não na linha: cobrar a Amazon é outro trabalho que cobrar a livraria de
    # rua, e a carteira só separa os dois se o canal estiver na tela.
    team_id = fields.Many2one('crm.team', string='Sales Channel',
                              readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Journal', readonly=True)
    invoice_date = fields.Date(string='Invoice Date', readonly=True)
    date_maturity = fields.Date(string='Due Date', readonly=True)
    days_overdue = fields.Integer(string='Days Overdue', readonly=True)
    # O espelho do de cima: quantos dias faltam para vencer, zero quando já
    # venceu. Existe para a pergunta "o que vence nos próximos N dias", que
    # o painel de Recebíveis faz e que um domínio estático não consegue
    # fazer com datas (não há "hoje" num domínio de planilha). No a pagar é
    # a mesma pergunta, olhada do caixa.
    days_to_due = fields.Integer(string='Days to Due', readonly=True)

    # As seis faixas. Cada uma carrega o residual inteiro da linha ou zero:
    # somadas dão o total, e agrupadas por parceiro dão a matriz da tela do
    # Enterprise sem nenhuma conta a mais.
    amount_current = fields.Monetary(string='Not Due', readonly=True)
    amount_30 = fields.Monetary(string='1-30', readonly=True)
    amount_60 = fields.Monetary(string='31-60', readonly=True)
    amount_90 = fields.Monetary(string='61-90', readonly=True)
    amount_120 = fields.Monetary(string='91-120', readonly=True)
    amount_older = fields.Monetary(string='Older', readonly=True)
    amount_total = fields.Monetary(string='Total', readonly=True)

    # Conciliar acontece DENTRO de uma conta e exige os dois lados. Quando o
    # parceiro só tem lançamentos de um lado -- 28 linhas de -335,00 e nenhum
    # débito, que foi o caso que apareceu na conta ::dep:: -- não há o que
    # casar. Sem este campo o botão aparecia assim mesmo e só dizia "não há
    # nada a conciliar" depois do clique, o que é constatar em vez de ajudar.
    can_reconcile = fields.Boolean(string='Can Be Reconciled', readonly=True)

    # Um saldo em conta de cliente pressupõe um cliente. Quando o parceiro
    # nunca emitiu um documento deste lado, não há fatura a caminho e nunca
    # haverá: a linha está no razão errado, e o conserto é RECLASSIFICAR, não
    # conciliar nem cobrar.
    #
    # O caso que fez este campo existir: a ADOBE SYSTEMS BRASIL, com 34
    # pagamentos na conta-ponte `1.1.2.900 ::dep::` do a receber e nenhuma
    # fatura de cliente na vida -- é fornecedor. No prod são 237 parceiros
    # assim, somando R$ 2.286.154 em contas a receber.
    partner_off_ledger = fields.Boolean(
        string='Wrong Ledger', readonly=True,
        help='The partner has never issued a document on this side, so no '
             'invoice is coming. The line needs reclassifying, not chasing.')

    @classmethod
    def _aged_sql(cls, table, account_type, sign, doc_types=()):
        """A view. `sign` inverte a apresentação sem tocar no razão."""
        tipos = ', '.join("'%s'" % t for t in doc_types)
        s = '%d * ' % sign
        # `date_maturity` é nulo em lançamento que não é fatura -- o pagamento
        # avulso, a ponte da migração. Cair para `date` mantém essas linhas na
        # tela em vez de jogá-las todas em "Não vencido".
        venc = 'COALESCE(aml.date_maturity, aml.date)'
        atraso = 'CURRENT_DATE - %s' % venc

        def faixa(condicao):
            return ('CASE WHEN %s THEN %saml.amount_residual ELSE 0 END'
                    % (condicao, s))

        return """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    aml.id                            AS id,
                    aml.id                            AS line_id,
                    aml.move_id                       AS move_id,
                    am.name                           AS move_name,
                    am.move_type                      AS move_type,
                    am.state                          AS move_state,
                    aml.partner_id                    AS partner_id,
                    rp.commercial_group_display       AS partner_group,
                    am.team_id                        AS team_id,
                    aml.company_id                    AS company_id,
                    co.currency_id                    AS currency_id,
                    aml.account_id                    AS account_id,
                    aml.journal_id                    AS journal_id,
                    am.invoice_date                   AS invoice_date,
                    {venc}                            AS date_maturity,
                    GREATEST({atraso}, 0)::integer    AS days_overdue,
                    GREATEST(-({atraso}), 0)::integer AS days_to_due,
                    {f_atual}                         AS amount_current,
                    {f_30}                            AS amount_30,
                    {f_60}                            AS amount_60,
                    {f_90}                            AS amount_90,
                    {f_120}                           AS amount_120,
                    {f_older}                         AS amount_older,
                    {s}aml.amount_residual            AS amount_total,
                    (am.state = 'posted'
                     AND SUM(CASE WHEN aml.amount_residual > 0 THEN 1 ELSE 0 END)
                         OVER par > 0
                     AND SUM(CASE WHEN aml.amount_residual < 0 THEN 1 ELSE 0 END)
                         OVER par > 0)                AS can_reconcile,
                    (aml.partner_id IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM account_move doc
                                      WHERE doc.partner_id = aml.partner_id
                                        AND doc.move_type IN ({tipos})))
                                                      AS partner_off_ledger
                  FROM account_move_line aml
                  JOIN account_move     am ON am.id = aml.move_id
                  JOIN account_account  aa ON aa.id = aml.account_id
                  JOIN res_company      co ON co.id = aml.company_id
                  LEFT JOIN res_partner rp ON rp.id = aml.partner_id
                 WHERE am.state IN ('posted', 'draft')
                   AND aa.account_type = '{account_type}'
                   AND ROUND(aml.amount_residual, 2) <> 0
                WINDOW par AS (
                    PARTITION BY aml.company_id, aml.account_id,
                                 aml.partner_id, aml.currency_id)
            )
        """.format(
            table=table, venc=venc, atraso=atraso, s=s,
            account_type=account_type, tipos=tipos,
            f_atual=faixa('%s <= 0' % atraso),
            f_30=faixa('%s BETWEEN 1 AND 30' % atraso),
            f_60=faixa('%s BETWEEN 31 AND 60' % atraso),
            f_90=faixa('%s BETWEEN 61 AND 90' % atraso),
            f_120=faixa('%s BETWEEN 91 AND 120' % atraso),
            f_older=faixa('%s > 120' % atraso),
        )

    # ------------------------------------------------------------------
    # A view SQL lê a TABELA; o ORM guarda escrita pendente em CACHE. Dentro
    # de uma transação que acabou de lançar algo -- um teste, um script de
    # `odoo shell`, um botão que posta e relê -- a linha existe para o Odoo e
    # não existe para o Postgres, e o relatório vem vazio sem dizer por quê.
    #
    # Foi exatamente o que aconteceu ao escrever os testes: o primeiro
    # lançamento aparecia (a busca anterior tinha descarregado o cache por
    # acaso) e os seguintes sumiam. Descarregar as duas tabelas de origem
    # antes de consultar custa pouco -- relatório se lê, não se escreve.
    # E há a metade oposta do mesmo problema: o id de uma linha desta view é
    # o id do item de diário, que NÃO muda quando o razão à volta muda. Uma
    # linha já lida fica no cache com o valor antigo, e campos que dependem do
    # conjunto -- `can_reconcile`, `partner_off_ledger` -- continuam
    # respondendo o que valia antes. Num pedido web isso não aparece (cada
    # requisição nasce com cache limpo); num teste ou num script que lança e
    # relê, aparece e engana. Relatório se lê do banco: invalidar é o certo.
    def _descarregar_origem(self):
        self.env['account.move.line'].flush_model()
        self.env['account.move'].flush_model()
        # `res.partner` entrou na lista quando a view passou a ler o
        # `commercial_group_display`. Ele é COMPUTADO e stored: pôr o parceiro
        # numa rede recalcula a coluna, mas o novo valor fica no cache do ORM
        # até alguém descarregar. Sem esta linha o relatório continuava
        # agrupando pela rede ANTIGA -- o teste
        # `test_com_rede_o_grupo_e_a_rede` foi quem mostrou.
        self.env['res.partner'].flush_model()
        self.invalidate_model()

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        self._descarregar_origem()
        return super()._search(domain, offset=offset, limit=limit,
                               order=order, **kwargs)

    @api.model
    def _read_group(self, domain, groupby=(), aggregates=(), having=(),
                    offset=0, limit=None, order=None):
        self._descarregar_origem()
        return super()._read_group(domain, groupby=groupby,
                                   aggregates=aggregates, having=having,
                                   offset=offset, limit=limit, order=order)

    # ------------------------------------------------------------------
    def action_open_move(self):
        """Pula para a fatura -- ou para o pagamento, quando a linha é o
        dinheiro solto que ainda não baixou nada."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_registrar_pagamento(self):
        """Abre o registrar-pagamento do Odoo com as faturas selecionadas.

        Serve o caminho de quem cobra: ve a divida na tela de idade, marca as
        linhas e baixa dali mesmo, sem ter de abrir fatura por fatura.

        Duas recusas explicadas, em vez de erro do framework:

        * Linha que nao e FATURA nao entra. O relatorio mostra tambem
          pagamento solto e lancamento de ajuste, e o assistente do Odoo so
          sabe liquidar documento (`is_invoice`). Selecionar uma mistura
          aproveita as faturas e diz quantas ficaram de fora.
        * EMPRESAS diferentes nao vao juntas. O assistente monta um pagamento
          so, e pagamento pertence a uma empresa: misturar produziria
          lancamento entre livros distintos.
        """
        rascunhos = self.filtered(lambda l: l.move_state != 'posted')
        if rascunhos:
            raise UserError(self.env._(
                'The selection has %(n)s draft document(s). A draft cannot be '
                'paid: post it first, and it becomes a debt that can be '
                'settled.', n=len(rascunhos)))
        faturas = self.mapped('move_id').filtered(lambda m: m.is_invoice())
        if not faturas:
            raise UserError(self.env._(
                'None of the selected lines is an invoice. Only invoices can '
                'be settled here: a loose payment or an adjustment entry has '
                'nothing to pay, it is what pays.'))
        empresas = faturas.mapped('company_id')
        if len(empresas) > 1:
            raise UserError(self.env._(
                'The selection mixes %(n)s companies (%(names)s). A payment '
                'belongs to one company, so settle one company at a time.',
                n=len(empresas),
                names=', '.join(empresas.mapped('name'))))
        fora = len(self) - len(self.filtered(
            lambda l: l.move_id in faturas))
        nome = self.env._('Register Payment')
        if fora:
            nome = self.env._('Register Payment (%(n)s line(s) left out)',
                              n=fora)
        return {
            'name': nome,
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': faturas.ids,
                'default_company_id': empresas.id,
            },
        }

    def action_open_reconcile(self):
        """Pula para a tela de baixa manual da OCA, já posicionada neste
        parceiro e nesta conta.

        O `account.account.reconcile` é view SQL agrupada por conta +
        parceiro e chaveada por `min(aml.id)`, então não se pode montar o id:
        procura-se pelo par.
        """
        self.ensure_one()
        if self.move_state != 'posted':
            raise UserError(self.env._(
                'This line is a draft document. A draft has no accounting '
                'entry yet, so there is nothing to reconcile against. Post '
                '%(doc)s first.', doc=self.move_name or ''))
        if not self.partner_id:
            raise UserError(self.env._(
                'This line has no partner, so Odoo has no set of entries to '
                'match it against. Set the partner on the journal item and '
                'the line becomes reconcilable.'))
        if not self.can_reconcile:
            raise UserError(self.env._(
                'Nothing to match here. Reconciling means cancelling a debit '
                'against a credit inside one account, and every open line of '
                '%(partner)s on %(account)s is on the same side. What is '
                'missing is the other half of the entry, not the matching.',
                partner=self.partner_id.display_name,
                account=self.account_id.display_name))
        alvo = self.env['account.account.reconcile'].search([
            ('account_id', '=', self.account_id.id),
            ('partner_id', '=', self.partner_id.id),
        ], limit=1)
        if not alvo:
            raise UserError(self.env._(
                'Odoo has no reconciliation view for %(partner)s on '
                '%(account)s. This usually means the open lines sit in '
                'different currencies.',
                partner=self.partner_id.display_name,
                account=self.account_id.display_name))
        # KANBAN, e nao form -- e a diferenca entre a tela abrir e estourar.
        #
        # O form de `account.account.reconcile` chama `this.env.exposeController`
        # no seu `setup()`, e esse metodo NAO existe no cliente web do Odoo:
        # quem o injeta e o controller KANBAN da propria OCA, por `useSubEnv`
        # (`reconcile_kanban/reconcile_controller.esm.js`). Ou seja, o form so
        # existe embutido dentro do kanban. Abri-lo como acao de topo cria um
        # `env` sem o pai, `exposeController` vem `undefined` e o Owl estoura
        # com "TypeError: this.env.exposeController is not a function".
        #
        # Nao e bug da OCA: as tres acoes do proprio modulo abrem em kanban.
        # O `view_ref` no contexto e obrigatorio -- e ele que diz ao kanban
        # qual form embutir; sem ele a tela vem sem o painel de conciliacao.
        # E o `res_id` continua valendo: o `action_service` do Odoo o copia
        # para `resId` seja qual for o tipo de view, e o controller da OCA o
        # respeita para escolher o par a mostrar.
        return {
            'name': self.env._('Reconcile'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.account.reconcile',
            'view_mode': 'kanban',
            'views': [(self.env.ref(
                'account_reconcile_oca.account_account_reconcile_kanban_view'
            ).id, 'kanban')],
            'domain': [('account_id', '=', self.account_id.id)],
            'res_id': alvo.id,
            'target': 'current',
            'context': {
                'view_ref':
                    'account_reconcile_oca.account_account_reconcile_form_view',
            },
        }
