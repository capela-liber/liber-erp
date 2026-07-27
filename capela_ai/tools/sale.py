# -*- coding: utf-8 -*-
"""Vendas: propor orçamentos. O caso dos "quatro S000 diferentes".

Esta é a ferramenta que dá nome ao desenho inteiro. O pedido original era
"criar 4 S000 diferentes para essa lista de pedidos" -- uma ação que mexe em
vários documentos e que, apesar disso, não é uma ação em massa.

A diferença é que aqui cada orçamento é NOMEADO antes de existir: quem é o
cliente, quais produtos, quantas unidades, e uma frase que o gerente lê. Quatro
linhas de plano, quatro frases, um botão. O que não existe é o outro caminho --
não há como exprimir "e faça o mesmo para todos os clientes que casarem com
este filtro", porque não há linha de plano que signifique "e o resto também".

O handler roda sob `capela_ai_planning`, então ele LÊ à vontade (nomes de
cliente, nomes de produto, o que for preciso para escrever um resumo honesto) e
não consegue gravar nem por acidente.

O QUE ESTA FERRAMENTA NÃO FAZ, e por quê: confirmar pedido. Confirmar não é
gravar um campo, é chamar `action_confirm` -- e o motor de plano, hoje, só sabe
criar e alterar. Suportar chamada de método exige uma quarta operação com
allowlist de (modelo, método) declarada pela ferramenta, e isso é uma decisão
de desenho que merece ser tomada com calma, não enfiada aqui. Ver NOTES.md.
Confirmação, aliás, é o caso de uso da automação -- que ficou para a v2.
"""

from odoo import _
from odoo.exceptions import UserError

from .registry import KIND_PLAN, tool


@tool(
    'sale.plan_quotations',
    kind=KIND_PLAN,
    title='Propor orçamentos',
    description=(
        "Propõe a criação de um ou mais orçamentos de venda (S000), um por "
        "cliente. NÃO cria nada: devolve uma proposta que a pessoa aprova na "
        "tela. Cada orçamento precisa ser descrito individualmente — cliente e "
        "itens. Não existe forma de dizer 'faça para todos que casarem com um "
        "filtro'; se a pessoa pedir isso, primeiro use query.search para "
        "levantar a lista concreta, mostre-a, e só então proponha os "
        "orçamentos um a um."
    ),
    writes=('sale.order',),
    automation_safe=False,
    input_schema={
        'type': 'object',
        'properties': {
            'quotations': {
                'type': 'array',
                'description': "Um item por orçamento a propor.",
                'items': {
                    'type': 'object',
                    'properties': {
                        'partner_id': {
                            'type': 'integer',
                            'description': "id do res.partner do cliente.",
                        },
                        'reason': {
                            'type': 'string',
                            'description': (
                                "Por que este orçamento, em uma frase. É o que "
                                "a pessoa vai ler antes de aprovar — escreva "
                                "para ela, não para o log."
                            ),
                        },
                        'lines': {
                            'type': 'array',
                            'description': "Itens do orçamento.",
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'product_id': {'type': 'integer'},
                                    'quantity': {'type': 'number'},
                                },
                                'required': ['product_id', 'quantity'],
                                'additionalProperties': False,
                            },
                        },
                    },
                    'required': ['partner_id', 'reason', 'lines'],
                    'additionalProperties': False,
                },
            },
        },
        'required': ['quotations'],
        'additionalProperties': False,
    },
)
def plan_quotations(env, quotations):
    if not quotations:
        raise UserError(_("Nenhum orçamento foi descrito na proposta."))

    lines = []
    for spec in quotations:
        partner = env['res.partner'].browse(spec['partner_id'])
        if not partner.exists():
            raise UserError(_(
                "Cliente #%(partner_id)s não existe.", partner_id=spec['partner_id'],
            ))
        if not spec.get('lines'):
            raise UserError(_(
                "O orçamento para %(partner)s ficou sem itens.",
                partner=partner.display_name,
            ))

        order_lines = []
        descriptions = []
        for item in spec['lines']:
            product = env['product.product'].browse(item['product_id'])
            if not product.exists():
                raise UserError(_(
                    "Produto #%(product_id)s não existe.", product_id=item['product_id'],
                ))
            quantity = float(item['quantity'])
            if quantity <= 0:
                raise UserError(_(
                    "Quantidade inválida para %(product)s.", product=product.display_name,
                ))
            order_lines.append([0, 0, {
                'product_id': product.id,
                'product_uom_qty': quantity,
            }])
            descriptions.append(f'{quantity:g}× {product.display_name}')

        lines.append({
            'operation': 'create',
            'model': 'sale.order',
            'values': {
                'partner_id': partner.id,
                'order_line': order_lines,
            },
            'summary': _(
                "Orçamento para %(partner)s — %(items)s. Motivo: %(reason)s",
                partner=partner.display_name,
                items='; '.join(descriptions),
                reason=spec['reason'],
            ),
        })

    return {
        'summary': _(
            "Criar %(count)s orçamento(s) de venda.", count=len(lines),
        ),
        'lines': lines,
    }
