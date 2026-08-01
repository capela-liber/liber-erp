# -*- coding: utf-8 -*-
"""O CFOP é tabela nacional: um código, um registro.

Mais de um módulo declara CFOP em XML — os treze da consignação aqui, os 619
oficiais no `liber_nfe_focus` — com `xmlid` de módulos diferentes para o mesmo
código. Sem adoção, o Odoo cria dois registros; e desde que o código virou
único, o segundo `INSERT` derruba a instalação inteira com `duplicate key`.

Foi o que aconteceu em 31/07/2026 ao instalar a casa num banco novo. O defeito
não estava no dado, estava na ordem: com o focus entrando primeiro, o
carregamento daqui quebrava; com ele entrando depois, passava. Testar isso é
testar a invariante, não a ordem — ordem de instalação não se prende.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCfopAdocao(TransactionCase):

    def test_nenhum_codigo_de_cfop_se_repete(self):
        self.env.cr.execute("""
            SELECT code, count(*) FROM nfe_cfop
             WHERE code IS NOT NULL GROUP BY code HAVING count(*) > 1
        """)
        repetidos = self.env.cr.fetchall()
        self.assertFalse(
            repetidos, "CFOP repetido no banco: %s. Quem escolhe na tela não vê "
            "diferença, e a nota sai com a natureza de um ou de outro conforme "
            "a sorte do search." % repetidos)

    def test_os_cfops_da_consignacao_existem_uma_vez_cada(self):
        for codigo in ('5113', '6113', '5114', '6114', '5919', '6919', '5949'):
            achados = self.env['nfe.cfop'].search([('code', '=', codigo)])
            self.assertEqual(
                len(achados), 1,
                "esperava um CFOP %s, achei %d" % (codigo, len(achados)))

    def test_o_xmlid_daqui_aponta_para_um_cfop_de_verdade(self):
        cfop = self.env.ref('liber_soc_audit.cfop_5113', raise_if_not_found=False)
        self.assertTrue(cfop, "o xmlid cfop_5113 deste módulo não resolve")
        self.assertEqual(cfop.code, '5113')

    def test_focus_e_consignacao_compartilham_o_mesmo_registro(self):
        """A prova da adoção: dois xmlid, um CFOP."""
        modulo = self.env['ir.module.module'].search(
            [('name', '=', 'liber_nfe_focus'), ('state', '=', 'installed')])
        if not modulo:
            self.skipTest("liber_nfe_focus não está instalado neste banco")
        daqui = self.env.ref('liber_soc_audit.cfop_5113')
        de_la = self.env.ref('liber_nfe_focus.cfop_5113')
        self.assertEqual(
            daqui.id, de_la.id,
            "os dois módulos declaram o CFOP 5113 e apontam para registros "
            "diferentes — a adoção do pre_init_hook não rodou")

    def test_um_cfop_duplicado_e_recusado(self):
        """A rede que segura o resto: com o focus instalado, o código é único."""
        modulo = self.env['ir.module.module'].search(
            [('name', '=', 'liber_nfe_focus'), ('state', '=', 'installed')])
        if not modulo:
            self.skipTest("a unicidade do código vem com o liber_nfe_focus")
        from psycopg2.errors import UniqueViolation
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self.env['nfe.cfop'].create({'code': '5113', 'name': 'Cópia indevida'})
            self.env.flush_all()
