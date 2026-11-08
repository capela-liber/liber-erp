# -*- coding: utf-8 -*-
{
    'name': 'Liber Project Stage Jobs',
    'version': '19.0.1.0.0',
    'summary': 'Entering a column schedules the jobs of that column as activities, dated from the deadline',
    'description': """
Jobs por coluna — um módulo para a **produção editorial**.

O irmão deste módulo, ``liber_project_priority_template``, serve ao marketing:
a estrela diz quanto se espera do lançamento, e a pauta vem dela. A produção
não anda por expectativa, anda por **colunas e prazos**: o card entra em
Produção e os jobs daquela coluna viram **atividades** dele, cada uma com
responsável, roteiro e data.

Onde mora o job
===============

Na própria **coluna**: engrenagem → Editar → aba **Jobs**. Cada linha é um job:
nome, tipo de atividade, responsável (vazio = o responsável do card), **dias**
e o **roteiro** (a nota da atividade — como checar o fechamento de um livro,
por exemplo). Pode haver jobs em mais de uma coluna: Produção tem os seus,
Prelo os seus.

A data
======

O **Período de produção** é o número de dias que se conta para trás do
**Prazo final** do card até o início da produção. Mora na coluna, no mesmo
formulário dos jobs (60 por omissão); não há nada global. Cada job vence no
início mais os seus dias: Prazo final 30/03, período de 60 dias, capa em 20
dias → a capa vence em 18/02 (−60 + 20).

Card sem Prazo final agenda as atividades de hoje mais os dias, e a nota do
chatter avisa. Quando o Prazo final é posto ou muda, as atividades
**intocadas** ganham a data nova; as que alguém já mexeu (data, responsável,
nota) ficam com a sua.

Regras
======

* Entrar na coluna cria as atividades dos jobs dela. Sair **não remove nada**:
  depois da produção o card segue mudando, e as atividades são trabalho em
  curso.
* Voltar à coluna não duplica: job que ainda tem a sua atividade aberta no
  card não é agendado de novo. Atividade concluída virou histórico; se o card
  voltar à coluna, o job é agendado outra vez.
* Só o card de primeiro nível dispara; modelos de tarefa nunca.
""",
    'author': 'EdLab Press',
    'category': 'Services/Project',
    'depends': ['project'],
    'data': [
        'security/ir.model.access.csv',
        'views/project_task_type_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_project_stage_jobs/static/src/js/stage_jobs_tour.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
