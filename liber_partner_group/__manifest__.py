# -*- coding: utf-8 -*-
{
    'name': 'Liber Partner Group (bookstore networks)',
    'version': '19.0.1.2.1',
    'summary': 'The commercial group (rede) above the branch: one grouping axis for reports, without touching the fiscal record',
    'description': """
A REDE ACIMA DA FILIAL, SEM MEXER NA NOTA.

Cada loja de uma rede de livrarias é um CNPJ próprio -- e tem de continuar
sendo: contrato de consignação, prateleira, saldo e NFe são por filial, e o
fisco não aceita outra coisa. Mas relatório lido loja a loja não conta a
história de ninguém: "LIVRARIA DA TRAVESSA LTDA" aparece oito vezes idênticas
na Análise de Vendas, e a pergunta que o comercial faz é "quanto vendemos PARA
A TRAVESSA?".

POR QUE UM CAMPO NOVO, e não o que já existe:

* `commercial_partner_id` não sobe: filial com CNPJ próprio é `is_company`,
  logo é o próprio parceiro comercial. O comentário de projeto em
  `liber_soc_agreements/models/res_partner.py` já registrava isso.
* `parent_id` carrega efeitos colaterais que rede nenhuma pediu: sincronização
  de campos comerciais, endereço, e o casamento de NFe por documento prefere
  ficha sem pai. Pendurar 40 lojas numa matriz para ganhar um agrupamento é
  pagar caro por pouco.
* a RAZÃO SOCIAL não basta como chave: agrupa a Travessa (uma razão, muitas
  filiais) mas não a Leitura, que é franquia -- cada loja uma razão social e
  um CNPJ de raiz diferente.

Então: um modelo pequeno (`liber.partner.group`), um Many2one na ficha da
empresa, e o eixo aparece onde se lê -- Análise de Vendas (`sale.report`) e o
Painel de Notas Fiscais (`nfe.xml.panel`). O grão de tudo continua a loja.

A RAIZ DO CNPJ SUGERE, A FICHA DECIDE. Os 8 primeiros dígitos do CNPJ
identificam a entidade legal: toda filial da Travessa começa com 31.004.013.
O grupo pode registrar suas raízes, e uma ficha nova (ou que ganha CNPJ) cai
no grupo sozinha -- mas o campo é editável, porque a Leitura (franquia, muitas
raízes) só se monta à mão, e uma escolha manual nunca é desfeita pela
sugestão.

DADO DESCE, CÓDIGO SOBE: as redes em si não são semeadas pelo módulo -- são
cadastro, nascem no banco de produção e descem. Para o dev existe
`scripts/seed_redes.py`.
""",
    'author': 'EdLab Press',
    'category': 'Sales',
    'depends': [
        # `sale` pelo sale.report (o eixo na Análise de Vendas) e pelos grupos
        # de acesso do comercial; `liber_nfe_xml` pelo vat_digits (a sugestão
        # pela raiz do CNPJ) e pelo Painel de Notas Fiscais que este módulo
        # estende. Quem quiser a rede sem o painel pode, mais tarde, partir a
        # ponte do painel num módulo próprio -- por ora as duas coisas moram
        # nos mesmos bancos.
        'sale',
        'liber_nfe_xml',
        # Pelo hook `_get_serialized_readonly_dashboard`: o "Principais
        # clientes" do Painel de Vendas passa a agrupar pela rede -- troca de
        # leitura, no molde do liber_geo_brasil.
        'spreadsheet_dashboard',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/partner_group_views.xml',
        'views/res_partner_views.xml',
        'views/sale_report_views.xml',
        'views/xml_panel_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_partner_group/static/src/js/partner_group_tour.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
