# -*- coding: utf-8 -*-
"""Da conversa para a CO: a tela de conferência.

O parser propõe, o humano confere, e SÓ então a CO nasce (em rascunho).
Mesmo racional do import de XML: sugerir é barato, errar acerto é caro.

Não é mais TransientModel de propósito (pedido do usuário, 10/08): a
conferência é trabalho — a pessoa sai para checar algo e volta. Um rascunho
por âncora; reabrir o botão devolve o rascunho como estava. Criar a CO
descarta o rascunho.

DUAS ÂNCORAS desde 01/09/2026. O assistente nasceu preso ao chamado, onde o
trabalho é REATIVO: chegou um e-mail, abre-se o documento a partir dele. O
atendimento ATIVO da consignação anda no sentido contrário — a pessoa parte
da CO da livraria, escreve para ela, e a resposta (e-mail, planilha, PDF,
XML de NFe) volta para DENTRO daquela CO. É o mesmo mecanismo; muda só de
onde ele é chamado.

Por isso `ticket_id` e `settlement_id` são exclusivos e um deles é
obrigatório (ver `_check_anchor`). Ancorado no chamado, criar abre/reusa a CO
do chamado; ancorado na CO, as linhas caem NAQUELA CO e nenhuma outra
nasce."""
import base64
import difflib
import logging
import re

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from ..models import co_parser

_logger = logging.getLogger(__name__)


