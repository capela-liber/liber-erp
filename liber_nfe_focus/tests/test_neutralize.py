# -*- coding: utf-8 -*-
"""O `neutralize` deste módulo: base de ensaio não emite nota de verdade.

O `odoo neutralize` do core desliga cron e e-mail e não sabe o que é NFe. O
ambiente da emissão é campo nosso e viaja no dump: em 27/08/2026 o dev acordou
de um clone do prod com `producao` em três das seis empresas e o token de
produção preenchido -- um clique na tela teria emitido nota válida.

O que se prova aqui é o arquivo que o core executa, rodado como ele roda: SQL
cru contra o banco de teste. Se o arquivo sumir ou parar de cobrir empresa
nova, este teste cai.
"""
import os

from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged("post_install", "-at_install")
class TestNeutralize(TransactionCase):

    CAMINHO = "liber_nfe_focus/data/neutralize.sql"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with file_open(cls.CAMINHO) as f:
            cls.sql = f.read()

    def _rodar(self):
        # O SQL do core roda direto no cursor: o que a ORM ainda tem na mão
        # não existe para ele. Sem o flush, o teste mede a própria memória.
        self.env.flush_all()
        self.env.cr.execute(self.sql)
        self.env.invalidate_all()

    def test_o_arquivo_esta_onde_o_core_procura(self):
        """O core lê `data/neutralize.sql` pelo caminho, não pelo manifesto."""
        self.assertTrue(os.path.basename(self.CAMINHO) == "neutralize.sql")
        self.assertIn("res_company", self.sql)

    def test_empresa_em_producao_volta_para_homologacao(self):
        """Caminho feliz: é exatamente o acidente de 27/08 sendo desfeito."""
        empresa = self.env.company
        empresa.focus_ambiente = "producao"
        self._rodar()
        self.assertEqual(empresa.focus_ambiente, "homologacao")

    def test_pega_todas_as_empresas_e_nao_so_a_ativa(self):
        """Eram três das seis: neutralizar uma empresa não neutraliza a casa."""
        outra = self.env["res.company"].search(
            [("id", "!=", self.env.company.id)], limit=1)
        if not outra:
            self.skipTest("banco de uma empresa só")
        (self.env.company | outra).write({"focus_ambiente": "producao"})
        self._rodar()
        self.assertEqual(
            set((self.env.company | outra).mapped("focus_ambiente")),
            {"homologacao"})

    def test_quem_ja_estava_em_homologacao_nao_e_tocado(self):
        """Caso de borda: rodar duas vezes não é diferente de rodar uma."""
        empresa = self.env.company
        empresa.focus_ambiente = "homologacao"
        antes = empresa.write_date
        self._rodar()
        self._rodar()
        self.assertEqual(empresa.focus_ambiente, "homologacao")
        self.assertEqual(empresa.write_date, antes,
                         "o UPDATE mexeu em linha que já estava certa")

    def test_o_token_de_producao_continua_no_lugar(self):
        """Erro que não se comete: apagar credencial. Quem decide é o ambiente.

        Um banco neutralizado que perdeu o token não volta a ser produção sem
        alguém recolar segredo -- e recolar segredo é onde o segredo vaza.
        """
        empresa = self.env.company.sudo()
        empresa.write({"focus_ambiente": "producao",
                       "focus_token_producao": "token-de-teste"})
        self._rodar()
        self.assertEqual(empresa.focus_ambiente, "homologacao")
        self.assertEqual(empresa.focus_token_producao, "token-de-teste")
