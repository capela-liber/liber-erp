# -*- coding: utf-8 -*-
"""A nota de remessa não leva conta bancária -- ninguém vai pagar nada nela.

Bloqueio de produção de 26/08/2026. A tela do C08577 (reposição de consignação
da n-1) recusou o "Criar nota" com

    A conta bancária da sua empresa não é confiável. Peça a um administrador
    ou a alguém com direitos de aprovação para verificá-la.

O erro é do core e é legítimo no lugar dele: `_compute_partner_bank_id` carimba
a primeira conta ativa da empresa em TODA fatura de cliente, e `_post()` recusa
a fatura se essa conta não estiver marcada como confiável (`allow_out_payment`,
que na tela é o interruptor "Enviar dinheiro"). É uma trava anti-fraude: o
golpe comum é trocar o número da conta numa fatura por e-mail.

Só que consignação não movimenta dinheiro -- é valor de estoque que continua
nosso, na prateleira do outro -- e bonificação é doação. Nenhuma das duas
cobra, e o próprio módulo já liquida a nota no post (`_remessa_auto_settle`)
justamente para que ela nunca peça pagamento. Dizer nela em que conta se recebe
é declarar uma cobrança que não existe.

Marcar a conta como confiável é o conserto da FATURA DE VENDA, onde há mesmo o
que receber. Aqui não: a remessa não deve ter conta nenhuma.

O que a equipe fazia antes disto era apagar o campo à mão, nota por nota, antes
de confirmar (INV/2026/0083 às 14:08:44, confirmada às 14:08:45).
"""
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRemessaSemContaBancaria(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': "Livraria do Banco"})
        cls.product = cls.env['product.product'].create({
            'name': "Livro da Remessa", 'type': 'consu', 'list_price': 40.0})
        cls.journal = cls.company._get_remessa_journal()
        cls.mirror = cls.env['account.account'].create({
            'name': "(-) Remessa (teste banco)", 'code': 'REMBCO',
            'account_type': 'expense', 'company_ids': [(4, cls.company.id)]})
        cls.fpos = cls.env['account.fiscal.position'].create({
            'name': "Remessa (teste banco)", 'company_id': cls.company.id,
            'auto_invoice_paid': True,
            'auto_invoice_paid_account_id': cls.mirror.id})
        # O MUNDO DO DEFEITO: a empresa tem conta bancária e NENHUMA delas é
        # confiável. É o estado do prod -- a n-1 tem nove contas ativas e nem
        # uma marcada.
        #
        # As DUAS metades importam. Criar a conta e parar aí não reproduz nada:
        # o banco de teste já vem com uma conta ligada a diário bancário, e o
        # Odoo confia automaticamente em conta de diário
        # (account_journal.py: `bank.allow_out_payment = True`). Como
        # `_compute_partner_bank_id` ordena pondo as confiáveis na frente, era
        # ELA que ia parar na nota, e a trava nunca disparava: o teste ficava
        # verde por acidente. Derrubar a confiança de todas é o que põe o
        # `testing` no estado em que a n-1 está.
        cls.conta_da_casa = cls.env['res.partner.bank'].create({
            'acc_number': "12345-6",
            'partner_id': cls.company.partner_id.id,
            'company_id': cls.company.id,
        })
        # Tirar a confiança não pede o grupo (só PÔR pede), mas o campo é
        # `readonly` na tela para quem não o tem -- daí o sudo.
        cls.env['res.partner.bank'].sudo().search([
            ('partner_id', '=', cls.company.partner_id.id),
        ]).allow_out_payment = False

    def _nota_de_remessa(self):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'fiscal_position_id': self.fpos.id,
            'invoice_date': '2026-08-26',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id, 'quantity': 3,
                'price_unit': 20.0})],
        })

    def test_a_conta_da_casa_nasce_nao_confiavel(self):
        """A premissa do teste, dita em voz alta.

        Se um dia o Odoo passar a criar conta já confiável, os testes abaixo
        continuariam verdes sem provar nada -- e este aqui fica vermelho para
        avisar.
        """
        self.assertFalse(
            self.conta_da_casa.allow_out_payment,
            "conta bancária nasceu confiável: os testes abaixo perderam o mundo")

    def test_remessa_nao_carimba_conta_bancaria(self):
        nota = self._nota_de_remessa()
        self.assertFalse(
            nota.partner_bank_id,
            "a nota de remessa carimbou a conta %s: não há o que pagar nela"
            % nota.partner_bank_id.display_name)

    def test_remessa_confirma_com_a_conta_da_casa_nao_confiavel(self):
        """O clique que morreu em produção: Criar nota -> post.

        O POST RODA COMO GENTE, e não como o superusuário do `TransactionCase`.
        A diferença não é detalhe: para o uid 1 o core não barra nada -- ele
        apaga o campo em silêncio e segue ("Do not block in case of automated
        flows"). Quem apanha é o usuário de carne, que não tem direito de
        avalizar conta bancária e leva o UserError. Rodar este teste como
        superusuário o deixaria verde com o defeito de pé.
        """
        operadora = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': "Operadora da Remessa",
                'login': 'operadora_remessa_banco',
                'company_id': self.company.id,
                'company_ids': [(6, 0, [self.company.id])],
                'group_ids': [
                    (4, self.env.ref('base.group_user').id),
                    (4, self.env.ref('account.group_account_invoice').id),
                ],
            })
        self.assertFalse(
            operadora.has_group('account.group_validate_bank_account'),
            "a operadora avaliza conta bancária: o teste perdeu o mundo")
        self.assertFalse(operadora.has_group('base.group_system'))

        nota = self._nota_de_remessa()
        nota.with_user(operadora).action_post()

        self.assertEqual(nota.state, 'posted')
        self.assertFalse(nota.partner_bank_id)
        # e o que o módulo já prometia continua valendo: nada a receber
        self.assertEqual(nota.payment_state, 'paid')
        self.assertEqual(nota.amount_residual, 0.0)

    def test_trocar_o_cliente_nao_traz_a_conta_de_volta(self):
        """O compute é `store` e recalcula quando a dependência muda.

        Zerar o campo no create resolveria a nota de hoje e deixaria a de
        amanhã quebrar: basta alguém tocar no cliente ou na moeda para o Odoo
        recarimbar. Por isso o conserto é no compute, e não no create.
        """
        nota = self._nota_de_remessa()
        outro = self.env['res.partner'].create({'name': "Outra Livraria"})
        nota.partner_id = outro
        self.assertFalse(
            nota.partner_bank_id,
            "trocar o cliente recarimbou a conta na nota de remessa")

    def test_a_fatura_de_venda_continua_carimbando(self):
        """A contraprova, e a que importa: a venda comum não mudou.

        A conta na fatura de venda é informação legítima -- é onde a livraria
        deposita. O que se corrigiu foi o documento que não cobra, não a trava
        do core.
        """
        venda = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': '2026-08-26',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id, 'quantity': 1,
                'price_unit': 40.0})],
        })
        self.assertFalse(venda.journal_id.is_remessa,
                         "o teste caiu num diário de remessa e não prova nada")
        self.assertTrue(
            venda.partner_bank_id,
            "a fatura de venda deixou de dizer em que conta se recebe")
