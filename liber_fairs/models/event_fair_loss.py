# -*- coding: utf-8 -*-
"""A perda da feira: o exemplar que saiu e não voltou nem virou venda.

A diferença entre o que a mesa deveria ter e o que voltou na caixa não é
detalhe de estoque: é dinheiro, e é a informação que decide o que se manda na
próxima vez. Título caro com extravio alto sai da grade.

Cada linha guarda o MOTIVO, e o motivo escolhe três coisas ao mesmo tempo:
para onde o exemplar vai no estoque, em que conta a baixa vai cair quando a
parte contábil existir, e como a perda aparece no retorno do canal. Por isso o
motivo é obrigatório: perda sem motivo é só um número que não fecha.
"""
from odoo import _, api, fields, models

MOTIVOS = [
    # O primeiro não é um motivo, é um ESTADO: sabe-se que faltou e não se
    # sabe por quê. Nasce assim na conferência da chegada, no meio da feira,
    # e é em Perdas -- com tempo -- que alguém o troca por um motivo de
    # verdade. Campo vazio seria um buraco; isto é uma pergunta em aberto.
    ('not_received', 'Not received (to explain)'),
    # O gêmeo do anterior, do outro lado da viagem: a feira mandou de volta e
    # o armazém não achou na caixa. Também é estado, não motivo -- e é o que
    # a conferência do RETORNO escreve.
    ('not_returned', 'Did not come back (to explain)'),
    ('sold', 'Sold and not recorded'),
    ('damaged', 'Damaged beyond sale'),
    ('missing', 'Missing'),
    ('courtesy', 'Given away at the fair'),
]

# Para onde o exemplar vai. Venda não lançada e cortesia SAEM para clientes:
# o livro foi para a mão de alguém, e não é descarte. Avaria e extravio são
# baixa de estoque.
# `not_received` e `not_returned` NÃO têm destino de estoque, e é por isso
# que não estão aqui: num, o exemplar nunca chegou na mesa; no outro, nunca
# voltou dela. Os dois estão parados no trânsito, e mexer neles antes de
# saber o que houve seria inventar um movimento.
DESTINO = {
    'sold': 'sale',
    'courtesy': 'sale',
    'damaged': 'loss',
    'missing': 'loss',
}


