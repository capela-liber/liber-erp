# -*- coding: utf-8 -*-
"""A planilha que vai anexa ao e-mail da cotação.

O PDF é para ler; a planilha é para trabalhar. O orçamentista da gráfica
recebe dez, vinte títulos numa cotação e precisa passar cada ficha para o
sistema dele -- fazer isso lendo PDF é digitação, e digitação é erro.

Uma linha por livro, com a ficha inteira mais a TIRAGEM, que não está no
cadastro do livro: vem da quantidade da linha do pedido, e é o primeiro
número que muda o preço.
"""

import base64
import csv
import io

from odoo import _, models

# Ponto e vírgula, e não vírgula: é o separador que o Excel em português
# entende sem perguntar nada. E BOM no começo, senão ele lê o UTF-8 como
# latin-1 e "Dimensões" chega "DimensÃµes".
SEPARADOR = ';'
CODIFICACAO = 'utf-8-sig'

COLUNAS = [
    ('ISBN', lambda l, p: p._metabooks_gtin()),
    ('Título', lambda l, p: p.metabooks_book_title or p.name),
    ('Tiragem', lambda l, p: int(l.product_qty)),
    ('Formato', lambda l, p: dict(
        p._fields['metabooks_product_form']._description_selection(p.env)
    ).get(p.metabooks_product_form, '')),
    ('Altura (mm)', lambda l, p: p._print_mm(p.metabooks_height)),
    ('Largura (mm)', lambda l, p: p._print_mm(p.metabooks_width)),
    ('Lombada (mm)', lambda l, p: p._print_mm(p.metabooks_thickness)),
    ('Páginas', lambda l, p: p.metabooks_page_count or ''),
    ('Peso (g)', lambda l, p: p._print_mm(p.metabooks_weight)),
    ('Encadernação', lambda l, p: dict(
        p._fields['metabooks_binding']._description_selection(p.env)
    ).get(p.metabooks_binding, '')),
    ('Cor da capa', lambda l, p: p.print_cover_colors or ''),
    ('Papel da capa', lambda l, p: p.print_cover_paper or ''),
    ('Acabamento da capa', lambda l, p: (p.print_cover_finish or '').strip()),
    ('Acabamentos', lambda l, p: ', '.join(p._print_finish_labels())),
    ('Largura da orelha (mm)', lambda l, p:
        p.print_flap_width if p.metabooks_has_flaps else ''),
    ('Cor do miolo', lambda l, p: p.print_body_colors or ''),
    ('Cadernos especiais', lambda l, p: p.print_body_extra_colors or ''),
    ('Papel do miolo', lambda l, p: p.print_body_paper or ''),
    ('Observações', lambda l, p: (p.print_notes or '').strip()),
]


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _print_spec_rows(self):
        """Uma linha por LINHA de pedido que seja livro, na ordem do pedido.

        Por linha e não por produto: o mesmo título pode aparecer duas vezes
        com tiragens diferentes, e são dois orçamentos.

        Na língua do FORNECEDOR, como o PDF já faz. Sem isto a planilha sai
        com "Paperback" e "Sewn" para quem lê "Brochura" e "Costurado" -- e
        quem lê é o orçamentista, não nós.
        """
        self.ensure_one()
        registro = self.with_context(lang=self.partner_id.lang or self.env.lang)
        linhas = []
        for linha in registro.order_line:
            livro = linha.product_id.product_tmpl_id
            if not (livro and livro._print_spec_is_relevant(livro)):
                continue
            linhas.append([leitor(linha, livro) for _rotulo, leitor in COLUNAS])
        return linhas

    def _print_spec_csv(self):
        """A planilha em bytes, ou False quando não há livro no pedido."""
        self.ensure_one()
        linhas = self._print_spec_rows()
        if not linhas:
            return False
        buffer = io.StringIO()
        escritor = csv.writer(buffer, delimiter=SEPARADOR,
                              quoting=csv.QUOTE_MINIMAL, lineterminator='\r\n')
        escritor.writerow([rotulo for rotulo, _leitor in COLUNAS])
        escritor.writerows(linhas)
        return buffer.getvalue().encode(CODIFICACAO)

    def _print_spec_attachment(self):
        """Cria (ou refaz) o anexo da planilha neste pedido.

        Refaz de propósito: entre um envio e outro o cadastro muda, e anexo
        velho no e-mail é pior que anexo nenhum. Um por pedido, sempre.
        """
        self.ensure_one()
        dados = self._print_spec_csv()
        if not dados:
            return self.env['ir.attachment']
        nome = _("Ficha técnica %s.csv") % (self.name or '').replace('/', '-')
        antigos = self.env['ir.attachment'].search([
            ('res_model', '=', 'purchase.order'), ('res_id', '=', self.id),
            ('name', 'like', 'Ficha técnica%'), ('mimetype', '=', 'text/csv'),
        ])
        antigos.unlink()
        return self.env['ir.attachment'].create({
            'name': nome,
            'datas': base64.b64encode(dados),
            'mimetype': 'text/csv',
            'res_model': 'purchase.order',
            'res_id': self.id,
        })
