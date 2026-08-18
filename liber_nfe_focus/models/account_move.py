# -*- coding: utf-8 -*-
"""Emissão de NFe modelo 55 pela Focus NFe, a partir da fatura.

O fluxo tem três tempos, e é assíncrono de propósito -- é assim que a SEFAZ
funciona:

  1. `action_focus_emitir`   POST, a nota entra na fila (processando_autorizacao)
  2. `action_focus_consultar` GET, até virar autorizado ou erro_autorizacao
  3. autorizada, guardamos a chave de acesso, o XML e o DANFE

O passo 2 também roda sozinho num cron, para não depender de alguém clicando.

A chave de acesso vai para `account.move.nfe_key`, o mesmo campo que o
liber_nfe_xml usa para amarrar XML e fatura -- uma nota que emitimos e uma nota
que recebemos passam a ser a mesma coisa para o resto do sistema.
"""

import base64
import logging
import re
from datetime import datetime

import pytz
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from . import nfe_payload
from .res_partner import MODALIDADE_FRETE
from .focus_client import (
    FocusClient, FocusError, FocusNotFound, FocusValidationError,
    STATUS_AUTORIZADO, STATUS_CANCELADO, STATUS_PROCESSANDO,
)

_logger = logging.getLogger(__name__)

FUSO_PADRAO = 'America/Sao_Paulo'

# Estados que aceitam nova consulta. Autorizado e cancelado são finais.
FOCUS_PENDENTES = ('processando_autorizacao', 'enviado')


