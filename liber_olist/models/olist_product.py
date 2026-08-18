# -*- coding: utf-8 -*-

import json
import logging
import re
import time
import unicodedata

from odoo import _, api, fields, models, modules, tools
from odoo.exceptions import UserError

from . import olist_client

_logger = logging.getLogger(__name__)


class OlistProduct(models.Model):
    """O espelho do catálogo do Olist — o que ELES dizem, guardado à parte.

    Este modelo não é o produto: é a leitura do produto lá, com a data em que
    foi lida. A separação é o ponto. Enquanto o saldo do Olist for um campo
    calculado na hora, ninguém consegue responder "o que está diferente?" sem
    bater na API, e a tela de conferência não existe. Guardado, dá para
    ordenar por divergência, filtrar, e escolher o que sincronizar.

    A comparação é sempre entre três números:

        saldo_olist   o que o Olist tem hoje (lido, com data)
        odoo_qty      o estoque do armazém desta empresa (o "Estoque" da ficha)
        qty_to_send   odoo_qty menos a margem de segurança, piso zero

    `divergencia = saldo_olist - qty_to_send` é o que a tela ordena. Divergência
    **avisa e não reescreve**: sincronizar é ação de gente, sobre linhas
    escolhidas. Ver liber_olist/NOTES.md §11.
    """
    _name = 'olist.product'
    _description = "Espelho de produto do Olist"
    _order = 'divergencia_abs desc, name'
    _rec_name = 'name'

    account_id = fields.Many2one(
        'olist.account', string="Conta", required=True, ondelete='cascade',
        index=True)
    company_id = fields.Many2one(
        related='account_id.company_id', store=True, index=True)
    olist_id = fields.Char("ID Olist", required=True, index=True,
                           help="Id interno do produto no Olist — a chave que "
                                "o endpoint de estoque aceita (o ISBN não).")
    codigo = fields.Char("Código (ISBN)", index=True)
    name = fields.Char("Nome no Olist")
    situacao = fields.Char("Situação")

    saldo_olist = fields.Float("Olist", digits='Product Unit of Measure')
    saldo_olist_date = fields.Datetime("Lido em", readonly=True)
    # Zero que nunca foi lido e zero de verdade são coisas diferentes, e na
    # tela apareciam idênticos: 580 livros marcando 0,00 porque a semeadura
    # nunca havia rodado, lidos como "o Olist está sem estoque" (18/08/2026).
    # A coluna passa a mostrar traço enquanto não houver leitura.
    saldo_olist_texto = fields.Char(
        "Olist", compute='_compute_saldo_olist_texto',
        help="O saldo que o Olist informou na última leitura. Traço significa "
             "que este livro ainda NÃO teve o saldo lido — não que ele esteja "
             "zerado lá.")

    @api.depends('saldo_olist', 'saldo_olist_date')
    def _compute_saldo_olist_texto(self):
        for linha in self:
            if not linha.saldo_olist_date:
                linha.saldo_olist_texto = "—"
            else:
                linha.saldo_olist_texto = "%g" % linha.saldo_olist

    # ------------------------------------------------------------------
    # A ficha do livro no Olist (produto.obter) — o que ELES sabem dele
    # ------------------------------------------------------------------
    # Guardados como campos, e não só no JSON cru, os que servem para DECIDIR:
    # preço (para comparar com o nosso), situação (ativo/inativo lá), e a
    # identidade editorial (marca, categoria, NCM, peso) que é onde se vê que
    # um cadastro está torto. O resto fica no `ficha_json`, íntegro.
    preco_olist = fields.Float("Preço no Olist")
    preco_promocional = fields.Float("Preço promocional")
    preco_custo = fields.Float("Preço de custo")
    situacao_olist = fields.Selection([
        ('A', "Ativo"), ('I', "Inativo"),
    ], string="Situação no Olist", index=True)
    gtin = fields.Char("GTIN/EAN no Olist",
                       help="Para livro, o ISBN-13 É o EAN-13. Vazio aqui "
                            "quer dizer que o marketplace não tem por onde "
                            "identificar o livro além do nosso código.")
    marca = fields.Char("Marca/Selo")
    categoria = fields.Char("Categoria")
    ncm = fields.Char("NCM")
    unidade = fields.Char("Unidade")
    peso_liquido = fields.Float("Peso líquido (kg)")
    peso_bruto = fields.Float("Peso bruto (kg)")
    descricao = fields.Html("Descrição no Olist", sanitize=False)
    ficha_lida_em = fields.Datetime("Ficha lida em", readonly=True)
    ficha_json = fields.Text(
        "Ficha crua", readonly=True,
        help="A ficha do Olist como veio, com os 52 campos. Nunca editada e "
             "nunca lida por lógica de negócio: é o que se devolve inteiro "
             "quando se altera um campo só, e é a prova do que estava lá.")

    preco_odoo = fields.Float(
        "Preço no Odoo", compute='_compute_preco', store=True,
        help="O preço de venda do produto casado.")
    divergencia_preco = fields.Float(
        "Diferença de preço", compute='_compute_preco', store=True,
        help="Preço no Olist menos o preço no Odoo. Positivo: o marketplace "
             "está cobrando mais caro do que a nossa tabela.")

    field_ids = fields.One2many(
        'olist.product.field', 'mirror_id', string="Ficha completa",
        help="Os demais campos da ficha do Olist, como pares chave/valor. Os "
             "que já têm coluna própria não se repetem aqui.")

    last_write_result = fields.Text(
        "Última escrita no Olist", readonly=True, copy=False,
        help="O que foi enviado e o que voltou na última alteração de ficha.")

    product_id = fields.Many2one(
        'product.product', string="Produto no Odoo", index='btree_not_null',
        help="Casado pelo ISBN (código de barras) ou à mão. Vazio quer dizer "
             "que o Odoo não tem esse código — e então a sincronia NÃO toca "
             "neste livro, ele segue no Olist com o número que já tinha.")
    product_tmpl_id = fields.Many2one(
        related='product_id.product_tmpl_id', store=True, index=True,
        string="Ficha do produto",
        help="O caminho de volta: é por ele que a ficha do livro no Odoo sabe "
             "se está espelhada no Olist — e portanto quais livros nossos "
             "ainda não estão à venda lá.")
    match_origin = fields.Selection([
        ('isbn', "Por ISBN"),
        ('manual', "À mão"),
    ], string="Casamento", readonly=True, index=True,
        help="Como este livro foi casado. 'À mão' é protegido: a próxima "
             "leitura do catálogo NÃO o desfaz — senão o trabalho de casar "
             "seiscentos livros evaporaria no dia seguinte.")
    suggested_product_id = fields.Many2one(
        'product.product', string="Sugestão", readonly=True,
        help="Candidato encontrado pelo TÍTULO, para os que não casam por "
             "ISBN. É sugestão, não casamento: quem decide é gente. Metade do "
             "catálogo do Olist é livro que já existe no Odoo com outro ISBN "
             "(reedição), e é isso que esta coluna encontra.")

    odoo_qty = fields.Float(
        "Odoo", compute='_compute_comparacao',
        digits='Product Unit of Measure',
        help="Estoque na área de estoque do armazém desta empresa — o mesmo "
             "número que a ficha do produto mostra em 'Estoque'.")
    qty_to_send = fields.Float(
        "Enviaria", compute='_compute_comparacao',
        digits='Product Unit of Measure',
        help="O que a sincronia mandaria: estoque do armazém menos a margem "
             "de segurança da conta, com piso em zero.")
    divergencia = fields.Float(
        "Divergência", compute='_compute_comparacao', store=True,
        digits='Product Unit of Measure',
        help="Saldo no Olist menos o que enviaríamos. Positivo: o Olist está "
             "oferecendo mais do que temos (risco de venda a descoberto).")
    divergencia_abs = fields.Float(compute='_compute_comparacao', store=True)

    # ------------------------------------------------------------------
    # O que este livro VENDEU no Olist — a régua para decidir o que casar
    # ------------------------------------------------------------------
    order_line_ids = fields.One2many('olist.order.line', 'mirror_id',
                                     string="Itens vendidos")
    sold_qty = fields.Float(
        "Vendido", compute='_compute_vendas', store=True,
        digits='Product Unit of Measure',
        help="Exemplares vendidos nos pedidos do Olist já detalhados, fora os "
             "cancelados.\n"
             "ATENÇÃO à cobertura: só entra pedido cujo DETALHE foi lido — é "
             "o detalhe que traz os itens. Enquanto a varredura não terminar, "
             "este número é um piso, não o total.")
    sold_orders = fields.Integer(
        "Pedidos", compute='_compute_vendas', store=True,
        help="Em quantos pedidos este livro apareceu.")
    last_sale_date = fields.Date(
        "Última venda", compute='_compute_vendas', store=True)

    duplicate_match = fields.Boolean(
        "Mesmo livro em outra linha", compute='_compute_duplicate_match',
        store=True, index='btree_not_null',
        help="Duas linhas do Olist casadas com o MESMO produto do Odoo — no "
             "catálogo real isso acontece com edições de capa diferente "
             "(Aríete cinza e vinho são um livro só aqui). Enviar estoque para "
             "as duas ofereceria o mesmo exemplar duas vezes, então o envio "
             "recusa até alguém decidir como dividir.")

    state = fields.Selection([
        ('sem_produto', "Sem produto no Odoo"),
        ('igual', "Igual"),
        ('olist_maior', "Olist oferece a mais"),
        ('olist_menor', "Olist oferece a menos"),
    ], string="Situação da comparação", compute='_compute_comparacao',
        store=True, index=True)

    last_push_date = fields.Datetime("Último envio", readonly=True)
    last_push_qty = fields.Float("Quantidade enviada", readonly=True,
                                 digits='Product Unit of Measure')
    last_push_result = fields.Text("Resposta do último envio", readonly=True)

    _olist_id_account_uniq = models.Constraint(
        'unique(account_id, olist_id)',
        "Este produto do Olist já está espelhado nesta conta.")

    @api.depends('preco_olist', 'product_id', 'product_id.list_price')
    def _compute_preco(self):
        for linha in self:
            linha.preco_odoo = linha.product_id.list_price or 0.0
            linha.divergencia_preco = (
                linha.preco_olist - linha.preco_odoo if linha.product_id else 0.0)

    @api.depends('order_line_ids.quantidade', 'order_line_ids.order_situacao',
                 'order_line_ids.order_data')
    def _compute_vendas(self):
        for linha in self:
            # Cancelado não é venda. Contá-lo faria um livro devolvido parecer
            # relevante justamente na tela que decide onde gastar o trabalho.
            itens = linha.order_line_ids.filtered(
                lambda l: (l.order_situacao or '').strip().lower() != 'cancelado')
            linha.sold_qty = sum(itens.mapped('quantidade'))
            linha.sold_orders = len(itens)
            datas = [d for d in itens.mapped('order_data') if d]
            linha.last_sale_date = max(datas) if datas else False

    @api.depends('product_id', 'account_id')
    def _compute_duplicate_match(self):
        for linha in self:
            if not linha.product_id:
                linha.duplicate_match = False
                continue
            linha.duplicate_match = bool(self.search_count([
                ('account_id', '=', linha.account_id.id),
                ('product_id', '=', linha.product_id.id),
                ('id', '!=', linha.id or 0),
            ]))

    @api.depends('saldo_olist', 'product_id', 'account_id.stock_reserve')
    def _compute_comparacao(self):
        for linha in self:
            produto = linha.product_id
            if not produto:
                linha.odoo_qty = 0.0
                linha.qty_to_send = 0.0
                linha.divergencia = 0.0
                linha.divergencia_abs = 0.0
                linha.state = 'sem_produto'
                continue
            template = produto.product_tmpl_id
            linha.odoo_qty = template._olist_wh_qty(linha.account_id)
            linha.qty_to_send = template._olist_stock_qty(linha.account_id)
            linha.divergencia = linha.saldo_olist - linha.qty_to_send
            linha.divergencia_abs = abs(linha.divergencia)
            if not linha.divergencia:
                linha.state = 'igual'
            elif linha.divergencia > 0:
                linha.state = 'olist_maior'
            else:
                linha.state = 'olist_menor'

    # ------------------------------------------------------------------
    # Casar à mão (e defender o que foi casado)
    # ------------------------------------------------------------------
    def write(self, vals):
        """Quem escreve `product_id` sem dizer a origem, casou à mão.

        A leitura do catálogo diz `match_origin='isbn'` por extenso. Todo o
        resto — a coluna editável da lista, o formulário, a ação de aceitar a
        sugestão — é gente decidindo, e fica marcado como tal para a releitura
        do catálogo não desfazer.
        """
        if 'product_id' in vals and 'match_origin' not in vals:
            vals = dict(vals, match_origin='manual' if vals['product_id'] else False)
        return super().write(vals)

    @staticmethod
    def _titulo_chave(texto):
        """O título reduzido ao que dá para comparar entre os dois cadastros.

        O Olist escreve `A cena lenta – Cláudio Oliveira`; o Odoo escreve
        `A cena lenta (Cláudio Oliveira. Editora Circuito)`. Corta-se no
        travessão ou no parêntese e compara-se o resto sem acento.

        A ORDEM importa e já custou caro: dobrar para ASCII antes de cortar
        apaga o travessão (que não é ASCII), o corte nunca acontece, e o
        casamento por título passa a falhar quase sempre — foi assim que uma
        primeira contagem disse que 204 livros não existiam no Odoo quando
        mais da metade existia.
        """
        texto = re.split(r'\s[–—-]\s|\(', texto or '')[0]
        texto = unicodedata.normalize('NFKD', texto)
        texto = texto.encode('ascii', 'ignore').decode().lower()
        return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', texto).split())

    def action_pull_from_olist(self):
        """Traz o catálogo do Olist para esta tela. Seis chamadas, só leitura.

        Mesma razão do botão gêmeo em Pedidos: é a primeira coisa que se faz
        aqui e precisa aparecer com a lista VAZIA (`display="always"` na view).
        E, como ele, sem `@api.model` -- ver a nota em olist.order.
        """
        conta = self.env['olist.account']._for_current_company()
        return conta.action_pull_catalogue()

    # ------------------------------------------------------------------
    # A ficha do livro: ler, e alterar um campo devolvendo a ficha inteira
    # ------------------------------------------------------------------
    # De-para entre o campo daqui e a chave da ficha do Olist. Uma tabela só,
    # usada pelo diff e pelo envio: se as duas listas divergissem, a tela
    # mostraria uma alteração pendente que o envio não manda (ou o contrário),
    # que é a pior espécie de mentira numa tela de sincronia.
    CAMPOS_OLIST = {
        'name': 'nome',
        'codigo': 'codigo',
        'gtin': 'gtin',
        'preco_olist': 'preco',
        'preco_promocional': 'preco_promocional',
        'preco_custo': 'preco_custo',
        'marca': 'marca',
        'categoria': 'categoria',
        'ncm': 'ncm',
        'unidade': 'unidade',
        'peso_liquido': 'peso_liquido',
        'peso_bruto': 'peso_bruto',
        'situacao_olist': 'situacao',
        'descricao': 'descricao_complementar',
    }

    # Os dois ARMAZENADOS, e juntos: `tem_alteracao` precisa ser armazenado
    # para virar filtro e coluna ordenável, e um compute com metade dos campos
    # armazenados dispara o aviso de 'store' inconsistente do Odoo.
    alteracoes_pendentes = fields.Text(
        "Alterações não enviadas", compute='_compute_alteracoes', store=True,
        help="O que foi editado aqui e ainda NÃO foi para o Olist. Editar "
             "nesta tela muda só o espelho; o Olist só sabe quando se manda.")
    tem_alteracao = fields.Boolean(
        "Editado", compute='_compute_alteracoes', store=True, index=True)

    @api.depends('ficha_json', 'name', 'codigo', 'gtin', 'preco_olist',
                 'preco_promocional', 'preco_custo', 'marca', 'categoria',
                 'ncm', 'unidade', 'peso_liquido', 'peso_bruto',
                 'situacao_olist', 'descricao',
                 # sem isto, editar um campo da ficha completa marcava a LINHA
                 # filha como alterada e o cabeçalho continuava dizendo que
                 # não havia nada pendente
                 'field_ids.alterado', 'field_ids.valor')
    def _compute_alteracoes(self):
        for linha in self:
            diferencas = linha._diff_ficha()
            linha.tem_alteracao = bool(diferencas)
            linha.alteracoes_pendentes = "\n".join(
                "%s: %s  ->  %s" % (campo, de, para)
                for campo, de, para in diferencas) or False

    def _diff_ficha(self):
        """[(campo, valor_no_olist, valor_aqui)] do que foi editado e não subiu.

        A comparação é contra a FICHA LIDA, não contra o que estava no espelho
        antes: o espelho é o que se editou, a ficha é o que o Olist tem. Sem
        uma foto do outro lado, "alterado" não quer dizer nada.
        """
        self.ensure_one()
        if not self.ficha_json:
            return []
        try:
            ficha = json.loads(self.ficha_json)
        except ValueError:
            return []
        saida = []
        for campo, chave in self.CAMPOS_OLIST.items():
            aqui = self[campo]
            la = ficha.get(chave)
            if isinstance(aqui, float):
                if abs(aqui - float(la or 0)) > 0.0001:
                    saida.append((campo, la, aqui))
                continue
            aqui_txt = (aqui or '').strip() if isinstance(aqui, str) else (aqui or '')
            la_txt = (str(la).strip() if la is not None else '')
            if str(aqui_txt) != la_txt:
                saida.append((campo, la_txt or '(vazio)', aqui_txt or '(vazio)'))
        for linha in self.field_ids.filtered('alterado'):
            saida.append((linha.chave, linha.valor_original or '(vazio)',
                          linha.valor or '(vazio)'))
        return saida

    def action_push_changes(self):
        """Manda para o Olist tudo o que foi editado aqui e ainda não subiu.

        Uma porta para todos os campos, com a mesma disciplina das específicas:
        lê a ficha, aplica as mudanças, devolve a ficha inteira. As ações de
        preço, ISBN e situação continuam existindo como atalho do dia a dia —
        esta é para quando se está arrumando o cadastro de verdade.
        """
        ok, erros, nada = 0, [], 0
        for linha in self:
            diferencas = linha._diff_ficha()
            if not diferencas:
                nada += 1
                continue
            proprios = {linha.CAMPOS_OLIST[campo]: linha[campo]
                        for campo, _de, _para in diferencas
                        if campo in linha.CAMPOS_OLIST}
            # Os genéricos vão com o TIPO do original: mandar "2" onde havia
            # o número 2 é pedir para o Olist decidir sozinho o que fazer com
            # a diferença.
            genericos = {}
            for campo_linha in linha.field_ids.filtered('alterado'):
                genericos[campo_linha.chave] = campo_linha._valor_tipado()
            mudancas = dict(proprios, **genericos)
            status, detalhe = linha._alterar_no_olist(mudancas, _("edição da ficha"))
            if status == 'OK':
                ok += 1
            else:
                erros.append("%s: %s" % (linha.codigo or linha.olist_id, detalhe))
        if not erros:
            return self._notificacao(
                _("Ficha atualizada no Olist"),
                _("%(n)s livro(s) enviados, %(z)s sem alteração pendente.",
                  n=ok, z=nada), 'success')
        return self._notificacao(
            _("Envio parcial"),
            _("%(ok)s enviados, %(e)s com erro:\n%(lista)s",
              ok=ok, e=len(erros), lista="\n".join(erros[:8])),
            'warning', sticky=True)

    def action_discard_changes(self):
        """Desfaz a edição local, voltando ao que a ficha do Olist diz."""
        for linha in self.filtered('ficha_json'):
            ficha = json.loads(linha.ficha_json)
            linha.write({
                campo: (ficha.get(chave) if not isinstance(linha[campo], float)
                        else float(ficha.get(chave) or 0))
                for campo, chave in linha.CAMPOS_OLIST.items()
            })
        return self._notificacao(
            _("Edição descartada"),
            _("%s linha(s) voltaram ao que o Olist tem.", len(self)), 'success')

    def action_read_ficha(self):
        """Lê no Olist a ficha completa das linhas escolhidas. Só leitura."""
        lidas = sum(1 for linha in self if linha._read_ficha())
        return False

    def _read_ficha(self):
        self.ensure_one()
        ficha = olist_client.get_produto(self.account_id.sudo().token,
                                         self.olist_id)
        if ficha is None:
            return False
        self.write({
            'name': ficha.get('nome') or self.name,
            'codigo': (ficha.get('codigo') or '').strip() or self.codigo,
            'preco_olist': float(ficha.get('preco') or 0.0),
            'preco_promocional': float(ficha.get('preco_promocional') or 0.0),
            'preco_custo': float(ficha.get('preco_custo') or 0.0),
            'situacao_olist': (ficha.get('situacao') or '').strip()[:1] or False,
            'gtin': (ficha.get('gtin') or '').strip() or False,
            'marca': ficha.get('marca') or False,
            'categoria': ficha.get('categoria') or False,
            'ncm': ficha.get('ncm') or False,
            'unidade': ficha.get('unidade') or False,
            'peso_liquido': float(ficha.get('peso_liquido') or 0.0),
            'peso_bruto': float(ficha.get('peso_bruto') or 0.0),
            'descricao': ficha.get('descricao_complementar') or False,
            'ficha_lida_em': fields.Datetime.now(),
            'ficha_json': json.dumps(ficha, ensure_ascii=False, indent=1),
        })
        self._sincroniza_campos(ficha)
        return True

    def _sincroniza_campos(self, ficha):
        """Reescreve os pares chave/valor a partir da ficha lida.

        Reescreve, não acumula: o espelho reflete o outro lado. Editar aqui e
        reler a ficha significa perder a edição — e isso é o certo, porque
        reler é justamente dizer "quero o que está lá".
        """
        self.ensure_one()
        self.field_ids.unlink()
        Campo = self.env['olist.product.field']
        for chave in sorted(ficha):
            if chave in self.CAMPOS_OLIST.values() or chave == 'id':
                continue    # esses já têm campo próprio: duas portas, não
            valor = ficha[chave]
            estrutura = isinstance(valor, (list, dict))
            Campo.create({
                'mirror_id': self.id,
                'chave': chave,
                'valor': (json.dumps(valor, ensure_ascii=False)
                          if estrutura else ('' if valor is None else str(valor))),
                'valor_original': (json.dumps(valor, ensure_ascii=False)
                                   if estrutura else ('' if valor is None else str(valor))),
                'editavel': not estrutura,
            })

    def _alterar_no_olist(self, mudancas, rotulo):
        """Aplica `mudancas` na ficha do Olist — devolvendo a ficha INTEIRA.

        A releitura antes de escrever não é zelo: não se sabe se
        `produto.alterar` faz atualização parcial ou substituição, e mandar só
        o campo alterado seria apostar que é parcial. Se não for, o livro perde
        peso, NCM, descrição e SEO de uma vez. Ler, trocar um campo e devolver
        tudo funciona nas duas hipóteses — e ainda deixa a ficha do espelho
        fresca no momento exato da escrita.
        """
        self.ensure_one()
        self.account_id._check_writable()
        token = self.account_id.sudo().token
        ficha = olist_client.get_produto(token, self.olist_id)
        if ficha is None:
            return 'ERR', _("não consegui ler a ficha antes de escrever")
        antes = {campo: ficha.get(campo) for campo in mudancas}
        ficha.update(mudancas)
        ficha['id'] = self.olist_id
        corpo, raw = olist_client.update_produto(token, ficha)
        status, detalhe = self._read_alterar_response(raw)
        self.write({
            'last_write_result': (
                "== %s ==\n%s\nantes: %s\ndepois: %s\n\nENVIADO %s\n\nRESPOSTA %s"
            ) % (rotulo, fields.Datetime.now(), antes, mudancas, corpo, raw),
        })
        if status == 'OK':
            self._read_ficha()
        _logger.info("Olist alterar %s (%s): %s", self.olist_id, rotulo, status)
        return status, detalhe

    @staticmethod
    def _read_alterar_response(raw):
        """(status, detalhe) da resposta de alteração. Nunca estoura."""
        try:
            retorno = json.loads(raw).get("retorno", {})
        except (ValueError, AttributeError):
            return 'ERR', (raw or '')[:200]
        if str(retorno.get("status", "")).upper() == "OK":
            return 'OK', _("alterado")
        registros = retorno.get("registros")
        if isinstance(registros, dict):
            registros = [registros]
        if registros:
            registro = registros[0].get("registro", {})
            if str(registro.get("status", "")).upper() == "OK":
                return 'OK', _("alterado")
            return 'ERR', str(registro.get("erros") or registro)[:200]
        return 'ERR', str(retorno.get("erros")
                          or retorno.get("codigo_erro") or raw)[:200]

    def action_push_price(self):
        """Manda para o Olist o preço de venda do Odoo, nas linhas escolhidas.

        O Odoo é o razão do preço — a tabela de venda é decidida aqui. O que
        estiver casado e divergente sobe; o que não tem produto casado não tem
        preço nosso para mandar, e é dito por extenso.
        """
        return self._escrita_em_lote(
            lambda linha: {'preco': linha.product_id.list_price},
            _("preço"), exige_produto=True)

    def action_push_isbn(self):
        """Corrige no Olist o código do livro para o ISBN do Odoo.

        É a correção que resolve a raiz do desencontro: 55% dos livros que não
        casam são o MESMO livro com ISBN antigo lá e novo aqui. Trocar o código
        no Olist faz o casamento passar a valer sozinho, para sempre — em vez
        de depender do de-para à mão.

        Preenche também o `gtin`: para livro, ISBN-13 É EAN-13, e o marketplace
        precisa dele para identificar o título fora do nosso código.
        """
        return self._escrita_em_lote(
            lambda linha: {'codigo': linha.product_id.barcode,
                           'gtin': linha.product_id.barcode},
            _("ISBN"), exige_produto=True, exige_barcode=True)

    def action_deactivate_in_olist(self):
        """Desativa o livro no Olist (situacao = I).

        Para o cadastro morto: a entrada velha que ficou para trás quando o
        livro ganhou ISBN novo, ou o que não se vende mais. Desativar não
        apaga histórico de venda nem nota — só tira o livro da vitrine.
        """
        return self._escrita_em_lote(
            lambda linha: {'situacao': 'I'}, _("desativação"))

    def action_activate_in_olist(self):
        """Volta a ativar o livro no Olist (situacao = A)."""
        return self._escrita_em_lote(
            lambda linha: {'situacao': 'A'}, _("ativação"))

    def _escrita_em_lote(self, monta_mudancas, rotulo,
                         exige_produto=False, exige_barcode=False):
        if not self:
            return False
        ok, erros = 0, []
        for linha in self:
            if exige_produto and not linha.product_id:
                erros.append("%s: %s" % (linha.codigo or linha.olist_id,
                                         _("sem produto casado no Odoo")))
                continue
            if exige_barcode and not linha.product_id.barcode:
                erros.append("%s: %s" % (linha.codigo or linha.olist_id,
                                         _("o produto do Odoo não tem ISBN")))
                continue
            status, detalhe = linha._alterar_no_olist(
                monta_mudancas(linha), rotulo)
            if status == 'OK':
                ok += 1
            else:
                erros.append("%s: %s" % (linha.codigo or linha.olist_id, detalhe))
        if not erros:
            return self._notificacao(
                _("Olist atualizado"),
                _("%(n)s livro(s): %(o)s enviada.", n=ok, o=rotulo), 'success')
        return self._notificacao(
            _("Atualização parcial"),
            _("%(ok)s ok, %(n)s com erro:\n%(lista)s",
              ok=ok, n=len(erros), lista="\n".join(erros[:8])),
            'warning', sticky=True)

    def action_create_in_odoo(self):
        """Cria no Odoo o livro que só existe no Olist, a partir da ficha.

        Só para os que não têm par NENHUM — e depois de olhar a sugestão por
        título, porque metade do que "falta" é livro que já existe com outro
        ISBN. Criar sem olhar é o caminho para duplicar o catálogo da editora.
        """
        criados, pulados = 0, []
        for linha in self:
            if linha.product_id:
                pulados.append("%s: %s" % (linha.codigo or linha.olist_id,
                                           _("já está casado")))
                continue
            if not linha.ficha_lida_em:
                pulados.append("%s: %s" % (linha.codigo or linha.olist_id,
                                           _("leia a ficha antes")))
                continue
            produto = self.env['product.product'].create({
                'name': linha.name or linha.codigo,
                'barcode': re.sub(r'\D', '', linha.codigo or '') or False,
                'default_code': linha.codigo or False,
                'list_price': linha.preco_olist,
                'weight': linha.peso_liquido,
                'type': 'consu',
                'is_storable': True,
            })
            linha.product_id = produto
            criados += 1
        if not pulados:
            return self._notificacao(
                _("Criados no Odoo"),
                _("%s livro(s).", criados), 'success')
        return self._notificacao(
            _("Criação parcial"),
            _("%(n)s criados, %(p)s pulados:\n%(lista)s",
              n=criados, p=len(pulados), lista="\n".join(pulados[:8])),
            'warning', sticky=True)

    def action_suggest_match(self):
        """Procura, pelo TÍTULO, um candidato para as linhas sem produto.

        Só preenche a coluna de sugestão — não casa nada. O casamento continua
        sendo ato de gente, porque título parecido não é prova: há livro com o
        mesmo nome de editoras diferentes, e há reedição que mudou de título.
        """
        alvo = self.filtered(lambda l: not l.product_id)
        if not alvo:
            return self._notificacao(
                _("Sugestão"), _("As linhas escolhidas já estão casadas."),
                'warning')
        # Um índice do catálogo, montado uma vez: 3 mil produtos contra 600
        # linhas não pode virar 600 buscas.
        indice = {}
        for produto in self.env['product.product'].search(
                [('name', '!=', False)]):
            indice.setdefault(self._titulo_chave(produto.name), produto)
        achou = 0
        for linha in alvo:
            candidato = indice.get(self._titulo_chave(linha.name))
            linha.suggested_product_id = candidato.id if candidato else False
            if candidato:
                achou += 1
        return self._notificacao(
            _("Sugestão por título"),
            _("%(n)s de %(t)s linha(s) têm candidato. Confira e use "
              "'Aceitar sugestão' — título parecido não é prova.",
              n=achou, t=len(alvo)), 'success')

    def action_accept_suggestion(self):
        """Casa as linhas selecionadas com o candidato sugerido."""
        alvo = self.filtered(
            lambda l: l.suggested_product_id and not l.product_id)
        for linha in alvo:
            linha.product_id = linha.suggested_product_id
        return False

    def action_unmatch(self):
        """Desfaz o casamento das linhas selecionadas."""
        self.write({'product_id': False})
        return False

    # ------------------------------------------------------------------
    # Ler o Olist (leitura)
    # ------------------------------------------------------------------
    # Quantos livros cabem num clique. A ~1,8s por chamada, 120 dão ~3,5min e
    # sobra folga para o teto de ~100s por requisição do túnel... não: o que
    # cabe de fato é medido pelo relógio abaixo, e este número é só o teto de
    # segurança. O resto fica para o clique seguinte, e é dito na mensagem.
    LOTE_ESTOQUE = 120
    MINUTOS_ESTOQUE = 2

    def action_pull_all_stock(self):
        """Semeia o espelho: lê o saldo dos livros que ainda não têm.

        A janela do cron pergunta "o que mudou desde a última leitura?" e
        mantém em dia o que já foi lido — mas NÃO semeia, e o Olist recusa
        janela maior que 30 dias ("Somente podem ser listados os registros dos
        últimos 30 dias", 18/08/2026). Então a semeadura é livro a livro
        mesmo, uma chamada por linha.

        Por lotes, com relógio: uma varredura de 580 livros leva ~20 minutos e
        estouraria o tempo da requisição. Cada clique lê o que couber, grava o
        que leu e diz quanto falta — quem nunca foi lido vem primeiro, porque
        é a linha que hoje mente na tela.
        """
        Linha = self.env['olist.product']
        alvo = self or Linha.search([('olist_id', '!=', False)])
        # Nunca lidos primeiro; entre os lidos, o mais antigo.
        pendentes = alvo.filtered(lambda l: l.olist_id).sorted(
            key=lambda l: (bool(l.saldo_olist_date), l.saldo_olist_date or ''))
        if not pendentes:
            raise UserError(_(
                "Não há linha com id do Olist para ler. Use 'Ler catálogo do "
                "Olist' na tela de Produtos primeiro."))
        limite = time.monotonic() + self.MINUTOS_ESTOQUE * 60
        lidas = 0
        for linha in pendentes[:self.LOTE_ESTOQUE]:
            if time.monotonic() > limite:
                break
            if linha._read_saldo():
                lidas += 1
                linha._grava_saldo_ja()
        faltam = len(pendentes.filtered(lambda l: not l.saldo_olist_date))
        if faltam:
            return self._notificacao(
                _("Estoques lidos (parcial)"),
                _("%(lidas)s livro(s) lidos agora. Ainda faltam %(faltam)s "
                  "sem leitura — clique de novo para continuar de onde parou.",
                  lidas=lidas, faltam=faltam), 'warning')
        return self._notificacao(
            _("Estoques lidos no Olist"),
            _("%s livro(s) com saldo atualizado.", lidas), 'success')

    def _grava_saldo_ja(self):
        """Commit por linha: estouro de tempo não pode jogar fora o que já
        veio — e a releitura custaria a cota de novo. Proibido em teste, que
        depende do rollback para isolar cada caso (mesma guarda do
        `olist.order._grava_ja`)."""
        if tools.config['test_enable'] or modules.module.current_test:
            return False
        self.env.cr.commit()
        return True

    def action_read_saldo(self):
        """Lê no Olist o saldo das linhas selecionadas. Não escreve nada.

        Uma chamada por linha: é para conferir um punhado antes de decidir,
        não para varrer o catálogo (isso é trabalho do cron).
        """
        for linha in self:
            linha._read_saldo()
        return self._notificacao(
            _("Saldo lido no Olist"),
            _("%s linha(s) atualizadas.", len(self)), 'success')

    def _read_saldo(self):
        self.ensure_one()
        token = self.account_id.sudo().token
        retorno = olist_client.get_estoque(token, self.olist_id)
        if retorno is None:
            return False
        self.write({
            'saldo_olist': float(retorno.get('saldo') or 0.0),
            'saldo_olist_date': fields.Datetime.now(),
        })
        return True

    # ------------------------------------------------------------------
    # Escrever no Olist (a única porta de escrita, e é sobre selecionados)
    # ------------------------------------------------------------------
    def action_sync_selected(self):
        """Empurra para o Olist o estoque das linhas SELECIONADAS.

        Deliberadamente sobre seleção, e não sobre tudo: o primeiro contato de
        uma escrita com uma conta viva se faz com três livros que a pessoa
        escolheu e sabe conferir. A varredura completa existe (na conta), mas
        não é por onde se começa.
        """
        if not self:
            return False
        contas = self.account_id
        bloqueadas = contas.filtered('read_only')
        if bloqueadas:
            raise UserError(_(
                "A conta %s está em modo somente leitura. Enquanto estiver, "
                "nada é escrito no Olist — é o que deixa testar com o token "
                "de verdade sem risco. Desligue 'Somente leitura' na conta "
                "para poder sincronizar.", bloqueadas[0].name))

        ok, erros = 0, []
        for linha in self:
            if not linha.product_id:
                erros.append("%s: %s" % (linha.codigo or linha.olist_id,
                                         _("sem produto no Odoo")))
                continue
            if linha.duplicate_match:
                # Duas linhas do Olist para um livro só do Odoo: mandar o saldo
                # cheio para as duas oferece o mesmo exemplar duas vezes.
                erros.append("%s: %s" % (
                    linha.codigo or linha.olist_id,
                    _("outro item do Olist aponta para o mesmo livro — "
                      "decida como dividir o saldo antes de enviar")))
                continue
            template = linha.product_id.product_tmpl_id._in_olist_company(
                linha.account_id.company_id)
            # O espelho JÁ sabe o id interno (veio do catálogo). Gravá-lo aqui
            # evita que o push saia procurando o produto por ISBN — uma
            # chamada de rede a mais, por livro, para descobrir o que já está
            # na nossa frente. E é o que mantém o teste offline: sem isto, uma
            # linha nova faz o suite bater na API de verdade.
            if template.olist_produto_id != linha.olist_id:
                template.olist_produto_id = linha.olist_id
            status, detalhe = template._push_stock_to_olist(linha.account_id)
            linha.write({
                'last_push_date': fields.Datetime.now(),
                'last_push_qty': linha.qty_to_send,
                'last_push_result': "%s: %s" % (status, detalhe),
            })
            if status == 'OK':
                ok += 1
                # O Olist passou a ter o nosso número: o espelho reflete isso
                # sem precisar de outra chamada.
                linha.write({'saldo_olist': linha.qty_to_send,
                             'saldo_olist_date': fields.Datetime.now()})
            else:
                erros.append("%s: %s" % (linha.codigo or linha.olist_id, detalhe))

        if not erros:
            return self._notificacao(
                _("Estoque sincronizado"),
                _("%s livro(s) atualizados no Olist.", ok), 'success')
        return self._notificacao(
            _("Sincronização parcial"),
            _("%(ok)s ok, %(n)s com erro:\n%(lista)s",
              ok=ok, n=len(erros), lista="\n".join(erros[:8])),
            'warning', sticky=True)

    @staticmethod
    def _notificacao(titulo, mensagem, tipo, sticky=False, recarregar=False):
        """Notificação sem recarregamento de página.

        O cliente web recarrega o registro sozinho depois de qualquer botão;
        o `next: reload` recarregava a PÁGINA e era o freeze (ver a nota no
        gêmeo em olist.order). `recarregar` ficou por compatibilidade e é
        ignorado.
        """
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': titulo, 'message': mensagem,
                       'type': tipo, 'sticky': sticky},
        }

    def action_open_product(self):
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Esta linha não tem produto casado no Odoo."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'res_id': self.product_id.product_tmpl_id.id,
            'view_mode': 'form',
        }


