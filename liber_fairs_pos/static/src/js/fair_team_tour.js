/** @odoo-module **/
import { registry } from "@web/core/registry";

/* OS DOIS PERFIS DE QUEM ESTÁ NA PRAÇA, cada um na tela dele.
 *
 * O que se prova aqui não é o que o ORM já sabe -- que grupo tem que direito
 * --, e sim o que só a tela responde: qual menu aparece dentro do aplicativo,
 * qual botão de cabeçalho existe, qual aba do formulário foi desenhada. Foi um
 * tour que pegou o Access Error do Editorial nas compras, e é a mesma ideia:
 * o ORM mede o que o teste pediu, a tela mede o que a tela pede.
 *
 * Os rótulos estão em PORTUGUÊS porque os usuários do tour nascem em pt_BR --
 * é assim que a tela chega para quem trabalha o evento. */

registry.category("web_tour.tours").add("fair_operator_tour", {
    url: "/odoo",
    steps: () => [
        {
            trigger: ".o_app[data-menu-xmlid='liber_fairs.menu_fairs_root']",
            content: "A operadora tem o aplicativo Eventos: é por ele que ela chega à carga",
            run: "click",
        },
        {
            // O QUE ELA NÃO VÊ, e é metade do desenho: nem as perdas, nem os
            // modelos de grade, nem a lista de eventos da casa. Ela recebe a
            // carga e vende; o resto não é dela.
            trigger: ".o_menu_sections:not(:has(a:contains('Perdas')))",
            content: "Perdas não é assunto de quem opera o balcão",
        },
        {
            trigger: ".o_menu_sections:not(:has(a:contains('Modelos de grade')))",
            content: "Nem os modelos, que são do planejamento",
        },
        {
            trigger: ".o_menu_sections a:contains('Recebimentos')",
            content: "O que ela tem é a chegada da carga",
            run: "click",
        },
        {
            trigger: ".o_list_view .o_data_row",
            content: "A carga da feira dela está esperando conferência",
        },
        {
            trigger: "thead .o_list_record_selector input",
            content: "Marcar o que chegou",
            run: "click",
        },
        {
            trigger: "button[name='action_fair_check']",
            content: "Sozinha na praça, ela confere e pronto",
            run: "click",
        },
        {
            trigger: ".o_list_view:not(:has(.o_data_cell:contains('Feira dos Dois Perfis')))",
            content: "A carga saiu da fila de conferência",
        },
    ],
});

registry.category("web_tour.tours").add("fair_lead_tour", {
    url: "/odoo",
    steps: () => [
        {
            trigger: ".o_app[data-menu-xmlid='liber_fairs.menu_fairs_root']",
            content: "O gerente de campo entra pelo mesmo aplicativo",
            run: "click",
        },
        {
            trigger: ".o_menu_sections a:contains('Perdas')",
            content: "Ele vê as perdas: é ele que sabe o que sumiu da mesa",
        },
        {
            // O planejamento não é dele. O evento foi montado antes de ele
            // existir para o sistema, e a grade se lê, não se refaz.
            trigger: ".o_menu_sections:not(:has(a:contains('Modelos de grade')))",
            content: "Os modelos de grade continuam sendo de quem planeja",
        },
        {
            trigger: ".o_menu_sections a:contains('Eventos')",
            content: "Abrir o evento dele",
            run: "click",
        },
        {
            trigger: ".o_data_row .o_data_cell:contains('Feira dos Dois Perfis')",
            content: "O evento em que ele está escalado",
            run: "click",
        },
        {
            trigger: ".o_form_view_container",
            content: "A ficha do evento abriu",
        },
        {
            trigger: ".o_form_view:not(:has(button[name='action_plan']))",
            content: "Planejar não é com ele",
        },
        {
            trigger: ".o_form_view:not(:has(button[name='action_ship']))",
            content: "Nem despachar: a remessa sai do depósito",
        },
        {
            // A aba inteira some. Decidir quanto cada um ganha -- inclusive
            // ele -- é de quem monta o evento; gerente circunstancial não é
            // juiz em causa própria.
            trigger: ".o_notebook:not(:has(.nav-link:contains('Comissões')))",
            content: "A aba de comissões não existe para ele",
        },
        {
            trigger: "button[name='action_return']",
            content: "O que ele faz é mandar a mercadoria de volta quando acaba",
        },
        {
            trigger: ".o_menu_sections a:contains('Fechamentos diários')",
            content: "E fechar o dia, que é trabalho de praça",
            run: "click",
        },
        {
            trigger: ".o_list_view",
            content: "Os fechamentos do evento dele",
        },
    ],
});
