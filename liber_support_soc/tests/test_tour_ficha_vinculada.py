# -*- coding: utf-8 -*-
"""A ficha de um chamado que já tem documento vinculado abre?

Nasceu de "não consigo abrir chamados da Catavento" (13/08/2026).

O caminho até aqui vale a nota, porque o próximo relato desses vai chegar do
mesmo jeito. O servidor não ajudava: no log do staging **toda** chamada do
cliente respondia 200, e `ir_logging` estava vazio -- o erro era do navegador, e
navegador não escreve no log de ninguém. O que resolveu foi perguntar ao banco
o que aqueles chamados tinham que os outros não tinham:

    de 1.884 chamados, só TRÊS tinham pedido de venda vinculado,
    e os três eram da Catavento.

Dois deles são também dois dos três com CO vinculada. Não era o cliente: era o
vínculo. E o que o vínculo faz na tela é acender o botão do topo, escondido em
todos os outros por `invisible="not sale_order_id"`.

Este teste semeia essa condição -- pedido e CO ligados ao chamado -- e abre a
ficha pela tela. Se o cliente quebrar ao desenhar o botão, o `HttpCase` falha
pelo erro de console, mesmo que nenhum passo do tour chegue a reprovar.

O que exatamente quebrava foi medido, não deduzido: com o campo dentro de
`<span class="o_stat_value">` o tour morre em `OwlError: Cannot find the
definition of component "FormLabel"`; com o MESMO campo solto dentro do
`<div class="o_stat_info">` (a forma do liber_amazon_vendor) ele passa. Ou
seja, "campo dentro de botão" não é a regra -- o nível de aninhamento é. A
suspeita de que o Amazon tinha o mesmo defeito foi levantada e derrubada
rodando as duas formas.
"""
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestFichaVinculadaTour(HttpCase):

    def test_ficha_com_pedido_e_co_abre(self):
        partner = self.env['res.partner'].create({
            'name': 'Distribuidora do Vínculo', 'is_company': True,
            'allow_consignment': True,
        })
        product = self.env['product.product'].create({
            'name': 'Livro do Vínculo', 'type': 'consu', 'is_storable': True,
            'list_price': 90.0, 'sale_ok': True,
        })
        team = self.env['liber.support.team'].create({
            'name': 'Comercial do Vínculo', 'company_id': self.env.company.id,
            'alias_name': 'tour-vinculo-test',
        })
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': product.id,
                                   'product_uom_qty': 2})],
        })
        settlement = self.env['consignment.settlement'].create({
            'partner_id': partner.id,
        })
        ticket = self.env['liber.support.ticket'].create({
            'name': 'Chamado com vínculos', 'team_id': team.id,
            'partner_id': partner.id,
            'kind': 'sale',
            'sale_order_id': order.id,
            'settlement_id': settlement.id,
        })
        # A condição que se quer provar é a do banco do staging, não a que o
        # teste acha que criou: se um dos dois vínculos não tivesse pegado, o
        # tour abriria uma ficha comum e passaria sem testar nada.
        self.assertTrue(ticket.sale_order_id, "o chamado nasceu sem pedido")
        self.assertTrue(ticket.settlement_id, "o chamado nasceu sem CO")

        self.start_tour('/odoo', 'liber_support_ficha_vinculada_tour',
                        login='admin')
