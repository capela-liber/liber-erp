/** @odoo-module **/

/**
 * O caminho de tela do painel Produtos, no perfil de quem vai usá-lo.
 *
 * O hoot ao lado prova o corte; o teste de ORM prova que o painel sai da
 * leitura com o `limit`. Nenhum dos dois prova que a tela abre com o remendo
 * dentro do pacote de verdade. O gráfico é desenhado em `canvas`, sem texto
 * no DOM para contar barras -- então o que se afirma aqui é o que o DOM
 * mostra: o painel na lateral, a planilha montada e as figuras desenhadas.
 *
 * O item se procura por "Product", que é o nome do painel na fonte: a sessão
 * do tour roda em inglês, como os tours do `liber_roles`.
 */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("painel_produtos_tour", {
    url: "/odoo/action-spreadsheet_dashboard.ir_actions_dashboard_action",
    steps: () => [
        {
            content: "o painel Produtos está na lista, em Vendas",
            trigger: ".o_spreadsheet_dashboard_search_panel .o_dashboard_name:contains(Product)",
            run: "click",
        },
        {
            content: "a planilha do painel montou",
            trigger: ".o_spreadsheet_dashboard_action .o-spreadsheet",
        },
        {
            content: "os cartões e os gráficos foram desenhados",
            trigger: ".o_spreadsheet_dashboard_action .o-figure-canvas",
        },
    ],
});
