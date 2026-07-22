# -*- coding: utf-8 -*-
{
    'name': 'Liber Roles (as funções da casa)',
    'version': '19.0.1.0.0',
    'summary': 'Perfis por função: departamento + nível, embrulhando os grupos do Odoo',
    'description': """
Os "perfis" nativos do Odoo são recortes por aplicativo (Vendas: Usuário,
Contabilidade: Contador...). A editora pensa por FUNÇÃO: Comercial, Financeiro,
Editorial, Marketing -- cada um em dois níveis (Assistente opera, Gerente
aprova e configura) -- mais a Direção, transversal.

Este módulo é só a tradução: cada função é um res.groups que IMPLICA
(implied_ids) o pacote certo de grupos nativos e dos nossos módulos. O
operador marca UMA função na ficha do usuário; o Odoo deriva o resto.
A tradução mora no repositório, onde uma decisão de acesso pode ser lida,
revisada e versionada -- não no estado de banco de quem clicou por último.

Decisões da v1 (a refinar; ver NOTES.md ao lado deste arquivo):

- Boards financeiros só para Direção e Financeiro/Gerente. Sai de graça da
  matemática dos grupos: o painel do orçamento exige os grupos do `budget`
  (que só essas funções recebem) e os relatórios contábeis exigem
  account_readonly ou superior (idem).
- Financeiro/Assistente é Cobrança (billing): faturas e pagamentos, sem
  relatórios contábeis nem orçamento. Lançar orçamento subiu para o Gerente.
- Comercial/Assistente vê TODOS os documentos de venda ("só os próprios"
  fica para a fase 2, via record rule).
- Direção enxerga tudo em leitura; a v1 ainda não IMPEDE a edição nos apps
  operacionais (fase 2). Diretor que opera uma área acumula a função dela.
- Marketing usa os grupos do website (mass_mailing não está instalado).

Fora da grade dos departamentos existe o VISITANTE: a conta da apresentação
pública. Enxerga o sistema inteiro e escreve no chatter, mas não cria, altera
nem apaga documento algum -- a trava é no ORM (ir.model.access.check), não no
menu, então vale também para RPC e URL colada. Ver models/ir_model_access.py.
""",
    'author': 'EdLab Press',
    'category': 'Technical',
    'depends': [
        'mail',
        'sale_management',
        'account',
        'stock',
        'project',
        'website',
        'liber_soc_agreements',
        'liber_copyright_contracts',
        'liber_budget',
        'liber_product_bonus',
        'liber_metabooks_integration',
        'payment',
        'purchase',
    ],
    'data': [
        'security/liber_roles_groups.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
