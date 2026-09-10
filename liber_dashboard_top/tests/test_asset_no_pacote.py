# -*- coding: utf-8 -*-
"""O corte só existe se o pacote de assets o carregar.

Um módulo de asset falha de um jeito silencioso: instalado, verde em tudo, e
sem efeito nenhum na tela porque o `assets` do manifesto aponta para um pacote
que não existe. Aqui a instalação é cobrada a dizer onde o arquivo entrou.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAssetNoPacote(TransactionCase):

    def _urls(self, pacote):
        conteudo = self.env['ir.qweb']._get_asset_content(pacote)[0]
        return [asset['url'] for asset in conteudo]

    def test_o_corte_esta_no_pacote_do_spreadsheet(self):
        """O patch entra no mesmo pacote da lib -- é onde o dashboard o lê."""
        urls = self._urls('spreadsheet.o_spreadsheet')
        self.assertTrue(any(url.endswith('/chart_limit.js') for url in urls),
                        [u for u in urls if 'liber_dashboard_top' in u])

    def test_o_corte_carrega_depois_da_fonte_de_dados(self):
        """Ordem importa: o patch pede a classe que o core define ao carregar."""
        urls = self._urls('spreadsheet.o_spreadsheet')
        fonte = next(i for i, u in enumerate(urls) if u.endswith('/chart_data_source.js'))
        corte = next(i for i, u in enumerate(urls) if u.endswith('/chart_limit.js'))
        self.assertGreater(corte, fonte)

    def test_teste_hoot_no_pacote_de_testes(self):
        urls = self._urls('web.assets_unit_tests')
        self.assertTrue(any(url.endswith('/chart_limit.test.js') for url in urls))
