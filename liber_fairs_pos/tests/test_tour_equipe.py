# -*- coding: utf-8 -*-
"""OS DOIS PERFIS DA PRAÇA, na tela, logados como eles.

O ORM diz quem tem qual direito. Ele não diz qual menu aparece dentro do
aplicativo, qual botão o formulário desenhou e qual aba existe -- e é aí que
mora a diferença entre os dois perfis:

  A OPERADORA vende no caixa dela e, sozinha na praça, confere a carga que
  chega. Caixa de livro chega no meio do movimento, e esperar gerente para
  conferir é deixar a mercadoria na calçada. Fora isso, nada: nem perdas, nem
  modelos, nem os outros eventos da casa.

  O GERENTE DE CAMPO é circunstancial. Ele toca o evento na rua: entra no
  caixa das colegas para destravar problema, dá desconto acima do praticado,
  conta a mesa, fecha o dia, registra perda e manda a mercadoria de volta. Ele
  NÃO planeja -- e, principalmente, não decide quanto ele mesmo ou os outros
  vão ganhar. Isso é de quem monta o evento, e é anterior à feira.

Cada tour entra com o usuário do perfil, criado pelo próprio módulo (é o
`action_open_pos` que concede o acesso), e não com o admin: admin passa em
tudo e não prova nada sobre perfil.
"""
from datetime import date, timedelta

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs_pos_tour')
class TestTourEquipe(HttpCase):

    def _palco(self):
        """Uma feira com carga esperando conferência e duas pessoas na equipe."""
        company = self.env.company
        hoje = date.today()
        livros = self.env['product.product'].create([{
            'name': 'Livro dos Dois Perfis %02d' % i,
            'type': 'consu', 'is_storable': True,
            'list_price': 40.0 + i, 'standard_price': 12.0 + i,
        } for i in range(1, 4)])
        armazem = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        for livro in livros:
            self.env['stock.quant']._update_available_quantity(
                livro, armazem.lot_stock_id, 60)

        fair = self.env['event.fair'].create({
            'name': 'Feira dos Dois Perfis',
            'date_start': hoje,
            'date_end': hoje + timedelta(days=1),
            'company_id': company.id,
            'line_ids': [(0, 0, {
                'product_id': livro.id, 'qty_planned': 9, 'qty_min': 3,
            }) for livro in livros],
        })
        fair.action_plan()

        # As duas pessoas. O contato vira usuário: sem conta, a pessoa
        # trabalha o balcão e não abre o sistema -- que é o caso comum, e não
        # o que este teste quer provar.
        equipe = {}
        for nome, papel in (('Operadora da Praça', 'operator'),
                            ('Gerente da Praça', 'manager')):
            contato = self.env['res.partner'].create({'name': nome})
            login = 'tour_%s' % papel
            self.env['res.users'].with_context(
                no_reset_password=True).create({
                    'name': nome, 'login': login, 'password': login,
                    'lang': 'pt_BR', 'partner_id': contato.id,
                    'company_id': company.id,
                    'company_ids': [(6, 0, [company.id])],
                    'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
                })
            equipe[papel] = self.env['event.fair.cashier'].create({
                'fair_id': fair.id, 'partner_id': contato.id, 'role': papel})

        # O acesso é dado pela abertura dos caixas, como na vida real.
        fair.action_open_pos()

        # E o depósito despacha: sem carga validada não há o que conferir --
        # não se confere a chegada de quem não saiu.
        saida = fair.action_ship()
        saida.action_assign()
        for move in saida.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        saida.button_validate()
        return fair, equipe

    def test_a_operadora_recebe_sozinha(self):
        self._palco()
        self.start_tour('/odoo', 'fair_operator_tour', login='tour_operator')

    def test_o_gerente_de_campo_na_tela(self):
        self._palco()
        self.start_tour('/odoo', 'fair_lead_tour', login='tour_manager')
