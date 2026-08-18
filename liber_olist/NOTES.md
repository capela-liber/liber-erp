# liber_olist — notas de arquitetura

> Versão enxuta do diário de desenvolvimento (2026-07 a 2026-08). Ficam aqui as
> decisões de desenho e as lições da API que qualquer instalação vai reencontrar.

## 1. O princípio que governa tudo

**O Odoo é o livro-razão canônico. O Olist é um adaptador plugável.**

O módulo nasceu de uma experiência ruim: quando a emissão fiscal vive numa caixa-preta
de terceiro, quem controla a caixa controla a editora. A regra que evita repetir isso:

- O Olist **não** é "o sistema fiscal" — é *uma* fonte de documento fiscal (o XML),
  exatamente como o upload manual do `liber_nfe_xml`. Desinstalar este módulo remove a
  integração e deixa o razão intacto.
- Consignação e financeiro dependem de uma interface de documento fiscal +
  `account.move`, **nunca** da API do Olist diretamente. Se o fornecedor mudar,
  troca-se o adaptador sem tocar no resto.
- O valor do Odoo não é emitir XML (commodity) — é **reconciliar**: casar pedido ↔
  nota ↔ pagamento. É o motor de conciliação que legitima o Odoo como sistema de registro.

## 2. Fronteira de donos por canal

O Olist/Tiny também é um ERP. Sem dono definido por canal, os dois cérebros brigam
por estoque e pedido (split-brain):

| Canal | Dono do pedido | Papel do Odoo |
|---|---|---|
| Consignação e venda direta | **Odoo** | Master |
| Marketplace (Mercado Livre, Shopify, Woo — via Olist) | **Olist** | Ingere para consolidar: pedido, canal, nota, fatura |

Corolário decidido depois de um desvio: **o emissor segue o dono do pedido**. O pedido
de marketplace nasce no Olist e a nota sai de lá; o pedido que nasce no Odoo não tem por
que ir para lá. O push de `sale.order` → Olist existiu como piloto e **foi removido** —
há um teste guardando a decisão, para que ela só volte à mesa de propósito.

## 3. As duas APIs, e por que a conta nasce em somente leitura

- **v2** (token único, extensão "Token API"): congelada — *"continuará funcional, sem
  data estimada para descontinuação, mas não receberá mais atualizações"*. É a que o
  módulo usa: sobe sem OAuth e cobre todas as superfícies necessárias.
- **v3** (OAuth2): recebe evolução, mas tem dois gates (plano Construa+ **e** a extensão
  "Gestão de Aplicativos"), refresh token de **1 dia** (exige cron de refresh) e não
  cria nota avulsa.
- **Não existe conector Odoo↔Olist pronto** (Apps Store, OCA, terceiros) — daí este módulo.
- **Não há sandbox.** O ambiente (produção/homologação) é configuração **global da
  conta**, não parâmetro da chamada: testar emissão derrubaria a emissão real. Por isso
  a conta Olist nasce com `read_only=True`, e a trava mora no caminho por onde **toda**
  escrita passa: uma base de teste pode rodar com o token de verdade, ler tudo, e não
  consegue escrever nem por engano.

## 4. Superfícies usadas (v2)

| Superfície | Endpoint | Direção |
|---|---|---|
| XML da nota | `nota.fiscal.obter.xml.php` | Olist → Odoo |
| Listagem de notas (situação) | `notas.fiscais.pesquisa.php` | Olist → Odoo |
| Pedido + canal | `pedidos.pesquisa.php` (lista) / `pedido.obter.php` (detalhe) | Olist → Odoo |
| Catálogo e ficha do produto | `produtos.pesquisa.php` / `produto.obter.php` | Olist → Odoo |
| Saldos alterados (janela) | `lista.atualizacoes.estoque.php` | Olist → Odoo |
| Estoque (balanço) | `produto.atualizar.estoque.php` | Odoo → Olist |
| Ficha do produto (escrita) | `produto.alterar.php` | Odoo → Olist |

