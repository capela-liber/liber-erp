# -*- coding: utf-8 -*-

import logging
import re
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import olist_client

_logger = logging.getLogger(__name__)

# Fuso FIXO, nunca o do usuário: num cron o `tz` do usuário é vazio e cai em
# UTC calado - foi o que datou um pedido no dia seguinte e o fez sumir dos
# filtros do Olist (NOTES.md §6-quater).
OLIST_TZ = pytz.timezone('America/Sao_Paulo')

# Olist "situacao" codes. Use the code, never descricao_situacao: the
# description is Portuguese prose and will change; the code will not.
SIT_PENDENTE = '1'
SIT_CANCELADA = '3'
SIT_AUTORIZADA = '6'
SIT_EMITIDA_DANFE = '7'


class OlistAccount(models.Model):
    """One Olist/Tiny account, bound to one Odoo company.

    Deliberately one record per account rather than a single global setting:
    the group runs several companies, each with its own Olist account, and the
    binding company <-> token is what lets a note prove which company it belongs
    to instead of being filed under whoever ran the sync.
    """
    _name = 'olist.account'
    _description = "Conta Olist"
    _order = 'name'

    name = fields.Char(
        string="Nome", required=True,
        help="Rótulo livre, normalmente o nome do selo.")
    company_id = fields.Many2one(
        'res.company', string="Empresa", required=True,
        default=lambda self: self.env.company,
        help="A empresa do Odoo a que esta conta Olist pertence. Uma nota só é "
             "importada se o XML dela nomear o CNPJ desta empresa.")
    token = fields.Char(
        string="Token da API v2", required=True, groups='base.group_system',
        help="Olist ERP > Extensões > Token API. Dá acesso de ESCRITA à conta "
             "fiscal: trate como senha e troque se vazar.")
    active = fields.Boolean(string="Ativa", default=True)
    read_only = fields.Boolean(
        string="Somente leitura", default=True,
        help="Ligado, este módulo NUNCA escreve no Olist: lê o catálogo, lê os "
             "saldos, mostra a divergência — e para aí.\n"
             "É o que permite instalar num banco de ensaio (o `dev` é cópia do "
             "prod) com o token de VERDADE e conferir a comparação sem risco "
             "nenhum: não existe token de homologação no Olist, a conta é uma "
             "só. Desligar é a decisão de deixar a sincronia escrever.")
    create_missing_products = fields.Boolean(
        string="Criar produto que falta no Odoo", default=False,
        help="Desligado, o espelho do catálogo apenas CASA por ISBN e guarda o "
             "id interno do Olist; código que não existe no Odoo é contado e "
             "ignorado.\n"
             "Ligar isto faz o Olist criar produto no Odoo — o contrário do "
             "desenho, em que o Odoo é o razão e o Olist é o adaptador. Serve "
             "para semear um banco de ensaio vazio, não para uma base com "
             "catálogo de verdade: num ISBN que não casa por erro de dígito, o "
             "que nasce é um livro duplicado.")
    stock_reserve = fields.Integer(
        string="Margem de segurança (livros)", default=0,
        help="Quantos exemplares NUNCA são oferecidos ao Olist. O saldo enviado "
             "é o estoque do armazém MENOS esta margem, com piso em zero — "
             "abaixo dela o livro sai como esgotado em vez de ser vendido.\n"
             "Existe porque a contagem erra: entre a última conferência e a "
             "venda no marketplace há devolução no balcão, exemplar avariado e "
             "livro que saiu sem baixa. Vender o último exemplar de um número "
             "que talvez esteja errado é o que gera cancelamento de pedido.\n"
             "Por conta, e portanto por empresa: cada selo escolhe a sua.")
    last_sync = fields.Datetime("Notas lidas em", readonly=True, copy=False)
    last_stock_push = fields.Datetime("Estoque enviado em", readonly=True,
                                      copy=False)
    last_catalogue_pull = fields.Datetime("Catálogo lido em", readonly=True,
                                          copy=False)
    last_stock_pull = fields.Datetime("Saldos lidos em", readonly=True,
                                      copy=False)
    last_orders_pull = fields.Datetime("Pedidos lidos em", readonly=True,
                                       copy=False)
    order_stock_cutoff = fields.Date(
        string="Operar pedidos a partir de",
        help="A data em que o marketplace passa a produzir EFEITO na operação. "
             "Pedidos com data igual ou posterior a ela são registrados por "
             "inteiro na importação: venda confirmada, entrega concluída na "
             "caixa Marketplaces (baixando o estoque do armazém) e fatura "
             "lançada.\n"
             "Anteriores entram como REGISTRO: espelho, rastreabilidade e o "
             "XML arquivado, sem mexer em estoque e sem lançar fatura.\n"
             "Vazio (o padrão) = nenhum pedido produz efeito. É assim que se "
             "começa: o histórico da conta tem cerca de mil pedidos, e importar "
             "para consolidar não pode reescrever o estoque de hoje nem a "
             "contabilidade de um ano atrás.\n"
             "Quando ligar: é isto que fecha o laço com o push de estoque. "
             "Enquanto a venda de marketplace não baixar aqui, o estoque do "
             "Odoo fica alto demais e o push devolve esse número inflado ao "
             "Olist — oferecendo livro já vendido.")
    payment_journal_id = fields.Many2one(
        'account.journal', string="Diário do recebimento",
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        help="Onde o valor da venda de marketplace é lançado como recebido. O "
             "comprador já pagou ao Olist quando o pedido chega aqui: deixar o "
             "título em aberto faria o financeiro cobrar quem já pagou.\n"
             "Use um diário PRÓPRIO do marketplace, não a conta bancária: o "
             "dinheiro está com o Olist até o repasse cair no banco, e é a "
             "reconciliação desse diário contra o repasse que revela as taxas.\n"
             "Vazio: nada é lançado, e a fatura fica em aberto.")
    invoice_auto_post = fields.Boolean(
        string="Lançar a fatura ao criar", default=True,
        help="A nota JÁ foi autorizada pela SEFAZ quando chega aqui — a fatura "
             "não emite nada, ela registra um fato fiscal consumado. Por isso "
             "nasce lançada.\n"
             "Desligue para conferir antes: a fatura fica em rascunho e alguém "
             "lança à mão.")
    marketplace_picking_type_id = fields.Many2one(
        'stock.picking.type', string="Caixa de despacho", readonly=True,
        copy=False,
        help="O tipo de operação das entregas de marketplace (série MP/OUT/). "
             "Nasce sozinho no primeiro pedido importado: o pacote de pessoa "
             "física é outro trabalho — pequeno, um livro, a etiqueta do "
             "Olist — e misturado ao WH/OUT genérico (o palete da Amazon, a "
             "remessa da livraria) ele some. A caixa própria vira um cartão "
             "no Inventário: a fila de embalagem, sem precisar de filtro.")

    order_ids = fields.One2many('olist.order', 'account_id',
                                string="Espelho de pedidos")
    order_count = fields.Integer("Pedidos", compute='_compute_order_count')
    order_detail_coverage = fields.Char(
        "Cobertura do detalhe", compute='_compute_order_count',
        help="Quantos pedidos já tiveram o DETALHE lido — e é o detalhe que "
             "traz os itens. Enquanto não for 100%, a coluna 'Vendido' da tela "
             "de catálogo é um piso, não o total: um livro pode aparecer com "
             "zero apenas porque os pedidos dele ainda não foram abertos.")
    order_pending_count = fields.Integer(
        "Pedidos a importar", compute='_compute_order_count',
        help="Pedidos com detalhe lido, não cancelados e DENTRO do corte, que "
             "ainda não entraram no Odoo. Os anteriores ao corte não contam: "
             "são história para consolidação, não fila de trabalho.")
    channel_ids = fields.One2many('olist.channel', 'account_id',
                                  string="Canais do Olist")
    channel_count = fields.Integer("Canais", compute='_compute_channel_count')
    channel_unmapped_count = fields.Integer(
        "Canais sem mapear", compute='_compute_channel_count',
        help="Canais que o Olist já usou e que ainda não têm canal de venda "
             "da casa. Pedido que chega por eles entra sem canal.")
    panel_ids = fields.One2many('nfe.xml.panel', 'olist_account_id',
                                string="NFes importadas")
    panel_count = fields.Integer("NFes", compute='_compute_panel_count')
    mirror_ids = fields.One2many('olist.product', 'account_id',
                                 string="Espelho do catálogo")
    mirror_count = fields.Integer("Linhas do espelho",
                                  compute='_compute_mirror_count')
    diverge_count = fields.Integer(
        "Divergentes", compute='_compute_mirror_count',
        help="Linhas em que o Olist oferece número diferente do nosso.")

    @api.constrains('company_id', 'active')
    def _check_one_active_account_per_company(self):
        """One active account per company - the binding must be unambiguous.

        Every entry point resolves the account BY COMPANY and takes the first
        hit; with two, which Olist account a company writes to would depend on
        record order. Archived accounts are exempt: keeping an old token on file
        is fine, it just cannot be a candidate.
        """
        for account in self:
            if not account.active:
                continue
            if self.search_count([('company_id', '=', account.company_id.id),
                                  ('id', '!=', account.id)]):
                raise ValidationError(_(
                    "A empresa %s já tem uma conta Olist ativa. Arquive a "
                    "antiga em vez de manter duas: é a empresa que decide em "
                    "qual conta se escreve, então ela precisa apontar para uma "
                    "só.",
                    account.company_id.display_name))

    @api.model_create_multi
    def create(self, vals_list):
        """A caixa de despacho nasce JUNTO com a conta, não no primeiro uso.

        O nascimento preguiçoso enganou na primeira olhada: o depósito abriu o
        Inventário procurando o cartão Marketplaces e ele não existia porque
        nenhum pedido tinha sido importado ainda. Cartão que só aparece depois
        do primeiro pacote é cartão que ninguém encontra na hora de procurar.
        """
        contas = super().create(vals_list)
        for conta in contas:
            conta._marketplace_picking_type()
        return contas

    def _marketplace_picking_type(self):
        """A caixa de despacho do marketplace — get-or-create, no primeiro uso.

        Tudo em sudo(), pela lição do liber_soc_moves: criar o tipo já era
        sudo, mas gravar o resultado na conta não — e o primeiro usuário
        não-administrador a importar um pedido levava AccessError. Não há
        escalada: o valor gravado é o registro que o método acabou de criar.
        """
        self.ensure_one()
        if self.marketplace_picking_type_id:
            return self.marketplace_picking_type_id
        warehouse = self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', self.company_id.id)], limit=1)
        if not warehouse:
            return False
        seq = self.env['ir.sequence'].sudo().create({
            'name': "Marketplaces (%s)" % self.company_id.name,
            'prefix': 'MP/OUT/%(year)s/',
            'padding': 5,
            'company_id': self.company_id.id,
        })
        tipo = self.env['stock.picking.type'].sudo().create({
            'name': "Marketplaces",
            'code': 'outgoing',
            'sequence_id': seq.id,
            'sequence_code': 'MP/OUT',
            'warehouse_id': warehouse.id,
            'company_id': self.company_id.id,
            'default_location_src_id': warehouse.lot_stock_id.id,
            'default_location_dest_id':
                self.env.ref('stock.stock_location_customers').id,
        })
        self.sudo().marketplace_picking_type_id = tipo
        return tipo

    @api.depends('channel_ids.team_id')
    def _compute_channel_count(self):
        for account in self:
            account.channel_count = len(account.channel_ids)
            account.channel_unmapped_count = len(
                account.channel_ids.filtered(lambda c: not c.team_id))

    @api.depends('panel_ids')
    def _compute_panel_count(self):
        for account in self:
            account.panel_count = len(account.panel_ids)

    @api.depends('mirror_ids.state')
    def _compute_mirror_count(self):
        for account in self:
            account.mirror_count = len(account.mirror_ids)
            account.diverge_count = len(account.mirror_ids.filtered(
                lambda l: l.state in ('olist_maior', 'olist_menor')))

    def action_view_panels(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("NFes de %s", self.name),
            'res_model': 'nfe.xml.panel',
            'view_mode': 'list,form',
            'domain': [('olist_account_id', '=', self.id)],
        }

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------
    def action_sync(self):
        """Pull every nota of the account into nfe.xml.panel. Read-only on Olist."""
        for account in self:
            account._sync_notas()
        return True

    @api.model
    def cron_sync(self):
        for account in self.search([]):
            try:
                account._sync_notas()
            except Exception as exc:  # one bad account must not stop the others
                _logger.exception("Olist sync failed for %s: %s", account.name, exc)

    def _sync_notas(self):
        self.ensure_one()
        token = self.sudo().token
        if not token:
            raise UserError(_("A conta Olist %s não tem token da API.",
                              self.name))

        Panel = self.env['nfe.xml.panel'].sudo()
        company_cnpj = re.sub(r'\D', '', self.company_id.partner_id.vat or '')
        if not company_cnpj:
            raise UserError(_(
                "A empresa %s não tem CNPJ. Sem ele não há como provar que uma "
                "nota é dela.", self.company_id.name))

        imported = cancelled = skipped = adopted = 0
        for nota in olist_client.list_notas(token):
            key = nota.get('chave_acesso')
            # No access key means SEFAZ never authorised it (pending, or
            # cancelled before authorisation): there is no XML to fetch and
            # nothing to book.
            if not key:
                continue

            existing = Panel.search([('key', '=', key)], limit=1)

            # A note authorised and LATER cancelled still has a key and an XML,
            # and would otherwise be booked as a good sale: the cancellation
            # lives in a separate event document, never inside the note's XML.
            if nota.get('situacao') == SIT_CANCELADA:
                if existing and not existing.is_cancelled:
                    self._flag_cancelled(existing, nota)
                    cancelled += 1
                continue

            if existing:
                # ADOÇÃO: o painel veio por outro caminho (o legado, um upload)
                # e não sabe que é desta nota do Olist. Sem o carimbo, o pedido
                # do espelho nunca acha o próprio XML — foram 843 assim no prod
                # em 19/08/2026, e é o que trava a consolidação do histórico.
                # Carimbar não muda o documento: só o apresenta ao pedido.
                if not existing.olist_nota_id:
                    existing.write({'olist_nota_id': str(nota['id']),
                                    'olist_account_id': self.id})
                    adopted += 1
                skipped += 1
                continue

            xml = olist_client.get_nota_xml(token, nota['id'])
            if not xml:
                _logger.warning("Olist nota %s: no XML after retries", nota['id'])
                continue

            # The XML must name THIS company. Anything else means the token and
            # the company were mismatched in the configuration - importing it
            # would file real fiscal documents under the wrong company.
            company = Panel._company_from_xml(xml)
            if company != self.company_id:
                _logger.error(
                    "Olist nota %s (key %s) belongs to %s, not to %s - skipped.",
                    nota['id'], key,
                    company.name or _("no known company"), self.company_id.name)
                continue

            panel = Panel._ingest_xml(
                xml, "olist-%s.xml" % nota['id'], company=company, source='olist',
                extra_vals={
                    'olist_account_id': self.id,
                    'olist_nota_id': str(nota['id']),
                })
            if panel:
                imported += 1

        self.last_sync = fields.Datetime.now()
        _logger.info("Olist %s: %s imported, %s cancelled, %s already known "
                     "(%s adopted).",
                     self.name, imported, cancelled, skipped, adopted)
        return {'imported': imported, 'cancelled': cancelled,
                'skipped': skipped, 'adopted': adopted}

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------
    def action_import_products(self):
        """Mirror the Olist catalogue into product.product, keyed by ISBN.

        Olist's product `codigo` is the ISBN-13, which for a book IS its EAN-13,
        so it lands straight in `barcode`: the book's own identity is the join
        key, and there is no mapping table to drift out of sync. Existing
        products are matched and left alone (their price and name are ours).

        By default nothing is CREATED here - see `create_missing_products`. On
        a real catalogue the mirror is a mapping job, not an import: what comes
        back from Olist is an id to remember, and an unmatched ISBN is news to
        look at, not a product to invent.
        """
        self.ensure_one()
        # Pinned to this account's company: the internal id captured below is a
        # company-dependent value, and writing it outside the right company
        # would file this account's ids under whoever happened to run the
        # import.
        Product = self.env['product.product'].with_context(
            allowed_company_ids=[self.company_id.id])
        created = matched = skipped = missing = 0
        for prod in olist_client.list_produtos(self.sudo().token):
            code = (prod.get('codigo') or '').strip()
            if not code:
                skipped += 1
                continue
            # Olist's internal id: not our join key (the ISBN is), but the ONLY
            # key the stock endpoint accepts. Captured here, where we already
            # hold both, so the stock push never has to search for it later.
            olist_id = str(prod['id']) if prod.get('id') else False
            existing = Product.search([('barcode', '=', code)], limit=1)
            if existing:
                # Left otherwise alone (name and price are ours), but backfill
                # the Olist id if we did not have it yet.
                if olist_id and existing.olist_produto_id != olist_id:
                    existing.olist_produto_id = olist_id
                matched += 1
                continue
            if not self.create_missing_products:
                # O caminho normal numa base com catálogo de verdade: o Odoo é
                # o razão, e um ISBN que não casa é notícia (dígito errado,
                # livro de outro selo, produto arquivado) - não motivo para
                # inventar produto.
                missing += 1
                continue
            Product.create({
                'name': prod.get('nome') or code,
                'barcode': code,
                'default_code': code,
                'list_price': float(prod.get('preco') or 0.0),
                'type': 'consu',
                'is_storable': True,
                'olist_produto_id': olist_id,
            })
            created += 1
        _logger.info("Olist %s: %s products created, %s already known, %s sem "
                     "correspondência no Odoo, %s without a code.",
                     self.name, created, matched, missing, skipped)
        return {'created': created, 'matched': matched, 'missing': missing,
                'skipped': skipped}

    # ------------------------------------------------------------------
    # Stock push (bulk + cron) - the write-back the products model performs
    # ------------------------------------------------------------------
    def action_push_stock(self):
        """Button: push stock for every in-Olist product now (manual trigger)."""
        self.ensure_one()
        return self._push_all_stock(interactive=True)

    @api.model
    def cron_push_stock(self):
        """Nightly: push on-hand to Olist for every account. active=False by
        default (see data/olist_cron.xml) - a stock write path is armed by hand,
        never on install."""
        for account in self.search([]):
            try:
                account._push_all_stock(interactive=False)
            except Exception as exc:  # one account must not stop the others
                _logger.exception("Olist stock push failed for %s: %s",
                                  account.name, exc)

    # ------------------------------------------------------------------
    # Espelho do catálogo (leitura) - o que alimenta a tela de comparação
    # ------------------------------------------------------------------
    def action_pull_catalogue(self):
        """Traz o catálogo do Olist para o espelho. Leitura, e barata.

        Seis chamadas (uma por página), não uma por livro: `produtos.pesquisa`
        não devolve saldo, então esta etapa monta as linhas e o saldo entra
        depois - pela janela incremental do cron, ou pelo botão de ler o saldo
        das linhas escolhidas. Separar as duas coisas é o que torna o espelho
        possível de manter sem gastar vinte minutos de cota por atualização.
        """
        self.ensure_one()
        Mirror = self.env['olist.product']
        existentes = {l.olist_id: l for l in Mirror.search(
            [('account_id', '=', self.id)])}
        criados = atualizados = 0
        for prod in olist_client.list_produtos(self.sudo().token):
            olist_id = str(prod.get('id') or '')
            if not olist_id:
                continue
            vals = {
                'codigo': (prod.get('codigo') or '').strip(),
                'name': prod.get('nome') or '',
                'situacao': prod.get('situacao') or '',
            }
            linha = existentes.get(olist_id)
            if linha and linha.match_origin == 'manual' and linha.product_id:
                # Casamento feito por gente NÃO se desfaz aqui. Metade do
                # catálogo do Olist é livro que existe no Odoo com outro ISBN,
                # e casá-los é trabalho de horas: se a releitura do catálogo
                # reescrevesse `product_id` pelo ISBN (que continua não
                # batendo), esse trabalho evaporaria na noite seguinte.
                vals.pop('product_id', None)
            else:
                casado = self._match_product(vals['codigo'])
                vals['product_id'] = casado.id
                vals['match_origin'] = 'isbn' if casado else False
            if linha:
                linha.write(vals)
                atualizados += 1
            else:
                Mirror.create(dict(vals, account_id=self.id, olist_id=olist_id))
                criados += 1
        self.last_catalogue_pull = fields.Datetime.now()
        _logger.info("Olist %s: espelho com %s novos e %s atualizados.",
                     self.name, criados, atualizados)
        return self.env['olist.product']._notificacao(
            _("Catálogo lido"),
            _("%(novos)s novos, %(upd)s atualizados. O saldo vem pelo cron ou "
              "pelo botão 'Ler saldo' das linhas escolhidas.",
              novos=criados, upd=atualizados), 'success')

    def _check_writable(self):
        """Barra qualquer escrita enquanto a conta estiver em somente leitura.

        Uma trava só, no caminho por onde toda escrita passa. Não há ambiente
        de homologação no Olist (a conta é uma só, e virar a chave de ambiente
        derruba a emissão real - §9.2), então o interruptor tem de estar do
        nosso lado, e vem ligado.
        """
        self.ensure_one()
        if self.read_only:
            raise UserError(_(
                "A conta %s está em modo SOMENTE LEITURA: o módulo lê o Olist "
                "e mostra a divergência, mas não escreve. Desligue 'Somente "
                "leitura' na conta quando quiser deixar a sincronia escrever.",
                self.name))

    def _match_product(self, codigo):
        """Produto do Odoo com esse ISBN, na empresa desta conta.

        Só o casamento pelo código de barras — cru e, se falhar, sem os
        separadores: o catálogo do Olist tem código gravado das duas formas
        (`9788587329960` e `978-85-9582-035-7`) e o `barcode` do Odoo é sem.
        Nada de aproximar por nome aqui: um casamento errado neste ponto manda
        o estoque de um livro para outro. Aproximar por título é o trabalho da
        SUGESTÃO, que não casa nada sozinha.
        """
        if not codigo:
            return self.env['product.product']
        Product = self.env['product.product'].with_context(
            allowed_company_ids=[self.company_id.id])
        achado = Product.search([('barcode', '=', codigo)], limit=1)
        if achado:
            return achado
        digitos = re.sub(r'\D', '', codigo)
        if digitos and digitos != codigo:
            return Product.search([('barcode', '=', digitos)], limit=1)
        return achado

    def _find_mirror(self, codigo=None, olist_id=None):
        """A linha do espelho de catálogo deste item. Mesma ordem de chaves.

        Existe para o item do pedido saber a que livro do CATÁLOGO pertence,
        mesmo quando esse livro ainda não tem produto no Odoo — é isso que
        permite dizer "este livro que não casa vendeu 40 exemplares", que é a
        informação que decide o que casar primeiro.
        """
        self.ensure_one()
        Mirror = self.env['olist.product']
        if olist_id:
            linha = Mirror.search([('account_id', '=', self.id),
                                   ('olist_id', '=', str(olist_id))], limit=1)
            if linha:
                return linha
        if codigo:
            digitos = re.sub(r'\D', '', codigo)
            if digitos:
                for linha in Mirror.search([('account_id', '=', self.id),
                                            ('codigo', '!=', False)]):
                    if re.sub(r'\D', '', linha.codigo or '') == digitos:
                        return linha
        return Mirror.browse()

    def _resolve_product(self, codigo=None, olist_id=None):
        """O produto do Odoo para um item do Olist — pela ordem certa de chaves.

        O ESPELHO vem antes do ISBN, e essa ordem é a coisa importante aqui.
        Metade do catálogo do Olist não casa por ISBN (reedição com código
        novo de um lado e cadastro velho do outro), e é por isso que existe o
        casamento à mão. Se cada superfície fosse procurar por ISBN por conta
        própria, esse trabalho serviria só para o estoque: um pedido do mesmo
        livro continuaria travado, e ninguém entenderia por quê.

        O espelho é, portanto, o de-para da integração. A ordem:

        1. `olist_id` — o id interno, chave exata, sem grafia para errar;
        2. `codigo` no espelho, comparado sem separadores;
        3. o ISBN direto no `barcode`, para o que ainda não está espelhado.
        """
        self.ensure_one()
        Mirror = self.env['olist.product']
        if olist_id:
            linha = Mirror.search([('account_id', '=', self.id),
                                   ('olist_id', '=', str(olist_id))], limit=1)
            if linha.product_id:
                return linha.product_id
        if codigo:
            digitos = re.sub(r'\D', '', codigo)
            linhas = Mirror.search([('account_id', '=', self.id),
                                    ('product_id', '!=', False),
                                    ('codigo', '!=', False)])
            for linha in linhas:
                if re.sub(r'\D', '', linha.codigo or '') == digitos:
                    return linha.product_id
        return self._match_product(codigo)

    # ------------------------------------------------------------------
    # Pedidos: o sentido de volta (Olist -> Odoo)
    # ------------------------------------------------------------------
    def _compute_order_count(self):
        Order = self.env['olist.order']
        for account in self:
            total = Order.search_count([('account_id', '=', account.id)])
            lidos = Order.search_count([('account_id', '=', account.id),
                                        ('detalhe_lido_em', '!=', False)])
            account.order_count = total
            account.order_pending_count = Order.search_count(
                [('account_id', '=', account.id), ('state', '=', 'nao_importado')])
            account.order_detail_coverage = "%s de %s (%s%%)" % (
                lidos, total, int(100 * lidos / total) if total else 0)

    def action_read_all_order_details(self):
        """Lê o detalhe de TODOS os pedidos que ainda não têm. Caro.

        Uma chamada por pedido: ~mil pedidos são mais de meia hora de cota.
        Existe porque a coluna "Vendido" da tela de catálogo só vale quando a
        cobertura é alta — decidir o que casar olhando um piso é decidir no
        escuro. É varredura de uma vez, não rotina: o cron mantém em dia daí
        para a frente.
        """
        self.ensure_one()
        pendentes = self.env['olist.order'].search([
            ('account_id', '=', self.id), ('detalhe_lido_em', '=', False)])
        lidos = sum(1 for pedido in pendentes if pedido._read_detail())
        return self.env['olist.order']._notificacao(
            _("Detalhe dos pedidos"),
            _("%(n)s de %(t)s lidos. Cobertura agora: %(c)s",
              n=lidos, t=len(pendentes), c=self.order_detail_coverage),
            'success')

    @api.model
    def _for_current_company(self):
        """A conta Olist da empresa corrente, para os botões das telas de lista.

        As telas de Pedidos e Estoque não sabem de conta nenhuma — quem as abre
        quer "trazer o que o Olist tem", e a conta é detalhe de configuração.
        Resolver aqui, por empresa, é o que evita um seletor de conta em toda
        tela; e sem conta o erro aponta para onde criá-la, em vez de sair
        escolhendo a de outra empresa (a regra do §10.5).
        """
        company = self.env.company
        account = self.search([('company_id', '=', company.id)], limit=1)
        if not account:
            raise UserError(_(
                "A empresa %s não tem conta Olist. Crie uma em "
                "Olist > Configurações > Contas.", company.display_name))
        return account

    def action_pull_orders(self):
        """Varredura BARATA: enche o espelho com a listagem de pedidos.

        Dez chamadas para mil pedidos. O que não vem aqui é o canal de venda —
        ele só existe no detalhe, uma chamada por pedido — e por isso as linhas
        nascem em "Falta ler o detalhe". A tela serve para escolher quais
        detalhar, e o cron faz o resto aos poucos.
        """
        self.ensure_one()
        return self._pull_orders(interactive=True)

    def _pull_orders(self, interactive=False, desde=None):
        self.ensure_one()
        Order = self.env['olist.order']
        token = self.sudo().token
        novos = atualizados = 0
        for dados in olist_client.list_pedidos(token, desde=desde):
            olist_id = str(dados.get('id') or '')
            if not olist_id:
                continue
            vals = {
                'numero': dados.get('numero') or False,
                'data_pedido': self._data_br(dados.get('data_pedido')),
                'situacao': dados.get('situacao') or False,
                'valor': float(dados.get('valor') or 0.0),
                'cliente_nome': dados.get('nome') or False,
                'numero_ecommerce': dados.get('numero_ecommerce') or False,
                # O rastreio vem na LISTAGEM — dez chamadas trazem o de mil
                # pedidos. É o dado mais barato da integração inteira, e o que
                # o atendimento mais pede.
                'codigo_rastreamento': dados.get('codigo_rastreamento') or False,
                'url_rastreamento': dados.get('url_rastreamento') or False,
            }
            existente = Order.search(
                [('account_id', '=', self.id), ('olist_id', '=', olist_id)],
                limit=1)
            if existente:
                # A situação muda com o tempo (Enviado -> Entregue -> Cancelado)
                # e é o único campo da listagem que interessa reescrever.
                existente.write(vals)
                atualizados += 1
            else:
                Order.create(dict(vals, account_id=self.id, olist_id=olist_id))
                novos += 1

        self.last_orders_pull = fields.Datetime.now()
        _logger.info("Olist %s: %s pedidos novos, %s atualizados.",
                     self.name, novos, atualizados)
        if not interactive:
            return {'novos': novos, 'atualizados': atualizados}
        return self.env['olist.order']._notificacao(
            _("Pedidos lidos"),
            _("%(n)s novos, %(a)s atualizados. Selecione linhas e use "
              "'Ler detalhe' para trazer o canal de venda.",
              n=novos, a=atualizados), 'success')

    @staticmethod
    def _data_br(texto):
        """dd/mm/aaaa -> date. O Olist não fala ISO nas listagens."""
        if not texto:
            return False
        try:
            dia, mes, ano = str(texto).split(' ')[0].split('/')
            return fields.Date.to_date("%s-%s-%s" % (ano, mes, dia))
        except (ValueError, TypeError):
            return False

    def _find_team(self, canal):
        """O `crm.team` que já se chama assim, se houver. NÃO cria.

        Serve a uma coisa só: pré-preencher a linha nova do espelho de canais
        quando o nome de lá coincide com um canal de venda que a casa já tem.
        É conveniência, não regra — e por isso o nome inteiro tem de bater.

        Procura inclusive entre os arquivados e os globais: o prod tem
        `Marketplaces`, `eBay` e `Website` guardados, e apontar para o que já
        existe é o contrário de inventar um segundo com o mesmo nome. O
        arquivado NÃO é reativado aqui: quem decide que um canal voltou a
        existir é a casa, não a leitura de uma API.
        """
        self.ensure_one()
        canal = (canal or '').strip()
        if not canal:
            return self.env['crm.team']
        return self.env['crm.team'].with_context(active_test=False).search([
            ('name', '=ilike', canal),
            ('company_id', 'in', [False, self.company_id.id]),
        ], limit=1)

    def _resolve_team(self, canal):
        """O canal de venda da casa para este canal do Olist. NUNCA cria.

        Aqui `crm.team` é canal de clientela, não time de gente — o mesmo
        vocabulário que `sale.order.team_id` e a ficha do cliente já usam na
        casa (liber_partner_commercial).

        A resposta sai do ESPELHO DE CANAIS (`olist.channel`), e só dele. Até
        18/08/2026 este método casava por nome e, falhando, criava um
        `crm.team` com o nome que o Olist tivesse mandado: foi assim que
        nasceu o canal 98 "Hedra" da EdLab Press no staging, único ativo da
        empresa enquanto os canais legítimos estavam arquivados. Uma leitura
        de API não decide a taxonomia comercial da casa.

        Vazio é resposta legítima: canal ainda não mapeado devolve nada, e o
        pedido entra sem canal em vez de estourar. A pendência fica visível na
        tela de Canais do Olist, que é onde ela se resolve.
        """
        self.ensure_one()
        canal = (canal or '').strip()
        if not canal:
            return self.env['crm.team']
        return self.env['olist.channel']._find_or_create(self, canal).team_id

    def action_map_channels(self):
        """Abre o espelho de canais, registrando antes o que os pedidos já disseram.

        Não cria canal de venda nenhum — registra no espelho os nomes que o
        Olist usou e leva a pessoa à tela onde o par se escolhe. É o gêmeo do
        "Map units from orders" do módulo da Amazon: descobrir é do módulo,
        decidir é da casa.
        """
        self.ensure_one()
        Channel = self.env['olist.channel']
        for pedido in self.env['olist.order'].search([
                ('account_id', '=', self.id), ('canal', '!=', False)]):
            Channel._find_or_create(self, pedido.canal, pedido.plataforma)
        return {
            'type': 'ir.actions.act_window',
            'name': _("Canais do Olist — %s", self.name),
            'res_model': 'olist.channel',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id},
        }

    def _resolve_partner(self, doc, nome, email, canal):
        """O contato do Odoo para este comprador.

        Com CPF/CNPJ, o comprador é uma pessoa de verdade e vira ficha própria,
        casada pelo documento. Sem documento, cai num contato genérico do canal
        — e isso não é desleixo: o Mercado Livre com frequência não entrega o
        dado do comprador, e inventar uma ficha por apelido de marketplace enche
        o cadastro de gente que não existe e nunca mais se concilia.

        CNPJ manda ser empresa (14 dígitos), CPF manda ser pessoa — a regra da
        casa, aplicada só na criação.

        A busca é por `vat_digits`, não por `vat`: o cadastro guarda o documento
        pontuado (e esta base tem até hífen invisível no meio), o Olist manda
        `171.037.078-55`, e comparar as duas grafias cruas nunca acerta — o que
        criaria uma ficha nova para um cliente que já existe. `vat_digits` é o
        campo que o próprio import de XML já usa para achar a contraparte.
        """
        self.ensure_one()
        Partner = self.env['res.partner']
        digitos = Partner._vat_digits(doc)
        if digitos:
            achado = Partner.search([('vat_digits', '=', digitos)], limit=1)
            if achado:
                return achado
            return Partner.create({
                'name': nome or doc,
                # Grava como o Olist mandou: a normalização é do `vat_digits`,
                # e guardar o original preserva o que a fonte disse.
                'vat': doc or digitos,
                'email': email or False,
                'is_company': len(digitos) == 14,
                'company_id': False,
            })
        rotulo = _("Clientes %s", canal or _("Olist"))
        generico = Partner.search([('name', '=', rotulo)], limit=1)
        if generico:
            return generico
        return Partner.create({'name': rotulo, 'is_company': True,
                               'company_id': False})

    def action_open_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Pedidos do Olist — %s", self.name),
            'res_model': 'olist.order',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id},
        }

    @api.model
    def cron_pull_orders(self):
        """Diário: relê a janela recente da listagem e detalha o que falta.

        Só a janela: reler mil pedidos todo dia é cota jogada fora, e pedido
        antigo não muda mais. O detalhe é buscado apenas para as linhas que
        ainda não o têm, com teto por rodada — a cota é dividida com o ERP e
        os marketplaces.
        """
        for account in self.search([]):
            try:
                desde = False
                if account.last_orders_pull:
                    desde = (account.last_orders_pull - timedelta(days=7)
                             ).strftime('%d/%m/%Y')
                account._pull_orders(interactive=False, desde=desde)
                faltando = self.env['olist.order'].search([
                    ('account_id', '=', account.id),
                    ('detalhe_lido_em', '=', False),
                ], limit=50)
                for pedido in faltando:
                    pedido._read_detail()
            except Exception as exc:  # uma conta ruim não para as outras
                _logger.exception("Olist: leitura de pedidos falhou em %s: %s",
                                  account.name, exc)

    def action_read_all_saldos(self):
        """Lê o saldo de TODAS as linhas do espelho. Caro: ~1 chamada por livro."""
        self.ensure_one()
        linhas = self.env['olist.product'].search([('account_id', '=', self.id)])
        lidas = sum(1 for linha in linhas if linha._read_saldo())
        self.last_stock_pull = fields.Datetime.now()
        return self.env['olist.product']._notificacao(
            _("Saldos lidos"), _("%s linha(s).", lidas), 'success')

    @api.model
    def cron_pull_stock_window(self):
        """4x ao dia: só o que MUDOU no Olist desde a última leitura.

        A releitura por janela do módulo da Amazon, aqui: uma chamada devolve
        os produtos cujo saldo se mexeu (venda no marketplace, ajuste na mão
        de lá). O espelho envelhece pouco e a cota quase não é tocada.

        Ela nunca ESCREVE - nem quando a conta já saiu do somente-leitura.
        Manter o espelho fresco e decidir sincronizar são dois atos, e só o
        segundo é de gente.
        """
        for account in self.search([]):
            try:
                account._pull_stock_window()
            except Exception as exc:  # uma conta ruim não para as outras
                _logger.exception("Olist janela de estoque falhou em %s: %s",
                                  account.name, exc)

    # O Olist recusa janela maior que isto: "Somente podem ser listados os
    # registros de atualização dos últimos 30 dias". Descoberto em 18/08/2026
    # tentando semear o espelho com uma janela de dez anos.
    JANELA_MAXIMA_DIAS = 30

    def _pull_stock_window(self):
        self.ensure_one()
        desde = self.last_stock_pull or (
            fields.Datetime.now() - timedelta(days=2))
        # Cron parado por mais de um mês pediria uma janela que o Olist
        # recusa, e a recusa derrubaria a rodada inteira. O teto é dele.
        limite = fields.Datetime.now() - timedelta(days=self.JANELA_MAXIMA_DIAS)
        if desde < limite:
            desde = limite
        # O Olist fala em horário local; `last_stock_pull` é UTC. Converter -
        # e com fuso fixo, nunca o do usuário, que num cron é vazio e cai em
        # UTC calado (a lição do §6-quater).
        local = pytz.utc.localize(desde).astimezone(OLIST_TZ)
        mudados = olist_client.list_atualizacoes_estoque(
            self.sudo().token, local.strftime("%d/%m/%Y %H:%M:%S"))
        Mirror = self.env['olist.product']
        tocadas = 0
        for prod in mudados:
            linha = Mirror.search([('account_id', '=', self.id),
                                   ('olist_id', '=', str(prod.get('id')))],
                                  limit=1)
            if not linha:
                continue
            linha.write({
                'saldo_olist': float(prod.get('saldo') or 0.0),
                'saldo_olist_date': fields.Datetime.now(),
            })
            tocadas += 1
        self.last_stock_pull = fields.Datetime.now()
        _logger.info("Olist %s: janela trouxe %s produto(s) alterados.",
                     self.name, tocadas)
        return tocadas

    def action_open_mirror(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Estoque: Olist × Odoo (%s)", self.name),
            'res_model': 'olist.product',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id,
                        'search_default_diverge': 1},
        }

    def _push_all_stock(self, interactive=False):
        """Push on-hand to Olist for every product that IS in Olist, here.

        The `olist_produto_id` filter is the whole "do not create products in
        Olist" rule in one line: a product Odoo knows but Olist does not is
        simply skipped, never sent. And because that id is company-dependent,
        the same filter also means "in THIS company's Olist account" - a book
        mirrored only for another company is not swept up here.

        The whole search and every push run pinned to this account's company
        (see product_template._in_olist_company): on-hand must mean on hand in
        this company, not the group's total.
        """
        self.ensure_one()
        self._check_writable()
        Template = self.env['product.template']
        products = Template._in_olist_company(self.company_id).search([
            ('olist_produto_id', '!=', False),
            ('company_id', 'in', [False, self.company_id.id]),
        ])

        ok, errors = 0, []
        for product in products:
            try:
                status, detail = product._push_stock_to_olist(self)
            except Exception as exc:  # never let one product abort the sweep
                status, detail = 'ERR', str(exc)
            if status == 'OK':
                ok += 1
            else:
                errors.append("%s: %s" % (
                    product.default_code or product.display_name, detail))

        self.last_stock_push = fields.Datetime.now()
        _logger.info("Olist %s: stock pushed for %s products, %s error(s).",
                     self.name, ok, len(errors))
        if not interactive:
            return {'ok': ok, 'errors': len(errors)}

        msg = _("%(ok)s produto(s) atualizados, %(err)s com erro.",
                ok=ok, err=len(errors))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Olist: estoque"),
                'message': msg,
                'type': 'success' if not errors else 'warning',
                'sticky': bool(errors),
            },
        }

    def _flag_cancelled(self, panel, nota):
        """Mark an already-imported NFe as cancelled, on the API's authority.

        The proper source is the procEventoNFe document, which carries the
        protocol and the justification - the v2 API does not serve it, so those
        stay empty and the event is stamped as coming from the API. The money
        figure is what matters here: an uncancelled cancelled note overstates
        revenue.
        """
        self.ensure_one()
        Event = self.env['nfe.xml.cancel.event'].sudo()
        if not Event.search_count([('key', '=', panel.key)]):
            Event.create({
                'key': panel.key,
                'nfe_id': panel.id,
                'desc_evento': _("Cancelada pela API do Olist (sem XML de "
                                 "evento)"),
                'company_id': self.company_id.id,
            })
        panel.write({'is_cancelled': True, 'status': 'cancelled'})
        panel.message_post(body=_(
            "Marcada como cancelada pela API do Olist (nota %s).",
            nota.get('id')))
