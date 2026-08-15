# -*- coding: utf-8 -*-
{
    'name': 'Liber Support',
    'version': '19.0.0.1.0',
    'summary': 'Commercial support desk: email in, kanban triage, basic SLA, '
               'order link',
    'description': """
Atendimento comercial — protótipo.

PROTÓTIPO, só no banco ``testing``. Desenho e decisões em
``_mds/atendimento-comercial.md``; desvios do desenho em ``NOTES.md`` na
pasta do módulo.

O que faz
=========

* Cada caixa comercial (``comercial@edlab.press``, ``@hedra.com.br``,
  ``@n-1edicoes.org``) vira o alias de uma equipe; o e-mail que chega cria um
  chamado na empresa certa.
* Kanban de triagem por estágio (Novo, Em andamento, Aguardando cliente,
  Aguardando interno, Resolvido, Fechado, Spam).
* A equipe lê e responde pelo chatter: "Enviar mensagem" vai ao cliente,
  "Nota" fica interna.
* Vínculo com o pedido (``sale.order``); o vínculo com a CO
  (``consignment.settlement``) entra pela ponte ``liber_support_soc``.
* SLA de dois relógios em horas úteis (primeira resposta e resolução), com
  pausa em "Aguardando cliente" e cron de atraso.

O que NÃO faz (de propósito)
============================

* Não guarda a caixa IMAP: a captura é por encaminhamento para o alias,
  como era no Odoo 15.
* Não migra os chamados do Helpdesk do 15 — decisão adiada.
* Não fala WhatsApp: os campos ``channel``/``external_ref`` existem para o
  dia em que o Chatwoot entrar como transporte.
""",
    'author': 'EdLab Press',
    'category': 'Services/Support',
    'depends': ['base', 'mail', 'sale', 'resource'],
    'data': [
        'security/liber_support_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/support_stage_data.xml',
        'data/ir_cron.xml',
        'data/mail_layout_clean.xml',
        'views/support_ticket_views.xml',
        'views/support_team_views.xml',
        'views/support_stage_views.xml',
        'views/sale_order_views.xml',
        'views/liber_support_menus.xml',
        # por último: a ponte precisa dos grupos daqui já carregados
        'data/liber_roles_bridge.xml',
    ],
    'installable': True,
    'application': True,
    # Família liber_ (ERP do selo), decisão de 10/08/2026: o balcão de
    # e-mail simples é do selo; capela_ fica reservado ao atendimento
    # multicanal complexo (Chatwoot, painéis) do plano antigo.
    'license': 'AGPL-3',
}
