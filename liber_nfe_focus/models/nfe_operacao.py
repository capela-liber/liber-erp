# -*- coding: utf-8 -*-
"""A operação fiscal: o CFOP sem o primeiro dígito.

O CFOP tem quatro dígitos e diz duas coisas de uma vez. Os três últimos dizem
**o que** a operação é; o primeiro diz **para onde** ela vai:

    saída    5 dentro do estado   6 interestadual   7 exterior
    entrada  1 dentro do estado   2 interestadual   3 exterior

A própria tabela do CONFAZ é organizada assim. Nos 619 códigos oficiais há 173
sufixos, e dentro do mesmo sentido as variantes repetem a descrição:

    101  →  1101 / 2101 / 3101   "compra para industrializacao"
            5101 / 6101 / 7101   "venda de producao do estabelecimento"

Tratar 5101 e 6101 como duas operações obrigava a configurar a mesma coisa duas
vezes e a torcer para as duas não divergirem. Aqui a operação é **uma**, e o
primeiro dígito nasce da comparação entre a UF do emitente e a do destinatário,
na hora de montar a nota.

**O exterior fica de fora da dedução, de propósito.** Em 22 sufixos o 7xxx (ou
o 3xxx) diz outra coisa: `5129` é "venda de insumo importado" e `7129` é "venda
ao mercado externo"; `1212` é devolução no mercado interno e `3212` no externo.
Exportação não é a mesma operação noutro lugar — é outra operação. Quem exporta
escolhe o CFOP explicitamente, na linha ou na nota.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# (sentido, local de destino) -> primeiro dígito. O exterior não está aqui:
# ele não se deduz.
PRIMEIRO_DIGITO = {
    ('saida', 'interna'): '5',
    ('saida', 'interestadual'): '6',
    ('entrada', 'interna'): '1',
    ('entrada', 'interestadual'): '2',
}


class NfeOperacao(models.Model):
    _name = 'nfe.operacao'
    _description = 'Operação fiscal (CFOP sem o primeiro dígito)'
    _order = 'sentido, code'
    _rec_name = 'display_name'

    code = fields.Char(
        string='Sufixo do CFOP', size=3, required=True, index=True,
        help="Os três últimos dígitos: 101 venda de produção, 917 remessa em "
             "consignação, 113 acerto. O primeiro dígito vem do destino.")
    sentido = fields.Selection(
        selection=[('saida', 'Saída'), ('entrada', 'Entrada')],
        string='Sentido', required=True, default='saida',
        help="O sufixo sozinho é ambíguo: 101 na saída é venda de produção, na "
             "entrada é compra para industrialização. São operações diferentes.")
    name = fields.Char(string='Operação', required=True)
    active = fields.Boolean(default=True)

    # -- como esta operação vira nota ----------------------------------
    natureza_operacao = fields.Char(
        string='Natureza da Operação', size=60,
        help="O texto que o destinatário lê no DANFE. Sem o nome da empresa — "
             "o DANFE já traz o emitente no cabeçalho.")
    finalidade = fields.Selection(
        selection=[('1', 'Normal'), ('2', 'Complementar'),
                   ('3', 'Ajuste'), ('4', 'Devolução')],
        string='Finalidade', default='1', required=True,
        help="Devolução emitida como normal é rejeitada pela SEFAZ.")
    cst_icms = fields.Char(
        string='CST / CSOSN do ICMS', size=3,
        help="Vazio deduz pelo regime da empresa: CST 41 no normal, CSOSN 400 "
             "no Simples — o certo para livro, que é imune.")
    cbenef = fields.Char(
        string='Código de Benefício Fiscal', size=10,
        help="Obrigatório em São Paulo desde abril de 2026. Depende do CST.")
    ibs_cbs_cst = fields.Char(string='CST do IBS/CBS', size=3)
    ibs_cbs_classificacao = fields.Char(
        string='Classificação Tributária (cClassTrib)', size=6)
    consumidor_final = fields.Selection(
        selection=[('0', 'Não'), ('1', 'Sim')], string='Consumidor Final',
        help="Vazio deduz pelo indicador de IE. Revenda nunca é consumidor final.")
    document_kind = fields.Selection(
        selection=[
            ('sale', 'Venda'), ('consignment', 'Remessa em consignação'),
            ('settlement', 'Acerto de consignação'),
            ('consignment_return', 'Devolução de consignação'),
            ('bonus', 'Bonificação'), ('event_out', 'Remessa para feira'),
            ('event_return', 'Retorno de feira'), ('transfer', 'Simples remessa'),
            ('other', 'Outra'),
        ], string='Documento')

    _codigo_unico_por_sentido = models.Constraint(
        'UNIQUE(code, sentido)',
        "Já existe uma operação com este sufixo neste sentido.")

    @api.depends('code', 'sentido', 'name')
    def _compute_display_name(self):
        for op in self:
            marca = 'x' if op.sentido == 'saida' else 'e'
            op.display_name = '%s%s — %s' % (
                marca, op.code or '', op.name or '')

    @api.constrains('code')
    def _check_code(self):
        for op in self:
            if not (op.code or '').isdigit() or len(op.code) != 3:
                raise ValidationError(_(
                    "O sufixo do CFOP tem exatamente três dígitos "
                    "(recebido %r).", op.code))

    # ------------------------------------------------------------------
    def cfop_para(self, local):
        """O CFOP de quatro dígitos desta operação para o destino dado.

        `local` é 'interna' ou 'interestadual'. O exterior devolve None: lá a
        operação é outra, e adivinhá-la geraria um CFOP que existe e significa
        coisa diferente — pior do que não emitir.

        Recordset vazio devolve None em vez de estourar. A maioria das posições
        fiscais herdadas do legado não tem operação, e um `ensure_one()` aqui
        derrubava a tela inteira de Posições Fiscais com "Expected singleton".
        """
        if not self:
            return None
        self.ensure_one()
        digito = PRIMEIRO_DIGITO.get((self.sentido, local))
        return (digito + self.code) if digito else None

    def cfop_record(self, local):
        """O registro da tabela oficial correspondente, para descrição e prova
        de que o código existe de fato no Anexo II."""
        if not self:
            return self.env['nfe.cfop']
        self.ensure_one()
        codigo = self.cfop_para(local)
        if not codigo:
            return self.env['nfe.cfop']
        return self.env['nfe.cfop'].search([('code', '=', codigo)], limit=1)

    def _focus_fiscal(self, company):
        """Atributos fiscais desta operação, com o padrão da empresa atrás."""
        op = self[:1]
        return {
            'natureza_operacao': (op.natureza_operacao
                                  or company.focus_natureza_operacao),
            'cst_icms': op.cst_icms or None,
            'cbenef': op.cbenef or company.focus_codigo_beneficio_fiscal,
            'finalidade': int(op.finalidade or '1'),
            'consumidor_final': (int(op.consumidor_final)
                                 if op.consumidor_final else None),
            'ibs_cbs_cst': op.ibs_cbs_cst or company.focus_ibs_cbs_cst,
            'ibs_cbs_classificacao': (op.ibs_cbs_classificacao
                                      or company.focus_ibs_cbs_classificacao),
        }
