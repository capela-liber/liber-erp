# -*- coding: utf-8 -*-
import os
import re

from odoo.tests import HttpCase, tagged

from ..controllers.main import _RELATIVE_URL, _absolute

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MENU = re.compile(r'<nav class="main">(.*?)</nav>', re.S)


@tagged("post_install", "-at_install")
class TestLiberSite(HttpCase):
    """O site é HTML estático servido por um controller que reescreve URLs.
    O que quebra na prática não é o texto: é um link de menu sem a seção
    correspondente, ou o reescritor comendo uma âncora."""

    def _pagina(self):
        resposta = self.url_open("/liber")
        self.assertEqual(resposta.status_code, 200)
        return resposta.text

    def test_quem_somos_esta_no_ar(self):
        """Caminho feliz: a seção existe, está ligada ao menu e traz o texto."""
        html = self._pagina()
        self.assertIn('id="quem-somos"', html, "a seção Quem somos sumiu do HTML")
        self.assertIn('href="#quem-somos"', html, "o menu perdeu o link Quem somos")
        self.assertIn("EdLab Press", html)
        self.assertIn("Jorge Sallum", html)

    def test_todo_link_do_menu_tem_destino(self):
        """Cada âncora do menu precisa de uma seção com aquele id — é o erro
        que se comete ao acrescentar uma aba e esquecer a seção (ou vice-versa)."""
        html = self._pagina()
        menu = _MENU.search(html)
        self.assertTrue(menu, "o menu do topo não foi encontrado")

        ancoras = re.findall(r'href="#([^"]+)"', menu.group(1))
        self.assertIn("quem-somos", ancoras)
        ids = set(re.findall(r'id="([^"]+)"', html))
        orfas = [a for a in ancoras if a not in ids]
        self.assertFalse(orfas, "links de menu sem seção: %s" % orfas)

    def test_ancora_nao_vira_caminho_de_asset(self):
        """O controller prefixa caminhos relativos com /liber_site/static/.
        Se pegasse as âncoras junto, clicar em 'Quem somos' tiraria o
        visitante da página — que é o motivo de não existir <base href>."""
        html = self._pagina()
        self.assertIn('href="#quem-somos"', html)
        self.assertNotIn('href="/liber_site/static/#quem-somos"', html)

    def test_asset_fora_de_static_nao_versiona_nem_estoura(self):
        """Caso de erro: um caminho que escapa de static/ (ou que não existe)
        passa sem ganhar ?v= e sem levantar exceção."""
        fora = _RELATIVE_URL.sub(_absolute, '<img src="../../etc/passwd.png">')
        self.assertNotIn("?v=", fora)
        self.assertIn('src="/liber_site/static/../../etc/passwd.png"', fora)

        inexistente = _RELATIVE_URL.sub(_absolute, '<img src="img/nao-existe.png">')
        self.assertEqual(inexistente, '<img src="/liber_site/static/img/nao-existe.png">')

    def test_fonte_e_o_que_se_serve_estao_iguais(self):
        """_web/ é a fonte e liber_site/static/ é o que o Odoo entrega; quando
        as duas divergem, a correção some no ar sem ninguém ver.
        Só roda no repositório de desenvolvimento, onde _web/ existe."""
        fonte = os.path.join(os.path.dirname(_RAIZ), "_web", "index.html")
        if not os.path.exists(fonte):
            self.skipTest("_web/ não existe nesta instalação (módulo distribuído sozinho)")

        servido = os.path.join(_RAIZ, "static", "index.html")
        with open(fonte, encoding="utf-8") as fh:
            a = fh.readlines()
        with open(servido, encoding="utf-8") as fh:
            b = fh.readlines()

        # Comparar o texto inteiro despeja um diff de dezenas de milhares de
        # caracteres que ninguém lê. A primeira linha divergente basta para
        # achar o trecho, e o recado é o comando que resolve.
        if a != b:
            for numero, (linha_fonte, linha_servida) in enumerate(zip(a, b), start=1):
                if linha_fonte != linha_servida:
                    self.fail(
                        "_web/index.html e liber_site/static/index.html divergiram "
                        "na linha %d — rode scripts/sync_web.sh\n  fonte:   %s\n  servido: %s"
                        % (numero, linha_fonte.strip()[:120], linha_servida.strip()[:120]))
            self.fail("_web/index.html e liber_site/static/index.html têm tamanhos "
                      "diferentes (%d x %d linhas) — rode scripts/sync_web.sh"
                      % (len(a), len(b)))
