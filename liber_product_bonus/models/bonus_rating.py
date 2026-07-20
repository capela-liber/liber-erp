# -*- coding: utf-8 -*-
"""A nota do parceiro: nível e direção.

O caso que originou isto, nas palavras dele: "Mandei para um mesmo influencer
10 livros. Ele divulgou dois bem e os outros 5 meia boca, e depois silenciou."

    2 x Arrasou   = 26
    5 x Meia-boca = 25
    3 x Silêncio  =  0
                    51 em 10 -> média 5,1

Média 5,1 lê como "meia-boca constante", e é mentira: a pessoa começou ótima e
morreu. Qualquer número único -- somado OU médio -- apaga exatamente a
informação que decide o próximo envio. Daí nível E direção.

Três mecanismos, cada um consertando um problema real:

1. MÉDIA COM RECÊNCIA, nunca soma. Soma premia quem recebeu mais, não quem
   rende mais (ele mesmo apontou). E o peso cai com a idade: "divulgou bem em
   2019" não sustenta quem sumiu desde então.

2. ENCOLHIMENTO ("em teste"). Quem recebeu 1 livro e arrasou não pode aparecer
   com 13 no topo: amostra de 1 não é avaliação, é sorte. Abaixo do limiar não
   há nota, há "em teste (1/3)". Acima dele a nota nasce puxada para a média da
   casa e vai se soltando conforme o histórico cresce -- com 3 avaliações é um
   palpite tímido, com 20 é retrato fiel. É a média bayesiana clássica.

3. DIREÇÃO. Metade recente contra metade anterior, e uma seta. É a seta, não a
   nota, que diz "esse acabou".

O que este arquivo deliberadamente NÃO faz: ordenar a lista por nota. No dia em
que a tela ordenar por melhor nota, os "novo" e "em teste" caem para o fim,
ninguém rola até lá, e em dois anos a lista é os mesmos 30 nomes de sempre --
a casa para de descobrir gente. Mostrar, filtrar e agrupar: sim. Ranquear por
padrão: não.
"""
from odoo import _, api, fields, models

# Fibonacci, escolha dele: os saltos crescem, então "Arrasou" vale muito mais
# que proporcionalmente mais -- que é como funciona de verdade (uma cobertura
# excelente vale mais que cinco mornas). Parametrizável em Definições.
DEFAULT_POINTS = {'silence': 0.0, 'weak': 5.0, 'good': 8.0, 'great': 13.0}
DEFAULT_TEST_SIZE = 3        # avaliações para sair do "em teste"
DEFAULT_HALF_LIFE = 12       # meses até uma avaliação valer metade

# Direção: diferença mínima (em pontos) entre a metade recente e a anterior
# para chamar de subida ou queda. Abaixo disso é "constante" -- sem isto, ruído
# de uma avaliação vira uma seta dramática.
TREND_BAND = 1.5

# Ícone, não cor, e sem palavra: cor sozinha não diz O QUE é, e estes dois
# casos precisam ser lidos como convite, não como score baixo.
#
# Font Awesome (4.7, o que o Odoo empacota), escolha dele: fa-pagelines para o
# broto e fa-flask para o teste. Exige campo Html -- um Char escapa a marcação
# --, e daí vem um ganho: o title no próprio <i> dá tooltip POR CÉLULA, que é
# a "explicação no foco" de verdade; o help do campo só aparece no cabeçalho.
#
# O rótulo em texto (ICON_*) continua existindo para exportação, PDF e testes,
# onde marcação não serve para nada.
ICON_NEW = "\u2698"      # ⚘ broto: nunca recebeu -- é assim que se descobre gente
ICON_TESTING = "\u2697"  # ⚗ alambique: amostra pequena demais para um score honesto

# Um tico maior que o texto ao redor -- o ícone é o conteúdo da célula, não um
# adorno ao lado de uma palavra. Mas só um tico: a 1,5em ele dominava a linha
# inteira e a lista virava um mural de símbolos.
ICON_STYLE = "font-size:1.15em;vertical-align:-0.05em;"
TIP_NEW = ("Nunca recebeu. Sem histórico não há score — e isso é um convite: "
           "é assim que a casa descobre gente.")
TIP_TESTING = ("Em teste: %(n)s de %(total)s avaliações. Uma amostra pequena "
               "não é avaliação, é sorte — abaixo de %(total)s nenhum número "
               "seria honesto.")

# A explicação que aparece ao passar o mouse. Uma escala que precisa de manual
# ao lado da tela é uma escala que ninguém usa.
SCORE_HELP = (
    "⚘ nunca recebeu. Sem histórico não há score, e isso é um convite: é assim "
    "que a casa descobre gente.\n"
    "⚗ n/N — recebeu pouco, ainda em teste. Uma amostra de 1 não é avaliação, "
    "é sorte; abaixo de N avaliações nenhum número seria honesto.\n"
    "0 a 13 — média dos resultados ponderada por recência (o recente pesa "
    "mais), encolhida para a média da casa enquanto o histórico é curto.\n"
    "↑ → ↓ — a direção compara os envios recentes com os anteriores. É a seta, "
    "não o número, que diz se a pessoa está esquentando ou acabando.\n"
    "Os pontos e os cortes ficam em Definições > Bonificações.")


