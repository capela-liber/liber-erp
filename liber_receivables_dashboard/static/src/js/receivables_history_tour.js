/** @odoo-module **/

/**
 * O Histórico dos Recebíveis pela tela, no perfil de quem vai usá-lo.
 *
 * O teste de ORM ao lado prova o que a foto guarda; ele não prova que a tela
 * abre. Aqui se afirma o que o DOM mostra: a lista chega agrupada por mês e
 * por faixa (é assim que a ação abre), e o menu Ações traz "Take today's
 * snapshot" para quem tem contabilidade.
 *
 * A sessão roda em inglês: os nomes na fonte são os do manifesto.
 */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("liber_receivables_history_tour", {
    url: "/odoo/action-liber_receivables_dashboard.liber_receivables_snapshot_action",
    steps: () => [
        {
            content: "a lista do histórico montou, agrupada por mês; abre o mês",
            trigger: ".o_list_view .o_group_header",
            run: "click",
        },
        {
            // Dentro do mês, a lista agrupa por faixa: abre a primeira.
            content: "dentro do mês, as faixas; abre a primeira",
            trigger: ".o_list_view .o_group_header:not(.o_group_open)",
            run: "click",
        },
        {
            content: "as linhas da faixa aparecem",
            trigger: ".o_list_view .o_data_row",
        },
        {
            // O menu Ações só existe com linhas marcadas: marca todas.
            content: "marca as linhas",
            trigger: ".o_list_view thead .o_list_record_selector input",
            run: "click",
        },
        {
            content: "o menu Ações apareceu",
            trigger: ".o_control_panel .o_cp_action_menus .dropdown-toggle",
            run: "click",
        },
        {
            content: "e traz a foto de hoje, para quem tem contabilidade",
            trigger: ".o-dropdown--menu .dropdown-item:contains(\"Take today's snapshot\")",
        },
    ],
});
