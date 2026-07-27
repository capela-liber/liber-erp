# -*- coding: utf-8 -*-
"""O catálogo: o que o agente sabe fazer, e por consequência tudo o que ele pode.

Uma ferramenta existe se, e só se, alguém a declarou aqui em Python. Não há
tela que crie ferramenta, não há registro que o administrador preencha para
inventar uma capacidade nova. Isso é deliberado: a lista do que o agente
consegue fazer precisa caber num `git log`, não no estado do banco de quem
clicou por último -- é a mesma escolha que o `liber_roles` fez ao mover a
tradução de perfis para o repositório.

Há exatamente DOIS tipos de ferramenta, e a ausência de um terceiro é o
desenho:

    'read'  -- consulta. Roda na hora, como o usuário, e devolve dados.
    'plan'  -- propõe. NÃO grava: devolve um plano enumerado que um humano
               aprova depois. Ver models/capela_ai_plan.py.

Não existe 'write'. Uma ferramenta que gravasse direto seria uma ferramenta
cujo efeito depende do texto que o modelo produziu -- e é exatamente isso que
não queremos, porque esse texto pode ter vindo do corpo de um e-mail de
cliente. Toda escrita passa pelo plano, e o plano passa por um humano.

E não existe 'unlink', em tipo nenhum. Apagar não é uma capacidade que se
concede com cuidado; é uma que não se concede. O idioma do Odoo para desfazer
é cancelar (`action_cancel`) e arquivar (`active = False`), e ambos são
escritas comuns que cabem num plano como qualquer outra.

Um detalhe que parece burocracia e não é: `writes` declara, ferramenta a
ferramenta, em quais modelos aquele plano pode mexer. O guarda em
`ir.model.access.check` lê essa declaração na hora de aplicar e recusa
qualquer modelo fora dela. Então uma ferramenta que se descuide -- ou que um
dia seja editada sem atenção -- falha em vez de escrever no lugar errado.
"""

import functools
import inspect

from odoo.exceptions import UserError

#: Os dois tipos. Ver o docstring acima para por que não há um terceiro.
KIND_READ = 'read'
KIND_PLAN = 'plan'
KINDS = (KIND_READ, KIND_PLAN)


class ToolDef:
    """Uma ferramenta declarada. Imutável depois de registrada."""

    __slots__ = (
        'name', 'title', 'description', 'input_schema', 'kind',
        'writes', 'automation_safe', 'handler',
    )

    def __init__(self, name, title, description, input_schema, kind,
                 writes, automation_safe, handler):
        self.name = name
        self.title = title
        self.description = description
        self.input_schema = input_schema
        self.kind = kind
        self.writes = frozenset(writes)
        self.automation_safe = automation_safe
        self.handler = handler

    def __repr__(self):
        return f'<ToolDef {self.name} ({self.kind})>'

    def to_api_schema(self):
        """A forma que a API do Claude espera em `tools`.

        `strict` liga a validação de esquema do lado do servidor: o modelo não
        consegue mandar um parâmetro que não existe nem omitir um obrigatório.
        Uma classe inteira de erro deixa de precisar de tratamento aqui.
        """
        return {
            'name': self.name,
            'description': self.description,
            'strict': True,
            'input_schema': self.input_schema,
        }


#: name -> ToolDef. Populado no import dos módulos de ferramenta.
REGISTRY = {}


def _validate_schema(name, schema):
    """Recusa esquema frouxo na hora do import, não na hora da chamada.

    `strict` da API exige `additionalProperties: False` e `required`
    explícito. Como o registro é montado no import do módulo, um esquema mal
    formado impede o Odoo de subir -- que é onde queremos descobrir isso, e
    não no meio de uma conversa com um cliente.
    """
    if schema.get('type') != 'object':
        raise ValueError(f"capela_ai: esquema de {name!r} precisa ser type=object")
    if schema.get('additionalProperties') is not False:
        raise ValueError(
            f"capela_ai: esquema de {name!r} precisa de additionalProperties=False "
            "(exigência do modo strict da API)"
        )
    if 'required' not in schema:
        raise ValueError(f"capela_ai: esquema de {name!r} precisa listar 'required'")
    declared = set(schema.get('properties') or {})
    required = set(schema['required'])
    if not required <= declared:
        faltando = ', '.join(sorted(required - declared))
        raise ValueError(
            f"capela_ai: {name!r} exige parâmetros que não declarou: {faltando}"
        )


def tool(name, *, title, description, input_schema, kind,
         writes=(), automation_safe=False):
    """Declara uma ferramenta. Usar como decorador sobre o handler.

    O handler recebe `env` como primeiro argumento posicional e o resto por
    nome, validado contra `input_schema`. O que ele devolve depende do tipo:

        read -> qualquer estrutura serializável em JSON (vira tool_result)
        plan -> {'summary': str, 'lines': [ {...} ]}, ver capela.ai.plan

    `automation_safe` marca as ferramentas que um dia poderão rodar sem humano
    no circuito (a v2, `capela_ai_automation`). O campo existe desde já porque
    decidir isso ferramenta a ferramenta, retroativamente, é onde se erra: na
    pressa de armar a primeira receita, tudo vira seguro.
    """
    if kind not in KINDS:
        raise ValueError(f"capela_ai: tipo {kind!r} inválido para {name!r}; use um de {KINDS}")
    if kind == KIND_READ and writes:
        raise ValueError(f"capela_ai: ferramenta de leitura {name!r} não declara `writes`")
    if kind == KIND_PLAN and not writes:
        raise ValueError(
            f"capela_ai: {name!r} é um plano e precisa declarar `writes` -- "
            "o guarda usa essa lista para recusar o resto"
        )
    _validate_schema(name, input_schema)

    def deco(fn):
        if name in REGISTRY:
            raise ValueError(f"capela_ai: ferramenta {name!r} declarada duas vezes")
        params = list(inspect.signature(fn).parameters)
        if not params or params[0] != 'env':
            raise ValueError(
                f"capela_ai: handler de {name!r} precisa receber `env` como "
                "primeiro parâmetro -- é por ele que a ferramenta herda o usuário"
            )
        REGISTRY[name] = ToolDef(
            name=name, title=title, description=description,
            input_schema=input_schema, kind=kind, writes=writes,
            automation_safe=automation_safe, handler=fn,
        )
        return fn

    return deco


def get(name):
    """A ferramenta, ou um erro que o usuário entende."""
    tool_def = REGISTRY.get(name)
    if tool_def is None:
        raise UserError(
            f"Ferramenta desconhecida: {name}. O agente só pode chamar o que "
            "está declarado no catálogo do módulo."
        )
    return tool_def


def all_names():
    return sorted(REGISTRY)
