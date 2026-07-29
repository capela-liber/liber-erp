# -*- coding: utf-8 -*-
"""A faxina do visitante: tirar do usuário o que a régua manda esconder.

Por que isto não cabe no XML. As entradas `(3, ...)` de `implied_ids` desfazem
o **vínculo de implicação** entre dois grupos -- e só isso. Se o usuário
carrega o grupo *diretamente*, porque alguém o concedeu na ficha ou porque um
módulo o concedeu numa cascata, nenhum `(3, ...)` o alcança: não há vínculo
para desfazer.

E a cascata acontece. Ao conceder `sales_team.group_sale_salesman_all_leads`
ao visitante em 27/07/2026, o `sale_project` acrescentou
`project.group_project_user` e o `website_sale` acrescentou
`website.group_website_restricted_editor` -- direto no usuário, sem passar
pelos implied_ids, sem erro nenhum. O app Projeto apareceu no home da conta
pública, e com ele o editor do site.

Reordenar a lista (concessões primeiro, remoções por último) foi a primeira
tentativa e não resolveu, exatamente pelo motivo acima: a ordem não muda o
fato de que `(3, ...)` não tem o que desfazer.

Então a faxina roda aqui, sobre os usuários, e é chamada por um `<function>`
no fim do liber_roles_groups.xml -- o que faz dela parte de todo `-u
liber_roles`, e não de uma migração de versão única. Toda atualização deste
módulo devolve a conta pública ao recorte declarado, aconteça o que acontecer
no meio.
"""

from odoo import api, models

#: Grupos que o visitante não pode ter, mesmo que alguém ou algum módulo
#: conceda. Espelha as entradas `(3, ...)` de group_visitante -- se você
#: mexer lá, mexa aqui.
CARONAS = (
    'sales_team.group_sale_manager',
    'stock.group_stock_manager',
    'project.group_project_user',
    'website.group_website_restricted_editor',
    'liber_soc_agreements.group_soc_manager',
    'liber_budget.group_budget_manager',
)


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _liber_faxina_do_visitante(self, extras=()):
        """Remove de quem é visitante os grupos que a régua manda esconder.

        `extras` são XML IDs de fora desta lista. Existe para o módulo que
        conceda grupo ao visitante e não possa ser citado aqui -- o nosso caso é
        um módulo proprietário, que este (AGPL) não pode ter como dependência.

        Por que parâmetro e não um método para sobrescrever: sem dependência
        declarada entre os dois módulos, a ordem de carga é livre, e quem carrega
        por último vence o MRO. O override falha calado -- a lista sai sem o
        grupo, e o visitante fica com uma permissão que ninguém quis dar.
        """
        visitante = self.env.ref('liber_roles.group_visitante',
                                 raise_if_not_found=False)
        if not visitante:
            return

        indesejados = self.env['res.groups']
        for xmlid in tuple(CARONAS) + tuple(extras):
            grupo = self.env.ref(xmlid, raise_if_not_found=False)
            if grupo:
                indesejados |= grupo
        if not indesejados:
            return

        # Só quem é visitante. Um diretor que também fosse visitante (não
        # existe hoje, mas o código não deve supor) perderia acesso legítimo
        # -- por isso a busca é pelo grupo, e a remoção é cirúrgica.
        visitantes = self.search([('all_group_ids', 'in', visitante.ids)])
        if not visitantes:
            return

        visitantes.write({'group_ids': [(3, g.id) for g in indesejados]})
        self.env.registry.clear_cache()
