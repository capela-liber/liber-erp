# -*- coding: utf-8 -*-
import json

from odoo import models

# A região que o `geo_json_service_brasil.js` acrescenta ao gráfico geo.
REGIAO_BR = 'br_uf'

# O que sai e o que entra: o país do cliente dá lugar à UF do cliente.
CAMPO_PAIS = 'country_id'
CAMPO_UF = 'state_id'

# A guarda "tem país", que o dashboard de Vendas põe no domínio do pivô para
# não listar a linha sem lugar nenhum.
GUARDA_PAIS = [CAMPO_PAIS, '!=', False]

# O título do card deixa de falar em países. Fica na família dos vizinhos do
# dashboard de Vendas -- "Top Customers", "Top Categories" -- e não presume qual
# é a medida, porque a troca vale para qualquer gráfico geo por país.
TITULO = 'Top UFs'

# O cabeçalho da tabela, que é o NOME do pivô -- não o rótulo do campo.
#
# A fórmula `PIVOT` escreve o nome do pivô na célula de canto (`result[0][0]`,
# no `compute` do o_spreadsheet) sempre que houver linha de cabeçalho. Por isso
# a tabela do dashboard de Vendas diz "Country", e não "País do cliente", que é
# o rótulo do `country_id`. Trocar a linha do pivô sem trocar o nome deixaria as
# UFs listadas debaixo de um cabeçalho escrito "Country".
#
# O nome é nosso de propósito, e não o rótulo do campo: o `state_id` de
# `sale.report` está traduzido errado no core -- em pt_BR ele diz "Situação do
# cliente", que é outra coisa.
TITULO_PIVO = 'UF'

# A medida de contagem das tabelas "Top ..." do dashboard de Vendas. O core não
# usa `__count`: ele conta o `order_reference` (a referência ao pedido), com o
# cabeçalho "Orders" escrito no `userDefinedName`.
MEDIDA_PEDIDOS = 'order_reference'
ROTULO_PEDIDOS = 'Orders'

# O que entra no lugar: a QUANTIDADE vendida, somada. Para uma editora, "3
# pedidos" diz menos que "412 exemplares".
CAMPO_QUANTIDADE = 'product_uom_qty'
ROTULO_QUANT = 'Quant'


