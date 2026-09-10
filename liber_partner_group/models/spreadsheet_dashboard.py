# -*- coding: utf-8 -*-
import json

from odoo import models

# O que sai e o que entra: a loja dá lugar à rede -- e quem não tem rede
# continua sendo ele mesmo, porque o campo já nasce com esse fallback.
CAMPO_LOJA = 'partner_id'
CAMPO_REDE = 'commercial_group_display'

# O cabeçalho da tabela é o NOME do pivô, não o rótulo do campo (a lição do
# `liber_geo_brasil`: a fórmula PIVOT escreve o nome na célula de canto).
# Sem a troca, as redes sairiam listadas debaixo de "Customer".
TITULO_PIVO = 'Grupo / Cliente'


class SpreadsheetDashboard(models.Model):
    """O "Principais clientes" do Painel de Vendas conta por rede.

    A tabela de fábrica agrupa pela ficha exata: a Travessa aparece como
    "LIVRARIA DA TRAVESSA LTDA (2)" e "LIVRARIA DA TRAVESSA LTDA (4)" -- duas
    linhas homônimas que só o contador distingue, e a pergunta "quanto vendemos
    PARA a Travessa" fica sem resposta ali. A linha do pivô passa a ser o eixo
    rede-ou-cliente: as redes colapsam, os independentes continuam de pé com o
    próprio nome, e ninguém cai num balde "Nenhum".

    A troca acontece NA LEITURA, não no dado gravado, pela mesma razão do
    `liber_geo_brasil` e do guard da consignação: o registro do
    `spreadsheet_dashboard_sale` não é `noupdate`, e todo upgrade do core
    reescreve o JSON por cima de qualquer edição nossa.
    """
    _inherit = 'spreadsheet.dashboard'

    def _get_serialized_readonly_dashboard(self):
        serializado = super()._get_serialized_readonly_dashboard()
        dados = json.loads(serializado)
        snapshot = dados.get('snapshot') or {}
        # Lista, não gerador: mais de um pivô pode agrupar por cliente, e
        # `any()` de gerador pararia no primeiro que mudasse.
        mudou = [self._arredar_pivo(pivo)
                 for pivo in (snapshot.get('pivots') or {}).values()]
        if any(mudou):
            return json.dumps(dados)
        return serializado

    def _arredar_pivo(self, pivo):
        """Pivô com uma linha só, e essa linha é o cliente: vira a rede.

        Regra estreita de propósito, no molde do `liber_geo_brasil`: pivô com
        mais níveis, ou agrupado por outra coisa, é de alguém que quis aquilo
        -- e sai intacto. E só quando o modelo do pivô conhece o eixo (o
        `sale.report` conhece; um pivô de outra fonte passa reto).
        """
        if not isinstance(pivo, dict):
            return False
        linhas = pivo.get('rows')
        if not isinstance(linhas, list) or len(linhas) != 1:
            return False
        if not isinstance(linhas[0], dict) or linhas[0].get('fieldName') != CAMPO_LOJA:
            return False
        modelo = pivo.get('model')
        if not modelo or modelo not in self.env:
            return False
        if CAMPO_REDE not in self.env[modelo]._fields:
            return False

        linhas[0]['fieldName'] = CAMPO_REDE
        pivo['name'] = TITULO_PIVO
        return True
