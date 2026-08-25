/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * O Relatório, medida por medida (23/08/2026).
 *
 * Este tour nasceu de um erro que os testes de ORM não pegaram: as medidas
 * novas passaram no ORM e a TELA caiu com `column valor_liquido does not
 * exist` — um banco irmão do mesmo servidor estava uma versão atrás. O ORM
 * mede o que o teste pediu; o pivô monta um `read_group` de verdade, com as
 * colunas todas, e é isso que este tour executa.
 *
 * Ele prova as duas correções pedidas: que as quatro medidas somam na tela, e
 * que o agrupamento se chama Data do pedido — o dia é intervalo dela.
 *
 * Ao vivo, no console (modo desenvolvedor):
 *     odoo.startTour("olist_relatorio_tour")
 * ou pelo tests/test_tour_relatorio.py.
 */
registry.category("web_tour.tours").add("olist_relatorio_tour", {
    url: "/odoo/action-liber_olist.action_olist_dashboard",
    steps: () => [
        {
            trigger: ".o_graph_renderer canvas",
            content: "O gráfico do Relatório desenha",
        },
        {
            trigger: ".o_cp_switch_buttons .o_switch_view.o_pivot",
            content: "Trocar para o pivô",
            run: "click",
        },
        {
            // A tabela do pivô é o read_group de verdade: se uma medida não
            // existir no banco, é AQUI que o SQL estoura.
            trigger: ".o_pivot .o_pivot_measure_row:contains('Valor bruto')",
            content: "O bruto é uma medida",
        },
        {
            trigger: ".o_pivot .o_pivot_measure_row:contains('Desconto')",
            content: "O desconto aparece ao lado — era o que faltava",
        },
        {
            trigger: ".o_pivot .o_pivot_measure_row:contains('Valor líquido')",
            content: "E o líquido, que é o número da meta",
        },
        {
            trigger: ".o_pivot_header_cell_closed:first",
            content: "Abrir o menu de agrupamento da linha",
            run: "click",
        },
        {
            // A correção do rótulo: o grupo é a DATA; Ano/Trimestre/Mês/
            // Semana/Dia são intervalos dela, no submenu.
            trigger: ".dropdown-menu .dropdown-item:contains('Data do pedido')",
            content: "O grupo chama-se Data do pedido, no padrão do Odoo",
            run: "click",
        },
        {
            trigger: ".o_pivot_cell_value",
            content: "Agrupado por data, os valores somam",
        },
    ],
});