A listagem de pedidos custa 1 chamada por 100 pedidos, mas **não traz o canal** — o
`ecommerce.nomeEcommerce` só existe no detalhe, 1 chamada por pedido. Por isso o fluxo
é: listagem enche o espelho, detalhe vem por seleção ou aos poucos pelo cron, com teto
por rodada e cobertura à vista ("47 de 978 lidos" — enquanto não termina, "vendeu 0"
quer dizer "ainda não lemos", não "não vende").

## 5. Lições da API que custaram caro

1. **O XML vem embrulhado** em `<retorno><xml_nfe>…</xml_nfe></retorno>`. Desembrulhar
   **recortando bytes** — reparsear com ElementTree reescreve namespaces e **invalida a
   assinatura digital** da NF-e.
2. **Rate limit se disfarça de resposta vazia.** Sob estrangulamento a v2 responde HTTP
   200 com erro no envelope — indistinguível de "não existe" para quem só olha o código
   HTTP. Tratar como falha **temporária** (recuo progressivo), nunca como dado ausente.
   Empírico: 1,1 s entre chamadas não basta; 2,2 s (30 req/min) aguenta. O teto real da
   conta não é determinável por documentação — as tabelas usam nomes de plano legados.
3. **Cancelamento não está no XML** — é evento à parte. Uma nota autorizada e depois
   cancelada entraria como venda boa e o razão superestimaria o faturamento. O sync lê a
   `situacao` da listagem e registra o evento de cancelamento por chave de acesso.
4. **`formato=json` governa a entrada também.** A doc mostra os parâmetros como XML, mas
   com `formato=json` o endpoint exige o parâmetro em JSON, com duplo embrulho:
   `estoque=json.dumps({"estoque": {...}})`. O erro é `codigo_erro 3 — JSON mal formado`.
5. **"A consulta não retornou registros" chega como `status: Erro`** — e significa zero
   resultados, não falha. Tratar como erro faria o cron gritar em dia sem venda.
6. **Fuso horário:** `date_order` é UTC; depois das 21h no Brasil a data já é a de
   amanhã, e pedido com data futura **some dos filtros** do Olist. Converter com fuso
   fixo `America/Sao_Paulo` — `context_timestamp` usa o fuso do usuário, que é vazio num
   cron e cai de volta em UTC.
7. **O ISBN do item de pedido vem com hífen** (`978-85-...`); o catálogo e o `barcode`
   vêm sem. Casar sempre pela grafia normalizada.
8. **`produto.alterar` pode ser substituição, não merge** (a doc não diz). Então: ler a
   ficha inteira, trocar o campo, devolver tudo — funciona nas duas hipóteses. E número
   volta como número, não como string.
9. **Numa escrita, ler errado a resposta é pior do que numa leitura.** O id remoto de
   uma escrita já feita é gravado imediatamente — o Odoo nunca pode esquecer o que o
   Olist já registrou; um retry duplicaria.

## 6. Decisões de desenho

**Uma conta por empresa.** A empresa da nota é derivada do CNPJ do `<emit>`/`<dest>` do
próprio XML e comparada com a da conta: um token apontado para a empresa errada não
consegue arquivar documento nela. Uma conta ativa por empresa (constraint) — com duas, a
escolhida dependeria da ordem dos registros.

**O espelho é leitura datada, não segunda verdade.** `olist.product` e `olist.order`
guardam o que o Olist disse e quando; a ficha crua fica em JSON íntegro. Editar o
espelho muda só o espelho — o Olist só sabe quando alguém usa "Enviar alterações", com o
de/para pendente à vista. Uma tabela só liga campo daqui à chave de lá, servindo ao diff
e ao envio — duas listas produziriam a pior mentira de uma tela de sincronia.

**O de-para de produto mora no espelho.** A chave preferida é o ISBN (`codigo` =
`barcode`), mas catálogo real tem reedição com ISBN novo de um lado e cadastro velho do
outro. Ordem de resolução, única para todas as superfícies: id interno do Olist →
casamento no espelho → ISBN. Casamento à mão **não é desfeito** pela releitura;
sugestão por título é sugestão, nunca casamento automático. Dois itens do Olist
apontando o mesmo produto ficam marcados e o envio recusa. E o espelho **não inventa
produto**: ISBN que não casa é notícia, não motivo para duplicar o catálogo da editora.