class CoFromConversation(models.Model):
    _name = 'liber.support.co.wizard'
    _description = 'Open a CO from this conversation (draft)'
    _rec_name = 'ticket_id'

    # As duas âncoras. Uma e só uma por rascunho (`_check_anchor`): o
    # assistente é o mesmo, o ponto de partida é que muda.
    ticket_id = fields.Many2one(
        'liber.support.ticket', ondelete='cascade', index=True)
    settlement_id = fields.Many2one(
        'consignment.settlement', string='Consignment (CO)',
        ondelete='cascade', index=True,
        help="When the draft was opened from a consignment, the imported "
             "lines land in THIS operation.")
    # `readonly=False`: o parceiro se resolve AQUI, e grava de volta no
    # chamado. Antes era só leitura, e um chamado sem cliente (o e-mail que
    # chega de um remetente que ninguém casou ainda) obrigava a fechar o
    # assistente, achar o chamado, preencher, e voltar. O rascunho sobrevive
    # -- é um por chamado --, mas 43 linhas de planilha na tela e um "feche
    # tudo e comece de novo" é o tipo de atrito que faz a pessoa desistir da
    # ferramenta.
    # Era `related='ticket_id.partner_id'`, e com duas âncoras o related não
    # serve mais: numa CO o cliente vem da CO. Computado-armazenado-editável
    # dá o mesmo comportamento de tela (preenche sozinho, aceita correção) e
    # a escrita de volta no chamado mora no `write` abaixo.
    partner_id = fields.Many2one(
        # Sem `string=`: o rótulo é herdado do chamado, que a casa já vê como
        # "Parceiro". Dar um nome novo aqui criaria um texto a traduzir e duas
        # palavras para a mesma coisa na mesma tela.
        'res.partner', compute='_compute_partner_id', store=True,
        readonly=False, precompute=True,
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
    # O domínio segue a âncora: os anexos do chamado, ou os da CO. Escrito
    # sobre dois campos calculados em vez de um literal, senão o assistente
    # aberto de uma CO ofereceria os anexos de um chamado que não existe.
    source_model = fields.Char(compute='_compute_source_ref')
    source_res_id = fields.Integer(compute='_compute_source_ref')
    attachment_id = fields.Many2one(
        'ir.attachment', string='Attached file',
        domain="[('res_model', '=', source_model),"
               " ('res_id', '=', source_res_id)]",
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

    # NULL não conflita com NULL no Postgres: as duas travas convivem, cada
    # uma valendo só para os rascunhos da sua âncora.
    _ticket_uniq = models.Constraint(
        'UNIQUE (ticket_id)', 'One draft per ticket — reopen it instead.')
    _settlement_uniq = models.Constraint(
        'UNIQUE (settlement_id)',
        'One draft per consignment — reopen it instead.')

    # ------------------------------------------------------------------
    # âncora
    # ------------------------------------------------------------------

    @api.constrains('ticket_id', 'settlement_id')
    def _check_anchor(self):
        for wizard in self:
            if bool(wizard.ticket_id) == bool(wizard.settlement_id):
                raise ValidationError(_(
                    "A draft belongs either to a support ticket or to a "
                    "consignment — never to both, never to neither."))

    def _anchor(self):
        """O registro de onde o assistente foi aberto. É ele que leva a
        empresa, o nome da origem e o chatter da anotação."""
        self.ensure_one()
        return self.ticket_id or self.settlement_id

    @api.depends('ticket_id.partner_id', 'settlement_id.partner_id')
    def _compute_partner_id(self):
        for wizard in self:
            wizard.partner_id = (wizard.settlement_id.partner_id
                                 or wizard.ticket_id.partner_id)

    @api.depends('ticket_id', 'settlement_id')
    def _compute_source_ref(self):
        for wizard in self:
            anchor = wizard.ticket_id or wizard.settlement_id
            wizard.source_model = anchor._name if anchor else False
            wizard.source_res_id = anchor.id if anchor else 0

    @api.model_create_multi
    def create(self, vals_list):
        # O `@api.constrains` só é chamado para os campos que aparecem nos
        # vals: um `create({})` passaria batido e nasceria um rascunho sem
        # âncora, invisível nas duas telas e impossível de reabrir.
        records = super().create(vals_list)
        records._check_anchor()
        return records

    def write(self, vals):
        res = super().write(vals)
        # O que o related fazia sozinho: corrigir o cliente aqui corrige o
        # do chamado. Na CO não se escreve de volta — lá o cliente é a
        # âncora, e trocá-lo por um assistente seria trocar o documento.
        if vals.get('partner_id'):
            for wizard in self:
                ticket = wizard.ticket_id
                if ticket and ticket.partner_id.id != vals['partner_id']:
                    ticket.partner_id = vals['partner_id']
        return res

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
        """Planilha (.xlsx, .xls, SpreadsheetML, HTML, CSV) ou PDF com
        camada de texto -> texto para o parser.

        Quem decide o formato é a assinatura do arquivo, no co_parser —
        metade dos anexos reais chega com a extensão errada. Arquivo que
        o leitor não consegue abrir devolve texto vazio em vez de
        estourar: o assistente ainda tem o texto do e-mail, e um
        traceback no onchange não deixa nem isso."""
        name = (name or '').lower()
        if name.endswith('.pdf') or raw[:5] == b'%PDF-':
            return CoFromConversation._pdf_to_text(raw)
        try:
            return co_parser.sheet_to_text(name, raw)
        except Exception:
            _logger.warning("Não consegui ler a planilha %s", name,
                            exc_info=True)
            return ''

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
                # `sale` não existe na Selection da linha: é outro
                # documento, não um destino. O onchange já o segurava na
                # tela, mas pelo ORM ele chegava até aqui e estourava no
                # INSERT — o caminho do ORM ficou exercitado quando a CO
                # passou a abrir o mesmo assistente.
                'dest': (self.default_dest
                         if self.default_dest in
                         ('sold', 'replenish', 'return') else 'sold'),
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
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': (_('Import lines into this consignment')
                     if self.settlement_id
                     else _('Open a CO from this conversation')),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # abertura (o mesmo gesto nas duas âncoras)
    # ------------------------------------------------------------------

    @api.model
    def _harvest(self, record):
        """Colhe de um registro com chatter o material do assistente:
        (texto das mensagens de e-mail, melhor anexo).

        Estava dentro do chamado e subiu para cá quando a CO passou a abrir
        o mesmo assistente — o atendimento ativo colhe da conversa da CO
        exatamente como o reativo colhe da do chamado."""
        inbound = record.message_ids.filtered(
            lambda m: m.message_type == 'email').sorted('date')
        parts = []
        for message in inbound:
            # tabelas-relatório (ex.: estoque mínimo da Olist) viram
            # linhas resolvidas (mínimo − estoque); o resto vira texto
            rest, items = co_parser.extract_report_tables(
                str(message.body or ''))
            if items:
                parts.append(co_parser.items_to_text(items))
            parts.append(co_parser.html_to_text(rest))
        source = '\n\n'.join(p for p in parts if p.strip())
        # NFe XML primeiro: é a fonte exata (ISBN + quantidade da SEFAZ).
        # Confere o CONTEÚDO, não só a extensão — nem todo .xml de anexo é
        # uma NFe.
        attachment = next(
            (a for a in self.env['ir.attachment'].search(
                [('res_model', '=', record._name),
                 ('res_id', '=', record.id),
                 ('name', '=ilike', '%.xml')],
                order='id desc')
             if co_parser.is_nfe_xml(
                 a.name, base64.b64decode(a.datas or b''))),
            self.env['ir.attachment'])
        if not attachment:
            attachment = self.env['ir.attachment'].search(
                [('res_model', '=', record._name),
                 ('res_id', '=', record.id),
                 '|', '|', ('name', '=ilike', '%.xlsx'),
                 ('name', '=ilike', '%.csv'),
                 ('name', '=ilike', '%.pdf')],
                order='id desc', limit=1)
        return source, attachment

    @api.model
    def _open_for(self, record):
        """Abre (ou devolve) o rascunho de conferência de um registro.

        Um por âncora: se já existe, volta exatamente como foi deixado —
        conferir outra coisa no meio não pode custar o trabalho feito."""
        field = ('ticket_id' if record._name == 'liber.support.ticket'
                 else 'settlement_id')
        wizard = self.search([(field, '=', record.id)], limit=1)
        if not wizard:
            source, attachment = self._harvest(record)
            wizard = self.create({
                field: record.id,
                'source_text': source,
                'attachment_id': attachment.id or False,
            })
            wizard.action_parse()
        return wizard._reopen()

    # ------------------------------------------------------------------
    # criação da CO
    # ------------------------------------------------------------------

    def _sale_order_values(self, anchor, lines):
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
            'partner_id': self.partner_id.id,
            'company_id': anchor.company_id.id,
            'origin': anchor.name,
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
            }) for line in lines],
        }

    def _action_create_sale(self, anchor, lines):
        """A opção Venda: um pedido, nenhuma CO.

        Vale nas duas âncoras. Aberta de uma CO, o pedido nasce com a CO na
        origem e a anotação cai no chatter dela — mas NENHUM campo da CO é
        escrito: `sale_order_id` da CO é o pedido do acerto, gerado pelo
        `action_run`, e escrevê-lo aqui faria a CO apontar para uma venda
        firme como se fosse a sua apuração."""
        order = self.env['sale.order'].create(
            self._sale_order_values(anchor, lines))
        if anchor._name == 'liber.support.ticket':
            anchor.sale_order_id = order
        # LINK, e não o nome em texto (pedido do usuário, 01/09/2026). Saindo
        # de uma CO, este pedido é raro e não tem campo que o guarde: a CO já
        # usa `sale_order_id` para o pedido do ACERTO, e escrevê-lo aqui faria
        # a apuração apontar para uma venda firme. Sem campo, a única trilha
        # que sobra é o chatter -- e um número escrito em texto obriga a copiar
        # e caçar na lista de pedidos. `_get_html_link` dá o mesmo <a> que o
        # Odoo usa nas suas próprias anotações, e o `Markup` é o que impede o
        # `message_post` de escapá-lo (o nome do cliente e a lista continuam
        # escapados, por virem pelo `%`).
        anchor.message_post(
            body=Markup(_(
                'Sale order %(link)s drafted from this conversation: '
                '%(count)s line(s), cover price with the customer\'s '
                'pricelist (%(pricelist)s).')) % {
                    'link': order._get_html_link(),
                    'count': len(lines),
                    'pricelist': (order.pricelist_id.display_name
                                  or _('none')),
                },
            message_type='comment', subtype_xmlid='mail.mt_note')
        # E a volta: o pedido guarda a CO só no `origin`, que é texto solto.
        # Quem cai nele por uma busca não tem como voltar à operação que o
        # gerou sem procurar o número à mão.
        order.message_post(
            body=Markup(_('Drafted from %(link)s.')) % {
                'link': anchor._get_html_link()},
            message_type='comment', subtype_xmlid='mail.mt_note')
        self.unlink()   # rascunho cumprido
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
        }

    def _apply_lines(self, settlement, lines):
        """Despeja as linhas conferidas numa CO, SOMANDO no produto que já
        estiver lá.

        Somar em vez de acrescentar é o que o atendimento ativo exige: a CO
        já vem com o mapa da prateleira (`action_populate_from_shelf`), e
        criar uma segunda linha do mesmo título faria o acerto contar duas
        vezes o que a livraria vendeu uma. No caminho antigo, o do chamado, a
        CO em geral nasce vazia e o efeito é o mesmo de antes."""
        Line = self.env['consignment.settlement.line']
        column = {'return': 'qty_return', 'replenish': 'qty_replenish'}
        for line in lines:
            field = column.get(line.dest, 'qty_reported')
            existing = settlement.line_ids.filtered(
                lambda l, p=line.product_id: l.product_id == p)[:1]
            if existing:
                existing[field] += line.qty
            else:
                Line.create({
                    'settlement_id': settlement.id,
                    'product_id': line.product_id.id,
                    field: line.qty,
                })

    def action_create_co(self):
        self.ensure_one()
        anchor = self._anchor()
        ticket = self.ticket_id
        if self.settlement_id and self.settlement_id.state != 'draft':
            raise UserError(_(
                "%(name)s is not a draft any more: it was already run, and "
                "adding lines to it would change an operation the customer "
                "has already been given. Open a new consignment.",
                name=self.settlement_id.name))
        if not self.partner_id:
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
            return self._action_create_sale(anchor, lines)
        # Ancorado na CO, o destino é ela mesma. Ancorado no chamado,
        # reusa-se a CO em rascunho do chamado ou abre-se uma.
        settlement = self.settlement_id
        if not settlement:
            settlement = ticket.settlement_id
            if not settlement or settlement.state != 'draft':
                settlement = self.env['consignment.settlement'].create({
                    'partner_id': self.partner_id.id,
                    'company_id': ticket.company_id.id,
                })
                ticket.settlement_id = settlement
        self._apply_lines(settlement, lines)
        anchor.message_post(
            # Anotações diferentes de propósito: na CO o documento já
            # existia, e dizer "aberta a partir desta conversa" seria falso.
            body=(_('%(count)s line(s) imported into this consignment.',
                    count=len(lines))
                  if self.settlement_id
                  # Mesmo motivo do link da venda: quem lê a anotação no
                  # chamado quer chegar à CO, não copiar o número dela.
                  else Markup(_('CO %(link)s drafted from this conversation: '
                                '%(count)s line(s).')) % {
                      'link': settlement._get_html_link(),
                      'count': len(lines)}),
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
