# -*- coding: utf-8 -*-
"""The bridge: the ticket linked to the CO, and the map as a reply."""
from odoo.exceptions import UserError
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestBridge(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria da Ponte',
            'email': 'ponte@livraria.test',
            'allow_consignment': True,
        })
        cls.agreement = cls.env['consignment.agreement'].create({
            'partner_id': cls.partner.id,
        })
        cls.settlement = cls.env['consignment.settlement'].create({
            'partner_id': cls.partner.id,
        })
        cls.team = cls.env['liber.support.team'].create({
            'name': 'Comercial Ponte',
            'company_id': cls.env.company.id,
            'alias_name': 'ponte-test',
        })
        cls.Ticket = cls.env['liber.support.ticket']

    # -- caminho feliz -------------------------------------------------

    def test_ticket_links_to_co(self):
        ticket = self.Ticket.create({
            'name': 'Cadê meu acerto',
            'team_id': self.team.id,
            'partner_id': self.partner.id,
            'settlement_id': self.settlement.id,
        })
        self.assertEqual(ticket.settlement_id, self.settlement)
        self.assertEqual(self.settlement.support_ticket_count, 1)

    def test_reply_with_map_uses_latest_co(self):
        """Without an explicit link, the button falls back to the
        partner's latest CO and opens a composer with the PDF attached."""
        ticket = self.Ticket.create({
            'name': 'Mapa por favor',
            'team_id': self.team.id,
            'partner_id': self.partner.id,
        })
        action = ticket.action_reply_with_map()
        self.assertEqual(action['res_model'], 'mail.compose.message')
        attachment_cmds = action['context']['default_attachment_ids']
        self.assertTrue(attachment_cmds)
        attachment = self.env['ir.attachment'].browse(
            attachment_cmds[0][1])
        self.assertIn(self.settlement.name, attachment.name)
        self.assertEqual(attachment.res_id, ticket.id)

    # -- caso de erro --------------------------------------------------

    def test_reply_with_map_without_partner_raises(self):
        ticket = self.Ticket.create({
            'name': 'Sem parceiro',
            'team_id': self.team.id,
        })
        with self.assertRaises(UserError):
            ticket.action_reply_with_map()


@tagged('post_install', '-at_install')
class TestCoParser(common.TransactionCase):
    """parse_lines é função pura — formatos reais da caixa comercial."""

    def test_email_list_format(self):
        from ..models.co_parser import parse_lines
        got = parse_lines(
            "Oi gente, tudo bem?\n\n"
            "3 Fim do SUS?\n"
            "2x Banguela\n"
            "Imaginações pós-capitalistas\n"
            "Rua João Elías Saada, n 61, CEP 05427-050\n"
            "Aos cuidados de Caroline\n"
            "Valeu, abração!\n")
        self.assertEqual([(l['qty'], l['label']) for l in got], [
            (3, 'Fim do SUS?'),
            (2, 'Banguela'),
            (1, 'Imaginações pós-capitalistas'),
        ])

    def test_excel_paste_and_isbn(self):
        from ..models.co_parser import parse_lines
        got = parse_lines("Banguela\t4\n9788577151234\t2\n")
        self.assertEqual(got[0]['qty'], 4)
        self.assertEqual(got[1]['isbn'], '9788577151234')
        self.assertEqual(got[1]['qty'], 2)

    def test_empty_and_noise_only(self):
        """Saudação, assinatura e nome solto (1 palavra) não viram linha."""
        from ..models.co_parser import parse_lines
        self.assertEqual(parse_lines(''), [])
        self.assertEqual(parse_lines('Bom dia!\nAtt,\nCaio'), [])
        self.assertEqual(parse_lines(None), [])

    def test_xlsx_rows_to_text(self):
        from ..models.co_parser import xlsx_rows_to_text
        text = xlsx_rows_to_text([('Banguela', 4), (None, None), ('X', 1)])
        self.assertEqual(text, 'Banguela\t4\nX\t1')


