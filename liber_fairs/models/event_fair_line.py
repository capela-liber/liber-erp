# -*- coding: utf-8 -*-
"""A grade da feira, título a título, e o que aconteceu com cada um.

As quantidades NÃO são digitadas: saem dos movimentos já feitos. Enviado é a
soma das remessas concluídas, vendido é a soma do que o fechamento diário
mandou para Clientes, e o que está na mesa é a diferença. Digitado, só o
planejado -- que é a intenção, não o fato.
"""
from odoo import _, api, fields, models


class EventFairLine(models.Model):
    _name = 'event.fair.line'
    _description = 'Fair Grid Line'
    _order = 'fair_id, id'

    fair_id = fields.Many2one(
        'event.fair', string='Fair', required=True, ondelete='cascade',
        index=True)
    company_id = fields.Many2one(
        related='fair_id.company_id', store=True)
    product_id = fields.Many2one(
        'product.product', string='Title', required=True,
        domain="[('type', '=', 'consu')]")
    qty_planned = fields.Float(
        string='Planned', digits='Product Unit', default=1.0,
        help="How many copies the grid calls for. Raise it during the event "
             "to trigger a replenishment.")
    # A decisão do gerente, tomada uma vez e levada para a mesa: é dela que
    # sai a sugestão de reposição em cada fechamento diário.
    qty_min = fields.Float(
        string='Minimum', digits='Product Unit',
        help="How few copies may be left on the table before this title has "
             "to be replenished. The daily count uses it to suggest the "
             "replenishment. Zero means no minimum.")
    qty_sent = fields.Float(
        string='Sent', digits='Product Unit', compute='_compute_moved',
        store=True)
    qty_returned = fields.Float(
        string='Returned', digits='Product Unit', compute='_compute_moved',
        store=True)
    qty_sold = fields.Float(
        string='Sold', digits='Product Unit', compute='_compute_moved',
        store=True)
    qty_lost = fields.Float(
        string='Lost', digits='Product Unit', compute='_compute_moved',
        store=True)
    # Pedido e ainda não chegado. Sem isto, a contagem do dia seguinte
    # sugeriria repor de novo o que já está na estrada, e a feira receberia
    # em dobro -- justamente o título que estava faltando.
    qty_in_transit = fields.Float(
        string='On the way', digits='Product Unit', compute='_compute_moved',
        store=True,
        help="Left the warehouse and has not been received at the fair yet.")
    # Tudo o que já foi pedido e ainda não chegou: no armazém à espera de
    # separação MAIS o que está na estrada. É por este número que o Despachar
    # sabe que não tem nada a mandar.
    qty_requested = fields.Float(
        string='Requested', digits='Product Unit', compute='_compute_moved',
        store=True,
        help="Asked for and not on the table yet, whether still in the "
             "warehouse or already on the road.")
    qty_on_shelf = fields.Float(
        string='On the table', digits='Product Unit', compute='_compute_moved',
        store=True,
        help="Sent minus returned, sold and lost: what should be on the "
             "table right now.")
    # O estoque que interessa para escolher é o do ARMAZÉM, e só ele.
    # O `qty_available` do núcleo soma todas as localizações internas da
    # empresa, e a localização de uma feira É interna (o livro na mesa
    # continua sendo nosso). Usá-lo aqui mostraria 60 exemplares de um título
    # que tem 38 no armazém e 22 numa mesa em Paraty -- e a pessoa montaria a
    # grade contando com livro que já está a seiscentos quilômetros.
    qty_warehouse = fields.Float(
        string='In stock', digits='Product Unit', compute='_compute_stock',
        help="On hand in the warehouse. Does not count copies already at a "
             "fair: those are ours, but they are not here.")
    qty_free = fields.Float(
        string='Free', digits='Product Unit', compute='_compute_stock',
        help="On hand in the warehouse minus what is already reserved for "
             "other orders. This is what you can actually send.")
    is_short = fields.Boolean(
        string='Short', compute='_compute_stock',
        help="What still has to be shipped is more than the warehouse has "
             "free.")

    _fair_product_uniq = models.Constraint(
        'unique(fair_id, product_id)',
        'A title can only appear once in a fair grid.')

    # NÃO existe mais trava de "mínimo maior que o planejado", e a remoção é
    # deliberada. Eu li o mínimo como patamar dentro da grade; na casa ele é
    # OUTRA COISA -- é o que a mesa precisa ter. Pedir quinze de um título do
    # qual só há dez é dizer que faltam cinco, e é assim que a equipe
    # descobre o que precisa de reimpressão. Barrar isso apagava justamente a
    # informação que interessa: o fechamento diário sugere a reposição, e o
    # que não existe no armazém aparece como falta, não como erro de
    # digitação.

    @api.depends('product_id', 'qty_planned', 'qty_sent', 'fair_id.company_id')
    def _compute_stock(self):
        """Saldo do armazém, por empresa, numa leitura só por grupo."""
        por_empresa = {}
        for line in self:
            por_empresa.setdefault(line.fair_id.company_id, self.browse())
            por_empresa[line.fair_id.company_id] |= line
        for company, lines in por_empresa.items():
            warehouse = company._fair_warehouse() if company else None
            if not warehouse:
                lines.update({'qty_warehouse': 0.0, 'qty_free': 0.0,
                              'is_short': False})
                continue
            produtos = lines.mapped('product_id').with_context(
                location=warehouse.lot_stock_id.id,
                company_id=company.id)
            saldo = {p.id: (p.qty_available, p.free_qty) for p in produtos}
            for line in lines:
                em_maos, livre = saldo.get(line.product_id.id, (0.0, 0.0))
                line.qty_warehouse = em_maos
                line.qty_free = livre
                line.is_short = (line.qty_planned - line.qty_sent) > livre

    @api.depends('fair_id.picking_ids.state',
                 'fair_id.picking_ids.fair_operation',
                 'fair_id.picking_ids.move_ids.quantity',
                 'fair_id.picking_ids.move_ids.product_uom_qty',
                 'fair_id.picking_ids.move_ids.product_id',
                 'fair_id.picking_ids.move_ids.location_dest_id',
                 'fair_id.picking_ids.move_ids.location_id')
    def _compute_moved(self):
        for line in self:
            done = line.fair_id.picking_ids.filtered(
                lambda p: p.state == 'done')
            totals = {'receipt': 0.0, 'return': 0.0, 'return_dispatch': 0.0,
                      'sale': 0.0, 'loss': 0.0}
            mesa = line.fair_id.stock_location_id
            # A MESA SE CONTA POR LOCALIZAÇÃO, não por nome de operação.
            #
            # O que está na mesa é o que ENTROU nela menos o que SAIU dela, e
            # isso vale em qualquer desenho. Contando por nome de operação, a
            # conta quebra sempre que o desenho muda: as feiras do começo do
            # protótipo mandavam a carga direto para a mesa, sem trânsito nem
            # conferência, e por isso apareciam com "enviado 0" e mesa
            # NEGATIVA -- vendiam livro que o sistema dizia nunca ter
            # chegado. Por localização, elas voltam a fechar.
            chegou_na_mesa = saiu_da_mesa = 0.0
            for picking in done:
                # Varre TODO movimento concluído da feira. Filtrar por nome
                # de operação antes de olhar a localização foi o que produziu
                # mesa negativa nas feiras de uma perna só: a remessa delas
                # se chama `shipment`, ia direto para a mesa, e era descartada
                # aqui -- a feira ficava com chegada zero e venda três.
                operacao = picking.fair_operation
                for move in picking.move_ids:
                    if move.product_id != line.product_id \
                            or move.state != 'done':
                        continue
                    if mesa and move.location_dest_id == mesa:
                        chegou_na_mesa += move.quantity
                    elif mesa and move.location_id == mesa:
                        saiu_da_mesa += move.quantity
                    if operacao not in totals:
                        continue
                    # Venda que ENTRA na mesa é devolução de balcão: o
                    # cliente desistiu e o exemplar voltou para a pilha.
                    # Contá-la como venda diria que a feira vendeu duas vezes
                    # e faria a mesa sumir com livro que está ali na frente.
                    sinal = -1.0 if (operacao == 'sale' and mesa
                                     and move.location_dest_id == mesa) else 1.0
                    totals[operacao] += sinal * move.quantity
            # ENVIADO = o que CHEGOU na mesa, e não o que o depósito soltou.
            # A ida tem duas pernas, e quem garante a chegada é quem está na
            # praça, conferindo a FEIRA/REC. Lido pela localização de destino,
            # o número também está certo nas feiras de uma perna só.
            totals['shipment'] = chegou_na_mesa
            # A CAMINHO = a segunda perna ainda não conferida. O Odoo põe a
            # entrada em "aguardando" enquanto a saída não sai, e em "pronto"
            # quando a carga já está no trânsito: é essa diferença que separa
            # "ainda no armazém" de "na estrada".
            a_caminho = pedido = 0.0
            for picking in line.fair_id.picking_ids.filtered(
                    lambda p: p.fair_operation == 'receipt'
                    and p.state not in ('done', 'cancel')):
                for move in picking.move_ids:
                    if move.product_id != line.product_id:
                        continue
                    pedido += move.product_uom_qty
                    if picking.state != 'waiting':
                        a_caminho += move.product_uom_qty
            line.qty_in_transit = a_caminho
            line.qty_requested = pedido
            line.qty_sent = totals['shipment']
            line.qty_returned = totals['return']
            line.qty_sold = totals['sale']
            line.qty_lost = totals['loss']
            # Entrou menos saiu. O que ficou no TRÂNSITO não aparece aqui, e
            # é o ponto: descontando pela chegada no armazém, uma feira que
            # voltou curta fechava dizendo "na mesa 2" de uma mesa que já
            # não existe -- e aqueles 2 nunca saíam dali. Eles são perda, e
            # vivem em Perdas até alguém dizer o que houve.
            line.qty_on_shelf = chegou_na_mesa - saiu_da_mesa
