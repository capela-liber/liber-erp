# -*- coding: utf-8 -*-
"""A aba Produtos: ler a ficha do Olist e alterá-la (NOTES.md §14).

O catálogo é o problema sério da integração: 219 dos 580 produtos do Olist não
casam por ISBN, e 55% deles são o MESMO livro com o código antigo lá. Casar à
mão resolve a tela; **corrigir o ISBN no Olist** resolve a causa — o casamento
passa a valer sozinho, para sempre.

O que se prova aqui:

1. a ficha completa entra no espelho (preço, situação, marca, NCM, peso);
2. toda alteração devolve a ficha INTEIRA — mandar só o campo mudado apostaria
   que a API faz atualização parcial, e perder essa aposta apaga peso, NCM e
   descrição do livro;
3. nada disso escreve enquanto a conta estiver em somente-leitura.
"""
import json
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client

# Recorte real do que `produto.obter.php` devolveu em 15/08/2026
FICHA = {
    'id': '738964228', 'codigo': '9788587329760', 'nome': 'A cena lenta',
    'preco': 54.9, 'preco_promocional': 0, 'preco_custo': 0,
    'situacao': 'A', 'gtin': '', 'marca': 'Hedra',
    'categoria': 'Livros >> Mundo Indígena', 'ncm': '4901.99.00',
    'unidade': 'UN', 'peso_liquido': 0.324, 'peso_bruto': 0.324,
    'descricao_complementar': '<p>Romance</p>',
    'seo_title': 'A cena lenta', 'seo_keywords': 'literatura',
    'estoque_minimo': 2, 'origem': 0, 'tipo': 'P',
}
OK = '{"retorno":{"status":"OK"}}'


