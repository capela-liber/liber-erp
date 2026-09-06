/** @odoo-module **/

/**
 * O cartão "Faturas sem pedido" e a lista que ele abre, no perfil de quem clica.
 *
 * O número do cartão é desenhado em canvas: não há texto no DOM para ler. O
 * que a tela mostra de verdade, e é o que se afirma aqui: o canvas do cartão
 * carrega `title="Faturas sem pedido"` e `role="button"` -- o `role` só
 * existe quando há um menu ligado ao cartão (é a prova de que o clique
 * existe); o clique leva à lista "Sales notes without order"; e o rodapé da
 * coluna "Net Value" soma o mesmo número que o cartão soma (o teste calcula
 * esse número no motor, com o recorte do próprio painel, e o passa por aqui
 * na URL... não: ele é fixo -- 150.00 -- porque o teste semeia três notas
 * conhecidas e é ele quem afirma que 150 é o que o cartão soma).
 *
 * A sessão roda em inglês: o nome do painel na fonte é "Sales".
 */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("liber_sales_dashboard_tour", {
    url: "/odoo/action-spreadsheet_dashboard.ir_actions_dashboard_action",
    steps: () => [
        {
            content: "o painel de Vendas está na lista -- o do core, reescrito",
            trigger: ".o_spreadsheet_dashboard_search_panel .o_dashboard_name:contains('Sales'):not(:contains('vs'))",
            run: "click",
        },
        {
            content: "a planilha montou",
            trigger: ".o_spreadsheet_dashboard_action .o-spreadsheet",
        },
        {
            content: "o cartão Faturas sem pedido está desenhado E é clicável (role=button)",
            trigger: ".o_spreadsheet_dashboard_action canvas.o-scorecard[title='Faturas sem pedido'][role='button']",
            run: "click",
        },
        {
            content: "o clique abriu a lista de Notas sem pedido",
            trigger: ".o_breadcrumb:contains('Sales notes without order')",
        },
        {
            // A ação abre agrupada por mês: a linha do grupo já traz as somas
            // (DANFE 165, líquido 150). Abre-se o grupo para ver as notas.
            content: "a lista abre agrupada por mês; abre o grupo",
            trigger: ".o_list_view .o_group_header:contains('(2)')",
            run: "click",
        },
        {
            content: "a lista traz a nota solta e a sem fatura",
            trigger: ".o_list_view .o_data_row:contains('Livraria Solta')",
        },
        {
            trigger: ".o_list_view .o_data_row:contains('Livraria Sem Fatura')",
        },
        {
            content: "e NÃO traz a nota cuja fatura está ligada ao pedido",
            trigger: ".o_list_view:not(:has(.o_data_row:contains('Livraria Ligada')))",
        },
        {
            // O período do painel viajou no clique: a nota de dois anos atrás
            // não está na lista, nem no rodapé (150, não 1.149).
            content: "nem a nota de dois anos atrás: o período do painel veio junto",
            trigger: ".o_list_view:not(:has(.o_group_header:contains('Livraria Velha'))):not(:has(.o_data_row:contains('Livraria Velha')))",
        },
        {
            // O rodapé soma o LÍQUIDO (90 + 60 = 150) na coluna Net Value; a
            // DANFE (105 + 60 = 165) fica na coluna ao lado, para quem quiser
            // o frete -- era a diferença de 33.340,82 contra 34.037,95 em
            // agosto/2026, quando a lista só tinha a DANFE.
            content: "o rodapé da lista soma o mesmo que o cartão: 150,00",
            trigger: ".o_list_view tfoot td:contains('150.00')",
        },
    ],
});
