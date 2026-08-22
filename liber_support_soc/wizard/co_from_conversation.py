# -*- coding: utf-8 -*-
"""Da conversa para a CO: a tela de conferência.

O parser propõe, o humano confere, e SÓ então a CO nasce (em rascunho).
Mesmo racional do import de XML: sugerir é barato, errar acerto é caro.

Não é mais TransientModel de propósito (pedido do usuário, 10/08): a
conferência é trabalho — a pessoa sai para checar algo e volta. Um rascunho
por chamado; reabrir o botão devolve o rascunho como estava. Criar a CO
descarta o rascunho."""
import base64
import csv
import difflib
import io
import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models import co_parser


class CoFromConversation(models.Model):
    _name = 'liber.support.co.wizard'
    _description = 'Open a CO from this conversation (draft)'
    _rec_name = 'ticket_id'

    ticket_id = fields.Many2one(
        'liber.support.ticket', required=True, ondelete='cascade',
        index=True)
    # `readonly=False`: o parceiro se resolve AQUI, e grava de volta no
    # chamado. Antes era só leitura, e um chamado sem cliente (o e-mail que
    # chega de um remetente que ninguém casou ainda) obrigava a fechar o
    # assistente, achar o chamado, preencher, e voltar. O rascunho sobrevive
    # -- é um por chamado --, mas 43 linhas de planilha na tela e um "feche
    # tudo e comece de novo" é o tipo de atrito que faz a pessoa desistir da
    # ferramenta.
    partner_id = fields.Many2one(
        # Sem `string=`: o rótulo é herdado do chamado, que a casa já vê como
        # "Parceiro". Dar um nome novo aqui criaria um texto a traduzir e duas
        # palavras para a mesma coisa na mesma tela.
        related='ticket_id.partner_id', readonly=False,
        help="The customer of this conversation. Setting it here also sets "
             "it on the ticket.")
    # A opção pedida em 10/08: acerto, reposição ou devolução para o lote
    # inteiro — a linha individual continua editável para a exceção.
    # `sale` vem PRIMEIRO por pedido da direção (12/08/2026), e é diferente
    # das outras três em natureza: elas escolhem o destino da linha DENTRO de
    # uma CO; ela escolhe outro documento. Ficou na mesma lista porque é assim
    # que quem atende pensa -- "o que faço com esta conversa?" --, e um segundo
    # campo "tipo de documento" antes deste seria mais fiel ao modelo e menos
    # fiel à cabeça de quem usa. Se um dia aparecer uma quinta opção que
    # também troque de documento, é hora de separar.
    default_dest = fields.Selection([
        ('sale', 'Sale'),
        ('sold', 'Settle (sold)'),
        ('replenish', 'Replenish'),
        ('return', 'Return'),
    ], string='Apply as', default='sold', required=True,
        help="Every proposed line gets this destination; change a single "
             "line on the grid for exceptions. 'Sale' is the odd one: it "
             "creates a plain sale order and no consignment settlement.")
    source_text = fields.Text(
        string='Raw text',
        help="Pre-filled with the customer's emails. Paste here freely "
             "— including straight from Excel (tab-separated works).")
    attachment_id = fields.Many2one(
        'ir.attachment', string='Attached file',
        domain="[('res_model', '=', 'liber.support.ticket'),"
               " ('res_id', '=', ticket_id)]",
        help="An NFe .xml, .xlsx, .csv or system-generated PDF that came "
             "with the conversation. Picking a file re-reads the lines. "
             "An NFe XML is the best source — exact ISBN and quantity — "
             "and, when present, the e-mail text is not read on top of "
             "it. Scanned PDFs (photos) have no text layer and come out "
             "empty.")
    xlsx_file = fields.Binary(
        string='Or upload a file',
        help="First sheet; title and quantity in any two columns.")
    xlsx_filename = fields.Char()
    line_ids = fields.One2many(
        'liber.support.co.wizard.line', 'wizard_id', string='Proposed Lines')
    # A conferência pedida em 22/08: o XML diz quem são as duas pontas
    # (emitente e destinatário), e se o parceiro do chamado não é nenhuma
    # delas, a tela grita. Aviso forte + confirmação explícita, não
    # bloqueio — há caso legítimo (filial emitindo pela matriz).
    cnpj_alert = fields.Char(readonly=True)
    cnpj_override = fields.Boolean(
        string='Create anyway — I checked the CNPJ mismatch',
        help="The NFe XML names two parties and the partner above is "
             "neither of them. Tick to confirm this is intentional "
             "(e.g. a branch issuing under the head office).")

    _ticket_uniq = models.Constraint(
        'UNIQUE (ticket_id)', 'One draft per ticket — reopen it instead.')

    # ------------------------------------------------------------------
    # parsing
    # ------------------------------------------------------------------

    def _all_products(self):
        return self.env['product.product'].search(
            [('sale_ok', '=', True)])

    @staticmethod
    def _norm(text):
        """Pontuação vira espaço: 'big-techs' casa com 'big techs', e o
        subtítulo depois do ':' não atrapalha o contains."""
        return re.sub(r'\s+', ' ',
                      re.sub(r"[-–—:;,!?.()'\"]", ' ',
                             (text or '').lower())).strip()

    def _match_product(self, label, isbn, products, names_norm):
        """ISBN/barcode wins; then exact name; then unique contains; then
        fuzzy with a confidence cut. Tudo sobre nomes normalizados."""
        if isbn:
            hit = products.filtered(lambda p: p.barcode == isbn)
            if hit:
                return hit[0], 'exact'
        low = self._norm(label)
        if not low:
            return None, 'none'
        exact = [p for p, n in zip(products, names_norm) if n == low]
        if exact:
            return exact[0], 'exact'
        contains = [p for p, n in zip(products, names_norm) if low in n]
        if len(contains) == 1:
            return contains[0], 'good'
        close = difflib.get_close_matches(low, names_norm, n=1, cutoff=0.6)
        if close:
            idx = names_norm.index(close[0])
            return products[idx], 'weak'
        return None, 'none'

    @staticmethod
    def _pdf_to_text(raw):
        """PDF com camada de texto -> texto puro para o parser. PDF
        escaneado (imagem) sai vazio — OCR é assunto do módulo claude."""
        import io as _io
        try:
            import pypdf as _pdf
        except ImportError:
            import PyPDF2 as _pdf
        reader = _pdf.PdfReader(_io.BytesIO(raw))
        return '\n'.join(page.extract_text() or '' for page in reader.pages)

    @staticmethod
    def _spreadsheet_to_text(name, raw):
        """.xlsx (openpyxl), .csv ou PDF com texto -> texto para o parser."""
        name = (name or '').lower()
        if name.endswith('.pdf') or raw[:5] == b'%PDF-':
            return CoFromConversation._pdf_to_text(raw)
        if name.endswith('.csv') or raw[:4] not in (b'PK\x03\x04',):
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                text = raw.decode('latin-1')
            if name.endswith('.csv') or ';' in text or ',' in text:
                rows = list(csv.reader(
                    io.StringIO(text),
                    delimiter=';' if ';' in text else ','))
                return co_parser.xlsx_rows_to_text(rows)
            return text
        import openpyxl
        book = openpyxl.load_workbook(
            io.BytesIO(raw), read_only=True, data_only=True)
        return co_parser.xlsx_rows_to_text(
            book.worksheets[0].iter_rows(values_only=True))

    @api.onchange('default_dest')
    def _onchange_default_dest(self):
        # `sale` não é destino de linha -- é outro documento. Propagá-lo
        # gravaria um valor que não existe na Selection da linha, e o Odoo
        # aceitaria em memória para estourar no salvamento. Na venda o destino
        # da linha simplesmente não importa: o pedido leva produto, quantidade
        # e preço, e nada de prateleira.
        if self.default_dest == 'sale':
            return
        self.line_ids.dest = self.default_dest

    def _build_lines(self, text):
        products = self._all_products()
        names_norm = [self._norm(p.name) for p in products]
        commands = [(5, 0, 0)]
        for cand in co_parser.parse_lines(text):
            product, confidence = self._match_product(
                cand['label'], cand['isbn'], products, names_norm)
            commands.append((0, 0, {
                'label_source': cand['label'],
                'product_id': product.id if product else False,
                'qty': cand['qty'],
                'confidence': confidence,
                'dest': self.default_dest or 'sold',
            }))
        self.line_ids = commands

    def _source_files(self):
        """(nome, bytes) de cada arquivo preenchido. O binário do upload
        pode chegar impróprio no onchange (o cliente web manda o tamanho,
        não o conteúdo) — quem não decodifica é pulado em silêncio."""
        files = []
        if self.attachment_id:
            files.append((self.attachment_id.name,
                          base64.b64decode(self.attachment_id.datas)))
        if self.xlsx_file:
            try:
                files.append((self.xlsx_filename or '.xlsx',
                              base64.b64decode(self.xlsx_file)))
            except Exception:
                pass
        return files

    def _parse_sources(self):
        """(Re)read the sources and rebuild the proposed lines.

        O XML de NFe VENCE: com itens vindos de um XML, o texto do
        e-mail e as planilhas não somam linhas por cima — é a fonte
        exata, e somar duplicaria item. Sem XML (ou com XML vazio ou
        quebrado), vale a soma antiga: arquivo + texto bruto."""
        self.ensure_one()
        xml_parts, other_parts = [], []
        for name, raw in self._source_files():
            if co_parser.is_nfe_xml(name, raw):
                items = co_parser.nfe_items(raw)
                if items:
                    xml_parts.append(co_parser.items_to_text(items))
            else:
                other_parts.append(self._spreadsheet_to_text(name, raw))
        if xml_parts:
            self._build_lines('\n'.join(xml_parts))
        else:
            other_parts.append(self.source_text or '')
            self._build_lines('\n'.join(other_parts))
        self._update_cnpj_alert(self._party_docs())

    def _party_docs(self):
        """As pontas (CNPJ/CPF) de todo XML de NFe entre os arquivos."""
        docs = set()
        for name, raw in self._source_files():
            if co_parser.is_nfe_xml(name, raw):
                docs |= co_parser.nfe_party_docs(raw)
        return docs

    def _update_cnpj_alert(self, party_docs):
        """Compara o CNPJ do parceiro com as DUAS pontas do XML — numa
        devolução a livraria é a emitente. Sem XML, sem alerta."""
        self.cnpj_alert = False
        self.cnpj_override = False
        if not party_docs:
            return
        partner = self.partner_id.commercial_partner_id
        if not partner:
            return
        vat = re.sub(r'\D', '', partner.vat or '')
        if not vat:
            self.cnpj_alert = _(
                "%(partner)s has no CNPJ on file, so the NFe XML "
                "(parties: %(docs)s) could not be checked against it.",
                partner=partner.display_name,
                docs=', '.join(sorted(party_docs)))
        elif vat not in party_docs:
            self.cnpj_alert = _(
                "CNPJ mismatch: %(partner)s (%(vat)s) is neither the "
                "issuer nor the recipient of this NFe XML "
                "(parties: %(docs)s). Check the file and the partner "
                "before creating anything.",
                partner=partner.display_name, vat=partner.vat,
                docs=', '.join(sorted(party_docs)))

    @api.onchange('attachment_id', 'xlsx_file')
    def _onchange_source_file(self):
        # Escolher o arquivo já relê — era o tropeço: selecionar o XML e
        # clicar Criar saía com as linhas velhas do e-mail.
        self._parse_sources()

    @api.onchange('partner_id')
    def _onchange_partner_cnpj(self):
        # Trocar o parceiro NÃO reconstrói a grade (edição manual é
        # trabalho); só a conferência de CNPJ acompanha.
        self._update_cnpj_alert(self._party_docs())

    def action_parse(self):
        """(Re)read the sources — the button for when the raw text was
        edited (text edits don't re-read on their own)."""
        self._parse_sources()
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Open a CO from this conversation'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # criação da CO
    # ------------------------------------------------------------------

    def _sale_order_values(self, ticket, lines):
        """Pedido de venda a partir das linhas reconhecidas na conversa.

        Três decisões, todas da direção em 12/08/2026:

        - **preço de capa**, não o que o cliente escreveu. O e-mail traz o
          preço que ele lembra, o que pagou da última vez ou o que gostaria de
          pagar; o preço da casa é o da ficha.
        - **desconto do cadastro** do cliente, que nesta casa é a LISTA DE
          PREÇO. Ver a nota abaixo -- ela custou uma volta inteira.
        - **o acordo de consignação não entra.** Vender para uma livraria não
          pressupõe acordo, e ler o CA aqui misturaria duas condições
          comerciais diferentes na mesma nota.

        NÃO se escreve `price_unit` nem `discount` aqui, e isso é o ponto.
        A primeira versão os calculava à mão (capa + um campo de desconto novo
        no parceiro) e o pedido saía com 0% para um cliente que tem "55% EL"
        na ficha: o valor escrito à mão vence o computado, e a lista era
        ignorada. A casa tem 131 listas e 11.595 clientes com lista própria --
        o desconto por cliente já estava cadastrado, com muito mais nuance do
        que um percentual único (rede, feira, N1, EL, HE).

        Deixando os dois campos em paz, o Odoo os calcula da lista do cliente:
        com regra de desconto, `price_unit` fica o preço de capa e o abatimento
        aparece na coluna de desconto -- exatamente o que a tela promete.
        """
        return {
            'partner_id': ticket.partner_id.id,
            'company_id': ticket.company_id.id,
            'origin': ticket.name,
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
            }) for line in lines],
        }

    def _action_create_sale(self, ticket, lines):
        """A opção Venda: um pedido, nenhuma CO."""
        order = self.env['sale.order'].create(
            self._sale_order_values(ticket, lines))
        ticket.sale_order_id = order
        ticket.message_post(
            body=_('Sale order %(name)s drafted from this conversation: '
                   '%(count)s line(s), cover price with the customer\'s '
                   'pricelist (%(pricelist)s).',
                   name=order.name, count=len(lines),
                   pricelist=order.pricelist_id.display_name or _('none')),
            message_type='comment', subtype_xmlid='mail.mt_note')
        self.unlink()   # rascunho cumprido
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
        }

    def action_create_co(self):
        self.ensure_one()
        ticket = self.ticket_id
        if not ticket.partner_id:
            # A mensagem não pode dizer "CO" quando se escolheu Venda: quem
            # lê procura o erro no lugar errado. E ela agora diz onde
            # resolver, porque o campo está nesta mesma tela.
            raise UserError(_(
                "This conversation has no customer yet. Fill in the "
                "customer above — it is saved on the ticket too — and then "
                "create the %(documento)s.",
                documento=(_("sale order") if self.default_dest == 'sale'
                           else _("consignment settlement (CO)"))))
        if self.cnpj_alert and not self.cnpj_override:
            # Grita, mas não bloqueia: a caixa de confirmação está na
            # mesma tela, para o caso legítimo (filial pela matriz).
            raise UserError(_(
                "The NFe XML raised a CNPJ warning:\n%(alert)s\n\n"
                "If this is intentional, tick \"Create anyway\" and "
                "create again.", alert=self.cnpj_alert))
        lines = self.line_ids.filtered(lambda l: l.product_id and l.qty > 0)
        if not lines:
            raise UserError(_(
                "No usable line: every line needs a product and a "
                "quantity."))

        # Venda desvia antes de qualquer coisa de consignação: nada de acordo,
        # nada de prateleira, nada de CO.
        if self.default_dest == 'sale':
            return self._action_create_sale(ticket, lines)
        settlement = ticket.settlement_id
        if not settlement or settlement.state != 'draft':
            settlement = self.env['consignment.settlement'].create({
                'partner_id': ticket.partner_id.id,
                'company_id': ticket.company_id.id,
            })
            ticket.settlement_id = settlement
        Line = self.env['consignment.settlement.line']
        for line in lines:
            values = {
                'settlement_id': settlement.id,
                'product_id': line.product_id.id,
            }
            if line.dest == 'return':
                values['qty_return'] = line.qty
            elif line.dest == 'replenish':
                values['qty_replenish'] = line.qty
            else:
                values['qty_reported'] = line.qty
            Line.create(values)
        ticket.message_post(
            body=_('CO %(name)s drafted from this conversation: '
                   '%(count)s line(s).',
                   name=settlement.name, count=len(lines)),
            message_type='comment', subtype_xmlid='mail.mt_note')
        self.unlink()  # rascunho cumprido
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'consignment.settlement',
            'res_id': settlement.id,
            'view_mode': 'form',
        }


class CoFromConversationLine(models.Model):
    _name = 'liber.support.co.wizard.line'
    _description = 'Proposed CO line'
    _order = 'id'

    wizard_id = fields.Many2one(
        'liber.support.co.wizard', required=True, ondelete='cascade')
    label_source = fields.Char(
        string='As Written', readonly=True,
        help="What the conversation actually said.")
    product_id = fields.Many2one(
        'product.product', string='Product',
        domain=[('sale_ok', '=', True)])
    qty = fields.Integer(string='Qty', default=1)
    dest = fields.Selection([
        ('sold', 'Settle (sold)'),
        ('return', 'Return'),
        ('replenish', 'Replenish'),
    ], default='sold', required=True, string='Destination',
        help="Sold feeds the settlement (qty_reported); Return recalls "
             "stock from the shelf (qty_return); Replenish resends to "
             "refill the shelf (qty_replenish).")
    confidence = fields.Selection([
        ('exact', 'Exact'),
        ('good', 'Good'),
        ('weak', 'Check!'),
        ('none', 'Not found'),
    ], readonly=True, string='Match')
