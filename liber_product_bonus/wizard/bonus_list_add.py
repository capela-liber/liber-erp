# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductBonusListAdd(models.TransientModel):
    """Filtre em Contatos, marque vários, jogue todos numa lista.

    "quero por exemplo fazer filtros e colocar vários na lista" -- e o lugar
    onde os filtros bons moram é a tela de Contatos, com as buscas, etiquetas e
    agrupamentos que o Odoo já dá de graça. Então o caminho é de LÁ para cá:
    marca-se o que interessa e a ação abre isto.

    Reentrância é a parte que importa. Rodar duas vezes com a mesma seleção não
    pode explodir na restrição de unicidade nem duplicar ninguém, e quem SAIU da
    lista (active=False) precisa voltar em vez de bater na restrição -- porque a
    segunda rodada quase sempre acontece: filtra-se de novo, encontra-se mais
    gente, e a maioria já estava lá.
    """
    _name = 'product.bonus.list.add'
    _description = 'Add Contacts to a VIP List'

    # Escolher-ou-criar num campo só: digitar um nome que não existe oferece
    # "Criar «...»" no dropdown, que é o padrão do Odoo.
    list_id = fields.Many2one(
        'product.bonus.list', string="Lista", required=True,
        domain=[('active', '=', True)])
    partner_ids = fields.Many2many(
        'res.partner', string="Contacts", required=True,
        default=lambda s: s._default_partner_ids())

    @api.model
    def _default_partner_ids(self):
        """Só herda a seleção quando ela É de contatos.

        `active_ids` não quer dizer "contatos marcados", quer dizer "os
        registros da tela de onde vim" -- e a tela de onde se vem também é a
        FICHA DA LISTA, pelo botão da aba Membros. De lá o contexto traz o id
        da própria lista, que era lido aqui como id de contato: abrir o
        assistente na lista 2074 tentava carregar res.partner(2074) e morria
        com "Registro não existe ou foi apagado".

        O erro é a sorte, não o problema. Se por acaso existisse um contato com
        aquele id -- e com dezenas de milhares deles, existe --, o assistente
        abriria em silêncio com um estranho já marcado, e alguém o adicionaria
        à lista sem nunca entender de onde ele saiu. Por isso a guarda é pelo
        MODELO, não um try/except em volta da leitura.
        """
        ctx = self.env.context
        if ctx.get('active_model') != 'res.partner':
            return []
        return ctx.get('active_ids', [])
    note = fields.Char(
        string="Note",
        help="Fica em cada membro adicionado -- por que este grupo entrou.")

    # A MESMA tela serve a duas portas, e elas pedem coisas opostas.
    # De Contatos > Ação, escolher a lista É a pergunta: a pessoa marcou gente
    # e ainda não disse para onde vai. Da ficha da lista, a lista já está
    # decidida -- e um seletor de lista no topo de um diálogo aberto DENTRO de
    # uma lista faz a tela parecer que serve para "incluir lista", que é outra
    # coisa. Aqui ela vira contexto (o título), e os contatos ocupam o lugar
    # de honra, que é o que de fato se escolhe.
    list_locked = fields.Boolean(
        default=lambda s: bool(s.env.context.get('default_list_id')))

    summary_html = fields.Html(compute='_compute_summary', sanitize=False)

    @api.depends('list_id', 'partner_ids')
    def _compute_summary(self):
        """Diz o que VAI acontecer, antes de acontecer.

        Sem isto o botão é um salto no escuro: "adicionei 40 e a lista cresceu
        3" vira mistério, quando na verdade 37 já estavam lá.
        """
        for wiz in self:
            total = len(wiz.partner_ids)
            if not total:
                wiz.summary_html = ""
                continue
            if not wiz.list_id:
                wiz.summary_html = ""
                continue
            existing = self.env['product.bonus.list.member'].with_context(
                active_test=False).search([('list_id', '=', wiz.list_id.id)])
            already = existing.filtered(
                lambda m: m.active and m.partner_id in wiz.partner_ids)
            back = existing.filtered(
                lambda m: not m.active and m.partner_id in wiz.partner_ids)
            fresh = total - len(already) - len(back)
            parts = ["<b>%s</b> novo(s)" % fresh] if fresh else []
            if back:
                parts.append("<b>%s</b> de volta" % len(back))
            if already:
                parts.append("<b>%s</b> já na lista (ignorado)" % len(already))
            wiz.summary_html = (
                "<p>%s → <b>%s</b></p>"
                % (", ".join(parts) or "nada a fazer", wiz.list_id.name))

    def action_add(self):
        self.ensure_one()
        target = self.list_id

        Member = self.env['product.bonus.list.member']
        # active_test=False é o ponto todo: um One2many ESCONDE os inativos,
        # então quem saiu da lista ficava invisível aqui, o create era tentado
        # de novo e estourava a restrição de unicidade -- justamente o caso da
        # segunda rodada, que é o normal.
        existing = Member.with_context(active_test=False).search(
            [('list_id', '=', target.id)])
        by_partner = {m.partner_id.id: m for m in existing}
        added = revived = 0
        for partner in self.partner_ids:
            member = by_partner.get(partner.id)
            if member is None:
                Member.create({
                    'list_id': target.id,
                    'partner_id': partner.id,
                    'note': self.note or False,
                })
                added += 1
            elif not member.active:
                # Voltou: não recria (a restrição de unicidade barraria) e não
                # apaga a história de quando entrou da primeira vez.
                member.write({'active': True, 'left_on': False})
                revived += 1

        target.message_post(body=_(
            "%(added)s contato(s) adicionado(s), %(revived)s reativado(s), "
            "de uma seleção de %(total)s.",
            added=added, revived=revived, total=len(self.partner_ids)))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.bonus.list',
            'res_id': target.id,
            'view_mode': 'form',
        }
