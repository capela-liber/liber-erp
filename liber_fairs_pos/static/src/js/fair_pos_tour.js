/** @odoo-module **/
import { registry } from "@web/core/registry";

/* Um caixa nascendo, na tela.
 *
 * Um caixa nasce de um OPERADOR: digita-se o nome de quem vai estar no
 * balcão, e o caixa aparece com o nome da feira e o dele. O ORM já provava
 * que o registro é criado; o que ele não vê é a aba, a linha, o botão e o
 * caixa aparecendo na lista do Ponto de Venda com o nome certo. */
registry.category("web_tour.tours").add("fair_pos_birth_tour", {
    url: "/odoo/action-liber_fairs.action_event_fair",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "A lista de feiras abre",
        },
        {
            trigger: ".o_data_row .o_data_cell:contains('Feira do Caixa')",
            content: "Abrir a feira que já está vendendo",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "A ficha da feira abriu",
        },
        {
            trigger: ".o_notebook a.nav-link:contains('Caixas')",
            content: "Ir para a aba dos caixas",
            run: "click",
        },
        {
            trigger: ".o_field_x2many_list_row_add a",
            content: "Somar um operador",
            run: "click",
        },
        {
            // DENTRO DA LINHA. O formulário da feira também tem campos de
            // nome, e um seletor solto escrevia em cima do nome da feira.
            trigger: ".o_field_x2many_list .o_selected_row div[name='partner_id'] input",
            content: "Quem vai estar no balcão",
            run: "edit Joana do Caixa",
        },
        {
            trigger: ".o-autocomplete--dropdown-item:contains('Joana do Caixa')",
            content: "Escolher o contato",
            run: "click",
        },
        {
            trigger: "button[name='action_open_pos']",
            content: "Abrir os caixas",
            run: "click",
        },
        {
            // O caixa novo PELO NOME de quem o opera: é o que a pessoa
            // procura na tela do Ponto de Venda.
            trigger: ".o_kanban_renderer:contains('Joana'), .o_list_view:contains('Joana')",
            content: "O caixa da Joana existe",
        },
    ],
});

/* E o mesmo caixa fechando.
 *
 * Tour separado, com URL própria, de propósito: voltar de uma ação empilhada
 * por migalha de pão é frágil, e o que interessa aqui é o clique que encerra
 * a feira -- que fecha a sessão viva do caixa e tira os caixas da lista de
 * quem opera PDV todo dia. */
registry.category("web_tour.tours").add("fair_pos_death_tour", {
    url: "/odoo/action-liber_fairs.action_event_fair",
    steps: () => [
        {
            trigger: ".o_data_row .o_data_cell:contains('Feira do Caixa')",
            content: "Abrir a feira",
            run: "click",
        },
        {
            trigger: "button[name='action_return']",
            content: "Encerrar a feira: é isto que fecha os caixas",
            run: "click",
        },
        {
            trigger: ".o_form_view:not(:has(button[name='action_return']))",
            content: "A feira voltou, e os caixas com ela",
        },
    ],
});
