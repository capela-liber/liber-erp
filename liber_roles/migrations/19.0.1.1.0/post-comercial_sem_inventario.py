# -*- coding: utf-8 -*-
"""O Comercial devolve o app Inventário à Logística.

Por que isto precisa ser uma migração, e não bastou editar o XML. Tirar um
grupo de `implied_ids` desfaz a IMPLICAÇÃO, e só. O Odoo, quando a implicação
foi criada, escreveu o grupo implicado na ficha de cada usuário do grupo pai
(`res.groups.write` propaga para os usuários) -- e nunca o retira de volta.
É o mesmo mecanismo que já mordeu a conta pública em 27/07/2026 e por isso
existe o `_liber_faxina_do_visitante`.

Sem esta passagem, o resultado do commit que criou a Logística seria o pior
dos dois mundos: o XML dizendo que o Comercial não tem Inventário, e todo
comercial já cadastrado continuando com o app aberto. Ninguém veria a
diferença, e a separação existiria só no repositório.

A régua da limpeza é estreita de propósito:

- só mexe em quem é Comercial. Um `stock.group_stock_user` concedido na mão a
  alguém de fora da grade é decisão de outra pessoa, e não cabe a uma migração
  desfazer o que alguém decidiu;
- e, mesmo dentro do Comercial, só tira de quem não tem OUTRA função que
  conceda o grupo. Isso não é uma lista a manter: pergunta-se ao fecho
  transitivo dos demais grupos do usuário (`all_implied_ids`), então Direção,
  Editorial, a nova Logística -- e qualquer função futura -- entram sozinhas
  na conta. Um gerente comercial que acumule Logística sai daqui como entrou.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    estoque = env.ref('stock.group_stock_user', raise_if_not_found=False)
    comercial = env.ref('liber_roles.group_comercial_assistente',
                        raise_if_not_found=False)
    if not (estoque and comercial):
        return

    # Quem é comercial: basta procurar pelo assistente, porque o gerente o
    # implica. E só interessa quem carrega o grupo DIRETO na ficha (`group_ids`)
    # -- é dele que a propagação do Odoo deixou o rastro a limpar.
    comerciais = env['res.users'].search([
        ('all_group_ids', 'in', comercial.ids),
        ('group_ids', 'in', estoque.ids),
    ])
    a_limpar = comerciais.filtered(
        lambda u: estoque not in (u.group_ids - estoque).all_implied_ids)
    if not a_limpar:
        return

    a_limpar.write({'group_ids': [(3, estoque.id)]})
    env.registry.clear_cache()
    _logger.info(
        "liber_roles: app Inventário retirado de %d usuário(s) do Comercial "
        "(%s). As transferências da consignação seguem com eles, pelo "
        "liber_soc_moves.group_consignment_stock_docs; o Inventário agora é "
        "da Logística.",
        len(a_limpar), ', '.join(a_limpar.mapped('login')))
