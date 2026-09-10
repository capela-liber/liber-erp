# -*- coding: utf-8 -*-
"""Sending changes back to Metabooks.

Nothing here touches the network: the export produces a file and stops. What is
worth asserting is the loop a person actually depends on -- edit a book, see
exactly that change queued, get it out as a spreadsheet with the changed cell in
red, and have the book leave the queue only once the file was really delivered.
"""

import base64
import io
import zipfile
from datetime import date, timedelta

import openpyxl
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..services import metabooks_sheet as sheet


def _max_track(env):
    """Where a book's change history starts for a book already sent."""
    return env['mail.tracking.value'].search([], order='id desc', limit=1).id or 0


def _font_rgb(cell):
    """Colour of a cell as a string.

    openpyxl hands back a plain str for an explicit colour and an RGB
    descriptor object for a default one, so normalise before comparing.
    """
    colour = cell.font.color
    return str(colour.rgb) if colour is not None and colour.rgb else ''


@tagged('post_install', '-at_install')
class TestMetabooksExport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The queue is global: action_prepare searches every pending book in
        # the database, so a real one left pending by someone working in this
        # database would join our batches and break the counts. Rolled back
        # with the rest of the transaction.
        cls.env['product.template'].search(
            [('metabooks_export_pending', '=', True)]
        ).action_metabooks_clear_pending()

        cls.availability = cls.env['metabooks.avalaibility.definition'].create({
            'identify_number': '21',
            'product_definition': 'Disponível',
        })
        cls.role_author = cls.env['author.contributor.role'].search(
            [('name', '=', 'A01')], limit=1)
        if not cls.role_author:
            cls.role_author = cls.env['author.contributor.role'].create(
                {'name': 'A01'})
        cls.author = cls.env['metabooks.auther.publiser'].create({
            'name': 'Augusto da',
            'author_last_name': 'Silva',
            'author_contributor_role': cls.role_author.id,
        })
        cls.book = cls.env['product.template'].create({
            'name': 'O Cortiço',
            'barcode': '9788599296264',
            'list_price': 59.90,
            'metabooks_vendor_id': 'BR0089701',
            'metabooks_book_title': 'O Cortiço',
            'metabooks_page_count': 300,
            'metabooks_ncm': '4901.99.00',
            'metabooks_publish_date': date(2020, 5, 1),
            'metabooks_product_availability': cls.availability.id,
            'book_auther_ids': [(6, 0, cls.author.ids)],
        })
        # A book Metabooks already knows: that is what makes it a V (update)
        # rather than a Z (new title), and it is the cut-off for the history.
        cls.book.with_context(metabooks_from_sync=True).write({
            'metabooks_export_pending': False,
            'metabooks_export_pending_since': False,
            'metabooks_export_last': fields.Datetime.now() - timedelta(days=30),
            'metabooks_export_last_track': _max_track(cls.env),
        })
        # A book that came from Metabooks and was never sent from here -- the
        # state every one of the 210 imported titles is actually in.
        cls.imported = cls.env['product.template'].create({
            'name': 'Livro importado',
            'barcode': '9780000007771',
            'list_price': 30.0,
            'metabooks_vendor_id': 'BR0089701',
            'metabooks_book_title': 'Livro importado',
        })
        # The connector creates it under metabooks_from_sync, so it arrives
        # already settled -- nothing to tell them, they are where it came from.
        cls.imported.action_metabooks_clear_pending()
        cls._settle(cls.env)

    def _batch(self):
        return self.env['metabooks.export.batch'].create({})

    @classmethod
    def _settle(cls, env=None):
        """Close the books on the current transaction's tracking.

        Odoo writes tracking values from a precommit callback and keeps one set
        of "initial values" per record per transaction. In real use a book is
        created in one request and edited in another, so an edit is compared
        against the stored record. In a test everything shares a transaction:
        without settling in between, an edit is compared against the record as
        it was created, and the before/after comes out blank.
        """
        env = env or cls.env
        env.flush_all()
        env.cr.precommit.run()

    def _edit(self, records=None, **vals):
        """Edit a book the way the chatter will actually see it."""
        (records or self.book).write(vals)
        self._settle(self.env)

    # ------------------------------------------------------------------ #
    #  The queue
    # ------------------------------------------------------------------ #

    def test_editing_a_mapped_field_queues_the_book(self):
        self.book.metabooks_book_title = 'O Cortiço (edição comentada)'
        self.assertTrue(self.book.metabooks_export_pending)
        self.assertTrue(self.book.metabooks_export_pending_since)

    def test_peso_digitado_aqui_vai_para_a_planilha(self):
        """Peso é digitado em quilo no Odoo; a planilha pede grama.

        Sem o espelho, o número ficava em casa — e a Metabooks seguia sem
        peso justamente nos livros em que só nós temos.
        """
        self.book.weight = 0.42

        self.assertAlmostEqual(self.book.metabooks_weight, 420.0, places=2)
        self.assertTrue(self.book.metabooks_export_pending,
                        "peso novo é mudança que a Metabooks precisa receber")

    def test_peso_do_painel_chega_ao_campo_do_odoo(self):
        """O caminho de volta do espelho: quem digita no painel (gramas)
        espera que o livro passe a ter peso — e é o campo do Odoo (quilos)
        que o estoque soma e a nota declara."""
        self.book.metabooks_weight = 529.0

        # 0,53 e não 0,529: o campo do Odoo é arredondado pela precisão
        # decimal "Stock Weight", que a casa deixa em duas casas.
        self.assertAlmostEqual(self.book.weight, 0.53, places=2)

    def test_peso_do_metabooks_nao_e_sobrescrito_pelo_espelho(self):
        """Quem manda no par é o valor explícito: o sync escreve os dois."""
        self.book.with_context(metabooks_from_sync=True).write({
            'weight': 0.3, 'metabooks_weight': 305.0})
        self.assertAlmostEqual(self.book.metabooks_weight, 305.0, places=2)

    def test_zerar_o_painel_nao_apaga_o_peso_do_odoo(self):
        self.book.weight = 0.4
        self.book.metabooks_weight = 0.0
        self.assertAlmostEqual(self.book.weight, 0.4, places=3)

    def test_zerar_o_peso_nao_apaga_o_catalogo(self):
        self.book.with_context(metabooks_from_sync=True).write(
            {'metabooks_weight': 300.0})
        self.book.weight = 0.0
        self.assertAlmostEqual(self.book.metabooks_weight, 300.0, places=2)

    def test_editing_an_unmapped_field_leaves_the_book_alone(self):
        # description_sale is not a Metabooks column, so there is nothing to
        # send and queueing the book would be a false promise.
        self.book.description_sale = 'texto interno'
        self.assertFalse(self.book.metabooks_export_pending)

    def test_import_from_metabooks_does_not_queue_the_book(self):
        """The echo guard: their own data must not bounce back at them."""
        self.book.with_context(metabooks_from_sync=True).write(
            {'metabooks_book_title': 'Título vindo da Metabooks'})
        self.assertFalse(self.book.metabooks_export_pending)

    def test_clearing_pending_by_hand(self):
        self.book.metabooks_page_count = 310
        self.assertTrue(self.book.metabooks_export_pending)
        self.book.action_metabooks_clear_pending()
        self.assertFalse(self.book.metabooks_export_pending)

    # ------------------------------------------------------------------ #
    #  Gathering the diff
    # ------------------------------------------------------------------ #

    def test_prepare_records_before_and_after(self):
        self._edit(metabooks_page_count=320)

        batch = self._batch()
        batch.action_prepare()

        self.assertEqual(len(batch.line_ids), 1)
        line = batch.line_ids
        self.assertEqual(line.gtin, '9788599296264')
        self.assertEqual(batch.mb_id, 'BR0089701')

        pages = line.change_ids.filtered(
            lambda c: c.column == 'Número de páginas')
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages.old_value, '300')
        self.assertEqual(pages.new_value, '320')

    def test_prepare_only_brings_what_changed(self):
        self._edit(metabooks_page_count=320)

        batch = self._batch()
        batch.action_prepare()

        columns = set(batch.change_ids.mapped('column'))
        self.assertEqual(columns, {'Número de páginas'},
                         "a book that only changed its page count should not "
                         "carry its whole record")

    def test_several_edits_collapse_to_first_and_last(self):
        """A -> B -> C is reported as A -> C: that is what they need to know."""
        self._edit(metabooks_book_title='Segundo título')
        self._edit(metabooks_book_title='Terceiro título')

        batch = self._batch()
        batch.action_prepare()
        change = batch.change_ids.filtered(lambda c: c.column == 'Título')
        self.assertEqual(change.old_value, 'O Cortiço')
        self.assertEqual(change.new_value, 'Terceiro título')

    def test_a_second_round_carries_only_the_new_change(self):
        """Where the history cut-off earns its keep.

        Reading the history from a timestamp lost this: mail.message.date only
        resolves to the second, so an edit landing in the same second as the
        send it followed looked older than that send, no history was found, and
        the fallback quietly sent every mapped column instead of the one that
        moved.
        """
        self._edit(metabooks_page_count=320)
        first = self._batch()
        first.action_prepare()
        first.action_generate()
        first.action_mark_sent()

        self._edit(metabooks_book_title='Título novo')
        second = self._batch()
        second.action_prepare()

        self.assertFalse(second.line_ids.no_history)
        self.assertEqual(set(second.change_ids.mapped('column')), {'Título'})
        change = second.change_ids
        self.assertEqual(change.old_value, 'O Cortiço')
        self.assertEqual(change.new_value, 'Título novo')

    def test_a_book_metabooks_already_has_is_an_update(self):
        """It carries their publisher id, so they have it -- even though we
        have never sent it. Asking "did we send it?" instead emptied the first
        update batch of the whole catalogue."""
        self.assertFalse(self.imported.metabooks_export_last)
        self._edit(self.imported, list_price=32.0)

        batch = self._batch()
        batch.action_prepare()
        self.assertIn(self.imported, batch.line_ids.product_id)

    def test_a_book_only_we_know_is_a_new_title(self):
        home_grown = self.env['product.template'].create({
            'name': 'Nosso', 'barcode': '9788599296266', 'list_price': 10.0})
        self._settle(self.env)
        self._edit(home_grown, list_price=12.0)
        self._edit(metabooks_page_count=320)   # a known book, so V is not empty

        update = self._batch()
        update.action_prepare()
        self.assertNotIn(home_grown, update.line_ids.product_id)

        new = self.env['metabooks.export.batch'].create({'task': sheet.TASK_NEW})
        new.action_prepare()
        self.assertIn(home_grown, new.line_ids.product_id)

    def test_unticking_one_change_keeps_the_book_and_drops_the_column(self):
        self._edit(metabooks_page_count=320, synopsys='Sinopse nova')
        batch = self._batch()
        batch.action_prepare()
        self.assertEqual(len(batch.change_ids), 2)

        batch.change_ids.filtered(lambda c: c.column == 'Sinopse').selected = False
        batch.action_generate()

        page = openpyxl.load_workbook(
            io.BytesIO(batch.attachment_id.raw)).active
        headers = [c.value for c in page[1]]
        self.assertIn('Número de páginas', headers)
        self.assertNotIn('Sinopse', headers,
                         "an unticked column must not be written at all -- a "
                         "column Metabooks does not receive it leaves alone")

    def test_a_value_edited_and_put_back_is_not_a_change(self):
        self._edit(list_price=99.0)
        self._edit(list_price=59.90)
        self._edit(metabooks_page_count=320)

        batch = self._batch()
        batch.action_prepare()
        self.assertEqual(set(batch.change_ids.mapped('column')),
                         {'Número de páginas'},
                         "the chatter remembers the round trip; Metabooks has "
                         "nothing to learn from it")

    def test_html_is_stripped_from_text(self):
        """The website editor writes into synopsys too, and their column is
        plain text -- a <div> would reach readers as literal markup."""
        self._edit(synopsys='<div data-oe-version="2.0">Um vilarejo.</div>')
        self.assertEqual(self.book._metabooks_cell('Sinopse'), 'Um vilarejo.')

    def test_plain_text_with_an_angle_bracket_survives(self):
        self._edit(synopsys='Sobre matemática: 3 < 5 e afins')
        self.assertEqual(self.book._metabooks_cell('Sinopse'),
                         'Sobre matemática: 3 < 5 e afins')

    def test_nothing_pending_is_an_error_not_an_empty_file(self):
        batch = self._batch()
        with self.assertRaises(UserError):
            batch.action_prepare()

    # ------------------------------------------------------------------ #
    #  Checking
    # ------------------------------------------------------------------ #

    def test_check_rejects_a_short_isbn(self):
        self._edit(metabooks_page_count=320)
        batch = self._batch()
        batch.action_prepare()
        batch.line_ids.gtin = '123'
        with self.assertRaises(UserError):
            batch.action_check()

    def test_check_rejects_two_books_with_the_same_isbn(self):
        twin = self.book.copy({'name': 'Cópia', 'barcode': '9788599296265'})
        twin.with_context(metabooks_from_sync=True).write({
            'metabooks_export_pending': False,
            'metabooks_export_last': fields.Datetime.now() - timedelta(days=30),
            'metabooks_export_last_track': _max_track(self.env),
        })
        self._settle(self.env)
        self._edit(self.book | twin, metabooks_page_count=321)

        batch = self._batch()
        batch.action_prepare()
        batch.line_ids[1].gtin = batch.line_ids[0].gtin
        with self.assertRaises(UserError):
            batch.action_check()

    def test_clearing_a_field_is_refused_not_silently_dropped(self):
        """A blank cell means "leave this alone" to Metabooks.

        So a field cleared in Odoo would reach them as no change at all, and the
        batch would report success over a change that never happened.
        """
        self._edit(metabooks_keywords='literatura, brasil')
        first = self._batch()
        first.action_prepare()
        first.action_generate()
        first.action_mark_sent()

        self._edit(metabooks_keywords=False)
        batch = self._batch()
        batch.action_prepare()
        with self.assertRaises(UserError):
            batch.action_check()
        with self.assertRaises(UserError):
            batch.action_generate()

    def test_generate_revalidates_an_already_checked_batch(self):
        self._edit(metabooks_page_count=320)
        batch = self._batch()
        batch.action_prepare()
        batch.action_check()
        batch.line_ids.gtin = '123'
        with self.assertRaises(UserError):
            batch.action_generate()

    def test_check_passes_and_moves_state(self):
        self._edit(metabooks_page_count=320)
        batch = self._batch()
        batch.action_prepare()
        batch.action_check()
        self.assertEqual(batch.state, 'checked')

    # ------------------------------------------------------------------ #
    #  The spreadsheet
    # ------------------------------------------------------------------ #

    def test_generated_sheet_carries_the_change_in_red(self):
        self._edit(metabooks_page_count=320)

        batch = self._batch()
        batch.action_prepare()
        batch.action_generate()

        self.assertEqual(batch.state, 'generated')
        self.assertTrue(batch.attachment_id)
        self.assertEqual(
            batch.filename,
            'V_BR0089701_%s_Alteracoes.xlsx' % date.today().strftime('%Y%m%d'))

        book = openpyxl.load_workbook(
            io.BytesIO(batch.attachment_id.raw))
        page = book.active
        headers = [c.value for c in page[1]]

        # Only what a human needs to read the row, plus what changed. Not 74
        # columns of blank.
        self.assertEqual(headers, ['GTIN', 'Título', 'Número de páginas'])

        row = {h: page.cell(row=2, column=i + 1)
               for i, h in enumerate(headers)}
        self.assertEqual(row['GTIN'].value, '9788599296264')
        self.assertEqual(row['Número de páginas'].value, 320)

        # The point of the exercise: changed cells stand out, the anchor does not.
        self.assertIn('B00020', _font_rgb(row['Número de páginas']))
        self.assertNotIn('B00020', _font_rgb(row['Título']))
        self.assertNotIn('B00020', _font_rgb(row['GTIN']))

    def test_dates_go_in_as_dates_not_text(self):
        """Their own template carries 44545, an Excel serial."""
        self._edit(metabooks_publish_date=date(2021, 3, 15))

        batch = self._batch()
        batch.action_prepare()
        batch.action_generate()

        page = openpyxl.load_workbook(
            io.BytesIO(batch.attachment_id.raw)).active
        headers = [c.value for c in page[1]]
        col = headers.index('Data de publicação') + 1
        self.assertEqual(page.cell(row=2, column=col).value.date(),
                         date(2021, 3, 15))

    def test_author_is_surname_first(self):
        self.assertEqual(self.book._metabooks_cell('Autor'),
                         'Silva, Augusto da')

    def test_availability_goes_as_its_label(self):
        self.assertEqual(self.book._metabooks_cell('Status de disponibilidade'),
                         'Disponível')

    # ------------------------------------------------------------------ #
    #  Delivery
    # ------------------------------------------------------------------ #

    def test_book_leaves_the_queue_only_once_marked_sent(self):
        self._edit(metabooks_page_count=320)

        batch = self._batch()
        batch.action_prepare()
        batch.action_generate()
        self.assertTrue(
            self.book.metabooks_export_pending,
            "generating a file is not delivering it -- an upload can fail")

        batch.action_mark_sent()
        self.assertEqual(batch.state, 'sent')
        self.assertFalse(self.book.metabooks_export_pending)
        self.assertTrue(self.book.metabooks_export_last)

    def test_unselected_books_stay_in_the_queue(self):
        twin = self.book.copy({'name': 'Cópia', 'barcode': '9788599296265'})
        twin.with_context(metabooks_from_sync=True).write({
            'metabooks_export_pending': False,
            'metabooks_export_last': fields.Datetime.now() - timedelta(days=30),
            'metabooks_export_last_track': _max_track(self.env),
        })
        self._settle(self.env)
        self._edit(self.book | twin, metabooks_page_count=321)

        batch = self._batch()
        batch.action_prepare()
        dropped = batch.line_ids.filtered(lambda l: l.product_id == twin)
        dropped.selected = False
        batch.action_generate()
        batch.action_mark_sent()

        self.assertFalse(self.book.metabooks_export_pending)
        self.assertTrue(twin.metabooks_export_pending,
                        "a book left unchecked was never sent, so it must stay")

    def test_a_sent_batch_is_frozen(self):
        self._edit(metabooks_page_count=320)
        batch = self._batch()
        batch.action_prepare()
        batch.action_generate()
        batch.action_mark_sent()
        with self.assertRaises(UserError):
            batch.action_reset()
        with self.assertRaises(UserError):
            batch.action_cancel()

    def test_history_survives_the_book_changing_again(self):
        self._edit(metabooks_page_count=320)
        batch = self._batch()
        batch.action_prepare()
        batch.action_generate()
        batch.action_mark_sent()

        self._edit(metabooks_page_count=999)

        change = batch.change_ids.filtered(
            lambda c: c.column == 'Número de páginas')
        self.assertEqual(change.new_value, '320',
                         "the log records what we sent, not what the book "
                         "happens to say later")


