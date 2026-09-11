# -*- coding: utf-8 -*-
"""Quem só LÊ a contabilidade também lê este relatório.

A ACL do modelo nascia liberando leitura a `account.group_account_user` -- o
contador PLENO. O menu, por outro lado, não tem grupo nenhum: aparece para
quem tem o app de Faturamento. O resultado, medido em 11/09/2026 na
demonstração pública, foi o pior dos dois mundos: o Odoo some com o menu de
quem não lê o modelo, e o manual publicado ficou falando de uma tela que
aquele perfil não tem.

O conserto é trocar o grupo da ACL pelo `account.group_account_readonly`.
Não afrouxa nada: o `group_account_user` IMPLICA o readonly, então todo
contador pleno continua lendo: quem ganha é o somente-leitura, que é quem
devia estar lendo um relatório de leitura desde o começo.

Este é um relatório: leitura para os dois, escrita para ninguém.
"""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_aged_receivable')
class TestAclSomenteLeitura(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        company = cls.env.ref('base.main_company')
        base = {
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
        }
        # Somente-leitura PELADO: só o grupo de leitura da contabilidade, para
        # o teste medir esse perfil e não o do admin, que passa em tudo.
        cls.somente_leitura = Users.create(dict(
            base, name='Contador somente leitura',
            login='readonly_receber@liber.test',
            group_ids=[(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('account.group_account_readonly').id,
            ])]))
        cls.contador = Users.create(dict(
            base, name='Contador pleno', login='pleno_receber@liber.test',
            group_ids=[(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('account.group_account_user').id,
            ])]))
        cls.env.flush_all()
        cls.env.registry.clear_cache()

    # --------------------------------------------------------- caminho feliz
    def test_somente_leitura_le_o_relatorio(self):
        env = self.env(user=self.somente_leitura.id, su=False)
        env['liber.aged.receivable'].check_access('read')
        env['liber.aged.receivable'].search([], limit=5).mapped('display_name')

    def test_contador_pleno_continua_lendo(self):
        """O conserto não pode ter tirado de quem já tinha."""
        env = self.env(user=self.contador.id, su=False)
        env['liber.aged.receivable'].check_access('read')

    def test_o_grupo_da_acl_e_o_de_leitura(self):
        """A ACL aponta para o readonly, e o pleno o implica.

        Sem a implicação, trocar o grupo teria TIRADO o acesso do contador
        pleno em vez de somar o do somente-leitura.
        """
        readonly = self.env.ref('account.group_account_readonly')
        pleno = self.env.ref('account.group_account_user')
        self.assertIn(readonly, pleno.all_implied_ids,
                      'o contador pleno deixou de implicar o somente-leitura: '
                      'a troca da ACL passa a restringir em vez de somar')

    # ------------------------------------------------------------- é leitura
    def test_ninguem_escreve_no_relatorio(self):
        """Relatório é view SQL: escrita não existe para perfil nenhum."""
        for user in (self.somente_leitura, self.contador):
            env = self.env(user=user.id, su=False)
            with self.assertRaises(AccessError):
                env['liber.aged.receivable'].check_access('write')

    # --------------------------------------------------------- caso de erro
    def test_sem_grupo_de_contabilidade_nao_le(self):
        """A régua corta dos dois lados: usuário interno cru não entra."""
        Users = self.env['res.users'].with_context(no_reset_password=True)
        cru = Users.create({
            'name': 'Sem contabilidade', 'login': 'cru_receber@liber.test',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.env.registry.clear_cache()
        env = self.env(user=cru.id, su=False)
        with self.assertRaises(AccessError):
            env['liber.aged.receivable'].check_access('read')
