# -*- coding: utf-8 -*-
"""O visitante: entra em tudo, não grava no que importa.

A apresentação pública do site precisa de uma conta que possa ser passada
adiante sem medo. Ela abre qualquer tela, roda qualquer relatório e conversa
pelo chatter -- mas não emite um S000 nem mexe no plano de contas.

Os grupos do Odoo somam permissão, nunca subtraem: não existe "grupo de
leitura" capaz de cancelar o write que outro grupo concedeu. Então o visitante
recebe o pacote de leitura mais largo da casa e a gravação é cortada um nível
abaixo, em `ir.model.access.check` -- por onde passa todo create/write/unlink
do ORM (`models.BaseModel._check_access` chama esse método antes das regras de
registro). Cortar aqui vale mais que esconder menus: fecha também a chamada
direta por RPC e a URL colada no navegador.

O corte é uma ALLOWLIST, não uma lista negra. Lista negra vaza: todo modelo
novo -- de um módulo nosso ou de um app instalado amanhã -- nasceria gravável.
Aqui nasce bloqueado, e liberar é uma linha explícita.

Duas fronteiras que este guarda NÃO cobre, ditas em voz alta:

- `sudo()`. Código que grava como superusuário passa (`env.su` é o primeiro
  desvio de `check`). É o preço de não quebrar o login, o cron e o envio de
  e-mail, que gravam por baixo do usuário. Os botões comuns do Odoo (confirmar
  pedido, validar fatura) gravam como o usuário e ficam barrados.
- Modelos transitórios. Os assistentes abrem e preenchem; o efeito deles cai
  no modelo real, que segue bloqueado. Preferimos o assistente abrindo e
  falhando no "Aplicar" a um menu que nem abre -- é uma demonstração.
"""

from odoo import api, models
from odoo.exceptions import AccessError

VISITOR_GROUP = 'liber_roles.group_visitante'

#: O que o visitante PODE gravar. Tudo o mais é leitura.
VISITOR_WRITABLE_MODELS = frozenset({
    # Conversar: chatter, seguidores, atividades, reações, anexos da mensagem.
    'mail.message',
    'mail.followers',
    'mail.notification',
    'mail.activity',
    'mail.message.reaction',
    'mail.link.preview',
    'discuss.channel',
    'discuss.channel.member',
    'ir.attachment',
    # A própria sessão: presença no chat e preferências de interface.
    'bus.presence',
    'res.users.settings',
    'res.users.settings.volumes',
})


class IrModelAccess(models.Model):
    _inherit = 'ir.model.access'

    @api.model
    def check(self, model, mode='read', raise_exception=True):
        if mode != 'read' and not self.env.su and self._is_visitor_blocked(model):
            if raise_exception:
                raise self._make_access_error(model, mode)
            return False
        return super().check(model, mode=mode, raise_exception=raise_exception)

    def _make_access_error(self, model, mode):
        """A recusa do visitante é esperada, não é um defeito de configuração.

        A mensagem padrão do Odoo manda "procurar o administrador" e lista os
        grupos que dariam acesso -- conselho inútil para quem está vendo o
        sistema pela primeira vez numa apresentação. Trocamos por uma frase
        que explica o que está acontecendo.
        """
        if mode != 'read' and not self.env.su and self._is_visitor_blocked(model):
            return AccessError(self.env._(
                "Modo visitante: esta é uma conta de demonstração e não grava "
                "dados. Você pode navegar por todas as telas, abrir relatórios "
                "e escrever no chatter — mas não criar, alterar ou apagar "
                "registros (aqui: %(document_kind)s).",
                document_kind=self.env['ir.model']._get(model).name or model,
            ))
        return super()._make_access_error(model, mode)

    def _is_visitor_blocked(self, model):
        """Este usuário é visitante e este modelo está fora da allowlist?"""
        if not self.env.user.has_group(VISITOR_GROUP):
            return False
        if model in VISITOR_WRITABLE_MODELS:
            return False
        Model = self.env.get(model)
        # Assistente: abre e preenche; o efeito cai no modelo real, bloqueado.
        return Model is None or not Model.is_transient()