class EventFairLoss(models.Model):
    _name = 'event.fair.loss'
    _description = 'Fair Loss'
    _order = 'fair_id, id'

    fair_id = fields.Many2one(
        'event.fair', string='Fair', required=True, ondelete='cascade',
        index=True)
    company_id = fields.Many2one(related='fair_id.company_id', store=True)
    product_id = fields.Many2one(
        'product.product', string='Title', required=True)
    qty = fields.Float(
        string='Copies', digits='Product Unit', required=True)
    reason = fields.Selection(
        MOTIVOS, string='Reason', required=True, default='not_received',
        help="Starts as \"Not received\" on the way out and \"Did not come "
             "back\" on the way home: the count knows a copy is missing, not "
             "why. Change it here, with time to think.")
    to_explain = fields.Boolean(
        string='To explain', compute='_compute_to_explain', store=True,
        help="Still waiting for somebody to say what happened.")
    stage = fields.Selection(
        [('fair', 'At the fair'), ('transit', 'On the way back')],
        string='Where', default='fair', required=True,
        help="At the fair: the table had fewer copies than it should. On the "
             "way back: the fair sent more than the warehouse received.")
    date = fields.Date(
        string='Date', default=fields.Date.context_today, required=True)
    unit_cost = fields.Float(
        string='Unit cost', digits='Product Price', readonly=True,
        help="The product's cost when the loss was recorded. Frozen here on "
             "purpose: the cost changes, and what this fair lost does not.")
    value = fields.Float(
        string='Value', digits='Product Price', compute='_compute_value',
        store=True)
    picking_id = fields.Many2one(
        'stock.picking', string='Transfer', readonly=True,
        help="The stock move that took these copies off the table.")
    # A perna que faltava. A falta acusada na conferência deixa o exemplar
    # PARADO NO TRÂNSITO: ninguém o tirou de lá, porque ninguém sabia ainda o
    # que havia acontecido. Quando o motivo é escolhido, é esta transferência
    # que finalmente o tira -- para descarte ou para o cliente, conforme o
    # motivo. Sem ela, o exemplar ficava no trânsito para sempre e o estoque
    # da casa carregava um livro que não existe.
    write_off_picking_id = fields.Many2one(
        'stock.picking', string='Write-off', readonly=True, copy=False,
        help="The transfer that took these copies out of transit, once "
             "somebody said what happened to them.")
    # QUEM PAGA por esta perda. A equipe responde pelo que sumiu SOB A GUARDA
    # dela -- o que estava na mesa. O exemplar que saiu do depósito e nunca
    # chegou na praça, ou que saiu da praça e não chegou no armazém, sumiu na
    # estrada: não é da conta de quem estava no balcão.
    #
    # É calculado, mas editável: existe o caso em que o gerente sabe de algo
    # que o sistema não sabe, e a decisão é dele.
    charged_to_team = fields.Boolean(
        string='Team pays', compute='_compute_charged_to_team', store=True,
        readonly=False,
        help="Whether this loss enters the split that the event team pays. "
             "By default, only what vanished from the table: copies that "
             "never arrived are not theirs.")
    note = fields.Char(string='Note')

    @api.depends('reason')
    def _compute_to_explain(self):
        for perda in self:
            perda.to_explain = perda.reason in ('not_received',
                                                'not_returned')

    @api.depends('picking_id', 'picking_id.fair_operation')
    def _compute_charged_to_team(self):
        """A guarda decide, e não o motivo.

        Perda que nasceu de uma CHEGADA (na praça ou no armazém) é exemplar
        que não chegou: ele sumiu entre um lugar e outro, e quem estava no
        balcão não tinha como cuidar dele. Todo o resto -- o que a mesa
        deveria ter e não entrou na caixa, a avaria da chuva, o extravio no
        meio do movimento -- aconteceu sob a guarda da equipe.
        """
        for perda in self:
            origem = perda.picking_id
            perda.charged_to_team = not (
                origem and origem.fair_operation in ('receipt', 'return'))

    @api.depends('qty', 'unit_cost')
    def _compute_value(self):
        for perda in self:
            perda.value = perda.qty * perda.unit_cost

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('unit_cost') and vals.get('product_id'):
                produto = self.env['product.product'].browse(
                    vals['product_id'])
                vals['unit_cost'] = produto.standard_price
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        # Só na TROCA de motivo: é o momento em que a pergunta em aberto vira
        # resposta, e a resposta manda o exemplar para algum lugar.
        if 'reason' in vals:
            self._baixar_do_transito()
        return res

    def _baixar_do_transito(self):
        """Tira o exemplar de ONDE ELE ESTÁ, quando a falta é explicada.

        Só age sobre perda que NASCEU de um movimento (tem transferência de
        origem): é ela que deixou exemplar parado em algum lugar. Perda
        lançada à mão -- a avaria da chuva no sábado, por exemplo -- é o
        gerente dizendo o que já sabe, e não sobrou exemplar nenhum para
        mover.

        Onde ele está depende da perna:

          - falta na CHEGADA (na praça ou no armazém): ficou no trânsito;
          - falta no DESPACHO DE VOLTA: ficou na mesa, porque a contagem
            dizia que estava lá e ninguém pôs na caixa.

        Move no máximo o que ESTIVER lá. Se não houver nada, avisa no
        histórico e não levanta erro: a contabilidade da feira não pode
        travar o depósito, e uma explicação dada com atraso não deve impedir
        ninguém de registrar o que sabe.
        """
        for perda in self:
            if perda.write_off_picking_id or perda.reason not in DESTINO:
                continue
            origem = perda.picking_id
            if not (origem and (origem.fair_is_arrival
                                or origem.fair_operation == 'return_dispatch')):
                continue
            company = perda.fair_id.company_id
            if origem.fair_operation == 'return_dispatch':
                lugar = perda.fair_id.stock_location_id
            else:
                # O corredor DESTA feira: o exemplar que faltou na chegada
                # está parado no trânsito dela, e não no genérico da empresa.
                lugar = perda.fair_id._get_transit_location()
            if not lugar:
                continue
            disponivel = perda.product_id.with_context(
                location=lugar.id, company_id=company.id).qty_available
            qty = min(perda.qty, disponivel)
            if qty <= 0:
                perda.fair_id.message_post(body=_(
                    "%(feira)s — %(titulo)s: nothing of this loss was still "
                    "there, so no stock was moved. The reason was recorded "
                    "anyway.",
                    feira=perda.fair_id.display_name,
                    titulo=perda.product_id.display_name))
                continue
            picking = perda.fair_id._create_fair_picking(
                DESTINO[perda.reason], {perda.product_id: qty},
                source=lugar)
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.with_context(
                skip_backorder=True,
                picking_ids_not_to_backorder=picking.ids).button_validate()
            perda.write_off_picking_id = picking
            perda.fair_id.message_post(body=_(
                "%(feira)s — %(qtd)s of %(titulo)s written off as "
                "%(motivo)s, from %(lugar)s, on %(mov)s.",
                lugar=lugar.display_name,
                feira=perda.fair_id.display_name, qtd=int(qty),
                titulo=perda.product_id.display_name,
                motivo=dict(perda._fields['reason']._description_selection(
                    perda.env))[perda.reason],
                mov=picking.name))
        return True
