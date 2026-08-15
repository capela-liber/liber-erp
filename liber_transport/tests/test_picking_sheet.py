# -*- coding: utf-8 -*-
"""O que estes testes guardam, na folha de quem separa:

- o mesmo título em duas entregas vira UMA linha somada na folha do passeio;
- a ordem é a da prateleira, crescente, e o que não tem endereço vai por
  último;
- título que mora em duas prateleiras sai em duas linhas — são duas paradas;
- o peso sai por linha e somado, e a folha DIZ quantos títulos estão sem peso
  cadastrado em vez de calar e mentir no total;
- o que a reserva não prendeu NUNCA vira linha de coleta: sai como aviso de
  entrega incompleta, sem posição e sem quadradinho;
- uma entrega só na seleção não ganha folha de passeio;
- e o PDF renderiza de ponta a ponta (o template compila).

Regra da casa: nunca criar res.company em teste — reaproveitar env.company.
"""
import io

from odoo.tests.common import TransactionCase
from odoo.tools.pdf import PdfFileReader


class TestPickingSheet(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.out_type = cls.warehouse.out_type_id
        cls.stock = cls.out_type.default_location_src_id
        cls.customer_location = cls.env.ref('stock.stock_location_customers')
        cls.customer = cls.env['res.partner'].create({'name': 'Livraria Teste'})

        Location = cls.env['stock.location']
        cls.shelf_a = Location.create({
            'name': 'ZZ-000001', 'usage': 'internal',
            'location_id': cls.stock.id})
        cls.shelf_b = Location.create({
            'name': 'ZZ-000002', 'usage': 'internal',
            'location_id': cls.stock.id})

        cls.book_a = cls._book('Livro da Prateleira A', weight=0.4)
        cls.book_b = cls._book('Livro da Prateleira B', weight=0.25)
        cls.book_loose = cls._book('Livro sem prateleira', weight=0.3)
        # Sem peso no cadastro: é o caso de 9 em cada 10 títulos da casa.
        cls.book_no_weight = cls._book('Livro sem peso', weight=0.0)

        cls._stock_up(cls.book_a, cls.shelf_a, 100)
        cls._stock_up(cls.book_b, cls.shelf_b, 100)
        cls._stock_up(cls.book_no_weight, cls.shelf_b, 100)
        cls._stock_up(cls.book_loose, cls.stock, 100)

    @classmethod
    def _book(cls, name, weight):
        return cls.env['product.product'].create({
            'name': name, 'type': 'consu', 'is_storable': True,
            'weight': weight})

    @classmethod
    def _stock_up(cls, product, location, qty):
        cls.env['stock.quant']._update_available_quantity(
            product, location, qty)

    def _delivery(self, lines):
        """Uma saída reservada, com (produto, quantidade) por linha."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.out_type.id,
            'partner_id': self.customer.id,
            'location_id': self.stock.id,
            'location_dest_id': self.customer_location.id,
            'move_ids': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': qty,
                'product_uom': product.uom_id.id,
                'location_id': self.stock.id,
                'location_dest_id': self.customer_location.id,
            }) for product, qty in lines],
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _values(self, pickings):
        return self.env['report.liber_transport.report_picking_sheet'] \
            ._get_report_values(pickings.ids)

    # --- a folha do passeio ---------------------------------------------

    def test_batch_sums_same_title(self):
        """Três entregas do mesmo título: uma linha, com a soma."""
        pickings = (self._delivery([(self.book_a, 10)])
                    | self._delivery([(self.book_a, 10)])
                    | self._delivery([(self.book_a, 10)]))
        batch = self._values(pickings)['batch']
        self.assertEqual(len(batch['lines']), 1)
        line = batch['lines'][0]
        self.assertEqual(line['qty'], 30)
        self.assertEqual(line['position'], 'ZZ-000001')
        self.assertAlmostEqual(line['weight'], 12.0, places=3)
        self.assertEqual(batch['titles_total'], 1)

    def test_batch_orders_by_shelf_and_leaves_unaddressed_last(self):
        pickings = (self._delivery([(self.book_b, 3), (self.book_loose, 2)])
                    | self._delivery([(self.book_a, 5)]))
        lines = self._values(pickings)['batch']['lines']
        self.assertEqual([line['position'] for line in lines],
                         ['ZZ-000001', 'ZZ-000002', ''])
        self.assertEqual(lines[-1]['product'], self.book_loose)

    def test_title_on_two_shelves_takes_two_lines(self):
        """Duas paradas do passeio não cabem numa linha só."""
        self._stock_up(self.book_a, self.shelf_b, 4)
        picking = self._delivery([(self.book_a, 102)])
        lines = self._values(picking)['sheets'][0]['lines']
        self.assertEqual(len(lines), 2)
        self.assertEqual([line['position'] for line in lines],
                         ['ZZ-000001', 'ZZ-000002'])
        self.assertEqual(sum(line['qty'] for line in lines), 102)

    def test_single_picking_has_no_batch_sheet(self):
        picking = self._delivery([(self.book_a, 4)])
        self.assertFalse(self._values(picking)['batch'])

    # --- peso -------------------------------------------------------------

    def test_weight_totals_and_missing_weight_warning(self):
        picking = self._delivery([(self.book_a, 10),
                                  (self.book_no_weight, 5)])
        sheet = self._values(picking)['sheets'][0]
        self.assertAlmostEqual(sheet['weight_total'], 4.0, places=3)
        self.assertEqual(sheet['no_weight'], 1)
        sem_peso = [line for line in sheet['lines'] if not line['has_weight']]
        self.assertEqual(len(sem_peso), 1)
        self.assertEqual(sem_peso[0]['product'], self.book_no_weight)

    def test_sheet_without_missing_weight_says_nothing(self):
        picking = self._delivery([(self.book_a, 2)])
        self.assertEqual(self._values(picking)['sheets'][0]['no_weight'], 0)

    # --- o que a reserva não prendeu -------------------------------------

    def test_unreserved_never_becomes_a_pick_line(self):
        """Pedir mais do que há: o que falta vira aviso, nunca linha de coleta.

        Linha na tabela é ordem de buscar. Mandar buscar o que o sistema não
        reservou ou não acha nada na prateleira, ou embala exemplar que não
        está na entrega — e o peso do rodapé, que não conta essas linhas,
        acusaria erro na balança.
        """
        picking = self._delivery([(self.book_a, 130)])
        sheet = self._values(picking)['sheets'][0]
        self.assertEqual(len(sheet['lines']), 1)
        self.assertEqual(sheet['lines'][0]['qty'], 100)
        self.assertEqual(sheet['shortfall'], {'qty': 30, 'titles': 1})
        # O que não foi reservado não entra no total que a balança confere.
        self.assertAlmostEqual(sheet['weight_total'], 40.0, places=3)

    def test_complete_delivery_has_no_shortfall_notice(self):
        picking = self._delivery([(self.book_a, 4)])
        self.assertEqual(
            self._values(picking)['sheets'][0]['shortfall']['titles'], 0)

    def test_batch_counts_incomplete_deliveries(self):
        """Quem monta o lote ainda pode mandar reservar antes do passeio."""
        pickings = (self._delivery([(self.book_a, 130)])
                    | self._delivery([(self.book_b, 2)]))
        batch = self._values(pickings)['batch']
        self.assertEqual(batch['incomplete_pickings'], 1)
        # E o que falta não entrou no passeio.
        self.assertEqual(sum(line['qty'] for line in batch['lines']), 102)

    # --- o PDF ------------------------------------------------------------

    def test_report_renders(self):
        pickings = (self._delivery([(self.book_a, 10), (self.book_loose, 1)])
                    | self._delivery([(self.book_b, 130)]))
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'liber_transport.report_picking_sheet', pickings.ids)
        html = html.decode()
        self.assertIn('Picking', html)
        self.assertIn('ZZ-000001', html)
        self.assertIn('Entrega incompleta', html)
        for picking in pickings:
            self.assertIn(picking.name, html)

    def test_pdf_keeps_the_batch_sheet(self):
        """O corte por registro não pode comer a folha do passeio.

        O motor de PDF do core fatia o arquivo por entrega para anexar cada
        pedaço no seu registro, e a folha do lote — que não é de entrega
        nenhuma — sumia no corte, em silêncio. O override do módulo desliga o
        fatiamento; este teste é o que avisa se ele voltar.
        """
        pickings = (self._delivery([(self.book_a, 4)])
                    | self._delivery([(self.book_b, 2)]))
        pdf, kind = self.env['ir.actions.report']._render_qweb_pdf(
            'liber_transport.report_picking_sheet', pickings.ids)
        self.assertEqual(kind, 'pdf')
        paginas = len(PdfFileReader(io.BytesIO(pdf), strict=False).pages)
        self.assertEqual(paginas, 3, "duas entregas e o passeio: três folhas")
