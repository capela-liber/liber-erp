# -*- coding: utf-8 -*-
"""O guarda: cinto por baixo do suspensório.

O suspensório é o catálogo de ferramentas (tools/registry.py): o agente só
consegue exprimir o que alguém declarou em Python, e apagar não está lá. Este
arquivo é o cinto -- ele existe para o caso de uma ferramenta se descuidar, ou
de alguém editar uma amanhã sem reler o desenho.

A técnica é a do visitante do `liber_roles`: cortar em `ir.model.access.check`,
por onde passa todo create/write/unlink do ORM, e não esconder menu. Cortar
aqui vale mais porque fecha também a chamada por RPC e a URL colada -- e, no
nosso caso, fecha a ferramenta que resolveu chamar um modelo que não declarou.

Duas fases, dois cortes diferentes:

    planejando  -- a ferramenta de plano está montando a proposta. Ela NÃO
                   pode gravar nada, de espécie alguma. Isso transforma "o
                   handler não deve escrever" de convenção educada em
                   propriedade verificável: se escrever, estoura.

    aplicando   -- o plano foi aprovado por um humano e está sendo executado.
                   Grava só nos modelos que a ferramenta declarou em `writes`,
                   mais o chatter (que é onde fica o rastro de auditoria).
                   `unlink` é recusado em qualquer caso.

A FRONTEIRA QUE ESTE GUARDA NÃO COBRE, dita em voz alta: `sudo()`. Código que
grava como superusuário passa reto -- `env.su` é o primeiro desvio aqui, como
é no visitante. Não é descuido, é o preço de funcionar: ao criar um pedido o
Odoo incrementa `ir.sequence`, insere `mail.message`, mexe em `mail.followers`
e em `bus.bus`, tudo por baixo do usuário. Bloquear isso quebraria exatamente
o ato que se quer permitir.

Então contra `sudo()` a defesa não é o ORM: é que nenhuma ferramenta o use, e
que exista um teste que quebre o build se alguém escrever `.sudo(` num arquivo
de ferramenta (tests/test_no_sudo.py). Uma regra que uma máquina confere vale
mais que uma que só a revisão confere -- mas ela é de outra natureza, e vale
saber qual das duas está segurando o quê.
"""

from odoo import api, models
from odoo.exceptions import AccessError

#: Chaves de contexto. Postas por capela.ai.plan; nunca por uma ferramenta.
CTX_PLANNING = 'capela_ai_planning'
CTX_WRITES = 'capela_ai_writes'

#: O chatter. Liberado durante a aplicação porque é ONDE o agente registra o
#: que fez -- o rastro que um contador vai pedir daqui a seis meses. Postar
#: recado nunca foi o risco; emitir documento é que era.
INFRA_WRITABLE_MODELS = frozenset({
    'mail.message',
    'mail.followers',
    'mail.notification',
    'mail.tracking.value',
    'mail.activity',
})


class IrModelAccess(models.Model):
    _inherit = 'ir.model.access'

    @api.model
    def check(self, model, mode='read', raise_exception=True):
        blocked = self._capela_ai_blocked(model, mode)
        if blocked:
            if raise_exception:
                raise AccessError(blocked)
            return False
        return super().check(model, mode=mode, raise_exception=raise_exception)

    @api.model
    def _capela_ai_blocked(self, model, mode):
        """Devolve a mensagem da recusa, ou None se pode seguir.

        Devolver a mensagem em vez de um booleano deixa o motivo exato viajar
        até o usuário: "o agente não pode apagar" e "o agente não pode mexer
        em contabilidade" são recusas diferentes e merecem frases diferentes.
        """
        # Leitura nunca é assunto daqui: as ACLs e as record rules do usuário
        # já resolvem, e é justamente delas que o agente herda o seu limite.
        if mode == 'read':
            return None
        # sudo passa. Ver o docstring do módulo -- é a fronteira declarada.
        if self.env.su:
            return None

        ctx = self.env.context

        if ctx.get(CTX_PLANNING):
            return self.env._(
                "O agente está montando uma proposta e propostas não gravam. "
                "Esta é uma falha do módulo, não sua: a ferramenta tentou "
                "escrever em %(document_kind)s durante o planejamento.",
                document_kind=self._capela_ai_model_name(model),
            )

        writes = ctx.get(CTX_WRITES)
        if writes is None:
            # Fora de ação do agente: usuário mexendo no Odoo normalmente.
            return None

        if mode == 'unlink':
            return self.env._(
                "O agente não apaga registros — nunca, em nenhum nível de "
                "acesso. Para desfazer, use cancelar ou arquivar (aqui: "
                "%(document_kind)s).",
                document_kind=self._capela_ai_model_name(model),
            )

        if model in INFRA_WRITABLE_MODELS or model in writes:
            return None

        return self.env._(
            "O agente só pode alterar o que a ferramenta declarou de "
            "antemão, e %(document_kind)s não está na lista dela. A ação foi "
            "recusada antes de gravar qualquer coisa.",
            document_kind=self._capela_ai_model_name(model),
        )

    @api.model
    def _capela_ai_model_name(self, model):
        """O nome que o usuário conhece, com o técnico como reserva."""
        described = self.env['ir.model']._get(model)
        return (described and described.name) or model
