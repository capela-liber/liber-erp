# -*- coding: utf-8 -*-
"""Sending our book data back to Metabooks, with a human in the middle.

The shape of the thing: editing a book marks it pending (product.template
below); a batch gathers what is pending, shows the before/after of every field,
and lets someone uncheck what should not go; generating produces the .xlsx with
the changed cells in red; only once the file is actually delivered do the books
stop being pending.

The one place this talks to Metabooks is _deliver(): the file goes up by FTP
to ftp.metabooks.com, folder 'upload', with the same credentials the API uses.
Downloading the file and uploading it by hand is still there as the fallback,
with "Mark as sent" closing the loop.

The batch, its lines and their changes are kept forever: they are the record of
what we asked Metabooks to alter, and when. The books move on; this does not.
"""

import base64
import ftplib
import io
import logging
from datetime import date

import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from ..services import metabooks_mapping as mapping
from ..services import onix_codes
from ..services import metabooks_sheet as sheet

_logger = logging.getLogger(__name__)

# Metabooks' documented ingestion channel: fixed host, passive mode (their
# firewall note: ports 20000-20500), our folder is 'upload' -- the other two
# belong to data clearing. Credentials are the portal ones, the same the REST
# API already uses, so there is nothing new to configure.
FTP_HOST = 'ftp.metabooks.com'
FTP_FOLDER = 'upload'
FTP_TIMEOUT = 60

# Which old_value_* column mail.tracking.value uses per field type.
_TRACKING_COLUMN = {
    'integer': 'integer',
    'boolean': 'integer',
    'float': 'float',
    'monetary': 'float',
    'date': 'datetime',
    'datetime': 'datetime',
    'char': 'char',
    'selection': 'char',
    'many2one': 'char',
    'many2many': 'char',
    'one2many': 'char',
    'text': 'text',
    'html': 'text',
}


_HTML = re.compile(r'<[a-zA-Z/][^>]*>')

# ISBN-13: the Bookland EAN prefixes, and nothing else, is what makes a
# product a book for Metabooks' purposes.
_ISBN13 = re.compile(r'^97[89]\d{10}$')

# The Série column takes a series CODE that already exists at Metabooks
# (AAA123456 in their guide), never a name. See _metabooks_serie.
_SERIE_CODE = re.compile(r'^[A-Z]{2,4}\d{4,10}$')


