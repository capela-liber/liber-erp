# -*- coding: utf-8 -*-
"""A ficha técnica chega ao PDF que a gráfica orça.

O que se mede aqui é a lista de linhas, não o PDF: o PDF é caro de medir e o
que decide o conteúdo é a lista. O caso do PDF de verdade -- o template que
casa com o do core -- fica no teste de renderização, no fim.
"""
import base64

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFichaParaAGrafica(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.livro = cls.env['product.template'].create({
            'name': 'O Cortiço',
            'barcode': '9788599296264',
            'metabooks_product_form': 'BC',
            'metabooks_height': 210.0,
            'metabooks_width': 140.0,
            'metabooks_thickness': 23.0,
            'metabooks_page_count': 300,
            'metabooks_binding': 'adhesive',
            'metabooks_has_flaps': True,
            'metabooks_has_lamination': True,
            'print_cover_finish': 'laminação fosca com reserva na lombada',
        })

    def _ficha(self, produto=None):
        return dict((produto or self.livro)._print_spec())

    # ------------------------------------------------------------------ #
    #  A ficha
    # ------------------------------------------------------------------ #

    def test_a_ficha_traz_o_que_a_grafica_pergunta(self):
        ficha = self._ficha()
        self.assertEqual(ficha['Dimensões (L x A x lombada)'], '140 x 210 x 23 mm',
                         'na gráfica "14 x 21" é comprido e "21 x 14" é '
                         'oblongo: a largura vem primeiro')
        self.assertEqual(ficha['Páginas'], '300')
        self.assertEqual(ficha['Encadernação'], 'Unsewn / adhesive bound')
        self.assertEqual(ficha['Formato'], 'Paperback')

    def test_o_acabamento_da_norma_sai_por_extenso(self):
        """Código não se manda para gráfica: "B415" não diz nada a ninguém."""
        ficha = self._ficha()
        self.assertIn('Laminated Cover', ficha['Acabamento'])
        self.assertIn('With Flaps', ficha['Acabamento'])
        self.assertNotIn('B415', ficha['Acabamento'])

    def test_o_que_a_onix_nao_nomeia_vai_em_texto(self):
        ficha = self._ficha()
        self.assertEqual(ficha['Acabamento da capa'],
                         'laminação fosca com reserva na lombada')

    def test_a_observacao_geral_fecha_a_ficha(self):
        """O que não cabe em campo nenhum, e vem por último."""
        self.livro.print_notes = 'encarte de 4 páginas, colado na p. 32'
        ficha = self.livro._print_spec()
        self.assertEqual(ficha[-1][1], 'encarte de 4 páginas, colado na p. 32')
        self.assertEqual(dict(ficha)['Observações'],
                         'encarte de 4 páginas, colado na p. 32')

    def test_medida_redonda_sai_sem_casa_decimal(self):
        """Borda: 210, não 210.0 -- a gráfica lê milímetro inteiro."""
        self.assertNotIn('.0', self._ficha()['Dimensões (L x A x lombada)'])

    def test_livro_sem_ficha_nao_gera_bloco_vazio(self):
        """Erro/borda: cadastro cru não pode imprimir rótulos sem valor."""
        cru = self.env['product.template'].create({
            'name': 'Sem ficha', 'barcode': '9788599296271'})
        self.assertFalse(cru._print_spec())

    def test_so_livro_ganha_ficha(self):
        """Parafuso e frete não têm lombada."""
        servico = self.env['product.template'].create(
            {'name': '(-) Frete', 'default_code': 'ADM0099'})
        self.assertFalse(servico._print_spec_is_relevant(servico))
        self.assertTrue(self.livro._print_spec_is_relevant(self.livro))

    # ------------------------------------------------------------------ #
    #  Português
    # ------------------------------------------------------------------ #

    def test_a_orelha_leva_a_medida(self):
        """Com orelhas, a gráfica precisa saber quanto ela mede.

        Sem a largura, a folha da capa não se calcula e a cotação volta como
        pergunta -- que é o que este módulo existe para evitar.
        """
        self.livro.print_flap_width = 90
        self.assertEqual(dict(self.livro._print_spec())['Largura da orelha'], '90 mm')

    def test_medida_de_orelha_sem_orelha_nao_sai(self):
        """Borda: número guardado por engano não vira linha no PDF."""
        self.livro.write({'metabooks_has_flaps': False, 'print_flap_width': 90})
        self.assertNotIn('Flap width', dict(self.livro._print_spec()))

    def test_as_cores_saem_na_notacao_da_gráfica(self):
        self.livro.write({'print_cover_colors': '4x0',
                          'print_body_colors': '1x1'})
        ficha = dict(self.livro._print_spec())
        self.assertEqual(ficha['Cor da capa'], '4x0')
        self.assertEqual(ficha['Cor do miolo'], '1x1')

    def test_o_caderno_fora_do_padrao_anda_junto_da_cor(self):
        """O que mais encarece e o que mais se esquece de dizer."""
        self.livro.write({'print_body_colors': '1x1',
                          'print_body_extra_colors': '1 caderno 4x4, p. 65-80'})
        self.assertEqual(dict(self.livro._print_spec())['Cor do miolo'],
                         '1x1 (1 caderno 4x4, p. 65-80)')

    def test_caderno_especial_sem_cor_base_ainda_sai(self):
        """Borda: quem só sabe do caderno especial não perde a informação."""
        self.livro.write({'print_body_colors': False,
                          'print_body_extra_colors': '1 caderno 4x4'})
        self.assertEqual(dict(self.livro._print_spec())['Cor do miolo'],
                         '1 caderno 4x4')

    def test_nenhum_campo_nosso_fica_em_ingles(self):
        """A varredura: rótulo em inglês na tela é defeito, não detalhe.

        Escrito depois de a tela mostrar "Cover Colors", "Body Colors" e
        "Special Signatures" para quem trabalha em português -- porque entrada
        acrescentada a um .po de módulo já instalado não é aplicada por
        caminho nenhum do carregador. Um teste por campo seria esquecido no
        campo seguinte; esta varredura não.
        """
        if not self.env['res.lang'].search([('code', '=', 'pt_BR')]):
            self.skipTest('pt_BR não está ativa nesta base')
        P = self.env['product.template']
        nossos = [f for f in P._fields if f.startswith('print_')]
        self.assertTrue(nossos, 'a varredura ficou sem nada para varrer')
        em_ingles = []
        for nome in nossos:
            en = P.with_context(lang='en_US')
            pt = P.with_context(lang='pt_BR')
            if (en._fields[nome].get_description(en.env)['string']
                    == pt._fields[nome].get_description(pt.env)['string']):
                em_ingles.append(nome)
        self.assertFalse(
            em_ingles, 'campo(s) sem tradução na tela: %s' % ', '.join(em_ingles))

    def test_a_encadernacao_mora_no_miolo(self):
        """Costura e cola são acabamento de miolo, e liam-se soltas à esquerda."""
        arch = self.env['product.template'].get_view(view_type='form')['arch']
        pos_miolo = arch.find('name="print_body_colors"')
        pos_binding = arch.find('name="metabooks_binding"')
        pos_capa = arch.find('name="print_cover_colors"')
        self.assertGreater(pos_binding, pos_capa,
                           'a encadernação ficou antes do bloco da capa')
        self.assertLess(pos_binding, pos_miolo,
                        'a encadernação tem de ABRIR o bloco do miolo, não '
                        'cair no fim dele')

    def test_a_lombada_mora_no_miolo(self):
        """A lombada sai do miolo: páginas vezes espessura do papel.

        Estava só dentro das dimensões, onde ninguém a procura na hora de
        especificar o miolo. E o xpath que a move precisa do predicado do
        rótulo, porque a view do Metabooks traz o campo duas vezes.
        """
        arch = self.env['product.template'].get_view(view_type='form')['arch']
        miolo = arch[arch.index('name="print_body"'):]
        self.assertIn('metabooks_thickness', miolo[:miolo.index('</group>')],
                      'a lombada não entrou no bloco do miolo')

    def test_papel_de_capa_e_de_miolo_saem_na_ficha(self):
        self.livro.write({'print_cover_paper': 'cartão triplex 250g',
                          'print_body_paper': 'pólen soft 80g'})
        ficha = dict(self.livro._print_spec())
        self.assertEqual(ficha['Papel da capa'], 'cartão triplex 250g')
        self.assertEqual(ficha['Papel do miolo'], 'pólen soft 80g')

    def test_capa_e_miolo_em_portugues_na_tela(self):
        """"Cover" e "Body" na tela era o defeito: o .po não grava termo de
        view neste módulo, e o hook é quem garante."""
        if not self.env['res.lang'].search([('code', '=', 'pt_BR')]):
            self.skipTest('pt_BR não está ativa nesta base')
        vista = self.env.ref(
            'liber_print_quote.view_product_template_print_finish')
        arch = vista.with_context(lang='pt_BR').arch_db or ''
        self.assertIn('Capa', arch)
        self.assertIn('Miolo', arch)
        self.assertNotIn('>Cover<', arch)
        self.assertNotIn('string="Body"', arch)

    def test_a_ficha_sai_em_portugues(self):
        """A gráfica é brasileira: rótulo E valor chegam em português.

        O VALOR é o que escapava: "Formato: Paperback" saía assim mesmo com a
        tela traduzida, porque a tabela ONIX crua não passa pelo .po. O rótulo
        vem escrito em português na fonte (ver `_print_spec`); o valor tem de
        vir da seleção do campo.
        """
        if not self.env['res.lang'].search([('code', '=', 'pt_BR')]):
            self.skipTest('pt_BR não está ativa nesta base')
        ficha = dict(self.livro.with_context(lang='pt_BR')._print_spec())
        self.assertEqual(ficha['Formato'], 'Brochura')
        self.assertEqual(ficha['Encadernação'], 'Colado (hotmelt)')
        self.assertIn('Capa laminada', ficha['Acabamento'])
        self.assertIn('Acabamento da capa', ficha)

    # ------------------------------------------------------------------ #
    #  O PDF
    # ------------------------------------------------------------------ #

    def test_o_pedido_de_cotacao_imprime_a_ficha(self):
        """O que o teste de lista não pega: o xpath casar com o core.

        Se o Odoo mudar o `td id="product"` do relatório, é aqui que se
        descobre -- e não na gráfica, com o PDF na mão.
        """
        fornecedor = self.env['res.partner'].create({'name': 'Gráfica Teste'})
        pedido = self.env['purchase.order'].create({
            'partner_id': fornecedor.id,
            'order_line': [(0, 0, {
                'product_id': self.livro.product_variant_id.id,
                'name': 'O Cortiço',
                'product_qty': 1000,
                'price_unit': 5.0,
            })],
        })
        html = self.env['ir.actions.report']._render_qweb_html(
            'purchase.report_purchasequotation', pedido.ids)[0].decode()
        self.assertIn('140 x 210 x 23 mm', html)
        self.assertIn('laminação fosca com reserva na lombada', html)


@tagged('post_install', '-at_install')
class TestPlanilhaParaOOrcamentista(TransactionCase):
    """A planilha anexa ao e-mail: o PDF é para ler, o CSV é para trabalhar."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.livro = cls.env['product.template'].create({
            'name': 'O Cortiço', 'barcode': '9788599296288',
            'metabooks_book_title': 'O Cortiço',
            'metabooks_product_form': 'BC', 'metabooks_height': 210.0,
            'metabooks_width': 140.0, 'metabooks_thickness': 23.0,
            'metabooks_page_count': 300, 'metabooks_binding': 'adhesive',
            'metabooks_has_flaps': True, 'print_flap_width': 90,
            'print_cover_colors': '4x0', 'print_cover_paper': 'cartão triplex 250g',
            'print_body_colors': '1x1', 'print_body_paper': 'pólen soft 80g',
            'print_notes': 'encarte de 4 páginas',
        })
        cls.grafica = cls.env['res.partner'].create({'name': 'Gráfica Teste'})

    def _pedido(self, quantidades=(1000,), produto=None):
        return self.env['purchase.order'].create({
            'partner_id': self.grafica.id,
            'order_line': [(0, 0, {
                'product_id': (produto or self.livro).product_variant_id.id,
                'name': 'O Cortiço', 'product_qty': q, 'price_unit': 5.0,
            }) for q in quantidades],
        })

    def _texto(self, pedido):
        return pedido._print_spec_csv().decode('utf-8-sig')

    def test_a_planilha_traz_a_ficha_e_a_tiragem(self):
        texto = self._texto(self._pedido())
        cabecalho, linha = texto.strip().split('\r\n')
        self.assertEqual(cabecalho.split(';')[:3], ['ISBN', 'Título', 'Tiragem'])
        campos = linha.split(';')
        self.assertEqual(campos[0], '9788599296288')
        self.assertEqual(campos[2], '1000', 'a tiragem vem da linha do pedido')
        self.assertIn('cartão triplex 250g', linha)
        self.assertIn('pólen soft 80g', linha)

    def test_o_mesmo_titulo_em_duas_tiragens_da_duas_linhas(self):
        """São dois orçamentos, não um: o preço por exemplar muda com a tiragem."""
        texto = self._texto(self._pedido((1000, 3000)))
        linhas = texto.strip().split('\r\n')[1:]
        self.assertEqual(len(linhas), 2)
        self.assertEqual([l.split(';')[2] for l in linhas], ['1000', '3000'])

    def test_o_excel_brasileiro_abre_sem_embaralhar(self):
        """Ponto e vírgula e BOM: sem isso "Dimensões" chega "DimensÃµes"."""
        bruto = self._pedido()._print_spec_csv()
        self.assertTrue(bruto.startswith(b'\xef\xbb\xbf'), 'faltou o BOM')
        self.assertIn(b';', bruto)
        self.assertIn('Encadernação'.encode('utf-8'), bruto)

    def test_a_planilha_sai_na_lingua_do_fornecedor(self):
        """Quem lê é o orçamentista. "Paperback" não diz nada a ele."""
        if not self.env['res.lang'].search([('code', '=', 'pt_BR')]):
            self.skipTest('pt_BR não está ativa nesta base')
        self.grafica.lang = 'pt_BR'
        texto = self._texto(self._pedido().with_context(lang='en_US'))
        self.assertIn('Brochura', texto)
        self.assertNotIn('Paperback', texto)
        self.assertIn('Com orelhas', texto)

    def test_pedido_sem_livro_nao_gera_planilha(self):
        """Borda: comprar papel ou frete não rende ficha técnica nenhuma."""
        servico = self.env['product.template'].create(
            {'name': '(-) Frete', 'default_code': 'ADM0099'})
        self.assertFalse(self._pedido(produto=servico)._print_spec_csv())
        self.assertFalse(self._pedido(produto=servico)._print_spec_attachment())

    def test_o_anexo_se_refaz_e_nao_se_acumula(self):
        """Entre um envio e outro o cadastro muda; anexo velho é pior que nenhum."""
        pedido = self._pedido()
        primeiro = pedido._print_spec_attachment()
        self.livro.print_cover_paper = 'supremo 300g'
        segundo = pedido._print_spec_attachment()
        self.assertNotEqual(primeiro.id, segundo.id)
        self.assertFalse(primeiro.exists(), 'o anexo velho ficou para trás')
        self.assertIn('supremo 300g',
                      base64.b64decode(segundo.datas).decode('utf-8-sig'))

    def test_o_email_leva_os_DOIS_pdf_e_planilha(self):
        """O que o teste do compositor não prova: o que sai no e-mail.

        O compositor mostra só o CSV; o PDF o template anexa na HORA do envio.
        São dois momentos, e só o segundo é o que a gráfica recebe -- este
        teste vai até lá.
        """
        pedido = self._pedido()
        acao = pedido.with_context(send_rfq=True).action_rfq_send()
        compositor = self.env['mail.compose.message'].with_context(
            **acao['context']).create({})
        compositor._action_send_mail()
        mensagem = self.env['mail.message'].search(
            [('model', '=', 'purchase.order'), ('res_id', '=', pedido.id)],
            order='id desc', limit=1)
        nomes = mensagem.attachment_ids.mapped('name')
        self.assertTrue(any(n.endswith('.csv') for n in nomes),
                        'a planilha não foi no e-mail: %s' % nomes)
        self.assertTrue([n for n in nomes if not n.endswith('.csv')],
                        'o pedido não foi no e-mail: %s' % nomes)
        self.assertEqual(len(nomes), 2, 'sobrou ou faltou anexo: %s' % nomes)

    def test_a_conversa_do_chatter_nao_leva_planilha(self):
        """"Enviar mensagem" é conversa, não cotação.

        Sem esta guarda, abrir o chatter de um pedido trazia a ficha técnica
        anexada, sem texto e sem PDF -- e quem abriu só queria escrever duas
        linhas para o fornecedor.
        """
        pedido = self._pedido()
        compositor = self.env['mail.compose.message'].with_context(
            default_model='purchase.order', default_res_ids=pedido.ids,
            default_composition_mode='comment').create({})
        self.assertFalse(
            compositor.attachment_ids,
            'o chatter abriu com anexo: %s'
            % compositor.attachment_ids.mapped('name'))

    def test_o_compositor_de_email_abre_com_os_dois(self):
        """O caminho da tela: o compositor abre com PDF e planilha."""
        pedido = self._pedido()
        acao = pedido.with_context(send_rfq=True).action_rfq_send()
        compositor = self.env['mail.compose.message'].with_context(
            **acao['context']).create({})
        nomes = compositor.attachment_ids.mapped('name')
        self.assertTrue(any(n.endswith('.csv') for n in nomes), nomes)
        # O relatório sai .pdf onde há wkhtmltopdf e .html onde não há; o que
        # se mede é que ele CONTINUA indo junto, não a extensão.
        self.assertTrue([n for n in nomes if not n.endswith('.csv')],
                        'o pedido não foi junto da planilha: %s' % nomes)


@tagged('post_install', '-at_install')
class TestOrelhaDesconfiada(TransactionCase):
    """Orelha menor que metade da largura é quase sempre dedo errado."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.livro = cls.env['product.template'].create({
            'name': 'Com orelha', 'barcode': '9788599296295',
            'metabooks_width': 140.0, 'metabooks_has_flaps': True,
        })

    def _aviso(self, largura_orelha):
        self.livro.print_flap_width = largura_orelha
        return self.livro._onchange_print_flap_width()

    def test_orelha_pequena_demais_avisa(self):
        """24 mm numa capa de 140: centímetro digitado onde se pede milímetro."""
        aviso = self._aviso(24)
        self.assertTrue(aviso, 'passou sem avisar')
        self.assertIn('24', aviso['warning']['message'])
        self.assertIn('140', aviso['warning']['message'])

    def test_orelha_plausivel_nao_incomoda(self):
        """70 mm em 140 é metade exata: o limite não pode acusar o normal."""
        self.assertFalse(self._aviso(70))
        self.assertFalse(self._aviso(120))

    def test_sem_largura_nao_ha_o_que_comparar(self):
        """Borda: livro sem largura no cadastro não vira aviso falso."""
        self.livro.metabooks_width = 0
        self.assertFalse(self._aviso(24))

    def test_o_aviso_nao_impede_gravar(self):
        """Avisar é diferente de barrar: a gráfica manda, não a nossa regra."""
        self._aviso(24)
        self.livro.flush_recordset()
        self.assertEqual(self.livro.print_flap_width, 24)
