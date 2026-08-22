# -*- coding: utf-8 -*-
"""O sentido de volta: pedido do Olist -> pedido no Odoo (NOTES.md §12).

Os payloads abaixo são recortes do que a conta REAL devolveu em 13/08/2026 —
inclusive as duas coisas que a pesquisa de papel tinha errado: o canal vem em
`ecommerce.nomeEcommerce` (não `canalVenda`), e o ISBN do item vem COM hífen
enquanto o `barcode` do Odoo é sem.

O que se prova aqui é o que decide se a tela é confiável:

1. o canal vira Canal de Venda (`crm.team`) — casando com o que já existe,
   inclusive arquivado, em vez de criar um segundo com o mesmo nome;
2. o ISBN casa apesar do hífen, e ISBN que não casa IMPEDE a importação em vez
   de deixar o pedido entrar com menos livros;
3. importar registra por inteiro; a entrega fica com a equipe.
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.service.model import call_kw
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client

LISTAGEM = [
    {'id': '743491633', 'numero': '1', 'data_pedido': '24/09/2025',
     'nome': 'Jorge Sallum', 'situacao': 'Entregue', 'valor': 64.99,
     'numero_ecommerce': '2000013159195532',
     # o rastreio vem NA LISTAGEM, sem custo de detalhe
     'codigo_rastreamento': 'P0XMHTN3289Q7H',
     'url_rastreamento': 'https://envios.olist.com/rastreios/pacote/P0XMHTN3289Q7H'},
    {'id': '743491999', 'numero': '2', 'data_pedido': '25/09/2025',
     'nome': 'Maria Silva', 'situacao': 'Cancelado', 'valor': 30.0},
]

DETALHE_ML = {
    'id': '743491633', 'numero': '1', 'situacao': 'Entregue',
    'data_pedido': '24/09/2025', 'id_nota_fiscal': '0',
    'ecommerce': {'id': '13594', 'numeroPedidoEcommerce': '2000013159195532',
                  'numeroPedidoCanalVenda': '', 'nomeEcommerce': 'Mercado Livre'},
    'cliente': {'nome': 'Jorge Sallum', 'cpf_cnpj': '171.037.078-55',
                'tipo_pessoa': 'F', 'email': 'jorge@hedra.com.br', 'uf': 'SP'},
    # ISBN COM hífen, como o Olist manda de verdade
    'itens': [{'item': {'id_produto': '738964228',
                        'codigo': '978-85-7715-835-5',
                        'descricao': 'A toca iluminada', 'unidade': 'UN',
                        'quantidade': '1', 'valor_unitario': '49.00'}}],
}


@tagged('post_install', '-at_install')
class TestOlistOrders(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Pedidos", 'company_id': cls.env.company.id,
            'token': "TOKEN-P", 'read_only': True,
        })
        # O livro do pedido, com o ISBN SEM hífen (como o Odoo guarda)
        cls.livro = cls.env['product.product'].create({
            'name': "A toca iluminada",
            'barcode': "9788577158355",
            'list_price': 49.0,
            'type': 'consu',
            'is_storable': True,
        })

    def _pull(self):
        with patch.object(olist_client, 'list_pedidos',
                          return_value=iter(LISTAGEM)):
            return self.account._pull_orders(interactive=False)

    def _detalhe(self, pedido, dados=None):
        with patch.object(olist_client, 'get_pedido',
                          return_value=dados or DETALHE_ML):
            pedido._read_detail()

    def _arquiva_xml(self, pedido, nota='555'):
        """Importar passou a EXIGIR XML arquivado (§17): a nota é a verdade
        fiscal da venda e é dela que a fatura nasce."""
        if pedido.id_nota_fiscal in (False, '0'):
            pedido.id_nota_fiscal = nota
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "n-%s.xml" % nota,
            'olist_nota_id': pedido.id_nota_fiscal,
            'olist_account_id': self.account.id,
            'partner_id': self.env['res.partner'].search([], limit=1).id,
        })
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_id': self.livro.id,
            'ks_product_name': "A toca iluminada", 'ks_product_qty': 1,
            'ks_price': 49.0, 'ks_product_barcode': '9788577158355'})
        pedido.invalidate_recordset()
        pedido.modified(['id_nota_fiscal'])
        return painel

    def _pedido(self, numero='1'):
        return self.env['olist.order'].search(
            [('account_id', '=', self.account.id), ('numero', '=', numero)])

    # -- 1. a varredura barata ----------------------------------------------
    def test_pull_fills_mirror_without_detail(self):
        res = self._pull()
        self.assertEqual(res['novos'], 2)
        pedido = self._pedido('1')
        self.assertEqual(pedido.state, 'sem_detalhe',
                         "sem detalhe não há canal, e a linha tem de dizer isso")
        self.assertFalse(pedido.canal)
        self.assertEqual(str(pedido.data_pedido), '2025-09-24')

    def test_pull_is_idempotent_and_updates_situacao(self):
        self._pull()
        antes = self.env['olist.order'].search_count(
            [('account_id', '=', self.account.id)])
        res = self._pull()
        self.assertEqual(res['novos'], 0)
        self.assertEqual(res['atualizados'], 2)
        self.assertEqual(self.env['olist.order'].search_count(
            [('account_id', '=', self.account.id)]), antes)

    def test_cancelled_is_not_a_pending_import(self):
        self._pull()
        self.assertEqual(self._pedido('2').state, 'cancelado')

    # -- 2. o canal vira Canal de Venda -------------------------------------
    def test_reading_detail_never_creates_a_channel(self):
        """Ler é ler. Se a leitura criasse canal, a lista de canais da casa
        cresceria sozinha e ninguém teria decidido nada."""
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self.assertEqual(pedido.canal, "Mercado Livre",
                         "o canal cru tem de ficar guardado de todo jeito")
        self.assertFalse(pedido.team_id, "a leitura criou um canal de venda")
        self.assertFalse(self.env['crm.team'].with_context(
            active_test=False).search_count([('name', '=ilike', "Mercado Livre")]))

    def test_mapping_a_channel_is_an_explicit_act(self):
        """Mudou em 18/08/2026: o botão MAPEIA, não cria mais canal de venda.

        Antes ele criava um `crm.team` por nome de canal do Olist — foi assim
        que nasceu o canal 98 "Hedra" da EdLab Press no staging. Agora ele
        registra o canal no espelho e leva à tela onde o par se escolhe; o par
        continua sendo decisão de gente, que é o que o teste velho queria
        dizer.
        """
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self.account.action_map_channels()
        espelho = self.env['olist.channel'].search(
            [('account_id', '=', self.account.id), ('name', '=', "Mercado Livre")])
        self.assertTrue(espelho, "o canal não foi registrado no espelho")
        self.assertFalse(espelho.team_id, "o mapeamento nasce vazio")
        self.assertFalse(self.env['crm.team'].with_context(
            active_test=False).search_count([('name', '=ilike', "Mercado Livre")]),
            "o botão criou canal de venda")

    def test_import_never_creates_the_channel(self):
        """A importação também não inventa canal — mudou em 18/08/2026.

        Antes o canal nascia aqui "para não sumir do relatório". O preço era a
        lista de canais da casa crescendo com nomes de marketplace que ninguém
        escolheu. Sem mapeamento, o pedido entra sem canal: é o mesmo que
        dizer "ainda não classificado", e a pendência está na tela de Canais.
        """
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self._arquiva_xml(pedido)
        pedido._import_to_odoo()
        self.assertFalse(pedido.sale_order_id.team_id)
        self.assertFalse(self.env['crm.team'].with_context(
            active_test=False).search_count([('name', '=ilike', "Mercado Livre")]))

    def test_existing_channel_is_reused_not_duplicated(self):
        existente = self.env['crm.team'].create({
            'name': "Mercado Livre", 'company_id': self.account.company_id.id})
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self.assertEqual(pedido.team_id, existente)
        self.assertEqual(self.env['crm.team'].with_context(
            active_test=False).search_count([('name', '=ilike', "Mercado Livre")]),
            1, "criou um canal duplicado ao lado do que já existia")

    def test_archived_channel_is_pointed_at_not_duplicated(self):
        """O prod tem Marketplaces/eBay/Website arquivados.

        Apontar para o que já existe é o contrário de criar um segundo com o
        mesmo nome. Reativar, porém, não é do módulo: quem decide que um canal
        voltou a existir é a casa (mudou em 18/08/2026 — antes a leitura
        reativava sozinha).
        """
        arquivado = self.env['crm.team'].create({
            'name': "Mercado Livre", 'company_id': self.account.company_id.id,
            'active': False})
        self._pull()
        self._detalhe(self._pedido('1'))
        espelho = self.env['olist.channel'].search(
            [('account_id', '=', self.account.id), ('name', '=', "Mercado Livre")])
        self.assertEqual(espelho.team_id, arquivado,
                         "o espelho devia apontar para o canal que já existia")
        arquivado.invalidate_recordset()
        self.assertFalse(arquivado.active, "a leitura reativou um canal sozinha")
        self.assertEqual(self.env['crm.team'].with_context(
            active_test=False).search_count([('name', '=ilike', "Mercado Livre")]), 1)

    # -- 3. o ISBN com hífen, e o que falta ---------------------------------
    def test_isbn_with_hyphen_matches_the_book(self):
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self.assertEqual(pedido.line_ids.product_id, self.livro,
                         "o ISBN com hífen não casou com o barcode sem hífen")

    def test_unmatched_isbn_blocks_the_import(self):
        detalhe = dict(DETALHE_ML)
        detalhe['itens'] = [{'item': {'codigo': '978-99-0000-000-0',
                                      'descricao': "Livro fantasma",
                                      'quantidade': '1',
                                      'valor_unitario': '10.00'}}]
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, detalhe)
        with self.assertRaises(UserError):
            pedido._import_to_odoo()
        self.assertFalse(pedido.sale_order_id,
                         "o pedido entrou com menos livros do que teve")

    # -- 4. a importação -----------------------------------------------------
    def test_import_creates_the_sale_order_on_the_channel(self):
        # Com um canal de venda de mesmo nome já cadastrado, o espelho nasce
        # apontando para ele e o S sai carimbado.
        self.env['crm.team'].create({
            'name': "Mercado Livre", 'company_id': self.account.company_id.id})
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self._arquiva_xml(pedido)
        pedido._import_to_odoo()

        venda = pedido.sale_order_id
        self.assertTrue(venda)
        self.assertEqual(pedido.state, 'importado')
        self.assertEqual(venda.team_id.name, "Mercado Livre")
        self.assertEqual(venda.client_order_ref, '2000013159195532',
                         "a referência tem de ser o nº do marketplace")
        self.assertEqual(venda.order_line.product_id, self.livro)
        self.assertEqual(venda.order_line.price_unit, 49.0)
        self.assertEqual(venda.state, 'sale',
                         "importar registra por inteiro: a venda confirma")
        self.assertTrue(venda.picking_ids, "importar tem de criar a entrega")
        # (o fixture é um pedido 'Entregue': a entrega conclui sozinha — o
        # caso do pacote ainda em casa é o test_import_confirms_but_does_not_deliver)

    def test_import_is_not_repeated(self):
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self._arquiva_xml(pedido)
        pedido._import_to_odoo()
        primeira = pedido.sale_order_id
        self.assertFalse(pedido._import_to_odoo())
        self.assertEqual(pedido.sale_order_id, primeira)

    def test_buyer_with_document_becomes_a_contact(self):
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self._arquiva_xml(pedido)
        pedido._import_to_odoo()
        self.assertEqual(pedido.partner_id.vat_digits, '17103707855')
        self.assertFalse(pedido.partner_id.is_company, "CPF não é empresa")

    def test_existing_contact_is_found_despite_the_punctuation(self):
        """O cadastro guarda pontuado, o Olist manda pontuado de outro jeito.

        Casar por `vat` cru não acerta e criaria uma ficha nova para quem já é
        cliente — é para isso que existe o `vat_digits` do liber_nfe_xml.
        """
        ja_existe = self.env['res.partner'].create({
            'name': "Jorge Sallum (já cadastrado)", 'vat': "171037078-55"})
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self._arquiva_xml(pedido)
        pedido._import_to_odoo()
        self.assertEqual(pedido.partner_id, ja_existe,
                         "criou contato novo para um cliente que já existia")

    def test_buyer_without_document_falls_back_to_a_channel_contact(self):
        detalhe = dict(DETALHE_ML)
        detalhe['cliente'] = {'nome': 'Comprador ML', 'cpf_cnpj': ''}
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, detalhe)
        self._arquiva_xml(pedido)
        pedido._import_to_odoo()
        self.assertIn("Mercado Livre", pedido.partner_id.name)

    def test_import_needs_the_detail_first(self):
        self._pull()
        with self.assertRaises(UserError):
            self._pedido('1')._import_to_odoo()

    def test_cancelled_order_is_never_imported(self):
        self._pull()
        cancelado = self._pedido('2')
        with self.assertRaises(UserError):
            cancelado._import_to_odoo()

    # -- 5. o laço com o estoque --------------------------------------------
    def test_import_confirms_but_does_not_deliver(self):
        # O corte saiu (22/08/2026): importar SEMPRE confirma a venda, e a
        # entrega fica Pronta — o estoque físico só baixa no clique de quem
        # embalou. O que sai da vitrine no import é o RESERVADO (o push
        # desconta), não o exemplar da estante.
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self._arquiva_xml(pedido)
        pedido.situacao = 'Enviado'      # etiqueta nascida; pacote em casa
        pedido._import_to_odoo()
        self.assertEqual(pedido.sale_order_id.state, 'sale')
        for entrega in pedido.sale_order_id.picking_ids:
            self.assertNotIn(entrega.state, ('done', 'cancel'),
                             "o import concluiu a entrega sozinho — o pacote "
                             "é da casa, quem valida é o funcionário")

    def test_delivered_at_olist_concludes_at_import(self):
        # 'Entregue' é o mundo confirmando que o pacote saiu: aí sim o
        # import já conclui, porque não há pacote a fazer.
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self._arquiva_xml(pedido)
        pedido.situacao = 'Entregue'
        pedido._import_to_odoo()
        for entrega in pedido.sale_order_id.picking_ids:
            self.assertEqual(entrega.state, 'done',
                             "pedido que o Olist já deu por entregue não "
                             "espera embalagem")

    # -- 6. a nota ----------------------------------------------------------
    def test_order_links_to_the_nfe_panel_by_olist_note_id(self):
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+",  # conteúdo é irrelevante aqui; o campo é obrigatório
            'file_name': "nota-teste.xml",
            'olist_nota_id': '555',
            'olist_account_id': self.account.id,
        })
        detalhe = dict(DETALHE_ML, id_nota_fiscal='555')
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, detalhe)
        self.assertEqual(pedido.nfe_panel_id, painel,
                         "o vínculo pedido->nota->XML é o id da nota no Olist")

    # -- 7. a chave do casamento: espelho antes do ISBN ----------------------
    def test_order_item_uses_the_manual_match_from_the_mirror(self):
        """O casamento à mão vale para o pedido também.

        Metade do catálogo do Olist não casa por ISBN. Se o item do pedido
        fosse procurar por ISBN por conta própria, o trabalho de casar a dedo
        no catálogo serviria só para o estoque — e o mesmo livro continuaria
        travando os pedidos, sem ninguém entender por quê.
        """
        outro = self.env['product.product'].create({
            'name': "A toca iluminada (reedição)",
            'barcode': "9786500000009", 'type': 'consu'})
        self.env['olist.product'].create({
            'account_id': self.account.id,
            'olist_id': '738964228',            # o id_produto do item
            'codigo': '9789999999999',          # ISBN que não bate com nada
            'name': "A toca iluminada",
            'product_id': outro.id,             # casado à mão
        })
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self.assertEqual(pedido.line_ids.product_id, outro,
                         "o item do pedido ignorou o casamento do espelho")

    def test_order_item_still_falls_back_to_the_isbn(self):
        # Sem espelho, o ISBN normalizado continua resolvendo.
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self.assertEqual(pedido.line_ids.product_id, self.livro)

    # -- 8. o ponto de entrada da tela ---------------------------------------
    def test_screen_button_pulls_without_knowing_the_account(self):
        """O botão da tela resolve a conta sozinho, pela empresa.

        Quem abre Pedidos quer "trazer o que o Olist tem" — a conta é detalhe
        de configuração, e pedir que a pessoa a escolha em cada tela seria
        empurrar a configuração para dentro do trabalho.

        Chamado pelo MESMO caminho do cliente web (`call_kw` com a lista de
        ids), e não direto no modelo. A diferença não é cerimônia: com
        `@api.model` o `call_kw` não retira os ids do `args` e o botão estoura
        com "takes 1 positional argument but 2 were given" — exatamente o que
        aconteceu em 15/08/2026, com o teste direto passando verde.
        """
        with patch.object(olist_client, 'list_pedidos',
                          return_value=iter(LISTAGEM)):
            acao = call_kw(self.env['olist.order'],
                           'action_pull_from_olist', [[]], {})
        self.assertEqual(acao['params']['type'], 'success')
        self.assertEqual(self.env['olist.order'].search_count(
            [('account_id', '=', self.account.id)]), 2)

    def test_screen_button_says_where_to_create_the_account(self):
        # Sem conta na empresa, o erro aponta para onde criá-la — e nunca sai
        # usando a conta de outra empresa (a regra do §10.5).
        self.account.unlink()
        with self.assertRaises(UserError):
            call_kw(self.env['olist.order'], 'action_pull_from_olist', [[]], {})

    def test_stock_screen_button_is_callable_the_same_way(self):
        # O botão gêmeo da tela de Estoque tem a mesma armadilha.
        with patch.object(olist_client, 'list_produtos', return_value=iter([])):
            acao = call_kw(self.env['olist.product'],
                           'action_pull_from_olist', [[]], {})
        self.assertEqual(acao['params']['type'], 'success')


    # -- 9. a entrega --------------------------------------------------------
    def test_tracking_comes_free_with_the_cheap_sweep(self):
        """Rastreio de mil pedidos por dez chamadas.

        `codigo_rastreamento` e `url_rastreamento` vêm na LISTAGEM, não no
        detalhe — é o dado mais barato da integração, e o que o atendimento
        mais pede quando o comprador pergunta onde está o livro.
        """
        self._pull()
        pedido = self._pedido('1')
        self.assertEqual(pedido.codigo_rastreamento, 'P0XMHTN3289Q7H')
        self.assertIn('envios.olist.com', pedido.url_rastreamento)
        self.assertFalse(pedido.detalhe_lido_em,
                         "não pode ter precisado do detalhe para isso")

    def test_detail_adds_the_carrier_and_the_service(self):
        detalhe = dict(DETALHE_ML, codigo_rastreamento='P0XMHTN3289Q7H',
                       nome_transportador='Olist Envios Pax',
                       forma_frete='Pax - Expresso', data_envio='12/08/2026',
                       valor_frete='18.50')
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, detalhe)
        self.assertEqual(pedido.transportadora, 'Olist Envios Pax')
        self.assertEqual(pedido.forma_frete, 'Pax - Expresso')
        self.assertEqual(str(pedido.data_envio), '2026-08-12')
        self.assertEqual(pedido.valor_frete, 18.50)

    def test_tracking_lands_on_the_odoo_delivery(self):
        """No campo do próprio Odoo, não num nosso.

        `carrier_tracking_ref` é onde o atendimento, o portal do cliente e o
        e-mail de entrega já olham. Um rastreio guardado só no espelho seria um
        número que ninguém acha na hora em que é pedido.
        """
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self._arquiva_xml(pedido)
        pedido._import_to_odoo()
        pedido.action_stamp_tracking()
        entregas = pedido.sale_order_id.picking_ids
        self.assertTrue(entregas, "o import devia ter gerado entrega")
        self.assertTrue(all(p.carrier_tracking_ref == 'P0XMHTN3289Q7H'
                            for p in entregas))

    def test_stamping_says_what_is_still_missing(self):
        # O rastreio chega DEPOIS da venda; sem pedido no Odoo ainda, o carimbo
        # não tem onde pousar — e isso é dito, não silenciado.
        self._pull()
        acao = self._pedido('1').action_stamp_tracking()
        self.assertEqual(acao['params']['type'], 'warning')

    # -- 10. o XML do pedido -------------------------------------------------
    def test_xml_status_has_three_states(self):
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, dict(DETALHE_ML, id_nota_fiscal='0'))
        self.assertEqual(pedido.xml_status, 'sem_nota')

        self._detalhe(pedido, dict(DETALHE_ML, id_nota_fiscal='555'))
        self.assertEqual(pedido.xml_status, 'sem_xml',
                         "nota emitida lá e sem lastro aqui tem de aparecer")

        self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "n.xml",
            'olist_nota_id': '555', 'olist_account_id': self.account.id})
        pedido.invalidate_recordset()
        pedido.modified(['id_nota_fiscal'])
        self.assertEqual(pedido.xml_status, 'arquivado')

    def test_fetch_xml_archives_through_the_same_door(self):
        """Usa o `_ingest_xml` do upload manual — não reimplementa ingestão.

        É o que garante a mesma validação, a mesma deduplicação por chave e a
        mesma prova de empresa pelo CNPJ do emitente.
        """
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, dict(DETALHE_ML, id_nota_fiscal='777'))
        empresa = self.account.company_id
        with patch.object(olist_client, 'get_nota_xml', return_value=b"<nfe/>"), \
             patch.object(type(self.env['nfe.xml.panel']), '_company_from_xml',
                          return_value=empresa), \
             patch.object(type(self.env['nfe.xml.panel']), '_ingest_xml') as ingest:
            status, _d = pedido._fetch_xml()

        self.assertEqual(status, 'OK')
        ingest.assert_called_once()
        vals = ingest.call_args.kwargs
        self.assertEqual(vals['source'], 'olist')
        self.assertEqual(vals['extra_vals']['olist_nota_id'], '777')

    def test_fetch_xml_refuses_a_note_of_another_company(self):
        # A empresa sai do CNPJ do emitente, nunca de quem chamou.
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, dict(DETALHE_ML, id_nota_fiscal='777'))
        outra = self.env['res.company'].search(
            [('id', '!=', self.account.company_id.id)], limit=1)
        if not outra:
            self.skipTest("banco com uma empresa só")
        with patch.object(olist_client, 'get_nota_xml', return_value=b"<nfe/>"), \
             patch.object(type(self.env['nfe.xml.panel']), '_company_from_xml',
                          return_value=outra), \
             patch.object(type(self.env['nfe.xml.panel']), '_ingest_xml') as ingest:
            status, _d = pedido._fetch_xml()
        self.assertEqual(status, 'ERR')
        ingest.assert_not_called()

    def test_fetch_xml_without_a_note_says_so(self):
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, dict(DETALHE_ML, id_nota_fiscal='0'))
        with patch.object(olist_client, 'get_nota_xml') as puxou:
            status, _d = pedido._fetch_xml()
        puxou.assert_not_called()
        self.assertEqual(status, 'ERR')

    def test_import_fetches_the_xml_when_it_is_missing(self):
        """"Um pedido já com o XML na mão" — e agora é condição, não cortesia.

        A importação tenta trazer a nota antes de desistir: quem seleciona
        vinte pedidos não deveria ter de clicar em "Trazer XML" para cada um
        antes de clicar em importar.
        """
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, dict(DETALHE_ML, id_nota_fiscal='888'))
        self.assertEqual(pedido.xml_status, 'sem_xml')

        def arquiva_de_verdade():
            self._arquiva_xml(pedido, nota='888')
            return ('OK', 'arquivado')

        with patch.object(type(pedido), '_fetch_xml',
                          side_effect=arquiva_de_verdade) as buscou:
            pedido._import_to_odoo()

        buscou.assert_called_once()
        self.assertTrue(pedido.sale_order_id)
        self.assertEqual(pedido.xml_status, 'arquivado')
    def test_import_refuses_without_the_xml(self):
        """Sem XML não se segue em frente — a regra mudou em 17/08/2026.

        Antes o pedido entrava e a nota podia chegar depois. Mas a fatura
        NASCE do XML (§16): importar sem ele produzia um pedido que ninguém
        conseguia faturar sem refazer o caminho todo. Agora o import tenta
        trazer a nota e, se ela não vier, recusa e diz por quê.
        """
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, dict(DETALHE_ML, id_nota_fiscal='999'))
        with patch.object(olist_client, 'get_nota_xml', return_value=None):
            with self.assertRaises(UserError):
                pedido._import_to_odoo()
        self.assertFalse(pedido.sale_order_id,
                         "entrou sem nota: a fatura ficaria órfã")

    def test_import_refuses_when_olist_never_issued_the_note(self):
        # Pedido sem nota no Olist não tem o que faturar aqui.
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, dict(DETALHE_ML, id_nota_fiscal='0'))
        with self.assertRaises(UserError):
            pedido._import_to_odoo()

    # -- 11. o sentido que NÃO existe ----------------------------------------
    def test_odoo_never_pushes_orders_to_olist(self):
        """A integração tem um sentido só para pedido: de lá para cá.

        O piloto de julho empurrava `sale.order` para o Olist (`pedido.incluir`)
        pensando em emissão fiscal por lá. A arquitetura decidiu outra coisa: o
        pedido de marketplace NASCE no Olist, e o pedido que nasce no Odoo
        (consignação, venda direta) não tem por que ir para lá. O que sobrava
        era um botão que ninguém usava numa porta de escrita para conta viva.

        Este teste existe para a porta não voltar por distração.
        """
        self.assertFalse(
            hasattr(self.env['sale.order'], 'action_push_to_olist'),
            "o push de pedido para o Olist voltou")
        self.assertNotIn('olist_pedido_id', self.env['sale.order']._fields,
                         "o campo do pedido no Olist voltou")
        self.assertFalse(hasattr(olist_client, 'create_pedido'),
                         "o cliente voltou a saber criar pedido no Olist")

    # -- 12. o que não casou fica dito no próprio pedido ---------------------
    def _detalhe_sem_produto(self, pedido):
        detalhe = dict(DETALHE_ML)
        detalhe['itens'] = [
            {'item': {'codigo': '978-99-0000-000-0', 'descricao': "Livro fantasma",
                      'quantidade': '2', 'valor_unitario': '10.00'}},
            {'item': {'id_produto': '738964228', 'codigo': '978-85-7715-835-5',
                      'descricao': 'A toca iluminada', 'quantidade': '1',
                      'valor_unitario': '49.00'}},
        ]
        self._detalhe(pedido, detalhe)

    def test_unmatched_items_are_counted_for_the_filter(self):
        self._pull()
        pedido = self._pedido('1')
        self._detalhe_sem_produto(pedido)
        self.assertEqual(pedido.itens_sem_produto, 1)
        # e o pedido é achável por isso
        achados = self.env['olist.order'].search(
            [('account_id', '=', self.account.id), ('itens_sem_produto', '>', 0)])
        self.assertIn(pedido, achados)

    def test_unmatched_items_are_written_in_the_chatter(self):
        """A notificação some da tela; o histórico do pedido fica.

        Quem lê o pedido semanas depois precisa saber POR QUE ele nunca entrou,
        e o lugar onde essa pergunta se faz é o próprio pedido.
        """
        self._pull()
        pedido = self._pedido('1')
        antes = len(pedido.message_ids)
        self._detalhe_sem_produto(pedido)
        self.assertGreater(len(pedido.message_ids), antes,
                           "nada foi anotado no histórico")
        corpo = pedido.message_ids[0].body
        self.assertIn('978-99-0000-000-0', corpo, "o ISBN que falta tem de estar lá")
        self.assertIn('Livro fantasma', corpo)
        self.assertNotIn('A toca iluminada', corpo,
                         "o que casou não é problema e não vai para o histórico")
        # E o HTML tem de CHEGAR como HTML: `_()` devolve texto puro e o
        # message_post o escapa, então a mensagem saía com "<p>" e "<li>" à
        # mostra no chatter (visto em 18/08/2026).
        self.assertNotIn('&lt;p&gt;', corpo,
                         "a mensagem está escapando: as tags aparecem cruas")
        self.assertIn('<li>', corpo, "a lista tem de ser lista de verdade")

    def test_the_chatter_message_escapes_what_comes_from_outside(self):
        """Marcar como HTML não pode virar porta de entrada: o código e a
        descrição chegam do Olist, e vão escapados."""
        self._pull()
        pedido = self._pedido('1')
        detalhe = dict(DETALHE_ML)
        detalhe['itens'] = [
            {'item': {'id_produto': '1', 'codigo': '<script>x</script>',
                      'descricao': 'Livro <b>falso</b>', 'quantidade': '1',
                      'valor_unitario': '10.00'}},
        ]
        self._detalhe(pedido, detalhe)

        corpo = pedido.message_ids[0].body
        self.assertNotIn('<script>', corpo, "injeção passou pelo Markup")
        self.assertIn('&lt;script&gt;', corpo, "o dado externo vai escapado")

    def test_nothing_is_logged_when_everything_matches(self):
        self._pull()
        pedido = self._pedido('1')
        antes = len(pedido.message_ids)
        self._detalhe(pedido)
        self.assertEqual(pedido.itens_sem_produto, 0)
        self.assertEqual(len(pedido.message_ids), antes,
                         "anotou histórico sem ter o que dizer")

    def test_the_count_clears_once_the_book_is_matched(self):
        # Casado o livro na tela de Produtos, relê-se o detalhe e o pedido
        # destrava — é esse o ciclo que o filtro serve.
        self._pull()
        pedido = self._pedido('1')
        self._detalhe_sem_produto(pedido)
        self.env['product.product'].create({
            'name': "Livro fantasma", 'barcode': "9789900000000",
            'type': 'consu'})
        self._detalhe_sem_produto(pedido)
        self.assertEqual(pedido.itens_sem_produto, 0)

    # -- 13. a tela tem de mostrar o que a ação fez --------------------------
    def test_a_successful_action_returns_nothing(self):
        """Sucesso não devolve ação — e é isso que tira o pisca da tela.

        Um botão que não devolve nada faz o cliente web recarregar o registro
        sozinho, em silêncio (view_button_hook.js: onClose -> reload). O
        `reload` explícito, que eu tinha posto para consertar o "Ler detalhe",
        recarrega a PÁGINA inteira: resolve o problema e cria outro.
        """
        self._pull()
        pedido = self._pedido('1')
        with patch.object(olist_client, 'get_pedido', return_value=DETALHE_ML):
            self.assertFalse(pedido.action_read_detail())
        self._arquiva_xml(pedido)
        self.assertFalse(pedido.action_fetch_xml())
        pedido._import_to_odoo()
        self.assertFalse(pedido.action_stamp_tracking())

    def test_a_problem_speaks_without_reloading_the_page(self):
        """O problema notifica — e NÃO recarrega a página.

        O registro o cliente web já recarrega sozinho depois de qualquer
        botão; o `next: reload` recarregava a página inteira e era o freeze.
        """
        self._pull()
        acao = self._pedido('1').action_stamp_tracking()
        self.assertEqual(acao['params']['type'], 'warning')
        self.assertNotIn('next', acao['params'],
                         "notificação arrastando reload de página: o freeze voltou")

    def test_importing_opens_the_sale_order(self):
        """Depois de importar, a tela vai para o S — não volta ao mesmo lugar."""
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self._arquiva_xml(pedido)
        acao = pedido.action_import_selected()
        self.assertEqual(acao['type'], 'ir.actions.act_window')
        self.assertEqual(acao['res_model'], 'sale.order')
        self.assertEqual(acao['res_id'], pedido.sale_order_id.id)

    def test_reimporting_an_imported_order_also_opens_its_sale_order(self):
        """Clicar de novo leva ao S — não a uma notificação vazia com freeze.

        Foi o caso do pedido 1012 (17/08/2026): já importado, o clique caía no
        "nada a fazer", que devolvia notificação vazia com reload de página —
        o freeze, e a pessoa no mesmo lugar.
        """
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido)
        self._arquiva_xml(pedido)
        pedido.action_import_selected()
        acao = pedido.action_import_selected()      # o segundo clique
        self.assertEqual(acao.get('res_model'), 'sale.order',
                         "o reclique tem de levar ao S")
        self.assertEqual(acao.get('res_id'), pedido.sale_order_id.id)

    # -- 14. a fila e o cron -------------------------------------------------
    def _muitos(self, quantos):
        """Espelha `quantos` pedidos sem detalhe, para exercitar o lote."""
        return self.env['olist.order'].create([{
            'account_id': self.account.id,
            'olist_id': 'F%s' % i, 'numero': 'F%s' % i,
            'situacao': 'Entregue', 'data_pedido': '2026-08-01',
        } for i in range(quantos)])

    def test_the_interactive_read_caps_and_queues_the_rest(self):
        """80 de uma vez derrubam a requisição; o que passa do lote vai à fila.

        Em 17/08/2026 uma leitura de 80 estourou o tempo do túnel e o rollback
        desfez as 80 -- nenhuma foi salva. O lote existe para isso não repetir.
        """
        pedidos = self._muitos(40)
        with patch.object(olist_client, 'get_pedido', return_value=DETALHE_ML):
            acao = pedidos.action_read_detail()

        lidos = pedidos.filtered('detalhe_lido_em')
        self.assertEqual(len(lidos), self.env['olist.order'].LOTE_INTERATIVO)
        self.assertEqual(len(pedidos.filtered('detalhe_pendente')),
                         40 - self.env['olist.order'].LOTE_INTERATIVO)
        self.assertEqual(acao['params']['type'], 'warning',
                         "o usuário precisa saber que sobrou fila")

    def test_a_small_selection_is_read_whole_without_queueing(self):
        pedidos = self._muitos(3)
        with patch.object(olist_client, 'get_pedido', return_value=DETALHE_ML):
            acao = pedidos.action_read_detail()
        self.assertEqual(len(pedidos.filtered('detalhe_lido_em')), 3)
        self.assertFalse(pedidos.filtered('detalhe_pendente'))
        self.assertFalse(acao, "lote que coube não precisa avisar nada")

    def test_the_cron_drains_the_queue_and_clears_the_flag(self):
        pedidos = self._muitos(5)
        pedidos.action_queue_detail()
        self.assertEqual(len(pedidos.filtered('detalhe_pendente')), 5)
        with patch.object(olist_client, 'get_pedido', return_value=DETALHE_ML):
            self.env['olist.order'].cron_read_details()
        self.assertFalse(pedidos.filtered('detalhe_pendente'),
                         "saiu da fila só quando lido")
        self.assertEqual(len(pedidos.filtered('detalhe_lido_em')), 5)

    def test_the_cron_does_nothing_when_there_is_nothing_to_do(self):
        """"Só o que é necessário": sem fila e sem pendência, nenhuma chamada.

        A cota é compartilhada com o ERP e os marketplaces; um cron que bate
        na API para descobrir que não tinha o que fazer é cota jogada fora
        todas as noites.
        """
        self._pull()
        with patch.object(olist_client, 'get_pedido', return_value=DETALHE_ML):
            self.env['olist.order'].search([]).write(
                {'detalhe_lido_em': '2026-01-01 00:00:00',
                 'detalhe_pendente': False})
            with patch.object(olist_client, 'get_pedido') as chamou:
                lidos = self.env['olist.order'].cron_read_details()
        chamou.assert_not_called()
        self.assertEqual(lidos, 0)

    def test_the_cron_stops_when_the_cycle_is_full(self):
        """O orçamento é do EXECUTOR, não meu.

        Eu tinha inventado 60 minutos e o cron estourava o tempo do Odoo,
        noite após noite ("Job 'Olist: ler detalhe' timed out", 18-19/08/2026),
        até alguém desativar os cinco crons. Agora o laço pergunta quanto
        resta e para quando o próximo pedido não cabe.
        """
        pedidos = self._muitos(10)
        pedidos.action_queue_detail()
        with patch.object(olist_client, 'get_pedido', return_value=DETALHE_ML), \
             patch.object(type(pedidos), '_grava_ja', return_value=1.0):
            lidos = self.env['olist.order'].cron_read_details()
        self.assertEqual(lidos, 0, "começou pedido que não cabia no ciclo")
        self.assertEqual(len(pedidos.filtered('detalhe_pendente')), 10,
                         "quem não foi lido continua na fila")

    def test_the_cron_reports_progress_to_the_runner(self):
        """Reportar progresso é o que faz o Odoo reagendar em vez de matar.

        Um cron que reporta é "parcialmente feito" e volta na hora para
        continuar; um que só demora é marcado como travado.
        """
        pedidos = self._muitos(3)
        pedidos.action_queue_detail()
        chamadas = []
        with patch.object(olist_client, 'get_pedido', return_value=DETALHE_ML), \
             patch.object(type(pedidos), '_grava_ja',
                          side_effect=lambda *a, **k: chamadas.append((a, k)) or 999.0):
            self.env['olist.order'].cron_read_details()
        self.assertTrue(chamadas, "não reportou progresso nenhum")
        # a primeira chamada declara o tamanho da fila
        self.assertEqual(chamadas[0][1].get('restantes'), 3)
        # e cada pedido lido reporta um a mais
        self.assertEqual(sum(1 for a, _k in chamadas if a and a[0] == 1), 3)

    def test_the_cron_skips_cancelled_orders(self):
        # Cancelado não vira pedido no Odoo: gastar cota lendo o detalhe dele
        # é trabalho que ninguém usa.
        self._pull()
        cancelado = self._pedido('2')
        with patch.object(olist_client, 'get_pedido',
                          return_value=DETALHE_ML) as chamou:
            self.env['olist.order'].cron_read_details()
        lidos = [c.args[1] for c in chamou.call_args_list]
        self.assertNotIn(cancelado.olist_id, lidos)

    def test_the_error_path_of_the_import_actually_runs(self):
        """O caminho COM erro também tem de executar até o fim.

        Em 17/08/2026 ele estourou `NameError: feitos is not defined` na mão do
        usuário: eu havia removido a variável e deixado a mensagem citando-a.
        Nenhum teste exercitava a importação com erro — todos passavam pelo
        caminho feliz, que é o que não quebra.
        """
        self._pull()
        pedido = self._pedido('1')
        self._detalhe(pedido, dict(DETALHE_ML, id_nota_fiscal='0'))  # sem nota
        acao = pedido.action_import_selected()
        self.assertEqual(acao['params']['type'], 'warning')
        self.assertIn('sem XML', acao['params']['message'])
        self.assertFalse(pedido.sale_order_id)

    def test_a_mixed_selection_reports_both_sides(self):
        # Um que entra e um que falha: a mensagem tem de contar os dois.
        self._pull()
        bom = self._pedido('1')
        self._detalhe(bom)
        self._arquiva_xml(bom)
        ruim = self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': 'X1', 'numero': 'X1',
            'situacao': 'Entregue', 'data_pedido': '2026-08-01',
            'detalhe_lido_em': '2026-08-01 00:00:00'})
        acao = (bom | ruim).action_import_selected()
        self.assertEqual(acao['params']['type'], 'warning')
        self.assertIn('1 importados', acao['params']['message'])
        self.assertTrue(bom.sale_order_id)


@tagged('post_install', '-at_install')
class TestRotuloDoLivro(TransactionCase):
    """O rótulo curto do Relatório: ISBN · título cortado (padrão da Amazon).

    O nome da ficha carrega autores e editora entre parênteses e atravessa a
    tela do pivô; e dois títulos de coleção cortados no mesmo ponto virariam o
    MESMO rótulo — o ISBN na frente mantém cada linha única.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Rótulo", 'company_id': cls.env.company.id,
            'token': "TOKEN-R", 'read_only': True})
        cls.pedido = cls.env['olist.order'].create({
            'account_id': cls.account.id, 'olist_id': 'R-1', 'numero': 'R-1'})

    def _linha(self, codigo, nome_produto):
        produto = self.env['product.product'].create({
            'name': nome_produto, 'list_price': 10.0})
        return self.env['olist.order.line'].create({
            'order_id': self.pedido.id, 'codigo': codigo,
            'quantidade': 1, 'valor_unitario': 10.0,
            'product_id': produto.id})

    def test_o_rotulo_corta_autores_e_poe_reticencias(self):
        linha = self._linha('9786551590016',
                            "A miséria brasileira: Do golpe militar à crise "
                            "social (José Chasin; Vânia Noeli)")
        self.assertEqual(
            linha.livro, '9786551590016 · A miséria brasileira: Do golpe mi…')

    def test_titulo_curto_fica_inteiro_e_sem_parenteses(self):
        linha = self._linha('978-65-5159-008-5', "Teia (Orides Fontela; Ieda)")
        self.assertEqual(linha.livro, '9786551590085 · Teia',
                         "o ISBN sai sem hífen e os autores caem fora")

    def test_colisao_de_titulo_nao_soma_linhas(self):
        """Caso de erro do pivô: dois livros de coleção com o mesmo começo
        de título têm rótulos DIFERENTES, graças ao ISBN."""
        a = self._linha('9780000000010', "Coleção Repente: volume um da série "
                                         "de cordel (Org. Alguém)")
        b = self._linha('9780000000027', "Coleção Repente: volume um da série "
                                         "de cordel especial (Org. Outrem)")
        self.assertNotEqual(a.livro, b.livro)
