/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * A nota do Olist chega com o livro certo e o desconto certo (05/09/2026).
 *
 * O teste de ORM prova `_linhas_de_fatura` e o `_create_invoice`. Este prova o
 * que o comercial vê depois de clicar em Despachar: abre a venda, abre a
 * fatura e lê o nome do livro na linha.
 *
 * Vale um clique porque os dois defeitos eram INVISÍVEIS no lugar onde
 * nasciam e só apareciam aqui. O produto-lixo ("CFOP5102", batizado com o
 * nome do primeiro livro que passou) entrava calado: a fatura era postada,
 * autorizada, paga — e dizia outro título. Quem descobriria seria o cliente,
 * lendo a DANFE. O desconto descartado, do mesmo jeito: número maior na nota
 * do que na venda, e ninguém olha os dois lados na mesma tela.
 *
 * O passo que importa é o último. Se a correção do produto sair, a linha da
 * fatura volta a dizer "Os cantos do homem-sombra" e o tour cai ali.
 *
 * Ao vivo, no console (modo desenvolvedor):
 *     odoo.startTour("olist_nota_do_olist_tour")
 */
registry.category("web_tour.tours").add("olist_nota_do_olist_tour", {
    url: "/odoo/action-liber_olist.action_olist_fila",
    steps: () => [
        {
            trigger: ".o_data_row td:contains('TOUR-NF1')",
            content: "O pedido do Olist está na fila, com a nota já arquivada",
        },
        {
            trigger: ".o_data_row:first .o_list_record_selector input",
            content: "Marcar o pedido",
            run: "click",
        },
        {
            trigger: "button[name='action_import_selected']",
            content: "Despachar: é aqui que a venda e a fatura nascem",
            run: "click",
        },
        {
            trigger: ".o_form_view_container [name='partner_id']",
            content: "A venda abriu",
        },
        {
            // O smart button das faturas só existe porque `sale_line_ids` foi
            // preenchido. Sem o elo, o pedido fica em "A faturar" e este
            // botão não aparece -- o passo cai aqui, e é o defeito dos 85
            // pedidos do prod.
            trigger: "button[name='action_view_invoice']",
            content: "A fatura está amarrada ao pedido",
            run: "click",
        },
        {
            // O PASSO QUE IMPORTA: o nome na linha da fatura.
            trigger: ".o_form_view:contains('Bom crioulo do Tour')",
            content: "A fatura saiu com o livro certo, não com o produto-lixo",
        },
    ],
});
