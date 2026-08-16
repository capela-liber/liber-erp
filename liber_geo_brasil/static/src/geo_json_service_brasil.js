import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { geoJsonService } from "@spreadsheet/helpers/geo_json_service";

/**
 * A região "Brasil (UF)" nos gráficos geo.
 *
 * O serviço do core sabe fazer três coisas: listar regiões, buscar o desenho de
 * uma delas e reduzir a etiqueta do dado ao `id` do desenho. Aqui as três
 * ganham um caso a mais e delegam todo o resto -- inclusive o mundo, que
 * continua sendo a região padrão de quem não escolheu nenhuma.
 */

export const REGIAO_BR = "br_uf";
export const MAPA_BR = "/liber_geo_brasil/static/geojson/brasil_uf.geo.json";

const MARCAS_DIACRITICAS = /[\u0300-\u036f]/g;

/** Minúsculas e sem acento: "São Paulo" e "sao paulo" são a mesma UF. */
export function normalizar(nome) {
    return nome.normalize("NFD").replace(MARCAS_DIACRITICAS, "").toLowerCase();
}

/**
 * O índice que leva do que a tela mostra para o que o mapa conhece.
 *
 * Entra o que o `res.country.state` tem (nome e sigla), sai um dicionário que
 * responde pelos dois: o dado pode vir agrupado por nome ("São Paulo") ou já
 * pela sigla, e nos dois casos o desenho é o mesmo.
 *
 * @param {Array<{name: string, code: string}>} estados
 */
export function indexarUfs(estados) {
    const indice = {};
    for (const estado of estados) {
        indice[normalizar(estado.name)] = estado.code;
        indice[normalizar(estado.code)] = estado.code;
    }
    return indice;
}

// O Odoo mostra estado com o país pendurado: "São Paulo (BR)". O parêntese é do
// rótulo, não do nome, e sai antes da busca.
const SUFIXO_PAIS = /(.*?)(\(.*\))?$/;

/**
 * A sigla da UF a partir da etiqueta do gráfico, ou `undefined` se não for uma.
 *
 * @param {string} etiqueta como vem do agrupamento -- "São Paulo (BR)"
 * @param {Object<string,string>} indice o que `indexarUfs` devolveu
 */
export function siglaDaEtiqueta(etiqueta, indice) {
    if (!etiqueta || !indice) {
        return undefined;
    }
    const casou = String(etiqueta).match(SUFIXO_PAIS);
    const nome = casou ? casou[1].trim() : String(etiqueta).trim();
    return indice[normalizar(nome)];
}

patch(geoJsonService, {
    start(env, dependencias) {
        const servico = super.start(env, dependencias);
        const { orm } = dependencias;

        let ufs;
        let ufsPendentes;
        let mapa;
        let mapaPendente;

        function carregarUfs() {
            if (ufs) {
                return Promise.resolve(ufs);
            }
            if (!ufsPendentes) {
                ufsPendentes = orm
                    .searchRead("res.country.state", [["country_id.code", "=", "BR"]],
                                ["name", "code"])
                    .then((estados) => {
                        ufs = indexarUfs(estados);
                        ufsPendentes = undefined;
                        return ufs;
                    })
                    .catch((erro) => {
                        // Sem o índice o mapa desenha cinza, que é melhor do que
                        // derrubar o dashboard inteiro por causa de um card.
                        console.error(erro);
                        ufs = {};
                        ufsPendentes = undefined;
                        return ufs;
                    });
            }
            return ufsPendentes;
        }

        function carregarMapa() {
            if (mapa) {
                return Promise.resolve(mapa);
            }
            if (!mapaPendente) {
                mapaPendente = fetch(MAPA_BR)
                    .then((resposta) => resposta.json())
                    .then((json) => {
                        mapa = json;
                        mapaPendente = undefined;
                        return mapa;
                    })
                    .catch((erro) => {
                        console.error(erro);
                        mapa = { type: "FeatureCollection", features: [] };
                        mapaPendente = undefined;
                        return mapa;
                    });
            }
            return mapaPendente;
        }

        return {
            ...servico,
            getAvailableRegions: () => [
                ...servico.getAvailableRegions(),
                { id: REGIAO_BR, label: _t("Brazil (states)"), defaultProjection: "mercator" },
            ],
            getTopoJson: async (regiao) => {
                if (regiao !== REGIAO_BR) {
                    return servico.getTopoJson(regiao);
                }
                // O índice tem de estar pronto quando o desenho chegar: quem
                // pergunta a sigla, logo depois, pergunta de forma síncrona.
                const [json] = await Promise.all([carregarMapa(), carregarUfs()]);
                return json;
            },
            geoFeatureNameToId: (regiao, nome) => {
                if (regiao !== REGIAO_BR) {
                    return servico.geoFeatureNameToId(regiao, nome);
                }
                return siglaDaEtiqueta(nome, ufs);
            },
        };
    },
});
