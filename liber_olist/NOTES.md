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

## 19. A etiqueta: desenhar, não. Buscar, sim (2026-08-20)

Pergunta do usuário: dá para fazer a etiqueta dentro do Odoo? Duas respostas, e elas são
opostas.

### 19.1 Desenhar a etiqueta nós mesmos: não — e seria errado mesmo se desse

A etiqueta de exemplo (Olist Envios / Pax) tem duas metades. Uma é nossa: a **DANFE
simplificada**, com a chave de acesso — sabemos desenhar. A outra **não é**: o código de
volume (`EBBM5V3`), o código de rastreio (`P0XRM8KU9VPXWJ`), a zona de triagem (`SSP-050-A`),
o desenho do transportador. Esses são atribuídos pela **transportadora** quando o envio é
criado, e nenhum deles vem no payload do pedido da v2 (as sete chaves de envio do §12.6 não os
incluem).

Reproduzir esse código de barras seria **inventar roteirização**: o pacote é mal encaminhado
ou recusado no balcão. A etiqueta é um contrato com a transportadora, não um documento nosso.
Meia etiqueta não é etiqueta.

### 19.2 Buscar a etiqueta pronta: sim, e a chave já está no Odoo

A **API do Olist Envios** (`envios-api.olist.com`, outra API — não é a Tiny v2 que usamos) tem:

| endpoint | devolve |
|---|---|
| `POST /v1/labels/pdf` | o PDF da etiqueta |
| `POST /v1/labels/zpl` | ZPL, para impressora térmica |
| `GET /v1/trackings/{codigo}` | rastreamento |

E o corpo aceita **`invoice_keys`** — a chave de acesso da NF-e. **Nós já a temos**, no painel
(`nfe.xml.panel.key`) e na fatura (`account.move.nfe_key`). Ou seja, o caminho da etiqueta até
a transferência é curto: mesma mecânica com que o XML passou a ficar pendurado no picking.

### 19.3 O que custa, e o que precisa ser confirmado com a Olist

- **Credenciais**: OAuth2 com PKCE, e `CLIENT_ID`/`CLIENT_SECRET` são **criados pelo time
  técnico da Olist**. É preciso informar a eles uma `REDIRECT_URI` antes.
- **Token de 4 horas** (`expires_in: 14400`), renovável por `refresh_token`. Exige **cron de
  renovação** — requisito de desenho, não detalhe (a mesma pedra da v3, §5).
- **Não queremos `POST /v1/shipments`**. Ele CRIA envios e a doc avisa sobre cobrança
  duplicada: é escrita paga. Os envios já existem — quem os cria é o Olist ao expedir. Nós
  queremos só a etiqueta do que já existe, o que nos mantém fora do caminho de cobrança.
- **A confirmar**: se `labels/pdf` devolve etiqueta de envio criado pelo **próprio Olist**, e
  não apenas pelos criados por nossa integração. É o ponto que decide tudo, e a doc não diz.

## 20. A janela de estoque não enxerga venda (2026-08-21)

O sintoma foi do dono: "Estranho não ter atualizado os estoques nessa madrugada."

Duas causas, independentes.

**A primeira, minha.** Ao rearmar os crons eu marquei quatro deles para o mesmo minuto.
`Olist: pull NFe XMLs` morreu com `could not serialize access due to concurrent update` no
`UPDATE olist_account SET last_sync…`: dois crons disputando a mesma linha da conta.
Corrigido escalonando o `nextcall` em staging (04:10, 04:25, 04:40, 04:55 UTC) — e os quatro
não voltam a coincidir porque os dois de período igual (2h) ficaram com deslocamento
diferente dentro da hora.

**A segunda, do Olist, e é a que importa.** `lista.atualizacoes.estoque.php` devolve
**zero produtos** — nas duas contas, e em janelas de 2, 7 e 29 dias, num período em que
houve venda. Não é erro de parâmetro, e isso foi conferido no ferro:

