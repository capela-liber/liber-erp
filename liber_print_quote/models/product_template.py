# -*- coding: utf-8 -*-
"""A ficha técnica do livro, do jeito que a gráfica precisa ler.

Duas coisas moram aqui, e nenhuma delas cabe no liber_metabooks_integration:

* o acabamento que a ONIX **não** nomeia. A lista 175 tem "laminada" (B415) e
  para aí -- não distingue fosca de brilho, não conhece reserva nem verniz, e
  do miolo só sabe dizer se o papel é alcalino ou permanente. Gramatura, tipo
  (pólen, offset, couché) e cores de impressão não existem na norma. Como a
  Metabooks só aceita código de lista, isto nunca vai para lá: é texto livre;
* a tradução da ficha para uma lista de linhas legíveis, que o PDF imprime sem
  precisar saber nada sobre ONIX.
"""

from odoo import api, fields, models

from odoo.addons.liber_metabooks_integration.services import onix_codes

# Notação da gráfica: cores na frente x cores no verso.
COLORS = [
    ('1x0', '1x0'), ('1x1', '1x1'),
    ('2x0', '2x0'), ('2x1', '2x1'), ('2x2', '2x2'),
    ('4x0', '4x0'), ('4x1', '4x1'), ('4x4', '4x4'),
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    print_cover_finish = fields.Text(
        'Cover Finish',
        help="O que a ONIX não nomeia: laminação fosca ou brilho, reserva, "
             "verniz, hotstamp em cor, relevo. Vai no PDF que a gráfica orça, "
             "e não para a Metabooks -- lá só entra código de lista.")
    print_cover_paper = fields.Char(
        'Cover Paper',
        help="O papel da capa e a gramatura: cartão triplex 250g, supremo "
             "300g. A ONIX não tem campo para isso.")
    print_body_paper = fields.Char(
        'Body Paper',
        help="O papel do miolo e a gramatura: pólen soft 80g, offset 90g.")

    # A orelha existe na ONIX como bandeira (B504, "com orelhas") e para aí.
    # Quanto ela mede é o que decide o tamanho da folha da capa, e portanto o
    # preço -- sem a medida, a gráfica devolve a cotação como pergunta.
    print_flap_width = fields.Integer(
        'Flap Width (mm)',
        help="A largura de cada orelha, em milímetros. Só faz sentido com "
             "orelhas marcadas, e é o que define a folha da capa.")

    # Cores em notação de gráfica: frente x verso. 4x0 é colorido de um lado
    # só; 1x1, preto nos dois. A ONIX não tem nada disso -- ela descreve o
    # livro pronto, não como imprimi-lo.
    print_cover_colors = fields.Selection(
        COLORS, 'Cover Colors',
        help="Cores da capa, frente x verso. 4x0 é o comum; 4x4 quando a "
             "parte de dentro da capa também é impressa.")
    print_body_colors = fields.Selection(
        COLORS, 'Body Colors',
        help="Cores do miolo inteiro. Caderno fora do padrão vai no campo "
             "ao lado.")
    print_body_extra_colors = fields.Char(
        'Special Signatures',
        help="O caderno que foge da regra: \"1 caderno 4x4, páginas 65-80\". "
             "É o que mais encarece e o que mais se esquece de dizer.")

    print_notes = fields.Text(
        'General Notes',
        help="O que não cabe em campo nenhum e a gráfica precisa saber: "
             "encarte, brinde, embalagem, prazo, referência de cor. Sai por "
             "último no PDF, depois da ficha.")

    def _print_spec(self):
        """A ficha em linhas (rótulo, valor), na ordem em que a gráfica lê.

        Os rótulos estão em português NA FONTE, contra a convenção da casa, e
        de propósito. O caminho normal -- literal em inglês e `.po` por cima --
        não entrega: medido em 09/09/2026, o leitor de `.po` do Odoo devolvia
        para este módulo entradas que já não existiam no arquivo e ignorava as
        que existiam, e o PDF saía metade em inglês para a gráfica. Rótulo de
        CAMPO continua traduzido pelo caminho certo (ver hooks.py); estes aqui
        são os poucos que não têm campo por trás.

        Se um dia a casa precisar cotar impressão fora do Brasil, isto volta a
        ser `_()` -- e aí o .po tem de ser conferido com o leitor, não com o
        `msgfmt`.

        Devolver lista pronta em vez de deixar o QWeb decidir é o que mantém
        isto testável: o PDF é difícil de medir, uma lista não é.
        """
        self.ensure_one()
        # Os rótulos vêm da SELEÇÃO do campo, não da tabela ONIX crua: é a
        # seleção que passa pelo .po, e a gráfica lê em português. Lendo a
        # constante, "Formato" saía "Paperback" mesmo com a tela traduzida.
        formatos = dict(self._fields['metabooks_product_form']
                        ._description_selection(self.env))
        encadernacoes = dict(self._fields['metabooks_binding']
                             ._description_selection(self.env))

        linhas = []
        if self.metabooks_product_form:
            linhas.append(('Formato', formatos.get(
                self.metabooks_product_form, self.metabooks_product_form)))
        if any((self.metabooks_height, self.metabooks_width,
                self.metabooks_thickness)):
            linhas.append(('Dimensões', '%s x %s x %s mm' % (
                self._print_mm(self.metabooks_height),
                self._print_mm(self.metabooks_width),
                self._print_mm(self.metabooks_thickness))))
        if self.metabooks_page_count:
            linhas.append(('Páginas', str(self.metabooks_page_count)))
        if self.metabooks_weight:
            linhas.append(('Peso', "%s g" % self._print_mm(self.metabooks_weight)))
        if self.metabooks_binding:
            linhas.append(('Encadernação', encadernacoes.get(
                self.metabooks_binding, self.metabooks_binding)))

        if self.print_cover_colors:
            linhas.append(('Cor da capa', self.print_cover_colors))
        cores_miolo = self.print_body_colors or ''
        if self.print_body_extra_colors:
            cores_miolo = ('%s (%s)' % (cores_miolo, self.print_body_extra_colors)
                           if cores_miolo else self.print_body_extra_colors)
        if cores_miolo:
            linhas.append(('Cor do miolo', cores_miolo))

        marcados = self._print_finish_labels()
        if marcados:
            linhas.append(('Acabamento', ', '.join(marcados)))
        if self.metabooks_has_flaps and self.print_flap_width:
            linhas.append(('Largura da orelha', "%s mm" % self.print_flap_width))
        if self.print_cover_paper:
            linhas.append(('Papel da capa', self.print_cover_paper.strip()))
        if self.print_cover_finish:
            linhas.append(('Acabamento da capa', self.print_cover_finish.strip()))
        if self.print_body_paper:
            linhas.append(('Papel do miolo', self.print_body_paper.strip()))
        if self.print_notes:
            linhas.append(('Observações', self.print_notes.strip()))
        return linhas

    def _print_finish_labels(self):
        """Os acabamentos ONIX marcados, pelo rótulo do próprio campo.

        Lê o rótulo em vez de repetir uma tabela de nomes: campo novo em
        `FINISH_BY_FIELD` aparece aqui sozinho, já traduzido pelo .po.
        """
        self.ensure_one()
        rotulos = []
        for campo in onix_codes.FINISH_BY_FIELD:
            if self._fields.get(campo) and self[campo]:
                rotulos.append(self._fields[campo].get_description(self.env)['string'])
        if self.metabooks_has_dust_jacket:
            rotulos.append(self._fields['metabooks_has_dust_jacket']
                           .get_description(self.env)['string'])
        return rotulos

    @staticmethod
    def _print_mm(valor):
        """Sem casa decimal quando não há: "210", não "210.0"."""
        if not valor:
            return '-'
        return str(int(valor)) if float(valor) == int(valor) else str(valor)

    @api.model
    def _print_spec_is_relevant(self, produto):
        """Só livro ganha ficha no PDF: parafuso e frete não têm lombada."""
        return bool(produto) and produto._metabooks_is_book()
