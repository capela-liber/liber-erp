# -*- coding: utf-8 -*-
"""A ficha de contato abre para as treze funções da casa.

A régua de 20/08/2026 é simples de dizer -- todo Gerente cadastra contato,
todo Assistente lê -- e foi por pouco que ela não nasceu falsa: a leitura
existia no ACL e a TELA não abria. Quem levantou foi a direção, com o print
do erro:

    Você não tem permissão para acessar registros de 'Contrato de
    Consignação' (consignment.agreement).

O contato não tem nada com consignação. O que havia era um cartão de
Consignação no formulário do parceiro (`liber_soc_agreements`) cujo compute
lê `consignment.agreement` como o usuário -- e o formulário é de todo mundo.
Dez das treze funções (todas menos o Comercial, a Direção e o Visitante)
esbarravam nele ANTES de a tela desenhar.

Este teste não trava aquele campo: trava a CLASSE do problema. Ele monta o
formulário como cada função, pega todos os campos que o arch pede e lê um a
um. Qualquer módulo que amanhã pendurar na ficha de contato um campo que lê
modelo cercado cai aqui, e não no colo de quem for cadastrar uma livraria.

⚠️ A ARMADILHA DE ESCREVER ESTE TESTE, registrada porque ela custou meia hora
e passaria por verde: o cache do ORM é da TRANSAÇÃO, não do usuário. Sem o
`invalidate_all()` antes de cada leitura, o primeiro perfil da lista (a
Direção, que pode tudo) computa o campo e todos os outros o encontram no
cache -- o teste passa com o bug em pé. É a diferença entre "ninguém
reclamou" e "está certo".
"""
from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_roles')
class TestFichaDeContato(TransactionCase):

    DEPARTAMENTOS = ('comercial', 'logistica', 'financeiro',
                     'editorial', 'juridico', 'marketing')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        company = cls.env.company

        cls.funcoes = (['direcao']
                       + ['%s_%s' % (dep, nivel)
                          for dep in cls.DEPARTAMENTOS
                          for nivel in ('assistente', 'gerente')]
                       + ['visitante'])
        cls.usuario = {}
        for funcao in cls.funcoes:
            cls.usuario[funcao] = Users.create({
                'name': funcao, 'login': '%s@contatos.test' % funcao,
                'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, cls.env.ref(
                    'liber_roles.group_%s' % funcao).id)],
            })

        #: uma livraria de verdade, com endereço e filho -- a ficha vazia não
        #: exercita os campos relacionais, que é justamente onde mora o risco
        cls.contato = cls.env['res.partner'].create({
            'name': 'Livraria da Ficha', 'is_company': True,
            'street': 'Rua do Teste, 1', 'city': 'São Paulo',
            'child_ids': [(0, 0, {'name': 'Compras', 'type': 'contact'})],
        })
        cls.env.flush_all()
        cls.env.registry.clear_cache()

    def _campos_do_arch(self, modelo, vista_xmlid, modo):
        """Os campos do próprio res.partner que a tela pede, como o usuário.

        Campos de subview (dentro de outro `<field>`) ficam de fora: são de
        outro modelo, e quem responde por eles é o teste daquele modelo.
        """
        vista = self.env.ref(vista_xmlid, raise_if_not_found=False)
        if not vista:
            return None
        arch = etree.fromstring(modelo.get_view(vista.id, modo)['arch'])
        nomes = []
        for no in arch.iter('field'):
            nome = no.get('name')
            if not isinstance(nome, str) or nome not in modelo._fields:
                continue
            if nome in nomes:
                continue
            pai, dentro_de_subview = no.getparent(), False
            while pai is not None:
                if pai.tag == 'field':
                    dentro_de_subview = True
                    break
                pai = pai.getparent()
            if not dentro_de_subview:
                nomes.append(nome)
        return nomes

    def test_a_ficha_de_contato_abre_para_todas_as_funcoes(self):
        vistas = (('form', 'base.view_partner_form'),
                  ('list', 'base.view_partner_tree'),
                  ('kanban', 'base.res_partner_kanban_view'))
        for funcao in self.funcoes:
            modelo = self.env['res.partner'].with_user(self.usuario[funcao])
            for modo, xmlid in vistas:
                self.env.invalidate_all()
                nomes = self._campos_do_arch(modelo, xmlid, modo)
                if nomes is None:
                    continue
                self.assertTrue(
                    nomes, '%s: a %s do contato veio sem campo nenhum'
                    % (funcao, modo))
                for nome in nomes:
                    # o cache é da transação: sem isto, quem lê depois da
                    # Direção lê o valor DELA e o teste passa com o bug em pé
                    self.env.invalidate_all()
                    try:
                        modelo.browse(self.contato.id).read([nome])
                    except Exception as erro:
                        self.fail(
                            'a %s do contato não abre para %s: o campo `%s` '
                            'esbarrou em %s.\nA ficha de contato é de toda a '
                            'casa; o campo que pendura nela um modelo cercado '
                            'precisa de `groups=` -- no campo E no nó da '
                            'view.' % (modo, funcao, nome,
                                       str(erro).splitlines()[0]))

    def test_o_cartao_da_consignacao_e_de_quem_tem_consignacao(self):
        """O caso concreto que originou o teste acima, pelos dois lados.

        Não basta a tela abrir: o cartão tem de aparecer para quem trabalha
        com consignação -- se o conserto tivesse sido "apagar o botão", este
        teste é quem reclamaria.
        """
        campo = 'consignment_agreement_count'
        for funcao in ('comercial_assistente', 'comercial_gerente', 'direcao'):
            modelo = self.env['res.partner'].with_user(self.usuario[funcao])
            self.env.invalidate_all()
            self.assertIn(
                campo, self._campos_do_arch(
                    modelo, 'base.view_partner_form', 'form'),
                '%s perdeu o cartão de Consignação na ficha do cliente'
                % funcao)

        for funcao in ('logistica_gerente', 'editorial_gerente',
                       'juridico_gerente', 'marketing_gerente',
                       'financeiro_gerente'):
            modelo = self.env['res.partner'].with_user(self.usuario[funcao])
            self.env.invalidate_all()
            self.assertNotIn(
                campo, self._campos_do_arch(
                    modelo, 'base.view_partner_form', 'form'),
                '%s enxerga o cartão de Consignação: o `groups=` do campo '
                'não pegou, e a ficha volta a quebrar' % funcao)
