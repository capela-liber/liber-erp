/** @odoo-module **/
import { registry } from "@web/core/registry";

/* Aplicar um modelo à grade, na tela, com o perfil do comercial.
 *
 * Existe porque o teste de ORM do mesmo caminho passava enquanto a tela não
 * deixava aplicar. O ORM mede o que o teste pediu; o tour mede o que a tela
 * pede -- o direito de ler event.fair.template, o botão dentro da aba, o
 * diálogo que abre e a linha que aparece na grade depois. */
registry.category("web_tour.tours").add("fair_apply_template_tour", {
    // direto na ação: passear pela gaveta de aplicativos é frágil sob o
    // web_responsive.
    url: "/odoo/action-liber_fairs.action_event_fair",
    steps: () => [
        {
            trigger: ".o_list_view",
            content: "A lista de feiras abre para o perfil",
        },
        {
            // PELO NOME, não pela primeira linha: num banco com feiras de
            // verdade (ou com a encenação de demonstração) a primeira linha
            // é outra feira, e o tour aplica o modelo no lugar errado.
            trigger: ".o_data_row .o_data_cell:contains('Feira do Modelo')",
            content: "Abrir a feira do tour",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "O formulário da feira abriu",
        },
        {
            trigger: ".o_notebook a.nav-link:contains('Grade')",
            content: "Ir para a aba da grade",
            run: "click",
        },
        {
            // pelo RÓTULO, não pelo name: o name do botão de ação é o id
            // numérico da ação, que muda de banco para banco. A sintaxe
            // %(xmlid)d só é resolvida no XML da view, nunca aqui.
            trigger: "button:contains('Aplicar um modelo')",
            content: "O botão de aplicar modelo está na aba",
            run: "click",
        },
        {
            trigger: ".modal .o_form_view",
            content: "O diálogo de aplicar modelo abriu",
        },
        {
            trigger: ".modal div[name='template_id'] input",
            content: "Escolher o modelo",
            run: "edit Modelo do Tour",
        },
        {
            trigger: ".o-autocomplete--dropdown-item:contains('Modelo do Tour')",
            content: "Confirmar o modelo na lista",
            run: "click",
        },
        {
            trigger: ".modal button[name='action_apply']",
            content: "Aplicar",
            run: "click",
        },
        {
            trigger: ".o_field_x2many_list .o_data_row:contains('Livro do Tour')",
            content: "O título do modelo entrou na grade",
        },
    ],
});