@tagged('post_install', '-at_install')
class TestMetabooksSheet(TransactionCase):
    """The file format on its own -- no products involved."""

    def test_filename_follows_the_2025_guide(self):
        name = sheet.build_filename(
            sheet.TASK_NEW, 'BR5108985', date(2025, 3, 20), 'Novos Títulos')
        self.assertEqual(name, 'Z_BR5108985_20250320_NovosTitulos.xlsx')

    def test_filename_rejects_an_unknown_task(self):
        with self.assertRaises(ValueError):
            sheet.build_filename('Q', 'BR1', date(2025, 1, 1), 'x')

    def test_unknown_column_is_refused(self):
        with self.assertRaises(ValueError):
            sheet.write_workbook(
                [{'values': {'Coluna Inventada': 'x'}, 'changed': set()}])

    def test_mandatory_columns_are_all_real_columns(self):
        self.assertEqual(set(sheet.MANDATORY) - set(sheet.COLUMNS), set())

    def test_workbook_is_a_valid_xlsx_with_one_sheet(self):
        data = sheet.write_workbook([{
            'values': {'GTIN': '9788599296264', 'Título': 'Um livro'},
            'changed': {'Título'},
        }])
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(data)))
        book = openpyxl.load_workbook(io.BytesIO(data))
        self.assertEqual(book.sheetnames, ['Planilha1'])

    def test_all_columns_emits_the_full_template(self):
        data = sheet.write_workbook(
            [{'values': {'GTIN': '1'}, 'changed': set()}], all_columns=True)
        page = openpyxl.load_workbook(io.BytesIO(data)).active
        self.assertEqual([c.value for c in page[1]], list(sheet.COLUMNS))


