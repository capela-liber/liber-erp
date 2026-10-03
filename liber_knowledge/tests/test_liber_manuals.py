# -*- coding: utf-8 -*-
"""A cópia dos manuais do Liber para o wiki, e quem o lê.

Os testes de sincronização usam uma pasta de manuais montada aqui mesmo
(`docs.js` + dois manuais + uma captura), para controlar o que muda entre uma
passada e outra. Um teste roda contra os manuais de verdade do liber_site: é
ele que pega um manual novo que o conversor não sabe ler.
"""
import os
import shutil
import tempfile

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..tools import wiki

DOCS_JS = '''// catálogo de teste
var DOCS = [
  { area: "Consignação", desc: "Do acordo ao acerto.", items: [
    { slug: "liber_a", title: "Manual A", desc: "O primeiro." },
    { slug: "liber_b", title: "Manual \\"B\\"", desc: "O segundo." },
  ]},
  { area: "Referência", desc: "O que vale para tudo.", items: [
    { slug: "glossario", title: "Glossário", desc: "Siglas." },
  ]},
];
function outraCoisa() { return { slug: "nao_e_manual" }; }
'''

MANUAL_A = '''<html><head><title>Manual A — Manuais do Liber</title></head><body>
<aside class="sidebar" id="sidebar"></aside>
<article class="doc">
<h1>Manual A</h1>
<p class="lead">Veja o <a href="liber_b.html#passo">passo do B</a>,
o <a href="glossario.html">glossário</a> e o
<a href="liber_fora.html">manual que não está no catálogo</a>.</p>
<figure class="shot"><img src="img/a.png" alt="Tela A"></figure>
<figure class="shot"><img src="img/falta.png" alt="Tela que falta"></figure>
<div class="callout tip"><span class="title">Dica</span><p>Texto.</p></div>
</article>
<nav class="pager" id="pager"></nav>
</body></html>'''

MANUAL_B = '''<html><body><article class="doc"><h1>Manual B</h1>
<h2 id="passo">Passo</h2><p>Faça <strong>assim</strong>.</p></article></body></html>'''

GLOSSARIO = '''<html><body><article class="doc"><h1>Glossário</h1>
<p><abbr class="sigla" title="Consignação">C</abbr></p></article></body></html>'''


@tagged('post_install', '-at_install')
class TestCatalogo(TransactionCase):
    """O leitor do docs.js e o conversor, sem banco nenhum no meio."""

    def test_le_areas_e_manuais_na_ordem_do_site(self):
        cat = wiki.ler_catalogo(DOCS_JS)
        self.assertEqual([a['area'] for a in cat], ['Consignação', 'Referência'])
        self.assertEqual([i['slug'] for i in cat[0]['items']], ['liber_a', 'liber_b'])
        # aspas escapadas no JS voltam a ser aspas
        self.assertEqual(cat[0]['items'][1]['title'], 'Manual "B"')

    def test_objeto_com_slug_fora_do_catalogo_nao_entra(self):
        slugs = {i['slug'] for a in wiki.ler_catalogo(DOCS_JS) for i in a['items']}
        self.assertNotIn('nao_e_manual', slugs)

    def test_catalogo_ilegivel_levanta(self):
        with self.assertRaises(ValueError):
            wiki.ler_catalogo('var OUTRA = [];')
        with self.assertRaises(ValueError):
            wiki.ler_catalogo('var DOCS = [\n];')

    def test_catalogo_real_do_site_bate_com_os_arquivos(self):
        docs = self.env['document.page']._liber_docs_dir()
        with open(os.path.join(docs, 'docs.js'), encoding='utf-8') as fh:
            cat = wiki.ler_catalogo(fh.read())
        slugs = {i['slug'] for a in cat for i in a['items']}
        arquivos = {f[:-5] for f in os.listdir(docs) if f.endswith('.html')} - {'index'}
        self.assertTrue(slugs)
        self.assertEqual(slugs, arquivos,
                         "manual no site sem entrada no docs.js, ou o contrário")


