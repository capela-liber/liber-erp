import { describe, expect, test } from "@odoo/hoot";
import { geoJsonService } from "@spreadsheet/helpers/geo_json_service";
import {
    REGIAO_BR,
    indexarUfs,
    siglaDaEtiqueta,
} from "@liber_geo_brasil/geo_json_service_brasil";

describe.current.tags("headless");

// O que o `res.country.state` devolve para o Brasil, no essencial.
const ESTADOS = [
    { name: "São Paulo", code: "SP" },
    { name: "Rio de Janeiro", code: "RJ" },
    { name: "Ceará", code: "CE" },
];

test("a etiqueta do gráfico vira sigla, com o país pendurado ou sem", () => {
    const indice = indexarUfs(ESTADOS);
    expect(siglaDaEtiqueta("São Paulo (BR)", indice)).toBe("SP");
    expect(siglaDaEtiqueta("São Paulo", indice)).toBe("SP");
    expect(siglaDaEtiqueta("SP", indice)).toBe("SP");
});

test("acento e caixa não separam a UF do seu desenho", () => {
    const indice = indexarUfs(ESTADOS);
    // O agrupamento nem sempre devolve o nome como está cadastrado.
    expect(siglaDaEtiqueta("ceara", indice)).toBe("CE");
    expect(siglaDaEtiqueta("CEARÁ (BR)", indice)).toBe("CE");
});

test("o que não é UF não vira nada", () => {
    const indice = indexarUfs(ESTADOS);
    // O runtime pula a etiqueta sem sigla; devolver qualquer coisa pintaria
    // o estado errado no mapa.
    expect(siglaDaEtiqueta("Buenos Aires (AR)", indice)).toBe(undefined);
    expect(siglaDaEtiqueta("", indice)).toBe(undefined);
    expect(siglaDaEtiqueta("São Paulo", undefined)).toBe(undefined);
});

test("o Brasil entra na lista de regiões, e o mundo continua sendo o padrão", () => {
    const servico = geoJsonService.start({}, { orm: {} });
    const regioes = servico.getAvailableRegions();
    // A primeira da lista é a região que o gráfico sem escolha usa.
    expect(regioes[0].id).toBe("world");
    expect(regioes.map((r) => r.id)).toInclude(REGIAO_BR);
    expect(regioes.find((r) => r.id === REGIAO_BR).defaultProjection).toBe("mercator");
});

test("região que não é a nossa continua sendo do core", () => {
    const servico = geoJsonService.start({}, { orm: {} });
    // Sem o mapeamento carregado o core devolve undefined -- o que importa
    // aqui é que ele foi chamado e nada estourou.
    expect(servico.geoFeatureNameToId("world", "Brazil")).toBe(undefined);
});
