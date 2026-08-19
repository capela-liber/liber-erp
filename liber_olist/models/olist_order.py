# -*- coding: utf-8 -*-

import json
import logging
import re
import time

from markupsafe import Markup

from odoo import _, api, fields, models, modules, tools
from odoo.exceptions import UserError

from . import olist_client

_logger = logging.getLogger(__name__)


def so_digitos(valor):
    """Só os dígitos — ISBN e CPF/CNPJ chegam formatados de jeitos diferentes.

    O item do pedido traz o ISBN COM hífen (`978-85-7715-835-5`) enquanto o
    catálogo traz sem, e o `barcode` do Odoo é sem. Comparar as duas grafias
    cruas perde livro que existe dos dois lados.
    """
    return re.sub(r'\D', '', valor or '')


class OlistOrder(models.Model):
    """O espelho do pedido do Olist — o que ELES dizem que foi vendido.

    Mesma disciplina do espelho de catálogo (`olist.product`): isto não é o
    pedido do Odoo, é a leitura do pedido de lá, com a data em que foi lida.
    Guardado, dá para filtrar, conferir e escolher o que importar; calculado
    na hora, não daria tela nenhuma.

    A leitura vem em DOIS passos, e a divisão não é preguiça: a listagem custa
    uma chamada por 100 pedidos e traz quase tudo, mas o **canal de venda** só
    existe no detalhe, uma chamada por pedido. Varrer ~1000 detalhes é mais de
    meia hora de cota — preço que não se paga para abrir uma tela. Por isso:
    varredura barata enche o espelho, e o detalhe se busca sobre as linhas que
    a pessoa escolheu (ou pelo cron, aos poucos).

    Ver liber_olist/NOTES.md §12.
    """
    _name = 'olist.order'
    _inherit = ['mail.thread']
    _description = "Espelho de pedido do Olist"
    _order = 'data_pedido desc, numero desc'
    _rec_name = 'numero'

    account_id = fields.Many2one(
        'olist.account', string="Conta", required=True, ondelete='cascade',
        index=True)
    company_id = fields.Many2one(
        related='account_id.company_id', store=True, index=True)

    olist_id = fields.Char("ID Olist", required=True, index=True)
    numero = fields.Char("Número", index=True)
    data_pedido = fields.Date("Data do pedido", index=True)
    situacao = fields.Char("Situação no Olist")
    valor = fields.Float("Valor no Olist")

    # --- o cliente, como o Olist o descreve -----------------------------
    cliente_nome = fields.Char("Cliente")
    cliente_doc = fields.Char("CPF/CNPJ")
    cliente_email = fields.Char("E-mail")
    cliente_uf = fields.Char("UF")

    # --- o canal (o bloco `ecommerce`) ----------------------------------
    canal = fields.Char(
        "Canal no Olist", index=True,
        help="`ecommerce.nomeEcommerce` — o nome do marketplace/loja como o "
             "Olist o informa. Guardado como texto, cru: é o que ELES dizem. "
             "O canal do Odoo é o campo ao lado.")
    numero_ecommerce = fields.Char("Nº no marketplace")
    team_id = fields.Many2one(
        'crm.team', string="Canal de Venda",
        help="O canal do Odoo (crm.team) correspondente. Aqui `crm.team` é "
             "canal de clientela, não time de gente — mesmo vocabulário que "
             "`sale.order.team_id` já usa na casa.")

    # --- a plataforma, que a API diz e o painel não precisa dizer ------
    plataforma = fields.Char(
        "Plataforma", index=True,
        help="`intermediador.nome` — a plataforma por trás do canal: Shopify, "
             "Mercado Livre. O canal é o nome da loja ('Hedra'); a plataforma "
             "é onde ela roda. São coisas diferentes e a API devolve as duas.")
    marcadores = fields.Char(
        "Marcadores", help="As etiquetas do pedido no Olist (ex.: '1ª venda').")

    # --- entrega: o que o Olist sabe do pacote -------------------------
    # Vem na LISTAGEM, não no detalhe — dez chamadas trazem o rastreio de mil
    # pedidos. É o dado mais barato da integração e o que o atendimento mais
    # pede quando o comprador pergunta "cadê meu livro?".
    codigo_rastreamento = fields.Char("Código de rastreio", index='btree_not_null')
    url_rastreamento = fields.Char("Link de rastreio")
    transportadora = fields.Char("Transportadora")
    forma_frete = fields.Char("Serviço de frete")
    data_envio = fields.Date("Enviado em")
    data_prevista = fields.Date("Previsão de entrega")
    data_entrega = fields.Date("Entregue em")
    data_faturamento = fields.Date("Faturado em")
    forma_envio = fields.Char("Modalidade de envio")
    deposito = fields.Char("Depósito no Olist")
    entrega_cidade = fields.Char("Cidade de entrega")
    entrega_uf = fields.Char("UF de entrega")
    valor_frete = fields.Float("Valor do frete")

    xml_status = fields.Selection([
        ('sem_nota', "Sem nota no Olist"),
        ('sem_xml', "Nota emitida, XML não arquivado"),
        ('arquivado', "XML arquivado"),
    ], string="Situação do XML", compute='_compute_nfe_panel', store=True,
        index=True,
        help="Três estados, e a diferença entre os dois últimos é a que "
             "importa: 'nota emitida, XML não arquivado' quer dizer que o "
             "Olist emitiu e nós ainda não puxamos o documento — o pedido "
             "está fiscalmente resolvido lá e sem lastro aqui.")

    id_nota_fiscal = fields.Char("ID da nota no Olist", index='btree_not_null')
    nfe_panel_id = fields.Many2one(
        'nfe.xml.panel', string="NFe", compute='_compute_nfe_panel',
        store=True,
        help="A nota deste pedido, se já tiver entrado pelo sync de XML. O "
             "vínculo é o id da nota no Olist, que já gravamos no painel.")

    partner_id = fields.Many2one('res.partner', string="Contato no Odoo")
    invoice_id = fields.Many2one(
        'account.move', string="Fatura no Odoo", index='btree_not_null',
        copy=False,
        help="A fatura montada a partir do XML da nota. Ela não emite nada: "
             "quando chega aqui, a SEFAZ já autorizou o documento e o que se "
             "faz é registrar o fato no razão.")
    sale_order_id = fields.Many2one('sale.order', string="Pedido no Odoo",
                                    index='btree_not_null')
    line_ids = fields.One2many('olist.order.line', 'order_id', string="Itens")

    detalhe_lido_em = fields.Datetime("Detalhe lido em", readonly=True)
    detalhe_pendente = fields.Boolean(
        "Na fila de leitura", index='btree_not_null', copy=False,
        help="Marcado para o cron ler o detalhe de madrugada. A leitura na "
             "tela é síncrona e o navegador (ou o túnel na frente dele) "
             "derruba requisição longa: ler 80 pedidos leva ~2,5 min e não "
             "chega ao fim. O que passa do lote entra nesta fila.")
    raw_json = fields.Text(
        "Payload cru", readonly=True,
        help="A resposta do Olist como veio. Nunca editada e nunca lida por "
             "lógica de negócio: é cache auditável de rede, para conferir "
             "depois o que exatamente chegou.")

    state = fields.Selection([
        ('sem_detalhe', "Falta ler o detalhe"),
        ('cancelado', "Cancelado no Olist"),
        ('anterior_corte', "Anterior ao corte"),
        # O rótulo é ação, não descrição: "A importar" é o mesmo nome do
        # filtro padrão e do contador da conta — o operador lê o badge
        # amarelo e sabe o que fazer, sem traduzir "não importado" de cabeça.
        ('nao_importado', "A importar"),
        ('importado', "Importado"),
    ], string="Situação", compute='_compute_state', store=True, index=True)

    a_despachar = fields.Boolean(
        "A despachar", compute='_compute_a_despachar', store=True, index=True,
        help="Nota emitida e a CASA ainda não concluiu a entrega. A régua é "
             "nossa, não do Olist: quando a etiqueta nasce o Olist marca "
             "'Enviado' e lava as mãos — o pacote continua na prateleira até "
             "a coleta. Só sai daqui quando o funcionário valida a entrega no "
             "Odoo (ou quando o Olist prova que saiu: Entregue).")

    itens_sem_produto = fields.Integer(
        "Livros não localizados", compute='_compute_itens_sem_produto',
        store=True, index='btree_not_null',
        help="Quantos itens deste pedido não têm produto casado no Odoo. "
             "Enquanto for maior que zero, o pedido NÃO importa — entraria "
             "com menos livros do que teve, e o número ficaria errado para "
             "sempre sem ninguém perceber.")

    divergencia_valor = fields.Float(
        "Divergência de valor", compute='_compute_state', store=True,
        help="Valor no Olist menos o total do pedido no Odoo. Frete e "
             "desconto do Olist não viram linha aqui, então uma diferença "
             "pequena é esperada — e fica visível em vez de silenciosa.")

    _olist_id_account_uniq = models.Constraint(
        'unique(account_id, olist_id)',
        "Este pedido do Olist já está espelhado nesta conta.")

    @api.depends('id_nota_fiscal', 'account_id')
    def _compute_nfe_panel(self):
        Panel = self.env['nfe.xml.panel']
        for pedido in self:
            painel = False
            tem_nota = bool(pedido.id_nota_fiscal
                            and pedido.id_nota_fiscal != '0')
            if tem_nota:
                painel = Panel.search([
                    ('olist_nota_id', '=', pedido.id_nota_fiscal),
                    ('olist_account_id', '=', pedido.account_id.id),
                ], limit=1)
            pedido.nfe_panel_id = painel or False
            if not tem_nota:
                pedido.xml_status = 'sem_nota'
            elif painel:
                pedido.xml_status = 'arquivado'
            else:
                pedido.xml_status = 'sem_xml' 

    @api.depends('line_ids.product_id')
    def _compute_itens_sem_produto(self):
        for pedido in self:
            pedido.itens_sem_produto = len(
                pedido.line_ids.filtered(lambda l: not l.product_id))

    @api.depends('sale_order_id', 'sale_order_id.amount_total', 'valor',
                 'situacao', 'detalhe_lido_em', 'data_pedido',
                 'account_id.order_stock_cutoff')
    def _compute_state(self):
        for pedido in self:
            pedido.divergencia_valor = 0.0
            corte = pedido.account_id.order_stock_cutoff
            if pedido.sale_order_id:
                pedido.state = 'importado'
                pedido.divergencia_valor = (
                    pedido.valor - pedido.sale_order_id.amount_total)
            elif (pedido.situacao or '').strip().lower() == 'cancelado':
                # Cancelado no Olist não é pendência: não se importa, e não
                # deve ficar pesando na fila do que falta trazer.
                pedido.state = 'cancelado'
            elif corte and pedido.data_pedido and pedido.data_pedido < corte:
                # Anterior ao corte é história, não trabalho: sai da fila
                # "A importar" e da frente do operador — importar continua
                # possível (consolidação é ato deliberado, por seleção), e é
                # por isso que a situação tem nome próprio em vez de sumir num
                # filtro. Vence até o "falta ler o detalhe": o detalhe desses
                # é assunto do cron, não de gente. Sem corte na conta, nada é
                # marcado — o vocabulário só existe onde a operação começou.
                pedido.state = 'anterior_corte'
            elif not pedido.detalhe_lido_em:
                pedido.state = 'sem_detalhe'
            else:
                pedido.state = 'nao_importado'

    @api.depends('state', 'situacao', 'id_nota_fiscal',
                 'sale_order_id.picking_ids.state')
    def _compute_a_despachar(self):
        for pedido in self:
            pendente = (
                pedido.state not in ('anterior_corte', 'cancelado')
                and bool(pedido.id_nota_fiscal)
                and pedido.id_nota_fiscal != '0'
                # O que o Olist PROVA que saiu não é a despachar — mas
                # "Enviado" não prova nada: é o nascimento da etiqueta.
                and (pedido.situacao or '').strip()
                not in self.SITUACOES_FORA_DA_CASA)
            if pendente and pedido.sale_order_id:
                saidas = pedido.sale_order_id.picking_ids.filtered(
                    lambda p: p.state != 'cancel')
                # Importado: quem responde é a entrega da casa. Sem nenhuma
                # saída (importou fora do corte) não há o que despachar por
                # aqui — o pacote daquele é assunto do histórico.
                pendente = bool(saidas) and any(
                    p.state != 'done' for p in saidas)
            pedido.a_despachar = pendente

    # ------------------------------------------------------------------
    # Ler o Olist (leitura)
    # ------------------------------------------------------------------
    def action_pull_from_olist(self):
        """Traz os pedidos do Olist para esta tela. Dez chamadas, só leitura.

        Este é o botão que precisa aparecer com a lista VAZIA — é a primeira
        coisa que se faz aqui, e é quando ele mais serve. Por isso vai com
        `display="always"` na view: sem isso o Odoo o guarda no bloco de ações
        de seleção, que só aparece com linhas marcadas.

        E NÃO leva `@api.model`, por mais que pareça: num botão o cliente web
        manda os ids como primeiro argumento, e o `call_kw` só os retira do
        `args` quando o método NÃO é `@api.model` (odoo/service/model.py:82).
        Com o decorador, a lista de ids sobra como argumento posicional e a
        tela quebra com "takes 1 positional argument but 2 were given" -- o
        que um teste que chame o método direto no modelo não pega.
        """
        conta = self.env['olist.account']._for_current_company()
        return conta._pull_orders(interactive=True)

    def action_fetch_xml(self):
        """Puxa e arquiva o XML da nota DESTES pedidos. Uma chamada por linha.

        O caminho direto que faltava. Até aqui o XML só chegava pela varredura
        da conta inteira (`action_sync`), que percorre as ~1000 notas para
        achar as que faltam — cara e desproporcional quando a pergunta é "traga
        o XML deste pedido aqui", e o pedido já sabe o id da nota.

        Não reimplementa nada: usa o mesmo `_ingest_xml` do upload manual, com
        a mesma deduplicação por chave de acesso e a mesma prova de empresa
        pelo CNPJ do emitente. Rodar duas vezes não duplica.
        """
        trazidos, jah, erros = 0, 0, []
        for pedido in self:
            status, detalhe = pedido._fetch_xml()
            if status == 'OK':
                trazidos += 1
            elif status == 'JA':
                jah += 1
            else:
                erros.append("%s: %s" % (pedido.numero or pedido.olist_id, detalhe))
        if not erros:
            return False
        return self._notificacao(
            _("Busca parcial"),
            _("%(n)s trazidos, %(e)s sem XML:\n%(lista)s",
              n=trazidos, e=len(erros), lista="\n".join(erros[:8])),
            'warning', sticky=True)

    def _fetch_xml(self):
        """(status, detalhe) — 'OK', 'JA' (já arquivado) ou 'ERR'."""
        self.ensure_one()
        if not self.id_nota_fiscal or self.id_nota_fiscal == '0':
            return 'ERR', _("o Olist ainda não emitiu nota para este pedido")
        if self.nfe_panel_id:
            return 'JA', _("já arquivado")

        Panel = self.env['nfe.xml.panel'].sudo()
        xml = olist_client.get_nota_xml(self.account_id.sudo().token,
                                        self.id_nota_fiscal)
        if not xml:
            # Ausência aqui é ambígua: nota pendente (sem chave, logo sem XML)
            # ou cota estourada. O cliente já insiste antes de desistir, então
            # chegar aqui quer dizer "não veio mesmo" — e isso se diz, não se
            # confunde com "não existe".
            return 'ERR', _("nota sem XML (pendente no Olist, ou cota estourada)")

        # A empresa sai do CNPJ do emitente, nunca de quem chamou: é o que
        # impede uma nota de ser arquivada na empresa errada quando há mais de
        # uma conta alimentando o mesmo banco.
        company = Panel._company_from_xml(xml)
        if company != self.company_id:
            return 'ERR', _(
                "a nota é da empresa %s, não de %s",
                company.name or _("nenhuma conhecida"), self.company_id.name)

        painel = Panel._ingest_xml(
            xml, "olist-%s.xml" % self.id_nota_fiscal, company=company,
            source='olist',
            extra_vals={'olist_account_id': self.account_id.id,
                        'olist_nota_id': str(self.id_nota_fiscal)})
        # E LÊ na hora. A ingestão só arquiva o arquivo: quem extrai itens,
        # valor e CFOP é o `action_import_xml_file`, que normalmente roda pelo
        # cron do liber_nfe_xml. Esperar o cron significaria arquivar o XML e
        # não conseguir faturar em seguida -- foi o que aconteceu no pedido
        # 1006 em 17/08/2026: "o XML não tem itens lidos", com a nota ali ao
        # lado.
        if painel:
            painel.action_import_xml_file()
        # O painel novo casa por `olist_nota_id`; o campo é calculado e
        # armazenado, então precisa ser recomputado para a tela mudar de estado.
        self.invalidate_recordset(['nfe_panel_id', 'xml_status'])
        self.modified(['id_nota_fiscal'])
        _logger.info("Olist: XML da nota %s arquivado (pedido %s)",
                     self.id_nota_fiscal, self.numero)
        return 'OK', _("arquivado")

    # Quantos cabem numa requisição. A ~1,8s por pedido, 25 dão ~45s e sobra
    # folga para o teto de ~100s que o túnel impõe. Passar disso não é
    # otimismo, é perder o lote inteiro: em 17/08/2026 uma leitura de 80
    # estourou o tempo e o rollback desfez os 80.
    LOTE_INTERATIVO = 25

    def _grava_ja(self):
        """Commit por registro — menos dentro de teste, onde é proibido.

        O framework de teste bloqueia commit (quebraria o rollback que isola
        cada caso), e é o mesmo motivo pelo qual o §10.3 recusou commit no
        push de estoque. Aqui ele é necessário: sem gravar a cada pedido, um
        estouro de tempo desfaz tudo o que já foi lido, e foi assim que 80
        leituras viraram zero em 17/08/2026.
        """
        if tools.config['test_enable'] or modules.module.current_test:
            return False
        self.env.cr.commit()
        return True

    def action_read_detail(self):
        """Lê o detalhe das linhas escolhidas — as que couberem agora.

        O que passa do lote vai para a FILA do cron, em vez de derrubar a
        requisição. E cada leitura é gravada na hora: se o tempo estourar
        mesmo assim, o que já foi lido está salvo — o rollback de uma
        transação única é o que fez 80 leituras virarem zero.
        """
        alvo, adiados = self, self.browse()
        if len(self) > self.LOTE_INTERATIVO:
            alvo = self[:self.LOTE_INTERATIVO]
            adiados = self[self.LOTE_INTERATIVO:]

        lidos = 0
        for pedido in alvo:
            if pedido._read_detail():
                lidos += 1
                # Grava já: o próximo pedido pode ser o que estoura o tempo.
                pedido._grava_ja()

        if not adiados:
            # Sem ação de retorno: o cliente web recarrega o registro sozinho,
            # em silêncio (view_button_hook.js: onClose -> reload). O `reload`
            # explícito recarrega a PÁGINA e é ele que pisca a tela.
            return False
        adiados.write({'detalhe_pendente': True})
        adiados._grava_ja()
        return self._notificacao(
            _("Lido o que cabia; o resto ficou na fila"),
            _("%(n)s lidos agora. Os outros %(f)s entraram na fila e o cron "
              "os lê de madrugada — a leitura na tela não aguenta mais que "
              "isso sem estourar o tempo.", n=lidos, f=len(adiados)),
            'warning', sticky=True)

    def action_queue_detail(self):
        """Põe as linhas escolhidas na fila, sem ler nada agora."""
        self.write({'detalhe_pendente': True})
        return self._notificacao(
            _("Na fila"),
            _("%s pedido(s) serão lidos pelo cron das 2h.", len(self)),
            'success', recarregar=False)

    @api.model
    def cron_read_details(self, minutos=60):
        """De madrugada, esvazia a fila — com relógio na mão.

        O orçamento de tempo não é zelo: o backup do Mac roda às 03:30, e uma
        varredura de mil pedidos leva meia hora. Começando às 02:00 e parando
        no teto, ela nunca alcança o backup.

        Commit por pedido, porque cron longo que morre no meio sem gravar é
        trabalho jogado fora — e a releitura de tudo custa a cota de novo.
        """
        limite = time.monotonic() + minutos * 60
        pendentes = self.search([('detalhe_pendente', '=', True)])
        if not pendentes:
            # Fila vazia: aproveita a janela para os que nunca foram lidos.
            pendentes = self.search([('detalhe_lido_em', '=', False),
                                     ('situacao', '!=', 'Cancelado')],
                                    order='data_pedido desc')
        lidos = 0
        for pedido in pendentes:
            if time.monotonic() > limite:
                _logger.info("Olist: janela de leitura esgotada com %s lidos; "
                             "%s continuam na fila.", lidos,
                             len(pendentes) - lidos)
                break
            try:
                if pedido._read_detail():
                    lidos += 1
            except Exception as exc:  # um pedido ruim não para a fila
                _logger.exception("Olist: falha lendo o pedido %s: %s",
                                  pedido.numero, exc)
            pedido.detalhe_pendente = False
            pedido._grava_ja()
        _logger.info("Olist: cron de detalhe leu %s pedido(s).", lidos)
        return lidos

    def _read_detail(self):
        self.ensure_one()
        token = self.account_id.sudo().token
        dados = olist_client.get_pedido(token, self.olist_id)
        if dados is None:
            return False
        self._absorve_detalhe(dados)
        return True

    def _absorve_detalhe(self, dados):
        """Grava o detalhe no espelho — sem criar nada no Odoo ainda."""
        self.ensure_one()
        ecommerce = dados.get('ecommerce') or {}
        cliente = dados.get('cliente') or {}
        canal = (ecommerce.get('nomeEcommerce') or '').strip()
        vals = {
            'situacao': dados.get('situacao') or self.situacao,
            'canal': canal or False,
            'numero_ecommerce': (ecommerce.get('numeroPedidoEcommerce')
                                 or dados.get('numero_ecommerce') or False),
            'id_nota_fiscal': dados.get('id_nota_fiscal') or False,
            'cliente_nome': cliente.get('nome') or self.cliente_nome,
            'cliente_doc': cliente.get('cpf_cnpj') or False,
            'cliente_email': cliente.get('email') or False,
            'cliente_uf': cliente.get('uf') or False,
            'codigo_rastreamento': (dados.get('codigo_rastreamento')
                                    or self.codigo_rastreamento),
            'url_rastreamento': (dados.get('url_rastreamento')
                                 or self.url_rastreamento),
            'transportadora': dados.get('nome_transportador') or False,
            'plataforma': (dados.get('intermediador') or {}).get('nome') or False,
            'marcadores': ", ".join(
                (m.get('marcador') or {}).get('descricao') or ''
                for m in (dados.get('marcadores') or [])) or False,
            'data_prevista': self.account_id._data_br(dados.get('data_prevista')),
            'data_entrega': self.account_id._data_br(dados.get('data_entrega')),
            'data_faturamento': self.account_id._data_br(
                dados.get('data_faturamento')),
            'forma_envio': dados.get('forma_envio') or False,
            'deposito': dados.get('deposito') or False,
            'entrega_cidade': (dados.get('endereco_entrega') or {}).get('cidade')
                              or (dados.get('cliente') or {}).get('cidade') or False,
            'entrega_uf': (dados.get('endereco_entrega') or {}).get('uf')
                          or (dados.get('cliente') or {}).get('uf') or False,
            'forma_frete': dados.get('forma_frete') or dados.get('forma_envio') or False,
            'data_envio': self.account_id._data_br(dados.get('data_envio')),
            'valor_frete': float(dados.get('valor_frete') or 0.0),
            'detalhe_lido_em': fields.Datetime.now(),
            'detalhe_pendente': False,
            'raw_json': json.dumps(dados, ensure_ascii=False, indent=1),
        }
        if canal:
            # A DESCOBERTA acontece aqui, que é onde o nome do canal chega. A
            # linha do espelho nasce (é registro do que o Olist disse, e é
            # barato); o canal de venda da casa, não — ele vem do mapeamento,
            # e vazio é resposta legítima: o pedido entra sem canal e a
            # pendência fica visível na tela de Canais do Olist.
            espelho = self.env['olist.channel']._find_or_create(
                self.account_id, canal, vals.get('plataforma') or None)
            vals['team_id'] = espelho.team_id.id
        self.write(vals)
        self._sincroniza_linhas(dados.get('itens') or [])

    def _sincroniza_linhas(self, itens):
        """Reescreve os itens a partir do que veio. O espelho reflete, não acumula."""
        self.ensure_one()
        self.line_ids.unlink()
        for bloco in itens:
            item = bloco.get('item') or bloco
            codigo = (item.get('codigo') or '').strip()
            # Pelo ESPELHO primeiro (id interno, depois código), e só então
            # pelo ISBN. O item do pedido traz o `id_produto` do Olist — a
            # chave exata — e o espelho é onde mora o casamento à mão. Sem
            # isso, um livro casado a dedo no catálogo continuaria travando os
            # pedidos dele, e o trabalho de casar não teria servido para nada.
            produto = self.account_id._resolve_product(
                codigo=codigo, olist_id=item.get('id_produto'))
            espelho = self.account_id._find_mirror(
                codigo=codigo, olist_id=item.get('id_produto'))
            self.env['olist.order.line'].create({
                'mirror_id': espelho.id,
                'order_id': self.id,
                'codigo': codigo,
                'descricao': item.get('descricao') or '',
                'quantidade': float(item.get('quantidade') or 0),
                'valor_unitario': float(item.get('valor_unitario') or 0),
                'olist_produto_id': item.get('id_produto') or False,
                'product_id': produto.id if produto else False,
            })
        self._registra_itens_sem_produto()

    def _registra_itens_sem_produto(self):
        """Anota no histórico quais livros não foram localizados.

        O bloqueio da importação já existia, mas ele acontecia lá adiante, numa
        notificação que some da tela. Quem lê o pedido semanas depois precisa
        saber POR QUE ele nunca entrou — e o lugar onde essa pergunta se faz é
        o próprio pedido, não o log do servidor.
        """
        self.ensure_one()
        faltando = self.line_ids.filtered(lambda l: not l.product_id)
        if not faltando:
            return False
        # Markup, e não str: `_()` devolve texto puro, e o `message_post`
        # ESCAPA texto puro -- a mensagem saía com as tags à mostra no chatter
        # (visto em 18/08/2026). O `%` do Markup escapa sozinho o que vem de
        # fora (código e descrição chegam do Olist), então o caminho seguro e
        # o caminho legível são o mesmo.
        linhas = Markup("").join(
            Markup("<li><b>%s</b> — %s (qtd %s)</li>") % (
                item.codigo or _("sem código"),
                item.descricao or '', int(item.quantidade or 0))
            for item in faltando)
        self.message_post(body=Markup(_(
            "<p>%(n)s livro(s) deste pedido não foram localizados no Odoo. "
            "Enquanto faltarem, o pedido não é importado — ele entraria com "
            "menos livros do que teve.</p><ul>%(lista)s</ul>"
            "<p>Case-os na tela <b>Produtos</b> (o código do Olist pode ser o "
            "ISBN antigo do mesmo livro) e leia o detalhe outra vez.</p>")) % {
                'n': len(faltando), 'lista': linhas})
        return True

    # ------------------------------------------------------------------
    # Trazer para o Odoo (escrita, e só sobre selecionados)
    # ------------------------------------------------------------------
    def action_import_selected(self):
        """Cria no Odoo o pedido das linhas SELECIONADAS.

        Escreve no Odoo, nunca no Olist — este é o sentido de volta, e a conta
        em modo somente-leitura não impede nada aqui (ela protege a conta
        externa, não a nossa base).

        Um pedido por vez, e um problema numa linha não derruba as outras: o
        que falta produto é dito por extenso, não inventado.
        """
        entraram, erros = 0, []
        for pedido in self:
            try:
                # Um savepoint POR PEDIDO. Sem ele, uma fatura que falha deixa
                # para trás o S que nasceu logo antes: foi o que produziu o
                # S63109 órfão, sem fatura, enquanto a tela dizia "0
                # importados, 1 com problema" (17/08/2026, pedido 1006).
                # Ou entra inteiro — S, fatura e eDoc — ou não entra.
                with self.env.cr.savepoint():
                    if pedido._import_to_odoo():
                        entraram += 1
            except UserError as exc:
                erros.append("%s: %s" % (pedido.numero or pedido.olist_id,
                                         exc.args[0] if exc.args else exc))
        # As vendas de TODOS os selecionados, não só das criadas agora: clicar
        # em "importar" num pedido que já entrou tem de levar ao S dele -- era
        # o caso "nada a fazer", que devolvia notificação vazia com reload de
        # página: o freeze, e a pessoa no mesmo lugar (17/08/2026, pedido 1012).
        vendas = self.sale_order_id
        if not erros and vendas:
            if len(vendas) == 1:
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.order',
                    'res_id': vendas.id,
                    'view_mode': 'form',
                }
            return {
                'type': 'ir.actions.act_window',
                'name': _("Pedidos importados do Olist"),
                'res_model': 'sale.order',
                'view_mode': 'list,form',
                'domain': [('id', 'in', vendas.ids)],
            }
        if not erros:
            return False    # nada selecionado tinha o que importar
        return self._notificacao(
            _("Importação parcial"),
            _("%(ok)s importados, %(n)s com problema:\n%(lista)s",
              ok=entraram, n=len(erros), lista="\n".join(erros[:8])),
            'warning', sticky=True)

    def _import_to_odoo(self):
        self.ensure_one()
        if self.sale_order_id:
            # Já tem S. Se lhe falta a fatura, o trabalho está pela metade e o
            # que a pessoa quer ao clicar de novo é COMPLETAR — não ouvir que
            # não há nada a fazer. É o resgate dos pedidos que entraram antes
            # do savepoint acima existir.
            #
            # Fora do corte, porém, S sem fatura NÃO é trabalho pela metade: é
            # o estado correto. Completar aqui seria o reimport furando o corte
            # pela porta dos fundos.
            if not self.invoice_id and self._dentro_do_corte():
                return self._create_invoice()
            return False
        if not self.detalhe_lido_em:
            raise UserError(_("falta ler o detalhe (é dele que vem o canal)"))
        if (self.situacao or '').strip().lower() == 'cancelado':
            raise UserError(_("cancelado no Olist — não se importa"))
        if not self.line_ids:
            raise UserError(_("sem itens"))

        # Sem XML não se segue em frente. A nota é a verdade fiscal da venda, e
        # é dela que a fatura nasce (§16): importar sem ela produziria um
        # pedido que ninguém consegue faturar depois sem refazer o caminho.
        if self.xml_status == 'sem_xml':
            self._fetch_xml()          # tenta agora; pode ser que já esteja lá
        if self.xml_status != 'arquivado':
            raise UserError(_(
                "sem XML arquivado (%s). A nota é a verdade fiscal da venda e "
                "a fatura nasce dela — traga o XML antes de importar.",
                dict(self._fields['xml_status'].selection).get(
                    self.xml_status, self.xml_status)))

        sem_produto = self.line_ids.filtered(lambda l: not l.product_id)
        if sem_produto:
            # O mesmo princípio do espelho de catálogo: ISBN que não casa é
            # notícia, não motivo para inventar produto. Sem isso, um pedido
            # entraria com menos livros do que teve, e o número ficaria errado
            # para sempre sem ninguém perceber.
            raise UserError(_(
                "ISBN sem produto no Odoo: %s",
                ", ".join(sem_produto.mapped('codigo'))))

        pedido_odoo = self.env['sale.order'].create(self._sale_order_vals())
        self.sale_order_id = pedido_odoo
        self._carimbar_posicao_fiscal(pedido_odoo)
        # "Um pedido já com o XML na mão": se a nota existe lá e o documento
        # ainda não está aqui, traz agora. Não é fatal se falhar -- o pedido e
        # o documento fiscal são duas verdades distintas, e a nota pode chegar
        # depois pelo botão ou pelo sync.
        if self.xml_status == 'sem_xml':
            status, detalhe = self._fetch_xml()
            if status != 'OK':
                _logger.info("Olist pedido %s: XML não veio agora (%s)",
                             self.numero, detalhe)
        _logger.info("Olist pedido %s -> %s (canal %s)",
                     self.numero, pedido_odoo.name, self.canal or '-')
        self._baixa_estoque_se_for_o_caso()
        # A fatura nasce junto: o pedido só entra com XML arquivado (acima),
        # então a nota está aqui e não há por que adiar o lançamento. O eDoc é
        # o próprio painel, que a fatura passa a apontar.
        #
        # Mas só a partir do CORTE. O corte governa a entrada do pedido na
        # operação, e faturar é o efeito mais pesado dela: lança no razão e,
        # com diário de recebimento configurado, registra o dinheiro. O
        # histórico da conta tem ~1000 pedidos, e importá-los para consolidar
        # não pode reescrever a contabilidade de um ano atrás (decisão do dono
        # em 18/08/2026). Antes do corte o pedido entra como registro: espelho,
        # rastreabilidade e o XML arquivado, sem estoque e sem lançamento.
        if self._dentro_do_corte():
            self._create_invoice()
        else:
            _logger.info(
                "Olist pedido %s (%s): anterior ao corte %s — entrou sem "
                "fatura e sem baixa de estoque.",
                self.numero, self.data_pedido,
                self.account_id.order_stock_cutoff)
        return True

    def _dentro_do_corte(self):
        """O pedido é recente o bastante para produzir efeito na operação?

        Um lugar só para a pergunta, porque ela governa DOIS efeitos (a baixa
        de estoque e a fatura) e duas respostas diferentes para a mesma data
        seriam um pedido que baixa prateleira sem faturar, ou o contrário.
        """
        self.ensure_one()
        corte = self.account_id.order_stock_cutoff
        return bool(corte and self.data_pedido and self.data_pedido >= corte)

    def _carimbar_posicao_fiscal(self, documento):
        """A posição fiscal do marketplace é a da VENDA, e vem das Definições.

        O S do Olist é venda comum -- a nota que o marketplace emitiu diz
        isso, com o CFOP de venda. A posição nasce do padrão da empresa
        (Definições > Faturamento), nunca da ficha do cliente: o comprador de
        marketplace é pessoa física avulsa, cadastro que ninguém parametriza.

        Escrita DEPOIS do create, de propósito: é o que dispara o recálculo de
        imposto das linhas (mesmo motivo do acerto de consignação). Empresa
        sem o padrão preenchido cai no comportamento do Odoo em vez de
        estourar -- importação é fluxo diário e não para por configuração.
        """
        self.ensure_one()
        posicao = self.company_id.sale_fiscal_position_id
        if posicao and not documento.fiscal_position_id:
            documento.fiscal_position_id = posicao

    def _sale_order_vals(self):
        self.ensure_one()
        parceiro = self.account_id._resolve_partner(
            self.cliente_doc, self.cliente_nome, self.cliente_email, self.canal)
        self.partner_id = parceiro
        # Última chance de o mapeamento carimbar o pedido: o canal pode ter
        # sido mapeado DEPOIS da leitura do detalhe. Não nasce canal nenhum
        # aqui — canal não mapeado devolve vazio, e o pedido entra sem canal
        # em vez de inventar uma taxonomia que ninguém decidiu.
        if self.canal and not self.team_id:
            self.team_id = self.account_id._resolve_team(self.canal)
        return {
            'partner_id': parceiro.id,
            'company_id': self.company_id.id,
            'team_id': self.team_id.id or False,
            'date_order': fields.Datetime.to_datetime(self.data_pedido),
            # A referência do cliente é o número no marketplace: é por ele que
            # a operação acha o pedido quando o comprador reclama.
            'client_order_ref': self.numero_ecommerce or self.numero,
            'origin': "Olist #%s" % (self.numero or self.olist_id),
            'order_line': [(0, 0, l._sale_line_vals()) for l in self.line_ids],
        }

    # As situações do Olist que PROVAM que o pacote saiu da casa: o comprador
    # recebeu, ou a entrega viajou e falhou. "Enviado" NÃO entra, e é o furo
    # que o dono apontou (18/08/2026): o Olist marca Enviado quando a ETIQUETA
    # nasce — o PDF cai na nossa mão e o pacote continua na prateleira,
    # esperando a coleta. Daí em diante, só a CASA sabe se ele saiu.
    SITUACOES_FORA_DA_CASA = ('Entregue', 'Não entregue')

    def _baixa_estoque_se_for_o_caso(self):
        """Confirma a venda — e só CONCLUI a entrega do que comprovadamente saiu.

        Sem corte (o padrão), nada se mexe: o pedido entra como rascunho, para
        consolidação. A partir do corte, a venda confirma (reservando o
        estoque) e a entrega nasce PRONTA — é a fila de embalagem do
        funcionário, que valida quando o pacote sai na coleta. Concluir
        sozinho, só quando o Olist prova que o pacote já não está aqui
        (Entregue): status de etiqueta não é status de prateleira.
        """
        self.ensure_one()
        if not self._dentro_do_corte():
            return False
        self.sale_order_id.action_confirm()
        self._mover_para_a_caixa_marketplaces()
        if (self.situacao or '').strip() in self.SITUACOES_FORA_DA_CASA:
            self._concluir_entregas()
        self._carimba_rastreio()
        return True

    def _mover_para_a_caixa_marketplaces(self):
        """A entrega muda para a caixa Marketplaces (série MP/OUT/).

        Decisão do dono (18/08/2026): o pacote do marketplace é outro
        trabalho — pequeno, pessoa física, etiqueta do Olist — e não pode se
        misturar ao WH/OUT do palete da Amazon. O tipo próprio dá ao depósito
        um cartão só dele no Inventário. Renomeia junto, antes de qualquer
        conclusão: o número precisa contar a série certa desde o começo.
        """
        self.ensure_one()
        tipo = self.account_id._marketplace_picking_type()
        if not tipo:
            return False
        for picking in self.sale_order_id.picking_ids:
            if picking.state in ('done', 'cancel'):
                continue
            if picking.picking_type_id == tipo:
                continue
            picking.write({'picking_type_id': tipo.id,
                           'name': tipo.sequence_id.next_by_id()})
        return True

    def _concluir_entregas(self):
        """Valida as entregas abertas do pedido: o pacote comprovadamente saiu."""
        self.ensure_one()
        for picking in self.sale_order_id.picking_ids:
            if picking.state in ('done', 'cancel'):
                continue
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.button_validate()
        return True

    def write(self, vals):
        """A releitura reconcilia: virou Entregue lá, conclui a entrega aqui.

        Se o funcionário embalar e esquecer de validar, o mundo acaba
        avisando — o comprador recebeu. O Odoo se corrige pela fonte, nunca o
        contrário. Vale para qualquer caminho que atualize a situação:
        listagem, detalhe, cron.
        """
        resultado = super().write(vals)
        if (vals.get('situacao')
                and vals['situacao'].strip() in self.SITUACOES_FORA_DA_CASA):
            for pedido in self.filtered('sale_order_id'):
                abertas = pedido.sale_order_id.picking_ids.filtered(
                    lambda p: p.state not in ('done', 'cancel'))
                if abertas:
                    pedido._concluir_entregas()
        return resultado

    def _carimba_rastreio(self):
        """Leva o código de rastreio do Olist para a entrega do Odoo.

        No campo do próprio Odoo (`stock.picking.carrier_tracking_ref`), e não
        num campo nosso: é lá que o atendimento e o portal do cliente já olham,
        e é lá que o e-mail de entrega o imprime. Um rastreio guardado só no
        espelho seria um número que ninguém encontra na hora em que é pedido.
        """
        self.ensure_one()
        if not self.codigo_rastreamento or not self.sale_order_id:
            return False
        pickings = self.sale_order_id.picking_ids
        if 'carrier_tracking_ref' not in pickings._fields:
            return False
        marcadas = 0
        for picking in pickings:
            if not picking.carrier_tracking_ref:
                picking.carrier_tracking_ref = self.codigo_rastreamento
                marcadas += 1
        return marcadas

    def action_create_invoice(self):
        """Cria a fatura dos pedidos escolhidos, a partir do XML da nota."""
        feitas, erros = 0, []
        for pedido in self:
            try:
                if pedido._create_invoice():
                    feitas += 1
            except UserError as exc:
                erros.append("%s: %s" % (pedido.numero or pedido.olist_id,
                                         exc.args[0] if exc.args else exc))
        if not erros:
            return False
        return self._notificacao(
            _("Faturamento parcial"),
            _("%(n)s criadas, %(e)s com problema:\n%(lista)s",
              n=feitas, e=len(erros), lista="\n".join(erros[:8])),
            'warning', sticky=True)

    def _create_invoice(self):
        """A fatura nasce do XML, não do pedido — e a diferença é o ponto.

        O XML é o que a SEFAZ autorizou: é a verdade fiscal. Montar a fatura a
        partir do pedido do Odoo arriscaria um documento contábil dizendo o que
        o documento fiscal não diz (o Olist pode ter emitido com outro valor,
        frete ou desconto), e ninguém perceberia. Nascendo do XML, os dois
        batem por construção.

        Ela também não EMITE nada. Quando chega aqui a nota já está autorizada;
        o que se faz é registrar no razão um fato fiscal consumado.
        """
        self.ensure_one()
        if self.invoice_id:
            return False
        painel = self.nfe_panel_id
        if not painel:
            raise UserError(_(
                "sem XML arquivado — traga a nota antes (a fatura sai dela, "
                "não do pedido)"))
        if not painel.panel_items:
            # Painel arquivado e ainda não lido (o parse é do cron do
            # liber_nfe_xml). Lê agora em vez de mandar a pessoa esperar a
            # madrugada para poder faturar.
            painel.action_import_xml_file()
            painel.invalidate_recordset(['panel_items'])
        if not painel.panel_items:
            raise UserError(_(
                "o XML foi arquivado mas não produziu itens — abra a NFe e "
                "veja o motivo da leitura ter falhado"))
        sem_produto = painel.panel_items.filtered(lambda i: not i.ks_product_id)
        if sem_produto:
            raise UserError(_(
                "itens do XML sem produto no Odoo: %s",
                ", ".join(i.ks_product_barcode or i.ks_product_name or '?'
                          for i in sem_produto)))

        parceiro = painel.partner_id or self.partner_id
        if not parceiro:
            raise UserError(_("o XML não resolveu o cliente"))

        fatura = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': parceiro.id,
            'company_id': self.company_id.id,
            'invoice_date': painel.file_create_date or self.data_pedido,
            'invoice_origin': (self.sale_order_id.name
                               or _("Olist #%s", self.numero or self.olist_id)),
            'ref': _("NFe %s", painel.danfe_no or painel.key or ''),
            'team_id': self.team_id.id or False,
            'nfe_key': painel.key or False,
            'invoice_line_ids': [(0, 0, self._linha_de_fatura(item))
                                 for item in painel.panel_items],
        })
        self.invoice_id = fatura
        # Antes de lançar: a posição fiscal é o que classifica a nota na
        # contabilidade, e depois do action_post não se muda mais.
        self._carimbar_posicao_fiscal(fatura)
        # O painel é o eDoc: é nele que a nota mora, e é por ele que se chega
        # ao XML a partir da fatura (o compute da chave faz o caminho de volta).
        if not painel.invoice_id:
            painel.invoice_id = fatura
        if self.account_id.invoice_auto_post:
            fatura.action_post()
            self._registra_recebimento(fatura)
        self._carimba_nota_na_movimentacao(fatura)
        self._anexa_xml_na_fatura(fatura)
        _logger.info("Olist pedido %s -> fatura %s (nota %s)",
                     self.numero, fatura.name, painel.danfe_no or painel.key)
        return True

    def _linha_de_fatura(self, item):
        """A linha da fatura, amarrada à linha do PEDIDO quando ela existe.

        Sem `sale_line_ids` a fatura fica solta: o comercial abre o S e vê
        "Faturado: 0" com a nota emitida e paga do outro lado. É esse vínculo
        que faz o smart button de Faturas aparecer no pedido e as quantidades
        faturadas baterem.
        """
        self.ensure_one()
        vals = {
            'product_id': item.ks_product_id.id,
            'name': item.ks_product_name or item.ks_product_id.display_name,
            'quantity': item.ks_product_qty,
            'price_unit': item.ks_price,
            'discount': 0.0,
        }
        linha_pedido = self.sale_order_id.order_line.filtered(
            lambda l: l.product_id == item.ks_product_id)[:1]
        if linha_pedido:
            vals['sale_line_ids'] = [(6, 0, linha_pedido.ids)]
        return vals

    def _carimba_nota_na_movimentacao(self, fatura):
        """Leva a nota para a transferência, que é a tela da logística.

        `stock.picking.nfe_move_id` é o campo que o liber_nfe_picking já usa —
        dele saem o filtro "Com nota" da lista e o menu de impressão. Sem
        carimbar, a logística conclui a movimentação e não tem por onde chegar
        à nota que já existe.

        Guardado por existência do campo: o liber_olist não depende do
        liber_nfe_picking, e quem não o tiver instalado simplesmente não ganha
        o carimbo.
        """
        self.ensure_one()
        pickings = self.sale_order_id.picking_ids
        if not pickings or 'nfe_move_id' not in pickings._fields:
            return False
        marcadas = 0
        for picking in pickings.filtered(lambda p: not p.nfe_move_id):
            picking.nfe_move_id = fatura
            # O XML vai junto: dentro do corte a entrega nasce ANTES da
            # fatura (a importação confirma primeiro), então o gancho da
            # confirmação não tinha o que pendurar — é aqui que o documento
            # alcança a caixa que a logística vai separar.
            picking._liber_olist_anexar_xml(self.nfe_panel_id)
            marcadas += 1
        return marcadas

    def _anexa_xml_na_fatura(self, fatura):
        """Pendura o XML na própria fatura.

        A chave de acesso já liga a fatura ao painel, mas ligação é caminho e
        arquivo é posse: quem abre a fatura para conferir quer o documento no
        clipe, não uma viagem até outra tela. O contador, o comercial e a
        auditoria pedem o arquivo — e pedem dele.
        """
        self.ensure_one()
        painel = self.nfe_panel_id
        if not painel or not painel.file:
            return False
        Anexo = self.env['ir.attachment']
        nome = painel.file_name or ("nfe-%s.xml" % (painel.danfe_no or painel.id))
        if Anexo.search_count([('res_model', '=', 'account.move'),
                               ('res_id', '=', fatura.id),
                               ('name', '=', nome)]):
            return False
        Anexo.create({
            'name': nome,
            'datas': painel.file,
            'res_model': 'account.move',
            'res_id': fatura.id,
            'mimetype': 'application/xml',
        })
        return True

    def _registra_recebimento(self, fatura):
        """O dinheiro já entrou no marketplace: a fatura nasce recebida.

        O financeiro não deve ver como "a receber" um valor que o comprador já
        pagou ao Olist. O recebimento é lançado no DIÁRIO configurado na conta
        — e é por isso que ele deve ser um diário próprio do marketplace, e não
        a conta bancária: o dinheiro está com o Olist, não no banco, até o
        repasse cair. Reconciliar esse diário contra o repasse é o passo
        seguinte, e é onde as taxas aparecem.

        Sem diário configurado, não se lança nada: inventar por onde o dinheiro
        entrou seria pior do que deixar o título em aberto.
        """
        self.ensure_one()
        diario = self.account_id.payment_journal_id
        if not diario or fatura.state != 'posted':
            return False
        registro = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=fatura.ids,
        ).create({
            'journal_id': diario.id,
            'amount': fatura.amount_total,
            'payment_date': fatura.invoice_date or fields.Date.today(),
            'communication': fatura.ref or fatura.name,
        })
        registro.action_create_payments()
        _logger.info("Olist: recebimento de %s lançado em %s",
                     fatura.name, diario.name)
        return True

    def action_open_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_("Este pedido ainda não tem fatura."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
        }

    def action_stamp_tracking(self):
        """Carimba o rastreio nas entregas dos pedidos escolhidos.

        Separado da importação porque o rastreio chega DEPOIS: o pedido entra
        no dia da venda e o pacote só ganha código quando sai. Sem uma ação
        própria, o número ficaria eternamente parado no espelho, e alguém
        teria de reimportar o pedido para levá-lo adiante.
        """
        marcadas = sum(pedido._carimba_rastreio() or 0 for pedido in self)
        sem_pedido = len(self.filtered(lambda p: not p.sale_order_id))
        if not sem_pedido:
            return False
        return self._notificacao(
            _("Carimbo parcial"),
            _("%(m)s entrega(s) atualizadas. %(n)s pedido(s) ainda não foram "
              "importados para o Odoo.", m=marcadas, n=sem_pedido),
            'warning', sticky=True)

    # ------------------------------------------------------------------
    @staticmethod
    def _notificacao(titulo, mensagem, tipo, sticky=False, recarregar=False):
        """Notificação SEM recarregamento de página — e a história importa.

        O cliente web recarrega o registro sozinho depois de qualquer botão
        (`view_button_hook.js`: onClose -> reload do registro), com ou sem
        notificação no retorno. O que ele NÃO faz sozinho é recarregar a
        página -- e foi o `next: reload` posto aqui em 17/08 (para consertar
        o "Ler detalhe" que parecia morto) que virou o freeze: página inteira
        recarregada para devolver a pessoa ao mesmo lugar.

        `recarregar` ficou na assinatura por compatibilidade e é ignorado.
        """
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': titulo, 'message': mensagem,
                       'type': tipo, 'sticky': sticky},
        }

    def action_open_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_("Este pedido ainda não foi importado."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
        }

    def action_open_nfe(self):
        self.ensure_one()
        if not self.nfe_panel_id:
            raise UserError(_("Nenhuma NFe deste pedido entrou ainda."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'nfe.xml.panel',
            'res_id': self.nfe_panel_id.id,
            'view_mode': 'form',
        }


class OlistOrderLine(models.Model):
    """Um item do pedido, como o Olist o descreve."""
    _name = 'olist.order.line'
    _description = "Item do espelho de pedido do Olist"
    _order = 'id'

    order_id = fields.Many2one('olist.order', required=True, ondelete='cascade',
                               index=True)
    codigo = fields.Char("Código (ISBN)", index=True)
    descricao = fields.Char("Descrição")
    quantidade = fields.Float("Qtd", digits='Product Unit of Measure')
    valor_unitario = fields.Float("Valor unitário")
    olist_produto_id = fields.Char("ID do produto no Olist")
    product_id = fields.Many2one('product.product', string="Produto no Odoo",
                                 index='btree_not_null')
    mirror_id = fields.Many2one(
        'olist.product', string="Linha do catálogo", index='btree_not_null',
        ondelete='set null',
        help="A linha do espelho de catálogo a que este item pertence. É por "
             "ela que a tela de casamento sabe o que cada livro vendeu — e "
             "portanto o que vale a pena casar primeiro.")
    order_situacao = fields.Char(related='order_id.situacao', store=True)
    order_data = fields.Date(related='order_id.data_pedido', store=True)
    # As medidas do Relatório: a linha é quem sabe livro e quantidade — o
    # pedido só sabe o total (com frete). Valor aqui é mercadoria, sem frete.
    canal = fields.Char(related='order_id.canal', store=True,
                        string="Canal no Olist")
    valor_total = fields.Float(
        "Valor", compute='_compute_valor_total', store=True,
        help="Quantidade × valor unitário da linha — mercadoria, sem o frete "
             "do pedido. É a medida de valor do Relatório.")

    @api.depends('quantidade', 'valor_unitario')
    def _compute_valor_total(self):
        for linha in self:
            linha.valor_total = (linha.quantidade or 0.0) * (
                linha.valor_unitario or 0.0)

    # O mesmo 34 do relatório da Amazon: cabe numa coluna de pivô sem empurrar
    # a tabela para fora da tela, e ainda deixa reconhecer o livro.
    SHORT_TITLE = 34

    livro = fields.Char(
        "Livro", compute='_compute_livro', store=True, index=True,
        help="O rótulo curto do Relatório: ISBN · título cortado. O nome "
             "completo da ficha carrega autores e editora entre parênteses — "
             "num pivô isso vira uma linha que atravessa a tela.")

    @api.depends('codigo', 'descricao', 'product_id.name')
    def _compute_livro(self):
        """ISBN na frente, título cortado atrás — o padrão da Amazon Vendor.

        O ISBN não é capricho: dois títulos de coleção cortados no mesmo
        ponto virariam o MESMO rótulo, o pivô somaria os dois numa linha só e
        o número sairia errado sem nada na tela denunciando. Com o ISBN na
        frente, cada linha é única mesmo quando o texto colide. O corte no
        ' (' tira os autores/editora que a casa embute no nome da ficha.
        """
        for linha in self:
            nome = (linha.product_id.name or linha.descricao or '?')
            nome = nome.split(' (')[0].strip()
            if len(nome) > linha.SHORT_TITLE:
                nome = nome[:linha.SHORT_TITLE - 1].rstrip() + '…'
            codigo = re.sub(r'\D', '', linha.codigo or '') or '—'
            linha.livro = '%s · %s' % (codigo, nome)

    def _sale_line_vals(self):
        self.ensure_one()
        return {
            'product_id': self.product_id.id,
            'product_uom_qty': self.quantidade,
            'price_unit': self.valor_unitario,
            'name': self.descricao or self.product_id.display_name,
        }
