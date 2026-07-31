# -*- coding: utf-8 -*-
"""Each test guards one clause of the rewrite agreed on 20/07:

a rejected send blocks the confirmation instead of leaving it confirmed-but-
rejected; the payload derives from the dropship destination and nothing else;
addresses survive without l10n_br; the freight picker is pure; the salesperson
can overrule it from 'Add shipping'; and the API client is the only door to
requests.
No test talks to the network -- the client is mocked at the model boundary.
"""
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


def _mock_api(responses):
    """Patch metabrasil.api._request to serve canned (code, data) answers,
    keyed by (method, path-prefix); records every call for assertions."""
    calls = []

    def _request(self, company, method, path, payload=None):
        calls.append((method, path, payload))
        for (m, prefix), answer in responses.items():
            if m == method and path.startswith(prefix):
                return answer
        return 404, {'error': 'no canned answer for %s %s' % (method, path)}

    return calls, _request


RATES = {
    'totalWeight': 1.2, 'totalVolumes': 1,
    'shippingCarrier': [
        {'name': "Loggi", 'cnpj': '11222333000144', 'code': 7,
         'shippingServices': [
             {'code': 71, 'price': '18.40', 'days': '6'},
             {'code': 72, 'price': '25.00', 'days': '3'}]},
        {'name': "Correios", 'cnpj': '34028316000103', 'code': 1,
         'shippingServices': [
             {'code': 41, 'price': '12.10', 'days': '9'}]},
    ]}


