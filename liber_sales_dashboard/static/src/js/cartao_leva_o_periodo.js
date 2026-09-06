/** @odoo-module **/

/**
 * O clique no cartão leva o período do painel para a lista.
 *
 * O core abre o menu ligado ao cartão "seco": a lista chega inteira, de 2019
 * em diante, e quem clicou tem de reconstituir o filtro à mão (o dono, em
 * 06/09/2026: "se eu clico no ícone em algo filtrado eu tenho que
 * reconstituir o filtro dentro da tabela"). As barras dos gráficos já fazem
 * o certo -- o clique numa barra abre a lista com o domínio daquela barra,
 * filtro incluso. Aqui o cartão passa a fazer o mesmo.
 *
 * Como: o cartão lê uma célula ("Dados!C5"); a célula é uma fórmula que, em
 * até quatro saltos, chega a um PIVOT.VALUE(3, ...). Esse pivô conhece o seu
 * domínio JÁ COM os filtros globais aplicados (`getPivotComputedDomain`). Se
 * o menu do cartão abre uma ação do mesmo modelo do pivô, a ação é aberta
 * com esse domínio; se não (Pedidos abertos aponta para a fila de pedidos,
 * e o pivô é o sale.report), vale o comportamento do core.
 */
import { patch } from "@web/core/utils/patch";
import * as spreadsheet from "@odoo/o-spreadsheet";
import { navigateTo } from "@spreadsheet/actions/helpers";

const { toCartesian } = spreadsheet.helpers;

/** O id do pivô que alimenta a célula `ref` ("Dados!C5"), seguindo as fórmulas. */
function pivoDaCelula(getters, ref, sheetIdPadrao) {
    for (let salto = 0; salto < 4 && ref; salto++) {
        const partes = ref.split("!");
        const xc = partes.pop();
        const nome = partes.join("!").replace(/^'|'$/g, "");
        const sheetId = nome ? getters.getSheetIdByName(nome) : sheetIdPadrao;
        if (!sheetId) {
            return undefined;
        }
        const { col, row } = toCartesian(xc);
        const conteudo = getters.getCell({ sheetId, col, row })?.content || "";
        const pivo = conteudo.match(/PIVOT\.VALUE\(\s*"?(\d+)"?/i);
        if (pivo) {
            return pivo[1];
        }
        // A primeira referência de célula da fórmula (B5 em =FORMAT.LARGE.NUMBER(B5)).
        const dep = conteudo.match(/(?:'[^']+'!|[A-Za-z0-9_]+!)?\$?[A-Z]{1,3}\$?\d+/);
        if (!dep) {
            return undefined;
        }
        ref = dep[0].includes("!") ? dep[0] : `${nome || ""}!${dep[0]}`;
        if (ref.startsWith("!")) {
            ref = ref.slice(1);
        }
    }
    return undefined;
}

patch(spreadsheet.components.ScorecardChart.prototype, {
    async navigateToOdooMenu(newWindow) {
        const getters = this.env.model.getters;
        const menu = getters.getChartOdooMenu(this.props.chartId);
        const env = getters.getOdooEnv?.();
        if (menu?.actionID && env) {
            const definicao = getters.getChartDefinition(this.props.chartId);
            const sheetId = getters.getFigureSheetId?.(this.props.figureId) || getters.getActiveSheetId();
            const pivotId = definicao.keyValue && pivoDaCelula(getters, definicao.keyValue, sheetId);
            if (pivotId) {
                const modelo = getters.getPivotCoreDefinition(pivotId).model;
                let acao;
                try {
                    acao = await env.services.action.loadAction(menu.actionID);
                } catch {
                    acao = undefined;
                }
                if (acao && acao.res_model === modelo) {
                    await navigateTo(
                        env,
                        menu.actionID,
                        {
                            name: acao.name || menu.name,
                            type: "ir.actions.act_window",
                            res_model: modelo,
                            views: acao.views,
                            domain: getters.getPivotComputedDomain(pivotId),
                            context: acao.context,
                        },
                        { newWindow }
                    );
                    return;
                }
            }
        }
        return super.navigateToOdooMenu(newWindow);
    },
});
