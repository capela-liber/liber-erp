# -*- coding: utf-8 -*-
import json

from odoo import models

# Quantos produtos o gráfico do painel mostra. O resto é cauda.
TOP = 50

# A chave que o `chart_limit.js` lê no `metaData` do gráfico Odoo.
CHAVE_LIMITE = 'limit'

# O contexto que tira o código do nome do produto. O `display_name` do
# `product.product` é "[código] nome" por padrão, e o código, na casa, é o
# ISBN: treze dígitos que não dizem nada num eixo de gráfico. Com esta chave
# em `False` o Odoo devolve só o nome -- e dois títulos iguais de ISBN
# diferente o próprio GraphModel do web separa, com um "(2)" no segundo.
CHAVE_CODIGO = 'display_default_code'

# A regra é estreita: só barras, só por produto. E, para o cartão "Mais
# vendido", só o pivô de uma linha, e essa linha é o produto.
TIPO_BARRAS = 'odoo_bar'
CAMPO_PRODUTO = 'product_id'


class SpreadsheetDashboard(models.Model):
    """O gráfico de produtos do painel mostra os primeiros, pelo nome.

    A troca é na leitura, não no dado gravado. O `spreadsheet_dashboard_sale`
    carrega o painel de um JSON num registro que não é `noupdate`: todo
    upgrade do core reescreve o registro e apagaria uma edição nossa sem
    avisar. Na leitura, o dado continua o do Odoo e a casa continua vendo só
    os primeiros, e sem o ISBN na frente de cada título.
    """
    _inherit = 'spreadsheet.dashboard'

    def _get_serialized_readonly_dashboard(self):
        serializado = super()._get_serialized_readonly_dashboard()
        dados = json.loads(serializado)
        snapshot = dados.get('snapshot') or {}
        # Lista, e não `or`: as duas passagens têm de acontecer.
        mudou = [self._ajustar_planilha(snapshot), self._ajustar_pivos(snapshot)]
        if any(mudou):
            return json.dumps(dados)
        return serializado

    # ------------------------------------------------------------------
    def _ajustar_planilha(self, snapshot):
        """Percorre as figuras da planilha. Devolve se alguma coisa mudou."""
        mudou = False
        if not isinstance(snapshot, dict):
            return False
        for aba in snapshot.get('sheets') or []:
            if not isinstance(aba, dict):
                continue
            for figura in aba.get('figures') or []:
                if self._ajustar_figura(figura):
                    mudou = True
        return mudou

    def _ajustar_figura(self, figura):
        """Uma figura é um gráfico só ou um carrossel de vários."""
        if not isinstance(figura, dict):
            return False
        dados = figura.get('data')
        if not isinstance(dados, dict):
            return False
        definicoes = dados.get('chartDefinitions')
        if definicoes is None:
            return self._ajustar_grafico(dados)
        if not isinstance(definicoes, dict):
            return False
        # Lista, e não gerador: todo gráfico do carrossel tem de passar aqui.
        return any([self._ajustar_grafico(d) for d in definicoes.values()])

    def _ajustar_grafico(self, definicao):
        """Barras por produto: o limite e o nome sem código. Devolve se mudou.

        As duas trocas são independentes, e as duas têm de acontecer -- por
        isso a lista, e não um `or` que pararia na primeira.
        """
        if not self._e_barras_por_produto(definicao):
            return False
        return any([self._limitar(definicao['metaData']),
                    self._tirar_o_codigo(definicao)])

    @staticmethod
    def _e_barras_por_produto(definicao):
        if not isinstance(definicao, dict) or definicao.get('type') != TIPO_BARRAS:
            return False
        meta = definicao.get('metaData')
        return isinstance(meta, dict) and meta.get('groupBy') == [CAMPO_PRODUTO]

    @staticmethod
    def _limitar(meta):
        """Só se ordenado: sem ordem não há "primeiros", há 50 quaisquer.

        E quem já pediu um limite fica com o seu -- este módulo põe o padrão
        da casa, não o impõe.
        """
        if not meta.get('order') or CHAVE_LIMITE in meta:
            return False
        meta[CHAVE_LIMITE] = TOP
        return True

    @classmethod
    def _tirar_o_codigo(cls, definicao):
        """O contexto da consulta pede o produto sem o código na frente.

        Entra no `searchParams.context`, que é o que o GraphModel repassa ao
        `read_group` -- e é o `read_group` quem escreve o rótulo.
        """
        params = definicao.get('searchParams')
        if not isinstance(params, dict):
            return False
        return cls._pedir_sem_codigo(params)

    @staticmethod
    def _pedir_sem_codigo(dono_do_contexto):
        """Põe a chave no `context` de quem a carrega. Devolve se pôs.

        Quem já decidiu sobre a chave, num sentido ou no outro, fica com a
        decisão.
        """
        contexto = dono_do_contexto.setdefault('context', {})
        if not isinstance(contexto, dict) or CHAVE_CODIGO in contexto:
            return False
        contexto[CHAVE_CODIGO] = False
        return True

    # ------------------------------------------------------------ o cartão
    def _ajustar_pivos(self, snapshot):
        """O cartão "Mais vendido" não lê o gráfico: lê um pivô por produto.

        O `PIVOT.HEADER` da aba Data escreve o nome que o `read_group` do
        pivô devolveu, e o pivô carrega o próprio `context`. A mesma chave,
        pelo mesmo caminho.
        """
        if not isinstance(snapshot, dict):
            return False
        pivos = snapshot.get('pivots')
        if not isinstance(pivos, dict):
            return False
        mudou = False
        for pivo in pivos.values():
            if self._ajustar_pivo(pivo):
                mudou = True
        return mudou

    @classmethod
    def _ajustar_pivo(cls, pivo):
        """Pivô de uma linha só, e essa linha é o produto: sem o código.

        Estreita como a regra do gráfico: pivô com mais níveis, ou agrupado
        por outra coisa, é de alguém que quis aquilo -- e sai intacto.
        """
        if not isinstance(pivo, dict):
            return False
        linhas = pivo.get('rows')
        if not isinstance(linhas, list) or len(linhas) != 1:
            return False
        if not isinstance(linhas[0], dict) or linhas[0].get('fieldName') != CAMPO_PRODUTO:
            return False
        return cls._pedir_sem_codigo(pivo)
