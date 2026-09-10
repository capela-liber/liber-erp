# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    # A feira tem tipos de operação PRÓPRIOS, separados da entrega de venda e
    # da consignação. Nascem sozinhos no primeiro uso e ficam parametrizados
    # aqui -- mesmo desenho do liber_soc_moves.
    fair_shipment_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Fair Shipment Operation',
        domain="[('code', '=', 'internal')]",
        help="Warehouse -> fair. Numbered FEIRA/OUT/. It is not a delivery: "
             "the books stay ours while they sit on the table.")
    fair_return_dispatch_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Fair Return Dispatch Operation',
        domain="[('code', '=', 'internal')]",
        help="Fair table -> transit, when the boxes are packed at the fair. "
             "Numbered FEIRA/RET/. It is what the return note declares.")
    fair_return_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Fair Return Operation',
        domain="[('code', '=', 'internal')]",
        help="Transit -> warehouse, checked on arrival. Numbered FEIRA/IN/. "
             "This is the leg where the count happens.")
    fair_receipt_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Fair Receipt Operation',
        domain="[('code', '=', 'internal')]",
        help="Transit -> fair table, confirmed by whoever is at the fair. "
             "Numbered FEIRA/REC/. It is the leg that says the books "
             "actually arrived.")
    fair_sale_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Fair Sale Operation',
        domain="[('code', '=', 'outgoing')]",
        help="Fair -> customers, what the daily closing sold. Numbered "
             "FEIRA/VND/. It moves stock only; the invoice comes later.")
    fair_loss_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Fair Loss Operation',
        domain="[('code', '=', 'internal')]",
        help="Fair -> losses, for what did not come back and was not sold. "
             "Numbered FEIRA/PRD/.")

    # ------------------------------------------------------------------
    # o que a casa decide UMA VEZ, e todo evento herda
    # ------------------------------------------------------------------
    fair_analytic_plan_id = fields.Many2one(
        'account.analytic.plan', string='Event analytic plan',
        help="Where the analytic account of each event is created. Without "
             "it the event has no place to gather what it cost and what it "
             "gave.")
    fair_service_product_id = fields.Many2one(
        'product.product', string='Event staff service',
        domain=[('type', '=', 'service')],
        help="The service line used on the bill that pays the event team: "
             "daily rates and commission.")
    fair_manager_id = fields.Many2one(
        'res.users', string='Events responsible',
        help="Who answers for the fairs team. Every new event starts with "
             "this person, and each event may change it.")

    def _fair_warehouse(self):
        self.ensure_one()
        return self.env['stock.warehouse'].search(
            [('company_id', '=', self.id)], limit=1)

    def _fair_series_start(self, prefix):
        """Primeiro número que a série nova pode puxar sem colidir.

        Herdado do liber_soc_moves: um `ir.sequence` recém-criado começando em
        1 gera um nome que já existe se alguém nomeou picking à mão, e morre na
        constraint name_uniq -- e o rollback desfaz também o tipo e a sequência
        criados aqui, então o clique seguinte repete tudo do zero. O erro é
        permanente, não transitório. Documento já emitido nunca muda de nome:
        começar adiante do maior é o comportamento correto de qualquer jeito.
        """
        self.ensure_one()
        static = prefix.split('%')[0]
        self.env['stock.picking'].flush_model(['name', 'company_id'])
        self.env.cr.execute(
            r"""SELECT COALESCE(MAX(substring(name FROM '(\d+)$')::int), 0)
                  FROM stock_picking
                 WHERE company_id = %s AND name LIKE %s""",
            (self.id, static + '%'))
        return self.env.cr.fetchone()[0] + 1

    def _create_fair_operation_type(self, name, prefix, seq_name, code='internal'):
        self.ensure_one()
        warehouse = self._fair_warehouse()
        seq = self.env['ir.sequence'].sudo().create({
            'name': seq_name,
            'prefix': prefix,
            'padding': 5,
            'company_id': self.id,
            'number_next': self._fair_series_start(prefix),
        })
        return self.env['stock.picking.type'].sudo().create({
            'name': name,
            'code': code,
            'sequence_id': seq.id,
            'sequence_code': prefix.replace('/%(year)s/', ''),
            'warehouse_id': warehouse.id if warehouse else False,
            'company_id': self.id,
        })

    # sudo DELIBERADO na gravação de volta no res.company: escrever em
    # res.company pede base.group_erp_manager, e quem abre uma feira é do
    # Comercial. Sem isto, o PRIMEIRO comercial a despachar numa empresa
    # recém-configurada leva um AccessError, e a partir da segunda vez (campo
    # já preenchido) ninguém vê nada. Não há escalada: o valor gravado é um
    # registro que o próprio método acabou de criar, e o usuário não o escolhe.
    def _get_fair_shipment_operation_type(self):
        """A remessa que SAI: esta é trabalho de armazém, e tem de aparecer.

        A carga que sai e a que volta são os dois movimentos que a logística
        pega na Visão geral do Inventário. Se o tipo estiver arquivado (uma
        faxina larga demais já arquivou), ele VOLTA aqui -- despachar sem
        cartão na bancada é despachar para ninguém, e foi o que aconteceu.
        """
        self.ensure_one()
        if not self.fair_shipment_operation_type_id:
            self.sudo().fair_shipment_operation_type_id = \
                self._create_fair_operation_type(
                    _('Fair Shipment'), 'FEIRA/OUT/%(year)s/',
                    'Fair Shipment Operation')
        tipo = self.sudo().fair_shipment_operation_type_id
        if not tipo.active:
            tipo.write({'active': True})
        return self.fair_shipment_operation_type_id

    def _get_fair_receipt_operation_type(self):
        """A chegada na feira também NASCE ARQUIVADA.

        Ela não é trabalho de armazém: quem confere está na praça, e confere
        pela tela de Recebimentos do próprio módulo. Um cartão "Recebimento na
        feira" na Visão geral do Inventário é trabalho oferecido a quem não
        vai fazê-lo -- e o depósito abriria para descobrir que a carga está a
        seiscentos quilômetros.

        Arquivar o TIPO não impede o movimento; tira só o cartão. O que a
        logística trabalha continua sendo dois: FEIRA/OUT, a carga que sai, e
        FEIRA/IN, a que volta para o armazém -- essa sim é dela.
        """
        self.ensure_one()
        if not self.fair_receipt_operation_type_id:
            tipo = self._create_fair_operation_type(
                _('Fair Receipt'), 'FEIRA/REC/%(year)s/',
                'Fair Receipt Operation')
            tipo.sudo().active = False
            self.sudo().fair_receipt_operation_type_id = tipo
        return self.fair_receipt_operation_type_id

    def _fair_transit_location(self):
        """O lugar onde a carga fica ENTRE o armazém e a mesa.

        Não é invenção deste módulo: toda empresa já tem a sua, criada pelo
        núcleo para transferências entre armazéns. É exatamente o mesmo
        problema -- mercadoria que saiu de um lugar e ainda não chegou no
        outro -- e reusar a do núcleo evita mais uma localização na árvore
        de quem trabalha no Inventário.
        """
        self.ensure_one()
        transito = self.env['stock.location'].search([
            ('usage', '=', 'transit'),
            ('company_id', '=', self.id),
        ], limit=1)
        if not transito:
            transito = self.env['stock.location'].search([
                ('usage', '=', 'transit'), ('company_id', '=', False),
            ], limit=1)
        if not transito:
            raise UserError(_(
                "Company %s has no transit location to move the fair load "
                "through.", self.display_name))
        return transito

    def _get_fair_return_dispatch_operation_type(self):
        """O despacho da volta também: quem embala está na praça."""
        self.ensure_one()
        if not self.fair_return_dispatch_operation_type_id:
            tipo = self._create_fair_operation_type(
                _('Fair Return Dispatch'), 'FEIRA/RET/%(year)s/',
                'Fair Return Dispatch Operation')
            tipo.sudo().active = False
            self.sudo().fair_return_dispatch_operation_type_id = tipo
        return self.fair_return_dispatch_operation_type_id

    def _fair_scrap_location(self):
        """O lugar onde a perda é baixada.

        No 19 não há mais campo `scrap_location` na localização: a de descarte
        é a de uso `inventory` chamada Scrap, uma por empresa. Procurar pelo
        campo antigo devolvia erro de coluna inexistente -- e o código de
        perdas nunca havia sido exercitado até agora.
        """
        self.ensure_one()
        Local = self.env['stock.location']
        descarte = Local.search([
            ('usage', '=', 'inventory'),
            ('company_id', '=', self.id),
            ('name', 'ilike', 'scrap'),
        ], limit=1)
        if not descarte:
            descarte = Local.search([
                ('usage', '=', 'inventory'),
                ('company_id', 'in', [self.id, False]),
            ], limit=1)
        if not descarte:
            raise UserError(_(
                "Company %s has no scrap location to book the loss to.",
                self.display_name))
        return descarte

    def _get_fair_return_operation_type(self):
        """A carga que VOLTA para o armazém: o outro trabalho da logística."""
        self.ensure_one()
        if not self.fair_return_operation_type_id:
            self.sudo().fair_return_operation_type_id = \
                self._create_fair_operation_type(
                    _('Fair Return'), 'FEIRA/IN/%(year)s/',
                    'Fair Return Operation')
        tipo = self.sudo().fair_return_operation_type_id
        if not tipo.active:
            tipo.write({'active': True})
        return self.fair_return_operation_type_id

    # Venda e perda NASCEM ARQUIVADAS, de propósito.
    #
    # A Visão geral do Inventário é a bancada da logística: cada cartão ali é
    # trabalho que alguém pega. "Venda em feira" não é trabalho de ninguém --
    # é a contrapartida contábil do fechamento diário, gerada e concluída pelo
    # sistema no mesmo clique, sem que nenhuma caixa se mova. Um cartão desses
    # entre os que se trabalha só faz a pessoa abrir para descobrir que não há
    # nada a fazer. Mesma decisão que o liber_soc_moves tomou com o COM/MOV.
    #
    # Arquivado o TIPO, os movimentos continuam nascendo e concluindo por ele:
    # o que o arquivamento tira é o cartão da Visão geral, não a operação.
    # O que a logística de feira trabalha de verdade são dois: FEIRA/OUT, a
    # carga que sai, e FEIRA/IN, a que volta.
    def _get_fair_sale_operation_type(self):
        self.ensure_one()
        if not self.fair_sale_operation_type_id:
            tipo = self._create_fair_operation_type(
                _('Fair Sale'), 'FEIRA/VND/%(year)s/',
                'Fair Sale Operation', code='outgoing')
            tipo.sudo().active = False
            self.sudo().fair_sale_operation_type_id = tipo
        return self.fair_sale_operation_type_id

    def _get_fair_loss_operation_type(self):
        self.ensure_one()
        if not self.fair_loss_operation_type_id:
            tipo = self._create_fair_operation_type(
                _('Fair Loss'), 'FEIRA/PRD/%(year)s/',
                'Fair Loss Operation')
            tipo.sudo().active = False
            self.sudo().fair_loss_operation_type_id = tipo
        return self.fair_loss_operation_type_id