**Canais: a descoberta é do módulo, o mapeamento é da casa.** O nome que vem do Olist
(`nomeEcommerce`) entra em `olist.channel` na primeira vez que aparece; o `crm.team`
correspondente nasce **vazio** e é escolhido em Configurações. `_resolve_team` nunca
cria `crm.team` — uma leitura de API não decide a taxonomia comercial da casa. Mapear
depois alcança o que já foi lido.

**Estoque: sobe a prateleira, não o "Em mãos".** `qty_available` soma toda localização
interna — inclusive o que já está em caixa fechada para outro cliente. O que se oferece
num marketplace é o estoque da área de armazém. E sobe **por empresa**: `with_company()`
não restringe (ele **soma** — `env.companies | company`), então a leitura fixa
`allowed_company_ids`; `olist_produto_id` e o log de push são `company_dependent`.
Armadilha do core: no `product.template` a chave de cache de `qty_available` ignora
`location` — o cálculo é feito nas **variantes**, onde a chave é completa. Margem de
segurança opcional por conta, com piso em zero; `tipo=B` substitui o saldo, não soma —
antes do primeiro push a pergunta não é "o código está certo?", é "o que muda em cada
livro?" (há tela de conferência com os três números lado a lado).

**Pedidos: importar é ato deliberado, e o XML é condição.** Item sem produto no Odoo
**bloqueia o pedido inteiro** — pedido com total errado é pior que pedido faltando. O
cliente casa por documento normalizado (`vat_digits`), nunca pela grafia crua; sem
documento, cai num contato genérico do canal (marketplace muitas vezes não entrega o
comprador). O corte de estoque (`order_stock_cutoff`) decide a partir de quando o pedido
baixa prateleira — vazio, nenhum mexe em estoque, porque importar mil pedidos antigos
não pode reescrever o estoque de hoje.

**A fatura nasce do XML.** O XML é o que a SEFAZ autorizou — a verdade fiscal. Montar a
fatura do pedido arriscaria o documento contábil dizer o que o fiscal não diz. Nascendo
do XML (os itens já parseados pelo `liber_nfe_xml`), os dois batem por construção. Ela
não emite nada: registra um fato consumado, e por isso nasce lançada.

**O recebimento vai num diário próprio do marketplace, nunca no banco.** O comprador já
pagou ao Olist, mas o dinheiro só chega no repasse, agregado e com taxas. Lançar no
banco diria que ele já está lá. O diário próprio deixa o valor identificável — e a
conciliação dele contra o repasse (a parte que ainda falta) é o que revela as taxas.

**Cada equipe alcança a nota onde já trabalha:** a logística na transferência, o
comercial no pedido (a linha de fatura ligada à linha do pedido, senão "Faturado: 0" com
nota emitida), o financeiro no título. Integrações vizinhas são detectadas pela
existência do campo, não por dependência dura.

## 7. Fora do escopo / futuro

- **Emissão pela API**: descartada — o emissor segue o dono do pedido (§2). A emissão
  da casa é assunto do `liber_nfe_focus`.
- **Conciliação do repasse** do marketplace (taxas): a fatura resolve o razão, não o caixa.
- E-book/ISS e NFC-e: fora — o escopo é livro físico, NF-e modelo 55.

O caminho de ingestão foi provado com o catálogo real: 705 XMLs importados, 100%
válidos, valor batendo em todos, zero na empresa errada, e segunda rodada idempotente
(0 importados, 705 pulados).

## 8. Fontes

[v2 vs v3, posição oficial](https://tiny.com.br/api-docs/api) ·
[Aplicativos API v3](https://ajuda.olist.com/hubs-e-plataformas-via-api/aplicativos-api-v3-configuracoes-e-utilizacao) ·
[OAuth2 v3](https://api-docs.erp.olist.com/documentacao/comecando/autenticacao) ·
[Obter XML da NF](https://tiny.com.br/api-docs/api2-notas-fiscais-obter-xml) ·
[Obter pedido](https://tiny.com.br/api-docs/api2-pedidos-obter) ·
[Atualizar estoque](https://tiny.com.br/api-docs/api2-produtos-atualizar-estoque) ·
[Limites da API](https://tiny.com.br/api-docs/api2-limites-api)