def _plain(value):
    """Text as Metabooks wants it: no markup.

    Synopses in particular pick up HTML -- the website editor writes into the
    same field -- and their spreadsheet column is plain text, so a <div> would
    reach readers as literal markup. Only touched when the value really does
    carry a tag, so ordinary text containing a "<" survives intact.
    """
    if not isinstance(value, str) or not _HTML.search(value):
        return value
    return html2plaintext(value).strip()


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    metabooks_export_pending = fields.Boolean(
        'Pending Metabooks Export', default=False, copy=False, index=True,
        readonly=True,
        help="Set when a field Metabooks knows about is edited here, cleared "
             "once the change has been delivered to them.")
    metabooks_export_pending_since = fields.Datetime(
        'Pending Since', copy=False, readonly=True)
    metabooks_export_last = fields.Datetime(
        'Last Sent to Metabooks', copy=False, readonly=True)
    metabooks_export_last_track = fields.Integer(
        'History Cut-off', copy=False, readonly=True, default=0,
        help="Highest mail.tracking.value id at the moment of the last send. "
             "Reading the change history from here rather than from a "
             "timestamp is what keeps an edit made in the same second as a "
             "send from being lost: mail.message.date only resolves to the "
             "second, and a change that falls inside it would look older than "
             "the send that did not carry it.")

    @staticmethod
    def _metabooks_espelhar_peso(vals):
        """Os dois campos de peso andam juntos, escreva-se em qual for.

        São dois porque servem a mundos diferentes: `metabooks_weight` é do
        catálogo (em GRAMAS, como o ONIX pede) e `weight` é do Odoo (em
        QUILOS, e é o que o estoque soma numa entrega e a nota fiscal
        declara). Quem preenche a ficha não tem por que saber disso — digita
        num dos dois e espera que o livro passe a ter peso.

        Sem o espelho, cada lado ficava cego para o outro: peso do painel não
        chegava à movimentação (a entrega pesava zero com o catálogo sabendo
        o peso), e peso digitado aqui não voltava para a Metabooks.

        Espelhar em `vals` (e não depois) é o que faz a máquina de sempre
        enxergar a mudança: campo vigiado alterado marca o livro pendente e o
        histórico guarda o antes/depois que a planilha publica. Escrever os
        dois na mesma chamada — como o sync faz — desliga o espelho: valor
        explícito manda.

        Zero nunca apaga o outro lado: apagar dado por engano custa mais do
        que um número velho.
        """
        tem_kg = 'weight' in vals
        tem_g = 'metabooks_weight' in vals
        if tem_kg == tem_g:          # nenhum dos dois, ou os dois explícitos
            return vals
        if tem_kg:
            gramas = round((vals.get('weight') or 0.0) * 1000.0, 2)
            return dict(vals, metabooks_weight=gramas) if gramas else vals
        quilos = round((vals.get('metabooks_weight') or 0.0) / 1000.0, 6)
        return dict(vals, weight=quilos) if quilos else vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._metabooks_vazio_e_nulo(v) for v in vals_list])

    @staticmethod
    def _metabooks_vazio_e_nulo(vals):
        """String vazia é `False`, aqui e em qualquer caminho de escrita.

        O Odoo devolve UM grupo para o NULL e OUTRO para o `''`, e os dois
        chegam ao `t-foreach` do kanban com a mesma chave -- vazia. Owl recusa
        chave repetida e a tela morre com "Got duplicate key in t-foreach". Foi
        o que aconteceu em 02/09/2026 ao agrupar Livros pela Coleção, com 933
        coleções, 946 subtítulos e 514 listas de palavra-chave gravados como
        `''` pelo importador.

        A trava mora aqui, e não só no importador, porque o problema é do DADO:
        qualquer caminho que grave `''` reabre o buraco, e quem paga é a tela.
        Só campos de texto do Metabooks: o resto do product.template não é
        assunto deste módulo.
        """
        vazios = {c: False for c in mapping.TEXT_FIELDS
                  if isinstance(vals.get(c), str) and not vals[c].strip()}
        return dict(vals, **vazios) if vazios else vals

    def write(self, vals):
        vals = self._metabooks_vazio_e_nulo(vals)
        vals = self._metabooks_espelhar_peso(vals)
        res = super().write(vals)
        touched = mapping.WATCHED_FIELDS.intersection(vals)
        # An import from Metabooks writes the same fields a person does. Left
        # alone it would mark every imported book as pending and send their own
        # data straight back at them.
        if self.env.context.get('metabooks_from_sync'):
            if touched:
                self._metabooks_settle_history()
            return res
        if not touched:
            return res
        stale = self.filtered(
            lambda p: not p.metabooks_export_pending and p._metabooks_is_book())
        if stale:
            stale.with_context(metabooks_from_sync=True).write({
                'metabooks_export_pending': True,
                'metabooks_export_pending_since': fields.Datetime.now(),
            })
        return res

    def _metabooks_settle_history(self):
        """Põe atrás do corte tudo o que a Metabooks acabou de escrever aqui.

        `metabooks_export_last_track` é onde o chatter começa a valer, e só era
        carimbado quando um lote saía. Livro que **veio** deles nunca saiu
        daqui, então o corte ficava em zero e a planilha propunha devolver a
        biografia inteira do registro: no 1964 (9788577154036), 16 das 19
        alterações eram a importação de 04/08 e a ficha técnica de 11/08 --
        altura, peso, páginas, NCM, sinopse, preço --, todas lidas deles.

        O carimbo espera o `precommit`: o Odoo grava os `mail.tracking.value`
        de uma escrita ali, depois do `write`, e um corte lido antes deixaria
        de fora justamente as linhas desta sincronização.

        Enterrar edição da casa anterior à sincronização é correto, não
        colateral: quem sincroniza sobrescreve o campo com o valor deles, então
        não sobrou nada nosso para contar.
        """
        ids = tuple(self.ids)
        if not ids:
            return

        def carimbar():
            cr = self.env.cr
            cr.execute("SELECT max(id) FROM mail_tracking_value")
            ultimo = cr.fetchone()[0] or 0
            cr.execute("""UPDATE product_template
                             SET metabooks_export_last_track = %s
                           WHERE id IN %s
                             AND coalesce(metabooks_export_last_track, 0) < %s""",
                       (ultimo, ids, ultimo))
            self.invalidate_recordset(['metabooks_export_last_track'])

        self.env.cr.precommit.add(carimbar)

    def action_metabooks_clear_pending(self):
        """Drop out of the queue without sending -- the change was not for them."""
        return self.with_context(metabooks_from_sync=True).write({
            'metabooks_export_pending': False,
            'metabooks_export_pending_since': False,
        })

    # ---------------------------------------------------------------- #
    #  Reading one book as Metabooks columns
    # ---------------------------------------------------------------- #

    def _metabooks_is_known(self):
        """Does Metabooks already have this title?

        Not "have we sent it before". Every book imported from them is already
        registered there, and none of them was ever sent from here -- so basing
        the new/update split on our own send history made the first update
        batch come up empty for the entire catalogue. Carrying their publisher
        id is the evidence that the title came from them.
        """
        self.ensure_one()
        return bool(self.metabooks_export_last or self.metabooks_vendor_id)

    def _metabooks_gtin(self):
        """Their dedup key. Digits only -- the guide says 'Somente números'."""
        self.ensure_one()
        raw = self.barcode or self.default_code or ''
        return ''.join(c for c in raw if c.isdigit())

    def _metabooks_is_book(self):
        """Is this product a book at all?

        Metabooks is a book catalogue, but `list_price` -- one of the watched
        fields -- lives on every product.template there is. The house keeps its
        chart of results as pseudo-products (ADM0006 "(-) Impostos", ADM0033
        "(-) Aluguel"), and every price touched on one of those was walking
        into the export queue alongside the catalogue.

        The line is the ISBN, and it is the same line Metabooks itself draws:
        a book carries an ISBN-13 in the Bookland range (978/979), in the
        barcode or, for titles that came from the legacy, in the internal
        reference. Anything without one could not be sent even if it got in --
        the check refuses a row with no GTIN -- so nothing is lost by keeping
        it out of the queue in the first place.
        """
        self.ensure_one()
        return bool(_ISBN13.match(self._metabooks_gtin()))

    def _metabooks_cell(self, column):
        """Current value of one Metabooks column for this book, or False."""
        self.ensure_one()
        field, kind, extra = mapping.BY_COLUMN[column]
        value = self[field]

        if kind == mapping.AUTHORS:
            return self._metabooks_contributors(extra)
        if kind == mapping.BISAC:
            return self._metabooks_lista_de_codigos(
                'bisac_code', self.bisac_code, value, 'bisac_code')
        if kind == mapping.THEMA:
            # O que viaja é o código, nunca a ementa traduzida. Para as
            # categorias, o principal vai na frente; os qualificadores não têm
            # principal e saem na ordem em que estão.
            principal = self.metabooks_thema_id if column == 'Categoria Thema' \
                else self.env['metabooks.thema.code']
            return self._metabooks_lista_de_codigos(
                'code', principal, value, 'code')
        if kind == mapping.AVAILABILITY:
            return value.product_definition or False if value else False
        if kind == mapping.COUNTRY:
            return value.code or False if value else False
        if kind == mapping.M2O_NAME:
            return value.name or False if value else False
        if kind == mapping.PRICE:
            return round(value, 2) if value else False
        if kind in (mapping.INT, mapping.FLOAT):
            # Zero is how Odoo spells "never filled in" for these; sending it
            # would tell Metabooks the book weighs nothing.
            return value or False
        if kind == mapping.DATE:
            return value or False
        if column == 'Palavra-chave':
            return self._metabooks_palavras_chave(value)
        if column == 'Acabamento':
            return self._metabooks_acabamento(value)
        if column == 'Série':
            return self._metabooks_serie(value)
        return _plain(value) or False

    def _metabooks_acabamento(self, encadernacao):
        """A encadernação e os acabamentos, todos códigos da lista 175.

        A coluna deles é "detalhes adicionais ao tipo de acabamento", com a
        lista 175 inteira -- e nós mandávamos só a encadernação. Orelha,
        sobrecapa, marcador, laminação, relevo e hotstamp ficavam sabidos aqui
        dentro e não chegavam à Metabooks.

        RESSALVA, dita porque importa: o manual deles declara o ponto e vírgula
        para BISAC, Thema e palavra-chave, e **não diz nada** para esta coluna.
        Adotamos o mesmo separador, que é o único que esta planilha documenta.
        O primeiro lote com acabamento merece ser de um livro só, para conferir
        no painel deles antes de ir o catálogo inteiro.
        """
        # `metabooks_binding` guarda apelido nosso ("sewn"), e a coluna pede o
        # código ONIX. Sem esta volta a planilha vinha mandando "sewn" para a
        # Metabooks desde sempre -- valor que a lista 175 não tem.
        codigo_encadernacao = onix_codes.DETAIL_BY_BINDING.get(encadernacao)
        codigos = [codigo_encadernacao] if codigo_encadernacao else []
        for campo, codigo in onix_codes.FINISH_BY_FIELD.items():
            if self[campo] and codigo not in codigos:
                codigos.append(codigo)
        if self.metabooks_has_dust_jacket:
            codigos.append(onix_codes.DETAIL_DUST_JACKET[0])
        return ';'.join(codigos) or False

    @staticmethod
    def _metabooks_palavras_chave(valor):
        """Ponto e vírgula entre elas, que é o que a planilha deles pede.

        "Separar com ponto e vírgula (;)", diz o manual, com o exemplo
        `Prêmio Jabuti; Adolescência; Desenvolvimento da criança`. O campo aqui
        guarda o que a importação escreveu, separado por vírgula, e a célula
        saía assim -- então vinte palavras-chave chegariam à Metabooks como UMA
        só, de duzentos caracteres, e o livro ficaria sem nenhuma busca.

        Aceita os dois separadores na entrada de propósito: quem digita na tela
        usa o que quiser, e a planilha sai certa de qualquer jeito.
        """
        texto = _plain(valor) or ''
        palavras = [p.strip() for p in texto.replace(';', ',').split(',')]
        return ';'.join(p for p in palavras if p) or False

    @staticmethod
    def _metabooks_serie(valor):
        """Só o código da série deles, nunca o nome da nossa coleção.

        "Apenas títulos de séries já existentes na Metabooks podem ser alocados
        por meio de importação via Excel, através de seu código (Exemplo:
        AAA123456)", diz o guia. O campo aqui guarda o nome -- "Biblioteca de
        Cordel", "Hedra de Bolso" -- e mandá-lo custou caro: na remessa de
        03/09/2026 os 49 livros que levaram esta coluna voltaram TODOS com
        MDS062, "Por favor especifique título da série". E a recusa é do
        registro inteiro, então esses livros perderam junto as palavras-chave,
        o Thema e o BISAC que iam na mesma linha.

        Enquanto a coleção não tiver código deles, a célula sai vazia: coluna
        que não vai é coluna que a Metabooks não mexe, e o resto do livro
        entra.
        """
        texto = (_plain(valor) or '').strip()
        return texto if _SERIE_CODE.match(texto) else False

    @staticmethod
    def _metabooks_lista_de_codigos(_campo, principal, lista, atributo):
        """Uma coluna, ponto e vírgula entre os códigos, o principal na frente.

        É o que o manual deles manda ("Separar por ponto e vírgula", exemplo
        `COM087030; REF032000`) e é como o painel sabe qual é a Classificação
        principal: pela ordem. O principal também está na lista -- entra uma
        vez só, e primeiro.
        """
        codigos = []
        for registro in principal:
            if registro[atributo]:
                codigos.append(registro[atributo])
        for registro in lista:
            valor = registro[atributo]
            if valor and valor not in codigos:
                codigos.append(valor)
        return ';'.join(codigos) or False

    def _metabooks_contributors(self, role_code):
        """"Silva, Augusto da; Araújo, Michele" -- surname first, "; " between."""
        self.ensure_one()
        names = []
        for author in self.book_auther_ids:
            if (author.author_contributor_role.name or '') != role_code:
                continue
            surname = (author.author_last_name or '').strip()
            given = (author.name or '').strip()
            if surname and given:
                names.append('%s, %s' % (surname, given))
            elif author.author_full_name:
                names.append(author.author_full_name.strip())
            elif surname or given:
                names.append(surname or given)
        return '; '.join(names) or False


