# -*- coding: utf-8 -*-
{
    'name': 'Liber Partner Commercial (sales channel)',
    'version': '19.0.1.6.0',
    'summary': 'The sales channel on the customer record, the channel grid, and the discount kept on its own field',
    'description': """
O CANAL DE VENDAS NO CADASTRO DO CLIENTE.

O Odoo 19 removeu `team_id` de `res.partner`. O `crm` só acrescenta
`opportunity_ids` e `opportunity_count`; o `sale_crm` não devolve o campo.
`sale.order._default_team_id` deixou de consultar o parceiro, e a equipe passou
a sair da filiação do vendedor (`crm.team.member`).

O QUE O 19 REMOVEU FOI A DEDUÇÃO, não o direito de gravar. E a dedução pressupõe
que o comercial se divide por QUEM VENDE -- departamento, território, "e.g.
North America" é o exemplo que a própria Odoo põe no formulário da equipe, e por
padrão um vendedor pertence a uma equipe só (pôr numa segunda arquiva a
primeira, salvo o parâmetro `sales_team.membership_multi`).

A nossa divisão é por O QUE O CLIENTE É: livrarias pequenas, médias,
independentes, universitárias, distribuidoras, site próprio, sebo, feiras,
instituições, governo. São 17 canais para 45 usuários, e uma única vendedora
cobre 13 deles entre 327 clientes. Nenhum arranjo de equipes-de-gente reproduz
isso -- deduzir do vendedor colapsaria 13 canais em 1.

NOTA HISTÓRICA. Uma versão anterior deste texto dizia que a Amazon espalhada por
três equipes na migração provava que deduzir não funciona. Não prova: prova que
os vínculos vendedor-equipe nunca foram migrados (há UM `crm.team.member` para
45 usuários no merge_02), e sem membro a heurística do `_get_default_team_id`
cai em "qualquer equipe da minha empresa, por sequência". O argumento correto é
o de cima, e é mais forte.

CANAL, NÃO EQUIPE. O nome do campo acompanha o resto da casa, que já chama isto
de `Sales Channel` -- `consignment.template`, `consignment.shortfall`,
`consignment.coverage`, `consignment.settlement` e `stock.quant`. E continua
apontando para `crm.team` de propósito: é o modelo que `sale.order.team_id` e
`account_move.team_id` carimbam (21.660 pedidos e 33.996 faturas no merge_02).
Um modelo próprio partiria o vocabulário em dois, e os campos do núcleo não
podem ser repontados.

O campo é `company_dependent`: num grupo com mais de uma editora o mesmo cliente
pode ser de canais diferentes em cada uma -- 233 fichas assim --, que é como o
Odoo 15 guardava (em `ir.property`, 3.377 vínculos).

POR QUE UM MÓDULO SÓ PARA ISTO. O campo serve todo cliente, e a maioria esmagadora
não faz consignação: na base de 2026 são ~13.100 que só compram contra 192 com
contrato. Pôr o caso majoritário dentro do módulo de consignação obrigaria quem
nunca consignou a instalá-lo para ter canal no cliente. A dependência aqui é
`sale` -- que já traz o `sales_team` --, e é o mínimo para poder renomear o
campo nos documentos, já que `sale.order.team_id` e `account.move.team_id` são
os dois definidos no `sale`.

UMA LÍNGUA SÓ NAS TELAS. Não adianta a ficha dizer "Canal de Vendas" e o pedido,
a fatura e os relatórios dizerem "Equipe de vendas": é o mesmo campo apontando
para o mesmo registro. O módulo reescreve o rótulo nos documentos e nos quatro
filtros de busca do núcleo que escrevem o texto à mão, além dos dois menus que
levam à lista. O nome técnico desses filtros no próprio Odoo, aliás, é
`sales_channel`: "canal" é o vocabulário antigo da Odoo, que sobreviveu nos
nomes técnicos depois que o rótulo virou "team".

A REGRA DE PRECEDÊNCIA (contrato manda, cadastro é o padrão) NÃO mora aqui: ela
precisa conhecer os dois lados, e vive no `liber_soc_agreements`. A dependência
é ao contrário do que se esperaria: o módulo de consignação NÃO depende deste,
e lê o canal por trás de uma guarda (`if 'team_id' not in self._fields`). É de
propósito -- uma casa que só consigna não deveria ser obrigada a instalar o
cadastro comercial inteiro para fechar um acerto. Quem quer os dois instala os
dois, e aí a leitura encontra o campo.

A GRADE DOS CANAIS. O módulo é também onde ficam os ajustes pequenos do lado
comercial, e o primeiro deles é a lista da ação `Equipes de vendas`: ela existia
no `sales_team` mas não aparecia na ação, que abre em kanban. Um cartão serve
para acompanhar um canal; para arrumar dezenas -- e eram dezenas no merge_02,
39 registros ativos para 21 nomes, porque o Odoo 15 guardava um canal por
editora -- é preciso ver todos de uma vez e digitar. A lista entra na ação,
vira editável e ganha a coluna de vendedores.

UM REGISTRO POR NOME, SEM EMPRESA (decisão de 08/08/2026). "Livrarias pequenas"
da Hedra e da n-1 são a mesma coisa: canal é recorte de CLIENTELA, não
propriedade da editora. Duplicar por empresa fazia toda tela da casa mostrar a
mesma linha duas vezes ao agrupar, porque agrupar é agrupar por registro. O
`check_company=True` do `sale.order.team_id` não se opõe: canal sem empresa é
compatível com documento de qualquer empresa. O que continua por empresa é o
canal DO CLIENTE (`res.partner.team_id` é `company_dependent`) -- some o canal
duplicado, não o recorte.

O DESCONTO NA LINHA. O segundo ajuste, e o que veio de fora: até 09/08/2026 a
opção "Descontos" era ligada pelo `edlab_stack`, o módulo privado da casa. Ela
não podia ficar lá. Com a opção desligada -- o padrão do Odoo -- o percentual
da lista de preços entra DENTRO do preço unitário e o campo Desc.% fica em
zero, e três coisas do produto aberto leem o desconto no campo:

* o royalty sobre o preço de venda (`liber_copyright_contracts_analytics`),
  que tem por base preço x quantidade -- com o preço já líquido, o autor
  recebe sobre o valor descontado;
* a venda especial, reconhecida quando o desconto da linha alcança o mínimo
  configurado -- com desconto zero, nenhuma alcança;
* o vDesc da NFe (`liber_nfe_focus`), que sai da diferença entre o bruto e o
  subtotal -- e um preço já líquido a zera.

Quem instalasse o Liber sem o módulo privado da casa receberia os três errados,
em silêncio. Por isso o interruptor mudou de casa. O que ficou no `edlab_stack`
foi o gosto de tela -- quais colunas o pedido e a fatura abrem mostrando.
""",
    'author': 'EdLab Press',
    'category': 'Sales',
    'depends': [
        # `sale` é o mínimo para renomear o campo nos documentos:
        # `sale.order.team_id` e `account.move.team_id` são os dois definidos
        # lá, e `sale` já traz o `sales_team`. O `account` vem por ele, e é
        # nomeado porque a view da fatura é herdada aqui.
        'sale',
        'account',
    ],
    'data': [
        'data/sale_discount_data.xml',
        'views/res_partner_views.xml',
        'views/crm_team_views.xml',
        'views/rotulos_canal.xml',
        'views/account_move_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