@tagged('post_install', '-at_install')
class TestCoWizard(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria Wizard', 'email': 'wiz@livraria.test',
            'allow_consignment': True})
        cls.agreement = cls.env['consignment.agreement'].create(
            {'partner_id': cls.partner.id})
        cls.agreement.action_activate()  # cria a prateleira (location)
        cls.product = cls.env['product.product'].create({
            'name': 'Fim do SUS?', 'type': 'consu', 'is_storable': True,
            'sale_ok': True, 'list_price': 50.0})
        cls.team = cls.env['liber.support.team'].create({
            'name': 'Equipe Wizard', 'company_id': cls.env.company.id,
            'alias_name': 'wizard-test'})
        cls.ticket = cls.env['liber.support.ticket'].create({
            'name': 'Acerto da vitrine', 'team_id': cls.team.id,
            'partner_id': cls.partner.id, 'kind': 'settlement'})

    def test_wizard_parses_and_creates_draft_co(self):
        wizard = self.env['liber.support.co.wizard'].create({
            'ticket_id': self.ticket.id,
            'source_text': '3 Fim do SUS?\n2 Título que não existe\n'})
        wizard._build_lines(wizard.source_text)
        by_label = {l.label_source: l for l in wizard.line_ids}
        self.assertEqual(by_label['Fim do SUS?'].product_id, self.product)
        self.assertEqual(by_label['Fim do SUS?'].confidence, 'exact')
        self.assertFalse(by_label['Título que não existe'].product_id)
        # linha sem produto é ignorada; a boa vira linha da CO
        action = wizard.action_create_co()
        settlement = self.env['consignment.settlement'].browse(
            action['res_id'])
        self.assertEqual(self.ticket.settlement_id, settlement)
        self.assertEqual(settlement.state, 'draft')
        line = settlement.line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.product_id, self.product)
        self.assertEqual(line.qty_reported, 3)

    def test_wizard_return_destination(self):
        """Devolução exige saldo na prateleira (constraint do SOC) —
        encena 10 exemplares na prateleira do acordo antes."""
        shelf = self.agreement.location_id
        self.assertTrue(
            shelf, f"acordo sem prateleira (state={self.agreement.state})")
        self.env['stock.quant'].create({
            'location_id': shelf.id, 'product_id': self.product.id,
            'quantity': 10})
        wizard = self.env['liber.support.co.wizard'].create(
            {'ticket_id': self.ticket.id})
        wizard.line_ids = [(0, 0, {'product_id': self.product.id,
                                   'qty': 5, 'dest': 'return',
                                   'label_source': 'devolução'})]
        action = wizard.action_create_co()
        line = self.env['consignment.settlement'].browse(
            action['res_id']).line_ids
        self.assertEqual(line.qty_return, 5)
        self.assertEqual(line.qty_reported, 0)

    def test_wizard_without_partner_raises(self):
        orphan = self.env['liber.support.ticket'].create({
            'name': 'Sem parceiro', 'team_id': self.team.id})
        wizard = self.env['liber.support.co.wizard'].create({
            'ticket_id': orphan.id})
        wizard.line_ids = [(0, 0, {'product_id': self.product.id,
                                   'qty': 1, 'label_source': 'x'})]
        with self.assertRaises(UserError):
            wizard.action_create_co()

    def test_link_latest_settlement_button(self):
        co = self.env['consignment.settlement'].create(
            {'partner_id': self.partner.id})
        ticket = self.env['liber.support.ticket'].create({
            'name': 'Vincular', 'team_id': self.team.id,
            'partner_id': self.partner.id, 'kind': 'consignment'})
        ticket.action_link_latest_settlement()
        self.assertEqual(ticket.settlement_id, co)


@tagged('post_install', '-at_install')
class TestHtmlToText(common.TransactionCase):
    """O e-mail real vem em <div>s; sem quebrar por bloco o parser fica
    cego (bug de 10/08, achado no HD/145398)."""

    def test_divs_become_lines(self):
        from ..models.co_parser import html_to_text, parse_lines
        html = ('<div>Oi gente, tudo bem?</div>'
                '<div><b>3 Fim do SUS?</b></div>'
                '<div><b>2x Banguela</b></div>'
                '<div>Rua João Elías Saada, n 61</div>'
                '<div>Valeu, abração!</div>')
        got = parse_lines(html_to_text(html))
        self.assertEqual([(l['qty'], l['label']) for l in got],
                         [(3, 'Fim do SUS?'), (2, 'Banguela')])

    def test_br_and_entities(self):
        from ..models.co_parser import html_to_text
        self.assertEqual(html_to_text('a<br/>b&amp;c\xa0d'), 'a\nb&c d')
        self.assertEqual(html_to_text(None), '')


