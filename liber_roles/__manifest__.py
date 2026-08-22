# -*- coding: utf-8 -*-
{
    'name': 'Liber Roles (as funções da casa)',
    'version': '19.0.2.5.0',
    'summary': 'Perfis por função: departamento + nível, embrulhando os grupos do Odoo',
    'description': """
Os "perfis" nativos do Odoo são recortes por aplicativo (Vendas: Usuário,
Contabilidade: Contador...). A editora pensa por FUNÇÃO: Comercial, Logística,
Financeiro, Editorial, Marketing -- cada um em dois níveis (Assistente opera,
Gerente aprova e configura) -- mais a Direção, transversal.

Este módulo é só a tradução: cada função é um res.groups que IMPLICA
(implied_ids) o pacote certo de grupos nativos e dos nossos módulos. O
operador marca UMA função na ficha do usuário; o Odoo deriva o resto.
A tradução mora no repositório, onde uma decisão de acesso pode ser lida,
revisada e versionada -- não no estado de banco de quem clicou por último.

ONDE SE DECIDE: em `_mds/PERFIS.md`. Aquele documento lista as 25 opções do
formulário de usuário do Odoo e diz o que cada função marca em cada uma; o
XML daqui é a transcrição, e nada mais. Linha nova aqui sem linha lá é uma
decisão sem dono.

A FORMA (reescrita de 11/08/2026): cada função é uma LISTA CHAPADA de
concessões. Sem `(3, ...)`, sem ordem que importe, sem soma implícita. O
Gerente cita o Assistente; a Direção cita os seis Gerentes. A única exceção é
o Visitante, que subtrai -- e por isso ali a ordem importa.

Retirar um grupo NÃO se faz apagando a linha: `implied_ids` é uma lista de
comandos incrementais, e a aresta sobrevive em qualquer base que já a tenha.
Pior: quando a implicação foi criada, o Odoo copiou o grupo para a ficha de
cada usuário, e nunca o retira. Retirada é migração, e faz as duas metades --
ver migrations/19.0.2.0.0/.

MÓDULO OPCIONAL TRAZ A PRÓPRIA PONTE, e não uma linha aqui: o `liber_support`
concede o Atendimento ao Comercial, o `liber_amazon_vendor` concede a Amazon,
o `capela_influencers` concede a Bonificação. Assim este módulo não vira
dependência de meio mundo, e um -u numa base sem eles não quebra.

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
        # o create de res.partner que a grade promete ao vendedor vem do ACL
        # do crm (res.partner.crm.user); sem ele a promessa quebra em silêncio
        'crm',
        'account',
        # chega de carona pelo account e pelo liber_budget, mas agora o
        # módulo referencia group_analytic_accounting diretamente
        'analytic',
        'stock',
        'project',
        'website',
        'liber_soc_agreements',
        # o grupo estreito de documentos de estoque do Comercial mora aqui
        'liber_soc_moves',
        'liber_copyright_contracts',
        'liber_budget',
        'liber_metabooks_integration',
        'payment',
        'purchase',
        # o menu do rastreio de links (utm) é aberto para o Marketing
        'utm',
        # o Painel do controller financeiro (11/08/2026): o grupo
        # spreadsheet_dashboard.group_dashboard_manager mora aqui
        'spreadsheet_dashboard',
        # RH (10/08/2026). O grosso do que se pediu para funcionários, folga e
        # despesa é o comportamento de quem NÃO tem grupo nenhum -- ver
        # ACESSOS.md. Daqui só saem duas concessões: o aprovador de despesa da
        # equipe, nos gerentes, e ver a ficha de todos, na Direção. A
        # dependência existe para os `ref` resolverem.
        'hr',
        'hr_expense',
        # Arquivos na nuvem: o Editorial opera (assistente) e configura
        # (gerente). Sem bridge próprio nesses módulos, a concessão mora aqui.
        'liber_dropbox',
        'liber_gdrive',
        'liber_github',
        # NÃO é uso: é ORDEM DE CARGA. Este módulo do core (auto_install,
        # Hidden) esvazia os grupos do menu Aplicativos, e nós os
        # devolvemos em security/menu_aplicativos.xml. Sem a dependência os
        # dois seriam irmãos sem relação e a ordem entre eles seria livre --
        # num dia qualquer o dele rodaria por último e o menu voltaria a
        # aparecer para a casa inteira, sem erro e sem aviso.
        'base_install_request',
    ],
    'data': [
        'security/liber_roles_groups.xml',
        'security/menu_aplicativos.xml',
        'security/menu_projetos.xml',
        'security/menu_link_tracker.xml',
        'security/menu_compras_editorial.xml',
        'security/ir.model.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_roles/static/src/js/editorial_compras_tour.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
