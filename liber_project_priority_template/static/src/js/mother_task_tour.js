/** @odoo-module **/

/**
 * Tarefa-mãe na busca: no board do Design, achar e agrupar as subtarefas que
 * vieram de um card de outro board. Roda como usuário de projeto.
 */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("mother_task_tour", {
    steps: () => [
        {
            content: "busca pelo nome do card-mãe",
            trigger: ".o_searchview_input",
            run: "edit Livro da Mãe",
        },
        {
            content: "escolhe buscar em Tarefa-mãe",
            trigger: ".o_searchview_autocomplete .o-dropdown-item:contains(Mother task)",
            run: "click",
        },
        {
            content: "só a subtarefa daquele card",
            trigger: ".o_kanban_view:not(:has(.o_kanban_record:contains(Arte de outro livro))) .o_kanban_record:contains(Arte do livro)",
        },
        {
            content: "limpa a busca",
            trigger: ".o_searchview .o_facet_remove",
            run: "click",
        },
        {
            content: "abre as opções da busca",
            trigger: ".o_searchview_dropdown_toggler",
            run: "click",
        },
        {
            content: "agrupar por Tarefa-mãe",
            trigger: ".o_group_by_menu .o-dropdown-item:contains(Mother task)",
            run: "click",
        },
        {
            content: "uma coluna por card-mãe",
            trigger: ".o_kanban_group .o_column_title:contains(Livro da Mãe)",
        },
    ],
});
