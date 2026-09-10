# -*- coding: utf-8 -*-
"""Abrir e fechar os caixas da feira.

O caixa não nasce com a feira. Nem toda feira vende no balcão -- há a que só
expõe, e há a que vende pela maquininha de outra pessoa --, e criar um Ponto
de Venda para cada evento encheria a tela de quem opera o PDV da casa com
caixas que ninguém abriu. Aqui se declara QUANTOS caixas a feira tem, e o
botão abre essa quantidade.

Caixa é plural porque feira grande é plural: uma Bienal tem duas ou três
frentes de pagamento, e uma fila só é uma fila que não anda.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EventFair(models.Model):
    _inherit = 'event.fair'

    # QUEM opera, e não quantos caixas. Contar máquinas não diz nada; o nome
    # de quem está no balcão é o que aparece na tela do PDV, é por ele que se
    # acha o caixa no meio dos caixas da casa, e é ele que responde pela
    # gaveta. Um operador, um caixa.
    cashier_ids = fields.One2many(
        'event.fair.cashier', 'fair_id', string='Operators')
    # O DESCONTO DA FEIRA é um número do evento, decidido por quem monta, e
    # não algo que cada um resolve no balcão. Ele vira o botão de desconto do
    # caixa, com esse percentual pronto.
    discount_pc = fields.Float(
        string='Fair discount (%)', digits=(5, 2), default=0.0,
        help="The discount this event practises. It becomes the discount "
             "button at the counter, already set. Operators can only apply "
             "this one; giving more is a manager's call.")
    pos_count = fields.Integer(
        string='Cash registers', compute='_compute_pos_count',
        help="One register per operator.")
    pos_config_ids = fields.One2many(
        'pos.config', 'fair_id', string='Registers')
    pos_picking_type_ids = fields.One2many(
        'stock.picking.type', 'fair_id', string='Register operations')
    # O primeiro caixa, para quem só tem um -- que é o caso comum. Serve à
    # ficha e aos atalhos; quem precisa de todos usa o One2many.
    pos_config_id = fields.Many2one(
        'pos.config', string='Cash register', compute='_compute_pos_first')
    pos_picking_type_id = fields.Many2one(
        'stock.picking.type', string='Register operation',
        compute='_compute_pos_first')
    pos_open_count = fields.Integer(
        string='Registers open', compute='_compute_pos')
    pos_order_count = fields.Integer(
        string='Register sales', compute='_compute_pos')
    pos_amount_total = fields.Monetary(
        string='Sold at the register', compute='_compute_pos',
        currency_field='company_currency_id')
    company_currency_id = fields.Many2one(
        related='company_id.currency_id', string='Currency')

    # A ABA DAS COMISSÕES lê as mesmas pessoas por outro campo, só para ter
    # colunas próprias: aqui é dinheiro, ali é quem opera o quê.
    commission_line_ids = fields.One2many(
        'event.fair.cashier', 'fair_id', string='Commissions')
    commission_total = fields.Monetary(
        string='Commission', currency_field='company_currency_id',
        compute='_compute_comissoes')
    daily_total = fields.Monetary(
        string='Dailies', currency_field='company_currency_id',
        compute='_compute_comissoes')
    loss_total = fields.Monetary(
        string='Losses at cost', currency_field='company_currency_id',
        compute='_compute_comissoes')
    team_loss_total = fields.Monetary(
        string='Split with the team', currency_field='company_currency_id',
        compute='_compute_comissoes',
        help="The part of the losses that vanished under the team's watch. "
             "What never arrived is not theirs, and is not split.")
    payout_total = fields.Monetary(
        string='To pay', currency_field='company_currency_id',
        compute='_compute_comissoes')
    bill_count = fields.Integer(compute='_compute_comissoes')

    @api.depends('cashier_ids.net_amount', 'cashier_ids.bill_id',
                 'loss_ids.value', 'loss_ids.charged_to_team')
    def _compute_comissoes(self):
        for fair in self:
            equipe = fair.cashier_ids
            fair.commission_total = sum(equipe.mapped('commission_amount'))
            fair.daily_total = sum(equipe.mapped('daily_amount'))
            fair.loss_total = sum(fair.loss_ids.mapped('value'))
            fair.team_loss_total = sum(fair.loss_ids.filtered(
                'charged_to_team').mapped('value'))
            fair.payout_total = sum(equipe.mapped('net_amount'))
            fair.bill_count = len(equipe.mapped('bill_id'))

    def action_generate_bills(self):
        """Uma conta a pagar por pessoa, com o evento no nome e no analítico.

        Só depois que o evento voltou: o rateio da perda depende do que a
        conferência do retorno apurou, e pagar antes seria pagar por cima de
        um número que ainda vai mudar.
        """
        self.ensure_one()
        if self.state != 'returned':
            raise UserError(_(
                "%s has not come home yet. The loss share is only known "
                "after the return is checked, and paying before that is "
                "paying over a number that will still change.",
                self.display_name))
        produto = self.company_id.fair_service_product_id
        if not produto:
            raise UserError(_(
                "Set the service that pays the event team in Settings: the "
                "bill needs a line, and inventing one here would put the "
                "cost in the wrong account."))
        analitico = self._get_analytic_account()
        contas = self.env['account.move']
        for operador in self.cashier_ids:
            if operador.bill_id or operador.net_amount <= 0:
                continue
            conta = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': operador.partner_id.id,
                'invoice_date': fields.Date.context_today(self),
                'ref': _('%(feira)s — %(pessoa)s', feira=self.display_name,
                         pessoa=operador.partner_id.name),
                'company_id': self.company_id.id,
                'invoice_line_ids': [(0, 0, {
                    'product_id': produto.id,
                    'name': _(
                        "%(feira)s: %(dias)s day(s) and commission, less the "
                        "share of what the event lost",
                        feira=self.display_name, dias=operador.days),
                    'quantity': 1,
                    'price_unit': operador.net_amount,
                    'analytic_distribution': {str(analitico.id): 100},
                })],
            })
            operador.sudo().bill_id = conta.id
            contas |= conta
        if contas:
            self.message_post(body=_(
                "%(quantos)s bill(s) created for the team of %(feira)s, "
                "totalling %(total)s.",
                quantos=len(contas), feira=self.display_name,
                total=sum(contas.mapped('amount_total'))))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Team bills'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in',
                        self.cashier_ids.mapped('bill_id').ids)],
        }

    def _contas_da_equipe_no_fechamento(self):
        """Encerrar o evento já deixa as contas da equipe prontas.

        Em RASCUNHO, sempre: criar conta a pagar não é pagar, e é o
        financeiro que confere e lança. O que se evita aqui é o esquecimento
        -- a equipe foi embora, o evento fechou, e três semanas depois
        alguém pergunta da diária.

        Quem ainda não tem número (comissão e diária em branco) não gera
        conta nenhuma: o botão da aba Comissões continua ali para quando os
        números forem preenchidos.
        """
        for fair in self:
            if not fair.company_id.fair_service_product_id:
                continue
            if not fair.cashier_ids.filtered(lambda c: c.net_amount > 0):
                continue
            try:
                with self.env.cr.savepoint():
                    fair.action_generate_bills()
            except Exception as erro:              # noqa: BLE001
                # Faltou configuração ou o contábil recusou: o evento VOLTA
                # do mesmo jeito. Estoque não espera contabilidade.
                fair.message_post(body=_(
                    "The team bills were not created automatically: %(erro)s "
                    "Use the button in the Commissions tab once it is "
                    "sorted.", erro=str(erro)[:200]))
        return True

    def action_view_bills(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Team bills'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in',
                        self.cashier_ids.mapped('bill_id').ids)],
        }

    @api.depends('cashier_ids')
    def _compute_pos_count(self):
        for fair in self:
            fair.pos_count = len(fair.cashier_ids)

    @api.depends('pos_config_ids', 'pos_picking_type_ids')
    def _compute_pos_first(self):
        for fair in self:
            fair.pos_config_id = fair.pos_config_ids[:1]
            fair.pos_picking_type_id = fair.pos_picking_type_ids[:1]

    @api.depends('pos_config_ids')
    def _compute_pos(self):
        for fair in self:
            # Conta também o caixa arquivado: a feira que voltou continua
            # tendo vendido o que vendeu.
            configs = fair.with_context(active_test=False).pos_config_ids
            pedidos = self.env['pos.order'].search(
                [('config_id', 'in', configs.ids)]) if configs \
                else self.env['pos.order']
            fair.pos_order_count = len(pedidos)
            fair.pos_amount_total = sum(pedidos.mapped('amount_total'))
            fair.pos_open_count = len(configs.filtered('active'))

    # --- abrir -----------------------------------------------------------
    def action_open_pos(self):
        """Abre (ou reabre) os caixas desta feira e leva para eles."""
        self.ensure_one()
        if self.state in ('draft', 'returned'):
            raise UserError(_(
                "The register opens for a fair that is planned or already on "
                "the road. %s is not.", self.display_name))
        if not self.cashier_ids:
            raise UserError(_(
                "Say who works the counter first: add at least one operator "
                "in the Registers tab of %s. A register with nobody on it is "
                "a machine, not a cash register.", self.display_name))
        # ARQUIVADO NÃO APARECE NO One2many, e é por isso que aqui se lê com
        # `active_test=False`: sem isso, uma feira que voltou (caixas
        # arquivados) e foi reaberta criaria caixas NOVOS por cima dos
        # antigos, com série nova e histórico partido.
        todos = self.with_context(active_test=False)
        arquivados = todos.pos_config_ids.filtered(lambda c: not c.active)
        if arquivados:
            arquivados.sudo().write({'active': True})
            todos.pos_picking_type_ids.filtered(
                lambda t: not t.active).sudo().write({'active': True})
        for operador in todos.cashier_ids.filtered(
                lambda c: not c.pos_config_id):
            caixa = self._criar_caixa(operador)
            operador.pos_config_id = caixa
            caixa.sudo().fair_cashier_id = operador.id
        self._liberar_titulos_no_pdv()
        self.invalidate_recordset(['pos_config_ids', 'pos_config_id'])
        caixas = self.pos_config_ids
        if len(caixas) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Cash register'),
                'res_model': 'pos.config',
                'res_id': caixas.id,
                'view_mode': 'form',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cash registers'),
            'res_model': 'pos.config',
            'view_mode': 'kanban,list,form',
            'domain': [('fair_id', '=', self.id)],
        }

    def _rotulo_caixa(self, operador):
        """O nome que a pessoa lê no cartão do PDV: feira e operador.

        Quem abre o Ponto de Venda procura a FEIRA -- e, dentro dela, o seu
        caixa. Numerar ("#1", "#2") obrigava a lembrar de cabeça qual número
        era o seu; o nome de quem opera não precisa ser lembrado.
        """
        self.ensure_one()
        return '%s - %s' % (self.name, operador.name)

    def _criar_caixa(self, operador):
        """A operação aponta para a MESA, e é isso que faz o PDV honesto."""
        self.ensure_one()
        company = self.company_id
        warehouse = company._fair_warehouse()
        if not warehouse:
            raise UserError(_(
                "%s has no warehouse, and the register needs one to hang "
                "the operation on.", company.display_name))
        # O PDV cria diário de caixa e formas de pagamento ao nascer, e para
        # isso a empresa precisa de contabilidade. Falhar aqui, com o nome do
        # que falta, é melhor do que o erro do núcleo três telas adiante.
        if not self.env['account.journal'].search(
                [('type', 'in', ('bank', 'cash')),
                 ('company_id', '=', company.id)], limit=1):
            raise UserError(_(
                "%s has no bank or cash journal: the register cannot take "
                "money in a company that has no place to put it.",
                company.display_name))
        # A série é POR CAIXA, e isso não é capricho. Dois caixas com o mesmo
        # `sequence_code` compartilham o prefixo do nome da transferência, e o
        # segundo colide no `stock_picking_name_uniq` do primeiro -- doença
        # que a casa já conhece na série COM/IN. O número inicial vem de
        # `_fair_series_start`, que começa adiante do maior já existente.
        codigo = (self.code or str(self.id)).replace('/', '')
        # A série é por CAIXA, e o desempate é o id do operador: dois caixas
        # da mesma feira com o mesmo prefixo colidiriam no nome da
        # transferência.
        if len(self.cashier_ids) > 1:
            codigo = '%s-%d' % (codigo, operador.id)
        prefixo = 'FEIRA/PDV/%s/' % codigo
        sequencia = self.env['ir.sequence'].sudo().create({
            'name': _('Fair register %s', codigo),
            'prefix': prefixo,
            'padding': 5,
            'company_id': company.id,
            'number_next': company._fair_series_start(prefixo),
        })
        rotulo = self._rotulo_caixa(operador)
        tipo = self.env['stock.picking.type'].sudo().create({
            'name': _('Register — %s', rotulo),
            'code': 'outgoing',
            'sequence_id': sequencia.id,
            'sequence_code': 'PDV%s' % codigo,
            'company_id': company.id,
            'warehouse_id': warehouse.id,
            'fair_id': self.id,
            'is_fair_register': True,
            'default_location_src_id': self._get_stock_location().id,
            'default_location_dest_id': self.env.ref(
                'stock.stock_location_customers').id,
        })
        vals = {
            'name': rotulo,
            'company_id': company.id,
            'picking_type_id': tipo.id,
            'fair_id': self.id,
        }
        vals.update(self._desconto_do_caixa(operador))
        config = self.env['pos.config'].sudo().with_company(company).create(
            vals)
        self.message_post(body=_(
            "%(feira)s — cash register %(caixa)s opened. It sells from the "
            "table, not from the warehouse.",
            feira=self.display_name, caixa=config.name))
        return config

    def _get_pricelist(self):
        """A lista de preços da feira: o desconto JÁ NO PREÇO.

        Botão de desconto é outra coisa -- é alguém apertar, título a título.
        O desconto de feira não é isso: é o preço que a feira pratica, e o
        balcão tem de mostrá-lo pronto, para o cliente e para quem vende.
        Uma regra global de percentual resolve, e vale para todo o catálogo
        da mesa.
        """
        self.ensure_one()
        if not self.discount_pc:
            return self.env['product.pricelist']
        nome = _('%(feira)s (-%(pc)s%%)',
                 feira=self.code or self.name, pc=self.discount_pc)
        lista = self.env['product.pricelist'].sudo().search([
            ('fair_id', '=', self.id)], limit=1)
        if not lista:
            lista = self.env['product.pricelist'].sudo().create({
                'name': nome,
                'company_id': self.company_id.id,
                'currency_id': self.company_id.currency_id.id,
                'fair_id': self.id,
            })
        else:
            lista.write({'name': nome})
        regra = lista.item_ids[:1]
        vals = {
            'pricelist_id': lista.id,
            'applied_on': '3_global',
            'compute_price': 'percentage',
            'percent_price': self.discount_pc,
        }
        if regra:
            regra.sudo().write(vals)
        else:
            self.env['product.pricelist.item'].sudo().create(vals)
        return lista

    def _desconto_do_caixa(self, operador):
        """O desconto deste caixa, conforme quem opera.

        Duas coisas diferentes, e a diferença é a regra da casa:

          - o PREÇO já sai com o desconto da feira, pela lista de preços.
            Ninguém precisa lembrar de apertar nada, e o cliente vê o preço
            certo;
          - `manual_discount` é a linha em branco, onde se digita um desconto
            a mais. Essa é do GERENTE. O assistente não digita desconto.

        Sem isso, ou ninguém dá desconto, ou todo mundo dá o que quiser -- e a
        segunda hipótese é dinheiro saindo pela porta.
        """
        self.ensure_one()
        gerente = operador.role == 'manager'
        vals = {'manual_discount': gerente}
        lista = self._get_pricelist()
        if lista:
            vals.update({
                'use_pricelist': True,
                'pricelist_id': lista.id,
                'available_pricelist_ids': [(6, 0, lista.ids)],
            })
        return vals

    def _sincronizar_desconto(self):
        """Muda o desconto do evento, muda o de cada caixa aberto."""
        for fair in self:
            for operador in fair.with_context(
                    active_test=False).cashier_ids.filtered('pos_config_id'):
                caixa = operador.pos_config_id
                if not caixa.active:
                    continue
                aberto = self.env['pos.session'].search_count(
                    [('config_id', '=', caixa.id), ('state', '!=', 'closed')])
                if aberto:
                    # O PDV recusa mexer em caixa vendendo, e com razão.
                    fair.message_post(body=_(
                        "%(caixa)s is selling right now: the new discount "
                        "only reaches it after the register closes.",
                        caixa=caixa.name))
                    continue
                caixa.sudo().write(fair._desconto_do_caixa(operador))
        return True

    def _liberar_titulos_no_pdv(self):
        """Põe a GRADE no balcão, e só a grade.

        Duas coisas, e as duas por experiência de tela. A primeira é a
        marca `available_in_pos`: sem ela o livro não aparece, e a equipe
        abriria o caixa na feira para encontrar a tela vazia. A segunda é o
        recorte por categoria de PDV: sem ele o balcão abre com o CATÁLOGO
        INTEIRO da empresa, e quem está na praça tem de procurar catorze
        títulos no meio de milhares. Uma mesa de feira é uma mesa; o balcão
        tem de mostrar o que está em cima dela.

        A categoria é por feira, porque duas feiras simultâneas têm mesas
        diferentes -- mas é a MESMA para os caixas de uma feira, que vendem
        da mesma mesa.
        """
        self.ensure_one()
        produtos = self.line_ids.mapped('product_id.product_tmpl_id')
        if not produtos:
            return produtos
        rotulo = _('Fair %s', self.code or self.name)
        categoria = self.env['pos.category'].sudo().search(
            [('name', '=', rotulo)], limit=1)
        if not categoria:
            categoria = self.env['pos.category'].sudo().create(
                {'name': rotulo})
        produtos.sudo().write({
            'available_in_pos': True,
            'pos_categ_ids': [(4, categoria.id)],
        })
        # Caixa COM SESSÃO ABERTA não se mexe, e o PDV tem razão: mudar o
        # sortimento no meio do turno é mudar a mesa embaixo de quem está
        # vendendo. Abrir um segundo caixa numa feira que já vende passava
        # por aqui e morria na trava do núcleo.
        abertos = self.env['pos.session'].sudo().search([
            ('config_id', 'in', self.pos_config_ids.ids),
            ('state', '!=', 'closed')]).mapped('config_id')
        alvo = self.pos_config_ids - abertos
        if alvo:
            alvo.sudo().write({
                'limit_categories': True,
                'iface_available_categ_ids': [(6, 0, categoria.ids)],
            })
        self._avisar_titulos_sem_receita(produtos)
        return produtos

    def _avisar_titulos_sem_receita(self, produtos):
        """Avisa cedo o que só apareceria com dinheiro na gaveta.

        Fechar a sessão do PDV é lançamento contábil, e o núcleo recusa
        fechá-la se um título vendido não tem conta de receita -- nem no
        produto, nem na categoria dele. O erro nasce no PIOR momento: no fim
        da feira, na hora de encerrar. Aqui ele vira aviso no histórico, com
        os nomes, enquanto ainda há tempo de configurar.

        É aviso, não trava: quem está na praça não resolve plano de contas, e
        barrar a abertura do caixa por isso seria a contabilidade impedindo a
        venda.
        """
        self.ensure_one()
        company = self.company_id
        sem_conta = produtos.with_company(company).filtered(
            lambda p: not p.property_account_income_id
            and not p.categ_id.property_account_income_categ_id)
        if not sem_conta:
            return sem_conta
        nomes = ', '.join(sem_conta[:8].mapped('name'))
        if len(sem_conta) > 8:
            nomes += _(' and %s more', len(sem_conta) - 8)
        self.message_post(body=_(
            "%(feira)s — heads up: %(quantos)s titles have no income account "
            "(neither on the product nor on its category): %(nomes)s. The "
            "register sells them, but it will refuse to CLOSE at the end of "
            "the fair until an account is set.",
            feira=self.display_name, quantos=len(sem_conta), nomes=nomes))
        return sem_conta

    def action_view_pos_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Register sales'),
            'res_model': 'pos.order',
            'view_mode': 'list,form',
            'domain': [('config_id', 'in', self.with_context(
                active_test=False).pos_config_ids.ids)],
        }

    # --- fechar ----------------------------------------------------------
    def action_return(self):
        """Pedir o retorno fecha os caixas, e nessa ordem.

        Antes de contar a mesa: sessão aberta ainda pode registrar venda, e
        venda lançada depois da contagem faria o retorno pedir livro que já
        saiu. Fechar é ato de caixa, com lançamento contábil -- e é por isso
        que ele acontece aqui, no clique de quem encerra a feira, e não
        escondido no meio do movimento de estoque.
        """
        self._fechar_caixas()
        return super().action_return()

    def _fechar_caixas(self):
        """Fecha as sessões abertas dos caixas desta feira.

        A contagem de dinheiro fica igual ao esperado, como no fechamento
        diário da mesa: quem tem divergência de caixa a lança no PDV, que é
        onde essa conversa acontece. Pedido em rascunho, sim, interrompe --
        é venda começada e não paga, e ninguém deve decidir isso por quem
        está no balcão.
        """
        for fair in self:
            todos = fair.with_context(active_test=False)
            sessoes = self.env['pos.session'].sudo().search([
                ('config_id', 'in', todos.pos_config_ids.ids),
                ('state', '!=', 'closed')])
            for sessao in sessoes:
                rascunhos = sessao.get_session_orders().filtered(
                    lambda o: o.state == 'draft')
                if rascunhos:
                    raise UserError(_(
                        "The register %(caixa)s of %(feira)s still has an "
                        "unpaid order. Finish or cancel it in the Point of "
                        "Sale, then ask for the return.",
                        caixa=sessao.config_id.name,
                        feira=fair.display_name))
                if sessao.config_id.cash_control:
                    sessao.cash_register_balance_end_real = \
                        sessao.cash_register_balance_end
                sessao.action_pos_session_closing_control()
                fair.message_post(body=_(
                    "%(feira)s — register %(caixa)s closed with the return.",
                    feira=fair.display_name, caixa=sessao.config_id.name))
        return True

    def write(self, vals):
        """O acesso da equipe segue o ESTADO do evento.

        Planejou, a equipe entra; voltou, a equipe sai. Amarrar no estado (e
        não no clique de um botão específico) cobre todos os caminhos --
        inclusive voltar ao rascunho, que também tira o acesso de gente que
        não vai mais trabalhar evento nenhum.
        """
        res = super().write(vals)
        if 'discount_pc' in vals:
            self._sincronizar_desconto()
        if 'state' in vals:
            self.with_context(active_test=False).cashier_ids \
                ._sincronizar_acesso()
        return res

    def unlink(self):
        """Soltar as amarras antes de apagar a feira.

        O caixa, a lista de preços e o tipo de operação apontam para a feira
        (e para a escala) de propósito, para o histórico não ir junto quando
        ela morre. Mas a chave estrangeira no banco nasceu sem `SET NULL` --
        e o resultado é apagar uma feira e levar um erro de banco que não diz
        nada a quem está na tela. Aqui as pontas são soltas antes.
        """
        todos = self.with_context(active_test=False)
        caixas = todos.pos_config_ids
        if caixas:
            caixas.sudo().write({'fair_id': False, 'fair_cashier_id': False})
        tipos = todos.pos_picking_type_ids
        if tipos:
            tipos.sudo().write({'fair_id': False})
        listas = self.env['product.pricelist'].sudo().search(
            [('fair_id', 'in', self.ids)])
        if listas:
            listas.write({'fair_id': False})
        return super().unlink()

    def _ao_retornar(self):
        """O que só faz sentido com a MERCADORIA de volta.

        Arquivar o caixa e deixar as contas da equipe prontas acontecia no
        clique de pedir o retorno -- quando a mesa ainda estava cheia e a
        conferência do armazém nem tinha começado. Agora acontece quando o
        evento fecha de verdade.
        """
        res = super()._ao_retornar()
        self._contas_da_equipe_no_fechamento()
        # O caixa da feira que acabou SAI DA LISTA de quem opera PDV todo
        # dia: ele é arquivado, não apagado -- a venda que passou por ele
        # continua existindo, e é ela que diz quanto a feira rendeu.
        for fair in self:
            todos = fair.with_context(active_test=False)
            caixas, tipos = todos.pos_config_ids.ids, \
                todos.pos_picking_type_ids.ids
            if not caixas:
                continue
            # Lê com `active_test=False`, ESCREVE sem ele. O contexto viaja
            # para dentro da gravação, e a trava do PDV -- que recusa
            # arquivar a operação enquanto um caixa a usa -- passa a enxergar
            # como ativo o caixa que acabou de ser arquivado.
            self.env['pos.config'].sudo().browse(caixas).write(
                {'active': False})
            self.env['stock.picking.type'].sudo().browse(tipos).write(
                {'active': False})
        return res