@tagged('post_install', '-at_install')
class TestOlistCatalog(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Catálogo", 'company_id': cls.env.company.id,
            'token': "TOKEN-K", 'read_only': True,
        })
        cls.livro = cls.env['product.product'].create({
            'name': "A cena lenta (Cláudio Oliveira. Editora Circuito)",
            'barcode': "9788595820395", 'list_price': 62.0, 'type': 'consu'})
        cls.linha = cls.env['olist.product'].create({
            'account_id': cls.account.id, 'olist_id': '738964228',
            'codigo': '9788587329760', 'name': 'A cena lenta'})

    def _ler_ficha(self):
        with patch.object(olist_client, 'get_produto', return_value=dict(FICHA)):
            self.linha.action_read_ficha()

    def _escrever(self):
        """Devolve (enviado, patcher) para inspecionar o que foi mandado."""
        enviado = {}

        def fake_update(token, ficha):
            enviado.update(ficha)
            return (json.dumps({'produto': ficha}), OK)

        return enviado, patch.object(olist_client, 'update_produto',
                                     side_effect=fake_update)

    # -- 1. a ficha ---------------------------------------------------------
    def test_ficha_lands_on_the_mirror(self):
        self._ler_ficha()
        self.assertEqual(self.linha.preco_olist, 54.9)
        self.assertEqual(self.linha.situacao_olist, 'A')
        self.assertEqual(self.linha.marca, 'Hedra')
        self.assertEqual(self.linha.ncm, '4901.99.00')
        self.assertEqual(self.linha.peso_liquido, 0.324)
        self.assertTrue(self.linha.ficha_lida_em)
        self.assertIn('seo_title', self.linha.ficha_json,
                      "os 52 campos têm de ficar guardados inteiros")

    def test_price_divergence_is_visible(self):
        self.linha.product_id = self.livro
        self._ler_ficha()
        self.assertEqual(self.linha.preco_odoo, 62.0)
        self.assertEqual(round(self.linha.divergencia_preco, 2), -7.1)

    # -- 2. somente leitura barra tudo --------------------------------------
    def test_read_only_blocks_every_write(self):
        self.linha.product_id = self.livro
        self._ler_ficha()
        for acao in ('action_push_price', 'action_push_isbn',
                     'action_deactivate_in_olist'):
            with self.assertRaises(UserError, msg=acao):
                getattr(self.linha, acao)()

    # -- 3. a ficha volta INTEIRA -------------------------------------------
    def test_write_sends_the_whole_card_not_just_the_field(self):
        """A aposta que não se faz.

        Não se sabe se `produto.alterar` faz atualização parcial ou
        substituição. Mandar só `preco` apostaria que é parcial; se não for, o
        livro perde peso, NCM, descrição e SEO de uma vez. Ler, trocar um campo
        e devolver tudo funciona nas duas hipóteses.
        """
        self.account.read_only = False
        self.linha.product_id = self.livro
        enviado, patcher = self._escrever()
        with patcher, patch.object(olist_client, 'get_produto',
                                   return_value=dict(FICHA)):
            self.linha.action_push_price()

        self.assertEqual(enviado['preco'], 62.0, "não mandou o preço do Odoo")
        # e tudo o mais continua lá
        for campo in ('ncm', 'peso_liquido', 'marca', 'seo_title',
                      'descricao_complementar', 'estoque_minimo'):
            self.assertIn(campo, enviado,
                          "a ficha foi enviada mutilada: sumiu %s" % campo)
        self.assertEqual(enviado['ncm'], '4901.99.00')

    def test_isbn_fix_writes_code_and_gtin(self):
        # Para livro, ISBN-13 É EAN-13: o marketplace precisa do GTIN para
        # identificar o título fora do nosso código.
        self.account.read_only = False
        self.linha.product_id = self.livro
        enviado, patcher = self._escrever()
        with patcher, patch.object(olist_client, 'get_produto',
                                   return_value=dict(FICHA)):
            self.linha.action_push_isbn()
        self.assertEqual(enviado['codigo'], '9788595820395')
        self.assertEqual(enviado['gtin'], '9788595820395')

    def test_deactivate_sets_situacao_inactive(self):
        self.account.read_only = False
        enviado, patcher = self._escrever()
        with patcher, patch.object(olist_client, 'get_produto',
                                   return_value=dict(FICHA)):
            self.linha.action_deactivate_in_olist()
        self.assertEqual(enviado['situacao'], 'I')

    def test_price_needs_a_matched_product(self):
        # Sem produto casado não há preço nosso para mandar — e isso é dito,
        # não adivinhado.
        self.account.read_only = False
        _enviado, patcher = self._escrever()
        with patcher as upd:
            acao = self.linha.action_push_price()
        upd.assert_not_called()
        self.assertEqual(acao['params']['type'], 'warning')

    def test_write_keeps_the_raw_exchange(self):
        self.account.read_only = False
        self.linha.product_id = self.livro
        _enviado, patcher = self._escrever()
        with patcher, patch.object(olist_client, 'get_produto',
                                   return_value=dict(FICHA)):
            self.linha.action_push_price()
        self.assertIn('ENVIADO', self.linha.last_write_result)
        self.assertIn('RESPOSTA', self.linha.last_write_result)

    # -- 4. criar no Odoo ---------------------------------------------------
    def test_create_in_odoo_uses_the_card(self):
        self._ler_ficha()
        self.linha.action_create_in_odoo()
        produto = self.linha.product_id
        self.assertTrue(produto)
        self.assertEqual(produto.barcode, '9788587329760')
        self.assertEqual(produto.list_price, 54.9)
        # O Odoo arredonda o peso pela precisão decimal 'Stock Weight' (2
        # casas): 0,324 kg entra como 0,32. São 4 gramas num livro — mas fica
        # dito, para ninguém tomar isso por perda de dado do nosso lado.
        self.assertAlmostEqual(produto.weight, 0.324, places=2)

    def test_create_refuses_before_reading_the_card(self):
        acao = self.linha.action_create_in_odoo()
        self.assertEqual(acao['params']['type'], 'warning')
        self.assertFalse(self.linha.product_id)

    def test_create_skips_what_is_already_matched(self):
        self.linha.product_id = self.livro
        self._ler_ficha()
        acao = self.linha.action_create_in_odoo()
        self.assertEqual(acao['params']['type'], 'warning')
        self.assertEqual(self.linha.product_id, self.livro)