class MetabooksExportBatch(models.Model):
    _name = 'metabooks.export.batch'
    _description = 'Metabooks Export Batch'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(
        'Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    task = fields.Selection(
        [(sheet.TASK_UPDATE, 'Alteração (V)'),
         (sheet.TASK_NEW, 'Cadastro novo (Z)'),
         (sheet.TASK_ARCHIVE, 'Arquivamento (X)'),
         (sheet.TASK_REACTIVATE, 'Reativação (R)')],
        string='Task', default=sheet.TASK_UPDATE, required=True,
        readonly=False, tracking=True,
        help="Metabooks reads this from the first letter of the file name. A "
             "file carries one task, so a batch does too.")
    state = fields.Selection(
        [('draft', 'Draft'), ('checked', 'Checked'),
         ('generated', 'Generated'), ('sent', 'Sent'), ('cancel', 'Cancelled')],
        default='draft', required=True, tracking=True)
    mb_id = fields.Char(
        'MB ID Editor', tracking=True,
        help="Publisher id at Metabooks, second part of the file name. Filled "
             "in by Fetch changes, which makes one batch per imprint: a file "
             "is signed by one publisher.")
    free_text = fields.Char(
        'File Name Text', default='Alteracoes',
        help="Last part of the file name. Only a human reads it.")
    line_ids = fields.One2many(
        'metabooks.export.line', 'batch_id', string='Books')
    # Flat view of every field change in the batch: the de/para screen, and
    # what comes out red in the spreadsheet.
    change_ids = fields.One2many(
        'metabooks.export.change', 'batch_id', string='Changes', readonly=True)
    selected_count = fields.Integer(compute='_compute_counts')
    change_count = fields.Integer(compute='_compute_counts')
    filename = fields.Char(readonly=True, copy=False)
    attachment_id = fields.Many2one(
        'ir.attachment', string='File', readonly=True, copy=False)
    generated_on = fields.Datetime(readonly=True, copy=False)
    generated_by = fields.Many2one('res.users', readonly=True, copy=False)
    sent_on = fields.Datetime(readonly=True, copy=False)
    sent_by = fields.Many2one('res.users', readonly=True, copy=False)
    note = fields.Text('Notes')
    is_neutralized = fields.Boolean(compute='_compute_is_neutralized')
    rejected_count = fields.Integer(compute='_compute_rejected_count')
    report_on = fields.Datetime(
        readonly=True, copy=False, string='Report Read On')

    @api.depends('line_ids.rejected')
    def _compute_rejected_count(self):
        for batch in self:
            batch.rejected_count = len(batch.line_ids.filtered('rejected'))

    def _compute_is_neutralized(self):
        neutralizado = bool(self.env['ir.config_parameter'].sudo().get_param(
            'database.is_neutralized'))
        for batch in self:
            batch.is_neutralized = neutralizado

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'metabooks.export.batch') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.selected', 'line_ids.change_ids',
                 'line_ids.change_ids.selected')
    def _compute_counts(self):
        for batch in self:
            chosen = batch.line_ids.filtered('selected')
            batch.selected_count = len(chosen)
            batch.change_count = len(chosen.change_ids.filtered('selected'))

    # ---------------------------------------------------------------- #
    #  Gathering
    # ---------------------------------------------------------------- #

    @api.model
    def action_prepare_round(self):
        """Build the round: what is pending, split by imprint.

        Lives on the list, not on a batch, because that is what it does -- it
        looks at the whole pending queue and lays out the round. On the form it
        read as "reload this batch", and pressing it twice made a second set of
        batches: the day this moved, the production list had 0003 and 0005 with
        the same 273 books, and 0004 and 0006 with the same 5.

        So it is idempotent by construction: an open batch for the same task
        and imprint is refilled, not duplicated. Pressing it again is how you
        pick up what changed since -- which is the only reason to press it.
        """
        products = self._pending_products()
        if not products:
            raise UserError(_(
                "No book is waiting to be sent to Metabooks for this task."))

        by_imprint = self._group_by_imprint(products)
        ordem = sorted(by_imprint, key=lambda k: (-len(by_imprint[k]), k or ''))

        rodada = self.browse()
        for imprint in ordem:
            lote = self._open_batch_for(imprint)
            lote.line_ids.unlink()
            for product in by_imprint[imprint]:
                lote._build_line(product)
            if lote.state != 'draft':
                lote.state = 'draft'
            rodada |= lote
        return self._action_show(rodada)

    @api.model
    def _open_batch_for(self, imprint):
        """The batch this imprint's books belong in: an open one, or a new one."""
        task = self.env.context.get('default_task') or sheet.TASK_UPDATE
        aberto = self.search([
            ('state', 'in', ('draft', 'checked')),
            ('task', '=', task),
            ('mb_id', '=', imprint or False),
        ], order='id desc', limit=1)
        return aberto or self.create({'task': task, 'mb_id': imprint or False})

    def action_prepare(self):
        """Refill this batch alone, keeping its imprint.

        Kept for the batches the round already laid out: it is the reload that
        does not touch the others. Not on the form's button bar -- fetching is
        a round-level act, and doing it per batch is what produced duplicates.
        """
        self.ensure_one()
        self._assert_open()
        self.line_ids.unlink()

        products = self._pending_products()
        if self.mb_id:
            products = products.filtered(
                lambda p: (p.metabooks_vendor_id or '') == self.mb_id)
        if not products:
            raise UserError(_(
                "No book is waiting to be sent to Metabooks for this task."))
        for product in products:
            self._build_line(product)
        if not self.mb_id:
            selos = self._group_by_imprint(products)
            if len(selos) == 1:
                self.mb_id = next(iter(selos)) or False
        return True

    def _pending_products(self):
        products = self.env['product.template'].search(
            [('metabooks_export_pending', '=', True)])
        # Braces as well as belt: the flag on a record predates the gate in
        # write(), and a batch built today should not carry yesterday's
        # accounting pseudo-products.
        products = products.filtered(lambda p: p._metabooks_is_book())
        if self.task == sheet.TASK_NEW:
            products = products.filtered(lambda p: not p._metabooks_is_known())
        elif self.task == sheet.TASK_UPDATE:
            products = products.filtered(lambda p: p._metabooks_is_known())
        return products

    @staticmethod
    def _group_by_imprint(products):
        grupos = {}
        for product in products:
            grupos.setdefault(product.metabooks_vendor_id or '', []).append(
                product)
        return grupos

    def _action_show(self, batches):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Batches for this round"),
            'res_model': self._name,
            'view_mode': 'list,form',
            'domain': [('id', 'in', batches.ids)],
            'target': 'current',
        }

    def _build_line(self, product):
        line = self.env['metabooks.export.line'].create({
            'batch_id': self.id,
            'product_id': product.id,
            'gtin': product._metabooks_gtin(),
            'title': (product.metabooks_book_title or product.name or '')[:200],
        })
        history = self._tracked_since(product, product.metabooks_export_last_track)
        columns = set()
        for field in history:
            columns.update(mapping.columns_for(field))
        # A book can be pending without usable history -- tracking added later,
        # a write that bypassed the chatter. Better to send every mapped column
        # than to send an empty row, so fall back to the whole record.
        #
        # Mas só quando o corte NUNCA foi carimbado. Com um corte de verdade,
        # "nada no chatter desde ele" quer dizer "nada a dizer" -- e cair no
        # manda-tudo aqui devolvia à Metabooks a ficha que ela mesma nos deu,
        # que é o buraco que o carimbo veio fechar.
        if not columns and not product.metabooks_export_last_track:
            line.no_history = True
            columns = set(mapping.BY_COLUMN)

        changes = []
        for column in sorted(columns):
            field = mapping.BY_COLUMN[column][0]
            new = product._metabooks_cell(column)
            old = history.get(field, {}).get('old')
            if new is False and old is None:
                continue
            # Edited and put back: the chatter remembers the round trip, but
            # Metabooks has nothing to learn from it.
            if old is not None and self._as_text(old) == self._as_text(new):
                continue
            never = self._never_really_filled(field, old, new)
            changes.append((0, 0, {
                'column': column,
                'field_name': field,
                'old_value': self._as_text(old),
                'new_value': self._as_text(new),
                'never_filled': never,
                # Visible but out of the envelope: the operator should be able
                # to see that the column was looked at, without the batch
                # dying over a value the house never set.
                'selected': not never,
            }))
        line.change_ids = changes
        return line

    def _never_really_filled(self, field, old, new):
        """Empty now, and the "before" was only Odoo's own default.

        A book with no price reads, in the chatter, as list_price 1.00 -> 0.00,
        because 1.00 is what Odoo puts there when a product is born and the
        import wrote over it. Read literally that is a cleared field, and the
        check refused the whole batch over it. But nobody cleared anything and
        Metabooks never received R$ 1,00 from us: the price was simply never
        filled in. The two cases need different remedies -- restore the value,
        versus type one for the first time -- so they must not share a message.
        """
        if self._as_text(new) or old is None:
            return False
        default = self.env['product.template']._fields[field].default
        if default is None:
            return False
        if callable(default):
            try:
                default = default(self.env['product.template'])
            except Exception:          # a default that needs a real record
                return False
        return self._as_text(default) == self._as_text(old)

    def _tracked_since(self, product, after_track_id):
        """{field name: {'old': value}} from the chatter.

        Only the oldest recorded old value matters: if a title went A -> B -> C
        since the last send, what Metabooks needs to know is that it was A and
        is now C. The new value is read live off the record rather than from
        tracking, so an edit made outside the chatter cannot make us send a
        stale one.
        """
        Tracking = self.env['mail.tracking.value']
        domain = [
            ('mail_message_id.model', '=', 'product.template'),
            ('mail_message_id.res_id', '=', product.id),
            ('field_id.name', 'in', list(mapping.WATCHED_FIELDS)),
        ]
        if after_track_id:
            domain.append(('id', '>', after_track_id))
        history = {}
        for track in Tracking.search(domain, order='id asc'):
            name = track.field_id.name
            if name in history:
                continue
            history[name] = {'old': self._tracking_old_value(track)}
        return history

    @staticmethod
    def _tracking_old_value(track):
        """Read the column mail.tracking.value stored this field in.

        Dispatch on the field type rather than taking the first non-empty
        column: a page count that went from 0 to 300 has a meaningful old value
        of zero, and scanning for truthiness would report it as blank.
        """
        suffix = _TRACKING_COLUMN.get(track.field_id.ttype)
        if suffix:
            return track['old_value_%s' % suffix]
        for suffix in ('char', 'text', 'datetime', 'float', 'integer'):
            value = track['old_value_%s' % suffix]
            if value not in (False, None, ''):
                return value
        return None

    @staticmethod
    def _as_text(value):
        if value is None:
            return ''
        if value is False:
            return ''
        if hasattr(value, 'strftime'):
            return fields.Date.to_string(value)
        return str(value)

    def _imprints(self):
        """The imprint codes actually present among the ticked books."""
        return {line.product_id.metabooks_vendor_id or ''
                for line in self.line_ids.filtered('selected')}

    # ---------------------------------------------------------------- #
    #  Selecting
    # ---------------------------------------------------------------- #

    def action_select_all(self):
        self.ensure_one()
        self._assert_open()
        self.line_ids.selected = True

    def action_select_none(self):
        self.ensure_one()
        self._assert_open()
        self.line_ids.selected = False

    # ---------------------------------------------------------------- #
    #  Checking
    # ---------------------------------------------------------------- #

    def action_check(self):
        """Everything we can catch before they do, at midnight, by e-mail."""
        self.ensure_one()
        self._assert_open()
        self._raise_on_problems()
        chosen = self.line_ids.filtered('selected')
        self.state = 'checked'
        self.message_post(body=_(
            "Checked: %(books)s book(s), %(changes)s field change(s).",
            books=len(chosen), changes=len(chosen.change_ids)))
        return True

    def _raise_on_problems(self):
        problems = self._problems()
        if problems:
            raise UserError(
                _("Metabooks would reject this file:\n\n• %s")
                % '\n• '.join(problems))

    def _problems(self):
        self.ensure_one()
        chosen = self.line_ids.filtered('selected')
        if not chosen:
            raise UserError(_("Nothing is selected to send."))

        problems = []
        if not self.mb_id:
            problems.append(_("The MB ID Editor is empty; the file name needs it."))

        # A file is signed by one publisher. Batches are split by imprint when
        # prepared, but books can be added by hand afterwards, and a mixed file
        # would file someone else's titles under this MB ID.
        selos = self._imprints()
        if len(selos) > 1:
            problems.append(_(
                "This batch mixes %(n)s imprints (%(list)s), and the file is "
                "signed by one. Press Fetch changes to split it, or untick the "
                "books that do not belong to %(mine)s.",
                n=len(selos), list=', '.join(sorted(s or _("no MB ID")
                                                    for s in selos)),
                mine=self.mb_id or _("this batch")))
        elif selos and self.mb_id and self.mb_id not in selos:
            problems.append(_(
                "The MB ID Editor says %(mine)s, but the books belong to "
                "%(theirs)s.",
                mine=self.mb_id, theirs=', '.join(sorted(
                    s or _("no MB ID") for s in selos))))

        seen = {}
        for line in chosen:
            label = line.title or line.product_id.display_name
            if not line.gtin:
                problems.append(_("%s: no ISBN/barcode.", label))
            elif len(line.gtin) != 13:
                problems.append(_(
                    "%(book)s: ISBN %(gtin)s is not 13 digits.",
                    book=label, gtin=line.gtin))
            elif line.gtin in seen:
                problems.append(_(
                    "%(book)s and %(other)s share the ISBN %(gtin)s.",
                    book=label, other=seen[line.gtin], gtin=line.gtin))
            else:
                seen[line.gtin] = label

            if self.task in sheet.KEY_ONLY_TASKS:
                continue
            picked = line.change_ids.filtered('selected')
            if not picked:
                problems.append(_(
                    "%s: no change is ticked, so the row would be empty.",
                    label))

            # A cleared field cannot ride in the sheet: Metabooks reads a blank
            # cell as "leave this alone", and wiping one needs an explicit
            # marker ($$, -1, 11/11/1111) which we do not write yet -- and which
            # their documentation does not say every column accepts. Sending the
            # row anyway would look like the change went through when it did
            # not, so say so instead of guessing.
            empty = [c for c in picked if not c.new_value and c.old_value]
            cleared = [c.column for c in empty if not c.never_filled]
            if cleared:
                problems.append(_(
                    "%(book)s: %(cols)s was cleared here, and clearing a field "
                    "at Metabooks needs a deletion marker this export does not "
                    "write yet. Either put the value back, or leave this book "
                    "out of the batch and clear it in their panel.",
                    book=label, cols=', '.join(cleared)))
            never = [c.column for c in empty if c.never_filled]
            if never:
                problems.append(_(
                    "%(book)s: %(cols)s was never filled in -- the only "
                    "history is Odoo's own default. Type the value on the "
                    "product, or untick this change: an empty column is one "
                    "Metabooks leaves alone.",
                    book=label, cols=', '.join(never)))
            if self.task == sheet.TASK_NEW:
                filled = {c.column for c in picked if c.new_value}
                missing = [c for c in sheet.MANDATORY
                           if c != sheet.KEY_COLUMN and c not in filled]
                if missing:
                    problems.append(_(
                        "%(book)s: a new title needs %(cols)s.",
                        book=label, cols=', '.join(missing)))

        return problems

    # ---------------------------------------------------------------- #
    #  Generating
    # ---------------------------------------------------------------- #

    def action_generate(self):
        self.ensure_one()
        self._assert_open()
        # Always, not only from draft: a batch checked an hour ago can have had
        # books unticked since, and the file is what actually leaves.
        self._raise_on_problems()

        chosen = self.line_ids.filtered('selected')
        rows = [line._as_row(self.task) for line in chosen]
        data = sheet.write_workbook(rows)
        name = sheet.build_filename(
            self.task, self.mb_id, date.today(), self.free_text or 'Export')

        attachment = self.env['ir.attachment'].create({
            'name': name,
            'datas': base64.b64encode(data),
            'res_model': self._name,
            'res_id': self.id,
            'type': 'binary',
        })
        self.write({
            'filename': name,
            'attachment_id': attachment.id,
            'generated_on': fields.Datetime.now(),
            'generated_by': self.env.user.id,
            'state': 'generated',
        })
        self.message_post(
            body=_("Generated %(name)s: %(books)s book(s), %(changes)s change(s).",
                   name=name, books=len(chosen), changes=len(chosen.change_ids)),
            attachment_ids=attachment.ids)
        # No download: the file is filed in the chatter, and the reason to
        # generate is usually to send. Whoever wants the file presses Baixar.
        return True

    def action_download(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("Generate the file first."))
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % self.attachment_id.id,
            'target': 'self',
        }

    # ---------------------------------------------------------------- #
    #  Delivering
    # ---------------------------------------------------------------- #

    def action_send_ftp(self):
        """Upload the file to Metabooks and, if it took, let the books go.

        One button, two steps that only make sense together: the STOR is what
        delivers, and clearing the queue is what records it. A failed upload
        raises before anything is written, so the books stay pending and the
        batch stays generated -- press again, or fall back to download +
        Mark as Sent.
        """
        self.ensure_one()
        self._assert_open()
        # Before generating, not after: a UserError rolls the request back, so
        # a file generated first would be lost anyway, and saying otherwise
        # would be a lie on screen.
        self._refuse_if_neutralized()
        # One click for the whole thing: generating is a step towards sending,
        # not a separate errand. The file is filed either way, so pressing this
        # from Draft leaves the same paper trail as pressing Gerar planilha
        # first.
        if self.state != 'generated':
            self.action_generate()
        self._deliver()
        self._mark_sent(_(
            "Sent %(name)s to Metabooks by FTP (%(host)s/%(folder)s): "
            "%(books)s book(s) left the queue. Their confirmation e-mail "
            "arrives after midnight.",
            name=self.filename, host=FTP_HOST, folder=FTP_FOLDER,
            books=len(self.line_ids.filtered('selected'))))
        return True

    def action_mark_sent(self):
        """Confirm a file uploaded by hand reached Metabooks, and let the books go.

        The manual path, kept beside the FTP button: only the person who did
        the upload knows whether it worked. Clearing the pending flag on
        generation instead would silently lose changes whenever an upload
        failed.
        """
        self.ensure_one()
        if self.state != 'generated':
            raise UserError(_("Generate the file before marking it as sent."))
        self._mark_sent(_(
            "Marked as delivered to Metabooks: %s book(s) left the queue. "
            "Their confirmation e-mail arrives after midnight.",
            len(self.line_ids.filtered('selected'))))
        return True

    def _mark_sent(self, body):
        chosen = self.line_ids.filtered('selected')
        products = chosen.product_id
        now = fields.Datetime.now()
        # Where each book's history stood before this file: without it, a book
        # the Metabooks report later refuses cannot be put back -- the cut-off
        # would swallow the very changes the file failed to deliver.
        for line in chosen:
            line.track_before = line.product_id.metabooks_export_last_track
        # Everything tracked up to here is what this file carried; anything
        # recorded after it is a change we still owe them.
        cut_off = self.env['mail.tracking.value'].search(
            [], order='id desc', limit=1).id or 0
        products.with_context(metabooks_from_sync=True).write({
            'metabooks_export_pending': False,
            'metabooks_export_pending_since': False,
            'metabooks_export_last': now,
            'metabooks_export_last_track': cut_off,
        })
        self.write({'state': 'sent', 'sent_on': now, 'sent_by': self.env.user.id})
        self.message_post(body=body)

    def _deliver(self):
        """Hand the file to Metabooks over FTP.

        Any failure -- wrong password, user not enabled for FTP by their
        support, firewall on the passive ports, network -- comes back as one
        UserError naming the server's own words. The transaction rolls back
        with it, so nothing is marked.
        """
        self.ensure_one()
        self._refuse_if_neutralized()
        if not self.attachment_id:
            raise UserError(_("Generate the file first."))
        username, password = self._ftp_credentials()
        data = base64.b64decode(self.attachment_id.datas)
        try:
            self._ftp_upload(username, password, self.filename, data)
        except ftplib.all_errors as exc:
            _logger.warning("Metabooks FTP upload of %s failed: %s",
                            self.filename, exc)
            raise UserError(_(
                "Metabooks did not take the file (%(host)s): %(error)s\n\n"
                "Nothing was marked; the books are still in the queue. Check "
                "the Metabooks username and password in Settings, and that "
                "their support has enabled FTP for this user.",
                host=FTP_HOST, error=exc)) from exc

    def _refuse_if_neutralized(self):
        """A copy of production is still production's data and password.

        An upload from dev or staging reaches the real Metabooks and overwrites
        the real catalogue with whatever someone was trying out. Both clones
        mark themselves neutralized when they are made; that mark is what stops
        the file. Checked in two places on purpose: at the button, so the
        person is told before anything happens, and inside _deliver(), so no
        other caller can slip past.
        """
        if self.env['ir.config_parameter'].sudo().get_param(
                'database.is_neutralized'):
            raise UserError(_(
                "This database is a copy for testing, so nothing is sent to "
                "Metabooks from here. Press Gerar planilha to produce the "
                "file and check it -- that part works. Real delivery happens "
                "in production."))

    def _ftp_credentials(self):
        icp = self.env['ir.config_parameter'].sudo()
        username = icp.get_param('metabooks_username')
        password = icp.get_param('metabooks_password')
        if not (username and password):
            raise UserError(_(
                "Set the Metabooks username and password in Settings. FTP "
                "uses the same ones as the API."))
        return username, password

    @api.model
    def test_ftp(self):
        """Bate na porta do FTP e volta. Devolve o erro em texto, ou False.

        Existe porque são DUAS portas com a mesma chave: a API e o FTP. O
        suporte deles habilita o FTP por usuário, então a senha certa pode
        autenticar na API e ser recusada aqui -- e isso só aparecia na hora de
        entregar a planilha, com o lote pronto e a pessoa esperando.

        Não sobe arquivo: entra, troca para passivo e abre a pasta de destino,
        que é o que a entrega vai precisar. Devolve texto em vez de levantar,
        para que quem chama possa dizer o que funcionou junto com o que não.
        """
        try:
            username, password = self._ftp_credentials()
        except UserError as exc:
            return exc.args[0]
        try:
            self._ftp_probe(username, password)
        except ftplib.all_errors as exc:
            _logger.warning("Metabooks FTP test failed: %s", exc)
            return str(exc)
        return False

    @staticmethod
    def _ftp_probe(username, password):
        """A chamada de rede, sozinha, para os testes ficarem no lugar dela."""
        with ftplib.FTP(FTP_HOST, timeout=FTP_TIMEOUT) as ftp:
            ftp.login(username, password)
            ftp.set_pasv(True)
            ftp.cwd(FTP_FOLDER)

    @staticmethod
    def _ftp_upload(username, password, filename, data):
        """The network call, alone, so tests can stand in for it."""
        with ftplib.FTP(FTP_HOST, timeout=FTP_TIMEOUT) as ftp:
            ftp.login(username, password)
            ftp.set_pasv(True)
            ftp.cwd(FTP_FOLDER)
            ftp.storbinary('STOR %s' % filename, io.BytesIO(data))

    # ---------------------------------------------------------------- #

    def action_open_report(self):
        """Read Metabooks' answer for this batch."""
        self.ensure_one()
        acao = self.env['ir.actions.act_window']._for_xml_id(
            'liber_metabooks_integration.action_metabooks_import_report')
        acao['context'] = {'default_batch_id': self.id}
        return acao

    def action_cancel(self):
        self.ensure_one()
        if self.state == 'sent':
            raise UserError(_("A batch that was sent cannot be cancelled."))
        self.state = 'cancel'

    def action_reset(self):
        self.ensure_one()
        if self.state == 'sent':
            raise UserError(_("A batch that was sent cannot be reopened."))
        self.state = 'draft'

    def _assert_open(self):
        if self.state in ('sent', 'cancel'):
            raise UserError(_("This batch is closed."))


