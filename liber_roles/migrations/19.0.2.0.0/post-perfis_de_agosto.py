# -*- coding: utf-8 -*-
"""As três retiradas decididas em 11/08/2026, no _mds/PERFIS.md.

    Comercial/Assistente   perde  product.group_product_manager
    Editorial/Assistente   perde  stock.group_stock_user
    Marketing/Gerente      perde  liber_soc_agreements.group_soc_user

POR QUE ISTO É UMA MIGRAÇÃO E NÃO UMA LINHA A MENOS NO XML. Retirar um grupo
tem DUAS metades, e apagar a linha do `implied_ids` só desfaz a primeira --
mal: nem desfaz. `implied_ids` escrito com `(4, ...)` é uma lista de comandos
INCREMENTAIS; apagar a linha deixa de mandar acrescentar a aresta e não manda
tirá-la, então ela sobrevive a todo `-u` numa base que já a tenha.

A segunda metade é pior de ver. Quando a implicação foi criada, o Odoo
escreveu o grupo implicado na ficha de cada usuário do grupo pai, e nunca o
retira de volta -- o `_remove_group` do core (conferido em 11/08/2026) mexe
só na aresta. Uma retirada feita só no repositório produz o pior resultado
possível: a regra escrita, revisada e versionada, e a base fazendo outra
coisa em silêncio. Foi o que aconteceu em 31/07/2026 com o Inventário do
Comercial, e é por isso que existe a migração vizinha, de 19.0.1.1.0.

A RÉGUA DA LIMPEZA é estreita, e igual à daquela migração:

- só mexe em quem carrega o papel de onde o grupo saiu. Um grupo concedido na
  mão a alguém de fora da grade é decisão de outra pessoa, e não cabe a uma
  migração desfazer o que alguém decidiu;
- e, mesmo dentro do papel, só tira de quem não tem OUTRA função que conceda
  o mesmo grupo. Não é uma lista a manter: pergunta-se ao fecho transitivo dos
  demais grupos do usuário (`all_implied_ids`), então a Direção, o Marketing,
  o Editorial -- e qualquer função futura -- entram sozinhos na conta. Quem
  acumula duas funções sai daqui como entrou.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

#: (papel de onde sai, grupo que sai, por quê)
RETIRADAS = [
    ('liber_roles.group_comercial_assistente',
     'product.group_product_manager',
     'produto é livro, e livro é do Editorial e do Marketing'),
    ('liber_roles.group_editorial_assistente',
     'stock.group_stock_user',
     'editor edita texto; o app Inventário é da Logística'),
    ('liber_roles.group_marketing_gerente',
     'liber_soc_agreements.group_soc_user',
     'marketing não tem nada a ver com consignação'),
    # Esta é de 10/08 ("perde a gerência") e estava sendo cumprida por um
    # `(3, ...)` no XML -- que funciona, mas precisa ser reaplicado a cada
    # `-u` e some no dia em que alguém limpa a lista. Virou linha daqui na
    # reescrita de 11/08, junto com as outras três: a retirada acontece uma
    # vez, nas duas metades, e o XML volta a ser só concessão.
    ('liber_roles.group_editorial_gerente',
     'liber_copyright_contracts.group_contract_manager',
     'contrato quem assina é o Jurídico; o Editorial consulta e redige'),
]


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    mexeu = False

    for xid_papel, xid_grupo, porque in RETIRADAS:
        papel = env.ref(xid_papel, raise_if_not_found=False)
        grupo = env.ref(xid_grupo, raise_if_not_found=False)
        if not (papel and grupo):
            _logger.info("liber_roles: pulei %s -> %s (grupo ausente nesta base)",
                         xid_papel, xid_grupo)
            continue

        # Primeira metade: a aresta. `_remove_group` alcança também os papéis
        # que herdam este (o Gerente que cita o Assistente, a Direção que cita
        # o Gerente), que é exatamente o que se quer.
        if grupo in papel.all_implied_ids:
            papel._remove_group(grupo)
            mexeu = True

        # Segunda metade: a ficha de cada pessoa.
        candidatos = env['res.users'].search([
            ('all_group_ids', 'in', papel.ids),
            ('group_ids', 'in', grupo.ids),
        ])
        a_limpar = candidatos.filtered(
            lambda u: grupo not in (u.group_ids - grupo).all_implied_ids)
        if a_limpar:
            a_limpar.write({'group_ids': [(3, grupo.id)]})
            mexeu = True
            _logger.info(
                "liber_roles: %s retirado de %d usuário(s) de %s (%s) -- %s",
                xid_grupo, len(a_limpar), xid_papel,
                ', '.join(a_limpar.mapped('login')), porque)
        else:
            _logger.info("liber_roles: %s -> %s, nenhuma ficha a limpar",
                         xid_papel, xid_grupo)

    if mexeu:
        env.registry.clear_cache()
