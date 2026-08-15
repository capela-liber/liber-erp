# -*- coding: utf-8 -*-
"""A ponte com o `liber_roles`, na direção certa.

Pedido da direção em 10/08/2026: "amazon tem que estar disponível para o
comercial; pense num balanço entre gerente e assistente".

O balanço não precisou ser inventado — este módulo já o tinha desenhado, e a
grade da casa só encaixa nele. Vale escrever a correspondência, porque ela é o
argumento:

- **Comercial/Assistente → Operator** (`group_liber_amazon_user`). É quem
  trabalha o pedido: importa da Amazon, corrige o casamento de produto e gera
  a cotação. Lê a conta e não a altera (`r1 w0 c0 u0` em
  `liber.amazon.account`), e não apaga pedido. O grupo já implica
  `sales_team.group_sale_salesman` porque a cotação é documento de vendas — o
  comercial já o tem por outro caminho, e a redundância aqui é do módulo, não
  nossa.
- **Comercial/Gerente → Manager** (`group_liber_amazon_manager`). É quem
  monta a operação: cria e edita a conta Amazon, escolhe o cliente, mexe nas
  unidades, apaga pedido e abre o menu Configuração.
- **Direção → Manager.** Não é generosidade: desde 09/08/2026 a régua do
  `liber_roles` é que a Direção alcança tudo que qualquer função alcança, e há
  um teste lá que junta o fecho de todos os perfis e exige que não sobre nada
  fora do dela. Sem esta linha, dar a Amazon ao Comercial deixaria aquele
  teste vermelho — apontando para cá, corretamente.

O que NENHUM dos dois recebe, e é bom dizer: a **credencial**. O refresh token
e os campos da conexão são `groups="base.group_system"` no próprio modelo, e
nenhum grupo daqui contorna isso. O gerente cria a conta; o administrador cola
o token.

Por que a concessão mora AQUI e não no `liber_roles`. O `liber_roles` está
instalado em prod, staging, liber e testing; este módulo, não em todos. Uma
linha lá viraria dependência de módulo, e o próximo `-u liber_roles` numa base
sem Amazon iria querer instalar o módulo inteiro sem ninguém ter pedido. A
seta se inverte, como já acontece com o `capela_influencers` e o
`liber_support`: o módulo opcional é que se pendura no `liber_roles` **se ele
estiver instalado**. Nenhum dos dois declara dependência do outro.

Uma armadilha que já mordeu a casa e que este arquivo herda: a ponte roda na
instalação e em todo `-u`. Instalar o módulo numa base ANTES de o clone ter
este arquivo deixa o app sem dono nenhum, sem erro e sem aviso — foi
exatamente o que aconteceu com o `liber_support` em prod. Se instalar a Amazon
numa base nova, rode um `-u liber_amazon_vendor` depois.
"""

from odoo import api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _liber_amazon_ligar_no_comercial(self):
        """Dá a Amazon ao Comercial (nos dois níveis) e à Direção.

        Chamada por um `<function>` do data/liber_roles_bridge.xml. Sem o
        liber_roles instalado, não faz nada e não reclama.

        `(4, ...)` e não uma lista fechada: os comandos de x2many são
        incrementais, então um `-u liber_roles` reaplica o XML de lá — que
        também é uma lista de `(4, ...)` / `(3, ...)` — e não apaga o que
        acrescentamos aqui. A ordem entre os dois módulos deixa de importar.
        """
        #: perfil do liber_roles -> nível da Amazon que ele recebe
        CONCESSOES = {
            'liber_roles.group_comercial_assistente': 'group_liber_amazon_user',
            'liber_roles.group_comercial_gerente': 'group_liber_amazon_manager',
            'liber_roles.group_direcao': 'group_liber_amazon_manager',
        }
        for xmlid_perfil, nivel in CONCESSOES.items():
            perfil = self.env.ref(xmlid_perfil, raise_if_not_found=False)
            grupo = self.env.ref('liber_amazon_vendor.%s' % nivel,
                                 raise_if_not_found=False)
            if perfil and grupo:
                perfil.write({'implied_ids': [(4, grupo.id)]})
