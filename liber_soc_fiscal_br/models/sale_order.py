# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    """O CFOP decide o documento.

    Três operações tiram o livro do armazém sem vender, e elas não são a mesma coisa:

        consignação (5917/6917)  o livro continua nosso, na prateleira do cliente;
        bonificação (5910/6910)  o livro é dado -- sai do estoque, nunca vira receita;
        feira       (5914/6914)  o livro viaja e volta (1914/2914).

    Meter as três no mesmo Pedido C faria o mapa da consignação mentir: o consignado
    aumentaria com livros que foram doados, e o acerto cobraria por eles.
    """
    _inherit = 'sale.order'

    # O DOMÍNIO É A TRAVA MAIS BARATA que existe: em vez de deixar escolher
    # errado e depois recusar com uma mensagem, a lista já não oferece o que
    # não cabe. Um pedido de venda não escolhe 5917 (remessa em consignação) e
    # um Pedido C não escolhe 5102 (venda) -- porque o CFOP aqui não descreve
    # a nota, ele DECIDE que documento isto é, e trocá-lo troca a identidade
    # do pedido. Foi por essa porta que 21 pedidos de venda viraram
    # consignação em agosto/2026, sem que ninguém conseguisse reconstituir o
    # clique.
    _CFOP_DE_CONSIGNACAO = ('consignment', 'consignment_return')
    _CFOP_DE_VENDA = ('sale', 'settlement', 'bonus', 'event_out',
                      'event_return', 'transfer', 'other')

    cfop_id = fields.Many2one(
        'nfe.cfop', string='CFOP', copy=False, index=True,
        domain="[('document_kind', 'in', "
               "('consignment', 'consignment_return') if is_consignment else "
               "('sale', 'settlement', 'bonus', 'event_out', 'event_return', "
               "'transfer', 'other'))]",
        help="A operação fiscal desta saída. É ela que decide que documento isto é. "
             "A lista já vem recortada pelo que este pedido é: uma venda não "
             "oferece remessa em consignação, e um Pedido C não oferece venda.")
    document_kind = fields.Selection(
        related='cfop_id.document_kind', store=True, string='Operation',
        help="Derivado do CFOP. Vazio = indefinido: ninguém adivinha.")

    # --- a trava do meio-termo -------------------------------------------
    #
    # "Uma C000 não pode usar outra posição fiscal que a de consignação."
    # Trava dura resolveria, mas uma exceção legítima (regime especial,
    # substituição tributária) viraria chamado para o desenvolvedor. Então:
    # default aplicado, campo VISÍVEL para quem emite conferir antes da nota, e
    # editável só por quem tem responsabilidade fiscal na casa.
    # Vale para os DOIS documentos da operação: o S do acerto (via
    # consignment_operation_id) e o Pedido C (via is_consignment).
    consignment_fiscal_locked = fields.Boolean(
        compute='_compute_consignment_fiscal_locked',
        help="A posição fiscal deste pedido é ditada pela operação de "
             "consignação. Só o Administrador de faturamento pode trocá-la.")

    @api.depends('consignment_operation_id', 'is_consignment')
    def _compute_consignment_fiscal_locked(self):
        # has_group uma vez, não por registro: é o mesmo usuário na lista toda.
        pode_editar = self.env.user.has_group('account.group_account_manager')
        for order in self:
            order.consignment_fiscal_locked = (
                (bool(order.consignment_operation_id) or order.is_consignment)
                and not pode_editar)

    @api.depends('is_consignment')
    def _compute_fiscal_position_id(self):
        """A posição fiscal do Pedido C vem das Definições, não da ficha.

        Mesma tese do acerto (ver consignment_settlement.py deste módulo): o
        parceiro tem UM campo de posição fiscal, e a mesma livraria recebe
        remessa de consignação (5917) e compra em firme (5102) -- a ficha não
        codifica as duas. O padrão do Odoo, que deriva da ficha, resolvia o
        eixo errado em silêncio: no staging, 23% dos Pedidos C estavam sem
        posição nenhuma, e os demais dependiam de cadastro certo.

        Empresa sem configuração cai no padrão do Odoo em vez de estourar --
        a operação não pode parar por configuração que nunca foi preenchida.
        """
        super()._compute_fiscal_position_id()
        for order in self:
            if not order.is_consignment:
                continue
            fp = order.company_id.consignment_shipment_fiscal_position_id
            if fp:
                order.fiscal_position_id = fp

    @api.onchange('cfop_id')
    def _onchange_cfop_id(self):
        """O CFOP manda: quem é consignação vira Pedido C, quem não é, não."""
        for order in self:
            if order.cfop_id.document_kind == 'consignment':
                order.is_consignment = True
                order.consignment_type = order.consignment_type or 'opening'
            elif order.cfop_id.document_kind in ('bonus', 'event_out', 'event_return'):
                order.is_consignment = False
                order.consignment_type = False

    # ------------------------------------------------------------------
    # A malandragem: venda comum vestida de consignação
    # ------------------------------------------------------------------
    # A trava acima protege o Pedido C -- ele não sai da posição fiscal da
    # consignação sem alguém com responsabilidade fiscal. A porta INVERSA
    # ficou aberta, e é a que o dono nomeou em 06/09/2026: "a única trava útil
    # é não poder entrar em pedido de venda e meter uma posição fiscal de
    # consignação. Uma malandragem."
    #
    # Ela é malandragem porque funciona: o pedido continua sendo um S, aparece
    # na lista de Pedidos, conta na Análise de vendas -- e a NOTA sai como
    # remessa, sem receita e sem imposto de venda. O documento diz uma coisa e
    # o fiscal diz outra, e quem lê qualquer um dos dois lados sozinho não vê
    # nada de errado.
    #
    # Quem é consignação de verdade passa: o Pedido C (`is_consignment`) e o
    # S do acerto (`consignment_operation_id`), que são os dois documentos da
    # operação.
    @api.constrains('fiscal_position_id', 'is_consignment',
                    'consignment_operation_id')
    def _check_posicao_fiscal_de_consignacao(self):
        for order in self:
            if not order.fiscal_position_id or not order.company_id:
                continue
            if order.is_consignment or order.consignment_operation_id:
                continue
            empresa = order.company_id
            posicoes = (empresa.consignment_shipment_fiscal_position_id
                        | empresa.consignment_sale_fiscal_position_id
                        | empresa.consignment_return_fiscal_position_id)
            if order.fiscal_position_id in posicoes:
                raise UserError(_(
                    "%(order)s is a sales order and cannot carry the "
                    "consignment fiscal position %(fp)s.\n\n"
                    "The books would leave on a remessa note, with no revenue "
                    "and no sales tax, while the order still counts as a sale "
                    "in Sales Analysis. Consignment is the Consignment "
                    "Settlement's document, not a fiscal position you put on "
                    "a sale.",
                    order=order.name, fp=order.fiscal_position_id.display_name))

    @api.constrains('cfop_id', 'is_consignment')
    def _check_cfop_matches_document(self):
        for order in self:
            # read it from the CFOP itself: document_kind is a stored related field and
            # has not necessarily been recomputed when the constraint runs
            kind = order.cfop_id.document_kind
            if not kind:
                continue
            if kind == 'consignment' and not order.is_consignment:
                raise UserError(_(
                    "%(order)s carries CFOP %(cfop)s, a consignment shipment: the books "
                    "stay ours, on the customer's shelf. It has to be a Pedido C.",
                    order=order.name, cfop=order.cfop_id.code))
            # A metade que faltava: um Pedido C com CFOP de VENDA. O erro de
            # agosto/2026 saiu por aqui -- o pedido ficava consignado, a nota
            # saía como remessa e o dinheiro nunca aparecia no faturamento.
            if kind == 'sale' and order.is_consignment:
                raise UserError(_(
                    "%(order)s is a Pedido C but carries CFOP %(cfop)s, a sale. "
                    "On a consignment shipment the books stay ours: the sale only "
                    "happens at the Settlement. Pick a consignment CFOP, or make "
                    "this a sales order.",
                    order=order.name, cfop=order.cfop_id.code))
            if kind in ('bonus', 'event_out', 'event_return') and order.is_consignment:
                rotulo = dict(
                    order.cfop_id._fields['document_kind'].selection).get(kind, kind)
                raise UserError(_(
                    "%(order)s carries CFOP %(cfop)s (%(kind)s) and cannot be a Pedido C.\n\n"
                    "A bonus is given away -- it leaves the stock and never becomes "
                    "revenue. An event shipment comes back to us. Neither belongs on a "
                    "customer's consignment shelf, and neither is ever settled.",
                    order=order.name, cfop=order.cfop_id.code, kind=rotulo))

    # ------------------------------------------------------------------
    # A nota do Pedido C: uma remessa (REM/), nunca uma fatura
    # ------------------------------------------------------------------
    remessa_note_move_id = fields.Many2one(
        'account.move', string="Remessa note", readonly=True, copy=False)
    # The number, never the state: a remessa note can only be posted, so
    # "Lançado" under the button said nothing. The REM/ number says where to
    # look in Remessas; "A emitir" says there is nothing yet.
    remessa_note_label = fields.Char(
        compute='_compute_remessa_note_label', string="Note")

    # ------------------------------------------------------------------
    # A MESMA LÍNGUA DAS VENDAS
    # ------------------------------------------------------------------
    # "Deveria ser algo parecido com o que já temos em vendas, para não
    # obrigar a equipe a decorar duas linguagens: item em menu, filtro,
    # status."
    #
    # Em Vendas os três existem há sempre, e giram em torno de UM campo:
    # `invoice_status` (Nada a faturar / A faturar / Totalmente faturado), que
    # é badge na lista, filtro na busca e menu em "A faturar". Quem trabalha
    # ali lê o estado, filtra por ele e o encontra no menu — três portas, um
    # conceito.
    #
    # A consignação tinha o conceito e não tinha o campo: o estado da remessa
    # vivia espalhado em `qty_delivered` de um lado e `remessa_note_move_id`
    # do outro, e cada tela remontava a conta com um domínio composto. Ler a
    # tela exigia saber a receita. Este campo é a tradução do `invoice_status`
    # para o documento que a consignação emite -- mesmos três degraus, mesmas
    # cores, mesma posição na linha:
    #
    #     Vendas         invoice_status : Nada a faturar  A faturar  Faturado
    #     Consignação    remessa_status : Nada a emitir   A emitir   Emitida
    #
    # A palavra muda porque o documento muda -- remessa não é fatura, e o dono
    # foi explícito nisso. A GRAMÁTICA não muda, que é o que a equipe decora.
    remessa_status = fields.Selection([
        ('no', "Nothing to Issue"),
        ('to issue', "To Issue"),
        ('issued', "Issued"),
    ], string="Remessa Status", compute='_compute_remessa_status', store=True,
        help="Where the consignment shipment note (REM/) stands, the way "
             "Invoice Status says where the invoice stands.")

    @api.depends('is_consignment', 'state', 'order_line.qty_delivered',
                 'remessa_note_move_id', 'remessa_note_move_id.state')
    def _compute_remessa_status(self):
        for order in self:
            nota = order.remessa_note_move_id
            if nota and nota.state != 'cancel':
                # Nota cancelada não é nota -- a mesma regra do rótulo e do
                # botão. Cancelada, o pedido volta a "A emitir" sozinho.
                order.remessa_status = 'issued'
            elif not order.is_consignment or order.state not in ('sale',):
                order.remessa_status = 'no'
            elif any(line.qty_delivered > 0 for line in order.order_line
                     if not line.display_type):
                # A MESMA RÉGUA DO BOTÃO (`_remessa_linhas_a_faturar`): a nota
                # declara o que SAIU. Um pedido cuja carga saiu e voltou tem
                # líquido zero e não tem o que declarar -- o botão recusa, e o
                # status tem de dizer o mesmo, senão a tela promete o que o
                # botão nega.
                order.remessa_status = 'to issue'
            else:
                order.remessa_status = 'no'

    @api.depends('remessa_note_move_id.name', 'remessa_note_move_id.state')
    def _compute_remessa_note_label(self):
        # Nota cancelada não é nota: o botão volta a dizer "A emitir", que é a
        # verdade do pedido -- ele está de novo sem documento fiscal.
        for order in self:
            nota = order.remessa_note_move_id
            order.remessa_note_label = (
                nota.name if nota and nota.state != 'cancel' else "A emitir")

    def _remessa_linhas_a_faturar(self):
        """(linha, quantidade) do que REALMENTE saiu do armazém.

        A nota de remessa não é uma promessa, é o documento que viaja com a
        carga: o que ela declara tem que ser o que está na caixa. O C08547
        mostrou o preço de não checar -- pedido de 100, estoque para 62, nada
        expedido ainda, e a nota saiu dizendo 100.

        O S000 nunca teve esse problema porque o core faz a conta por ele: com
        política por entrega, `invoice_status` só vira "a faturar" quando há
        quantidade entregue, e `_create_invoices` fatura `qty_to_invoice`.
        Este botão não passa por nada disso, e a checagem foi embora junto com
        a estrutura. Aqui ela volta, na única forma que serve para uma
        remessa: a quantidade é a ENTREGUE, não a pedida.
        """
        self.ensure_one()
        return [
            (line, line.qty_delivered)
            for line in self.order_line
            if not line.display_type and line.qty_delivered > 0
        ]

    def action_generate_remessa_note(self):
        """The consignment shipment's fiscal note -- also a remessa.

        "Precisamos pensar na nota fiscal de consignação, que é também uma
        remessa." The Criar-fatura path on a Pedido C dead-ends by design (a
        consignment is not a sale; there is nothing to invoice), which left
        the C000 with NO note at all. This is the note: an out_invoice in the
        REM/ journal, under the CONSIGNMENT fiscal position from Settings --
        the field that sat unread since it was declared -- auto-settled on
        post, so the bookseller is never billed for books still ours.
        """
        for order in self:
            if not order.is_consignment:
                raise UserError(_(
                    "%s is not a Pedido C -- a regular sale invoices through "
                    "Criar fatura.", order.name))
            if order.state != 'sale':
                raise UserError(_(
                    "%s: confirm the Pedido first, then generate the note.",
                    order.name))
            # Nota cancelada não segura o pedido. Cancelada a nota (na SEFAZ e
            # no Odoo), o C000 volta a poder emitir: senão um cancelamento
            # deixa o pedido preso para sempre, sem documento e sem botão.
            # Nota VIVA continua segurando, e apertar de novo não duplica.
            if order.remessa_note_move_id.state not in (False, 'cancel'):
                continue
            company = order.company_id
            fpos = company.consignment_shipment_fiscal_position_id
            if not (fpos and fpos.auto_invoice_paid
                    and fpos.auto_invoice_paid_account_id):
                raise UserError(_(
                    "The consignment shipment fiscal position is not mapped "
                    "(it needs Auto Invoice Paid and its account). Set it in "
                    "Settings > Consignment Fiscal -- a remessa de consignação "
                    "(CFOP 5917/6917) must never bill the bookseller."))
            linhas = order._remessa_linhas_a_faturar()
            if not linhas:
                pendentes = order.picking_ids.filtered(
                    lambda p: p.state not in ('done', 'cancel'))
                raise UserError(_(
                    "%(pedido)s ainda não movimentou mercadoria: não há o que "
                    "declarar na nota.\n\nValide a transferência "
                    "%(mov)s primeiro — a nota de remessa acompanha a carga, "
                    "e uma nota que declara livro que não saiu não bate com o "
                    "volume na estrada.",
                    pedido=order.name,
                    mov=", ".join(pendentes.mapped('name')) or _("do pedido")))
            journal = company._get_remessa_journal(
                kind='consignment', fiscal_position=fpos,
                name=_("Remessas de Consignação"), code='REM-C')
            note = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'journal_id': journal.id,
                'partner_id': order.partner_id.id,
                'fiscal_position_id': fpos.id,
                'invoice_date': fields.Date.context_today(order),
                'invoice_origin': order.name,
                'remessa_origin': 'consignment',
                'invoice_line_ids': [
                    (0, 0, {
                        'product_id': line.product_id.id,
                        'quantity': qty,
                        'price_unit': line.price_unit,
                        'discount': line.discount,
                    })
                    for line, qty in linhas
                ],
            })
            note.action_post()
            order.remessa_note_move_id = note
        return True

    def action_view_remessa_note(self):
        self.ensure_one()
        if not self.remessa_note_move_id:
            raise UserError(_(
                "%s has no remessa note yet. Generate it with the "
                "\"Criar nota\" button after confirming.", self.name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.remessa_note_move_id.id,
            'view_mode': 'form',
        }

    def _create_invoices(self, grouped=False, final=False, date=None):
        # A bonificação e a remessa para feira também não faturam: uma é doação, a
        # outra é transferência. O Pedido C já é barrado no soc_moves.
        nao_fatura = self.filtered(
            lambda o: o.document_kind in ('bonus', 'event_out', 'event_return'))
        if nao_fatura:
            raise UserError(_(
                "These orders do not invoice: %(orders)s.\n\n"
                "A bonus is a gift -- it is an expense, never revenue. An event "
                "shipment is a transfer between our own locations, and it comes back.",
                orders=", ".join(nao_fatura.mapped('name')),
            ))
        return super()._create_invoices(grouped=grouped, final=final, date=date)