@tagged('post_install', '-at_install')
class TestMetabooksUniversoDosLivros(TestMetabooksExport):
    """Quem entra na fila, e o que conta como campo apagado.

    Duas coisas que a tela do prod mostrou no mesmo dia (01/09/2026): o lote
    trazia pseudo-produtos do plano de contas, e travava inteiro por um preço
    que ninguém havia apagado.
    """

    def _conta_administrativa(self):
        """ADM0006 "(-) Impostos": produto de verdade, livro nenhum."""
        return self.env['product.template'].create({
            'name': '(-) Impostos :: Ordinários',
            'default_code': 'ADM0006',
            'list_price': 0.0,
        })

    # ------------------------------------------------------------------ #
    #  O universo é o dos livros
    # ------------------------------------------------------------------ #

    def test_produto_sem_isbn_nao_entra_na_fila(self):
        conta = self._conta_administrativa()
        conta.action_metabooks_clear_pending()
        conta.list_price = 1234.0
        self.assertFalse(
            conta.metabooks_export_pending,
            "mexer no preço de uma conta contábil não é assunto da Metabooks")

    def test_livro_continua_entrando_na_fila(self):
        """O caminho feliz não pode ter sido fechado junto."""
        self.book.action_metabooks_clear_pending()
        self.book.list_price = 79.90
        self.assertTrue(self.book.metabooks_export_pending)

    def test_isbn_na_referencia_interna_ainda_e_livro(self):
        """Título vindo do legado traz o ISBN em `default_code`, sem barcode."""
        legado = self.env['product.template'].create({
            'name': 'Título do legado',
            'default_code': '9788599296271',
            'list_price': 40.0,
        })
        legado.action_metabooks_clear_pending()
        legado.list_price = 45.0
        self.assertTrue(legado.metabooks_export_pending)

    def test_pendencia_antiga_de_nao_livro_nao_entra_no_lote(self):
        """A marca pode ser anterior ao portão; o lote filtra de novo."""
        conta = self._conta_administrativa()
        conta.with_context(metabooks_from_sync=True).write({
            'metabooks_export_pending': True,
            'metabooks_export_pending_since': fields.Datetime.now(),
        })
        self._edit(metabooks_book_title='O Cortiço (2ª edição)')
        batch = self._batch()
        batch.action_prepare()
        self.assertNotIn(
            conta, batch.line_ids.product_id,
            "conta contábil marcada de véspera não pode viajar no lote")
        self.assertIn(self.book, batch.line_ids.product_id)

    # ------------------------------------------------------------------ #
    #  Nunca preenchido não é apagado
    # ------------------------------------------------------------------ #

    def _livro_sem_preco(self):
        """Nasce com o 1,00 de fábrica do Odoo e é zerado depois."""
        livro = self.env['product.template'].create({
            'name': 'Ocupar a psicanálise',
            'barcode': '9786561190305',
            'metabooks_vendor_id': 'BR0089701',
        })
        livro.action_metabooks_clear_pending()
        self._settle(self.env)
        self._edit(records=livro, list_price=0.0)
        return livro

    def test_preco_nunca_preenchido_nasce_desmarcado(self):
        livro = self._livro_sem_preco()
        batch = self._batch()
        batch.action_prepare()
        preco = batch.line_ids.change_ids.filtered(
            lambda c: c.product_id == livro and c.column == 'R$')
        self.assertTrue(preco, "a alteração deve aparecer, para ser vista")
        self.assertTrue(preco.never_filled)
        self.assertFalse(
            preco.selected,
            "o 1,00 de fábrica não é valor da casa: fora do envelope")

    def test_preco_nunca_preenchido_nao_trava_o_lote(self):
        """Era exatamente isto que barrava o MBX/2026/0001 no prod.

        Lá os dois livros tinham outras alterações de verdade; só o preço
        fantasma derrubava a remessa inteira.
        """
        livro = self._livro_sem_preco()
        self._edit(records=livro, metabooks_book_title='Ocupar a psicanálise')
        batch = self._batch()
        batch.action_prepare()
        batch.action_check()
        self.assertEqual(batch.state, 'checked')
        self.assertNotIn(
            'R$', batch.line_ids.change_ids.filtered('selected').mapped('column'),
            "o preço fantasma fica de fora do que é enviado")

    def test_livro_so_com_o_fantasma_e_avisado_como_linha_vazia(self):
        """Nada a dizer à Metabooks é outra recusa, e é a honesta.

        Sem nenhuma alteração de verdade, o livro não tem por que viajar --
        e a mensagem tem de ser essa, não a do marcador de exclusão.
        """
        self._livro_sem_preco()
        batch = self._batch()
        batch.action_prepare()
        with self.assertRaises(UserError) as erro:
            batch.action_check()
        self.assertIn('the row would be empty', str(erro.exception))
        self.assertNotIn('deletion marker', str(erro.exception))

    def test_preco_realmente_apagado_ainda_trava(self):
        """Caso de erro: valor da casa apagado continua sendo recusado."""
        self._edit(list_price=0.0)     # o Cortiço valia 59,90
        batch = self._batch()
        batch.action_prepare()
        preco = batch.line_ids.change_ids.filtered(
            lambda c: c.product_id == self.book and c.column == 'R$')
        self.assertFalse(preco.never_filled)
        self.assertTrue(preco.selected)
        with self.assertRaises(UserError) as erro:
            batch.action_check()
        self.assertIn('deletion marker', str(erro.exception))

    def test_a_recusa_de_nunca_preenchido_diz_o_remedio_certo(self):
        """Se o operador marcar mesmo assim, a mensagem não mente."""
        livro = self._livro_sem_preco()
        batch = self._batch()
        batch.action_prepare()
        batch.line_ids.change_ids.filtered(
            lambda c: c.product_id == livro and c.column == 'R$'
        ).selected = True
        with self.assertRaises(UserError) as erro:
            batch.action_check()
        self.assertIn('never filled in', str(erro.exception))
        self.assertNotIn('deletion marker', str(erro.exception))


