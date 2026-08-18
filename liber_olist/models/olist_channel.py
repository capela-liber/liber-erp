# -*- coding: utf-8 -*-
"""O canal do Olist, e quem ele é no nosso cadastro.

O Olist manda o nome do canal DELE em cada pedido — "Mercado Livre",
"Online: Hedra", "Online: Circuito", "Hedra" — e esses nomes não são os canais
de venda da casa, que são "Marketplaces", "Online", "Livrarias independentes",
"Website HE". São duas taxonomias, montadas por gente diferente, para
perguntas diferentes.

Até 18/08/2026 a integração resolvia isso casando por nome e, quando não
achava, CRIANDO um `crm.team` com o nome que o Olist tinha mandado. O efeito
está no staging: o canal 98 "Hedra" (empresa 3, EdLab Press) nasceu assim e é
o único ativo daquela empresa, enquanto os canais legítimos estão arquivados.
Uma leitura de API não pode decidir a taxonomia comercial da casa.

Daí este espelho, no mesmo espírito do mapa de unidades da Amazon
(`liber.amazon.unit`): o nome externo é a única chave que atravessa a
fronteira, o módulo o REGISTRA sozinho na primeira vez que o vê — isso é
descoberta, e é barato —, e o par do lado de cá fica VAZIO até alguém dizer
qual é. Canal sem par não trava nada: o pedido entra sem canal, e a linha sem
par fica visível na tela para ser resolvida.
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class OlistChannel(models.Model):
    _name = 'olist.channel'
    _description = "Espelho de canal de venda do Olist"
    _order = 'account_id, name'

    name = fields.Char(
        "Canal no Olist", required=True, index=True,
        help="O nome do canal exatamente como o Olist o manda "
             "(`ecommerce.nomeEcommerce`). É a chave que atravessa a "
             "fronteira, e por isso é guardada crua.")
    account_id = fields.Many2one(
        'olist.account', string="Conta", required=True, ondelete='cascade',
        index=True)
    company_id = fields.Many2one(
        related='account_id.company_id', store=True, index=True)

    team_id = fields.Many2one(
        'crm.team', string="Canal de venda",
        domain="[('company_id', 'in', (False, company_id))]",
        help="O canal de venda da casa (`crm.team`) a que este canal do Olist "
             "corresponde. Nasce VAZIO de propósito: o módulo descobre o nome "
             "de lá, mas quem decide a taxonomia comercial daqui é a casa. "
             "Enquanto estiver vazio, os pedidos deste canal entram sem canal "
             "— o que é o mesmo que dizer 'ainda não classificado'.")
    platform = fields.Char(
        "Plataforma", help="A plataforma que o Olist informa por trás do canal "
                           "(`intermediador.nome`): Shopify, Mercado Livre. O "
                           "canal é o nome da loja; a plataforma é onde ela "
                           "roda. Informativo — o mapeamento é o campo ao lado.")
    order_count = fields.Integer(
        "Pedidos", compute='_compute_order_count',
        help="Quantos pedidos desta conta chegaram por este canal. É o número "
             "que diz o que vale a pena mapear primeiro.")
    active = fields.Boolean(default=True)

    _name_account_uniq = models.Constraint(
        'unique(account_id, name)',
        "Este canal do Olist já está espelhado nesta conta.")

    def _compute_order_count(self):
        contagem = {}
        if self.ids:
            contagem = {
                (conta.id, canal): total
                for conta, canal, total in self.env['olist.order']._read_group(
                    [('account_id', 'in', self.account_id.ids),
                     ('canal', 'in', [c for c in self.mapped('name') if c])],
                    ['account_id', 'canal'], ['__count'])
            }
        for linha in self:
            linha.order_count = contagem.get(
                (linha.account_id.id, linha.name), 0)

    @api.depends('name', 'team_id')
    def _compute_display_name(self):
        for linha in self:
            linha.display_name = "%s — %s" % (
                linha.name or '?',
                linha.team_id.name or _("sem canal do Odoo"))

    # ------------------------------------------------------------------
    # Descoberta
    # ------------------------------------------------------------------
    @api.model
    def _find_or_create(self, account, canal, plataforma=None):
        """A linha do espelho deste canal, criando-a na primeira vez.

        Isto é DESCOBERTA, não cadastro: registra que o Olist usou este nome,
        e nada mais. Nenhum `crm.team` nasce aqui — foi exatamente isso que
        poluiu a lista de canais da casa antes de 18/08/2026.

        A conveniência que sobra é o pré-preenchimento: se já existe um canal
        de venda com o MESMO nome, a linha nova nasce apontando para ele, e
        ninguém precisa refazer à mão um par óbvio. Se não existe, fica vazio
        e a tela mostra a pendência.
        """
        if not account or not canal:
            return self.browse()
        canal = canal.strip()
        if not canal:
            return self.browse()
        linha = self.with_context(active_test=False).search(
            [('account_id', '=', account.id), ('name', '=', canal)], limit=1)
        if linha:
            # A plataforma pode chegar depois do canal (o primeiro pedido
            # daquele canal pode não ter intermediador). Preenche uma vez.
            if plataforma and not linha.platform:
                linha.platform = plataforma
            return linha
        equipe = account._find_team(canal)
        linha = self.create({
            'account_id': account.id,
            'name': canal,
            'platform': plataforma or False,
            'team_id': equipe.id,
        })
        _logger.info(
            "Olist: canal '%s' descoberto na conta %s (%s).", canal,
            account.name,
            "casado com o canal de venda '%s'" % equipe.name if equipe
            else "sem canal de venda — falta mapear")
        return linha

    # ------------------------------------------------------------------
    # O mapa muda: os pedidos já lidos precisam saber
    # ------------------------------------------------------------------
    def _stamp_orders(self, equipe_anterior=None):
        """Leva o mapeamento aos pedidos que já estavam espelhados.

        `olist.order.team_id` é campo comum, não calculado — não existe
        `@api.depends` para "qualquer canal com este nome". Sem este empurrão,
        mapear o canal hoje não consertaria os pedidos lidos ontem: eles
        continuariam sem canal e ninguém entenderia por quê (é a mesma lição
        de `liber.amazon.unit._recompute_orders`).

        Só mexe no que ainda não foi decidido de outra forma: pedido sem canal,
        ou com o canal que ESTE mapa dizia antes. Um canal posto à mão num
        pedido específico não é reescrito.
        """
        for linha in self:
            if not linha.name:
                continue
            dominio = [('account_id', '=', linha.account_id.id),
                       ('canal', '=', linha.name)]
            anterior = (equipe_anterior or {}).get(linha.id)
            if anterior:
                dominio.append(('team_id', 'in', [False, anterior]))
            else:
                dominio.append(('team_id', '=', False))
            pedidos = self.env['olist.order'].search(dominio)
            if pedidos:
                pedidos.write({'team_id': linha.team_id.id or False})
        return True

    @api.model_create_multi
    def create(self, vals_list):
        linhas = super().create(vals_list)
        linhas.filtered('team_id')._stamp_orders()
        return linhas

    def write(self, vals):
        if 'team_id' not in vals and 'name' not in vals:
            return super().write(vals)
        anterior = {linha.id: linha.team_id.id for linha in self}
        res = super().write(vals)
        self._stamp_orders(equipe_anterior=anterior)
        return res

    def action_open_orders(self):
        """Os pedidos que chegaram por este canal."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Pedidos do canal %s", self.name),
            'res_model': 'olist.order',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.account_id.id),
                       ('canal', '=', self.name)],
        }