@tagged('post_install', '-at_install')
class TestOlistAbsent(TransactionCase):
    """A pergunta inversa: o que é nosso e ainda não está no Olist.

    Foi ela que mostrou 446 livros físicos ausentes do marketplace — 80 deles
    com estoque parado, 9.459 exemplares que ninguém estava oferecendo.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Ausentes", 'company_id': cls.env.company.id,
            'token': "TOKEN-A", 'read_only': True})
        cls.no_olist = cls.env['product.product'].create({
            'name': "Livro espelhado", 'barcode': "9781111111119",
            'list_price': 40.0, 'type': 'consu'})
        cls.fora = cls.env['product.product'].create({
            'name': "Livro fora do Olist", 'barcode': "9782222222227",
            'list_price': 50.0, 'type': 'consu'})
        cls.env['olist.product'].create({
            'account_id': cls.account.id, 'olist_id': '8001',
            'codigo': '9781111111119', 'name': "Livro espelhado",
            'product_id': cls.no_olist.id})

    def test_absent_flag_separates_the_two(self):
        self.assertFalse(self.no_olist.product_tmpl_id.olist_absent)
        self.assertTrue(self.fora.product_tmpl_id.olist_absent)

    def test_flag_flips_when_the_mirror_line_appears(self):
        # É o vínculo que decide, e ele muda quando alguém casa o livro à mão.
        linha = self.env['olist.product'].create({
            'account_id': self.account.id, 'olist_id': '8002',
            'codigo': '9782222222227', 'name': "Livro fora"})
        self.fora.product_tmpl_id.invalidate_recordset()
        self.assertTrue(self.fora.product_tmpl_id.olist_absent)
        linha.product_id = self.fora
        self.fora.product_tmpl_id.invalidate_recordset()
        self.assertFalse(self.fora.product_tmpl_id.olist_absent)

    def test_publish_is_blocked_while_read_only(self):
        with self.assertRaises(UserError):
            self.fora.product_tmpl_id.action_publish_in_olist()

    def test_publish_sends_the_identity_and_not_the_stock(self):
        """Manda o essencial; o saldo NÃO vai junto.

        Quem manda estoque é o push, que aplica a margem de segurança e a
        regra de empresa. Mandar saldo aqui seria uma segunda porta para o
        mesmo número, sem nenhuma das duas travas.
        """
        self.account.read_only = False
        enviado = {}

        def fake_create(token, ficha):
            enviado.update(ficha)
            return (json.dumps({'produto': ficha}), '{"retorno":{"status":"OK"}}')

        with patch.object(olist_client, 'create_produto', side_effect=fake_create):
            self.fora.product_tmpl_id.action_publish_in_olist()

        self.assertEqual(enviado['codigo'], '9782222222227')
        self.assertEqual(enviado['gtin'], '9782222222227')
        self.assertEqual(enviado['preco'], 50.0)
        self.assertEqual(enviado['situacao'], 'A')
        for proibido in ('estoque', 'saldo', 'quantidade'):
            self.assertNotIn(proibido, enviado,
                             "o saldo não pode ir junto na criação")

    def test_publish_refuses_a_book_without_isbn(self):
        self.account.read_only = False
        sem_isbn = self.env['product.product'].create({
            'name': "Sem ISBN", 'type': 'consu'})
        with patch.object(olist_client, 'create_produto') as criou:
            acao = sem_isbn.product_tmpl_id.action_publish_in_olist()
        criou.assert_not_called()
        self.assertEqual(acao['params']['type'], 'warning')

    def test_publish_skips_what_is_already_there(self):
        self.account.read_only = False
        with patch.object(olist_client, 'create_produto') as criou:
            acao = self.no_olist.product_tmpl_id.action_publish_in_olist()
        criou.assert_not_called()
        self.assertEqual(acao['params']['type'], 'warning')


@tagged('post_install', '-at_install')
class TestOlistCardEditing(TransactionCase):
    """Editar a ficha do Olist a partir do Odoo (NOTES.md §14.4).

    A regra da tela: **editar aqui muda só o espelho**. O Olist só sabe quando
    alguém manda. Sem isso, um campo digitado por engano viraria escrita numa
    conta viva no instante do Enter.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Edição", 'company_id': cls.env.company.id,
            'token': "TOKEN-E", 'read_only': True})
        cls.linha = cls.env['olist.product'].create({
            'account_id': cls.account.id, 'olist_id': '738964228',
            'codigo': '9788587329760', 'name': 'A cena lenta'})
        with patch.object(olist_client, 'get_produto', return_value=dict(FICHA)):
            cls.linha.action_read_ficha()

    def test_a_freshly_read_card_has_nothing_pending(self):
        self.assertFalse(self.linha.tem_alteracao)
        self.assertFalse(self.linha.alteracoes_pendentes)

    def test_editing_marks_pending_and_says_what_changed(self):
        self.linha.ncm = '4901.10.00'
        self.assertTrue(self.linha.tem_alteracao)
        self.assertIn('ncm', self.linha.alteracoes_pendentes)
        self.assertIn('4901.99.00', self.linha.alteracoes_pendentes)
        self.assertIn('4901.10.00', self.linha.alteracoes_pendentes)

    def test_editing_does_not_write_to_olist(self):
        # O ponto da tela: digitar não é enviar.
        with patch.object(olist_client, 'update_produto') as escreveu:
            self.linha.marca = 'Circuito'
            self.linha.categoria = 'Livros >> Arte'
        escreveu.assert_not_called()

    def test_push_sends_only_the_edited_fields_but_the_whole_card(self):
        self.account.read_only = False
        self.linha.marca = 'Circuito'
        self.linha.peso_liquido = 0.5
        enviado = {}

        def fake_update(token, ficha):
            enviado.update(ficha)
            return (json.dumps({'produto': ficha}), OK)

        with patch.object(olist_client, 'update_produto', side_effect=fake_update), \
             patch.object(olist_client, 'get_produto', return_value=dict(FICHA)):
            self.linha.action_push_changes()

        self.assertEqual(enviado['marca'], 'Circuito')
        self.assertEqual(enviado['peso_liquido'], 0.5)
        # o que não foi editado volta como estava
        self.assertEqual(enviado['ncm'], '4901.99.00')
        self.assertEqual(enviado['seo_title'], 'A cena lenta')

    def test_push_is_blocked_while_read_only(self):
        self.linha.marca = 'Circuito'
        with self.assertRaises(UserError):
            self.linha.action_push_changes()

    def test_discard_goes_back_to_what_olist_has(self):
        self.linha.marca = 'Errado'
        self.linha.preco_olist = 1.0
        self.linha.action_discard_changes()
        self.assertEqual(self.linha.marca, 'Hedra')
        self.assertEqual(self.linha.preco_olist, 54.9)
        self.assertFalse(self.linha.tem_alteracao)

    def test_pending_clears_after_a_successful_push(self):
        # O envio relê a ficha, então o pendente tem de zerar sozinho.
        self.account.read_only = False
        self.linha.marca = 'Circuito'
        depois = dict(FICHA, marca='Circuito')
        with patch.object(olist_client, 'update_produto',
                          return_value=('{}', OK)), \
             patch.object(olist_client, 'get_produto', return_value=depois):
            self.linha.action_push_changes()
        self.assertFalse(self.linha.tem_alteracao,
                         "ficou pendente depois de enviado")

    # -- a ficha inteira, como pares chave/valor -----------------------------
    def test_the_whole_card_shows_up_as_editable_pairs(self):
        """"São 50 campos" — e todos aparecem, sem eu adivinhar quais importam."""
        campos = {c.chave: c for c in self.linha.field_ids}
        # os que não têm coluna própria estão lá
        for chave in ('seo_title', 'seo_keywords', 'estoque_minimo',
                      'origem', 'tipo'):
            self.assertIn(chave, campos, "sumiu da ficha: %s" % chave)
        # e os que TÊM coluna própria não se repetem: duas portas, não
        for chave in ('preco', 'ncm', 'marca', 'nome', 'codigo', 'situacao'):
            self.assertNotIn(chave, campos,
                             "%s tem campo próprio e apareceu duas vezes" % chave)

    def test_structured_values_are_shown_but_locked(self):
        # Devolver uma lista como texto colado corromperia a ficha do livro.
        ficha = dict(FICHA, anexos=[{'anexo': 'https://x/y.jpg'}])
        with patch.object(olist_client, 'get_produto', return_value=ficha):
            self.linha.action_read_ficha()
        anexos = self.linha.field_ids.filtered(lambda c: c.chave == 'anexos')
        self.assertTrue(anexos)
        self.assertFalse(anexos.editavel, "estrutura não pode ser editável")
        self.assertIn('anexo', anexos.valor)

    def test_editing_a_generic_field_becomes_a_pending_change(self):
        campo = self.linha.field_ids.filtered(lambda c: c.chave == 'seo_title')
        campo.valor = "A cena lenta — Cláudio Oliveira"
        self.assertTrue(campo.alterado)
        self.assertTrue(self.linha.tem_alteracao)
        self.assertIn('seo_title', self.linha.alteracoes_pendentes)

    def test_generic_field_is_sent_with_the_original_type(self):
        """Número volta número.

        Reenviar tudo como string funciona às vezes e falha calado noutras — e
        "às vezes" não é critério para escrever em catálogo vivo.
        """
        self.account.read_only = False
        campo = self.linha.field_ids.filtered(
            lambda c: c.chave == 'estoque_minimo')
        campo.valor = '5'
        enviado = {}

        def fake_update(token, ficha):
            enviado.update(ficha)
            return (json.dumps({'produto': ficha}), OK)

        with patch.object(olist_client, 'update_produto', side_effect=fake_update), \
             patch.object(olist_client, 'get_produto', return_value=dict(FICHA)):
            self.linha.action_push_changes()

        self.assertEqual(enviado['estoque_minimo'], 5)
        self.assertIsInstance(enviado['estoque_minimo'], int,
                              "mandou texto onde havia número")

    def test_rereading_the_card_discards_local_edits(self):
        # Reler é dizer "quero o que está lá".
        campo = self.linha.field_ids.filtered(lambda c: c.chave == 'seo_title')
        campo.valor = "outro"
        with patch.object(olist_client, 'get_produto', return_value=dict(FICHA)):
            self.linha.action_read_ficha()
        campo = self.linha.field_ids.filtered(lambda c: c.chave == 'seo_title')
        self.assertEqual(campo.valor, 'A cena lenta')
        self.assertFalse(self.linha.tem_alteracao)

    def test_the_catalogue_screen_is_pbook_only(self):
        """"Catálogo" tem uma definição, e ela mora no domínio da ação.

        Serviço editorial, retirada de lucros e o catálogo de distribuição de
        terceiros não são livro nosso para publicar. A aproximação anterior
        ("estocável") trazia 3.632 registros no staging; pbook traz 428.
        """
        acao = self.env.ref('liber_olist.action_olist_absent')
        dominio = acao.domain.replace('\n', ' ')
        self.assertIn("'metabooks_product_type.name', '=', 'pbook'", dominio)
        self.assertIn("'olist_absent', '=', True", dominio)

    def test_the_absent_filters_are_and_not_or(self):
        """Filtros vizinhos sem separador o Odoo combina com OU.

        Sem os separadores, "Livro físico" e "Com estoque" viravam "físico OU
        com estoque" — e a tela trazia o catálogo inteiro.
        """
        from lxml import etree
        vista = self.env.ref('liber_olist.view_olist_absent_search')
        arch = etree.fromstring(vista.arch)
        nos = [n.tag if n.tag == 'separator' else n.get('name')
               for n in arch if n.tag in ('filter', 'separator')]
        i_fisico, i_saldo = nos.index('fisico'), nos.index('com_saldo')
        self.assertIn('separator', nos[i_fisico + 1:i_saldo],
                      "sem separador entre os dois, o Odoo faz OU")

    def test_availability_is_in_the_absent_report(self):
        """A disponibilidade declarada pelo Metabooks entra no relatório.

        Dos 428 pbooks fora do Olist no staging, 227 estão "Disponível" — o
        resto é indisponível, retirado de venda, esgotado ou substituído por
        edição nova. Publicar esses seria oferecer o que a editora já tirou de
        circulação, por isso ela é coluna, filtro e agrupamento.
        """
        from lxml import etree
        lista = etree.fromstring(
            self.env.ref('liber_olist.view_olist_absent_list').arch)
        campos = [n.get('name') for n in lista.iter('field')]
        self.assertIn('metabooks_product_availability', campos)

        busca = etree.fromstring(
            self.env.ref('liber_olist.view_olist_absent_search').arch)
        filtros = [n.get('name') for n in busca.iter('filter')]
        self.assertIn('disponivel', filtros)
        self.assertIn('g_disp', filtros)

    def test_availability_filter_is_anded_with_the_stock_one(self):
        # Mesma armadilha do OU: sem separador, "Disponível" e "Com estoque"
        # virariam alternativas em vez de somarem-se.
        from lxml import etree
        arch = etree.fromstring(
            self.env.ref('liber_olist.view_olist_absent_search').arch)
        nos = [n.tag if n.tag == 'separator' else n.get('name')
               for n in arch if n.tag in ('filter', 'separator')]
        i_disp, i_saldo = nos.index('disponivel'), nos.index('com_saldo')
        entre = nos[min(i_disp, i_saldo) + 1:max(i_disp, i_saldo)]
        self.assertIn('separator', entre)

    def test_a_successful_action_returns_nothing_and_does_not_flash(self):
        """Sucesso não devolve ação — e é isso que tira o pisca da tela.

        Um botão que não devolve nada faz o cliente web recarregar o registro
        sozinho, em silêncio (view_button_hook.js: onClose -> reload). O
        `reload` explícito, que eu tinha posto, recarrega a PÁGINA inteira: a
        tela pisca e volta ao mesmo lugar de onde saiu.
        """
        with patch.object(olist_client, 'get_produto', return_value=dict(FICHA)):
            acao = self.linha.action_read_ficha()
        self.assertFalse(acao, "ação de sucesso não deve devolver nada")