@tagged('post_install', '-at_install')
class TestMetabooksClassificacao(TestMetabooksExport):
    """Thema e BISAC: a lista existe, é lida deles, e viaja como código."""

    def test_as_duas_listas_estao_carregadas(self):
        Thema = self.env['metabooks.thema.code']
        self.assertGreater(Thema.search_count([('kind', '=', 'category')]), 3000)
        self.assertGreater(Thema.search_count([('kind', '=', 'qualifier')]), 5000)
        self.assertGreater(
            self.env['biblio.bisac.codes'].search_count([]), 5000,
            "a tabela BISAC vazia é o que deixava o campo sem opção na tela")

    def test_o_codigo_do_livro_1964_existe_nas_duas(self):
        """Os códigos que a Metabooks mostra para 9788577154036."""
        thema = self.env['metabooks.thema.code'].search([('code', '=', 'NHK')])
        self.assertEqual(thema.kind, 'category')
        bisac = self.env['biblio.bisac.codes'].search(
            [('bisac_code', '=', 'HIS033000')])
        self.assertTrue(bisac)
        self.assertIn(thema, bisac.thema_code_ids,
                      "a equivalência oficial da EDItEUR liga HIS033000 a NHK")

    def test_qualificador_conhece_o_seu_grupo(self):
        lugar = self.env['metabooks.thema.code'].search([('code', '=', '1KBB')])
        self.assertEqual(lugar.kind, 'qualifier')
        self.assertEqual(lugar.qualifier_kind, 'place')

    def test_o_pai_se_resolve_pelo_codigo(self):
        """Borda: 9.187 linhas entram numa ordem em que o pai nem sempre existe."""
        filho = self.env['metabooks.thema.code'].search([('code', '=', '1DDF-FR-XE')])
        self.assertTrue(filho, "código com hífen tem de entrar")
        self.assertEqual(filho.parent_id.code, filho.parent_code)

    def test_a_planilha_leva_o_codigo_e_nao_a_ementa(self):
        thema = self.env['metabooks.thema.code'].search([('code', '=', 'NHK')])
        quals = self.env['metabooks.thema.code'].search(
            [('code', 'in', ['1KBB', '3MPB'])])
        self._edit(metabooks_thema_id=thema.id,
                   metabooks_thema_ids=[(6, 0, thema.ids)],
                   metabooks_thema_qualifier_ids=[(6, 0, quals.ids)])
        self.assertEqual(self.book._metabooks_cell('Categoria Thema'), 'NHK')
        self.assertEqual(
            self.book._metabooks_cell('Qualificador Thema'), '1KBB;3MPB')

    def test_o_principal_sai_na_frente_e_uma_vez_so(self):
        """Uma coluna, ponto e vírgula, principal primeiro -- é o manual deles.

        A ordem é o que faz o painel deles saber qual é a Classificação
        principal, e o principal também está na lista: não pode sair duas vezes.
        """
        principal = self.env['metabooks.thema.code'].search([('code', '=', 'NHK')])
        outra = self.env['metabooks.thema.code'].search([('code', '=', 'JBSF')])
        self._edit(metabooks_thema_id=principal.id,
                   metabooks_thema_ids=[(6, 0, (outra | principal).ids)])
        self.assertEqual(
            self.book._metabooks_cell('Categoria Thema'), 'NHK;JBSF')

    def test_bisac_tem_a_mesma_forma(self):
        Bisac = self.env['biblio.bisac.codes']
        principal = Bisac.search([('bisac_code', '=', 'HIS033000')])
        outro = Bisac.search([('bisac_code', '=', 'HIS000000')])
        self._edit(bisac_code=principal.id,
                   bisac_code_ids=[(6, 0, (outro | principal).ids)])
        self.assertEqual(
            self.book._metabooks_cell('BISAC'), 'HIS033000;HIS000000')

    def test_editar_so_o_principal_marca_o_livro(self):
        """Borda: `bisac_code` não tem linha no mapa, e mesmo assim é vigiado."""
        self.book.action_metabooks_clear_pending()
        principal = self.env['biblio.bisac.codes'].search(
            [('bisac_code', '=', 'HIS033000')])
        self.book.bisac_code = principal.id
        self.assertTrue(self.book.metabooks_export_pending)

    def test_o_sync_le_os_esquemas_10_e_93(self):
        """Era o buraco: só o esquema 20 era lido, e os outros dois caíam fora."""
        vals = self.env['metabooks.connector']._classificacao([
            {'subjectSchemeIdentifier': '20', 'subjectHeadingText': 'Política'},
            {'subjectSchemeIdentifier': '10', 'subjectCode': 'HIS033000'},
            {'subjectSchemeIdentifier': '93', 'subjectCode': 'NHK',
             'mainSubject': True},
            {'subjectSchemeIdentifier': '93', 'subjectCode': '1KBB'},
        ])
        thema = self.env['metabooks.thema.code'].search([('code', '=', 'NHK')])
        lugar = self.env['metabooks.thema.code'].search([('code', '=', '1KBB')])
        bisac = self.env['biblio.bisac.codes'].search(
            [('bisac_code', '=', 'HIS033000')])
        self.assertEqual(vals['metabooks_thema_id'], thema.id,
                         "mainSubject=True manda no principal")
        self.assertEqual(vals['metabooks_thema_ids'], [(6, 0, [thema.id])])
        self.assertEqual(vals['metabooks_thema_qualifier_ids'], [(6, 0, [lugar.id])])
        self.assertEqual(vals['bisac_code_ids'], [(6, 0, [bisac.id])])
        self.assertEqual(vals['bisac_code'], bisac.id)

    def test_codigo_fora_da_lista_e_ignorado(self):
        """Erro: código que não existe no padrão não vira linha nova."""
        vals = self.env['metabooks.connector']._classificacao([
            {'subjectSchemeIdentifier': '93', 'subjectCode': 'ZZZINVENTADO'},
        ])
        self.assertEqual(vals, {})
        self.assertFalse(self.env['metabooks.thema.code'].search(
            [('code', '=', 'ZZZINVENTADO')]))