@tagged('post_install', '-at_install')
class TestSincronizacao(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Page = cls.env['document.page']
        cls.raiz = cls.env.ref('liber_knowledge.page_liber_manuals')
        # A instalação já copiou os manuais de verdade; os testes com a pasta
        # montada precisam de uma árvore limpa.
        cls.Page.with_context(active_test=False).search(
            [('liber_manual_slug', '!=', False)]).unlink()

    def setUp(self):
        super().setUp()
        self.docs = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.docs)
        os.makedirs(os.path.join(self.docs, 'img'))
        self._escrever('docs.js', DOCS_JS)
        self._escrever('liber_a.html', MANUAL_A)
        self._escrever('liber_b.html', MANUAL_B)
        self._escrever('glossario.html', GLOSSARIO)
        with open(os.path.join(self.docs, 'img', 'a.png'), 'wb') as fh:
            fh.write(b'\x89PNG')

    def _escrever(self, nome, texto):
        with open(os.path.join(self.docs, nome), 'w', encoding='utf-8') as fh:
            fh.write(texto)

    def _pagina(self, slug):
        return self.Page.search([('liber_manual_slug', '=', slug)])

    def test_cria_a_arvore_do_site(self):
        stats = self.Page._liber_sync_manuals(self.docs)
        self.assertEqual(stats['created'], 3)
        areas = self.Page.search([('parent_id', '=', self.raiz.id)])
        self.assertEqual(set(areas.mapped('name')), {'Consignação', 'Referência'})
        self.assertTrue(all(a.type == 'category' for a in areas))
        a = self._pagina('liber_a')
        self.assertEqual(a.name, 'Manual A')
        self.assertEqual(a.parent_id.name, 'Consignação')
        self.assertFalse(a.company_id, "o manual vale para todas as empresas")
        self.assertEqual(len(a.history_ids), 1)
        self.assertEqual(a.history_head.summary, 'Copiado do site')
        # a ordem da árvore é a do site, não a alfabética
        b = self._pagina('liber_b')
        self.assertLess(a.liber_sequence, b.liber_sequence)
        self.assertLess(a.parent_id.liber_sequence, self._pagina('glossario').parent_id.liber_sequence)

    def test_conteudo_links_e_capturas(self):
        self.Page._liber_sync_manuals(self.docs)
        a, b, glo = self._pagina('liber_a'), self._pagina('liber_b'), self._pagina('glossario')
        html = a.content
        self.assertIn('href="/odoo/manuais/%d#passo"' % b.id, html)
        self.assertIn('href="/odoo/manuais/%d"' % glo.id, html)
        # manual fora do catálogo continua indo para o site
        self.assertIn('href="/liber_site/static/docs/liber_fora.html"', html)
        self.assertIn('src="/liber_site/static/docs/img/a.png"', html)
        # captura que não existe vira o espaço reservado, não imagem quebrada
        self.assertNotIn('img/falta.png"', html.replace('<code', ''))
        self.assertIn('Tela a inserir', html)
        # o estilo vai embutido (o <style> do site não chega ao Odoo)
        self.assertIn('style="', html)
        self.assertNotIn('sidebar', html)
        self.assertNotIn('<article', html)
        # o título já é o nome da página: o <h1> do manual não se repete
        self.assertNotIn('<h1', html)

    def test_segunda_passada_nao_mexe(self):
        self.Page._liber_sync_manuals(self.docs)
        stats = self.Page._liber_sync_manuals(self.docs)
        self.assertEqual((stats['created'], stats['updated'], stats['unchanged']), (0, 0, 3))
        self.assertEqual(len(self._pagina('liber_a').history_ids), 1)
        self.assertEqual(self.Page.search_count([('liber_manual_slug', '=like', 'area:%')]), 2)

    def test_manual_alterado_no_site_atualiza_com_historico(self):
        self.Page._liber_sync_manuals(self.docs)
        self._escrever('liber_b.html', MANUAL_B.replace('assim', 'assado'))
        stats = self.Page._liber_sync_manuals(self.docs)
        self.assertEqual(stats['updated'], 1)
        b = self._pagina('liber_b')
        self.assertIn('assado', b.content)
        self.assertEqual(len(b.history_ids), 2)
        self.assertEqual(b.history_head.summary, 'Atualizado do site')

    def test_pagina_editada_no_wiki_nao_e_sobrescrita(self):
        self.Page._liber_sync_manuals(self.docs)
        b = self._pagina('liber_b')
        b.write({'content': '<p>Escrito aqui dentro.</p>'})
        self._escrever('liber_b.html', MANUAL_B.replace('assim', 'assado'))
        stats = self.Page._liber_sync_manuals(self.docs)
        self.assertEqual(stats['edited'], ['Manual "B"'])
        self.assertEqual(b.content, '<p>Escrito aqui dentro.</p>')

    def test_arquivo_do_manual_faltando_e_relatado(self):
        os.remove(os.path.join(self.docs, 'glossario.html'))
        stats = self.Page._liber_sync_manuals(self.docs)
        self.assertEqual(stats['missing'], ['glossario'])
        self.assertTrue(self._pagina('liber_a').content)

    def test_catalogo_ausente_levanta_erro_legivel(self):
        os.remove(os.path.join(self.docs, 'docs.js'))
        with self.assertRaises(UserError):
            self.Page._liber_sync_manuals(self.docs)

    def test_manuais_de_verdade(self):
        stats = self.Page._liber_sync_manuals()
        self.assertFalse(stats['missing'])
        self.assertGreaterEqual(stats['created'], 40)
        acerto = self._pagina('liber_soc_settlement')
        self.assertEqual(acerto.parent_id.parent_id, self.raiz)
        self.assertIn('/liber_site/static/docs/img/', acerto.content)
        dados = acerto.liber_reader_page()
        self.assertTrue(dados['from_site'])
        self.assertEqual(dados['last_user'], '', "a cópia do site não tem o OdooBot como autor")


