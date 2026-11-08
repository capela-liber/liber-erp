# -*- coding: utf-8 -*-
{
    'name': 'Liber Project Priority Templates',
    'version': '19.0.1.3.0',
    'summary': 'Starring a task creates its sub-tasks from a template, one per priority level',
    'description': """
Pauta pela estrela — um módulo para as operações de **marketing**.

A estrela é a expectativa sobre o lançamento: quanto maior, mais ações de
divulgação o card pede. Para a produção editorial, que anda por colunas e
prazos, há o irmão ``liber_project_stage_jobs`` (jobs por coluna).

Quando um card ganha estrela (Média, Alta ou Urgente), cada card-modelo do
projeto marcado com a mesma estrela vira uma subtarefa dele.

Onde mora o template
====================

Nos **modelos de tarefa nativos** do Odoo 19. Cada card-modelo é uma subtarefa
em potencial: nome, responsável, coluna (estágio), marcadores e descrição vão
para a subtarefa. A estrela é a do próprio card-modelo. Três modelos com ★★
dão três subtarefas, na ordem da lista. As subtarefas que um card-modelo tem
dentro vêm junto, como subtarefas da subtarefa: o que o modelo mostra é o que
a tarefa recebe.

Como as Tarefas recorrentes, é uma opção do projeto: **Definições →
Gerenciamento de tarefas → Subtarefas por prioridade**, com o link **Modelos
de tarefa**, que abre a lista dos modelos daquele projeto (e só dele). Não há
menu.

Regras
======

* A estrela manda: trocar de ★ para ★★ tira as subtarefas do ★ que ninguém
  mexeu e põe as do ★★; tirar a estrela tira as intocadas.
* Subtarefa mexida é trabalho feito e fica: qualquer gravação (nome,
  responsável, coluna, prazo...), um comentário no chatter, ou uma subtarefa
  nova dentro dela. Vale para o bloco inteiro: neta mexida segura a filha.
* Subtarefa feita à mão nunca sai, e não impede a estrela de gerar as do
  modelo. Modelo que já tem a sua subtarefa lá não é copiado de novo.
* Só a tarefa de primeiro nível dispara; os próprios modelos nunca.
* Projeto com a opção desligada não dispara nem comenta.
* Cada troca deixa uma nota no chatter: o que entrou, o que saiu, o que ficou
  por já ter sido mexido, e a estrela sem modelo.

Tarefa-mãe na busca
===================

A busca das tarefas, em todo board, ganha **Tarefa-mãe**: digitar o nome do
card traz as subtarefas dele, e **Agrupar por → Tarefa-mãe** separa uma
coluna por card. É o que acha, no board do Design, a arte que veio de um
lançamento da Editoria.
""",
    'author': 'EdLab Press',
    'category': 'Services/Project',
    'depends': ['project'],
    'data': [
        'views/task_template_views.xml',
        'views/project_project_views.xml',
        'views/project_task_search_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_project_priority_template/static/src/js/priority_template_tour.js',
            'liber_project_priority_template/static/src/js/priority_star_tour.js',
            'liber_project_priority_template/static/src/js/mother_task_tour.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
