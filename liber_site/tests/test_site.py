# -*- coding: utf-8 -*-
import ast
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

    def test_faq_esta_no_ar(self):
        """Caminho feliz: a seção existe, o menu leva até ela, e as perguntas
        são acordeão de verdade (<details>), não um paredão de texto."""
        html = self._pagina()
        self.assertIn('id="faq"', html, "a seção de dúvidas frequentes sumiu do HTML")
        self.assertIn('href="#faq"', html, "o menu perdeu o link Dúvidas")
        self.assertGreaterEqual(
            html.count("<details"), 20,
            "o acordeão do FAQ encolheu — eram 27 perguntas")
        self.assertEqual(html.count("<details"), html.count("</details>"),
                         "<details> aberto e não fechado engole o resto da página")

    def test_faq_indica_os_parceiros(self):
        """As três indicações são o motivo de o FAQ existir, e cada uma já se
        perdeu uma vez em revisão de texto: a Edoo para implantar, a Capela
        para marketing, e o diretório da Odoo para quem quer escolher sozinho."""
        html = self._pagina()
        for alvo in ("edoo.me", "capela.press", "odoo.com/partners"):
            self.assertIn(alvo, html, "o FAQ perdeu a indicação de %s" % alvo)

    def test_faq_nao_promete_enterprise(self):
        """Caso de erro que importa: a resposta sobre o Enterprise se apoia em
        'nenhum módulo depende dele'. Se um dia depender, o texto vira mentira
        — e o teste é o lugar de descobrir isso, não o leitor."""
        html = self._pagina()
        self.assertIn("Nenhum módulo do Liber depende do Enterprise", html)

        raiz = os.path.dirname(_RAIZ)
        proprietarios = {
            "account_accountant", "account_reports", "documents", "sign",
            "web_studio", "helpdesk", "planning", "marketing_automation",
            "timesheet_grid", "approvals", "appraisal", "quality_control",
        }
        escopo = os.path.join(raiz, "scripts", "liber_erp_modules.txt")
        if not os.path.exists(escopo):
            self.skipTest("lista de escopo ausente (módulo distribuído sozinho)")

        with open(escopo, encoding="utf-8") as fh:
            modulos = [l.strip() for l in fh
                       if l.strip() and not l.startswith("#")]

        culpados = []
        for modulo in modulos:
            manifesto = os.path.join(raiz, modulo, "__manifest__.py")
            if not os.path.exists(manifesto):
                continue
            with open(manifesto, encoding="utf-8") as fh:
                declarado = ast.literal_eval(fh.read())
            for dependencia in declarado.get("depends", []):
                if dependencia in proprietarios:
                    culpados.append("%s -> %s" % (modulo, dependencia))

        self.assertFalse(
            culpados,
            "o FAQ afirma que nada depende do Enterprise, mas: %s" % culpados)

    def test_o_rodape_leva_de_volta_ao_edlab(self):
        """Os dois sites são da mesma casa e se apontam: o do EdLab manda para
        /liber no rodapé, e este manda de volta para edlab.press. O link é
        absoluto de propósito — o liber_site também roda em Odoo de terceiro,
        onde um /edlab relativo não existiria."""
        html = self._pagina()
        self.assertIn("https://www.edlab.press", html,
                      "o rodapé perdeu o caminho de volta para o EdLab")

    def test_manuais_tem_rota_propria(self):
        """Caminho feliz: /liber/docs existe (o README já o anunciava quando
        ele dava 404) e entrega o índice e cada manual."""
        raiz = self.url_open("/liber/docs", allow_redirects=False)
        self.assertEqual(raiz.status_code, 301, "/liber/docs deixou de redirecionar")
        self.assertTrue(raiz.headers.get("Location", "").endswith("/liber/docs/"),
                        "o redirecionamento tem de terminar em barra")

        indice = self.url_open("/liber/docs/")
        self.assertEqual(indice.status_code, 200)
        self.assertIn("docs.js", indice.text)

        manual = self.url_open("/liber/docs/liber_nfe_focus.html")
        self.assertEqual(manual.status_code, 200)
        self.assertIn("Emissão de NF-e", manual.text)

    def test_landing_nao_anuncia_mais_a_nota_fiscal(self):
        """A seção da NF-e saiu da vitrine por decisão editorial: emitir nota
        não é o que distingue o Liber, e a página já era longa. O assunto
        continua no FAQ e nos manuais — o que sai é o destaque."""
        html = self._pagina()
        self.assertNotIn('id="fiscal"', html, "a seção da NF-e voltou à landing")
        self.assertNotIn('href="#fiscal"', html, "o menu voltou a ter o item Fiscal")

    def test_manual_do_focus_nao_fica_orfao(self):
        """O que preocupa ao tirar a seção: era dela que saía o link para o
        manual da emissão. A página tem de continuar levando até ele — hoje
        pela resposta do FAQ — e o manual tem de responder."""
        html = self._pagina()
        self.assertIn("/liber/docs/liber_nfe_focus.html", html,
                      "a landing perdeu o único caminho até o manual da emissão")
        self.assertEqual(
            self.url_open("/liber/docs/liber_nfe_focus.html").status_code, 200)

    def test_a_chamada_do_olist_leva_ao_manual(self):
        """Entrou em 18/08/2026 como card discreto no "E mais": o Liber é
        aberto e mesmo assim alcança marketplace através de um serviço pago e
        fechado — o argumento vive nesse card, e o caminho até o manual não
        pode quebrar."""
        html = self._pagina()
        self.assertIn("Marketplaces via Olist", html,
                      "o card do Olist saiu da home")
        self.assertIn("/liber/docs/liber_olist.html", html,
                      "o card do Olist perdeu o link do manual")
        self.assertEqual(
            self.url_open("/liber/docs/liber_olist.html").status_code, 200,
            "o manual do Olist não responde — o card leva a lugar nenhum")

    def test_todo_manual_aparece_no_indice(self):
        """Manual que existe em docs/ mas não está no catálogo do docs.js é
        manual invisível: o índice monta os cartões a partir do DOCS, então
        quem não está lá não é encontrado por ninguém."""
        docs = os.path.join(_RAIZ, "static", "docs")
        with open(os.path.join(docs, "docs.js"), encoding="utf-8") as fh:
            catalogo = set(re.findall(r'slug:\s*"([^"]+)"', fh.read()))

        arquivos = {nome[:-5] for nome in os.listdir(docs)
                    if nome.endswith(".html") and nome != "index.html"}

        invisiveis = sorted(arquivos - catalogo)
        self.assertFalse(invisiveis,
                         "manuais fora do catálogo do docs.js (ninguém os acha): %s"
                         % invisiveis)

        quebrados = sorted(catalogo - arquivos)
        self.assertFalse(quebrados,
                         "o índice anuncia manual que não existe: %s" % quebrados)

    def test_url_antiga_dos_manuais_desvia_para_a_rota_sem_cache(self):
        """A URL de asset continua existindo (o Odoo serve /módulo/static/ por
        conta própria) e entrega uma semana de cache com o docs.js sem versão.
        Foi por ela que o manual da emissão de NF-e sumiu do índice: o catálogo
        em cache era anterior ao manual. Toda página dos manuais carrega o
        desvio para /liber/docs/, senão o buraco reabre no próximo manual."""
        docs = os.path.join(_RAIZ, "static", "docs")
        sem_desvio = []
        for nome in sorted(os.listdir(docs)):
            if not nome.endswith(".html"):
                continue
            with open(os.path.join(docs, nome), encoding="utf-8") as fh:
                if '"/liber_site/static/docs/"' not in fh.read():
                    sem_desvio.append(nome)
        self.assertFalse(sem_desvio,
                         "manuais sem o desvio da URL antiga: %s" % sem_desvio)

    def test_pagina_de_manual_nao_fica_uma_semana_em_cache(self):
        """O motivo de a rota existir. Servido como asset, o manual vinha com
        max-age=604800: publicava-se a correção e o leitor via a versão velha
        por até sete dias, concluindo que nada tinha subido."""
        for url in ("/liber", "/liber/docs/", "/liber/docs/liber_nfe_focus.html"):
            resposta = self.url_open(url)
            self.assertEqual(resposta.headers.get("Cache-Control"), "no-cache",
                             "%s voltou a ser servido com cache" % url)

    def test_manual_inexistente_e_fuga_de_pasta_dao_404(self):
        """Casos de erro: nome que não existe, e caminho que tenta sair de
        docs/ para ler arquivo do módulo."""
        self.assertEqual(self.url_open("/liber/docs/nao-existe.html").status_code, 404)
        fuga = self.url_open("/liber/docs/..%2f..%2f__manifest__.py",
                             allow_redirects=False)
        self.assertNotEqual(fuga.status_code, 200,
                            "caminho com .. leu arquivo de fora de docs/")

    def test_link_de_manual_aponta_para_a_rota_sem_cache(self):
        """De nada adianta a rota se a página continua mandando o visitante
        para /liber_site/static/docs/, que é o caminho com cache de uma semana."""
        html = self._pagina()
        self.assertIn('href="/liber/docs/index.html"', html,
                      "o menu Manuais voltou a apontar para o caminho de asset")
        self.assertNotIn('href="/liber_site/static/docs/', html)

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