class OlistProductField(models.Model):
    """Um campo da ficha do Olist, como par chave/valor editável.

    A ficha tem 52 campos e só uns catorze mereciam virar coluna. Os outros
    não são menos reais — NCM de embalagem, estoque mínimo, SEO, dias de
    preparação, dimensões — e alguém precisa poder mexer neles sem esperar que
    eu adivinhe quais importam e escreva um campo Odoo para cada.

    Então a ficha inteira aparece aqui, e o que é escalar é editável. O que é
    estrutura (anexos, imagens, variações) aparece como JSON e NÃO é editável:
    mandar de volta um texto colado no lugar de uma lista é o caminho curto
    para corromper a ficha de um livro.

    As chaves que JÁ têm campo próprio no espelho ficam fora daqui de
    propósito: duas portas para o mesmo valor é como se produz conflito
    silencioso. Ver liber_olist/NOTES.md §14.5.
    """
    _name = 'olist.product.field'
    _description = "Campo da ficha do produto no Olist"
    _order = 'chave'
    _rec_name = 'chave'

    mirror_id = fields.Many2one('olist.product', required=True,
                                ondelete='cascade', index=True)
    chave = fields.Char("Campo no Olist", readonly=True, index=True)
    valor = fields.Char("Valor")
    valor_original = fields.Char("Valor no Olist", readonly=True)
    editavel = fields.Boolean(
        "Editável", readonly=True,
        help="Falso quando o valor é uma estrutura (lista ou objeto): "
             "devolvê-la como texto corromperia a ficha.")
    alterado = fields.Boolean(compute='_compute_alterado', store=True)

    @api.depends('valor', 'valor_original')
    def _compute_alterado(self):
        for linha in self:
            linha.alterado = (linha.valor or '') != (linha.valor_original or '')

    def _valor_tipado(self):
        """O valor editado, no tipo que o original tinha.

        O Olist devolve número como número e texto como texto. Reenviar tudo
        como string funciona às vezes e falha calado noutras -- e "às vezes"
        não é critério para escrever em catálogo vivo.
        """
        self.ensure_one()
        original, novo = self.valor_original or '', self.valor or ''
        try:
            int(original)
            return int(novo)
        except (TypeError, ValueError):
            pass
        try:
            float(original)
            return float(novo)
        except (TypeError, ValueError):
            pass
        return novo


class OlistProductOpen(models.Model):
    """O botão de abrir a ficha, na primeira coluna da lista.

    A seta do `open_form_view` fica no FIM da linha, e numa tela com muitas
    colunas ela sai do campo de visão -- foi exatamente o que aconteceu. Um
    botão no começo da linha resolve sem depender da largura do monitor.
    """
    _inherit = 'olist.product'

    def action_open_ficha(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name or self.codigo,
            'res_model': 'olist.product',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref(
                'liber_olist.view_olist_catalog_form').id, 'form')],
            'target': 'current',
        }
