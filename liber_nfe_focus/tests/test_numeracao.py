# -*- coding: utf-8 -*-
"""A numeração própria da NFe: quando a casa numera, e o que isso exige.

Trazida em 12/08/2026 porque o campo do painel da Focus não gravava e não
havia como conferir o que ela guardava -- cada tentativa custava uma nota
emitida. O que estes testes travam não é "funciona": é o comportamento nas
bordas, que é onde numeração fiscal machuca.
"""
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged

from .test_account_move_focus import preparar_documento_latam


@tagged('post_install', '-at_install')
class TestNumeracaoPropria(AccountTestInvoicingCommon):
    """Herda o ambiente contábil de propósito: dois destes testes precisam de
    uma fatura de verdade, e criar `account.move` num banco com o `l10n_br` por
    perto exige diário, moeda e tipo de documento LATAM. Montar isso à mão aqui
    seria reescrever o que o `AccountTestInvoicingCommon` já monta certo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']

    def _fatura_vazia(self):
        """Uma fatura só para exercitar a gravação da resposta da Focus."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-08-12',
        })
        preparar_documento_latam(move)
        return move

    def setUp(self):
        super().setUp()
        self.company.sudo().write({
            'nfe_serie_homologacao': 0, 'nfe_proximo_numero_homologacao': 0,
            'nfe_serie_producao': 0, 'nfe_proximo_numero_producao': 0,
        })

    def test_sem_configurar_a_focus_continua_numerando(self):
        """O padrão não muda para quem não pediu nada."""
        serie, numero = self.company._nfe_reservar_numero('homologacao')
        self.assertEqual((serie, numero), (0, 0),
                         "empresa sem numeração configurada deve devolver (0,0) "
                         "-- é o que faz o payload sair sem serie/numero")

    def test_reserva_avanca_e_nao_repete(self):
        """Cada reserva entrega um número e deixa o próximo pronto."""
        self.company.sudo().write({'nfe_serie_homologacao': 1,
                                   'nfe_proximo_numero_homologacao': 11022})
        self.assertEqual(self.company._nfe_reservar_numero('homologacao'), (1, 11022))
        self.assertEqual(self.company._nfe_reservar_numero('homologacao'), (1, 11023))
        self.assertEqual(self.company._nfe_reservar_numero('homologacao'), (1, 11024))
        self.assertEqual(
            self.company.sudo().nfe_proximo_numero_homologacao, 11025,
            "o campo tem de refletir a próxima reserva, não a última entregue")

    def test_os_dois_ambientes_nao_se_misturam(self):
        """Homologação e produção têm contadores separados -- na SEFAZ também.

        Se um vazasse no outro, um teste em homologação queimaria número da
        produção, e o buraco só apareceria na contabilidade.
        """
        self.company.sudo().write({
            'nfe_serie_homologacao': 9, 'nfe_proximo_numero_homologacao': 31,
            'nfe_serie_producao': 1, 'nfe_proximo_numero_producao': 11022,
        })
        self.assertEqual(self.company._nfe_reservar_numero('homologacao'), (9, 31))
        self.assertEqual(
            self.company.sudo().nfe_proximo_numero_producao, 11022,
            "reservar em homologação mexeu no contador de produção")
        self.assertEqual(self.company._nfe_reservar_numero('producao'), (1, 11022))

    def test_serie_sem_numero_nao_numera(self):
        """Meia configuração é configuração nenhuma.

        Série preenchida e número zerado (ou o contrário) devolve (0,0) em vez
        de emitir com número 0 -- que a SEFAZ rejeitaria, e depois de já ter
        gasto a tentativa.
        """
        self.company.sudo().write({'nfe_serie_homologacao': 1,
                                   'nfe_proximo_numero_homologacao': 0})
        self.assertEqual(self.company._nfe_reservar_numero('homologacao'), (0, 0))
        self.company.sudo().write({'nfe_serie_homologacao': 0,
                                   'nfe_proximo_numero_homologacao': 11022})
        self.assertEqual(self.company._nfe_reservar_numero('homologacao'), (0, 0))

    def test_reemissao_reusa_o_numero_da_nota(self):
        """A borda que evita buraco na sequência.

        Nota rejeitada pela SEFAZ volta para a fila e é reenviada. Se cada
        tentativa tirasse número novo, uma rejeição boba (cadastro do
        destinatário) abriria buraco. Rejeição não consome número na SEFAZ,
        então reusar é o certo.
        """
        move = self.env['account.move'].new({'company_id': self.company.id})
        payload = {}
        move.focus_numero, move.focus_serie = '11022', '1'
        move._focus_aplicar_numeracao(payload)
        self.assertEqual((payload.get('numero'), payload.get('serie')), (11022, 1))
        self.assertEqual(
            self.company.sudo().nfe_proximo_numero_homologacao, 0,
            "reemissão não pode consumir número novo")

    def test_rejeicao_nao_apaga_o_numero_reservado(self):
        """A borda que só apareceu emitindo de verdade.

        A resposta da Focus sobrescrevia número e série SEMPRE. Enquanto quem
        numerava era ela, não havia nada nosso a perder; com a numeração da
        casa, uma rejeição (que não traz número) apagava o número já reservado
        -- e a tentativa seguinte tiraria outro, deixando o anterior órfão.
        """
        move = self._fatura_vazia()
        move.sudo().write({'focus_numero': '11022', 'focus_serie': '1'})

        move._focus_aplicar_resposta({
            'status': 'erro_autorizacao',
            'mensagem_sefaz': 'Rejeição: qualquer coisa de cadastro',
        })

        self.assertEqual(move.focus_numero, '11022',
                         "a rejeição apagou o número reservado")
        self.assertEqual(move.focus_serie, '1')

    def test_autorizacao_grava_o_numero_que_a_sefaz_confirmou(self):
        """O outro lado: quando a resposta TRAZ número, ele manda.

        É o que mantém a fatura fiel ao que existe na SEFAZ, inclusive para as
        empresas onde quem numera continua sendo a Focus.
        """
        move = self._fatura_vazia()
        move._focus_aplicar_resposta({
            'status': 'autorizado', 'numero': '11022', 'serie': '1',
            'mensagem_sefaz': 'Autorizado o uso da NF-e',
        })
        self.assertEqual(move.focus_numero, '11022')
        self.assertEqual(move.focus_serie, '1')