@tagged('post_install', '-at_install')
class TestMetabooksCorteDoHistorico(TestMetabooksExport):
    """O que veio deles não volta para eles.

    `metabooks_export_last_track` só era carimbado quando um lote saía, e livro
    importado nunca saiu daqui — então o corte ficava em zero e a planilha
    propunha devolver a biografia inteira do registro. No 1964, 16 das 19
    alterações eram exatamente isso.
    """

    def _livro_importado(self):
        livro = self.env['product.template'].create({
            'name': '1964',
            'barcode': '9788577154036',
            'metabooks_vendor_id': 'BR0089701',
        })
        livro.action_metabooks_clear_pending()
        self._settle(self.env)
        return livro

    def test_o_sync_carimba_o_corte(self):
        livro = self._livro_importado()
        self.assertEqual(livro.metabooks_export_last_track, 0)
        livro.with_context(metabooks_from_sync=True).write({
            'metabooks_page_count': 420,
            'metabooks_weight': 515.0,
            'synopsys': 'Reúne textos e depoimentos inéditos.',
        })
        self._settle(self.env)
        self.assertGreater(
            livro.metabooks_export_last_track, 0,
            "o que a Metabooks escreveu aqui tem de cair atrás do corte")

    def test_o_que_veio_deles_nao_entra_no_lote(self):
        livro = self._livro_importado()
        livro.with_context(metabooks_from_sync=True).write({
            'metabooks_page_count': 420,
            'metabooks_weight': 515.0,
            'synopsys': 'Reúne textos e depoimentos inéditos.',
        })
        self._settle(self.env)
        # Marcada à mão porque o sync, de propósito, não enfileira.
        livro.with_context(metabooks_from_sync=True).write({
            'metabooks_export_pending': True,
            'metabooks_export_pending_since': fields.Datetime.now(),
        })
        batch = self._batch()
        batch.action_prepare()
        linha = batch.line_ids.filtered(lambda l: l.product_id == livro)
        colunas = set(linha.change_ids.mapped('column'))
        self.assertFalse(
            colunas & {'Número de páginas', 'Peso', 'Sinopse'},
            "a ficha técnica que eles nos deram não volta para eles")

    def test_edicao_da_casa_depois_do_sync_continua_valendo(self):
        """O corte não pode calar a casa: é o caminho feliz do conserto."""
        livro = self._livro_importado()
        livro.with_context(metabooks_from_sync=True).write(
            {'metabooks_page_count': 420})
        self._settle(self.env)
        # Palavra-chave, e não Série: a coluna Série só sai com o código deles,
        # então uma coleção nossa não produziria mudança nenhuma aqui.
        self._edit(records=livro, metabooks_keywords='cordel')
        batch = self._batch()
        batch.action_prepare()
        linha = batch.line_ids.filtered(lambda l: l.product_id == livro)
        self.assertEqual(
            set(linha.change_ids.mapped('column')), {'Palavra-chave'},
            "só a edição feita depois do sync tem notícia para eles")


@tagged('post_install', '-at_install')
class TestClassificarPorISBN(TestMetabooksExport):
    """`classify_isbns` escreve a classificação e nada mais."""

    RESPOSTA = {
        'subjects': [
            {'subjectSchemeIdentifier': '20', 'subjectHeadingText': 'Política'},
            {'subjectSchemeIdentifier': '10', 'subjectCode': 'HIS033000'},
            {'subjectSchemeIdentifier': '93', 'subjectCode': 'NHK',
             'mainSubject': True},
            {'subjectSchemeIdentifier': '93', 'subjectCode': '1KBB'},
        ],
        # o que NÃO pode ser escrito por este caminho
        'titles': [{'title': 'Título deles'}],
        'prices': [{'priceType': '02', 'priceAmount': 1.0}],
    }

    def _rodar(self, resposta=None):
        conector = self.env['metabooks.connector']
        with patch.object(type(conector), '_get_client') as get_client:
            get_client.return_value.get_product_by_isbn.return_value = (
                self.RESPOSTA if resposta is None else resposta)
            return conector.classify_isbns([self.book.barcode])

    def test_escreve_bisac_e_thema(self):
        res = self._rodar()
        self.assertEqual(res['classified'], 1)
        self.assertEqual(self.book.metabooks_thema_id.code, 'NHK')
        self.assertEqual(self.book.metabooks_thema_ids.mapped('code'), ['NHK'])
        self.assertEqual(
            self.book.metabooks_thema_qualifier_ids.mapped('code'), ['1KBB'])
        self.assertEqual(self.book.bisac_code.bisac_code, 'HIS033000')
        self.assertEqual(
            self.book.bisac_code_ids.mapped('bisac_code'), ['HIS033000'])

    def test_traz_as_palavras_chave(self):
        self._rodar()
        self.assertEqual(self.book.metabooks_keywords, 'Política')

    def test_sem_palavra_chave_nao_apaga_as_da_casa(self):
        """Borda: ausência não é ordem de apagar, aqui também."""
        self._edit(metabooks_keywords='1964, Ditadura militar')
        self._rodar({'subjects': [
            {'subjectSchemeIdentifier': '93', 'subjectCode': 'NHK',
             'mainSubject': True}]})
        self.assertEqual(self.book.metabooks_keywords, '1964, Ditadura militar')

    def test_nao_toca_na_colecao(self):
        """Pedido explícito de 03/09: coleção fica de fora desta varredura."""
        self._edit(metabooks_collections='Hedra Edições')
        self._rodar({'subjects': [
            {'subjectSchemeIdentifier': '93', 'subjectCode': 'NHK'}],
            'collection': 'Outra coisa'})
        self.assertEqual(self.book.metabooks_collections, 'Hedra Edições')

    def test_nao_toca_no_editorial(self):
        """O motivo de existir: reimportar traria título e preço por cima."""
        titulo, preco = self.book.metabooks_book_title, self.book.list_price
        self._rodar()
        self.assertEqual(self.book.metabooks_book_title, titulo)
        self.assertEqual(self.book.list_price, preco)

    def test_nao_enfileira_o_livro_de_volta(self):
        """O que veio deles não volta para eles."""
        self.book.action_metabooks_clear_pending()
        self._rodar()
        self.assertFalse(self.book.metabooks_export_pending)
        self.assertGreater(self.book.metabooks_export_last_track, 0)

    def test_sem_subjects_o_livro_e_pulado(self):
        """Erro/borda: ausência não é ordem de apagar."""
        thema = self.env['metabooks.thema.code'].search([('code', '=', 'NHK')])
        self._edit(metabooks_thema_id=thema.id)
        res = self._rodar({'titles': [{'title': 'sem assunto'}]})
        self.assertEqual(res['classified'], 0)
        self.assertEqual(res['no_subjects'], [self.book.barcode])
        self.assertEqual(self.book.metabooks_thema_id, thema,
                         'a classificação da casa foi apagada por silêncio')


@tagged('post_install', '-at_install')
class TestVazioNaoEDois(TestMetabooksExport):
    """Texto vazio é `False`, nunca `''`.

    Agrupar o kanban pela Coleção derrubava a tela com
    `OwlError: Got duplicate key in t-foreach`. O Odoo devolve um grupo para o
    NULL e outro para a string vazia, e os dois chegam ao `t-foreach` com a
    mesma chave. Owl recusa chave repetida, e tem razão: são o mesmo "vazio".
    """

    CAMPOS = ('metabooks_collections', 'metabooks_book_subtitle',
              'synopsys', 'metabooks_keywords')

    def test_o_feed_sem_serie_nao_grava_string_vazia(self):
        parsed = self.env['metabooks.connector']._parse_feed({
            'isbn': '9788599296288', 'title': 'Livro sem série',
        })
        for campo in self.CAMPOS:
            self.assertNotEqual(
                parsed['vals'].get(campo), '',
                '%s saiu como string vazia; vazio no Odoo é False' % campo)

    def test_o_onix_sem_subtitulo_nao_grava_string_vazia(self):
        parsed = self.env['metabooks.connector']._parse_onix({
            'identifiers': [{'productIdentifierType': '03',
                             'idValue': '9788599296295'}],
            'titles': [{'title': 'Só título'}],
        })
        for campo in self.CAMPOS:
            self.assertNotEqual(
                parsed['vals'].get(campo), '',
                '%s saiu como string vazia; vazio no Odoo é False' % campo)

    def test_agrupar_por_colecao_da_um_grupo_vazio_so(self):
        """O que a tela faz: dois livros sem série, um grupo só.

        Este é o teste que fecha o buraco de verdade -- os outros dois olham
        quem escreve, este olha o que o kanban recebe.
        """
        comum = {'metabooks_vendor_id': 'BR0089701'}
        self.env['product.template'].create([
            dict(comum, name='Sem série A', barcode='9788599296301',
                 metabooks_collections=False),
            dict(comum, name='Sem série B', barcode='9788599296318',
                 metabooks_collections=''),
        ])
        grupos = self.env['product.template'].read_group(
            [('barcode', 'in', ['9788599296301', '9788599296318'])],
            ['id'], ['metabooks_collections'])
        vazios = [g for g in grupos if not g['metabooks_collections']]
        self.assertEqual(
            len(vazios), 1,
            'dois grupos "vazio" no agrupamento: é a chave repetida que mata '
            'o kanban com "Got duplicate key in t-foreach"')


