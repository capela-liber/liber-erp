/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Mover livros de uma prateleira para outra, no perfil de quem opera o
 * depósito -- a tela real, não o ORM.
 *
 * O tour cria a transferência interna do zero: prateleira de origem,
 * prateleira de destino, uma linha, Validar. O mundo (duas prateleiras TST-
 * e um livro com 10 exemplares na primeira) é semeado por
 * tests/test_tour_transferencia_interna.py, que confere os saldos no fim.
 *
 * Os passos miram a estrutura (nomes de campo e de botão), nunca o texto
 * traduzido; a sessão roda em inglês como os outros tours da casa.
 *
 *     odoo.startTour("shelves_transferencia_interna_tour")
 */
registry.category("web_tour.tours").add("shelves_transferencia_interna_tour", {
    // Direto na ação: o menu de apps é instável sob web_responsive.
    url: "/odoo/action-stock.action_picking_tree_internal",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "A lista de transferências internas abre para o depósito",
        },
        {
            trigger: ".o_list_button_add",
            content: "Nova transferência",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "O formulário abre com a raiz nos dois locais",
        },
        {
            trigger: ".o_field_widget[name='location_id'] input",
            content: "A prateleira de onde os livros saem",
            run: "edit TST-000001",
        },
        {
            trigger: ".o-autocomplete--dropdown-item:contains('TST-000001')",
            content: "Escolher a prateleira de origem",
            run: "click",
        },
        {
            // A prateleira do cliente (CO/...) existe, é interna, e NÃO pode
            // aparecer aqui: transferência interna é do armazém.
            trigger: ".o_field_widget[name='location_dest_id'] input",
            content: "Procurar a prateleira de um cliente no destino",
            run: "edit Livraria do Tour",
        },
        {
            trigger: ".o-autocomplete--dropdown-menu:not(:has(.o-autocomplete--dropdown-item:contains('Livraria do Tour')))",
            content: "A lista não oferece a prateleira do cliente",
        },
        {
            trigger: ".o_field_widget[name='location_dest_id'] input",
            content: "A prateleira para onde vão",
            run: "edit TST-000002",
        },
        {
            trigger: ".o-autocomplete--dropdown-item:contains('TST-000002')",
            content: "Escolher a prateleira de destino",
            run: "click",
        },
        {
            trigger: ".o_field_x2many_list_row_add a",
            content: "Adicionar o livro",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='product_id'] input",
            content: "Qual livro",
            run: "edit Os Sertões do Tour",
        },
        {
            trigger: ".o-autocomplete--dropdown-item:contains('Os Sertões do Tour')",
            content: "Escolher o livro",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='product_uom_qty'] input",
            content: "Quantos",
            run: "edit 3",
        },
        {
            // O Validar do rascunho (o_btn_validate) confirma, reserva e
            // valida de uma vez.
            trigger: "button.o_btn_validate",
            content: "Validar",
            run: "click",
        },
        {
            trigger: ".o_statusbar_status button[data-value='done'].o_arrow_button_current",
            content: "A transferência está concluída",
        },
        {
            trigger: "body:not(:has(.modal))",
            content: "E nenhuma caixa de erro subiu no caminho",
        },
    ],
});

/**
 * A armadilha da raiz, vista da tela: a transferência preparada pelo teste
 * saiu com a raiz na origem e a reserva caiu na própria prateleira de
 * destino. Validar tem de ser recusado com uma caixa que diz isso.
 */
registry.category("web_tour.tours").add("shelves_armadilha_da_raiz_tour", {
    // Sem `url`: o teste abre a transferência pelo id, direto no formulário
    // (a lista do testing tem centenas de internas, e a nova não está na
    // primeira página).
    steps: () => [
        {
            trigger: ".o_form_view_container",
            content: "A transferência que saiu da raiz abre pronta para validar",
        },
        {
            // A coluna Separar de denuncia: a prateleira reservada é a de
            // destino. É o que o core escondia atrás de Detalhes.
            trigger: ".o_data_row td[name='shelf_from']:contains('TST-000002')",
            content: "Separar de mostra a própria prateleira de destino",
        },
        {
            trigger: "button[name='button_validate']:not(.o_btn_validate)",
            content: "Validar -- o clique do acidente",
            run: "click",
        },
        {
            trigger: ".modal:contains('Nothing would move')",
            content: "A guarda recusou e explicou",
        },
    ],
});