class BonusRatingMixin(models.AbstractModel):
    """O cálculo, isolado: o partner o usa, e quem mais precisar também."""
    _name = 'bonus.rating.mixin'
    _description = 'Bonus Rating Computation'

    @api.model
    def _rating_settings(self):
        """Os parâmetros da casa. Tudo em Definições > Bonificações."""
        get = self.env['ir.config_parameter'].sudo().get_param
        points = {}
        for key, default in DEFAULT_POINTS.items():
            raw = get('product_bonus.points_%s' % key)
            try:
                points[key] = float(raw) if raw not in (None, '', False) else default
            except (TypeError, ValueError):
                points[key] = default

        def _int(param, default):
            raw = get(param)
            try:
                value = int(float(raw)) if raw not in (None, '', False) else default
            except (TypeError, ValueError):
                return default
            return value if value > 0 else default

        return (points,
                _int('product_bonus.rating_test_size', DEFAULT_TEST_SIZE),
                _int('product_bonus.rating_half_life', DEFAULT_HALF_LIFE))

    @api.model
    def _rating_house_average(self, points):
        """A média da casa -- o prior para onde as notas pouco firmes puxam.

        Sem histórico nenhum a casa não tem média: usa o ponto do 'Divulgou'
        como neutro. Um prior otimista de propósito -- na dúvida, a casa aposta
        na pessoa, que é a política do módulo inteiro.
        """
        judged = self.env['product.bonus'].search([
            ('outcome', '!=', False), ('state', '!=', 'cancelled')])
        if not judged:
            return points.get('good', 8.0)
        total = sum(points.get(b.outcome, 0.0) for b in judged)
        return total / len(judged)

    @api.model
    def _rating_html(self, label, band, n=0, test_size=0):
        """O mesmo estado, marcado para a tela.

        Só para exibição: quem exporta, imprime ou testa usa o rótulo em texto.
        """
        if band == 'new':
            return ('<div style="text-align:center">'
                    '<i class="fa fa-pagelines" style="%s" title="%s"/></div>'
                    % (ICON_STYLE, TIP_NEW))
        if band == 'testing':
            # Só o ícone: o "n de N" já está no title, e na célula ele competia
            # com o próprio símbolo. O rótulo em TEXTO mantém a fração, porque
            # exportação e PDF não têm para onde passar o mouse.
            tip = TIP_TESTING % {'n': n, 'total': test_size}
            return ('<div style="text-align:center">'
                    '<i class="fa fa-flask" style="%s" title="%s"/></div>'
                    % (ICON_STYLE, tip))
        # text-align no próprio HTML: a classe da célula não atravessa o
        # widget html, então centralizar pela view não pegava.
        return ('<div style="text-align:center">%s</div>' % (label or ''))

    @api.model
    def _rating_for(self, bonuses):
        """(nota, rótulo, direção, n_avaliadas) para um conjunto de fichas.

        nota é None enquanto está em teste: sem dado suficiente, nenhum número
        é honesto.
        """
        points, test_size, half_life = self._rating_settings()
        judged = bonuses.filtered(
            lambda b: b.outcome and b.state != 'cancelled').sorted('date')
        n = len(judged)
        if not n:
            return None, ICON_NEW, '', 0
        if n < test_size:
            return None, "%s %s/%s" % (ICON_TESTING, n, test_size), '', n

        today = fields.Date.context_today(self)
        weighted = total_weight = 0.0
        for bonus in judged:
            months = ((today.year - bonus.date.year) * 12
                      + today.month - bonus.date.month) if bonus.date else 0
            weight = 0.5 ** (max(months, 0) / float(half_life))
            weighted += points.get(bonus.outcome, 0.0) * weight
            total_weight += weight

        # Encolhimento: test_size observações fictícias na média da casa.
        house = self._rating_house_average(points)
        score = ((weighted + house * test_size)
                 / (total_weight + test_size)) if total_weight else house

        # Direção: metades cruas (sem peso de recência -- aqui a comparação JÁ
        # é temporal, pesar de novo contaria o tempo duas vezes).
        half = n // 2
        older = judged[:half]
        recent = judged[n - half:]
        trend = ''
        if half:
            avg_old = sum(points.get(b.outcome, 0.0) for b in older) / len(older)
            avg_new = sum(points.get(b.outcome, 0.0) for b in recent) / len(recent)
            delta = avg_new - avg_old
            trend = '↑' if delta > TREND_BAND else '↓' if delta < -TREND_BAND else '→'

        return score, "%.0f %s" % (score, trend), trend, n
