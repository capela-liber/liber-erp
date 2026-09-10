# -*- coding: utf-8 -*-
"""A nota que acompanha a carga da feira.

Livro na estrada sem nota é livro apreendido. E a nota da feira não é nota de
venda: a mercadoria não muda de dono ao subir na van, muda de lugar. É uma
simples remessa, com CFOP de remessa para exposição ou feira, emitida para a
própria editora.
"""
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EventFair(models.Model):
    _inherit = 'event.fair'

    note_move_ids = fields.One2many(
        'account.move', 'fair_id', string='Remessa Notes')
    note_count = fields.Integer(compute='_compute_note_count')
    pickings_without_note = fields.Integer(
        compute='_compute_note_count',
        help="Shipments already out with no fiscal note covering them.")

    @api.depends('note_move_ids', 'picking_ids.state',
                 'picking_ids.fair_operation',
                 'picking_ids.fair_note_move_id')
    def _compute_note_count(self):
        for fair in self:
            fair.note_count = len(fair.note_move_ids)
            # O botão aparece desde o DESPACHO, e não só depois de o armazém
            # validar. Escondido até lá, ele deixava a pessoa que acabou de
            # despachar procurando onde emitir a nota -- e a resposta "espere
            # o armazém validar" é justamente o que a tela precisa dizer, em
            # vez de sumir. Apertado antes da hora, ele diz isso.
            fair.pickings_without_note = len(
                fair._shipments_pending_note()) + len(fair._returns_to_note())

    def _pickings_to_note(self):
        """Remessas já concluídas que ainda não têm nota viva.

        Nota cancelada não segura a carga: cancelada na SEFAZ e no Odoo, a
        transferência volta a poder ser declarada. Nota viva segura, e apertar
        o botão de novo não duplica. É a mesma regra do C000
        (liber_soc_fiscal_br/models/sale_order.py).
        """
        self.ensure_one()
        return self.picking_ids.filtered(
            lambda p: p.fair_operation == 'shipment'
            and p.state == 'done'
            and p.fair_note_move_id.state in (False, 'cancel'))

    def _shipments_pending_note(self):
        """Remessas sem nota viva, validadas ou não. Só para o botão."""
        self.ensure_one()
        return self.picking_ids.filtered(
            lambda p: p.fair_operation == 'shipment'
            and p.state != 'cancel'
            and p.fair_note_move_id.state in (False, 'cancel'))

    def _returns_to_note(self):
        """Retornos viajando sem nota.

        É a PRIMEIRA perna da volta (mesa -> trânsito) que a nota acompanha:
        ela viaja com as caixas. A segunda (trânsito -> armazém) é a
        conferência de quem recebe, e não gera documento novo.
        """
        self.ensure_one()
        return self.picking_ids.filtered(
            lambda p: p.fair_operation == 'return_dispatch'
            and p.state != 'cancel'
            and p.fair_note_move_id.state in (False, 'cancel'))

    def _fair_note_fiscal_position(self):
        self.ensure_one()
        fpos = self.company_id.fair_shipment_fiscal_position_id
        if not (fpos and fpos.auto_invoice_paid
                and fpos.auto_invoice_paid_account_id):
            raise UserError(_(
                "The fair shipment fiscal position of %(empresa)s is not "
                "ready: it needs Auto Invoice Paid and its account. Set it in "
                "Settings > Fairs.\n\nA remessa para feira must never bill "
                "anyone: the books are going to our own table, and the "
                "company cannot owe money to itself.",
                empresa=self.company_id.display_name))
        return fpos

    def action_generate_remessa_note(self):
        """Uma nota por carga despachada, com o que REALMENTE saiu.

        O mesmo botão fecha as duas pontas: se houver retorno viajando sem
        nota, ele emite a da volta também. Quem aperta quer a feira em dia
        com o fiscal, não escolher entre dois botões parecidos.
        """
        notes = self.env['account.move']
        for fair in self:
            if fair._returns_to_note():
                notes |= fair.action_generate_return_note()
            pickings = fair._pickings_to_note()
            if not pickings:
                if notes:
                    continue
                pendentes = fair.picking_ids.filtered(
                    lambda p: p.fair_operation == 'shipment'
                    and p.state not in ('done', 'cancel'))
                if pendentes:
                    raise UserError(_(
                        "%(feira)s has not shipped yet: there is nothing to "
                        "declare.\n\nValidate %(mov)s first — the note "
                        "travels with the load, and a note declaring books "
                        "that did not leave does not match the van.",
                        feira=fair.display_name,
                        mov=", ".join(pendentes.mapped('name'))))
                raise UserError(_(
                    "Every shipment of %s already has its note.",
                    fair.display_name))
            fpos = fair._fair_note_fiscal_position()
            journal = fair.company_id._get_remessa_journal(
                kind='event', fiscal_position=fpos,
                name=_("Remessas de Feira"), code='REM-F')
            for picking in pickings:
                linhas = fair._note_lines(picking)
                if not linhas:
                    continue
                note = self.env['account.move'].create({
                    'move_type': 'out_invoice',
                    'journal_id': journal.id,
                    # O destinatário somos NÓS. A mercadoria não muda de dono
                    # ao subir na van: muda de lugar. É o que distingue a
                    # remessa para feira da remessa de consignação, que sai
                    # para o livreiro.
                    'partner_id': fair.company_id.partner_id.id,
                    'fiscal_position_id': fpos.id,
                    'invoice_date': fields.Date.context_today(fair),
                    'invoice_origin': '%s / %s' % (fair.code, picking.name),
                    'remessa_origin': 'event',
                    'fair_id': fair.id,
                    'company_id': fair.company_id.id,
                    'invoice_line_ids': linhas,
                })
                note.action_post()
                picking.fair_note_move_id = note
                fair._carimbar_na_logistica(picking, note)
                fair._avisar_a_nota(picking, note, volta=False)
                notes |= note
        return notes

    def _carimbar_na_logistica(self, picking, note):
        """A transferência tem de conhecer a sua nota.

        A logística vive na tela do movimento, não na da contabilidade: é lá
        que ela imprime a DANFE e é lá que estão os filtros "Com nota" e "Sem
        nota". O `liber_nfe_picking` guarda esse vínculo em `nfe_move_id`, e o
        carimba andando movimento -> pedido de venda -> transferências.

        A feira NÃO TEM pedido de venda: o caminho nunca chega nela. O
        resultado, na tela, é a caixa pronta para viajar e o Imprimir dizendo
        "Sem nota fiscal" sobre uma carga cuja nota existe e está lançada.
        Quem emite a nota da feira é este módulo, então é ele quem carimba.

        A DANFE continua chegando só quando a SEFAZ autoriza: o relatório
        cobra o PDF depois de cobrar o vínculo. O que se conserta aqui é o
        vínculo, que faltava.
        """
        self.ensure_one()
        if 'nfe_move_id' in picking._fields:
            picking.nfe_move_id = note
        return True

    # ------------------------------------------------------------------
    # a nota do retorno
    # ------------------------------------------------------------------
    def _fair_return_fiscal_position(self, exigir=True):
        self.ensure_one()
        fpos = self.company_id.fair_return_fiscal_position_id
        if not (fpos and fpos.auto_invoice_paid
                and fpos.auto_invoice_paid_account_id):
            if not exigir:
                return self.env['account.fiscal.position']
            raise UserError(_(
                "The fair return fiscal position of %(empresa)s is not "
                "ready: it needs Auto Invoice Paid and its account. Set it "
                "in Settings > Fairs.\n\nThe books cannot travel back "
                "without a note.",
                empresa=self.company_id.display_name))
        return fpos

    def action_generate_return_note(self):
        """A nota que acompanha a carga na volta.

        Sai no MESMO clique do retorno, e declara a quantidade PEDIDA, não a
        recebida -- ao contrário da nota de ida. Não é inconsistência, é a
        estrada: a nota de ida se emite depois que o armazém separa, porque é
        aqui que se sabe o que de fato entrou na van; a de volta se emite
        quando as caixas deixam a feira, porque ela viaja COM elas. Nota que
        só saísse na chegada deixaria o caminhão rodar sem documento.

        A diferença entre o que a nota declara e o que o armazém recebe é
        assunto da conferência do retorno, que ainda não existe. Ela vai
        aparecer como divergência de recebimento, que é onde essa conversa
        tem de acontecer -- e não escondida numa nota que ninguém emitiu.
        """
        notes = self.env['account.move']
        for fair in self:
            pickings = fair._returns_to_note()
            if not pickings:
                raise UserError(_(
                    "%s has no return travelling without a note.",
                    fair.display_name))
            fpos = fair._fair_return_fiscal_position()
            journal = fair.company_id._get_remessa_journal(
                kind='event', fiscal_position=
                fair.company_id.fair_shipment_fiscal_position_id,
                name=_("Remessas de Feira"), code='REM-F')
            ida = fair.note_move_ids.filtered(
                lambda m: m.move_type == 'out_invoice'
                and m.state == 'posted')[:1]
            for picking in pickings:
                linhas = fair._note_lines(picking, use_demand=True)
                if not linhas:
                    continue
                vals = {
                    # Nota de CRÉDITO: a ida e a volta se anulam, que é
                    # exatamente o que aconteceu -- a mercadoria saiu e
                    # voltou, e nada mudou de dono no caminho.
                    'move_type': 'out_refund',
                    'journal_id': journal.id,
                    'partner_id': fair.company_id.partner_id.id,
                    'fiscal_position_id': fpos.id,
                    'invoice_date': fields.Date.context_today(fair),
                    'invoice_origin': '%s / %s' % (fair.code, picking.name),
                    'remessa_origin': 'event',
                    'fair_id': fair.id,
                    'company_id': fair.company_id.id,
                    'invoice_line_ids': linhas,
                }
                if ida and 'focus_nota_referenciada_id' in self.env[
                        'account.move']._fields:
                    # A volta referencia a chave da ida: é o que fecha o par
                    # aos olhos da SEFAZ.
                    vals['focus_nota_referenciada_id'] = ida.id
                note = self.env['account.move'].create(vals)
                note.action_post()
                picking.fair_note_move_id = note
                fair._carimbar_na_logistica(picking, note)
                fair._avisar_a_nota(picking, note, volta=True)
                notes |= note
        return notes

    def _do_return(self, devolvendo, perdas):
        """Retornar já libera a nota: a carga não roda sem documento.

        Mas contabilidade NÃO trava armazém. Se a posição fiscal de retorno
        da empresa não estiver pronta, o retorno acontece do mesmo jeito e a
        feira registra em alto e bom som o que falta configurar -- em vez de
        deixar as caixas na praça esperando alguém preencher um campo em
        Definições. A nota se emite depois, pelo botão, e o aviso fica no
        histórico até lá.
        """
        pickings = super()._do_return(devolvendo, perdas)
        for fair in self:
            # A PRIMEIRA perna da volta é a que viaja e a que precisa de
            # nota. A segunda é a conferência de quem recebe.
            pendentes = fair.picking_ids.filtered(
                lambda p: p.fair_operation == 'return_dispatch'
                and p.state != 'cancel'
                and not p.fair_note_move_id)
            if not pendentes:
                continue
            if fair._fair_return_fiscal_position(exigir=False):
                fair.action_generate_return_note()
            else:
                fair.message_post(body=Markup(_(
                    "<p><b>%(feira)s — the return went out without a fiscal "
                    "note.</b> "
                    "The fair return fiscal position of %(empresa)s is not "
                    "configured (it needs Auto Invoice Paid and its "
                    "account, in Settings &gt; Fairs). Fix it and press "
                    "<b>Fiscal note</b>.</p>",
                    feira=fair.display_name,
                    empresa=fair.company_id.display_name)))
        return pickings

    def _avisar_a_nota(self, picking, note, volta=False):
        """Diz no histórico da feira que a nota saiu, e qual é.

        A nota do retorno sai sozinha, no clique do Retorno, e sem este aviso
        ninguém descobre: o número aparece num contador no alto e mais nada.
        A pergunta do dono da casa -- "quando eu retorno, onde faço a nota?"
        -- não era sobre o mecanismo, era sobre a tela não contar o que
        tinha acabado de fazer.
        """
        self.ensure_one()
        corpo = _(
            "<p><b>%(feira)s</b> — %(tipo)s <b>%(nota)s</b> issued for "
            "<b>%(mov)s</b>. It lives in Invoicing &gt; Customers &gt; "
            "Remessas.</p>",
            feira=self.display_name,
            tipo=(_("return note") if volta else _("remessa note")),
            nota=note.name, mov=picking.name)
        self.message_post(body=Markup(corpo))
        return True

    def _note_lines(self, picking, use_demand=False):
        """O que a nota declara: a quantidade CONCLUÍDA daquela carga.

        Não a planejada, nem a pedida. Uma nota que diz 100 quando saíram 62
        não bate com o volume na estrada, e é a nota que o fiscal lê. O valor
        é o preço de venda do título — o valor da mercadoria que viaja.
        """
        self.ensure_one()
        por_produto = {}
        for move in picking.move_ids:
            qty = move.product_uom_qty if use_demand else move.quantity
            if not use_demand and move.state != 'done':
                continue
            if qty <= 0:
                continue
            por_produto.setdefault(move.product_id, 0.0)
            por_produto[move.product_id] += qty
        return [
            (0, 0, {
                'product_id': product.id,
                'quantity': qty,
                'price_unit': product.lst_price,
            })
            for product, qty in por_produto.items()
        ]

    def action_view_notes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fair Notes'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('fair_id', '=', self.id)],
        }
