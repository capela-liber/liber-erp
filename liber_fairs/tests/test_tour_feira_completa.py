# -*- coding: utf-8 -*-
"""O caminho inteiro da feira na TELA, com dados fundos por baixo.

Não basta uma feira e um livro. Uma tela vazia esconde justamente os defeitos
que aparecem quando há dados: coluna que não soma, filtro que traz o que não
devia, lista que abre em branco porque o filtro padrão comeu tudo, botão de
cabeçalho que só nasce com linhas marcadas. Por isso este teste encena uma
casa com feiras em três estados -- uma que voltou (com perdas), uma que está
em curso e a que o tour vai operar -- e só então abre o navegador.

A mesma encenação, mais funda, está em `scripts/seed_fairs_demo.py`, que
serve ao banco de demonstração da vitrine. Aqui ela é menor de propósito: o
tour tem de ser determinístico e rápido.
"""
from datetime import date, timedelta

from odoo.tests import HttpCase, tagged



# A senha do usuário de tour é IGUAL AO LOGIN -- é assim que o `start_tour`
# entra. O literal fica no login e a senha o referencia: escrito das duas
# vezes, ele casa com a varredura de segredos do publish_liber_erp.sh e barra
# a publicação inteira.
LOGIN = 'tour_feira_completa'

@tagged('post_install', '-at_install', 'liber_fairs_tour')
class TestTourFeiraCompleta(HttpCase):

    def _usuario(self, company):
        grupos = [(4, self.env.ref('liber_fairs.group_fair_manager').id)]
        papel = self.env.ref('liber_roles.group_comercial_gerente',
                             raise_if_not_found=False)
        if papel:
            grupos.append((4, papel.id))
        # Sem o papel de Inventário DE PROPÓSITO: quem trabalha a feira não
        # opera o depósito, e a conferência tem de funcionar assim.
        return self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Feira do Tour Completo',
                'login': LOGIN,
                'password': LOGIN,
                'lang': 'pt_BR',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': grupos,
            })

    def _titulos(self, quantos=6):
        livros = self.env['product.product'].create([{
            'name': 'Título de Feira %02d' % i,
            'type': 'consu',
            'is_storable': True,
            'list_price': 30.0 + i,
            'standard_price': 15.0 + i,
        } for i in range(1, quantos + 1)])
        armazem = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        for livro in livros:
            self.env['stock.quant']._update_available_quantity(
                livro, armazem.lot_stock_id, 80)
        return livros

    def _feira(self, nome, livros, inicio, dias=1, qty=8):
        return self.env['event.fair'].create({
            'name': nome,
            'date_start': inicio,
            'date_end': inicio + timedelta(days=dias - 1),
            'company_id': self.env.company.id,
            'line_ids': [(0, 0, {
                'product_id': livro.id,
                'qty_planned': qty,
                'qty_min': 3,
            }) for livro in livros],
        })

    def _entregar(self, fair):
        saida = fair.action_ship()
        saida.action_assign()
        for move in saida.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        saida.button_validate()
        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt' and p.state != 'done')
        chegada.action_fair_check()
        return fair

    def test_o_caminho_inteiro_na_tela(self):
        company = self.env.company
        hoje = date.today()
        livros = self._titulos()

        # Um modelo salvo, para a tela de modelos não abrir vazia.
        self.env['event.fair.template'].create({
            'name': 'Modelo geral de feira',
            'company_id': company.id,
            'line_ids': [(0, 0, {
                'product_id': livro.id, 'qty_planned': 8, 'qty_min': 3,
            }) for livro in livros],
        })

        # Uma feira que já voltou, com venda e perda: dá história ao módulo.
        passada = self._feira('Feira que já voltou', livros,
                              hoje - timedelta(days=30), dias=2)
        passada.action_plan()
        self._entregar(passada)
        dia = passada.day_ids[0]
        dia.action_fill()
        for linha in dia.line_ids:
            linha.qty_counted = max(0, linha.qty_expected - 3)
        dia.action_close()
        volta = passada.action_return()
        if volta.state in ('done', 'cancel'):
            return volta
        volta.action_assign()
        for move in volta.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        volta.button_validate()
        de_volta = passada.picking_ids.filtered(
            lambda p: p.fair_operation == 'return' and p.state != 'done')
        if de_volta:
            de_volta.action_fair_check()

        # Uma feira em curso, para a lista não ter uma linha só.
        em_curso = self._feira('Feira em curso', livros[:3],
                               hoje - timedelta(days=1), dias=3)
        em_curso.action_plan()
        self._entregar(em_curso)

        # E a feira que o tour vai operar. O depósito JÁ DESPACHOU e validou
        # uma carga -- é ela que espera conferência na praça --, e sobra
        # quantidade planejada para o tour apertar Despachar e ver a segunda
        # sair. Carga que o depósito não validou não aparece em Recebimentos,
        # e é assim que tem de ser: não se confere a chegada de quem não saiu.
        fair = self._feira('Feira do Tour Completo', livros, hoje, dias=2)
        fair.action_plan()
        primeira = fair.action_ship()
        primeira.action_assign()
        for move in primeira.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        primeira.button_validate()
        fair.line_ids[0].qty_planned += 4

        self._usuario(company)
        self.start_tour('/odoo', 'fair_full_tour',
                        login=LOGIN)

        fair.invalidate_recordset()
        self.assertEqual(fair.state, 'shipped')
        self.assertEqual(
            len(fair.picking_ids.filtered(
                lambda p: p.fair_operation == 'shipment')), 2,
            "O Despachar da tela tinha de soltar a segunda carga")
        self.assertTrue(all(line.qty_sent for line in fair.line_ids),
                        "A conferência na tela tem de ter feito a carga "
                        "CHEGAR: sem isso, o ok geral não fez nada")
        fechados = fair.day_ids.filtered(lambda d: d.state == 'closed')
        self.assertTrue(
            fechados,
            "Nenhum dia fechou. Dias da feira: %s" % [
                (str(d.date), d.state) for d in fair.day_ids])
        self.assertTrue(sum(fechados.mapped('qty_sold')) > 0,
                        "A contagem corrigida para baixo virou venda")
