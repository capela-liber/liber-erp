# -*- coding: utf-8 -*-
"""Cada tela abre a SUA lista.

O modelo `olist.product` tem duas listas, e elas respondem perguntas
diferentes: a do menu Estoque compara os dois saldos (Olist × Odoo), a do
menu Produtos casa livro por ISBN. Uma ação sem view amarrada deixa o Odoo
escolher entre as duas — e foi o que aconteceu em 18/08/2026: o menu Estoque
abria a lista do catálogo, sem as colunas de quantidade, e o dono procurou
os números numa tela que nunca os teve.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTelasDoOlist(TransactionCase):
    def _lista_da_acao(self, xmlid):
        acao = self.env.ref('liber_olist.%s' % xmlid)
        vinculos = self.env['ir.actions.act_window.view'].search([
            ('act_window_id', '=', acao.id), ('view_mode', '=', 'list')])
        self.assertTrue(
            vinculos, "a ação %s não amarra lista nenhuma: o Odoo escolhe "
                      "entre as duas do modelo" % xmlid)
        return vinculos[0].view_id

    def test_estoque_abre_a_lista_da_comparacao(self):
        lista = self._lista_da_acao('action_olist_product')

        self.assertEqual(
            lista, self.env.ref('liber_olist.view_olist_product_list'))
        for campo in ('saldo_olist', 'odoo_qty', 'qty_to_send', 'divergencia'):
            self.assertIn(campo, lista.arch,
                          "a tela de estoque tem de mostrar %s" % campo)

    def test_produtos_abre_a_lista_do_catalogo(self):
        lista = self._lista_da_acao('action_olist_catalog')

        self.assertEqual(
            lista, self.env.ref('liber_olist.view_olist_catalog_list'))

    def test_as_duas_telas_nao_mostram_a_mesma_lista(self):
        self.assertNotEqual(
            self._lista_da_acao('action_olist_product'),
            self._lista_da_acao('action_olist_catalog'),
            "Estoque e Produtos respondem perguntas diferentes")

    def test_despachar_busca_o_xml_sem_esperar_o_cron(self):
        """O cron das notas é lento e a fila não pode depender dele.

        Quem está na fila vê "Sem XML" e, sem este botão, não tem o que fazer
        senão esperar a próxima varredura. `action_fetch_xml` pergunta pela
        nota DESTE pedido — ele já sabe o id dela — em vez de percorrer a
        conta inteira.
        """
        lista = self.env.ref('liber_olist.view_olist_order_list_fila')

        self.assertIn('action_fetch_xml', lista.arch,
                      "a fila não oferece o Buscar o XML")
        self.assertIn('action_import_selected', lista.arch,
                      "o Despachar sumiu da fila")
        self.assertLess(
            lista.arch.index('action_import_selected'),
            lista.arch.index('action_fetch_xml'),
            "o Despachar é a ação principal e vem primeiro: mudar a ordem "
            "move o botão que a equipe já clica de olhos fechados")

    def test_o_ler_detalhe_avisa_que_regrava(self):
        """O texto tem de dizer o que o botão FAZ.

        Até 16/09/2026 a ajuda dizia "só leitura" e o método apagava e
        recriava os itens. Quando o direito faltava, a tela respondia "você
        não tem permissão para excluir" a quem tinha acabado de ler que
        aquilo era só leitura — e ninguém conseguia ligar uma coisa à outra.
        """
        # Pelo BOTÃO, não pela arch inteira: "só leitura" é verdade no
        # `action_pull_from_olist` ao lado (ele só traz a listagem), e varrer
        # o texto todo reprovava a frase honesta do vizinho.
        from lxml import etree
        achou = 0
        for xmlid in ('view_olist_order_list_fila', 'view_olist_order_list'):
            arch = etree.fromstring(self.env.ref('liber_olist.%s' % xmlid).arch)
            for botao in arch.xpath("//button[@name='action_read_detail']"):
                achou += 1
                ajuda = botao.get('help') or ''
                self.assertNotIn(
                    "só leitura", ajuda,
                    "%s promete 'só leitura' num botão que regrava" % xmlid)
                self.assertIn(
                    "REGRAVA", ajuda,
                    "%s não avisa que o Ler detalhe regrava os itens" % xmlid)
        self.assertEqual(achou, 2,
                         "o Ler detalhe tem de estar na fila E na auditoria")

    def test_o_botao_da_fila_aponta_para_metodo_que_existe(self):
        """Botão de view não é verificado no carregamento.

        Um `name` errado no XML passa no `-u` e só falha no clique, na frente
        de quem despacha. O teste faz aqui a checagem que o Odoo não faz.
        """
        self.assertTrue(
            hasattr(self.env['olist.order'], 'action_fetch_xml'),
            "o botão da fila chama um método que não existe")

    def test_o_relatorio_mede_quantidade_e_valor_por_livro(self):
        """O Relatório nasce da LINHA (quem sabe livro e quantidade), abre no
        gráfico, exclui cancelados e mora antes das Configurações."""
        acao = self.env.ref('liber_olist.action_olist_dashboard')
        self.assertEqual(acao.res_model, 'olist.order.line',
                         "só a linha sabe produto e quantidade")
        self.assertTrue(acao.view_mode.startswith('graph'))
        self.assertIn("Cancelado", acao.domain,
                      "cancelado contaria como venda no relatório")
        self.assertIn('f_30_dias', acao.context,
                      "sem a janela de 30 dias o gráfico vira a história toda")
        pivo = self.env.ref('liber_olist.view_olist_order_line_pivot')
        for medida in ('quantidade', 'valor_total'):
            self.assertIn(medida, pivo.arch,
                          "o pivô perdeu a medida %s" % medida)
        busca = self.env.ref('liber_olist.view_olist_order_line_search')
        self.assertIn("'livro'", busca.arch,
                      "o agrupamento usa o rótulo CURTO (ISBN · título…), "
                      "não o nome completo da ficha")
        menu = self.env.ref('liber_olist.menu_olist_dashboard')
        config = self.env.ref('liber_olist.menu_olist_config')
        self.assertLess(menu.sequence, config.sequence,
                        "o Relatório mora antes das Configurações")

    def test_a_poda_dos_botoes_nao_volta(self):
        """Poda de 19/08/2026: Gerar fatura, Ler em segundo plano e Carimbar
        rastreio saíram da fileira — o presente fatura no Importar, a fila de
        detalhe anda sozinha (cron 2/2h) e o rastreio carimba no write. Se um
        voltar, volta por decisão, não por copy-paste."""
        lista = self.env.ref('liber_olist.view_olist_order_list')
        for morto in ('action_create_invoice', 'action_queue_detail',
                      'action_stamp_tracking'):
            self.assertNotIn(morto, lista.arch,
                             "o botão podado voltou à fileira: %s" % morto)
        for vivo in ('action_read_detail', 'action_import_selected',
                     ):
            self.assertIn(vivo, lista.arch,
                          "a poda levou botão demais: %s" % vivo)

    def test_a_fila_e_uma_tela_enxuta(self):
        """Desenho do dono (19/08/2026), depois de a equipe se perder entre
        dois filtros gêmeos: a FILA (o que importar) é uma tela; a lista
        completa é outra — a auditoria, que abre sem filtro padrão.

        Nasceu com UM botão. Em 16/09/2026 o dono somou dois, e os dois são a
        mesma pergunta por metades: `Buscar o XML` para "Nota emitida, XML não
        arquivado" (o cron varre de 2 em 2h e não dá conta) e `Ler detalhe`
        para o pedido que chegou sem canal, sem itens ou sem cliente. Trocar de
        tela para resolver cada metade era o que fazia perder o lugar na fila.

        Continua fora `action_pull_from_olist` (traz a listagem INTEIRA, é o
        trabalho da auditoria, não o de despachar) e `action_create_invoice`.
        """
        acao = self.env.ref('liber_olist.action_olist_fila')
        self.assertIn("'nao_importado'", acao.domain,
                      "a fila mostra só o que está pronto para importar")
        self.assertIn('despachavel', acao.domain,
                      "quem exige (ou dispensa) a nota é a política das "
                      "Definições — o domínio pergunta ao campo, não "
                      "hardcodeia a DANFE")
        fila = self.env.ref('liber_olist.view_olist_order_list_fila')
        self.assertIn('action_import_selected', fila.arch)
        self.assertIn('action_fetch_xml', fila.arch,
                      "sem o Buscar o XML a fila só sabe esperar o cron")
        self.assertIn('action_read_detail', fila.arch,
                      "sem o Ler detalhe o pedido incompleto trava a fila")
        for fora in ('action_pull_from_olist', 'action_create_invoice'):
            self.assertNotIn(fora, fila.arch,
                             "a fila é enxuta; %s não é o trabalho dela" % fora)
        self.assertLess(
            self.env.ref('liber_olist.menu_olist_fila').sequence,
            self.env.ref('liber_olist.menu_olist_order').sequence,
            "a fila vem antes da auditoria: o app abre no trabalho")
        auditoria = self.env.ref('liber_olist.action_olist_order')
        self.assertNotIn('search_default', auditoria.context or '{}',
                         "a auditoria abre completa, sem filtro escondendo")
        busca = self.env.ref('liber_olist.view_olist_order_search')
        self.assertNotIn('f_a_despachar', busca.arch,
                         "o filtro gêmeo morreu com a criação da fila")
