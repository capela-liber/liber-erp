# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    fair_id = fields.Many2one(
        'event.fair', string='Fair', index=True, ondelete='set null',
        copy=False,
        help="The event this transfer belongs to.")
    # O papel do movimento não se deduz das localizações: uma feira pode
    # repor, e a segunda remessa tem o mesmo par origem/destino da primeira.
    # Guardar o papel explicitamente é o que deixa "enviado", "vendido" e
    # "voltou" somarem certo depois.
    fair_operation = fields.Selection(
        [('shipment', 'Fair shipment'),
         ('receipt', 'Fair receipt'),
         ('return_dispatch', 'Fair return dispatch'),
         ('return', 'Fair return'),
         ('sale', 'Fair sale'),
         ('loss', 'Fair loss')],
        string='Fair Operation', copy=False, readonly=True)
    # De qual fechamento diário veio o pedido. Quem separa no armazém precisa
    # saber que esta caixa é a reposição da contagem de sábado, e não uma
    # remessa solta: é o que permite perguntar a coisa certa a quem pediu.
    fair_day_id = fields.Many2one(
        'event.fair.day', string='Fair Day', readonly=True, copy=False,
        index='btree_not_null',
        help="The daily closing that asked for this replenishment.")
    # Gravado de propósito: filtro e agrupamento só funcionam em campo que
    # está no banco, e a lista de transferências é a tela da logística.
    is_fair_replenishment = fields.Boolean(
        string='Fair Replenishment', compute='_compute_is_fair_replenishment',
        store=True,
        help="The fair is already running and ran out of this title. It is "
             "not the first load: it is the one that is being waited for.")

    @api.depends('fair_day_id')
    def _compute_is_fair_replenishment(self):
        for picking in self:
            picking.is_fair_replenishment = bool(picking.fair_day_id)

    # ------------------------------------------------------------------
    # a conferência: duas colunas e um ok
    # ------------------------------------------------------------------
    # Recebido é o que quem mandou DIZ que mandou. Conferido é o que quem
    # recebeu CONTOU. Enquanto os dois são iguais, conferir é um clique --
    # e é o que acontece em quase toda carga. A diferença é a exceção, e é
    # só ela que pede explicação.
    # As três GRAVADAS: a lista soma as colunas e filtra por elas, e nem
    # soma nem filtro funcionam em campo que não está no banco. Sem isto, o
    # cabeçalho do grupo aparecia em branco justamente nas duas colunas que
    # dão nome à tela.
    fair_qty_received = fields.Float(
        string='Received', digits='Product Unit',
        compute='_compute_fair_conferencia', store=True,
        help="What whoever sent it says was sent.")
    fair_qty_checked = fields.Float(
        string='Checked', digits='Product Unit',
        compute='_compute_fair_conferencia', store=True,
        help="What whoever received it counted.")
    # Gravado porque a lista FILTRA por ele: "chegou curto" é a pergunta que
    # se faz nesta tela, e filtro só funciona em campo que está no banco.
    fair_shortfall = fields.Float(
        string='Missing', digits='Product Unit',
        compute='_compute_fair_conferencia', store=True,
        help="Received minus checked: what did not arrive.")
    fair_is_arrival = fields.Boolean(
        string='Fair Arrival', compute='_compute_fair_conferencia',
        store=True,
        help="A leg that ARRIVES somewhere: at the fair table, or back at "
             "the warehouse. These are the ones somebody has to check.")
    # A CARGA SAIU? É a única pergunta que decide se uma chegada pode ser
    # conferida, e ela não se responde pelo estado do movimento: no clique da
    # tela o Odoo reserva sozinho, e a segunda chegada de uma feira aparecia
    # "Pronto" comendo o estoque que era da primeira. Aqui se lê a corrente:
    # a perna que alimenta esta chegada já foi concluída?
    fair_on_the_road = fields.Boolean(
        string='On the road', compute='_compute_fair_on_the_road', store=True,
        help="The leg that feeds this arrival is already done, so there is "
             "really something on the way to be checked.")

    fair_checked_by_id = fields.Many2one(
        'res.users', string='Checked by', readonly=True, copy=False)
    fair_checked_on = fields.Datetime(
        string='Checked on', readonly=True, copy=False)

    @api.depends('fair_operation', 'move_ids.product_uom_qty',
                 'move_ids.quantity', 'state')
    def _compute_fair_conferencia(self):
        for picking in self:
            chegada = picking.fair_operation in ('receipt', 'return')
            picking.fair_is_arrival = chegada
            if not chegada:
                picking.fair_qty_received = 0.0
                picking.fair_qty_checked = 0.0
                picking.fair_shortfall = 0.0
                continue
            recebido = sum(picking.move_ids.mapped('product_uom_qty'))
            conferido = sum(picking.move_ids.mapped('quantity'))
            picking.fair_qty_received = recebido
            picking.fair_qty_checked = conferido
            picking.fair_shortfall = max(0.0, recebido - conferido)

    def action_fair_check(self):
        """O ok geral: confere a carga inteira e assina quem contou.

        É o caminho de quase toda carga -- chegou o que disseram que ia
        chegar. Selecionar as linhas e apertar aqui vale por abrir uma a uma,
        digitar a mesma quantidade que já está escrita e validar.

        Quem conta e quando fica no histórico dos dois lados: no movimento,
        para quem trabalha no Inventário, e na feira, onde a equipe do evento
        conversa. Conferência sem assinatura é conferência que ninguém fez.
        """
        # A PORTEIRA É A PERMISSÃO DA FEIRA, não a do armazém.
        #
        # Quem confere está na praça, e não vai ter o papel de Inventário --
        # nem deveria: conferir a caixa da feira não é operar o depósito. O
        # direito de conferir é o de feira; a escrita no estoque vai em sudo,
        # que é o mesmo desenho do liber_nfe_picking ("a porteira é o
        # picking: quem pode abrir a transferência recebe a DANFE").
        #
        # Não há escalada: o que se grava é a quantidade que o próprio
        # documento já declarava, e quem conferiu fica registrado no campo e
        # no histórico. A assinatura é o que substitui o direito.
        # `env.su` passa: cron, script e teste chamam como sistema, e barrar
        # o sistema seria barrar a própria automação.
        # Quem trabalha as feiras na casa, OU quem está escalado no evento.
        # A operadora pode ficar sozinha na praça, e caixa de livro chega no
        # meio do movimento: esperar alguém com o papel da casa para dizer
        # "chegou" é deixar a mercadoria na calçada. O que ela pode conferir
        # já está limitado pela regra de registro -- a carga do evento dela.
        papeis = ('liber_fairs.group_fair_user',
                  'liber_fairs_pos.group_fair_cashier')
        if not self.env.su and not any(
                self.env.user.has_group(p) for p in papeis
                if self.env.ref(p, raise_if_not_found=False)):
            raise UserError(_(
                "Checking a fair load is for whoever works the fairs, or for "
                "the team scheduled on the event."))
        for picking in self:
            if not picking.fair_is_arrival:
                raise UserError(_(
                    "%s is not a fair arrival: there is nothing to check "
                    "here.", picking.name))
            if picking.state in ('done', 'cancel'):
                continue
            conferente = self.env.user
            movimento = picking.sudo()
            movimento.action_assign()
            for move in movimento.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            movimento.button_validate()
            movimento.write({
                'fair_checked_by_id': conferente.id,
                'fair_checked_on': fields.Datetime.now(),
            })
            # sudo com o uid do conferente: o recado sai ASSINADO por quem
        # contou, mas sem exigir dela direito de escrita no picking -- a
        # regra do mail.message pede escrita no documento, e quem está na
        # praça só tem leitura.
        movimento.with_user(conferente).sudo()._avisar_a_conferencia()
        return True


    @api.depends('fair_id', 'fair_is_arrival', 'move_ids.move_orig_ids.state')
    def _compute_fair_on_the_road(self):
        for picking in self:
            if not (picking.fair_id and picking.fair_is_arrival):
                picking.fair_on_the_road = False
                continue
            pendentes = picking.move_ids.move_orig_ids.filtered(
                lambda m: m.state not in ('done', 'cancel'))
            picking.fair_on_the_road = not pendentes

    # ------------------------------------------------------------------
    # em feira nada fica pendurado
    # ------------------------------------------------------------------
    def button_validate(self):
        """Movimento de feira NUNCA gera pedido em espera.

        "Não vamos precisar de backorder nunca... chegou ou não chegou." O
        diálogo do núcleo pergunta se o resto vem depois, e numa feira não
        vem: a caixa que chegou é a que chegou, e precisando de mais livro o
        caminho é a grade e o Despachar, que é visível e some do trânsito.

        Deixar o pedido em espera nascer criaria uma segunda transferência
        que ninguém vai trabalhar, pendurada para sempre na Visão geral.
        """
        self._exigir_a_partida_antes_da_chegada()
        feira = self.filtered('fair_id')
        registro = self
        if feira:
            registro = self.with_context(
                skip_backorder=True,
                picking_ids_not_to_backorder=feira.ids)
        return super(StockPicking, registro).button_validate()

    def _exigir_a_partida_antes_da_chegada(self):
        """Chegada não se confere antes da partida.

        A viagem da feira tem duas pernas encadeadas, e a segunda só pode ser
        conferida depois que a primeira saiu. Sem esta trava acontece o pior
        caso possível, e aconteceu: o trânsito guardava livro de OUTRA
        operação, o Odoo marcou a chegada como pronta com o que achou, e
        validar fechou o movimento com 8 de 107 -- porque feira não cria
        pedido em espera. Os 99 que faltaram viraram perda "Não voltou", num
        retorno em que ninguém tinha perdido nada.

        A regra de não criar pedido em espera continua certa; o que faltava
        era impedir que ela fosse aplicada a uma carga que ainda nem saiu.
        """
        for picking in self.filtered(
                lambda p: p.fair_id and p.fair_is_arrival
                and p.state not in ('done', 'cancel')):
            partidas = picking.move_ids.move_orig_ids.filtered(
                lambda m: m.state not in ('done', 'cancel'))
            if partidas:
                raise UserError(_(
                    "%(chegada)s cannot be confirmed yet: the load has not "
                    "left. Validate %(partida)s first -- a fair transfer "
                    "never waits for a second delivery, so confirming an "
                    "arrival too early turns everything still on the road "
                    "into a loss.",
                    chegada=picking.name,
                    partida=', '.join(
                        sorted(set(partidas.mapped('picking_id.name'))))))
        return True

    def _action_done(self):
        """A falta se mede ANTES de concluir.

        Sem pedido em espera, o núcleo reescreve a demanda para a quantidade
        concluída ao fechar o movimento: depois do super() a diferença não
        existe mais, e a perda seria zero. Por isso a medição acontece aqui,
        de fora para dentro.
        """
        faltas = {}
        # Vale para a CHEGADA e para o DESPACHO DE VOLTA. Na chegada, falta é
        # o que não veio; no despacho de volta, é o que a mesa deveria ter e
        # não entrou na caixa -- e essa é tão perda quanto a outra. Sem isto,
        # a diferença do retorno ficava como estoque numa mesa que já foi
        # desmontada, e ninguém era avisado de nada.
        for picking in self.filtered(
                lambda p: p.fair_id and (
                    p.fair_is_arrival
                    or p.fair_operation == 'return_dispatch')):
            linhas = [
                (move.product_id, move.product_uom_qty - move.quantity)
                for move in picking.move_ids
                if move.product_uom_qty - move.quantity > 0
            ]
            if linhas:
                faltas[picking.id] = linhas
        res = super()._action_done()
        self._ajustar_a_perna_seguinte()
        for picking_id, linhas in faltas.items():
            self.browse(picking_id)._registrar_a_falta(linhas)
        self._fechar_a_volta()
        return res

    def _fechar_a_volta(self):
        """A mesa esvaziou: agora sim o armazém tem trabalho, e o evento fecha.

        A remessa de volta validada é o instante em que a mercadoria deixa a
        praça. É aqui que nasce o cartão do armazém (e não antes, quando ele
        seria um vermelho de carga que nem saiu) e é aqui que o evento vira
        RETORNADO.
        """
        voltas = self.filtered(
            lambda p: p.fair_id and p.fair_operation == 'return_dispatch'
            and p.state == 'done')
        for picking in voltas:
            picking.fair_id._abrir_a_chegada_do_retorno(picking)
        voltas.fair_id._talvez_retornado()

    def _ajustar_a_perna_seguinte(self):
        """O que saiu é o que pode chegar.

        As duas pernas nascem com a mesma demanda, e quando a primeira fecha
        com MENOS -- porque feira não cria pedido em espera -- a segunda
        continuava pedindo o número velho. Duas consequências, as duas erradas:

          - na volta, os cinco que não entraram na caixa viravam perda no
            despacho E de novo na chegada, contados em dobro;
          - na ida, o que o armazém não achou virava "não recebido" na praça,
            como se a praça tivesse perdido livro que nunca saiu do depósito.

        Aqui a demanda da perna seguinte passa a ser o que a anterior
        efetivamente moveu. Zerou, o movimento é cancelado: carga que não
        saiu não tem chegada para esperar.
        """
        for picking in self.filtered('fair_id'):
            seguintes = picking.move_ids.move_dest_ids.filtered(
                lambda m: m.state not in ('done', 'cancel'))
            for destino in seguintes:
                saiu = sum(destino.move_orig_ids.filtered(
                    lambda m: m.state == 'done').mapped('quantity'))
                if destino.product_uom_qty == saiu:
                    continue
                if saiu <= 0:
                    destino._action_cancel()
                else:
                    destino.product_uom_qty = saiu
            vazios = seguintes.mapped('picking_id').filtered(
                lambda p: p.state not in ('done', 'cancel')
                and all(m.state == 'cancel' for m in p.move_ids))
            if vazios:
                vazios.action_cancel()
        return True

    def _registrar_a_falta(self, linhas):
        """A falta descoberta na chegada vira perda, com status "Não recebido".

        No meio de uma feira ninguém para para classificar avaria. Registra-se
        que faltou, com quantidade e custo congelado, e a explicação vem
        depois em Perdas -- que é onde há tempo de pensar. Pergunta em aberto
        é melhor do que exemplar que ninguém sabe que faltou.
        """
        self.ensure_one()
        if not self.fair_id:
            return self.env['event.fair.loss']
        # Onde o exemplar sumiu decide as duas coisas: o motivo e o estágio.
        #
        #   chegada na praça (receipt)   -> não recebido, ficou no trânsito
        #   chegada no armazém (return)  -> não voltou, ficou no trânsito
        #   despacho de volta (RET)      -> não voltou, ficou NA MESA: a
        #                                   contagem dizia que estava lá e
        #                                   ninguém pôs na caixa.
        #
        # Nenhum dos três baixa estoque: os três são perguntas em aberto, e a
        # baixa acontece quando alguém escolher o motivo de verdade.
        no_despacho = self.fair_operation == 'return_dispatch'
        de_volta = self.fair_operation == 'return' or no_despacho
        estagio = 'fair' if (no_despacho
                             or self.fair_operation == 'receipt') else 'transit'
        motivo = 'not_returned' if de_volta else 'not_received'
        perdas = self.env['event.fair.loss'].create([{
            'fair_id': self.fair_id.id,
            'product_id': produto.id,
            'qty': falta,
            'reason': motivo,
            'stage': estagio,
            'picking_id': self.id,
        } for produto, falta in linhas])
        if perdas:
            texto = _(
                "<p><b>%(feira)s</b> — <b>%(mov)s</b> left short: %(qtd)s "
                "copies the table should have had did not go into the box. "
                "They are in Losses as <b>%(motivo)s</b>, waiting for "
                "somebody to say what happened.</p>") if no_despacho else _(
                "<p><b>%(feira)s</b> — <b>%(mov)s</b> arrived short: "
                "%(qtd)s copies did not come. They are in Losses as "
                "<b>%(motivo)s</b>, waiting for somebody to say what "
                "happened.</p>")
            self.fair_id.message_post(body=Markup(texto % dict(
                feira=self.fair_id.display_name, mov=self.name,
                motivo=dict(perdas._fields['reason']._description_selection(
                    self.env))[motivo],
                qtd=int(sum(p.qty for p in perdas)))))
        return perdas

    def _avisar_a_conferencia(self):
        self.ensure_one()
        quando = fields.Datetime.context_timestamp(
            self, self.fair_checked_on or fields.Datetime.now())
        corpo = _(
            "<p><b>%(feira)s</b> — checked by <b>%(quem)s</b> on "
            "%(quando)s: %(qtd)s copies.</p>",
            feira=self.fair_id.display_name or '',
            quem=(self.fair_checked_by_id or self.env.user).display_name,
            quando=quando.strftime('%d/%m/%Y %H:%M'),
            qtd=int(self.fair_qty_checked))
        self.message_post(body=Markup(corpo))
        if self.fair_id:
            self.fair_id.message_post(body=Markup(corpo))
        return True

    def _avisar_de_qual_feira(self, fair, operation):
        """Escreve no histórico da transferência DE QUAL FEIRA ela é.

        A conversa da equipe acontece no lado direito da tela, e ali o Odoo
        só diz "Transferir criado". Quem recebe uma caixa precisa saber que
        ela é da Bienal do Livro de Paraty antes de responder qualquer coisa
        -- o código E00011 sozinho não diz nada a quem está no armazém, e o
        nome da feira é como as pessoas se referem a ela entre si.
        """
        rotulos = {
            'shipment': _('shipment to the fair'),
            'return': _('return from the fair'),
            'sale': _('sale at the fair'),
            'loss': _('loss at the fair'),
        }
        for picking in self:
            picking.message_post(body=Markup(_(
                "<p><b>%(feira)s</b> — %(tipo)s.</p>",
                feira=fair.display_name,
                tipo=rotulos.get(operation, operation))))
        return True
