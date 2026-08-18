# -*- coding: utf-8 -*-
"""A fatura nasce do XML, não do pedido (NOTES.md §16).

Quando a nota chega aqui a SEFAZ já a autorizou: a fatura não emite nada,
registra no razão um fato fiscal consumado. E ela é montada a partir do XML —
montá-la a partir do pedido do Odoo arriscaria um documento contábil dizendo o
que o documento fiscal não diz (o Olist pode ter emitido com outro valor, frete
ou desconto), e ninguém perceberia.
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client

LISTAGEM = [{'id': '900', 'numero': '900', 'data_pedido': '10/08/2026',
             'nome': 'Comprador', 'situacao': 'Entregue', 'valor': 100.0}]
DETALHE = {
    'id': '900', 'numero': '900', 'situacao': 'Entregue',
    'id_nota_fiscal': '555',
    'ecommerce': {'nomeEcommerce': 'Hedra', 'numeroPedidoEcommerce': '77'},
    'cliente': {'nome': 'Comprador', 'cpf_cnpj': '171.037.078-55'},
    'itens': [{'item': {'codigo': '9781111111119', 'descricao': 'Livro',
                        'quantidade': '2', 'valor_unitario': '50.00'}}],
}


@tagged('post_install', '-at_install')
class TestOlistInvoice(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Fatura", 'company_id': cls.env.company.id,
            'token': "TOKEN-F", 'read_only': True,
            # A conta OPERA: o corte governa a entrada do pedido na
            # operação (estoque e fatura), e o cenário normal destes
            # testes é o do pedido que produz efeito.
            'order_stock_cutoff': '2020-01-01'})
        cls.livro = cls.env['product.product'].create({
            'name': "Livro", 'barcode': "9781111111119", 'list_price': 50.0,
            'type': 'consu'})
        cls.cliente = cls.env['res.partner'].create({'name': "Comprador"})

    def _pedido_com_nota(self, com_itens=True):
        with patch.object(olist_client, 'list_pedidos',
                          return_value=iter(LISTAGEM)):
            self.account._pull_orders(interactive=False)
        pedido = self.env['olist.order'].search(
            [('account_id', '=', self.account.id), ('numero', '=', '900')])
        with patch.object(olist_client, 'get_pedido', return_value=DETALHE):
            pedido._read_detail()
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "n.xml",
            'olist_nota_id': '555', 'olist_account_id': self.account.id,
            'partner_id': self.cliente.id,
            'danfe_no': '12345',
            'file_create_date': '2026-08-10',
        })
        if com_itens:
            self.env['nfe.xml.items'].create({
                'soc_xml_id': painel.id, 'ks_product_id': self.livro.id,
                'ks_product_name': "Livro", 'ks_product_qty': 2,
                'ks_price': 50.0, 'ks_product_barcode': '9781111111119'})
        pedido.invalidate_recordset()
        pedido.modified(['id_nota_fiscal'])
        return pedido, painel

    def test_the_invoice_is_built_from_the_xml_items(self):
        pedido, painel = self._pedido_com_nota()
        pedido._create_invoice()
        fatura = pedido.invoice_id
        self.assertTrue(fatura)
        self.assertEqual(fatura.move_type, 'out_invoice')
        self.assertEqual(len(fatura.invoice_line_ids), 1)
        linha = fatura.invoice_line_ids
        self.assertEqual(linha.product_id, self.livro)
        self.assertEqual(linha.quantity, 2)
        self.assertEqual(linha.price_unit, 50.0)

    def test_the_invoice_carries_the_key_and_the_panel(self):
        """O caminho de volta da fatura ao XML é a chave de acesso."""
        pedido, painel = self._pedido_com_nota()
        painel.key = '35260812345678000190550010000000011000000017'
        pedido._create_invoice()
        self.assertEqual(pedido.invoice_id.nfe_key, painel.key)
        self.assertEqual(painel.invoice_id, pedido.invoice_id,
                         "o painel é o eDoc: a nota tem de apontar a fatura")

    def test_the_invoice_carries_the_sales_channel(self):
        """O canal vem do MAPEAMENTO (olist.channel), não de um canal inventado.

        Mudou em 18/08/2026: antes o botão da conta criava um `crm.team` com o
        nome que o Olist mandasse. Agora o par se escolhe no espelho, e é ele
        que a fatura carimba.
        """
        pedido, _painel = self._pedido_com_nota()
        equipe = self.env['crm.team'].create({
            'name': "Loja Hedra", 'company_id': self.account.company_id.id})
        espelho = self.env['olist.channel'].search(
            [('account_id', '=', self.account.id), ('name', '=', "Hedra")])
        self.assertTrue(espelho, "o canal devia ter sido descoberto na leitura")
        espelho.team_id = equipe
        pedido.invalidate_recordset()
        self.assertEqual(pedido.team_id, equipe,
                         "mapear o canal tem de alcançar o pedido já lido")
        pedido._create_invoice()
        self.assertEqual(pedido.invoice_id.team_id, equipe)

    def test_it_refuses_without_an_archived_xml(self):
        # A fatura sai da nota; sem ela não há de onde tirá-la.
        with patch.object(olist_client, 'list_pedidos',
                          return_value=iter(LISTAGEM)):
            self.account._pull_orders(interactive=False)
        pedido = self.env['olist.order'].search(
            [('account_id', '=', self.account.id), ('numero', '=', '900')])
        with patch.object(olist_client, 'get_pedido', return_value=DETALHE):
            pedido._read_detail()
        with self.assertRaises(UserError):
            pedido._create_invoice()

    def test_it_refuses_when_an_xml_item_has_no_product(self):
        pedido, painel = self._pedido_com_nota(com_itens=False)
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_name': "Desconhecido",
            'ks_product_qty': 1, 'ks_price': 10.0,
            'ks_product_barcode': '9789999999992'})
        with self.assertRaises(UserError):
            pedido._create_invoice()
        self.assertFalse(pedido.invoice_id)

    def test_it_never_invoices_twice(self):
        pedido, _painel = self._pedido_com_nota()
        pedido._create_invoice()
        primeira = pedido.invoice_id
        self.assertFalse(pedido._create_invoice())
        self.assertEqual(pedido.invoice_id, primeira)

    def test_auto_post_can_be_turned_off(self):
        self.account.invoice_auto_post = False
        pedido, _painel = self._pedido_com_nota()
        pedido._create_invoice()
        self.assertEqual(pedido.invoice_id.state, 'draft')

    def test_importing_creates_the_invoice_right_away(self):
        """"Ao criar o pedido S já criar a Invoice e o Edoc."

        Deixou de haver data de corte: como a importação passou a EXIGIR XML
        arquivado, a nota está sempre aqui quando o pedido entra — e adiar o
        lançamento seria guardar trabalho para depois sem motivo.
        """
        pedido, painel = self._pedido_com_nota()
        pedido._import_to_odoo()
        self.assertTrue(pedido.sale_order_id, "o S tem de nascer")
        self.assertTrue(pedido.invoice_id, "a fatura tem de nascer junto")
        self.assertEqual(painel.invoice_id, pedido.invoice_id,
                         "o eDoc tem de apontar a fatura")

    def _posicao_de_venda(self):
        posicao = self.env['account.fiscal.position'].create({
            'name': "(A) Venda de mercadoria adquirida de terceiros",
            'company_id': self.env.company.id})
        self.env.company.sale_fiscal_position_id = posicao
        return posicao

    def test_o_pedido_e_a_fatura_nascem_com_a_posicao_da_venda(self):
        """O S do marketplace é venda comum, e a posição vem das Definições.

        Antes disso, pedido e fatura do Olist nasciam SEM posição fiscal
        nenhuma (8 de 8 no staging, 18/08/2026): o comprador de marketplace é
        pessoa física avulsa, cadastro que ninguém parametriza, então derivar
        da ficha não resolvia nada."""
        posicao = self._posicao_de_venda()
        pedido, painel = self._pedido_com_nota()

        pedido._import_to_odoo()

        self.assertEqual(pedido.sale_order_id.fiscal_position_id, posicao,
                         "o S tem de nascer carimbado")
        self.assertEqual(pedido.invoice_id.fiscal_position_id, posicao,
                         "e a fatura também — é ela que vai à contabilidade")

    def test_sem_padrao_configurado_a_importacao_nao_para(self):
        """Configuração em branco não pode derrubar fluxo diário."""
        self.env.company.sale_fiscal_position_id = False
        pedido, painel = self._pedido_com_nota()

        pedido._import_to_odoo()

        self.assertTrue(pedido.sale_order_id, "o S entra do mesmo jeito")
        self.assertTrue(pedido.invoice_id)

    def test_importing_refuses_without_the_note(self):
        # Sem nota não há fatura possível, e o pedido não entra pela metade.
        with patch.object(olist_client, 'list_pedidos',
                          return_value=iter(LISTAGEM)):
            self.account._pull_orders(interactive=False)
        pedido = self.env['olist.order'].search(
            [('account_id', '=', self.account.id), ('numero', '=', '900')])
        with patch.object(olist_client, 'get_pedido', return_value=DETALHE), \
             patch.object(olist_client, 'get_nota_xml', return_value=None):
            pedido._read_detail()
            with self.assertRaises(UserError):
                pedido._import_to_odoo()
        self.assertFalse(pedido.sale_order_id)
        self.assertFalse(pedido.invoice_id)

    def test_an_unparsed_panel_is_read_before_giving_up(self):
        """XML arquivado e não lido: lê agora, não manda esperar o cron.

        A ingestão só arquiva o arquivo; quem extrai itens, valor e CFOP é o
        `action_import_xml_file` do liber_nfe_xml, que normalmente roda pelo
        cron. Sem isto, arquivar o XML e tentar faturar em seguida dava "o XML
        não tem itens lidos" com a nota ali do lado — foi o pedido 1006 em
        17/08/2026.
        """
        pedido, painel = self._pedido_com_nota(com_itens=False)
        self.assertFalse(painel.panel_items)
        chamou = []

        def parse_de_mentira():
            chamou.append(True)
            self.env['nfe.xml.items'].create({
                'soc_xml_id': painel.id, 'ks_product_id': self.livro.id,
                'ks_product_name': "Livro", 'ks_product_qty': 2,
                'ks_price': 50.0})

        with patch.object(type(painel), 'action_import_xml_file',
                          side_effect=parse_de_mentira):
            pedido._create_invoice()

        self.assertTrue(chamou, "nem tentou ler o XML antes de recusar")
        self.assertTrue(pedido.invoice_id)

    def test_a_panel_that_cannot_be_read_says_so_clearly(self):
        # Se a leitura falhar mesmo, a mensagem manda olhar a NFe — em vez de
        # dizer só "não tem itens", que soa como culpa de quem clicou.
        pedido, painel = self._pedido_com_nota(com_itens=False)
        with patch.object(type(painel), 'action_import_xml_file'):
            with self.assertRaises(UserError) as erro:
                pedido._create_invoice()
        self.assertIn("abra a NFe", str(erro.exception))

    def test_a_failed_invoice_rolls_the_sale_order_back(self):
        """Ou entra inteiro — S, fatura e eDoc — ou não entra.

        Sem savepoint por pedido, a fatura que falhava deixava para trás o S
        nascido logo antes: foi o S63109 órfão de 17/08/2026, com a tela
        dizendo "0 importados, 1 com problema".
        """
        pedido, painel = self._pedido_com_nota(com_itens=False)
        with patch.object(type(painel), 'action_import_xml_file'):
            acao = pedido.action_import_selected()
        self.assertEqual(acao['params']['type'], 'warning')
        pedido.invalidate_recordset()
        self.assertFalse(pedido.sale_order_id,
                         "o S ficou órfão: a fatura falhou e ele sobreviveu")

    def test_clicking_again_completes_a_half_imported_order(self):
        """Pedido com S e sem fatura: o clique COMPLETA, não diz 'nada a fazer'.

        É o resgate dos que entraram pela metade antes do savepoint existir.
        """
        pedido, painel = self._pedido_com_nota()
        pedido._import_to_odoo()
        fatura = pedido.invoice_id
        self.assertTrue(fatura)
        # simula o estado órfão: S sem fatura
        pedido.invoice_id = False
        painel.invoice_id = False
        self.assertTrue(pedido._import_to_odoo(), "devia ter completado")
        self.assertTrue(pedido.invoice_id)
        self.assertEqual(painel.invoice_id, pedido.invoice_id)

    def test_antes_do_corte_entra_sem_fatura(self):
        """O corte governa a ENTRADA na operação, não só o estoque.

        Faturar é o efeito mais pesado da importação: lança no razão e, com
        diário de recebimento, registra o dinheiro. O histórico da conta tem
        ~1000 pedidos, e importá-los para consolidar não pode reescrever a
        contabilidade de um ano atrás (decisão do dono, 18/08/2026)."""
        self.account.order_stock_cutoff = '2026-12-31'   # depois do pedido
        pedido, painel = self._pedido_com_nota()

        pedido._import_to_odoo()

        self.assertTrue(pedido.sale_order_id,
                        "o pedido entra: espelho e rastreabilidade valem")
        self.assertFalse(pedido.invoice_id,
                         "mas anterior ao corte não fatura")
        self.assertFalse(pedido.sale_order_id.picking_ids,
                         "nem baixa estoque — os dois efeitos andam juntos")

    def test_sem_corte_nenhum_pedido_fatura(self):
        """Vazio é o padrão, e o padrão é não produzir efeito nenhum."""
        self.account.order_stock_cutoff = False
        pedido, painel = self._pedido_com_nota()

        pedido._import_to_odoo()

        self.assertTrue(pedido.sale_order_id)
        self.assertFalse(pedido.invoice_id)

    def test_a_partir_do_corte_fatura_e_baixa(self):
        """E depois do corte, os dois efeitos acontecem."""
        pedido, painel = self._com_pedido_e_corte()

        self.assertTrue(pedido.invoice_id, "a partir do corte, fatura")
        self.assertTrue(pedido.sale_order_id.picking_ids,
                        "e baixa estoque")

    def _com_pedido_e_corte(self):
        """Pedido importado com baixa de estoque, para haver picking."""
        self.account.order_stock_cutoff = '2026-01-01'
        pedido, painel = self._pedido_com_nota()
        pedido._import_to_odoo()
        return pedido, painel

    # -- comercial: a INV aparece a partir do S ------------------------------
    def test_the_invoice_is_reachable_from_the_sale_order(self):
        """Sem `sale_line_ids` a fatura fica solta.

        O comercial abre o S e vê "Faturado: 0" com a nota emitida e paga do
        outro lado. O vínculo linha-a-linha é o que faz o smart button de
        Faturas aparecer no pedido.
        """
        pedido, _painel = self._pedido_com_nota()
        pedido._import_to_odoo()
        venda = pedido.sale_order_id
        self.assertIn(pedido.invoice_id, venda.invoice_ids,
                      "a fatura não aparece no pedido de venda")
        self.assertTrue(pedido.invoice_id.invoice_line_ids.sale_line_ids)

    # -- logística: a nota aparece na movimentação ---------------------------
    def test_the_note_is_stamped_on_the_delivery(self):
        """`nfe_move_id` é o campo que a logística já lê (liber_nfe_picking).

        Sem carimbar, a movimentação é concluída e não há por onde chegar à
        nota que já existe.
        """
        Picking = self.env['stock.picking']
        if 'nfe_move_id' not in Picking._fields:
            self.skipTest("liber_nfe_picking não está instalado")
        pedido, _painel = self._com_pedido_e_corte()
        entregas = pedido.sale_order_id.picking_ids
        self.assertTrue(entregas, "o corte devia ter gerado entrega")
        self.assertTrue(all(p.nfe_move_id == pedido.invoice_id
                            for p in entregas))

    # -- financeiro: o valor já entrou --------------------------------------
    def test_nothing_is_paid_without_a_journal(self):
        """Sem diário configurado, não se inventa por onde o dinheiro entrou."""
        self.assertFalse(self.account.payment_journal_id)
        pedido, _painel = self._pedido_com_nota()
        pedido._import_to_odoo()
        self.assertEqual(pedido.invoice_id.payment_state, 'not_paid')

    def test_the_invoice_is_born_paid_when_a_journal_is_set(self):
        """O comprador já pagou ao Olist: deixar em aberto faria o financeiro
        cobrar quem já pagou."""
        diario = self.env['account.journal'].search(
            [('type', 'in', ('bank', 'cash')),
             ('company_id', '=', self.env.company.id)], limit=1)
        if not diario:
            self.skipTest("a empresa não tem diário de banco/caixa")
        self.account.payment_journal_id = diario
        pedido, _painel = self._pedido_com_nota()
        pedido._import_to_odoo()
        self.assertIn(pedido.invoice_id.payment_state, ('paid', 'in_payment'),
                      "a fatura ficou em aberto com o dinheiro já recebido")

    def test_a_picking_created_later_still_gets_the_note(self):
        """O carimbo tem de acontecer quando o picking NASCE.

        O caso normal não é o pedido já entrar com entrega: sem corte de
        estoque, o S entra em rascunho e alguém o confirma horas depois — e o
        picking nasce com a fatura já existindo. Foi assim que a logística viu
        "Sem nota fiscal: EL-VG/OUT/01888" com a NFe arquivada do outro lado.
        """
        Picking = self.env['stock.picking']
        if 'nfe_move_id' not in Picking._fields:
            self.skipTest("liber_nfe_picking não está instalado")
        self.account.order_stock_cutoff = False        # o pedido só registra
        pedido, _painel = self._pedido_com_nota()
        pedido._import_to_odoo()
        venda = pedido.sale_order_id
        self.assertFalse(venda.picking_ids, "fora do corte não há entrega")
        self.assertFalse(pedido.invoice_id, "nem fatura automática")
        pedido.action_create_invoice()                 # o faturista, à mão
        self.assertTrue(pedido.invoice_id)

        venda.action_confirm()                          # a logística, depois
        self.assertTrue(venda.picking_ids)
        self.assertTrue(all(p.nfe_move_id == pedido.invoice_id
                            for p in venda.picking_ids),
                        "o picking nasceu sem a nota que já existia")

    def test_the_xml_hangs_on_the_invoice(self):
        """Ligação é caminho; arquivo é posse.

        A chave já liga a fatura ao painel, mas quem abre a fatura para
        conferir quer o documento no clipe, não uma viagem a outra tela.
        """
        pedido, painel = self._pedido_com_nota()
        pedido._import_to_odoo()
        anexos = self.env['ir.attachment'].search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', pedido.invoice_id.id)])
        self.assertTrue(anexos.filtered(lambda a: a.name.endswith('.xml')),
                        "o XML não ficou pendurado na fatura")

    def test_the_xml_hangs_on_the_delivery_too(self):
        # Quem separa a caixa confere a nota ali; mandar navegar até o painel
        # no meio da expedição é pedir que não se confira.
        Picking = self.env['stock.picking']
        if 'nfe_move_id' not in Picking._fields:
            self.skipTest("liber_nfe_picking não está instalado")
        pedido, _painel = self._pedido_com_nota()
        pedido._import_to_odoo()
        # Dentro do corte a importação já confirma a venda (o corte manda na
        # operação inteira) — confirmar de novo aqui seria erro do Odoo.
        entrega = pedido.sale_order_id.picking_ids[:1]
        self.assertTrue(entrega, "dentro do corte a entrega nasce na importação")
        anexos = self.env['ir.attachment'].search([
            ('res_model', '=', 'stock.picking'), ('res_id', '=', entrega.id)])
        self.assertTrue(anexos.filtered(lambda a: a.name.endswith('.xml')))