```
params=['dataAlteracao']  -> codigo_erro 20 "A consulta não retornou registros"
params=['data_alteracao'] -> codigo_erro 10 "O parâmetro dataAlteracao deve ser informado"
```

A segunda linha é a prova de que o nome está certo: o próprio Olist o exige. E a primeira
diz, sem rodeios, que não há registro nenhum.

A leitura mais provável: **esse endpoint reporta só a alteração de estoque feita VIA API** —
o eco das nossas próprias escritas — e não a movimentação que o ERP faz ao vender. Como a
conta está em somente-leitura desde o primeiro dia, nunca escrevemos, e por isso não há o que
ecoar. É hipótese, não certeza; a certeza é o zero.

**O que se fez com isso.** A janela fica (é uma chamada, é barata, e volta a valer no dia em
que o push for armado), mas deixou de ser o único caminho: o que sobra do ciclo, em cada
rodada, relê os saldos **mais velhos**, um livro por chamada, até o executor do cron avisar
que o tempo acabou (`_grava_ja` → `ir.cron._commit_progress`). O espelho converge por
antiguidade em vez de por aviso. Com quatro rodadas por dia o catálogo se renova em poucos
dias, e nenhuma rodada estoura — que era exatamente o defeito de 18/08.

Fora do cron o mesmo método devolve infinito e a varredura **não** acontece: o botão da tela
não pode virar vinte minutos de leitura sem ninguém ter pedido. Há teste para os três casos
(cabe / não cabe / fora do cron), porque as três vezes em que isto quebrou na mão do dono
foram exatamente as vezes em que eu testei a camada de baixo e não o que chega na tela.

**A pergunta que fica para o suporte do Olist**, junto com a das etiquetas (§19.3): o
`lista.atualizacoes.estoque` deveria reportar movimentação de venda, ou só alteração via API?
Se for a primeira, há defeito do lado deles e a releitura por antiguidade é paliativo.

## 21. O que de fato não subiu: o push estourava o tempo (2026-08-21)

A pergunta era sobre o estoque da madrugada, e a primeira resposta (§20) estava certa mas
respondia à pergunta errada: eu olhei o espelho de LEITURA, no staging. O que a operação usa
é o **prod**, e lá as duas contas estão com `read_only=false`, margem 5, e o cron que **sobe**
o estoque **armado**.

O log do prod diz, sem interpretação:

```
2026-08-21 02:09:39 ERROR prod ir_cron: Job 'Olist: push stock (balanço)' (58) timed out
```

`failure_count=3`, e o último envio bem-sucedido foi 18/08 (só a N1-Site; a EdLab Press
nunca). Três noites seguidas.

A causa é a mesma que derrubou o `ler detalhe` em 18/08, no mesmo módulo, e eu não a corrigi
aqui: `_push_all_stock` varria ~580 produtos numa transação só, a ~2,2 s por chamada — uns
vinte minutos contra o teto de um ciclo de cron. O Odoo derruba a transação inteira: não é
que subiu menos, é que **não subiu nada**. E na terceira falha o executor passa a pular o
cron sem sequer rodá-lo.

**Correção.** A varredura passou a ser orçada e retomável, como as outras: `_grava_ja` antes
de cada livro, `stock_push_cursor` gravado a cada envio, e a rodada seguinte continua do id
onde parou em vez de recomeçar do início e nunca alcançar o fim do catálogo. Ao varrer tudo,
o cursor volta a zero. O botão da tela continua sem orçamento — quem clicou pediu a varredura.

Quatro testes: para dentro do ciclo, retoma de onde parou, varre tudo e volta ao início, e o
botão não é orçado.

**A lição que se repete.** Corrigi o orçamento em três crons em 19/08 e deixei o quarto —
justamente o único armado no prod. Quando a causa é de desenho, ela vale para todos os
irmãos, não só para aquele em que ela apareceu.