@tagged('post_install', '-at_install')
class TestMetabrasil(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.printer = cls.env['res.partner'].create({
            'name': "Metabrasil (teste)", 'company_type': 'company'})
        cls.company.write({
            'metabrasil_enabled': True,
            'metabrasil_mode': 'test',
            'metabrasil_test_api_url': 'https://sandbox.invalid/api',
            'metabrasil_access_key': 'chave-teste',
            'metabrasil_partner_id': cls.printer.id,
            'metabrasil_auto_validate_picking': False,
            'metabrasil_send_status_mails': False,
        })
        cls.company.partner_id.write({
            'street': "Av. do Trabalho, 450", 'zip': '06700-930',
            'street2': "Vila Guilherme",  # bairro without l10n_br
            'city': "São Paulo", 'vat': '12.345.678/0001-90'})
        cls.customer = cls.env['res.partner'].create({
            'name': "Livraria Cliente",
            'street': "Rua João XXIII, 987", 'zip': '06730-000',
            'city': "Cotia"})
        cls.book = cls.env['product.product'].create({
            'name': "Livro Teste", 'type': 'consu', 'is_storable': True,
            'list_price': 60.0, 'barcode': '9786583400999'})
        cls.api_cls = type(cls.env['metabrasil.api'])

    def _sale(self):
        return self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {
                'product_id': self.book.id, 'product_uom_qty': 3})],
        })

    def _purchase(self, sale=None, dest=None):
        line = {'product_id': self.book.id, 'product_qty': 3,
                'price_unit': 20.0}
        if sale:
            line['sale_line_id'] = sale.order_line[0].id
        return self.env['purchase.order'].create({
            'partner_id': self.printer.id,
            'company_id': self.company.id,
            'dest_address_id': dest and dest.id or False,
            'order_line': [(0, 0, line)],
        })

    # -- address without l10n_br ----------------------------------------
    def test_split_street(self):
        po_model = self.env['purchase.order']
        self.assertEqual(po_model._metabrasil_split_street("Rua João XXIII, 987"),
                         ("Rua João XXIII", "987"))
        self.assertEqual(po_model._metabrasil_split_street("Av. Brasil 1500"),
                         ("Av. Brasil", "1500"))
        self.assertEqual(po_model._metabrasil_split_street("Estrada do Campo"),
                         ("Estrada do Campo", "S/N"))
        self.assertEqual(po_model._metabrasil_split_street(False),
                         ("", "S/N"))

    # -- payload derives from the dropship destination -------------------
    def test_payload_warehouse_mode(self):
        """No delivery address on the print order: the run lands at our depot
        and the payload says EDITORA."""
        sale = self._sale()
        po = self._purchase(sale=sale)
        payload = po._metabrasil_prepare_payload()
        self.assertEqual(payload['pedidoType'], 'EDITORA')
        self.assertEqual(payload['metodo_envio'], 'CARRO META')
        self.assertEqual(payload['cpf_cnpj'], '12345678000190')
        self.assertEqual(payload['cep_entrega'], '06700-930')  # our depot
        # bairro_entrega is required by Metabrasil; a missing one is a hard 400
        self.assertEqual(payload['bairro_entrega'], 'Vila Guilherme')
        self.assertEqual(len(payload['listaItems']), 1)
        self.assertEqual(payload['listaItems'][0]['referenciaISBN'],
                         '9786583400999')

    def test_payload_warehouse_pickup(self):
        self.company.metabrasil_warehouse_transport = 'pickup'
        sale = self._sale()
        po = self._purchase(sale=sale)
        self.assertEqual(po._metabrasil_prepare_payload()['metodo_envio'],
                         'RETIRADA')

    def test_payload_customer_mode(self):
        """A delivery address means dropship: DROP_SHIP plus the transporter
        codes the sale remembered from 'Add shipping'."""
        sale = self._sale()
        sale.write({'metabrasil_carrier_vat': '11.222.333/0001-44',
                    'metabrasil_carrier_code': 7,
                    'metabrasil_service_code': 71})
        po = self._purchase(sale=sale, dest=self.customer)
        payload = po._metabrasil_prepare_payload()
        self.assertEqual(payload['pedidoType'], 'DROP_SHIP')
        self.assertFalse(payload['metodo_envio'])
        self.assertEqual(payload['cnpjTransportadora'], '11222333000144')
        self.assertEqual(payload['shippingServicesCode'], 71)
        self.assertEqual(payload['cep_entrega'], '06730-000')
        self.assertEqual(payload['logradouro_entrega'], "Rua João XXIII")
        self.assertEqual(payload['numero_entrega'], "987")

    def test_delivery_mode_reads_the_destination(self):
        """The destination address is the whole question -- there is no second
        place to declare it and therefore nothing to disagree with."""
        po = self._purchase(dest=self.customer)
        self.assertEqual(po._metabrasil_delivery_mode(), 'customer')
        po_wh = self._purchase()
        self.assertEqual(po_wh._metabrasil_delivery_mode(), 'warehouse')

    def test_print_order_links_back_to_the_sale(self):
        """Both directions, through the real line-to-line link."""
        sale = self._sale()
        po = self._purchase(sale=sale, dest=self.customer)
        self.assertEqual(po.metabrasil_sale_order_id, sale)
        self.assertEqual(sale.metabrasil_purchase_order_ids, po)
        self.assertEqual(sale.metabrasil_purchase_order_count, 1)
        action = sale.action_view_metabrasil_purchase_orders()
        self.assertEqual(action['res_id'], po.id)

    # -- sending: success and persistent failure ------------------------
    def test_send_success(self):
        po = self._purchase()
        calls, fake = _mock_api({('POST', '/pedidos'):
                                 (200, {'codigoEncomenda': 'MB-123'})})
        with patch.object(self.api_cls, '_request', fake):
            po._metabrasil_send()
        self.assertTrue(po.metabrasil_sent)
        self.assertEqual(po.metabrasil_status, 'included')
        self.assertEqual(po.metabrasil_order_ref, 'MB-123')
        self.assertEqual(len(calls), 1)

    def test_send_failure_blocks_confirmation(self):
        """A rejection on the way out raises, so the confirmation rolls back
        and the order never advances -- fix the cause and confirm again. No
        error status is written, because the order stays an RFQ."""
        po = self._purchase()
        _, fake = _mock_api({('POST', '/pedidos'):
                             (400, {'titulo': 'O item 9786583400999 não '
                                    'encontrado no POD, favor verificar'})})
        with patch.object(self.api_cls, '_request', fake):
            with self.assertRaises(UserError):
                po._metabrasil_send()
        self.assertFalse(po.metabrasil_sent)
        self.assertEqual(po.metabrasil_status, 'not_sent')

    # -- production pricing ladder (/precificacao) ------------------------
    def test_production_ladder_is_keyed_by_tiragem(self):
        """The ladder is keyed by tiragem, never by position: trusting the
        order would price a 100-copy run at the 50-copy rate the day the
        printer reorders the list.

        The live endpoint is still a 404 on their side (2026-07); this guards
        the contract so the day they publish it, we read it right.
        """
        ladder = self.env['product.template']._metabrasil_parse_ladder({
            'isbn': '9786583400999',
            'resultados': [{'tiragem': 100, 'valor': 527.20},
                           {'tiragem': 50, 'valor': 300.00}]})
        # valor is the total for the run; supplierinfo.price is per unit
        self.assertAlmostEqual(ladder[100], 5.272, places=3)
        self.assertAlmostEqual(ladder[50], 6.0, places=3)

    def test_production_ladder_drops_junk(self):
        """Zeros, missing keys and unparseable runs never reach a price."""
        ladder = self.env['product.template']._metabrasil_parse_ladder({
            'resultados': [{'tiragem': 50, 'valor': 0.0},
                           {'tiragem': 'x', 'valor': 10.0},
                           {'valor': 10.0},
                           {'tiragem': 10, 'valor': 25.0}]})
        self.assertEqual(ladder, {10: 2.5})

    # -- vendor price ladder (cron + buttons) -----------------------------
    def _price_answer(self, ladder):
        return _mock_api({('POST', '/precificacao'): (200, {
            'isbn': self.book.barcode,
            'resultados': [{'tiragem': run, 'valor': value}
                           for run, value in ladder.items()]})})

    def test_price_sweep_writes_supplierinfo(self):
        """The ladder lands as native vendor-price lines, in BRL, one per run
        -- which is what lets Odoo resolve the price by quantity offline.

        `valor` is the total for the run and supplierinfo.price is per unit,
        so the numbers must come out divided: quoting 527.20 for a hundred
        copies is 5.272 each, not 527.20 each.
        """
        self.company.metabrasil_print_runs = '1,15,100'
        tmpl = self.book.product_tmpl_id
        _, fake = self._price_answer({1: 7.462, 15: 84.66, 100: 527.20})
        with patch.object(self.api_cls, '_request', fake):
            summary = tmpl._metabrasil_refresh_prices()
        self.assertEqual(summary['priced'], 1)
        lines = tmpl.seller_ids.filtered(
            lambda s: s.partner_id == self.printer)
        self.assertEqual(sorted(lines.mapped('min_qty')), [1.0, 15.0, 100.0])
        self.assertAlmostEqual(
            lines.filtered(lambda s: s.min_qty == 100).price, 5.272, places=3)
        self.assertAlmostEqual(
            lines.filtered(lambda s: s.min_qty == 15).price, 5.644, places=3)
        # mapped() over a m2o dedupes, so this asserts "every line, one and
        # the same currency, and it is BRL".
        self.assertEqual(lines.currency_id.mapped('name'), ['BRL'])
        self.assertTrue(tmpl.metabrasil_price_date)

    def test_above_cost_flag(self):
        """The red line: printing costs more than the book is worth to us."""
        tmpl = self.book.product_tmpl_id
        tmpl.standard_price = 10.0
        cheap, dear = self.env['product.supplierinfo'].create([
            {'partner_id': self.printer.id, 'product_tmpl_id': tmpl.id,
             'min_qty': 100, 'price': 6.0,
             'currency_id': self.company.currency_id.id},
            {'partner_id': self.printer.id, 'product_tmpl_id': tmpl.id,
             'min_qty': 1, 'price': 14.0,
             'currency_id': self.company.currency_id.id},
        ])
        self.assertFalse(cheap.metabrasil_above_cost)
        self.assertTrue(dear.metabrasil_above_cost)
        self.assertEqual(dear.metabrasil_product_cost, 10.0)

    def test_above_cost_needs_a_cost(self):
        """No cost recorded means nothing to compare -- never flag red on a
        product whose cost simply was not filled in."""
        tmpl = self.book.product_tmpl_id
        tmpl.standard_price = 0.0
        line = self.env['product.supplierinfo'].create({
            'partner_id': self.printer.id, 'product_tmpl_id': tmpl.id,
            'min_qty': 1, 'price': 999.0,
            'currency_id': self.company.currency_id.id})
        self.assertFalse(line.metabrasil_above_cost)

    def test_zero_valor_is_not_a_free_book(self):
        """The printer answers 0 for titles it has no price for -- most of
        the catalogue. Storing that would make purchase lines cost nothing."""
        self.company.metabrasil_print_runs = '1,15'
        tmpl = self.book.product_tmpl_id
        _, fake = self._price_answer({1: 0.0, 15: 0.0})
        with patch.object(self.api_cls, '_request', fake):
            summary = tmpl._metabrasil_refresh_prices()
        self.assertEqual(summary['unpriced'], 1)
        self.assertFalse(tmpl.seller_ids.filtered(
            lambda s: s.partner_id == self.printer))

    def test_price_sweep_prunes_dropped_run(self):
        """Drop a run from Settings and its line must go, or the ladder keeps
        quoting a tier nobody asks for."""
        tmpl = self.book.product_tmpl_id
        self.company.metabrasil_print_runs = '1,15,40'
        _, fake = self._price_answer({1: 30.0, 15: 12.0, 40: 8.5})
        with patch.object(self.api_cls, '_request', fake):
            tmpl._metabrasil_refresh_prices()
        self.company.metabrasil_print_runs = '1,40'
        _, fake = self._price_answer({1: 29.0, 40: 8.0})
        with patch.object(self.api_cls, '_request', fake):
            tmpl._metabrasil_refresh_prices()
        lines = tmpl.seller_ids.filtered(
            lambda s: s.partner_id == self.printer)
        self.assertEqual(sorted(lines.mapped('min_qty')), [1.0, 40.0])

    def test_price_sweep_tags_and_untags(self):
        """A price coming back is the catalogue-membership test; losing it
        takes the tag off but keeps the last known prices, because a purchase
        line at zero is a worse lie than a stale price."""
        tag = self.env['product.tag'].create({'name': "PoD (teste)"})
        self.company.metabrasil_pod_tag_id = tag.id
        self.company.metabrasil_print_runs = '1'
        tmpl = self.book.product_tmpl_id

        _, fake = self._price_answer({1: 30.0})
        with patch.object(self.api_cls, '_request', fake):
            tmpl._metabrasil_refresh_prices()
        self.assertIn(tag, tmpl.product_tag_ids)

        _, silent = _mock_api({('POST', '/precificacao'): (404, {})})
        with patch.object(self.api_cls, '_request', silent):
            summary = tmpl._metabrasil_refresh_prices()
        self.assertEqual(summary['unpriced'], 1)
        self.assertNotIn(tag, tmpl.product_tag_ids)
        self.assertTrue(tmpl.seller_ids.filtered(
            lambda s: s.partner_id == self.printer))

    def test_cron_batches_and_chains(self):
        """The cron is killed at 120s and the catalogue needs minutes, so it
        must take a bite and re-trigger -- never try the whole thing at once,
        which would die at the same book on every run."""
        Product = self.env['product.template']
        for index in range(4):
            Product.create({'name': "Lote %s" % index,
                            'barcode': '978100000000%s' % index})
        # Count what THIS batch stamped, by time. Counting the table measured
        # the fixture instead of the batch (green on an empty base, red on a
        # full one), and counting the delta of "has a date at all" still missed
        # any book the batch picked that already carried an older, stale date
        # -- and the cron sweeps with commit=True, so earlier runs leave those
        # behind on a real base.
        started = fields.Datetime.subtract(fields.Datetime.now(), seconds=1)
        self.company.metabrasil_print_runs = '1'
        _, fake = self._price_answer({1: 10.0})
        with patch.object(self.api_cls, '_request', fake), \
             patch('odoo.addons.liber_metabrasil.models.product_template.'
                   'CRON_BATCH', 2), \
             patch.object(type(self.env['ir.cron']), '_trigger') as chained:
            Product._cron_metabrasil_refresh_prices()
        # more stale books than one batch -> it asks to be run again
        chained.assert_called_once()
        swept = Product.search_count(
            [('metabrasil_price_check_date', '>=', started)])
        self.assertEqual(swept, 2, "a batch must stop at CRON_BATCH books")

    def test_cron_skips_freshly_checked(self):
        """A book asked about yesterday is not asked about again today: that
        is what lets each chained run advance."""
        Product = self.env['product.template']
        book = Product.create({'name': "Fresco", 'barcode': '9781000009999'})
        # Everything else in the base must be non-stale too, or the cron has
        # other work and the assertion below says nothing. Marking them checked
        # is the way to do that: the previous version UNLINKED every barcoded
        # product instead, which on a base with a real catalogue died on the
        # first foreign key pointing at it (royalty lines, order lines, quants).
        now = fields.Datetime.now()
        Product.search([('id', '!=', book.id),
                        ('barcode', '!=', False)]).metabrasil_price_check_date = now
        book.metabrasil_price_check_date = now
        with patch.object(self.api_cls, '_request') as called:
            summary = Product._cron_metabrasil_refresh_prices()
        called.assert_not_called()
        self.assertEqual(summary['priced'], 0)

    def test_price_sweep_refuses_to_run_twice(self):
        """A second click must not start a parallel sweep: two of them double
        the load on the printer and race each other over the same lines."""
        Product = self.env['product.template']
        self.assertTrue(Product._metabrasil_claim_sweep())
        try:
            self.company.metabrasil_print_runs = '1'
            _, fake = self._price_answer({1: 30.0})
            with patch.object(self.api_cls, '_request', fake):
                summary = self.book.product_tmpl_id._metabrasil_refresh_prices()
            self.assertTrue(summary.get('busy'))
            self.assertEqual(summary['priced'], 0)
        finally:
            Product._metabrasil_release_sweep()
        # lock released -> the next caller goes through
        self.assertTrue(Product._metabrasil_claim_sweep())
        Product._metabrasil_release_sweep()

    def test_inline_sweep_is_capped(self):
        """Too many books selected: refuse instead of freezing the browser."""
        books = self.env['product.template']
        for index in range(3):
            books |= self.env['product.template'].create({
                'name': "Livro %s" % index, 'barcode': '978000000000%s' % index})
        with patch.object(type(books), '_metabrasil_refresh_prices') as swept:
            with patch('odoo.addons.liber_metabrasil.models.product_template.'
                       'INLINE_LIMIT', 2):
                with self.assertRaises(UserError):
                    books.action_metabrasil_refresh_prices()
            swept.assert_not_called()

    def test_settings_button_schedules_instead_of_blocking(self):
        """The catalogue-wide button hands the job to the cron."""
        settings = self.env['res.config.settings'].create({})
        cron = self.env.ref('liber_metabrasil.ir_cron_metabrasil_prices')
        with patch.object(type(cron), '_trigger') as triggered:
            action = settings.action_metabrasil_refresh_prices()
        triggered.assert_called_once()
        self.assertEqual(action['tag'], 'display_notification')

    def test_print_run_list_parsing(self):
        """Settings is free text, so junk must not reach the API."""
        self.company.metabrasil_print_runs = '100, 1 ,,15, abc, -5, 15'
        self.assertEqual(self.company._metabrasil_print_run_list(),
                         [1, 15, 100])

    # -- status ladder ---------------------------------------------------
    def test_status_apply(self):
        po = self._purchase()
        po.metabrasil_sent = True
        po._metabrasil_apply_status({'statusPedido': 'Impressão',
                                     'codigoEncomenda': 'MB-9'})
        self.assertEqual(po.metabrasil_status, 'printing')
        self.assertEqual(po.metabrasil_order_ref, 'MB-9')
        po._metabrasil_apply_status({'statusPedido': 'Expedido',
                                     'codigoRastreio': 'XX123BR',
                                     'urlRastreio': 'https://t.invalid/XX123BR'})
        self.assertEqual(po.metabrasil_status, 'shipped')

    def test_status_unknown_is_kept_quiet(self):
        po = self._purchase()
        po.metabrasil_status = 'printing'
        po._metabrasil_apply_status({'statusPedido': 'Algo Novo'})
        self.assertEqual(po.metabrasil_status, 'printing')  # unchanged
        self.assertTrue(po.metabrasil_sync_date)

    # -- freight picking is pure ----------------------------------------
    def test_carrier_service_choice(self):
        carrier = self.env.ref('liber_metabrasil.delivery_carrier_metabrasil')
        cheap = carrier._metabrasil_services(RATES['shippingCarrier'])
        self.assertEqual(cheap[0]['price'], 12.10)
        self.assertEqual(cheap[0]['carrier_name'], "Correios")
        carrier.metabrasil_service_choice = 'fast'
        fast = carrier._metabrasil_services(RATES['shippingCarrier'])
        self.assertEqual(fast[0]['days'], 3)
        carrier.metabrasil_excluded_carriers = 'correios'
        carrier.metabrasil_service_choice = 'cheap'
        no_correios = carrier._metabrasil_services(RATES['shippingCarrier'])
        self.assertTrue(all(s['carrier_name'] != "Correios"
                            for s in no_correios))

    def test_rate_shipment_remembers_choice(self):
        """No wizard in sight (a website or automated quote): the carrier's
        own rule picks, and the sale still remembers the codes."""
        sale = self._sale()
        carrier = self.env.ref('liber_metabrasil.delivery_carrier_metabrasil')
        _, fake = _mock_api({('POST', '/fretes/'): (200, RATES)})
        with patch.object(self.api_cls, '_request', fake):
            result = carrier.metabrasil_rate_shipment(sale)
        self.assertTrue(result['success'])
        self.assertEqual(result['price'], 12.10)
        self.assertEqual(sale.metabrasil_carrier_name, "Correios")
        self.assertEqual(sale.metabrasil_service_code, 41)
        self.assertEqual(sale.metabrasil_total_volumes, 1)

    # -- dropship with nobody to buy from --------------------------------
    def _dropship_route(self):
        return self.env.ref('stock_dropshipping.route_drop_shipping')

    def test_dropship_without_vendor_is_named_and_refused(self):
        """The silent failure: on the dropship route no delivery is planned
        out of our stock, and with no vendor no purchase is born either -- so
        confirmation would produce nothing at all while the customer is
        invoiced. It must be visible on the quotation and refused at
        confirmation."""
        self.book.product_tmpl_id.route_ids = [(4, self._dropship_route().id)]
        self.assertFalse(self.book.seller_ids)
        sale = self._sale()
        self.assertIn(self.book.display_name, sale.metabrasil_dropship_warning)
        with self.assertRaises(UserError):
            sale.action_confirm()
        self.assertEqual(sale.state, 'draft', "the order must stay a quotation")

    def test_dropship_with_vendor_passes(self):
        """A vendor is all it takes: the warning clears and the order
        confirms."""
        self.book.product_tmpl_id.write({
            'route_ids': [(4, self._dropship_route().id)],
            'seller_ids': [(0, 0, {'partner_id': self.printer.id,
                                   'min_qty': 1, 'price': 20.0})],
        })
        sale = self._sale()
        self.assertFalse(sale.metabrasil_dropship_warning)
        sale.action_confirm()
        self.assertEqual(sale.state, 'sale')

    def test_vendorless_product_off_the_route_is_left_alone(self):
        """The guard is about dropship, not about vendors: an ordinary book
        with no vendor ships from stock and must not be blocked."""
        self.assertFalse(self.book.seller_ids)
        sale = self._sale()
        self.assertFalse(sale.metabrasil_dropship_warning)
        sale.action_confirm()
        self.assertEqual(sale.state, 'sale')

    def test_dropship_vendor_only_on_a_tier_still_passes(self):
        """A vendor whose price ladder starts above the ordered quantity is
        still a vendor. Blocking there would be a false positive -- the
        ladder not reaching a print run is Odoo's own complaint, not ours."""
        self.book.product_tmpl_id.write({
            'route_ids': [(4, self._dropship_route().id)],
            'seller_ids': [(0, 0, {'partner_id': self.printer.id,
                                   'min_qty': 100, 'price': 5.0})],
        })
        sale = self._sale()  # 3 copies, ladder starts at 100
        self.assertFalse(sale.metabrasil_dropship_warning)

    # -- choosing the transporter in 'Add shipping' -----------------------
    def _delivery_wizard(self, sale):
        carrier = self.env.ref('liber_metabrasil.delivery_carrier_metabrasil')
        return self.env['choose.delivery.carrier'].create({
            'order_id': sale.id, 'carrier_id': carrier.id})

    def test_wizard_lists_every_quoted_transporter(self):
        """One call to Metabrasil, every service on the table -- and the
        carrier's Pick By rule only decides which one starts selected."""
        sale = self._sale()
        wizard = self._delivery_wizard(sale)
        calls, fake = _mock_api({('POST', '/fretes/'): (200, RATES)})
        with patch.object(self.api_cls, '_request', fake):
            wizard.update_price()
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(wizard.metabrasil_option_ids), 3)
        self.assertEqual(wizard.metabrasil_option_id.carrier_name, "Correios")
        self.assertEqual(wizard.delivery_price, 12.10)

    def test_wizard_honours_the_chosen_transporter(self):
        """Overruling the cheapest must not re-quote (their prices move
        between calls) and must be what lands on the sale."""
        sale = self._sale()
        wizard = self._delivery_wizard(sale)
        _, fake = _mock_api({('POST', '/fretes/'): (200, RATES)})
        with patch.object(self.api_cls, '_request', fake):
            wizard.update_price()

        loggi_fast = wizard.metabrasil_option_ids.filtered(
            lambda o: o.carrier_name == "Loggi" and o.service_code == 72)
        wizard.metabrasil_option_id = loggi_fast
        with patch.object(self.api_cls, '_request') as never:
            wizard._onchange_metabrasil_option_id()
            wizard.button_confirm()
        never.assert_not_called()

        self.assertEqual(wizard.delivery_price, 25.00)
        self.assertEqual(sale.metabrasil_carrier_name, "Loggi")
        self.assertEqual(sale.metabrasil_service_code, 72)
        self.assertEqual(sale.metabrasil_carrier_vat, '11222333000144')
        self.assertEqual(sale.metabrasil_delivery_days, 3)
        self.assertEqual(sale.metabrasil_freight_cost, 25.00)
        self.assertEqual(sale.metabrasil_total_volumes, 1)
        # ...and it survives into the print order's payload
        po = self._purchase(sale=sale, dest=self.customer)
        payload = po._metabrasil_prepare_payload()
        self.assertEqual(payload['shippingServicesCode'], 72)
        self.assertEqual(payload['shippingCarrierCode'], 7)

    def test_wizard_keeps_the_choice_across_a_requote(self):
        """Press 'Get rate' again and the transporter already chosen stays
        chosen, as long as Metabrasil still offers it."""
        sale = self._sale()
        wizard = self._delivery_wizard(sale)
        _, fake = _mock_api({('POST', '/fretes/'): (200, RATES)})
        with patch.object(self.api_cls, '_request', fake):
            wizard.update_price()
            wizard.metabrasil_option_id = wizard.metabrasil_option_ids.filtered(
                lambda o: o.service_code == 72)
            wizard.update_price()
        self.assertEqual(wizard.metabrasil_option_id.service_code, 72)
        self.assertEqual(wizard.delivery_price, 25.00)
