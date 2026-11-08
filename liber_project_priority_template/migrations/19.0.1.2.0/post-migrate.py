"""Cada modelo que já existe passa a valer para o projeto em que mora.

Até a 19.0.1.1.0, o projeto do card-modelo dizia as duas coisas: de quem era
a estrela que o disparava e onde a subtarefa nascia. A partir daqui são dois
campos; o modelo antigo fica valendo onde estava.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE project_task
           SET priority_template_project_id = project_id
         WHERE is_template
           AND parent_id IS NULL
           AND priority_template_project_id IS NULL
           AND project_id IS NOT NULL
    """)
