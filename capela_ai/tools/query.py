# -*- coding: utf-8 -*-
"""Consulta: a metade do produto que não precisa de aprovação nenhuma.

"Me dá os mais vendidos dos últimos meses, mas cruze com o que tínhamos em
estoque" é uma pergunta de leitura. Não move nada, não precisa de plano, e
seria um desperdício exigir que alguém pré-construísse um relatório para cada
recorte que um gerente é capaz de imaginar.

Duas ferramentas genéricas bastam -- listar e agrupar -- porque o cruzamento em
si o modelo faz no raciocínio: agrupa `sale.order.line` por produto no período,
lê `qty_available` daqueles produtos, e junta. Não é preciso máquina nova, e
cobre a família inteira de perguntas.

Por que isto é seguro sendo genérico, quando a escrita não é: porque o ORM já
é a trava. `search_read` e `_read_group` rodam como a pessoa e respeitam ACLs e
record rules dela. O agente não vira um canal para ler o que o usuário não
poderia abrir sozinho -- ele vira um jeito mais rápido de abrir o que já podia.
Um assistente de marketing perguntando margem por cliente recebe AccessError do
ORM, e a recusa nem passou por aqui.

O que sobra de risco é volume e escopo, não confidencialidade. Daí três
limites: allowlist de modelos de negócio, teto de linhas, e um teto absoluto
que o parâmetro não consegue furar.
"""

from odoo import _
from odoo.exceptions import UserError

from .registry import KIND_READ, tool

#: Teto absoluto, acima do que o parâmetro pede. Uma consulta de agente serve
#: para responder pergunta, não para exportar base.
HARD_LIMIT = 500

#: Os modelos que o agente pode consultar. Allowlist e não lista negra, pelo
#: mesmo motivo do visitante no `liber_roles`: com lista negra, todo modelo
#: novo -- de um módulo nosso ou de um app instalado amanhã -- nasce exposto.
#: Aqui nasce fora, e incluir é uma linha explícita que alguém revisa.
#:
#: Repare no que NÃO está: `res.users`, `ir.*`, `mail.message`. Não é sigilo
#: (o ORM já barraria o que a pessoa não pode ler) -- é que consultar a
#: infraestrutura do Odoo nunca responde uma pergunta de negócio, e deixar
#: fora encurta a superfície sem custo nenhum.
QUERYABLE_MODELS = frozenset({
    'res.partner',
    'product.product',
    'product.template',
    'product.category',
    'sale.order',
    'sale.order.line',
    'purchase.order',
    'purchase.order.line',
    'stock.quant',
    'stock.move',
    'stock.picking',
    'account.move',
    'account.move.line',
    'crm.lead',
})


def _check_model(model):
    if model not in QUERYABLE_MODELS:
        raise UserError(_(
            "O agente não consulta %(model)s. Ele tem uma lista fechada de "
            "modelos de negócio, e ampliá-la é uma alteração de código.",
            model=model,
        ))


@tool(
    'query.search',
    kind=KIND_READ,
    title='Listar registros',
    description=(
        "Lista registros de um modelo de negócio do Odoo, com filtro, campos e "
        "ordenação. Use para responder perguntas sobre dados existentes. O "
        "resultado já vem limitado pelas permissões de quem perguntou: se vier "
        "vazio ou der erro de acesso, a pessoa realmente não pode ver aquilo. "
        "Para totais e contagens por categoria prefira query.group_by, que é "
        "muito mais barato que listar tudo e somar."
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'model': {
                'type': 'string',
                'description': "Nome técnico do modelo, ex.: 'sale.order'.",
            },
            'domain': {
                'type': 'array',
                'description': (
                    "Domain do Odoo em JSON, ex.: "
                    "[[\"date_order\", \">=\", \"2026-01-01\"], [\"state\", \"=\", \"sale\"]]. "
                    "Lista vazia traz tudo que a pessoa pode ver."
                ),
            },
            'fields': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': "Campos a trazer. Peça só o necessário.",
            },
            'limit': {
                'type': 'integer',
                'description': f"Máximo de linhas (teto absoluto de {HARD_LIMIT}).",
            },
            'order': {
                'type': 'string',
                'description': "Ordenação, ex.: 'date_order desc'.",
            },
        },
        'required': ['model', 'domain', 'fields'],
        'additionalProperties': False,
    },
)
def search(env, model, domain, fields, limit=None, order=None):
    _check_model(model)
    limit = min(int(limit or 80), HARD_LIMIT)
    records = env[model].search_read(
        domain or [], fields, limit=limit, order=order or None,
    )
    return {
        'model': model,
        'count': len(records),
        'truncated': len(records) == limit,
        'records': records,
    }


@tool(
    'query.group_by',
    kind=KIND_READ,
    title='Agrupar e somar',
    description=(
        "Agrupa registros e calcula agregados — o jeito certo de responder "
        "'quais os mais vendidos', 'quanto por cliente', 'total por mês'. "
        "Muito mais barato que listar e somar. Agregados no formato "
        "'campo:função', ex.: 'product_uom_qty:sum'. Agrupamento por data "
        "aceita granularidade, ex.: 'date_order:month'."
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'model': {'type': 'string', 'description': "Nome técnico do modelo."},
            'domain': {'type': 'array', 'description': "Domain do Odoo em JSON."},
            'group_by': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': "Campos de agrupamento, ex.: ['product_id'].",
            },
            'aggregates': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': "Agregados, ex.: ['product_uom_qty:sum', '__count'].",
            },
            'limit': {'type': 'integer', 'description': f"Máximo de grupos (teto {HARD_LIMIT})."},
            'order': {'type': 'string', 'description': "Ordenação dos grupos."},
        },
        'required': ['model', 'domain', 'group_by', 'aggregates'],
        'additionalProperties': False,
    },
)
def group_by(env, model, domain, group_by, aggregates, limit=None, order=None):
    _check_model(model)
    limit = min(int(limit or 50), HARD_LIMIT)
    rows = env[model]._read_group(
        domain or [], groupby=group_by, aggregates=aggregates,
        limit=limit, order=order or None,
    )
    # `_read_group` devolve tuplas na ordem (group_by..., aggregates...).
    # Nomear as colunas aqui evita que o modelo tenha de adivinhar posição.
    columns = list(group_by) + list(aggregates)
    return {
        'model': model,
        'columns': columns,
        'rows': [
            {
                column: (value.id if hasattr(value, 'id') else value)
                for column, value in zip(columns, row)
            }
            for row in rows
        ],
    }