class AccountMove(models.Model):
    _inherit = 'account.move'

    focus_ref = fields.Char(
        string='Referência Focus', copy=False, readonly=True, index='btree_not_null',
        help="Identificador desta nota na Focus NFe. É nosso, não deles: "
             "reenviar a mesma referência devolve a nota já emitida em vez de "
             "emitir outra, o que é a proteção contra duplicidade quando o "
             "envio dá timeout.")
    focus_status = fields.Selection(
        selection=[
            ('nao_enviado', 'Não enviada'),
            ('processando_autorizacao', 'Processando'),
            ('autorizado', 'Autorizada'),
            ('cancelado', 'Cancelada'),
            ('erro_autorizacao', 'Erro de autorização'),
            ('denegado', 'Denegada'),
        ],
        string='Status na SEFAZ', default='nao_enviado', copy=False,
        readonly=True, tracking=True)
    focus_ambiente = fields.Selection(
        selection=[('homologacao', 'Homologação'), ('producao', 'Produção')],
        string='Ambiente da emissão', copy=False, readonly=True,
        help="Ambiente em que ESTA nota foi enviada, congelado no envio. Se a "
             "empresa mudar de ambiente depois, a consulta continua indo ao "
             "lugar certo.")
    focus_mensagem = fields.Text(
        string='Mensagem da SEFAZ', copy=False, readonly=True)
    focus_protocolo = fields.Char(
        string='Protocolo', copy=False, readonly=True)
    # Volumes e peso viajam no grupo transp/vol da NFe. Nascem da movimentação
    # (ver liber_nfe_picking, que sabe achar as transferências da nota), mas
    # ficam graváveis: quem fatura confere a caixa fechada na bancada e é a
    # última palavra. O que não se admite é seguir sem eles.
    nfe_volumes = fields.Integer(
        string='Volumes (caixas)', copy=False,
        help="Quantas caixas esta nota acompanha. Vem da contagem feita na "
             "transferência e pode ser corrigida aqui antes de emitir.")
    nfe_peso_bruto = fields.Float(
        string='Peso bruto (kg)', digits='Stock Weight', copy=False,
        help="Peso total dos volumes, em quilos. Calculado a partir do peso "
             "dos produtos da movimentação — quando o cadastro não tem o "
             "peso, preencha aqui.")
    nfe_especie_volumes = fields.Char(
        string='Espécie dos volumes', default='CAIXA', copy=False,
        help="Como os volumes são descritos na nota: CAIXA, PACOTE, FARDO.")
    # Frete e transportadora viajam no mesmo grupo transp. Nascem no cadastro
    # do cliente e no pedido (ver liber_nfe_picking, que os traz de lá), mas
    # ficam graváveis pelo mesmo motivo dos volumes: quem fatura é a última
    # palavra. Vazios, a nota sai como 9 -- sem ocorrência de transporte --,
    # que é o caso do acerto de consignação.
    nfe_modalidade_frete = fields.Selection(
        selection=MODALIDADE_FRETE, string='Modalidade do frete', copy=False,
        help="Quem contrata o transporte desta nota. Vem do pedido, que "
             "herda do cadastro do cliente. Vazio emite como 9 — sem "
             "ocorrência de transporte, o caso do acerto de consignação.")
    nfe_transportadora_id = fields.Many2one(
        'res.partner', string='Transportadora', copy=False,
        help="A empresa que leva a carga, declarada no grupo transportador "
             "da NFe. Vem do método de entrega da transferência do pedido. "
             "Só viaja quando a modalidade declara transporte.")
    focus_numero = fields.Char(string='Número da NFe', copy=False, readonly=True)
    focus_serie = fields.Char(string='Série', copy=False, readonly=True)
    focus_danfe_url = fields.Char(string='DANFE (Focus)', copy=False, readonly=True)
    nfe_cfop_id = fields.Many2one(
        'nfe.cfop', string='CFOP da Nota',
        help="A operação fiscal desta nota. É ela que decide a natureza da "
             "operação, o CST e a finalidade — uma remessa em consignação "
             "(5917) não é uma venda (5102) e não pode sair como tal. Vazio "
             "herda do pedido de origem, e depois do padrão da empresa.")
    focus_nota_referenciada_id = fields.Many2one(
        'account.move', string='Nota de origem',
        help="A nota que esta aqui devolve ou complementa. Numa devolução é o "
             "que amarra as duas na SEFAZ: sem ela, não há como saber o que "
             "está sendo devolvido.")
    focus_chave_referenciada = fields.Char(
        string='Chave da nota de origem', size=44,
        help="Use quando a nota de origem não está no Odoo — uma devolução ao "
             "fornecedor, por exemplo. Preenchido automaticamente quando a "
             "nota de origem é escolhida acima.")
    focus_correcoes = fields.Text(
        string='Cartas de Correção', copy=False, readonly=True,
        help="Histórico das CC-e enviadas. A SEFAZ aceita até 20 por nota, e "
             "cada uma SUBSTITUI a anterior: a última vale por inteiro.")

    @api.onchange('focus_nota_referenciada_id')
    def _onchange_focus_nota_referenciada_id(self):
        for move in self:
            if move.focus_nota_referenciada_id.nfe_key:
                move.focus_chave_referenciada = \
                    move.focus_nota_referenciada_id.nfe_key

    def _focus_chaves_referenciadas(self):
        """Chaves das notas que esta referencia."""
        self.ensure_one()
        chaves = [self.focus_nota_referenciada_id.nfe_key,
                  self.focus_chave_referenciada]
        # dict.fromkeys preserva a ordem e tira a repetida quando os dois
        # campos apontam para a mesma nota, que é o caso comum.
        return list(dict.fromkeys(c for c in chaves if c))

    # ------------------------------------------------------------------
    # referência
    # ------------------------------------------------------------------
    def _focus_build_ref(self):
        """Referência única e estável.

        Inclui o prefixo da empresa porque o mesmo token pode atender mais de
        um banco (staging e produção): sem o prefixo, a consulta de um banco
        devolveria a nota do outro.

        A fórmula é determinística de propósito: se o envio estourar depois de
        a Focus ter aceitado a nota, o rollback apaga o `focus_ref` gravado,
        mas a próxima tentativa recalcula exatamente a mesma referência -- e a
        Focus, vendo referência repetida, devolve a nota que já existe em vez
        de emitir uma segunda. É o que dispensa `commit()` no meio da ação.
        """
        self.ensure_one()
        prefixo = (self.company_id.focus_ref_prefix or 'ODOO').strip()
        return '%s-%s-%s' % (prefixo, self.company_id.id, self.id)

    def _focus_ref_para_emissao(self):
        """A referência desta tentativa de emissão.

        Reaproveita a gravada -- é a idempotência que protege contra nota
        duplicada quando um envio estoura depois de a Focus ter aceitado.
        EXCETO depois de rejeição definitiva: a Focus congela a ref na nota
        rejeitada e devolveria a recusa velha para sempre, por mais certo
        que o payload novo esteja. Nesse caso a ref avança com sufixo -R2,
        -R3..., preservando a fórmula e deixando o rastro das tentativas.

        O sufixo só anda DEPOIS de um `erro_autorizacao`: uma repetição da
        mesma tentativa (rollback, clique duplo) continua caindo na mesma
        ref, que é o ponto da proteção.
        """
        self.ensure_one()
        ref = self.focus_ref or self._focus_build_ref()
        if self.focus_status != 'erro_autorizacao':
            return ref
        casado = re.match(r'^(.*)-R(\d+)$', ref)
        if casado:
            return '%s-R%d' % (casado.group(1), int(casado.group(2)) + 1)
        return '%s-R2' % ref

    # ------------------------------------------------------------------
    # montagem do payload
    # ------------------------------------------------------------------
    def _focus_data_emissao(self):
        """Agora, no fuso da empresa, em ISO 8601 com offset.

        A SEFAZ rejeita data futura e desconfia de data velha, então usamos o
        instante do envio e não `invoice_date`: a data contábil da fatura pode
        ser de ontem sem que isso valha para a emissão.
        """
        self.ensure_one()
        fuso = pytz.timezone(self.env.user.tz or FUSO_PADRAO)
        return datetime.now(fuso).replace(microsecond=0).isoformat()

    def _focus_item_referenciado(self, line, indice):
        """Qual item da nota de origem esta linha devolve.

        A SEFAZ quer o casamento item a item, não só a nota. O número vem do
        campo da linha quando alguém o preencheu; senão, procura-se o produto
        na nota de origem — que acerta no caso comum e é ambíguo só quando o
        mesmo produto aparece duas vezes lá, que é justamente quando se
        preenche à mão.
        """
        self.ensure_one()
        chave = (self.focus_chave_referenciada
                 or self.focus_nota_referenciada_id.nfe_key)
        if not chave:
            return None, None
        if line.nfe_item_referenciado:
            return chave, line.nfe_item_referenciado
        origem = self.focus_nota_referenciada_id
        if origem:
            for i, linha_origem in enumerate(
                    origem._focus_linhas_produto(), start=1):
                if linha_origem.product_id == line.product_id:
                    return chave, i
        # Sem nota de origem no Odoo (devolução a fornecedor, por exemplo):
        # a posição na nossa nota é o melhor palpite disponível.
        return chave, indice

    def _focus_item_data(self, line, indice, fiscal=None):
        """Converte uma linha da fatura num item do payload."""
        self.ensure_one()
        company = self.company_id
        produto = line.product_id
        # A linha pode carregar operação própria (uma nota mistura operações,
        # e a posição fiscal decide imposto a imposto), e nesse caso os
        # atributos fiscais são os DELA, não os da nota.
        explicito = line.nfe_cfop_id
        operacao = (explicito._operacao() if explicito
                    else (line._focus_operacao_do_imposto()
                          or self.fiscal_position_id.nfe_operacao_id))
        if operacao or explicito:
            fiscal = operacao._focus_fiscal(company)
        else:
            operacao = self._focus_operacao_da_nota()
        codigo_cfop = self._focus_cfop_da_operacao(operacao, explicito)
        if not codigo_cfop:
            raise UserError(_(
                "A linha '%(linha)s' não tem operação fiscal, e a empresa não "
                "tem operação padrão configurada.",
                linha=line.name or produto.display_name))

        ncm = produto.product_tmpl_id._focus_ncm(company) if produto else company.focus_ncm_padrao
        if not ncm:
            raise UserError(_(
                "O produto '%s' não tem NCM e a empresa não tem NCM padrão.",
                produto.display_name or line.name))

        # O ISBN é o identificador que a livraria concilia. Ele é o código de
        # barras do livro, e vale como cProd quando não há referência interna:
        # `cProd` saindo "0" (o id do produto) torna a nota inútil do outro lado
        # do balcão, ainda que a SEFAZ aceite.
        gtin = (produto.barcode or '').strip() or None
        # Referência interna que não identifica nada ("0", "/") é sujeira de
        # migração, e cai fora: melhor o ISBN, que a livraria reconhece.
        interno = (produto.default_code or '').strip()
        if interno in ('', '0', '/', '-'):
            interno = None
        prefere_barras = company.focus_codigo_produto == 'barras'
        item = {
            'codigo': ((gtin or interno) if prefere_barras else (interno or gtin))
                      or (produto.id and str(produto.id)) or str(indice),
            'codigo_barras_comercial': gtin,
            'codigo_barras_tributavel': gtin,
            'descricao': line.name or produto.display_name,
            'ncm': ncm,
            'cfop': codigo_cfop,
            'unidade': line.product_uom_id._nfe_sigla(),
            'quantidade': line.quantity,
            'valor_unitario': line.price_unit,
            # O bruto é sem desconto: o desconto vai no campo próprio, senão a
            # SEFAZ acha que o preço unitário é outro.
            'valor_bruto': line.quantity * line.price_unit,
            'icms_origem': int(produto.nfe_origem or '0') if produto else 0,
            'icms_situacao_tributaria': fiscal.get('cst_icms'),
            # O produto sobrepõe o CFOP: um item com tratamento próprio o
            # carrega consigo, entre operações.
            'codigo_beneficio_fiscal': (
                (produto.product_tmpl_id.nfe_codigo_beneficio_fiscal
                 if produto else None) or fiscal.get('cbenef')),
            'ibs_cbs_situacao_tributaria': (
                (produto.product_tmpl_id.nfe_ibs_cbs_cst if produto else None)
                or fiscal.get('ibs_cbs_cst')),
            'ibs_cbs_classificacao_tributaria': (
                (produto.product_tmpl_id.nfe_ibs_cbs_classificacao
                 if produto else None) or fiscal.get('ibs_cbs_classificacao')),
        }
        # O desconto sai da diferença entre o bruto e o que o Odoo cobra, e não
        # de `line.discount` -- assim o líquido do item na nota bate com o
        # subtotal da linha na fatura, arredondamento do Odoo incluído. Um
        # centavo de divergência entre o que a nota diz e o que se cobra é
        # problema fiscal, não estético.
        #
        # A comparação é pela moeda, não por `> 0`: 3 x 89,90 em ponto flutuante
        # dá 269.70000000000005, e a diferença de 5,7e-14 contra o subtotal é
        # "maior que zero". Sem isto, TODA nota sai com um desconto fantasma de
        # 0,00 no XML e no DANFE.
        moeda = self.currency_id or self.company_id.currency_id
        desconto = moeda.round((line.quantity * line.price_unit) - line.price_subtotal)
        if moeda.compare_amounts(desconto, 0.0) > 0:
            item['valor_desconto'] = desconto

        # Só numa devolução: fora dela o campo é indevido.
        if (fiscal or {}).get('finalidade') == nfe_payload.FINALIDADE_DEVOLUCAO:
            chave_ref, numero_ref = self._focus_item_referenciado(line, indice)
            if chave_ref:
                item['chave_dfe_referenciado'] = chave_ref
                item['numero_item_dfe_referenciado'] = numero_ref
        return item

    def _focus_local_destino(self):
        """'interna', 'interestadual' ou 'exterior'.

        O exterior se decide pelo PAÍS, não pela UF: um cliente português não
        tem UF brasileira, e olhar só a UF o classificaria como operação
        interna -- o erro mais silencioso possível.
        """
        self.ensure_one()
        pais_emitente = self.company_id.partner_id.country_id
        pais_destino = self.partner_id.country_id
        if pais_destino and pais_emitente and pais_destino != pais_emitente:
            return 'exterior'
        local = nfe_payload.local_destino(
            self.company_id.partner_id.state_id.code,
            self.partner_id.state_id.code)
        return {nfe_payload.DESTINO_INTERNA: 'interna',
                nfe_payload.DESTINO_INTERESTADUAL: 'interestadual',
                nfe_payload.DESTINO_EXTERIOR: 'exterior'}[local]

    def _focus_operacao_do_pedido(self):
        """Operação do pedido de venda que originou a nota, se houver.

        A leitura é defensiva: `sale.order.cfop_id` vem do liber_soc_fiscal_br,
        que **não** é dependência deste módulo. Duas ligações, porque a nota de
        remessa não usa `sale_line_ids` -- ela nasce solta e só guarda o nome do
        pedido em `invoice_origin`.
        """
        self.ensure_one()
        Pedido = self.env.get('sale.order')
        if Pedido is None or 'cfop_id' not in Pedido._fields:
            return self.env['nfe.operacao']
        linhas = self.invoice_line_ids
        cfops = self.env['nfe.cfop']
        if 'sale_line_ids' in linhas._fields:
            cfops = linhas.sale_line_ids.order_id.cfop_id
        if not cfops and self.invoice_origin:
            cfops = Pedido.search(
                [('name', '=', self.invoice_origin)], limit=1).cfop_id
        return cfops[:1]._operacao() if cfops else self.env['nfe.operacao']

    def _focus_operacao_da_nota(self):
        """A operação que rege a nota inteira.

        Em cascata: a que os **impostos** trazem (por onde a posição fiscal a
        entrega), a do pedido de origem, e o padrão da empresa. Um CFOP escrito
        à mão na nota também define a operação, pelo sufixo.
        """
        self.ensure_one()
        if self.nfe_cfop_id:
            return self.nfe_cfop_id._operacao()
        for linha in self._focus_linhas_produto():
            operacao = linha._focus_operacao_do_imposto()
            if operacao:
                return operacao
        return (self.fiscal_position_id.nfe_operacao_id
                or self._focus_operacao_do_pedido()
                or self.company_id.focus_operacao_padrao_id)

    def _focus_cfop_da_operacao(self, operacao, cfop_explicito=None):
        """O CFOP de quatro dígitos que vai sair.

        Um CFOP escolhido à mão vale como está — é o caminho da exportação e de
        qualquer operação que não se deduza. Sem ele, o código nasce da operação
        mais o destino.
        """
        self.ensure_one()
        if cfop_explicito:
            return cfop_explicito.code
        if not operacao:
            return None
        local = self._focus_local_destino()
        codigo = operacao.cfop_para(local)
        if not codigo:
            raise UserError(_(
                "%(fatura)s vai para o exterior, e o CFOP de exportação não se "
                "deduz da operação '%(operacao)s': lá o código significa outra "
                "coisa (5129 é venda de insumo importado, 7129 é venda ao "
                "mercado externo).\n\n"
                "Escolha o CFOP explicitamente no campo 'CFOP da Nota', ou na "
                "linha.",
                fatura=self.display_name, operacao=operacao.display_name))
        return codigo

    def _focus_duplicatas(self):
        """As parcelas da fatura, que na nota viram duplicatas.

        Saem das linhas de prazo do próprio lançamento (`payment_term`), que é
        onde o Odoo guarda vencimento e valor de cada parcela. Assim a nota diz
        a mesma coisa que o contas a receber -- e não uma segunda versão dela.

        Uma remessa em consignação não tem parcela nenhuma, e é isso mesmo:
        nada se paga, e a nota sai sem cobrança.
        """
        self.ensure_one()
        parcelas = self.line_ids.filtered(
            lambda l: l.display_type == 'payment_term')
        moeda = self.currency_id or self.company_id.currency_id
        emissao = self.invoice_date or fields.Date.context_today(self)
        duplicatas = []
        for numero, parcela in enumerate(
                parcelas.sorted(lambda l: (l.date_maturity or l.date, l.id)), start=1):
            valor = abs(parcela.amount_currency or parcela.balance)
            if moeda.is_zero(valor):
                continue
            # Pagamento à vista NÃO tem duplicata, e mandá-la é rejeição:
            # "Dados de cobrança não devem ser informados para pagamento à
            # vista". Uma duplicata só é duplicata se vence DEPOIS da emissão.
            if not parcela.date_maturity or parcela.date_maturity <= emissao:
                continue
            duplicatas.append({
                'numero': '%03d' % numero,
                'data_vencimento': (parcela.date_maturity
                                    and parcela.date_maturity.isoformat() or None),
                'valor': valor,
            })
        return duplicatas

    def _focus_formas_pagamento(self, duplicatas):
        """Como esta nota se paga.

        A Focus assume 01 (dinheiro) quando nada se diz, e livro vendido a
        livraria não se paga em dinheiro no balcão: venda a prazo é duplicata
        mercantil (14). Remessa, consignação e bonificação não se pagam de forma
        nenhuma -- para elas a NFe tem o código 90.
        """
        self.ensure_one()
        if duplicatas:
            return [{'forma_pagamento': nfe_payload.FORMA_DUPLICATA,
                     'valor_pagamento': sum(d['valor'] for d in duplicatas)}]
        # Sem parcela a vencer, mas com valor a receber: é venda à vista. Como
        # se recebe é decisão da casa (dinheiro, boleto, PIX), então é campo da
        # empresa e não palpite meu.
        if not self.currency_id.is_zero(self.amount_total) and self.is_sale_document():
            return [{'forma_pagamento': (self.company_id.focus_forma_pagamento_vista
                                         or nfe_payload.FORMA_DINHEIRO),
                     'valor_pagamento': self.amount_total}]
        # Remessa, consignação, bonificação: nada se paga.
        return [{'forma_pagamento': nfe_payload.FORMA_SEM_PAGAMENTO,
                 'valor_pagamento': 0.0}]

    def _focus_linhas_produto(self):
        """Linhas que viram item da nota: produto de verdade, sem seções.

        `display_type` é obrigatório desde o 17 e vale 'product' na linha de
        mercadoria -- o `not l.display_type` que funcionava até o 16 descarta
        TODAS as linhas aqui, e a nota sai vazia.
        """
        self.ensure_one()
        return self.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product' and l.quantity)

    def _focus_conferir_posicao_fiscal(self):
        """Barra a emissão quando a linha não acompanhou a posição fiscal.

        Trocar a posição fiscal numa fatura que já tem linhas **não** refaz o
        imposto: `_compute_tax_ids` depende de `product_id` e `product_uom_id`,
        não dela. O Odoo avisa na tela (`show_update_fpos` acende o botão
        "Atualizar posição fiscal") e deliberadamente não recomputa sozinho,
        para não destruir uma escolha manual.

        Um aviso, porém, se ignora. Aqui é o último instante antes de a nota ir
        para a SEFAZ, e sair com o CFOP da operação errada é problema fiscal.
        Então o que na tela é aviso, aqui é porta fechada.
        """
        self.ensure_one()
        posicao = self.fiscal_position_id
        if not posicao or not posicao.tax_ids:
            return
        # Os impostos que esta posição fiscal substitui.
        substituidos = posicao.tax_ids.original_tax_ids
        for linha in self._focus_linhas_produto():
            pendentes = linha.tax_ids & substituidos
            if not pendentes:
                continue
            deveriam = posicao.map_tax(pendentes)
            raise UserError(_(
                "A linha '%(linha)s' ainda usa %(atual)s, que a posição fiscal "
                "'%(posicao)s' substitui por %(novo)s.\n\n"
                "A posição fiscal foi escolhida depois da linha, e o imposto "
                "não acompanhou — a nota sairia com o CFOP da operação errada. "
                "Use o botão 'Atualizar posição fiscal' na fatura, ou corrija o "
                "imposto da linha.",
                linha=linha.name or linha.product_id.display_name,
                atual=', '.join(pendentes.mapped('name')),
                posicao=posicao.display_name,
                novo=', '.join(deveriam.mapped('name')) or _('outro imposto')))

    def _focus_informacoes_adicionais(self):
        """O que vai em DADOS ADICIONAIS da DANFE.

        O número do pedido entra aqui porque é por ele que o cliente casa a
        nota com a compra que fez: a livraria confere o romaneio contra o
        pedido dela, não contra o número da nota, que ela nunca viu antes.
        A observação escrita à mão na fatura vem junto, quando existe.
        """
        self.ensure_one()
        partes = []
        pedido = self.invoice_origin or ', '.join(
            self.invoice_line_ids.sale_line_ids.order_id.mapped('name'))
        if pedido:
            partes.append('Pedido: %s' % pedido)
        if self.narration:
            partes.append(html2plaintext(self.narration).strip())
        return '\n'.join(p for p in partes if p) or None

    def _focus_modalidade_frete(self):
        """A modalidade que vai na nota, como inteiro do modFrete.

        Vazio é 9 de propósito: a fatura sem transporte declarado (o acerto
        de consignação, a nota de serviço) sai como "sem ocorrência", que é
        o comportamento que o módulo sempre teve.
        """
        self.ensure_one()
        return (int(self.nfe_modalidade_frete)
                if self.nfe_modalidade_frete else nfe_payload.FRETE_SEM)

    def _focus_build_payload(self):
        """Payload completo da NFe desta fatura."""
        self.ensure_one()
        self._focus_conferir_posicao_fiscal()
        company = self.company_id
        linhas = self._focus_linhas_produto()
        if not linhas:
            raise UserError(_(
                "A fatura %s não tem linha de produto para emitir.", self.display_name))

        # A operação da nota decide natureza, finalidade e tributação. Ela vem
        # do CFOP -- da nota, do pedido de origem, ou o padrão da empresa.
        operacao_nota = self._focus_operacao_da_nota()
        fiscal = operacao_nota._focus_fiscal(company)

        itens = [self._focus_item_data(linha, i, fiscal)
                 for i, linha in enumerate(linhas, start=1)]

        consumidor_final = fiscal.get('consumidor_final')
        if consumidor_final is None:
            consumidor_final = 1 if self.partner_id.nfe_indicador_ie == '9' else 0

        # O primeiro dígito do CFOP diz o sentido: 1/2/3 entra, 5/6/7 sai. Uma
        # devolução de consignação (1918) é ENTRADA mesmo sendo nós a emitir a
        # nota -- e sair como saída inverte a operação para a SEFAZ.
        tipo_documento = (nfe_payload.ENTRADA
                          if operacao_nota.sentido == 'entrada'
                          else nfe_payload.SAIDA)

        finalidade = fiscal.get('finalidade') or nfe_payload.FINALIDADE_NORMAL
        referencias = self._focus_chaves_referenciadas()
        if finalidade == nfe_payload.FINALIDADE_DEVOLUCAO and not referencias:
            raise UserError(_(
                "%(fatura)s é uma devolução (CFOP %(cfop)s) e não aponta a "
                "nota de origem. Sem a chave da nota devolvida a SEFAZ não "
                "sabe o que está sendo devolvido — preencha 'Nota de origem' "
                "na aba NFe.",
                fatura=self.display_name,
                cfop=operacao_nota.display_name or '?'))

        duplicatas = self._focus_duplicatas()
        nota = {
            'duplicatas': duplicatas,
            'numero_fatura': self.name or None,
            'formas_pagamento': self._focus_formas_pagamento(duplicatas),
            'natureza_operacao': (fiscal.get('natureza_operacao')
                                  or 'Venda de mercadoria'),
            'data_emissao': self._focus_data_emissao(),
            'tipo_documento': tipo_documento,
            'notas_referenciadas': referencias,
            'finalidade_emissao': finalidade,
            # Consumidor final e presença do comprador mudam a validação do
            # ICMS de destino; venda para revenda (livraria) não é consumidor
            # final, e a operação não é presencial.
            'consumidor_final': consumidor_final,
            'presenca_comprador': nfe_payload.PRESENCA_OUTROS,
            'modalidade_frete': self._focus_modalidade_frete(),
            'volumes': self.nfe_volumes,
            'especie_volumes': self.nfe_especie_volumes,
            'peso_bruto': self.nfe_peso_bruto,
            'informacoes_adicionais': self._focus_informacoes_adicionais(),
        }

        destinatario = self.partner_id._focus_destinatario_data()
        # Em homologação o nome do destinatário é imposto pela SEFAZ. Trocá-lo
        # aqui, e não no cadastro, deixa o cliente real intacto -- e é o que
        # permite testar a emissão com uma fatura de verdade.
        if (self.focus_ambiente or company.sudo().focus_ambiente) == 'homologacao':
            destinatario['nome'] = nfe_payload.NOME_DESTINATARIO_HOMOLOGACAO

        # A transportadora só entra quando a modalidade declara transporte:
        # com 9 (sem ocorrência) o grupo não viaja, ainda que o campo esteja
        # preenchido -- nomear quem carrega uma carga que oficialmente não
        # anda é contradição na nota.
        transportador = None
        if (self.nfe_transportadora_id
                and self._focus_modalidade_frete() != nfe_payload.FRETE_SEM):
            transportador = \
                self.nfe_transportadora_id._focus_transportador_data()

        payload = nfe_payload.build_payload(
            nota=nota,
            emitente=company._focus_emitente_data(),
            destinatario=destinatario,
            itens=itens,
            transportador=transportador,
        )

        faltando = nfe_payload.missing_fields(payload)
        if faltando:
            raise UserError(_(
                "Faltam dados para emitir a NFe de %(fatura)s:\n\n%(campos)s\n\n"
                "Confira o cadastro da empresa, do cliente e dos produtos.",
                fatura=self.display_name, campos='\n'.join('- %s' % c for c in faltando)))

        # A numeração entra POR ÚLTIMO, e de propósito: só depois de o payload
        # passar pela conferência. Reservar antes queimaria um número a cada
        # tentativa que morresse por cadastro incompleto -- e buraco em
        # numeração fiscal se explica à SEFAZ, não ao programador.
        self._focus_aplicar_numeracao(payload)
        return payload

    def _focus_aplicar_numeracao(self, payload):
        """Põe `serie` e `numero` no payload quando a numeração é nossa.

        Sem numeração configurada na empresa, não mexe em nada e quem numera
        é a Focus -- que é como sempre funcionou e segue valendo para as
        outras empresas da casa.

        REEMISSÃO REUSA O NÚMERO. Uma nota rejeitada pela SEFAZ (cadastro do
        destinatário errado, imposto fora da regra) volta para a fila e é
        reenviada; se cada tentativa tirasse um número novo, uma rejeição
        boba abriria buraco na sequência. Rejeição não consome número na
        SEFAZ, então reusar é o certo.
        """
        self.ensure_one()
        company = self.company_id.sudo()
        ambiente = self.focus_ambiente or company.focus_ambiente

        if self.focus_numero and self.focus_serie:
            payload['numero'] = int(self.focus_numero)
            payload['serie'] = int(self.focus_serie)
            return

        serie, numero = self.company_id._nfe_reservar_numero(ambiente)
        if not (serie and numero):
            return

        payload['numero'] = numero
        payload['serie'] = serie
        # Gravado na fatura na hora: é o que faz a reemissão reusar, e é onde
        # alguém vai olhar quando a SEFAZ reclamar de número repetido.
        self.sudo().write({'focus_numero': str(numero), 'focus_serie': str(serie)})

    # ------------------------------------------------------------------
    # ações
    # ------------------------------------------------------------------
    def action_focus_emitir(self):
        """Envia a nota para a Focus. Assíncrono: volta 'processando'."""
        for move in self:
            if move.state != 'posted':
                raise UserError(_(
                    "Só se emite NFe de fatura lançada. %s ainda está em "
                    "rascunho.", move.display_name))
            if move.focus_status in ('autorizado', 'processando_autorizacao'):
                raise UserError(_(
                    "%(fatura)s já foi enviada (%(status)s). Use 'Consultar' "
                    "para atualizar o status.",
                    fatura=move.display_name, status=move.focus_status))
            # A nota desta fatura JÁ EXISTE: ela nasceu de um XML autorizado
            # (Olist e afins) e o painel a segura. Emitir pela Focus criaria
            # uma SEGUNDA NFe para a mesma venda na SEFAZ -- duplicação
            # fiscal, não reemissão. O botão some da tela pela view; esta é a
            # porta de dentro, para o caminho por código ou lista.
            if move.nfe_xml_panel_id and not move.nfe_xml_panel_id.is_cancelled:
                raise UserError(_(
                    "%(fatura)s já tem NFe autorizada de origem externa "
                    "(nº %(numero)s). O XML está no painel — veja o botão "
                    "'NFe XML' da fatura. Emitir pela Focus criaria uma "
                    "segunda nota para a mesma venda na SEFAZ.",
                    fatura=move.display_name,
                    numero=move.nfe_danfe_no or move.nfe_key))

            payload = move._focus_build_payload()
            ref = move._focus_ref_para_emissao()
            ambiente = move.company_id.sudo().focus_ambiente

            move.write({'focus_ref': ref, 'focus_ambiente': ambiente})
            try:
                resposta = move.company_id._focus_client().emitir_nfe(ref, payload)
            except FocusValidationError as exc:
                # Sem gravar nada antes de levantar: o UserError desfaz a
                # transação inteira, então um `write` aqui iria pelo ralo e só
                # daria a impressão de ter sido salvo. A mensagem vai na caixa
                # de diálogo, e a nota continua 'não enviada' -- que é a verdade,
                # porque a Focus a recusou antes de mandá-la à SEFAZ.
                raise UserError(_("Focus NFe recusou a nota:\n\n%s", exc.message)) from exc
            except FocusError as exc:
                raise UserError(_("Focus NFe: %s", exc.message)) from exc

            move._focus_aplicar_resposta(resposta)
            _logger.info("NFe %s enviada à Focus (%s): %s",
                         move.display_name, ambiente, move.focus_status)
        return True

    def action_focus_consultar(self):
        """Pergunta à Focus em que pé está a nota e aplica o que voltar."""
        for move in self:
            if not move.focus_ref:
                raise UserError(_(
                    "%s ainda não foi enviada à Focus NFe.", move.display_name))
            try:
                resposta = move._focus_client_da_nota().consultar_nfe(move.focus_ref)
            except FocusNotFound:
                move.write({
                    'focus_status': 'nao_enviado',
                    'focus_mensagem': _(
                        "A Focus não conhece a referência %s neste ambiente. "
                        "A nota não chegou a ser aceita.", move.focus_ref),
                })
                continue
            except FocusError as exc:
                raise UserError(_("Focus NFe: %s", exc.message)) from exc
            move._focus_aplicar_resposta(resposta)
        return True

    def action_focus_carta_correcao(self):
        """Abre o assistente da CC-e.

        A carta de correção conserta erro de REDAÇÃO numa nota já autorizada —
        e só isso. Valor, imposto, data de emissão, remetente e destinatário
        não se corrigem por carta: a nota errada se cancela e se emite outra.
        """
        self.ensure_one()
        if self.focus_status != STATUS_AUTORIZADO:
            raise UserError(_(
                "Só se corrige nota autorizada. %(fatura)s está como "
                "%(status)s.", fatura=self.display_name, status=self.focus_status))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Carta de Correção'),
            'res_model': 'nfe.focus.correcao.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_id': self.id},
        }

    def action_focus_cancelar(self):
        """Abre o assistente que pede a justificativa (15 a 255 caracteres)."""
        self.ensure_one()
        if self.focus_status != STATUS_AUTORIZADO:
            raise UserError(_(
                "Só se cancela nota autorizada. %(fatura)s está como "
                "%(status)s.", fatura=self.display_name, status=self.focus_status))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cancelar NFe'),
            'res_model': 'nfe.focus.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_id': self.id},
        }

    # ------------------------------------------------------------------
    # resposta
    # ------------------------------------------------------------------
    def _focus_client_da_nota(self):
        """Cliente no ambiente em que ESTA nota foi enviada.

        Não é o mesmo que o ambiente atual da empresa: quem passou de
        homologação para produção ainda precisa consultar as notas velhas onde
        elas estão.
        """
        self.ensure_one()
        company = self.company_id.sudo()
        ambiente = self.focus_ambiente or company.focus_ambiente
        if ambiente == company.focus_ambiente:
            return self.company_id._focus_client()
        token = (company.focus_token_producao if ambiente == 'producao'
                 else company.focus_token_homologacao)
        if not token:
            raise UserError(_(
                "Esta nota foi enviada em %(ambiente)s, mas não há token "
                "configurado para esse ambiente.", ambiente=ambiente))
        return FocusClient(token, ambiente=ambiente)

    def _focus_chave_de_acesso(self, resposta):
        """Extrai a chave de acesso limpa do que a Focus devolveu.

        A Focus manda `chave_nfe` **prefixada com "NFe"**
        (`NFe35260712345678000195...`), que é como a chave aparece no código de
        barras do DANFE. O `account.move.nfe_key` do liber_nfe_xml exige 44
        dígitos e nada mais -- gravar o prefixo levanta ValidationError e
        derruba a consulta inteira, inclusive a de uma nota autorizada.

        Devolve None quando o que veio não são 44 dígitos: chave malformada não
        entra no índice, e a nota fica com o status certo mesmo assim.
        """
        self.ensure_one()
        digitos = re.sub(r'\D', '', resposta.get('chave_nfe') or '')
        if not digitos:
            return None
        if len(digitos) != 44:
            _logger.warning(
                "NFe %s: a Focus devolveu uma chave com %d dígitos (%r); "
                "esperados 44. Chave não gravada.",
                self.display_name, len(digitos), resposta.get('chave_nfe'))
            return None
        return digitos

    def _focus_aplicar_resposta(self, resposta):
        """Grava na fatura o que a Focus devolveu."""
        self.ensure_one()
        if not isinstance(resposta, dict):
            return

        status_anterior = self.focus_status
        status = resposta.get('status') or STATUS_PROCESSANDO
        valores = {
            'focus_status': status,
            'focus_mensagem': resposta.get('mensagem_sefaz')
            or resposta.get('mensagem') or False,
            'focus_protocolo': resposta.get('protocolo')
            or resposta.get('numero_protocolo') or False,
        }
        # Número e série só se ESCREVEM quando a resposta os traz. Antes eles
        # eram sobrescritos sempre, e uma rejeição (que não traz número)
        # apagava o que já estava lá. Isso não incomodava enquanto quem
        # numerava era a Focus -- não havia nada nosso para perder. Passou a
        # incomodar em 12/08/2026: com a numeração da casa, o número é
        # reservado ANTES do envio e gravado na fatura, e apagá-lo na
        # rejeição faria a tentativa seguinte tirar um número novo, deixando
        # o anterior órfão. Buraco em numeração fiscal se explica à SEFAZ.
        if resposta.get('numero'):
            valores['focus_numero'] = resposta['numero']
        if resposta.get('serie'):
            valores['focus_serie'] = resposta['serie']
        valores['focus_danfe_url'] = (resposta.get('caminho_danfe')
                                      or resposta.get('url_danfe') or False)

        # A chave só se grava quando a nota existe de fato na SEFAZ. Gravar a
        # chave de uma nota rejeitada envenenaria o índice do liber_nfe_xml.
        chave = self._focus_chave_de_acesso(resposta)
        if chave and status in (STATUS_AUTORIZADO, STATUS_CANCELADO):
            valores['nfe_key'] = chave

        self.write(valores)
        if status != status_anterior:
            self._focus_registrar_no_historico(status, resposta)

        # Também no cancelamento: é lá que nasce o XML do evento, e ele tem de
        # chegar ao painel como qualquer outro documento fiscal.
        if status in (STATUS_AUTORIZADO, STATUS_CANCELADO):
            self._focus_guardar_documentos(resposta)

    def _focus_registrar_no_historico(self, status, resposta):
        """Deixa no histórico da fatura o que a SEFAZ respondeu.

        Sem isto, uma nota rejeitada não deixava rastro nenhum: a mensagem
        aparecia na tela e sumia com ela, e semanas depois ninguém sabia por que
        aquela nota nunca saiu. O status ficava no campo, mas o campo guarda o
        estado de agora, não a história.

        Só na mudança de estado, e só do que a SEFAZ de fato devolveu: repetir a
        mesma linha a cada consulta do cron transformaria o histórico em ruído.
        """
        self.ensure_one()
        motivo = resposta.get('mensagem_sefaz') or resposta.get('mensagem') or ''
        codigo = resposta.get('status_sefaz') or ''
        chave = self.nfe_key or self._focus_chave_de_acesso(resposta) or ''

        # `Markup` de propósito: desde o 16 o Odoo escapa corpo de mensagem que
        # não seja marcado como HTML, e a mensagem sairia com as tags à mostra.
        # O `%` do Markup ainda escapa os VALORES, então a mensagem da SEFAZ não
        # vira injeção.
        if status == STATUS_AUTORIZADO:
            corpo = Markup(_(
                "<p><b>NFe autorizada pela SEFAZ.</b></p>"
                "<ul>"
                "<li>Chave de acesso: <code>%(chave)s</code></li>"
                "<li>Número %(numero)s, série %(serie)s</li>"
                "<li>Protocolo: %(protocolo)s</li>"
                "</ul><p>%(motivo)s</p>")) % {
                    'chave': chave, 'numero': self.focus_numero or '?',
                    'serie': self.focus_serie or '?',
                    'protocolo': self.focus_protocolo or '?', 'motivo': motivo}
        elif status in ('erro_autorizacao', 'denegado'):
            rotulo = _("denegada") if status == 'denegado' else _("rejeitada")
            corpo = Markup(_(
                "<p><b>NFe %(rotulo)s pela SEFAZ.</b></p>"
                "<p>%(codigo)s%(motivo)s</p>"
                "<p>A nota <b>não</b> existe na SEFAZ. Corrija o apontado acima "
                "e emita de novo — a referência é a mesma, então não haverá "
                "nota em duplicidade.</p>")) % {
                    'rotulo': rotulo,
                    'codigo': ('[%s] ' % codigo) if codigo else '',
                    'motivo': motivo}
        elif status == STATUS_CANCELADO:
            corpo = Markup(_(
                "<p><b>NFe cancelada na SEFAZ.</b></p><p>%(motivo)s</p>")) % {
                    'motivo': motivo}
        else:
            return

        self.message_post(body=corpo, subtype_xmlid='mail.mt_note')

    def _focus_guardar_documentos(self, resposta):
        """Baixa os XMLs e o DANFE, e os entrega ao painel de XMLs.

        Anexar à fatura não basta: o `liber_nfe_xml` é onde a casa junta TODOS
        os XMLs -- os que chegam de fornecedores e, a partir daqui, os que nós
        emitimos. Uma nota emitida e uma nota recebida passam a estar no mesmo
        lugar, procuráveis pela mesma chave.

        Três documentos, e os três importam:
          - o XML da nota autorizada  -> vira `nfe.xml.panel`
          - o XML do cancelamento     -> vira `nfe.xml.cancel.event`
          - o XML da carta de correção-> idem, o painel roteia por `tpEvento`

        Falha aqui não derruba a emissão: a nota já está autorizada na SEFAZ, e
        um documento que não baixou se busca de novo na próxima consulta.
        """
        self.ensure_one()
        try:
            client = self._focus_client_da_nota()
        except UserError:
            return

        def baixar(campo):
            caminho = resposta.get(campo)
            if not caminho:
                return None
            try:
                return client.baixar(caminho)
            except FocusError as exc:
                _logger.warning("NFe %s: falha ao baixar %s: %s",
                                self.display_name, campo, exc)
                return None

        # -- anexos na fatura, para quem está olhando a fatura --------
        for campo, sufixo, mimetype in (
            ('caminho_xml_nota_fiscal', '.xml', 'application/xml'),
            ('caminho_danfe', '.pdf', 'application/pdf'),
        ):
            conteudo = baixar(campo)
            if not conteudo:
                continue
            nome = '%s%s' % (self.focus_ref, sufixo)
            if self.env['ir.attachment'].search_count([
                    ('res_model', '=', 'account.move'), ('res_id', '=', self.id),
                    ('name', '=', nome)]):
                continue
            self.env['ir.attachment'].create({
                'name': nome, 'datas': base64.b64encode(conteudo),
                'mimetype': mimetype, 'res_model': 'account.move',
                'res_id': self.id,
            })

        # -- o painel de XMLs, para quem está olhando a casa ----------
        self._focus_registrar_no_painel(resposta, baixar)

    def _focus_registrar_no_painel(self, resposta, baixar):
        """Entrega os XMLs ao `liber_nfe_xml`, que já sabe lê-los."""
        self.ensure_one()
        Painel = self.env['nfe.xml.panel'].sudo()
        chave = self._focus_chave_de_acesso(resposta) or self.nfe_key

        xml_nota = baixar('caminho_xml_nota_fiscal')
        if xml_nota and chave:
            # A chave é única no painel: reemitir a mesma nota não cria outra
            # linha, completa a que existe.
            painel = Painel.search([('key', '=', chave)], limit=1)
            valores = {
                'file': base64.b64encode(xml_nota),
                'file_name': '%s-nfe.xml' % chave,
                'invoice_id': self.id,
                'company_id': self.company_id.id,
                # Os três campos que dizem, por ângulos diferentes, que esta
                # nota é nossa -- e que ficavam nos padrões de nota recebida,
                # porque ninguém os escrevia. O painel juntava tudo no mesmo
                # balaio: das 40.845 linhas do prod, as 18 que a casa emitiu
                # eram indistinguíveis das 40.827 que chegaram de terceiros.
                #   source          quem trouxe o XML (a Focus, nesta emissão)
                #   system_generated  nasceu aqui dentro, não veio de fora
                #   xml_type        documento da casa, não documento recebido
                # Escrevemos os três mesmo quando a linha já existe: a nota
                # que emitimos volta pela varredura da SEFAZ e pode ter chegado
                # primeiro por lá. Quem emitiu continua sendo a casa, e é isso
                # que o painel precisa dizer -- a origem anterior está no
                # rastro do próprio registro.
                'source': 'focus',
                'system_generated': True,
                'xml_type': 'internal',
            }
            if painel:
                painel.write(valores)
            else:
                # status 'imported' é o que o cron do painel procura para
                # extrair itens, CFOP, partes e valores.
                Painel.create(dict(valores, key=chave, status='imported'))

        # Cancelamento: o painel tem modelo próprio para isso e marca a NFe
        # como cancelada.
        xml_cancel = baixar('caminho_xml_cancelamento')
        if xml_cancel:
            Painel.register_cancellation_event(
                xml_cancel, file_name='%s-cancelamento.xml' % (chave or self.focus_ref),
                company_id=self.company_id.id)

        # Carta de correção: NÃO vai no `nfe.xml.cancel.event`. Aquele modelo é
        # de cancelamento -- aceita só 110111 e 110112, e gravar a carta lá
        # marcaria a nota como cancelada, que é o oposto do que a carta faz.
        # Enquanto o `liber_nfe_xml` não tiver modelo de evento genérico, a
        # carta fica anexada ao painel da própria NFe: agrupada com ela,
        # achável pela mesma chave, e sem mentir sobre o que é.
        xml_carta = baixar('caminho_xml_carta_correcao')
        if xml_carta and chave:
            painel = Painel.search([('key', '=', chave)], limit=1)
            if painel:
                nome = '%s-carta-correcao.xml' % chave
                if not self.env['ir.attachment'].sudo().search_count([
                        ('res_model', '=', 'nfe.xml.panel'),
                        ('res_id', '=', painel.id), ('name', '=', nome)]):
                    self.env['ir.attachment'].sudo().create({
                        'name': nome, 'datas': base64.b64encode(xml_carta),
                        'mimetype': 'application/xml',
                        'res_model': 'nfe.xml.panel', 'res_id': painel.id,
                    })

    # ------------------------------------------------------------------
    # os documentos da nota, para quem os pede de fora
    # ------------------------------------------------------------------
    def _liber_documentos_da_nfe(self):
        """DANFE e XML da nota autorizada, nesta ordem.

        São os dois anexos que o `_focus_guardar_documentos` grava na fatura.
        O nome deles é a referência da emissão, que ganha sufixo `-R2` depois
        de uma rejeição -- procurar pela referência ATUAL é o que devolve os
        documentos da nota que vale, e não os da tentativa que a SEFAZ recusou.

        Nota não autorizada não tem documento: enquanto a SEFAZ não autoriza,
        não existe DANFE nem XML, e o que houver na fatura é de outra coisa.
        """
        self.ensure_one()
        nota = self._origin
        if nota.focus_status != STATUS_AUTORIZADO or not nota.focus_ref:
            return self.env['ir.attachment']
        documentos = self.env['ir.attachment'].search([
            ('res_model', '=', 'account.move'), ('res_id', '=', nota.id),
            ('name', 'in', ['%s.pdf' % nota.focus_ref,
                            '%s.xml' % nota.focus_ref]),
        ])
        # DANFE primeiro: é o que se abre para olhar. O XML é para arquivar.
        return documentos.sorted(lambda anexo: not anexo.name.endswith('.pdf'))

    def _liber_nome_do_documento(self, anexo):
        """O nome com que o documento chega a quem recebe a nota.

        Dentro de casa o anexo se chama pela referência da emissão
        (`LIBER-3-14512.pdf`), que é o que dá idempotência ao download e não
        diz nada a ninguém de fora. Para o cliente, o DANFE se procura pelo
        número da nota e o XML pela chave de acesso -- é assim que o contador
        dele arquiva, e é o nome que o programa dele espera.

        Quem é qual se decide pelo SUFIXO, não pelo mimetype: o Odoo rebaixa
        todo anexo parecido com XML para `text/plain` quando quem grava não é
        usuário de sistema (é a proteção contra HTML injetado, no
        `ir.attachment._check_contents`), e a emissão roda no usuário que
        clicou. Olhando o mimetype, o XML da nota emitida em produção não seria
        reconhecido -- e sairia no e-mail com a referência interna no nome.

        Sem número ou sem chave, o nome guardado segue como está: um anexo com
        nome feio é melhor do que um anexo que não vai.
        """
        self.ensure_one()
        if not self.focus_ref:
            return anexo.name
        if anexo.name == '%s.pdf' % self.focus_ref and self.focus_numero:
            return 'DANFE-%s.pdf' % self.focus_numero
        if anexo.name == '%s.xml' % self.focus_ref and self.nfe_key:
            return '%s-nfe.xml' % self.nfe_key
        return anexo.name

    # ------------------------------------------------------------------
    # cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_focus_consultar_pendentes(self, limite=100):
        """Consulta as notas que ainda estão processando.

        Uma nota por transação: se a Focus derrubar a conexão na terceira, as
        duas primeiras já estão salvas.
        """
        pendentes = self.search([
            ('focus_ref', '!=', False),
            ('focus_status', 'in', list(FOCUS_PENDENTES)),
        ], limit=limite)
        for move in pendentes:
            try:
                move.action_focus_consultar()
                move.env.cr.commit()  # pylint: disable=invalid-commit
            except Exception as exc:  # noqa: BLE001 - o cron não pode morrer
                move.env.cr.rollback()
                _logger.warning("NFe %s: consulta falhou: %s", move.display_name, exc)
        return True


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    nfe_cfop_id = fields.Many2one(
        'nfe.cfop', string='CFOP',
        help="CFOP desta linha. Vazio usa o CFOP padrão da empresa para a "
             "operação (dentro do estado ou interestadual).")
    def _focus_operacao_do_imposto(self):
        """Operação que os impostos desta linha carregam.

        É por aqui que a **posição fiscal** entrega o CFOP: ela substitui o
        imposto, o imposto traz o CFOP, e nada mais precisa ser configurado.
        Foi o mecanismo que o sistema em produção usou em 110 mil linhas.

        Com mais de um imposto marcado na linha, vence o primeiro — a ordem é a
        do próprio campo. Linha com dois CFOPs diferentes é erro de cadastro, e
        um erro que a SEFAZ não tem como apontar: por isso o CFOP fica visível
        na linha da fatura.
        """
        self.ensure_one()
        operacoes = self.tax_ids.nfe_operacao_id
        return operacoes[:1]

    nfe_item_referenciado = fields.Integer(
        string='Item da nota de origem',
        help="Numa devolução, qual item da nota original esta linha devolve. "
             "Vazio procura pelo produto na nota de origem — preencha quando "
             "o mesmo produto aparece em mais de uma linha lá.")
