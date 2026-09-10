import { animationFrame } from "@odoo/hoot-mock";
import { describe, expect, test } from "@odoo/hoot";

import { defineSpreadsheetModels } from "@spreadsheet/../tests/helpers/data";
import { createSpreadsheetWithChart } from "@spreadsheet/../tests/helpers/chart";
import { limiteDe, primeirosGrupos } from "@liber_dashboard_top/chart_limit";

describe.current.tags("headless");
defineSpreadsheetModels();

/**
 * Um gráfico de barras por produto, carregado. Os dados de mentira do
 * spreadsheet têm quatro parceiros em dois produtos: um com três, outro com
 * um. Ordenado DESC, o de três vem primeiro.
 */
async function barrasPorProduto(extra = {}) {
    const { model } = await createSpreadsheetWithChart({
        type: "odoo_bar",
        definition: {
            metaData: {
                groupBy: ["product_id"],
                measure: "__count",
                order: "DESC",
                resModel: "partner",
                ...extra,
            },
        },
    });
    const chartId = model.getters.getChartIds(model.getters.getActiveSheetId())[0];
    model.getters.getChartRuntime(chartId); // dispara o carregamento
    await animationFrame();
    const dados = model.getters.getChartRuntime(chartId).chartJsConfig.data;
    return { model, chartId, dados };
}

test("sem limite o gráfico continua inteiro", async () => {
    const { dados } = await barrasPorProduto();
    expect(dados.labels.length).toBe(2);
    expect(dados.datasets[0].data).toEqual([3, 1]);
});

test("com limite ficam os primeiros -- que, ordenado, são os maiores", async () => {
    const inteiro = await barrasPorProduto();
    const { dados } = await barrasPorProduto({ limit: 1 });
    expect(dados.labels).toEqual([inteiro.dados.labels[0]]);
    expect(dados.datasets[0].data).toEqual([3]);
});

test("o domínio do clique acompanha o corte", async () => {
    // Cada barra guarda o domínio que abre a lista ao clicar. Cortar rótulo
    // sem cortar domínio faria a primeira barra abrir a lista de outra.
    const { model, chartId } = await barrasPorProduto({ limit: 1 });
    const fonte = model.getters.getChartDataSource(chartId);
    expect(fonte.getData().datasets[0].domains.length).toBe(1);
    expect(fonte.getData().datasets[0].domains[0]).toEqual([["product_id", "=", 41]]);
});

test("limite maior que os grupos não inventa nada", async () => {
    const { dados } = await barrasPorProduto({ limit: 50 });
    expect(dados.labels.length).toBe(2);
});

test("limite que não presta é como não ter", () => {
    expect(limiteDe({ limit: 50 })).toBe(50);
    for (const torto of [0, -1, 2.5, "50", null, undefined]) {
        expect(limiteDe({ limit: torto })).toBe(undefined);
    }
    expect(limiteDe(undefined)).toBe(undefined);
});

test("o corte é por grupo do eixo, e leva todas as séries do grupo", () => {
    // Gráfico empilhado: dois agrupamentos, o primeiro é o eixo.
    const pontos = [
        { labels: ["A", "x"] },
        { labels: ["A", "y"] },
        { labels: ["B", "x"] },
        { labels: ["C", "x"] },
        { labels: ["B", "y"] },
    ];
    expect(primeirosGrupos(pontos, 2).map((p) => p.labels.join("/"))).toEqual([
        "A/x",
        "A/y",
        "B/x",
        "B/y",
    ]);
    expect(primeirosGrupos([], 2)).toEqual([]);
});