@tagged('post_install', '-at_install')
class TestPalavrasChaveNaPlanilha(TestMetabooksExport):
    """"Separar com ponto e vírgula (;)", diz o manual deles."""

    def _celula(self, texto):
        self._edit(metabooks_keywords=texto)
        return self.book._metabooks_cell('Palavra-chave')

    def test_virgula_no_campo_vira_ponto_e_virgula_na_planilha(self):
        self.assertEqual(
            self._celula('1964, Democracia, Política'),
            '1964;Democracia;Política')

    def test_quem_ja_digita_com_ponto_e_virgula_e_respeitado(self):
        self.assertEqual(
            self._celula('1964; Democracia; Política'),
            '1964;Democracia;Política')

    def test_uma_lista_longa_nao_vira_uma_palavra_so(self):
        """O caso do 1964: vinte termos, vinte palavras-chave."""
        termos = ['golpe de 1964', 'ditadura militar', 'redemocratização',
                  'Cebrap', 'Angela Alonso', 'história do Brasil',
                  'anos de chumbo', 'Comissão da Verdade',
                  'transição democrática', 'ciência política']
        celula = self._celula(', '.join(termos))
        self.assertEqual(celula.count(';'), len(termos) - 1)
        self.assertEqual(celula.split(';'), termos)

    def test_campo_vazio_nao_vira_ponto_e_virgula_solto(self):
        """Borda: nada a dizer é célula em branco, não lixo."""
        self.assertFalse(self._celula(''))
        self.assertFalse(self._celula(' , ; , '))


@tagged('post_install', '-at_install')
class TestEnvioPorFTP(TestMetabooksExport):
    """O botão que sobe a planilha. A rede é a única coisa fingida aqui."""

    FTP = ('odoo.addons.liber_metabooks_integration.models.'
           'metabooks_export.ftplib.FTP')

    def setUp(self):
        super().setUp()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('metabooks_username', 'editora@hedra.com.br')
        icp.set_param('metabooks_password', 'segredo')
        self._edit(metabooks_page_count=320)
        self.batch = self._batch()
        self.batch.action_prepare()
        self.batch.action_generate()

    def _ftp_que(self, **efeitos):
        """Um ftplib.FTP de mentira, usável com `with`, que registra as chamadas."""
        from unittest.mock import MagicMock
        ftp = MagicMock()
        ftp.__enter__.return_value = ftp
        for metodo, erro in efeitos.items():
            getattr(ftp, metodo).side_effect = erro
        return ftp

    def test_sobe_o_arquivo_certo_na_pasta_certa_e_baixa_a_fila(self):
        from ..models import metabooks_export as mod
        ftp = self._ftp_que()
        with patch(self.FTP, return_value=ftp) as classe:
            self.batch.action_send_ftp()

        classe.assert_called_once_with(mod.FTP_HOST, timeout=mod.FTP_TIMEOUT)
        self.assertEqual(mod.FTP_HOST, 'ftp.metabooks.com')
        ftp.login.assert_called_once_with('editora@hedra.com.br', 'segredo')
        ftp.set_pasv.assert_called_once_with(True)
        ftp.cwd.assert_called_once_with('upload')
        comando, corpo = ftp.storbinary.call_args.args
        self.assertEqual(comando, 'STOR %s' % self.batch.filename)
        self.assertEqual(corpo.read(),
                         base64.b64decode(self.batch.attachment_id.datas),
                         'o que sobe é a planilha gerada, byte a byte')

        self.assertEqual(self.batch.state, 'sent')
        self.assertEqual(self.batch.sent_by, self.env.user)
        self.assertFalse(self.book.metabooks_export_pending)
        ultima = self.batch.message_ids[0]
        self.assertIn('FTP', ultima.body)
        self.assertIn(self.batch.filename, ultima.body)

    def test_recusa_do_servidor_nao_marca_nada(self):
        """Senha errada, usuário sem FTP liberado: a fila fica como estava."""
        import ftplib
        ftp = self._ftp_que(login=ftplib.error_perm('530 Login incorrect.'))
        with patch(self.FTP, return_value=ftp), \
                self.assertRaises(UserError) as capturado:
            self.batch.action_send_ftp()
        self.assertIn('530 Login incorrect', str(capturado.exception))
        self.assertEqual(self.batch.state, 'generated')
        self.assertTrue(self.book.metabooks_export_pending)
        ftp.storbinary.assert_not_called()

    def test_rede_fora_e_erro_legivel_e_nao_traceback(self):
        with patch(self.FTP, side_effect=OSError('Network is unreachable')), \
                self.assertRaises(UserError):
            self.batch.action_send_ftp()
        self.assertEqual(self.batch.state, 'generated')
        self.assertTrue(self.book.metabooks_export_pending)

    def test_sem_credencial_nem_tenta_conectar(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'metabooks_password', False)
        with patch(self.FTP) as classe, self.assertRaises(UserError):
            self.batch.action_send_ftp()
        classe.assert_not_called()
        self.assertEqual(self.batch.state, 'generated')

    def test_lote_vazio_nao_tem_o_que_enviar(self):
        novo = self._batch()
        with patch(self.FTP) as classe, self.assertRaises(UserError):
            novo.action_send_ftp()
        classe.assert_not_called()

    def test_enviar_direto_do_rascunho_gera_e_sobe(self):
        """Um clique: quem quer enviar não quer gerar antes, nem baixar."""
        self._edit(metabooks_page_count=340)
        lote = self._batch()
        lote.action_prepare()
        self.assertEqual(lote.state, 'draft')

        ftp = self._ftp_que()
        with patch(self.FTP, return_value=ftp):
            lote.action_send_ftp()

        self.assertEqual(lote.state, 'sent')
        self.assertTrue(lote.attachment_id, 'a planilha fica arquivada')
        self.assertTrue(lote.filename)
        ftp.storbinary.assert_called_once()
        self.assertFalse(self.book.metabooks_export_pending)

    def test_gerar_nao_baixa_nada(self):
        """O download era o incômodo: a planilha se arquiva, e só."""
        self._edit(metabooks_page_count=341)
        lote = self._batch()
        lote.action_prepare()
        self.assertTrue(lote.action_generate() is True)
        self.assertTrue(lote.attachment_id)
        baixar = lote.action_download()
        self.assertEqual(baixar['type'], 'ir.actions.act_url',
                         'quem quiser o arquivo ainda tem o botão Baixar')

    def test_lote_enviado_nao_se_reenvia(self):
        ftp = self._ftp_que()
        with patch(self.FTP, return_value=ftp):
            self.batch.action_send_ftp()
            with self.assertRaises(UserError):
                self.batch.action_send_ftp()
        self.assertEqual(ftp.storbinary.call_count, 1)

    def test_o_caminho_manual_continua_de_pe(self):
        """Baixar + Marcar como enviada segue existindo, sem tocar na rede."""
        with patch(self.FTP) as classe:
            self.batch.action_mark_sent()
        classe.assert_not_called()
        self.assertEqual(self.batch.state, 'sent')
        self.assertFalse(self.book.metabooks_export_pending)


@tagged('post_install', '-at_install')
class TestTestarAsDuasPortas(TestMetabooksExport):
    """O botão de Configuração prova a API E o FTP.

    São duas portas com a mesma chave, e o suporte da Metabooks habilita o FTP
    por usuário. Testar só a API dizia "conexão bem-sucedida" a quem não
    conseguiria entregar planilha nenhuma, e a recusa aparecia depois -- com o
    lote pronto e a pessoa esperando.
    """

    def setUp(self):
        super().setUp()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('metabooks_username', 'usuario')
        icp.set_param('metabooks_password', 'senha')
        self.Batch = self.env['metabooks.export.batch']

    def _settings(self):
        return self.env['res.config.settings'].create({})

    def test_ftp_de_pe_nao_devolve_erro(self):
        with patch.object(type(self.Batch), '_ftp_probe', return_value=None):
            self.assertFalse(self.Batch.test_ftp())

    def test_ftp_recusado_devolve_a_fala_do_servidor(self):
        import ftplib
        with patch.object(type(self.Batch), '_ftp_probe',
                          side_effect=ftplib.error_perm('530 Login incorrect')):
            self.assertIn('530 Login incorrect', self.Batch.test_ftp())

    def test_sem_credenciais_diz_o_que_falta(self):
        """Borda: nem chega a bater na porta."""
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('metabooks_username', '')
        icp.set_param('metabooks_password', '')
        self.assertIn('Settings', self.Batch.test_ftp())

    def test_api_boa_e_ftp_ruim_e_recusa_que_explica(self):
        """O caso que motivou tudo: a chave abre uma porta e não a outra."""
        import ftplib
        Conector = type(self.env['metabooks.connector'])
        with patch.object(Conector, 'test_connection', return_value=True), \
             patch.object(type(self.Batch), '_ftp_probe',
                          side_effect=ftplib.error_perm('530 Not enabled')):
            with self.assertRaises(UserError) as erro:
                self._settings().action_test_metabooks_connection()
        mensagem = str(erro.exception)
        self.assertIn('530 Not enabled', mensagem)
        self.assertIn('API answered', mensagem,
                      'a mensagem tem de dizer que metade funcionou')

    def test_as_duas_de_pe_avisa_as_duas(self):
        Conector = type(self.env['metabooks.connector'])
        with patch.object(Conector, 'test_connection', return_value=True), \
             patch.object(type(self.Batch), '_ftp_probe', return_value=None):
            res = self._settings().action_test_metabooks_connection()
        self.assertIn('FTP', res['params']['message'])