class MetabooksExportLine(models.Model):
    _name = 'metabooks.export.line'
    _description = 'Metabooks Export Line'
    _order = 'title, id'

    batch_id = fields.Many2one(
        'metabooks.export.batch', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one(
        'product.template', string='Book', required=True, ondelete='restrict')
    selected = fields.Boolean(default=True)
    gtin = fields.Char('ISBN', readonly=True)
    title = fields.Char(readonly=True)
    change_ids = fields.One2many('metabooks.export.change', 'line_id')
    change_count = fields.Integer(compute='_compute_change_count')
    no_history = fields.Boolean(
        readonly=True,
        help="No chatter history was found for this book, so every mapped "
             "field is being sent rather than just what changed.")
    track_before = fields.Integer(
        readonly=True, copy=False,
        help="Where this book's history stood before the file was sent, so a "
             "book Metabooks refuses can be put back exactly where it was.")
    rejected = fields.Boolean(
        readonly=True, copy=False,
        help="Metabooks refused this book in their upload report.")
    error_code = fields.Char(readonly=True, copy=False)
    error_message = fields.Char(readonly=True, copy=False)

    def _refuse(self, code, message):
        """Metabooks refused this line: record why and put the book back.

        Their refusal is of the whole record, not of the offending column, so
        everything this row carried -- keywords, Thema, BISAC -- never landed.
        Restoring the cut-off is what makes the next round pick those changes
        up again.
        """
        self.ensure_one()
        self.write({
            'rejected': True,
            'error_code': code or '',
            'error_message': (message or '')[:500],
        })
        self.product_id.with_context(metabooks_from_sync=True).write({
            'metabooks_export_pending': True,
            'metabooks_export_pending_since': fields.Datetime.now(),
            'metabooks_export_last_track': self.track_before or 0,
        })

    @api.depends('change_ids', 'change_ids.selected')
    def _compute_change_count(self):
        for line in self:
            line.change_count = len(line.change_ids.filtered('selected'))

    def _as_row(self, task):
        """One spreadsheet row: the key, an anchor, and what changed."""
        self.ensure_one()
        values = {sheet.KEY_COLUMN: self.gtin}
        changed = set()
        if task in sheet.KEY_ONLY_TASKS:
            return {'values': values, 'changed': changed}

        # The title rides along unmarked even when it did not change: a row of
        # a bare ISBN and a loose price is unreadable, and re-sending a title we
        # own is harmless.
        title = self.product_id._metabooks_cell('Título')
        if title:
            values['Título'] = title

        for change in self.change_ids.filtered('selected'):
            value = self.product_id._metabooks_cell(change.column)
            if value is False:
                continue
            values[change.column] = value
            changed.add(change.column)
        return {'values': values, 'changed': changed}


class MetabooksExportChange(models.Model):
    _name = 'metabooks.export.change'
    _description = 'Metabooks Export Change'
    _order = 'column, id'

    line_id = fields.Many2one(
        'metabooks.export.line', required=True, ondelete='cascade', index=True)
    batch_id = fields.Many2one(
        related='line_id.batch_id', store=True, index=True)
    product_id = fields.Many2one(related='line_id.product_id', store=True)
    selected = fields.Boolean(
        default=True,
        help="Untick to leave this one field out. The book still goes; the "
             "column simply is not written, and a column Metabooks does not "
             "receive is a column it leaves alone.")
    column = fields.Char('Metabooks Column', readonly=True)
    field_name = fields.Char('Odoo Field', readonly=True)
    old_value = fields.Char('Before', readonly=True)
    new_value = fields.Char('After', readonly=True)
    never_filled = fields.Boolean(
        'Never Filled In', readonly=True,
        help="The field is empty now and the only 'before' on record is the "
             "default Odoo writes when a product is created -- so nothing was "
             "cleared, the value was simply never typed. Born unticked.")
