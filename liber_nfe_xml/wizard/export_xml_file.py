# -*- coding: utf-8 -*-
"""Pacote de XMLs de um ou mais meses, do jeito que o contador pede.

O que existia era o download da SELEÇÃO da lista: a tela manda os ids na URL e
o servidor grava cada XML no `data_dir` antes de zipar. Serve para meia dúzia
de notas; para um mês inteiro, não — e deixava de fora justamente o que a
escrituração precisa junto, que são os eventos (cancelamento e carta de
correção) das notas do período.

Aqui os meses se marcam numa lista, inclusive salteados (março e julho, sem
abril), o ZIP se monta em memória e vem com uma planilha de conferência.
"""

import base64
import csv
import io
import logging
import re
import zipfile
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Lidos em lotes para que os blobs não fiquem todos no cache do ORM de uma vez
# (a base tem dezenas de milhares de XMLs). Mesmo tamanho que o painel usa.
CHUNK = 500

# Pastas dentro do ZIP. O contador separa entrada de saída antes de qualquer
# outra coisa, então a pasta já entrega isso pronto.
FOLDER_BY_DIRECTION = {
    'out': 'saidas',
    'in': 'entradas',
    'internal': 'internas',
    'external': 'outras',
}
FOLDER_CANCELLED = 'canceladas'
FOLDER_EVENTS = 'eventos'

NO_DATE = '0000-00'   # ordena antes de qualquer mês de verdade


def _slug(text):
    """Nome de pasta seguro dentro do ZIP."""
    cleaned = re.sub(r'[^\w\s.-]', '', text or '', flags=re.UNICODE).strip()
    return re.sub(r'\s+', ' ', cleaned) or 'sem-nome'