@tagged('post_install', '-at_install')
class TestUmArquivoUmSelo(TestMetabooksExport):
    """A casa tem vários selos, e o arquivo é assinado por um só."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.outro_selo = cls.book.copy({
            'name': 'Livro do outro selo',
            'barcode': '9788599296301',
            'metabooks_vendor_id': 'BR0090213',
        })
        cls.sem_selo = cls.book.copy({
            'name': 'Livro sem selo',
            'barcode': '9788599296318',
            'metabooks_vendor_id': False,
        })
        for livro in (cls.outro_selo, cls.sem_selo):
            livro.with_context(metabooks_from_sync=True).write({
                'metabooks_export_pending': False,
                'metabooks_export_pending_since': False,
                'metabooks_export_last': fields.Datetime.now() - timedelta(days=30),
                'metabooks_export_last_track': _max_track(cls.env),
            })
        cls._settle(cls.env)

    def _lotes_da_rodada(self, acao):
        dominio = dict(acao['domain'])if isinstance(acao['domain'], dict) else acao['domain']
        ids = dominio[0][2]
        return self.env['metabooks.export.batch'].browse(ids)

    def _rodada(self):
        return self.env['metabooks.export.batch'].action_prepare_round()

    def test_tres_selos_viram_tres_lotes(self):
        self._edit(self.book | self.outro_selo | self.sem_selo,
                   metabooks_page_count=320)
        acao = self._rodada()

        lotes = self._lotes_da_rodada(acao)
        self.assertEqual(len(lotes), 3, 'um lote por selo, e nenhum livro perdido')
        por_selo = {l.mb_id or '': l for l in lotes}
        self.assertEqual(set(por_selo), {'BR0089701', 'BR0090213', ''})
        self.assertEqual(por_selo['BR0090213'].line_ids.product_id,
                         self.outro_selo)
        self.assertEqual(por_selo[''].line_ids.product_id, self.sem_selo)

    def test_o_lote_do_selo_maior_vem_primeiro(self):
        """Quem abre a rodada vê o que importa, não os dois livros avulsos."""
        self._edit(self.book | self.outro_selo, metabooks_page_count=321)
        lotes = self._lotes_da_rodada(self._rodada())
        maior = lotes.filtered(lambda l: l.mb_id == 'BR0089701')
        self.assertEqual(maior.line_ids.product_id, self.book)

    def test_um_selo_so_e_um_lote_so(self):
        self._edit(metabooks_page_count=322)
        lotes = self._lotes_da_rodada(self._rodada())
        self.assertEqual(len(lotes), 1)
        self.assertEqual(lotes.mb_id, 'BR0089701')

    def test_buscar_duas_vezes_nao_duplica_o_lote(self):
        """O que produziu 0003 e 0005 iguais no prod, com os mesmos 273 livros."""
        self._edit(self.book | self.outro_selo, metabooks_page_count=327)
        primeira = self._lotes_da_rodada(self._rodada())
        segunda = self._lotes_da_rodada(self._rodada())
        self.assertEqual(primeira, segunda,
                         'a segunda busca reenche os mesmos lotes')
        self.assertEqual(
            self.env['metabooks.export.batch'].search_count(
                [('state', 'in', ('draft', 'checked'))]), len(primeira))

    def test_a_segunda_busca_traz_o_que_mudou_depois(self):
        self._edit(metabooks_page_count=328)
        lotes = self._lotes_da_rodada(self._rodada())
        self.assertEqual(lotes.line_ids.product_id, self.book)

        self._edit(self.outro_selo, metabooks_page_count=329)
        lotes = self._lotes_da_rodada(self._rodada())
        self.assertEqual(lotes.line_ids.product_id,
                         self.book | self.outro_selo)

    def test_lote_ja_verificado_volta_a_rascunho_ao_reencher(self):
        """Senão a pessoa gera uma planilha com a conferência de antes."""
        self._edit(metabooks_page_count=330)
        lote = self._lotes_da_rodada(self._rodada())
        lote.action_check()
        self.assertEqual(lote.state, 'checked')
        self._edit(metabooks_page_count=331)
        self._rodada()
        self.assertEqual(lote.state, 'draft')

    def test_nenhum_livro_se_perde_na_divisao(self):
        self._edit(self.book | self.outro_selo | self.sem_selo,
                   metabooks_page_count=323)
        lotes = self._lotes_da_rodada(self._rodada())
        self.assertEqual(
            lotes.line_ids.product_id,
            self.book | self.outro_selo | self.sem_selo)

    def test_livro_de_outro_selo_somado_a_mao_e_recusado(self):
        """A rede de segurança: dividir na preparação não impede editar depois."""
        self._edit(self.book | self.outro_selo, metabooks_page_count=324)
        lote = self._lotes_da_rodada(self._rodada()).filtered(
            lambda l: l.mb_id == 'BR0089701')
        lote._build_line(self.outro_selo)

        with self.assertRaises(UserError) as capturado:
            lote.action_check()
        recado = str(capturado.exception)
        self.assertIn('BR0090213', recado)
        self.assertIn('BR0089701', recado)

    def test_selo_do_cabecalho_trocado_a_mao_e_recusado(self):
        self._edit(metabooks_page_count=325)
        lote = self._lotes_da_rodada(self._rodada())
        lote.mb_id = 'BR0000000'
        with self.assertRaises(UserError) as capturado:
            lote.action_check()
        self.assertIn('BR0089701', str(capturado.exception))

    def test_lote_sem_selo_reclama_do_cadastro_e_nao_gera(self):
        """Borda: o livro sem MB ID não some, vira um lote que se queixa."""
        self._edit(self.sem_selo, metabooks_page_count=326)
        lote = self._lotes_da_rodada(self._rodada())
        self.assertFalse(lote.mb_id)
        self.assertEqual(lote.line_ids.product_id, self.sem_selo)
        with self.assertRaises(UserError):
            lote.action_generate()


@tagged('post_install', '-at_install')
class TestCopiaNaoEnviaParaAMetabooks(TestMetabooksExport):
    """Dev e staging carregam o dado e a senha do prod. Não podem entregar."""

    FTP = TestEnvioPorFTP.FTP

    def setUp(self):
        super().setUp()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('metabooks_username', 'editora@hedra.com.br')
        icp.set_param('metabooks_password', 'segredo')
        icp.set_param('database.is_neutralized', 'True')
        self._edit(metabooks_page_count=350)
        self.lote = self._batch()
        self.lote.action_prepare()

    def test_base_neutralizada_nao_toca_no_ftp(self):
        from unittest.mock import MagicMock
        with patch(self.FTP, MagicMock()) as classe:
            with self.assertRaises(UserError) as capturado:
                self.lote.action_send_ftp()
        classe.assert_not_called()
        self.assertIn('copy for testing', str(capturado.exception).lower())

    def test_a_planilha_ainda_se_gera_para_conferencia(self):
        """Bloquear a entrega não pode impedir de testar o resto."""
        self.lote.action_generate()
        self.assertTrue(self.lote.attachment_id)
        self.assertEqual(self.lote.state, 'generated')

        with patch(self.FTP) as classe, self.assertRaises(UserError):
            self.lote.action_send_ftp()
        classe.assert_not_called()
        self.assertTrue(self.book.metabooks_export_pending,
                        'nada foi entregue, então nada sai da fila')

    def test_o_bloqueio_vale_tambem_por_dentro(self):
        """Quem chamar _deliver() direto também não passa."""
        self.lote.action_generate()
        with patch(self.FTP) as classe, self.assertRaises(UserError):
            self.lote._deliver()
        classe.assert_not_called()

    def test_a_tela_avisa_antes_do_clique(self):
        self.assertTrue(self.lote.is_neutralized)

    def test_na_producao_o_envio_segue_normal(self):
        """Sem a marca, entrega. É o prod que não a tem."""
        self.env['ir.config_parameter'].sudo().set_param(
            'database.is_neutralized', False)
        self.lote.invalidate_recordset(['is_neutralized'])
        ftp = TestEnvioPorFTP._ftp_que(self)
        with patch(self.FTP, return_value=ftp):
            self.lote.action_send_ftp()
        ftp.storbinary.assert_called_once()
        self.assertEqual(self.lote.state, 'sent')


@tagged('post_install', '-at_install')
class TestSerieSoPorCodigo(TestMetabooksExport):
    """MDS062: a coluna Série quer o código deles, não o nome da coleção."""

    def _celula(self, texto):
        self._edit(metabooks_collections=texto)
        return self.book._metabooks_cell('Série')

    def test_nome_de_colecao_nao_vai(self):
        """O caso real: 49 livros recusados por 'Biblioteca de Cordel'."""
        self.assertFalse(self._celula('Biblioteca de Cordel'))
        self.assertFalse(self._celula('Hedra de Bolso'))

    def test_codigo_da_metabooks_vai(self):
        self.assertEqual(self._celula('AAA123456'), 'AAA123456')

    def test_vazio_continua_vazio(self):
        self.assertFalse(self._celula(''))

    def test_o_resto_do_livro_ainda_sai_na_planilha(self):
        """O ponto todo: a recusa levava junto Thema, BISAC e palavras-chave."""
        self._edit(metabooks_collections='Biblioteca de Cordel',
                   metabooks_keywords='cordel, poesia')
        lote = self._batch()
        lote.action_prepare()
        colunas = set(lote.change_ids.mapped('column'))
        self.assertNotIn('Série', colunas,
                         'coluna que a Metabooks recusaria não entra no lote')
        self.assertIn('Palavra-chave', colunas)


@tagged('post_install', '-at_install')
class TestRetornoDaMetabooks(TestMetabooksExport):
    """Ler a planilha que eles mandam depois da meia-noite."""

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param(
            'database.is_neutralized', False)
        self._edit(metabooks_page_count=360)
        self.lote = self._batch()
        self.lote.action_prepare()
        self.track_antes = self.book.metabooks_export_last_track
        self.lote.action_generate()
        self.lote.action_mark_sent()

    def _relatorio(self, linhas, aba='Rejeitados', arquivo=None):
        """Uma planilha no formato deles, com o cabeçalho que eles escrevem."""
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = aba
        ws.append(['GTIN', 'Mensagem de erro', 'Detalhes',
                   'Status do produto', 'Hora do registro',
                   'Nome do arquivo', 'Código do erro'])
        for gtin, msg, cod in linhas:
            ws.append([gtin, msg, '', 'ativo', '2026-09-03 22:11:36',
                       arquivo or ('!jsallum!_%s_3789aa56'
                                   % (self.lote.filename or '').rsplit('.', 1)[0]),
                       cod])
        buffer = io.BytesIO()
        wb.save(buffer)
        return base64.b64encode(buffer.getvalue())

    def _ler(self, linhas, **kw):
        wizard = self.env['metabooks.import.report'].create({
            'file': self._relatorio(linhas, **kw),
            'filename': 'relatorio.xlsx',
        })
        return wizard.action_import()

    def test_livro_recusado_volta_para_a_fila(self):
        self.assertFalse(self.book.metabooks_export_pending)

        self._ler([(self.book.barcode,
                    'Por favor especifique título da série.', 'MDS062')])

        self.assertTrue(self.book.metabooks_export_pending,
                        'recusado não foi entregue, então continua devendo')
        linha = self.lote.line_ids.filtered(
            lambda l: l.product_id == self.book)
        self.assertTrue(linha.rejected)
        self.assertEqual(linha.error_code, 'MDS062')
        self.assertIn('série', linha.error_message)
        self.assertEqual(self.lote.rejected_count, 1)
        self.assertTrue(self.lote.report_on)

    def test_a_alteracao_recusada_volta_a_aparecer(self):
        """Sem restaurar o corte, a mudança que não chegou some para sempre."""
        self._ler([(self.book.barcode, 'Erro qualquer', 'MDS062')])
        self.assertEqual(self.book.metabooks_export_last_track,
                         self.track_antes)

        novo = self._batch()
        novo.action_prepare()
        colunas = set(novo.change_ids.mapped('column'))
        self.assertIn('Número de páginas', colunas,
                      'a alteração que a Metabooks recusou volta ao próximo lote')

    def test_livro_aceito_nao_e_mexido(self):
        outro = self.book.copy({'name': 'Aceito', 'barcode': '9788599296400'})
        self._ler([(self.book.barcode, 'Erro', 'MDS062')])
        self.assertFalse(outro.metabooks_export_pending or False)
        linhas = self.lote.line_ids.filtered(lambda l: not l.rejected)
        self.assertFalse(linhas.mapped('error_code') and
                         any(linhas.mapped('error_code')))

    def test_isbn_que_nao_e_nosso_nao_derruba_a_leitura(self):
        """Borda: relatório com um ISBN de outro envio, ou de outra editora."""
        acao = self._ler([(self.book.barcode, 'Erro', 'MDS062'),
                          ('9789999999990', 'Erro', 'MDS062')])
        self.assertEqual(acao['params']['type'], 'warning')
        self.assertTrue(self.book.metabooks_export_pending)

    def test_relatorio_sem_recusa_avisa_e_nao_mexe(self):
        with self.assertRaises(UserError):
            self._ler([])
        self.assertFalse(self.book.metabooks_export_pending)

    def test_arquivo_que_nao_e_planilha_da_recado(self):
        wizard = self.env['metabooks.import.report'].create({
            'file': base64.b64encode(b'nem xlsx nem nada'),
            'filename': 'foto.png',
        })
        with self.assertRaises(UserError):
            wizard.action_import()

    def test_em_analise_tambem_conta_como_nao_entregue(self):
        self._ler([(self.book.barcode, '', '')], aba='Em análise')
        self.assertTrue(self.book.metabooks_export_pending)
        linha = self.lote.line_ids.filtered(
            lambda l: l.product_id == self.book)
        self.assertTrue(linha.rejected)
        self.assertTrue(linha.error_message, 'sem mensagem deles, a nossa')


@tagged('post_install', '-at_install')
class TestAcabamentoNaPlanilha(TestMetabooksExport):
    """A coluna Acabamento é a lista 175 inteira, não só a encadernação.

    "Código ONIX (Lista 175) para detalhes adicionais ao tipo de acabamento",
    diz o manual deles, com `B504 = Com orelhas` de exemplo. Mandávamos só a
    encadernação: orelha, sobrecapa, marcador e todo o acabamento de capa
    ficavam sabidos aqui dentro e não chegavam lá.
    """

    def test_o_apelido_da_encadernacao_vira_codigo_onix(self):
        """Guardamos "adhesive"; a lista 175 conhece B305, não "adhesive"."""
        self._edit(metabooks_binding='adhesive')
        self.assertEqual(self.book._metabooks_cell('Acabamento'), 'B305')

    def test_os_acabamentos_marcados_viajam_junto(self):
        self._edit(metabooks_binding='adhesive', metabooks_has_flaps=True,
                   metabooks_has_lamination=True, metabooks_has_foil_cover=True)
        celula = self.book._metabooks_cell('Acabamento')
        self.assertEqual(celula.split(';')[0], 'B305',
                         'a encadernação abre a lista')
        self.assertEqual(set(celula.split(';')), {'B305', 'B504', 'B415', 'B422'})

    def test_sem_encadernacao_o_acabamento_ainda_sai(self):
        """Borda: e-book laminado não existe, mas brochura sem código, sim."""
        self._edit(metabooks_binding=False, metabooks_has_lamination=True)
        self.assertEqual(self.book._metabooks_cell('Acabamento'), 'B415')

    def test_livro_sem_nada_nao_manda_lixo(self):
        self._edit(metabooks_binding=False, metabooks_has_flaps=False,
                   metabooks_has_lamination=False)
        self.assertFalse(self.book._metabooks_cell('Acabamento'))

    def test_a_importacao_le_o_acabamento_de_capa(self):
        """O outro lado: o que eles mandam, nós lemos."""
        vals = self.env['metabooks.connector']._parse_technical({
            'form': {'productFormDetail': ['B415', 'B422', 'B504']},
        })
        self.assertTrue(vals['metabooks_has_lamination'])
        self.assertTrue(vals['metabooks_has_foil_cover'])
        self.assertTrue(vals['metabooks_has_flaps'])
        self.assertFalse(vals['metabooks_has_emboss'])
