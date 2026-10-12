# -*- coding: utf-8 -*-
"""A ponte com o `liber_roles`, na direção certa.

Pedido da direção em 10/08/2026: o Atendimento tem de aparecer para o
Comercial, nos dois níveis.

Por que a concessão mora AQUI e não lá. O `liber_roles` traduz funções da casa
em grupos do Odoo, e a tentação é escrever mais uma linha no `implied_ids` do
Comercial. Não dá: o `liber_roles` está instalado em `prod`, `staging`, `liber`
e `testing`, e o `liber_support` só no `testing`. Uma linha lá viraria uma
dependência de módulo, e o próximo `-u liber_roles` em produção iria querer
instalar o atendimento inteiro na futura produção sem ninguém ter pedido.

Então a seta se inverte, como já acontece com o `capela_influencers`: o módulo
opcional é que se pendura no `liber_roles` **se ele estiver instalado**. Nenhum
dos dois declara dependência do outro, e onde o atendimento não existe isto é
um no-op silencioso.

Quem recebe, e em que nível. A régua veio da direção e cai exatamente onde os
ACLs deste módulo já cortavam:

- **Comercial/Assistente → `group_support_user`.** É o atendente: grava o
  chamado (responde, muda de fase, põe selo) e apenas **lê** equipes e selos.
  Fazer o atendimento, não configurá-lo.
- **Comercial/Gerente → `group_support_manager`.** Administra: cria e edita
  equipes, selos e as horas de SLA que moram na equipe. Ele implica o
  `group_support_user`, então o nível de baixo vem junto e não se escreve duas
  vezes -- aresta redundante entra fácil e só sai com `(3, ...)`.
- **Direção → `group_support_manager`.** Não é generosidade: desde 09/08/2026 a
  régua do `liber_roles` é que a Direção alcança tudo que qualquer função
  alcança, e há um teste lá que junta o fecho de todos os perfis e exige que
  não sobre nada fora do dela. Sem esta linha, dar o atendimento ao Comercial
  deixaria aquele teste vermelho -- apontando para cá, corretamente.

- **Visitante → `group_support_user`** (desde 12/10/2026, decisão do dono:
  "ele é Liber também"). Até então ficava de fora, por ser conversa de cliente;
  na vitrine os chamados são de demonstração, e a escrita do visitante segue
  travada pela allowlist do `liber_roles`, como em todo o resto. NOTES §4.

As concessões saem todas da MESMA chamada de propósito: assim aparecem e somem
juntas, e o teste de superconjunto do `liber_roles` nunca vê um estado pela
metade -- a ordem de carga entre módulos sem dependência é livre.
"""

from odoo import api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _liber_support_ligar_no_comercial(self):
        """Dá o Atendimento ao Comercial (atendente e gerente) e à Direção.

        Chamada por um `<function>` do data/liber_roles_bridge.xml, então roda
        na instalação E em todo `-u liber_support`. Sem o liber_roles
        instalado, não faz nada e não reclama.

        `(4, ...)` e não uma lista fechada: os comandos de x2many são
        incrementais, então um `-u liber_roles` reaplica o XML de lá -- que
        também é uma lista de `(4, ...)` / `(3, ...)` -- e não apaga o que
        acrescentamos aqui. A ordem entre os dois módulos deixa de importar.
        """
        #: perfil do liber_roles -> nível do atendimento que ele recebe
        CONCESSOES = {
            'liber_roles.group_comercial_assistente': 'group_support_user',
            'liber_roles.group_comercial_gerente': 'group_support_manager',
            'liber_roles.group_direcao': 'group_support_manager',
            'liber_roles.group_visitante': 'group_support_user',
        }
        for xmlid_perfil, nivel in CONCESSOES.items():
            perfil = self.env.ref(xmlid_perfil, raise_if_not_found=False)
            grupo = self.env.ref('liber_support.%s' % nivel,
                                 raise_if_not_found=False)
            if perfil and grupo:
                perfil.write({'implied_ids': [(4, grupo.id)]})
        self._liber_support_visitante_le_tudo()

    @api.model
    def _liber_support_visitante_le_tudo(self):
        """A demonstração lê TODOS os chamados, não só os da equipe dele.

        No nível de usuário, a regra "own teams" mostra só os chamados das
        equipes de que a pessoa é membro -- e o visitante não é membro de
        nenhuma, então a lista abria vazia (12/10/2026). Uma regra só de
        LEITURA, só para o visitante: as regras de grupo se somam com OU, e
        as operações de escrita seguem barradas pela allowlist do liber_roles.
        Mora aqui, e não em XML, porque citar o grupo do liber_roles num
        arquivo de dados seria dependência de módulo.
        """
        visitante = self.env.ref('liber_roles.group_visitante',
                                 raise_if_not_found=False)
        if not visitante:
            return
        Regra = self.env['ir.rule'].sudo().with_context(active_test=False)
        modelo = self.env['ir.model']._get('liber.support.ticket')
        valores = {
            'name': 'Support ticket: the demo visitor reads all',
            'model_id': modelo.id,
            'domain_force': '[(1, "=", 1)]',
            'groups': [(6, 0, visitante.ids)],
            'perm_read': True, 'perm_write': False,
            'perm_create': False, 'perm_unlink': False,
            'active': True,
        }
        regra = Regra.search([('name', '=', valores['name']),
                              ('model_id', '=', modelo.id)], limit=1)
        if regra:
            regra.write(valores)
        else:
            Regra.create(valores)
