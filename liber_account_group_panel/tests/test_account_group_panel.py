# -*- coding: utf-8 -*-
"""A barra lateral do Plano de Contas, medida no ORM.

O que se prova aqui não é o desenho: é que `group_id`, que o core define como
compute SEM store, passou a ser exprimível em SQL -- e portanto agrupável e
filtrável, que é tudo o que o `searchpanel` pede.
"""
from odoo.tests import tagged

from .common import AccountGroupPanelCommon


@tagged('post_install', '-at_install')
class TestAccountGroupPanel(AccountGroupPanelCommon):

    # --- o compute do core continua dizendo a verdade -----------------------

    def test_group_id_resolve_a_rubrica_mais_funda(self):
        """Cada conta cai na rubrica mais específica que cobre o seu código."""
        self.assertEqual(self.acc_banco.group_id, self.g_caixa)
        self.assertEqual(self.acc_clientes.group_id, self.g_receber)
        self.assertEqual(self.acc_venda.group_id, self.g_receita)

    def test_group_id_cai_no_ancestral_quando_falta_a_folha(self):
        """Edge: sem rubrica `1.1.9`, a conta pousa em `1.1`."""
        self.assertEqual(self.acc_orfa_rasa.group_id, self.g_circulante)

    def test_group_id_vazio_fora_do_plano(self):
        """Erro do lado do dado: código que nenhuma rubrica cobre não inventa uma."""
        self.assertFalse(self.acc_sem_rubrica.group_id)

    # --- o que o core NÃO fazia: group_id em SQL ----------------------------

    def test_group_id_filtra_em_banco(self):
        """`search` em group_id -- era ValueError antes deste módulo."""
        encontradas = self.env['account.account'].search([
            ('id', 'in', self.accounts.ids),
            ('group_id', 'in', self.g_caixa.ids),
        ])
        self.assertEqual(encontradas, self.acc_banco | self.acc_caixa)

    def test_group_id_agrupa_em_banco(self):
        """`_read_group` em group_id: é o que alimenta os contadores do painel."""
        grupos = self.env['account.account']._read_group(
            [('id', 'in', self.accounts.ids)],
            groupby=['group_id'],
            aggregates=['__count'],
        )
        contagem = {(g.id if g else False): n for g, n in grupos}
        self.assertEqual(contagem.get(self.g_caixa.id), 2)
        self.assertEqual(contagem.get(self.g_receber.id), 1)
        self.assertEqual(contagem.get(self.g_circulante.id), 1)
        self.assertEqual(contagem.get(self.g_receita.id), 1)
        self.assertEqual(contagem.get(False), 1, "a conta fora do plano fica sem rubrica")

    # --- e o painel propriamente dito ---------------------------------------

    def test_searchpanel_devolve_a_arvore(self):
        """O painel sai HIERÁRQUICO: `parent_id` volta preenchido e encadeia."""
        resultado = self.env['account.account'].search_panel_select_range(
            'group_id',
            search_domain=[('id', 'in', self.accounts.ids)],
            enable_counters=True,
            limit=False,
        )
        self.assertEqual(resultado['parent_field'], 'parent_id')

        por_id = {v['id']: v for v in resultado['values']}
        # Os pais entram no painel mesmo sem conta própria: `parent_of`.
        self.assertIn(self.g_ativo.id, por_id)
        self.assertIn(self.g_circulante.id, por_id)
        self.assertIn(self.g_caixa.id, por_id)

        self.assertFalse(por_id[self.g_ativo.id]['parent_id'])
        self.assertEqual(por_id[self.g_circulante.id]['parent_id'], self.g_ativo.id)
        self.assertEqual(por_id[self.g_caixa.id]['parent_id'], self.g_circulante.id)
        self.assertEqual(por_id[self.g_caixa.id]['__count'], 2)

        # E o nome é a rubrica, não o recorte de dois caracteres: era `1.`.
        self.assertEqual(
            por_id[self.g_circulante.id]['display_name'],
            '7.1 Ativo Circulante do Tour')

    def test_searchpanel_root_id_era_inutil(self):
        """A régua: o painel antigo devolve `1`, `1.`, `3`, `3.` -- e nada mais."""
        resultado = self.env['account.account'].search_panel_select_range(
            'root_id',
            search_domain=[('id', 'in', self.accounts.ids)],
            limit=False,
        )
        nomes = {v['display_name'] for v in resultado['values']}
        self.assertEqual(nomes, {'7', '7.', '8', '8.', '9', '9.'})

    def test_view_herdada_trocou_o_campo(self):
        """A view de busca do core passou a declarar group_id no searchpanel."""
        arch = self.env['account.account'].get_view(
            self.env.ref('account.view_account_search').id, 'search')['arch']
        self.assertIn('group_id', arch)
        self.assertNotIn('root_id', arch)
