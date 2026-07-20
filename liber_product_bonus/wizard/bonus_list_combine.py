# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductBonusListCombine(models.TransientModel):
    """Select a group of lists, make a new one.

    With hundreds of VIP lists this is the operation that keeps them usable --
    but note what it is NOT for. If you just want to ship one campaign to three
    lists, do that on the dispatch (which takes several lists and dedups on its
    own); a permanent list born of a one-off campaign is how you end up with
    three hundred of them.

    Combine when the union REPEATS. "Imprensa de poesia" = imprensa literária ∩
    tag poesia is a thing you will want again next year. "Lançamento de março" is
    not -- the BO already records who got that book.
    """
    _name = 'product.bonus.list.combine'
    _description = 'Combine VIP Lists'

    name = fields.Char(string="New list", required=True)
    list_ids = fields.Many2many(
        'product.bonus.list', string="Lists", required=True,
        default=lambda s: s.env.context.get('active_ids', []))
    mode = fields.Selection([
        ('union', 'Union -- everyone in any of them'),
        ('intersection', 'Intersection -- only who is in ALL of them'),
        ('difference', 'Difference -- the first one, minus the others'),
    ], default='union', required=True)
    user_id = fields.Many2one(
        'res.users', string="Owner", required=True, default=lambda s: s.env.user)
    tag_ids = fields.Many2many('product.bonus.list.tag', string="Tags")
    note = fields.Text(
        string="Nota",
        help="Por que esta lista existe. Vai para a nota da nova lista, "
             "acima da procedência -- que o assistente escreve sozinho.")

    # O que fazer com as originárias.
    #
    # Arquivar é o padrão do meio: some do seletor do BO (que é o incômodo
    # real de ter 132 listas) sem apagar o histórico de quem esteve nelas.
    # Apagar existe porque lista de teste é lixo e lixo se joga fora -- mas
    # recusa quando a lista já bonificou alguém, porque aí ela não é lixo, é
    # registro.
    source_action = fields.Selection([
        ('keep', "Manter como estão"),
        ('archive', "Arquivar as originárias"),
        ('delete', "Apagar as originárias"),
    ], string="As listas de origem", default='keep', required=True)

    preview_html = fields.Html(compute='_compute_preview', sanitize=False)
    result_count = fields.Integer(compute='_compute_preview')

    def _sets(self):
        self.ensure_one()
        return [l.member_ids.filtered('active').mapped('partner_id')
                for l in self.list_ids]

    def _resolve(self, mode=None):
        """The members a mode produces. Pass `mode` explicitly rather than
        toggling self.mode inside a compute -- that reads clever and breaks the
        first time two things read it at once."""
        self.ensure_one()
        sets = self._sets()
        if not sets:
            return self.env['res.partner']
        mode = mode or self.mode
        out = sets[0]
        if mode == 'union':
            out = self.env['res.partner']
            for s in sets:
                out |= s
        elif mode == 'intersection':
            for s in sets[1:]:
                out &= s
        else:  # difference: the first, minus everybody else
            for s in sets[1:]:
                out -= s
        return out

    @api.depends('list_ids', 'mode')
    def _compute_preview(self):
        for wiz in self:
            result = wiz._resolve()
            wiz.result_count = len(result)
            wiz.preview_html = wiz._render(result)

    def _render(self, result):
        self.ensure_one()
        if not self.list_ids:
            return '<div class="text-muted">Escolha as listas.</div>'
        total = sum(len(l.member_ids.filtered('active')) for l in self.list_ids)
        # The overlap IS the information. "37 pessoas estão em mais de uma
        # lista" is the number that tells you whether these lists are really
        # different things or the same thing under two names.
        overlap = total - len(self._resolve('union'))
        rows = ['<div style="font-size:13px;line-height:1.8;">']
        for l in self.list_ids:
            rows.append('<div>&middot; %s &mdash; <b>%d</b> membros</div>'
                        % (l.name, len(l.member_ids.filtered('active'))))
        rows.append('<hr style="margin:6px 0;"/>')
        rows.append('<div><b>%d</b> membros somados &middot; <b>%d</b> em mais de '
                    'uma lista</div>' % (total, overlap))
        if overlap and self.mode == 'union':
            rows.append('<div style="color:#888;font-size:11px;">'
                        'A união não duplica ninguém: quem está em duas listas '
                        'entra uma vez só.</div>')
        rows.append('<div style="margin-top:6px;font-size:15px;">'
                    '&rarr; a nova lista fica com <b style="color:#28a745;">%d</b> '
                    'pessoas</div>' % len(result))
        if not result:
            rows.append('<div style="color:#dc3545;">Ninguém sobra com este modo.</div>')
        rows.append('</div>')
        return ''.join(rows)

    def action_combine(self):
        self.ensure_one()
        result = self._resolve()
        if not result:
            raise UserError(_("Nobody is left with this mode."))

        # Recusar ANTES de criar a nova lista: metade do trabalho feito e um
        # erro na cara é pior que o erro sozinho.
        if self.source_action == 'delete':
            com_historico = self.list_ids.filtered(lambda l: l.bonus_count)
            if com_historico:
                raise UserError(_(
                    "Estas listas já bonificaram alguém e por isso não são "
                    "descartáveis -- apagá-las tiraria de cada bonificação a "
                    "informação de por qual lista ela passou:\n\n%(lists)s\n\n"
                    "Escolha 'Arquivar' -- some do seletor, o histórico fica.",
                    lists="\n".join("· %s (%s bonificações)"
                                    % (l.name, l.bonus_count)
                                    for l in com_historico)))

        procedencia = _("Combinada (%(mode)s) a partir de: %(lists)s",
                        mode=self.mode,
                        lists=", ".join(self.list_ids.mapped('name')))
        new = self.env['product.bonus.list'].create({
            'name': self.name,
            'user_id': self.user_id.id,
            'tag_ids': [(6, 0, self.tag_ids.ids)],
            'source_list_ids': [(6, 0, self.list_ids.ids)],
            'combine_mode': self.mode,
            # A nota dele primeiro, a procedência embaixo: quem abre a lista
            # quer ler o porquê, não a mecânica. E a procedência não é
            # opcional -- se as originárias forem apagadas, esta linha é a
            # única memória de onde esta gente veio.
            'note': "%s\n\n%s" % (self.note, procedencia) if self.note
                    else procedencia,
            'member_ids': [(0, 0, {'partner_id': p.id}) for p in result],
        })
        new.message_post(body=_(
            "Combined (%(mode)s) from %(lists)s -- %(n)s people.",
            mode=self.mode, lists=", ".join(self.list_ids.mapped('name')),
            n=len(result)))

        if self.source_action == 'archive':
            self.list_ids.action_archive()
            new.message_post(body=_(
                "Originárias arquivadas: %(lists)s",
                lists=", ".join(self.list_ids.mapped('name'))))
        elif self.source_action == 'delete':
            nomes = ", ".join(self.list_ids.mapped('name'))
            self.list_ids.unlink()
            new.message_post(body=_("Originárias apagadas: %(lists)s",
                                    lists=nomes))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.bonus.list',
            'res_id': new.id,
            'view_mode': 'form',
        }