class SpreadsheetDashboard(models.Model):
    """O mapa do dashboard é o do Brasil, e a divisão é a UF do cliente.

    A troca acontece aqui, na leitura, e não no dado gravado. O
    `spreadsheet_dashboard_sale` do Odoo carrega o dashboard de um arquivo JSON
    num registro que **não** é `noupdate`: todo upgrade daquele módulo reescreve
    o registro e apagaria uma edição nossa sem avisar. Na leitura, o dado
    continua sendo o do Odoo e a casa continua vendo o Brasil.
    """
    _inherit = 'spreadsheet.dashboard'

    def _get_serialized_readonly_dashboard(self):
        serializado = super()._get_serialized_readonly_dashboard()
        dados = json.loads(serializado)
        snapshot = dados.get('snapshot') or {}
        # As trocas são independentes, e todas têm de acontecer: sem a lista,
        # `or` de curto-circuito deixaria os pivôs por país quando o gráfico já
        # tivesse mudado.
        mudou = [self._brasilizar_planilha(snapshot), self._brasilizar_pivos(snapshot),
                 self._quantificar_pivos(snapshot)]
        if any(mudou):
            return json.dumps(dados)
        return serializado

    # ------------------------------------------------------------------
    def _brasilizar_planilha(self, snapshot):
        """Percorre as figuras da planilha. Devolve se alguma coisa mudou."""
        mudou = False
        for aba in snapshot.get('sheets') or []:
            for figura in aba.get('figures') or []:
                if self._brasilizar_figura(figura):
                    mudou = True
        return mudou

    def _brasilizar_figura(self, figura):
        """Uma figura é um gráfico só ou um carrossel de vários."""
        dados = figura.get('data') or {}
        definicoes = dados.get('chartDefinitions')
        if definicoes is None:
            trocou = self._brasilizar_grafico(dados)
        else:
            # `any(...)` de gerador pararia no primeiro: o carrossel pode ter
            # mais de um mapa, e todos têm de ser trocados.
            trocados = [self._brasilizar_grafico(d) for d in definicoes.values()]
            trocou = any(trocados)
        if trocou:
            dados.setdefault('title', {})['text'] = TITULO
        return trocou

    def _brasilizar_grafico(self, definicao):
        """Mapa-múndi agrupado por país vira mapa do Brasil agrupado por UF.

        A regra é estreita de propósito: gráfico geo, agrupado EXATAMENTE por
        `country_id`, e só quando o modelo do gráfico sabe a UF do cliente.
        Qualquer outra coisa passa intacta -- inclusive um mapa-múndi que
        alguém tenha montado de propósito com outro agrupamento.
        """
        if not isinstance(definicao, dict) or definicao.get('type') != 'odoo_geo':
            return False
        meta = definicao.get('metaData') or {}
        if meta.get('groupBy') != [CAMPO_PAIS]:
            return False
        if not self._modelo_sabe_a_uf(meta.get('resModel')):
            return False

        meta['groupBy'] = [CAMPO_UF]
        definicao['metaData'] = meta
        definicao.setdefault('searchParams', {})['groupBy'] = [CAMPO_UF]
        definicao['region'] = REGIAO_BR
        return True

    # ------------------------------------------------------------ a tabela
    def _brasilizar_pivos(self, snapshot):
        """A aba "Top 10", ao lado do mapa, conta a mesma história.

        O carrossel tem duas abas e só uma delas é gráfico. A outra é uma
        `carouselDataView`, que não desenha nada por conta própria: ela apaga a
        figura e deixa ver a planilha que está por baixo. No dashboard de
        Vendas, o que está por baixo é uma fórmula `PIVOT` agrupada por país --
        de outro registro, que a figura nem menciona. Trocar só o gráfico
        deixaria as duas abas do mesmo card discordando uma da outra.
        """
        mudou = False
        for pivo in (snapshot.get('pivots') or {}).values():
            if self._brasilizar_pivo(pivo):
                mudou = True
        return mudou

    def _brasilizar_pivo(self, pivo):
        """Pivô com uma linha só, e essa linha é o país: passa a ser a UF.

        A regra é a mesma do gráfico, estreita pelo mesmo motivo. Pivô com mais
        de um nível de linha, ou agrupado por outra coisa, é de alguém que quis
        aquilo -- e sai intacto.
        """
        if not isinstance(pivo, dict):
            return False
        linhas = pivo.get('rows')
        if not isinstance(linhas, list) or len(linhas) != 1:
            return False
        if not isinstance(linhas[0], dict) or linhas[0].get('fieldName') != CAMPO_PAIS:
            return False
        if not self._modelo_sabe_a_uf(pivo.get('model')):
            return False

        linhas[0]['fieldName'] = CAMPO_UF
        pivo['name'] = TITULO_PIVO
        pivo['domain'] = self._trocar_guarda_de_pais(pivo.get('domain'))
        return True

    def _trocar_guarda_de_pais(self, dominio):
        """Só a guarda "tem país" vira "tem UF". Todo o resto fica.

        Filtrar por um país e agrupar por UF é justamente o que a casa quer, e
        um `country_id = Brasil` no domínio tem de sobreviver. O que não pode
        ficar é o `country_id != False`, que traria de volta a linha sem UF --
        a linha que o mapa ao lado não tem como desenhar.
        """
        if not isinstance(dominio, list):
            return dominio
        return [[CAMPO_UF, '!=', False] if self._e_guarda_de_pais(termo) else termo
                for termo in dominio]

    @staticmethod
    def _e_guarda_de_pais(termo):
        return isinstance(termo, (list, tuple)) and list(termo) == GUARDA_PAIS

    def _modelo_sabe_a_uf(self, modelo):
        """O modelo do gráfico/pivô existe e tem onde guardar a UF do cliente."""
        if not modelo or modelo not in self.env:
            return False
        return CAMPO_UF in self.env[modelo]._fields

    # ------------------------------------------------------- a coluna "Quant"
    def _quantificar_pivos(self, snapshot):
        """A coluna "Orders" das tabelas "Top ..." vira a quantidade vendida.

        O dashboard de Vendas conta pedidos: as tabelas "Top Products", "Top
        Customers", "Top Sales Teams" etc. têm a medida `order_reference` de
        cabeçalho "Orders". Para uma editora, "3 pedidos" diz menos que "412
        exemplares" -- então a medida passa a ser a SOMA de `product_uom_qty`,
        de cabeçalho "Quant". A troca é de leitura, como a do mapa, e pela
        mesma razão: o registro não é `noupdate` e um upgrade do core apagaria
        a edição. O Revenue fica como está.
        """
        mudou = False
        for pivo in (snapshot.get('pivots') or {}).values():
            if self._quantificar_pivo(pivo):
                mudou = True
        return mudou

    def _quantificar_pivo(self, pivo):
        """Só a medida de contagem de cabeçalho "Orders", e uma só.

        A regra é estreita como a da UF, e aqui a estreiteza tem um motivo a
        mais: os pivôs de estatística do mesmo dashboard ("so stats") também
        contam `order_reference`, mas SEM `userDefinedName` -- e as células os
        leem por fórmula, `PIVOT.VALUE(11, "order_reference", ...)`, que
        quebraria se a medida mudasse de identidade. Exigir o cabeçalho
        "Orders" deixa esses de fora por construção. As tabelas "Top ...", ao
        contrário, saem de uma fórmula `PIVOT(...)` inteira, que desenha as
        medidas que o pivô tiver, com o `userDefinedName` de cabeçalho -- ali a
        troca é segura, porque célula nenhuma menciona a medida pelo nome.
        """
        if not isinstance(pivo, dict):
            return False
        medidas = pivo.get('measures')
        if not isinstance(medidas, list):
            return False
        if not self._modelo_sabe_a_quantidade(pivo.get('model')):
            return False
        alvos = [medida for medida in medidas if self._e_medida_de_pedidos(medida)]
        if len(alvos) != 1:
            return False
        # Pivô que JÁ soma a quantidade ao lado da contagem é de alguém que
        # quis as duas colunas -- e a troca criaria uma medida duplicada.
        if any(isinstance(medida, dict)
               and CAMPO_QUANTIDADE in (medida.get('id'), medida.get('fieldName'))
               for medida in medidas):
            return False

        alvo = alvos[0]
        alvo['id'] = CAMPO_QUANTIDADE
        alvo['fieldName'] = CAMPO_QUANTIDADE
        alvo['aggregator'] = 'sum'
        alvo['userDefinedName'] = ROTULO_QUANT
        return True

    @staticmethod
    def _e_medida_de_pedidos(medida):
        return (isinstance(medida, dict)
                and medida.get('fieldName') == MEDIDA_PEDIDOS
                and medida.get('userDefinedName') == ROTULO_PEDIDOS)

    def _modelo_sabe_a_quantidade(self, modelo):
        """O modelo do pivô existe e tem a quantidade vendida para somar."""
        if not modelo or modelo not in self.env:
            return False
        return CAMPO_QUANTIDADE in self.env[modelo]._fields
