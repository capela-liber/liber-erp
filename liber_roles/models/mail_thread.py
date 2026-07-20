# -*- coding: utf-8 -*-
"""A exceção que faz o visitante conversar.

Para o Odoo, postar no chatter de um documento é um ato de escrita: o
`mail.message` só nasce se o autor tiver `write` no documento (o padrão de
`_mail_post_access`, em mail/models/models.py). Modelos voltados ao portal
baixam isso para `read` -- é assim que um cliente comenta numa tarefa que ele
não pode editar.

O visitante quer exatamente esse regime, só que em todo o sistema: pode ler,
logo pode comentar. Baixamos a exigência para `read` apenas quando quem está
postando é visitante, e apenas na criação da mensagem. Editar e apagar
mensagem alheia continuam pedindo `write` -- e o guarda de
`ir_model_access.py` nega.
"""

from odoo import models

from .ir_model_access import VISITOR_GROUP


class Base(models.AbstractModel):
    _inherit = 'base'

    def _mail_get_operation_for_mail_message_operation(self, message_operation):
        operations = super()._mail_get_operation_for_mail_message_operation(message_operation)
        if message_operation == 'create' and self.env.user.has_group(VISITOR_GROUP):
            return dict.fromkeys(operations, 'read')
        return operations