@tagged('post_install', '-at_install')
class TestCoWizardDraft(common.TransactionCase):
    """O rascunho persiste: sair e voltar não perde a conferência."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria Draft', 'email': 'draft@livraria.test',
            'allow_consignment': True})
        cls.env['consignment.agreement'].create(
            {'partner_id': cls.partner.id}).action_activate()
        cls.product = cls.env['product.product'].create({
            'name': 'Título do Rascunho', 'type': 'consu',
            'is_storable': True, 'sale_ok': True, 'list_price': 30.0})
        cls.team = cls.env['liber.support.team'].create({
            'name': 'Equipe Draft', 'company_id': cls.env.company.id,
            'alias_name': 'draft-test'})
        cls.ticket = cls.env['liber.support.ticket'].create({
            'name': 'Acerto', 'team_id': cls.team.id,
            'partner_id': cls.partner.id, 'kind': 'settlement'})

    def test_reopen_returns_same_draft_with_edits(self):
        a1 = self.ticket.action_open_co_wizard()
        wizard = self.env['liber.support.co.wizard'].browse(a1['res_id'])
        wizard.line_ids = [(0, 0, {'product_id': self.product.id,
                                   'qty': 7, 'label_source': 'manual'})]
        a2 = self.ticket.action_open_co_wizard()
        self.assertEqual(a1['res_id'], a2['res_id'],
                         "reabrir deve voltar ao MESMO rascunho")
        self.assertEqual(wizard.line_ids[-1].qty, 7,
                         "a edição manual sobreviveu")

    def test_create_co_discards_draft(self):
        action = self.ticket.action_open_co_wizard()
        wizard = self.env['liber.support.co.wizard'].browse(
            action['res_id'])
        wizard.line_ids = [(0, 0, {'product_id': self.product.id,
                                   'qty': 2, 'label_source': 'x'})]
        wizard.action_create_co()
        self.assertFalse(self.env['liber.support.co.wizard'].search(
            [('ticket_id', '=', self.ticket.id)]),
            "rascunho cumprido some")

    def test_replenish_destination(self):
        wizard = self.env['liber.support.co.wizard'].create(
            {'ticket_id': self.ticket.id})
        wizard.line_ids = [(0, 0, {'product_id': self.product.id,
                                   'qty': 6, 'dest': 'replenish',
                                   'label_source': 'repor'})]
        action = wizard.action_create_co()
        line = self.env['consignment.settlement'].browse(
            action['res_id']).line_ids
        self.assertEqual(line.qty_replenish, 6)
        self.assertEqual(line.qty_reported, 0)

    def test_csv_attachment_parses(self):
        import base64
        att = self.env['ir.attachment'].create({
            'name': 'acerto.csv',
            'res_model': 'liber.support.ticket',
            'res_id': self.ticket.id,
            'datas': base64.b64encode(
                'Título do Rascunho;3\n'.encode('utf-8')),
        })
        wizard = self.env['liber.support.co.wizard'].create(
            {'ticket_id': self.ticket.id, 'attachment_id': att.id})
        wizard.action_parse()
        line = wizard.line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.product_id, self.product)
        self.assertEqual(line.qty, 3)


@tagged('post_install', '-at_install')
class TestReportTable(common.TransactionCase):
    """Caso de 10/08 (HD/145577, tabela da Olist) com a regra final,
    burra de propósito: achou ISBN + número, o número é a quantidade.
    Sem interpretar cabeçalho — inferência fica para o módulo claude."""

    OLIST = (
        '<table><tr><th>Olá! Confira o relatório</th></tr>'
        '<tr><td>Código</td><td>Produto</td><td>Estoque Mínimo</td>'
        '<td>Quantidade em Estoque</td></tr>'
        '<tr><td>9788577150199</td><td>A cidade e as serras</td>'
        '<td>2</td><td>0</td></tr>'
        '<tr><td>97885771 52438</td><td>A cor que caiu do espaço</td>'
        '<td>3</td><td>1</td></tr>'
        '</table>')

    def test_isbn_plus_number_is_qty(self):
        from ..models.co_parser import extract_report_tables
        rest, items = extract_report_tables(
            '<div>Você possui 54 produtos abaixo</div>' + self.OLIST)
        self.assertEqual(
            [(i['isbn'], i['qty'], i['label']) for i in items],
            [('9788577150199', 2, 'A cidade e as serras'),
             ('9788577152438', 3, 'A cor que caiu do espaço')],
            "primeiro número da linha é a quantidade; ISBN quebrado colado")
        # a tabela saiu do texto; o resto do e-mail fica
        self.assertNotIn('cidade e as serras', rest)
        self.assertIn('54 produtos', rest)

    def test_items_roundtrip_through_parser(self):
        from ..models.co_parser import (extract_report_tables,
                                        items_to_text, parse_lines)
        _rest, items = extract_report_tables(self.OLIST)
        got = parse_lines(items_to_text(items))
        self.assertEqual([(l['isbn'], l['qty'], l['label']) for l in got],
                         [('9788577150199', 2, 'A cidade e as serras'),
                          ('9788577152438', 3,
                           'A cor que caiu do espaço')])

    def test_row_without_number_defaults_to_one(self):
        from ..models.co_parser import table_items
        items = table_items([['9788577150199', 'A cidade e as serras']])
        self.assertEqual(items[0]['qty'], 1)

    def test_layout_table_is_not_a_report(self):
        from ..models.co_parser import extract_report_tables
        rest, items = extract_report_tables(
            '<table><tr><td>Olá!</td></tr>'
            '<tr><td>Um abraço, equipe</td></tr></table>')
        self.assertEqual(items, [])
        self.assertIn('Olá!', rest)


@tagged('post_install', '-at_install')
class TestXlsxRealWorld(common.TransactionCase):
    """Caso do HD/143298 (10/08): o modelo de importação da EdLab.
    openpyxl entrega float; a linha tem cliente e desconto além da
    quantidade."""

    def test_float_cells_become_ints(self):
        from ..models.co_parser import xlsx_rows_to_text
        text = xlsx_rows_to_text([
            ('Racine', 9786589705468.0, '1', 40.0),
            (None, 9788577159468.0, '2', 40.0),
        ])
        self.assertEqual(text, 'Racine\t9786589705468\t1\t40\n'
                               '9788577159468\t2\t40')

    def test_import_template_line(self):
        from ..models.co_parser import parse_lines, xlsx_rows_to_text
        text = xlsx_rows_to_text([
            ('Racine', '(A) Venda CFOP: 5101', 'Jorge Sallum',
             9786589705468.0, '1', 40.0),
            (None, None, None, 9788577159468.0, '3', 40.0),
        ])
        got = parse_lines(text)
        self.assertEqual([(l['isbn'], l['qty']) for l in got],
                         [('9786589705468', 1), ('9788577159468', 3)],
                         "quantidade é o primeiro número puro da linha, "
                         "não o desconto 40")


@tagged('post_install', '-at_install')
class TestDefaultDest(common.TransactionCase):
    """A opção de lote: acerto, reposição ou devolução para tudo."""

    def test_parse_uses_default_dest(self):
        partner = self.env['res.partner'].create(
            {'name': 'Livraria Lote', 'email': 'lote@livraria.test'})
        team = self.env['liber.support.team'].create({
            'name': 'Equipe Lote', 'company_id': self.env.company.id,
            'alias_name': 'lote-test'})
        ticket = self.env['liber.support.ticket'].create({
            'name': 'Reposição', 'team_id': team.id,
            'partner_id': partner.id})
        wizard = self.env['liber.support.co.wizard'].create({
            'ticket_id': ticket.id, 'default_dest': 'replenish',
            'source_text': '3 Qualquer Título\n2 Outro Livro\n'})
        wizard._build_lines(wizard.source_text)
        self.assertTrue(wizard.line_ids)
        self.assertEqual(set(wizard.line_ids.mapped('dest')),
                         {'replenish'},
                         "toda linha nasce com o destino do lote")


@tagged('post_install', '-at_install')
class TestPdfImport(common.TransactionCase):
    """PDF gerado por sistema tem camada de texto: a máquina de importar
    lê direto, sem OCR (10/08/2026)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria PDF', 'email': 'pdf@livraria.test'})
        cls.product = cls.env['product.product'].create({
            'name': 'Livro do PDF', 'type': 'consu', 'sale_ok': True,
            'barcode': '9788577159999', 'list_price': 45.0})
        cls.team = cls.env['liber.support.team'].create({
            'name': 'Equipe PDF', 'company_id': cls.env.company.id,
            'alias_name': 'pdf-test'})
        cls.ticket = cls.env['liber.support.ticket'].create({
            'name': 'Pedido em PDF', 'team_id': cls.team.id,
            'partner_id': cls.partner.id})

    @staticmethod
    def _make_pdf(lines):
        import io
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        y = 800
        for line in lines:
            c.drawString(40, y, line)
            y -= 20
        c.save()
        return buf.getvalue()

    def test_pdf_attachment_parses(self):
        import base64
        raw = self._make_pdf(['Pedido da livraria:',
                              '3 Livro do PDF',
                              '9788577159999 2'])
        att = self.env['ir.attachment'].create({
            'name': 'pedido.pdf',
            'res_model': 'liber.support.ticket',
            'res_id': self.ticket.id,
            'datas': base64.b64encode(raw)})
        wizard = self.env['liber.support.co.wizard'].create(
            {'ticket_id': self.ticket.id, 'attachment_id': att.id})
        wizard.action_parse()
        pairs = [(l.product_id, l.qty) for l in wizard.line_ids
                 if l.product_id]
        self.assertIn((self.product, 3), pairs,
                      "linha de texto do PDF virou proposta")
        self.assertIn((self.product, 2), pairs,
                      "ISBN + número do PDF: o número é a quantidade")

    def test_scanned_pdf_yields_nothing(self):
        """PDF sem camada de texto (só imagem) sai vazio, sem quebrar."""
        import base64
        raw = self._make_pdf([])  # página em branco = sem texto
        att = self.env['ir.attachment'].create({
            'name': 'scan.pdf',
            'res_model': 'liber.support.ticket',
            'res_id': self.ticket.id,
            'datas': base64.b64encode(raw)})
        wizard = self.env['liber.support.co.wizard'].create(
            {'ticket_id': self.ticket.id, 'attachment_id': att.id})
        wizard.action_parse()
        self.assertFalse(wizard.line_ids)