@tagged('post_install', '-at_install')
class TestTelaDeLeitura(TransactionCase):
    """Os três métodos que a tela "Manuais" chama, como o usuário que lê."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Page = cls.env['document.page']
        cls.leitor = new_test_user(cls.env, login='manuais_leitor', groups='base.group_user')
        cls.editor = new_test_user(
            cls.env, login='manuais_editor',
            groups='base.group_user,document_page.group_document_editor')
        cls.grupo_fin = cls.env['res.groups'].create({'name': 'Financeiro do teste'})
        cls.cat = Page.create({
            'name': 'Rotinas', 'type': 'category', 'company_id': False,
            'parent_id': cls.env.ref('liber_knowledge.page_internal_manuals').id})
        cls.pagina = Page.create({
            'name': 'Fechar o caixa', 'parent_id': cls.cat.id, 'company_id': False,
            'content': '<p style="color:#6e2f91">Conferir a maquininha antes.</p>'
                       '<script>alert(1)</script>'})
        cls.secreta = Page.create({
            'name': 'Senhas do banco', 'parent_id': cls.cat.id, 'company_id': False,
            'content': '<p>maquininha secreta</p>',
            'groups_id': [(6, 0, [cls.grupo_fin.id])]})

    def _ids(self, nos):
        for no in nos:
            yield no['id']
            yield from self._ids(no['children'])

    def test_arvore_aninha_e_respeita_o_acesso(self):
        arvore = self.env['document.page'].with_user(self.leitor).liber_reader_tree()
        ids = set(self._ids(arvore))
        self.assertIn(self.pagina.id, ids)
        self.assertNotIn(self.secreta.id, ids, "página restrita a outro grupo não aparece")
        raizes = [n['name'] for n in arvore]
        self.assertIn('Manuais internos', raizes)
        internos = next(n for n in arvore if n['name'] == 'Manuais internos')
        rotinas = next(n for n in internos['children'] if n['id'] == self.cat.id)
        self.assertEqual([n['id'] for n in rotinas['children']], [self.pagina.id])

    def test_pagina_sanitizada_com_estilo_e_caminho(self):
        dados = self.pagina.with_user(self.leitor).liber_reader_page()
        self.assertIn('Conferir a maquininha', dados['content'])
        self.assertIn('color:#6e2f91', dados['content'], "o estilo embutido dos manuais sobrevive")
        self.assertNotIn('<script', dados['content'])
        self.assertEqual([p['name'] for p in dados['path']], ['Manuais internos', 'Rotinas'])
        self.assertFalse(dados['can_edit'])
        self.assertFalse(dados['can_create'])

    def test_editor_ganha_os_botoes(self):
        dados = self.pagina.with_user(self.editor).liber_reader_page()
        self.assertTrue(dados['can_edit'])
        self.assertTrue(dados['can_create'])

    def test_categoria_lista_os_filhos(self):
        dados = self.cat.with_user(self.leitor).liber_reader_page()
        self.assertEqual(dados['content'], '')
        self.assertEqual([f['id'] for f in dados['children']], [self.pagina.id])

    def test_busca_no_texto_com_trecho_e_sem_vazar(self):
        achados = self.env['document.page'].with_user(self.leitor).liber_reader_search('maquininha')
        ids = [a['id'] for a in achados]
        self.assertIn(self.pagina.id, ids)
        self.assertNotIn(self.secreta.id, ids)
        trecho = next(a for a in achados if a['id'] == self.pagina.id)['snippet']
        self.assertIn('maquininha', trecho)
        self.assertNotIn('<p', trecho)

    def test_busca_curta_ou_vazia_nao_busca(self):
        Page = self.env['document.page'].with_user(self.leitor)
        self.assertEqual(Page.liber_reader_search(''), [])
        self.assertEqual(Page.liber_reader_search(' a '), [])

    def test_pagina_restrita_nao_abre_para_o_leitor(self):
        with self.assertRaises(AccessError):
            self.secreta.with_user(self.leitor).liber_reader_page()


@tagged('post_install', '-at_install')
class TestHistoricoNaMesmaTransacao(TransactionCase):
    """O defeito do document_page que a herança corrige (ver o modelo)."""

    def test_edicao_na_mesma_transacao_vira_a_versao_atual(self):
        pagina = self.env['document.page'].create(
            {'name': 'Rascunho', 'content': '<p>v1</p>'})
        pagina.write({'content': '<p>v2</p>'})
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(pagina.content, '<p>v2</p>')
        self.assertEqual(pagina.history_head, pagina.history_ids.sorted()[:1])
        self.assertEqual(len(pagina.history_ids), 2)


@tagged('post_install', '-at_install')
class TestAcesso(TransactionCase):
    """O wiki é de dentro: interno lê, portal não chega nem perto."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.interno = new_test_user(cls.env, login='wiki_interno', groups='base.group_user')
        cls.portal = new_test_user(cls.env, login='wiki_portal', groups='base.group_portal')
        cls.admin_cfg = new_test_user(cls.env, login='wiki_cfg', groups='base.group_system')
        cls.pagina = cls.env['document.page'].create({
            'name': 'Como fechar o mês',
            'parent_id': cls.env.ref('liber_knowledge.page_internal_manuals').id,
            'content': '<p>Passo a passo.</p>',
            'company_id': False,
        })

    def test_usuario_interno_le_sem_grupo_extra(self):
        self.assertTrue(self.interno.has_group('document_knowledge.group_document_user'))
        pagina = self.pagina.with_user(self.interno)
        self.assertEqual(pagina.content, '<p>Passo a passo.</p>')
        self.assertIn(self.env.ref('liber_knowledge.page_faq'),
                      self.env['document.page'].with_user(self.interno).search([]))

    def test_o_app_se_chama_manual_em_todo_idioma(self):
        menu = self.env.ref('document_knowledge.menu_document_root')
        self.env['document.page']._liber_app_name()
        for code, _nome in self.env['res.lang'].get_installed():
            self.assertEqual(menu.with_context(lang=code).name, 'Manual', code)

    def test_o_app_tem_icone_proprio_e_mora_ao_lado_do_treinamento(self):
        menu = self.env.ref('document_knowledge.menu_document_root')
        self.env['document.page']._liber_app_name()
        self.assertEqual(menu.web_icon, 'liber_knowledge,static/description/icon.png')
        vizinho = self.env.ref('capela_training.menu_training_root', raise_if_not_found=False)
        if vizinho:
            raizes = self.env['ir.ui.menu'].search([('parent_id', '=', False)], order='sequence, id')
            ids = raizes.ids
            self.assertEqual(ids.index(menu.id), ids.index(vizinho.id) + 1,
                             "o Manual vem logo depois do Treinamento")

    def test_usuario_interno_nao_edita(self):
        with self.assertRaises(AccessError):
            self.pagina.with_user(self.interno).write({'name': 'Outro'})

    def test_portal_nao_le(self):
        self.assertFalse(self.portal.has_group('document_knowledge.group_document_user'))
        with self.assertRaises(AccessError):
            self.env['document.page'].with_user(self.portal).search([])

    def test_admin_das_configuracoes_gerencia(self):
        self.assertTrue(self.admin_cfg.has_group('document_page.group_document_manager'))
        self.pagina.with_user(self.admin_cfg).write({'name': 'Como fechar o mês (v2)'})

    def test_so_gerente_dispara_a_atualizacao(self):
        with self.assertRaises(UserError):
            self.env['document.page'].with_user(self.interno).action_liber_sync_manuals()
        acao = self.env['document.page'].with_user(self.admin_cfg).action_liber_sync_manuals()
        self.assertEqual(acao['tag'], 'display_notification')
