/** @odoo-module **/

/**
 * A estrela pela tela: ★ traz o modelo ★, ★★ troca pelo modelo ★★.
 *
 * O ORM prova a troca; este prova que a tela não grava nada nas subtarefas
 * ao salvar a mãe -- se gravasse, elas virariam "mexidas" e a troca não
 * aconteceria. Roda no perfil de usuário de projeto, que precisa poder apagar.
 */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("priority_star_tour", {
    steps: () => [
        {
            content: "uma estrela",
            trigger: ".o_form_view div[name=priority] .o_priority_star:eq(0)",
            run: "click",
        },
        {
            content: "salva",
            trigger: ".o_form_button_save",
            run: "click",
        },
        {
            content: "aba Subtarefas",
            trigger: ".o_notebook_headers .nav-link:contains(Sub-tasks)",
            run: "click",
        },
        {
            content: "veio o modelo ★",
            trigger: ".o_field_widget[name=child_ids] td:contains(Modelo Uma)",
        },
        {
            content: "duas estrelas",
            trigger: ".o_form_view div[name=priority] .o_priority_star:eq(1)",
            run: "click",
        },
        {
            content: "salva",
            trigger: ".o_form_button_save",
            run: "click",
        },
        {
            content: "o ★ intocado saiu e entrou o ★★",
            trigger: ".o_field_widget[name=child_ids]:not(:has(td:contains(Modelo Uma))) td:contains(Modelo Duas)",
        },
    ],
});