class ExportXMLWizard(models.TransientModel):
    _name = 'nfe.xml.export'
    _description = "Export XML Files"

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
        domain="[('id', 'in', allowed_company_ids)]",
        help="One company per package: each one has its own bookkeeping.")
    month_ids = fields.One2many('nfe.xml.export.month', 'wizard_id',
                                string='Months')

    include_out = fields.Boolean(string='Issued by us', default=True)
    include_in = fields.Boolean(string='Received', default=True)
    include_internal = fields.Boolean(string='Between our companies', default=True)

    state = fields.Selection([('choose', 'Choose'), ('done', 'Done')],
                             default='choose', readonly=True)
    summary = fields.Text(readonly=True)
    file = fields.Binary(string='Package', readonly=True, attachment=False)
    file_name = fields.Char(readonly=True)

    # ------------------------------------------------------------------
    # a lista de meses
    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        company = vals.get('company_id') or self.env.company.id
        if 'month_ids' in fields_list:
            vals['month_ids'] = self._month_lines(company)
        return vals

    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Trocar de empresa refaz a lista: os meses são os dela."""
        self.month_ids = [(5, 0, 0)] + self._month_lines(self.company_id.id)

    @api.model
    def _month_lines(self, company_id):
        """Um mês por linha, com quantas notas tem, do mais recente ao antigo.

        Notas sem data de emissão ganham a sua própria linha em vez de sumirem
        do pacote sem ninguém notar - são poucas, mas são notas.
        """
        if not company_id:
            return []
        Panel = self.env['nfe.xml.panel']
        groups = Panel._read_group(
            [('company_id', '=', company_id)],
            groupby=['file_create_date:month'],
            aggregates=['__count'],
        )
        lines = []
        for month, count in groups:
            if not count:
                continue
            if not month:
                lines.append((0, 0, {
                    'name': _('No date'), 'sort_key': NO_DATE,
                    'no_date': True, 'n_notes': count,
                }))
                continue
            last_day = month + relativedelta(months=1, days=-1)
            lines.append((0, 0, {
                'name': month.strftime('%Y-%m'),
                'sort_key': month.strftime('%Y-%m'),
                'date_from': month, 'date_to': last_day, 'n_notes': count,
            }))
        lines.sort(key=lambda l: l[2]['sort_key'], reverse=True)
        return lines

    # ------------------------------------------------------------------
    # a exportação
    # ------------------------------------------------------------------
    def action_export(self):
        self.ensure_one()
        months = self.month_ids.filtered('selected')
        if not months:
            raise UserError(_("Tick at least one month to export."))
        directions = self._selected_directions()
        if not directions:
            raise UserError(_("Tick at least one kind of note: issued, "
                              "received or between our companies."))

        buffer = io.BytesIO()
        rows, tally = [], defaultdict(int)
        root = _slug(self.company_id.name)
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            taken = set()
            for month in months.sorted('sort_key'):
                self._write_month(archive, month, directions, rows, tally, root, taken)
            if not tally['notes'] and not tally['events']:
                raise UserError(_(
                    "Nothing to export: the months you ticked have no note of "
                    "the kinds selected."))
            archive.writestr('relacao.csv', self._relation_csv(rows))

        label = self._period_label(months)
        self.write({
            'state': 'done',
            'file': base64.b64encode(buffer.getvalue()),
            'file_name': 'XML-%s-%s.zip' % (root.replace(' ', ''), label),
            'summary': self._summary(tally, months),
        })
        _logger.info("nfe_xml export: %s, %s notas e %s eventos em %s mes(es)",
                     self.company_id.name, tally['notes'], tally['events'],
                     len(months))
        return self._reopen()

    def _selected_directions(self):
        chosen = []
        if self.include_out:
            chosen.append('out')
        if self.include_in:
            chosen.append('in')
        if self.include_internal:
            chosen.append('internal')
        # 'external' viaja junto com as recebidas: é nota que não é nossa, e
        # deixá-la fora sem dizer nada esconderia documento do contador.
        if self.include_in:
            chosen.append('external')
        return chosen

    def _write_month(self, archive, month, directions, rows, tally, root, taken):
        """Escreve um mês no ZIP: as notas, depois os eventos delas."""
        Panel = self.env['nfe.xml.panel']
        domain = [('company_id', '=', self.company_id.id)]
        if month.no_date:
            domain.append(('file_create_date', '=', False))
        else:
            domain += [('file_create_date', '>=', month.date_from),
                       ('file_create_date', '<=', month.date_to)]
        # nfe_direction em branco é nota antiga que nunca foi identificada;
        # entra com as recebidas para não desaparecer do pacote.
        directions_domain = ['|', ('nfe_direction', 'in', directions),
                             ('nfe_direction', '=', False)] \
            if 'in' in directions else [('nfe_direction', 'in', directions)]
        panels = Panel.search(domain + directions_domain, order='file_create_date, id')

        folder = '%s/%s' % (root, month.name)
        panel_ids = []
        for start in range(0, len(panels), CHUNK):
            chunk = panels[start:start + CHUNK]
            for panel in chunk:
                panel_ids.append(panel.id)
                if not panel.file:
                    tally['no_file'] += 1
                    continue
                sub = FOLDER_CANCELLED if panel.is_cancelled else \
                    FOLDER_BY_DIRECTION.get(panel.nfe_direction, 'outras')
                path = self._unique_path(
                    taken, '%s/%s' % (folder, sub),
                    panel.file_name or '%s-nfe.xml' % (panel.key or panel.id))
                archive.writestr(path, base64.b64decode(panel.file))
                tally['notes'] += 1
                rows.append(self._note_row(panel, path))
            chunk.invalidate_recordset(['file'])

        self._write_events(archive, month, folder, panel_ids, rows, tally, taken)

    def _write_events(self, archive, month, folder, panel_ids, rows, tally, taken):
        """Cancelamentos e cartas de correção do mês.

        Entram por dois caminhos, porque o contador precisa dos dois: o evento
        da nota que está no pacote (mesmo que o evento seja de outro mês), e o
        evento ocorrido no mês cuja nota não está na base.
        """
        Event = self.env['nfe.xml.cancel.event']
        clauses = []
        if panel_ids:
            clauses.append([('nfe_id', 'in', panel_ids)])
        if not month.no_date:
            # Os '&' explícitos importam: sem eles o '|' seguinte casa apenas
            # com os dois primeiros termos e a janela de datas passa a filtrar
            # TAMBÉM os eventos das notas do pacote - o cancelamento de uma
            # nota de março feito em abril sumia do ZIP.
            clauses.append(['&', '&',
                            ('nfe_id', '=', False),
                            ('event_date', '>=', month.date_from),
                            ('event_date', '<=', month.date_to)])
        if not clauses:
            return
        domain = clauses[0]
        for extra in clauses[1:]:
            domain = ['|'] + domain + extra
        events = Event.search(domain, order='event_date, id')
        for start in range(0, len(events), CHUNK):
            chunk = events[start:start + CHUNK]
            for event in chunk:
                if not event.file:
                    continue
                path = self._unique_path(
                    taken, '%s/%s' % (folder, FOLDER_EVENTS),
                    event.file_name or '%s-evt.xml' % (event.key or event.id))
                archive.writestr(path, base64.b64decode(event.file))
                tally['events'] += 1
                if event.event_kind == 'correction':
                    tally['corrections'] += 1
                rows.append(self._event_row(event, path))
            chunk.invalidate_recordset(['file'])

    @staticmethod
    def _unique_path(taken, folder, name):
        """Dois XMLs com o mesmo nome não podem sobrescrever um ao outro."""
        name = name.replace('/', '_').replace('\\', '_')
        path = '%s/%s' % (folder, name)
        if path not in taken:
            taken.add(path)
            return path
        stem, dot, ext = name.rpartition('.')
        stem = stem or name
        n = 2
        while True:
            candidate = '%s/%s-%s%s%s' % (folder, stem, n, dot, ext)
            if candidate not in taken:
                taken.add(candidate)
                return candidate
            n += 1

    # ------------------------------------------------------------------
    # a planilha de conferência
    # ------------------------------------------------------------------
    COLUMNS = ['chave', 'documento', 'numero', 'data', 'tipo', 'situacao',
               'cnpj_emitente', 'nome_emitente', 'cnpj_destinatario',
               'nome_destinatario', 'valor', 'observacao', 'arquivo']

    def _note_row(self, panel, path):
        directions = dict(panel._fields['nfe_direction'].selection)
        return {
            'chave': panel.key or '', 'documento': 'NFe',
            'numero': panel.danfe_no or '',
            'data': panel.file_create_date or '',
            'tipo': directions.get(panel.nfe_direction, ''),
            'situacao': _('Cancelled') if panel.is_cancelled else _('Valid'),
            'cnpj_emitente': panel.vendor_cnpj or '',
            'nome_emitente': panel.vendor_name or '',
            'cnpj_destinatario': panel.customer_cnpj or '',
            'nome_destinatario': panel.customer_name or '',
            'valor': ('%.2f' % (panel.danfe_value or 0.0)).replace('.', ','),
            'observacao': '', 'arquivo': path,
        }

    def _event_row(self, event, path):
        kinds = dict(event._fields['event_kind'].selection)
        note = event.nfe_id
        return {
            'chave': event.key or '', 'documento': kinds.get(event.event_kind, ''),
            'numero': note.danfe_no or '',
            'data': event.event_date and event.event_date.date() or '',
            'tipo': '', 'situacao': event.protocol or '',
            'cnpj_emitente': note.vendor_cnpj or '',
            'nome_emitente': note.vendor_name or '',
            'cnpj_destinatario': note.customer_cnpj or '',
            'nome_destinatario': note.customer_name or '',
            'valor': '',
            'observacao': (event.correction_text or event.reason or '').replace('\n', ' '),
            'arquivo': path,
        }

    def _relation_csv(self, rows):
        """CSV que o Excel brasileiro abre sem pedir nada: ';' e BOM."""
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=self.COLUMNS, delimiter=';',
                                extrasaction='ignore', lineterminator='\r\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: str(v) for k, v in row.items()})
        return out.getvalue().encode('utf-8-sig')

    # ------------------------------------------------------------------
    # resultado
    # ------------------------------------------------------------------
    @staticmethod
    def _period_label(months):
        names = months.sorted('sort_key').mapped('name')
        if len(names) == 1:
            return names[0]
        return '%s_%s' % (names[0], names[-1])

    def _summary(self, tally, months):
        notes = tally['notes']
        events = tally['events']
        corrections = tally['corrections']
        no_file = tally['no_file']
        counts = [
            (notes, _("%s XML(s) of notes")),
            (events, _("%s event(s): cancellations and correction letters")),
            (corrections, _("of which %s correction letter(s)")),
            (no_file, _("%s note(s) with no XML stored, listed nowhere")),
        ]
        lines = [_("Months: %s") % ', '.join(months.sorted('sort_key').mapped('name'))]
        lines += [label % count for count, label in counts if count]
        lines.append(_("The relacao.csv inside the ZIP lists every file."))
        return "\n".join(lines)

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Export XML File'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class ExportXMLMonth(models.TransientModel):
    _name = 'nfe.xml.export.month'
    _description = "Month to Export"
    _order = 'sort_key desc'

    wizard_id = fields.Many2one('nfe.xml.export', required=True, ondelete='cascade')
    # Nenhum destes é `readonly` no MODELO, e isso não é descuido: o servidor
    # monta as linhas em `default_get`, e campo readonly no modelo não volta do
    # cliente no create -- as linhas nasciam em branco, a tela mostrava meses
    # sem nome nem contagem e a exportação não achava nota nenhuma. Quem
    # segura a edição é a view, que os declara readonly.
    name = fields.Char()
    # Ordena e rotula sem depender da data, que a linha "sem data" não tem.
    sort_key = fields.Char()
    date_from = fields.Date()
    date_to = fields.Date()
    no_date = fields.Boolean()
    n_notes = fields.Integer(string='Notes')
    selected = fields.Boolean(string='Export')
