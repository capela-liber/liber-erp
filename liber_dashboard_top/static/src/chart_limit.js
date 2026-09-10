import { patch } from "@web/core/utils/patch";
import { ChartDataSource } from "@spreadsheet/chart/data_source/chart_data_source";

/**
 * O gráfico Odoo ganha um `limit` no `metaData`: os N primeiros grupos do eixo.
 *
 * O `GraphModel` do web, que carrega os dados do gráfico, ordena os pontos
 * quando a definição pede (`order: "DESC"`) mas não sabe cortar. O corte entra
 * aqui, e entra nos PONTOS -- antes de virarem séries -- por dois motivos:
 * tudo o que sai dali (rótulos, cada série de um gráfico empilhado, o domínio
 * que o clique usa) nasce coerente; e `updateMetaData` reprocessa os mesmos
 * pontos sem recarregar, então um corte feito nas séries prontas se desfaria
 * na primeira troca de tipo de gráfico.
 */

/** O limite pedido na definição, ou `undefined` se não há um que preste. */
export function limiteDe(metaData) {
    const n = metaData?.limit;
    return Number.isInteger(n) && n > 0 ? n : undefined;
}

/**
 * Os pontos dos `n` primeiros grupos do eixo, na ordem em que vieram.
 *
 * "Grupo" é o valor do primeiro agrupamento (`labels[0]`): é ele o eixo do
 * gráfico, e num gráfico empilhado o mesmo grupo aparece em vários pontos, um
 * por série. Todos os pontos de um grupo que fica, ficam.
 */
export function primeirosGrupos(pontos, n) {
    const posicao = new Map();
    const dentro = [];
    for (const ponto of pontos) {
        const grupo = ponto.labels?.[0];
        if (!posicao.has(grupo)) {
            posicao.set(grupo, posicao.size);
        }
        if (posicao.get(grupo) < n) {
            dentro.push(ponto);
        }
    }
    return dentro;
}

/** Ensina o modelo carregado a cortar, e refaz as séries com o corte. */
export function instalarLimite(model, n) {
    const original = model._getProcessedDataPoints.bind(model);
    model._getProcessedDataPoints = () => primeirosGrupos(original(), n);
    model._prepareData();
}

patch(ChartDataSource.prototype, {
    async _load() {
        await super._load();
        const n = limiteDe(this._metaData);
        if (n && this._model) {
            instalarLimite(this._model, n);
        }
    },
});
