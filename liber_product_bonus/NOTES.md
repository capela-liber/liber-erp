# Módulo `liber_product_bonus` — notas de concepção

> Documento de discussão/arquitetura do módulo de **bonificações** (exemplares dados a autores,
> jornalistas, influenciadores).
> Conversa de 2026-07-16, revisto na mesma data com as correções do `LOG.md`.
> Ainda **não há código** — só o desenho e as decisões que precisam de "vai".
>
> **Companheiros:** `UX.md` (como se usa — a tela de triagem é o coração do módulo) ·
> `TODO.md` (a ordem) · `LOG.md` (as correções dele, verbatim).

---

## 1. Motivação

Dar um livro não é "toma aí um livro". É um ato com dono, motivo, custo, **nota fiscal** e
**história**.

- Bonificação **se repete**: o mesmo jornalista recebe todo lançamento; listas VIP se acumulam.
- Bonificação **tem três donos diferentes**: editorial (autor), marketing, comercial.
- Bonificação **é obrigação contratual**: o autor assina e tem direito a X exemplares.
- Bonificação **compete com mídia paga**: mandar 40 livros à imprensa pode render mais que um
  anúncio. Para afirmar isso é preciso ter o número.
- Bonificação **consome tiragem** e tem que caber numa **meta travada**.
- Bonificação **gera nota** — no Brasil, toda movimentação precisa de XML.
- Bonificação **tem custo**, e esse custo pertence ao analítico do livro.

O que se quer guardar, no fundo, **não é o picking — é a história**.

## 2. A tese

**Bonificação não gera receita. Mas gera nota.**

As duas frases parecem brigar e não brigam — elas separam duas coisas que a palavra "fatura"
mistura:

| | Bonificação tem? |
|---|---|
| **Documento fiscal** (NF-e de simples remessa, CFOP 5910/6910, com valor) | **Sim, obrigatório** |
| **Lançamento contábil** (a despesa) | **Sim** |
| **Recebível / duplicata / financeiro** | **Não** |
| **Receita** | **Não** |
| **Pedido no funil comercial** | **Não** |

Uma nota de remessa **tem valor e não tem financeiro**. É esse o registro que falta.

> Correção do `LOG.md`: minha versão anterior dizia "nunca gera fatura". Errado. O que ela nunca
> gera é **recebível e receita** — a nota existe e é obrigatória.

## 2b. BO dispara, B000 é a ficha (correção dele, 2026-07-17)

> *"A BO é um disparador de lista vip e não propriamente a ficha de envio. Ela vai gerar uma B000
> para cada autor, pois cada um tem um endereço, um pacote que precisa ser feito lá no depósito e
> uma nota fiscal que vai ter que ser expedida."*

O primeiro protótipo colapsou os dois num documento só, e estava errado. **Uma decisão de
marketing vira N remessas físicas**, e cada uma tem endereço, pacote e nota próprios:

```
BO/2026/00007   o DISPARO — a decisão. Título, motivo, lista, meta, aprovação, campanha.
   ├── B00231   Ana Prado    · endereço · pacote no depósito · nota
   ├── B00232   Carla Nunes  · endereço · pacote no depósito · nota
   └── B00233   Davi Reis    · endereço · pacote no depósito · nota
```

Por que a distinção paga o preço de um modelo a mais:

- **A aprovação é do disparo.** O responsável da lista diz sim **uma vez**, não 47 vezes.
- **A meta é do disparo.** O contador vivo mede a decisão, não cada pacote.
- **O disparo é a unidade que discute com mídia paga.** *"47 livros, R$ 580"* contra
  *"um anúncio, R$ 4.000"* — uma ficha sozinha não faz essa frase.
- **A ficha é a unidade física e fiscal.** É ela que vira etiqueta, pacote e NF-e.

E fecha o D4: *"a convenção de duas letras é para os disparadores"*. **BO** é disparador e segue
`CR/ CO/ CP/` da casa. A ficha não é disparador → **B00231**, sem as duas letras.

## 3. O que o `B000` gera de fato

Ele pediu: *"um documento do tipo B000 que gera MOV e INV"* — e esclareceu: **INV é invoice
mesmo** (`account.move`), futuramente a fonte do **invoice-xml**. É a **ficha** (§2b) que gera os
três, uma vez por pessoa:

1. **MOV** — `stock.picking` no tipo `BON/`, validado na hora. O livro sai.
2. **INV** — `account.move`, com parceiro, linhas de produto, valores e **CFOP**. É dele que a
   emissão futura lê o XML. É nele que o analítico entra.
3. **XML** — ⚠️ **o repo é import-only: nada aqui emite.** (`liber_nfe_xml` só importa; não existe
   builder de `infNFe` fora de fixture de teste.) Então hoje a nota é emitida fora e **volta**
   como `nfe.xml.panel`, casada pelo `nfe_key` — que é como o repo já liga `account.move` ↔ XML
   (`liber_nfe_xml/models/account_move.py:10-34`). Quando o emissor existir (`liber_olist`), ele lê o INV do
   item 2. Até lá o B000 registra e **aguarda a chave**.

Um **estado da nota** no B000 ("a emitir / emitida / conciliada") fecha o ciclo e permite auditar
bonificação sem XML.

### ⚠️ Achado: a consignação NÃO tem solução de nota para copiar (18/07)

Ele pediu: *"não seria possível copiar a solução toda da C000 e apenas parametrizar em settings?"*
Fui olhar, e a resposta é **não — porque ela não existe lá**:

- **O acerto (S000) não gera nota por código.** O `action_run` cria um `sale.order` **em rascunho**
  (`liber_soc_settlement/models/consignment_settlement.py:615`) e para. Quem fatura é o usuário, pelo
  fluxo padrão do Odoo. Aquela nota tem recebível e pagamento porque é uma **venda comum**, não
  porque o soc fez algo.
- **A remessa (Pedido C) não tem documento de nota.** Nunca fatura (`_create_invoices` levanta).
  O contábil vem da **valorização de estoque** (`liber_soc_fiscal_br/models/stock_location.py:8`,
  `_should_be_valued()=False`) e a nota fiscal vem **importada** (`nfe.xml.panel`).
- ⚠️ **Os campos fiscais de consignação em Settings são configuração morta.** Posições fiscais e
  CFOPs (`liber_soc_fiscal_br/models/res_company.py:19-41`) estão declarados, aparecem na tela e
  **nenhum código os lê** — o `_create_sale_order` não seta posição fiscal nem CFOP. O único
  parâmetro realmente consumido é a conta de estoque de consignação. → **dívida do liber_soc_fiscal_br**,
  anotada; ou passa a ser consumida, ou a expectativa é falsa.

**Consequência para a bonificação:** o mecanismo "nota com valor e sem pagamento"
(`account.move` tipo `entry` + mapeamento em Settings) que existe no `liber_product_bonus` é o **único
do repo** que faz isso. Não havia o que copiar — mas também **não se inventa documento novo**: no
repo, nota = `account.move` + `nfe.xml.panel`. Um modelo `product.bonus.note` foi criado e
**removido** (18/07) justamente por quebrar essa simetria e criar um terceiro lugar para procurar
nota. As notas se veem todas em **Faturamento > NFe XML**.

### O B000 COORDENA, não emite (correção dele, 17/07)

> *"O documento B000 é homólogo do C000 ou S000. Ele serve para amarrar logística e nota. (...)
> Mas ele não pode prescindir de ser algo parecido com um documento que coordena nota e logística."*

O primeiro corte fazia o B000 **emitir** uma nota (bookar um `account.move` no envio e chamar isso
de "a nota"). Bizarro: o repo é **import-only**, como a consignação, e o coordenador de consignação
(`consignment.settlement`) **nunca emite** — ele amarra o picking (logística) e casa a NF-e
importada por `nfe_key`. Então o B000 ficou homólogo:

- **Logística** → `picking_id` (o MOV, BON/).
- **Nota** → `note_move_id` (a nota de remessa REM/, out_invoice auto-baixada) — antes era um `entry`,
  não a nota.
- **Nota fiscal** → `nfe_key` + `nfe_xml_panel_id` (casada por chave, como o `account.move` do
  `liber_nfe_xml`) + `fiscal_state`: **a emitir → emitida → conciliada**. O B000 **coordena**; a NF-e é
  emitida fora e volta por importação.
- **Comunicação** → chegou/rendeu.

A NF-e não é emitida por este módulo (nem pela consignação). O `fiscal_state` nasce "a emitir"; vira
"emitida" quando a chave casa com um `nfe.xml.panel` importado; e "conciliada" quando a mesma chave é
carimbada no lançamento (`action_reconcile_nfe`).

### ⚠️ O obstáculo estrutural do INV (é o **D9**, e é o ponto mais duro do desenho)

**No Odoo, um `out_invoice` não consegue não ter recebível.** A linha de AR é o que balanceia o
documento — não é opção, é a mecânica. Então "invoice sem financeiro" não existe nativamente, e é
exatamente isso que uma nota de remessa é. Três saídas, nenhuma limpa:

| | Como | Preço |
|---|---|---|
| **(a)** `out_invoice` com contrapartida trocada | Posição fiscal/conta do parceiro aponta o "recebível" para conta de **despesa** | É invoice de verdade, o emissor futuro lê sem adaptação. Mas mente no nome: a conta "a receber" é despesa. Muita localização BR faz assim |
| **(b)** `move_type='entry'` com linhas de produto + CFOP | Receita do `liber_soc_audit/models/consignment_move.py:132-144` | Contabilidade limpa, zero risco de AR. Mas **não é invoice** — o emissor futuro teria de aprender a ler outro formato |
| **(c)** `out_invoice` + baixa imediata contra despesa | Fatura normal, quitada na hora | Suja o razão do parceiro com AR que nunca existiu. **Descartar** |

**Resolvido por ele (17/07): faça como a consignação.** Não é nem (a) nem (b) como fatura — é o
caminho da consignação: a nota é um `account.move` **type `entry`** (Dr despesa / Cr saída de
estoque), com **config fiscal** (contas + posição fiscal + CFOP) em `Definições > Bonificações`,
igual ao `liber_soc_fiscal_br`. Como é `entry` e não `out_invoice`, **não há linha de recebível** — o
problema estrutural do D9 simplesmente não aparece. Valor se move, pagamento nunca é gerado.
Implementado: `product.bonus._create_note()`.

Em qualquer das saídas: **`account.move` não tem `cfop_id` hoje** — não existe em lugar nenhum do
repo. Sem ele não há invoice-xml. É pré-requisito.

### ⚠️ Achado: hoje dá para transformar uma bonificação em receita sem querer

O import de XML **ignora o CFOP por completo** (`grep -c cfop` em `liber_nfe_xml/models/liber_nfe_xml.py` = 0).
Se alguém importar o painel de uma 5910 e apertar "Criar Fatura", o `_invoice_import_one()`
(`liber_nfe_xml/models/liber_nfe_xml.py:247-259`) monta alegremente um `out_invoice` com os itens precificados
a `vUnCom` → **receita e recebível numa bonificação**. Exatamente o que o `liber_soc_fiscal_br` proíbe no
`sale.order` (`:61-73`) e que ninguém proíbe no import. As únicas guardas são `is_cancelled` e
fatura já existente.

É bug vivo, independente deste módulo. → **T1 no TODO.**

## 4. Os três motivos (confirmado por ele)

*"Temos razões distintas para doação. Autor (editorial), marketing, comercial."*

| | **Autor / Editorial** | **Marketing** | **Comercial** |
|---|---|---|---|
| Exemplo | Os 10 exemplares do contrato | Imprensa, influenciador, lançamento | Amostra para a livraria |
| Natureza | **Obrigação** (o contrato prometeu) | **Escolha** (substitui mídia) | Escolha (relacionamento) |
| Orçamento | Custo do título | Verba de marketing | Comercial |
| Aprovação | Não precisa (aprovada na assinatura) | Responsável da lista / gestor | Gestor comercial |

**Um único documento, um campo `motivo`, e o motivo roteia.** Não três módulos. O ato físico é
idêntico nos três; muda a classificação, a aprovação e o destino contábil.

Desenho: o motivo é um cadastro (permite motivos finos — "imprensa", "influenciador",
"lançamento") e cada motivo aponta para **um dos três baldes**. É no balde que a meta trava (§5).

Corolário: **exemplar de autor não é despesa de marketing.** Se cair na verba do marketing, o
marketing paga por um livro que não pediu e o custo do título fica subavaliado.

## 5. Tiragem é o estoque — e a meta é travada

> Correção do `LOG.md`: *"A tiragem é o estoque. Se fiz 3000 e quero doar x%, isso tem que ser
> acompanhado e travado."*

Isso derruba o modelo `print.run` que eu tinha proposto. **A quantidade impressa não é cadastro
novo — é a entrada em estoque.** O que precisa de modelo não é a tiragem: é a **meta de doação**.

```
Tiragem    = soma das entradas em estoque do título   (derivada, não cadastrada)
Doado      = soma das linhas de B000 do título        (derivada)
% doado    = Doado ÷ Tiragem
Meta       = o que se PERMITE doar, por balde         ← o único cadastro novo
Travamento = B000 que estoura a meta não passa        ← a regra que ele pediu
```

`product.bonus.quota` — por título × balde: 3000 impressos, meta 5% = 150 exemplares, divididos
p.ex. 40 autor / 90 marketing / 20 comercial. B000 que estoura → bloqueado. Liberação só por
gestor e **com registro** (o override é informação, não exceção).

⚠️ **O bloqueio é a rede, não o método.** Meta que só aparece na hora de salvar é punição e faz a
pessoa parar de mandar livro — que é o outro problema dele, tão real quanto o primeiro. A meta tem
de aparecer **enquanto se escolhe**, como contador vivo. Ver `UX.md` §2: *o freio é orçamento, não
permissão*. Se a UX funcionar, quase ninguém chega neste bloqueio.

Sutileza que precisa de decisão: **estoque é número móvel, tiragem é número fixo.** O saldo cai
conforme vende; a tiragem de 3000 continua 3000. Então "% da tiragem" tem de ler a **soma das
entradas**, não o saldo atual. E se houver reimpressão, 3000 + 2000 = 5000 — a meta se recalcula,
ou a 2ª tiragem tem meta própria? → **D1**.

⚠️ Não existe rastreio de lote/edição no repo (nada usa `tracking='lot'` nem `stock.lot`). Sem
isso, "tiragem" só existe **por título**, agregada — não dá para dizer "da 2ª tiragem doamos 4%".
Separar por tiragem é trabalho novo e não trivial. → **D1**.

## 6. Listas VIP — o cadastro operacional

> Correções do `LOG.md`: *"Uma lista VIP não é uma tag em contatos. Ela tem uma história. Quem
> montou, o que gastou, quem foi o responsável."* + *"Importação e emissão de etiquetas em lista
> VIP é algo muito importante, bem como follow-up para saber se o livro chegou."*

A lista não é um agrupamento — é **uma máquina de expedição com dono e orçamento**. Ela nasce,
alguém a monta, alguém responde por ela, ela gasta dinheiro e deixa rastro.

```
product.bonus.list
├── responsável (res.users)      → é ele quem APROVA os B000 desta lista
├── quem montou + quando
├── meta de doação               → o teto que os B000 da lista têm de caber
├── gasto acumulado              → "o que gastou" (soma dos B000 enviados)
├── membros → product.bonus.list.member   (NÃO é um m2m)
│   ├── parceiro, entrou_em, saiu_em, quem_adicionou, ativo
│   └── ← é isto que dá "história" à lista
└── histórico → os B000 gerados: quem recebeu QUE livro e por QUÊ
```

**Membro é um modelo, não um m2m.** Um m2m sabe quem está na lista *hoje*; ele quer saber quem
entrou, quando e por quem. É a diferença entre uma tag e um cadastro.

### 6b. O retorno — o que a bonificação rendeu

Metade da razão de existir do módulo (§7) e a coisa que faz a próxima decisão ser rápida.
Desenho completo em `UX.md` §7; aqui só o que é modelo:

```
product.bonus.outcome   (ou campos no próprio product.bonus — decidir)
├── retorno    Silêncio · Meia-boca · Divulgou · Arrasou   ← as palavras dele (U7)
├── link       URL do post/resenha/vídeo — a prova (U9)
├── data       quando se registrou
└── quem       quem marcou

product.bonus.reason  ganha:
└── janela_retorno_dias   Influencer 21 · Imprensa 120 · Comercial 60   (U8)
                          ⚠️ janela única faria o Estadão virar "silêncio"

res.partner  ganha:
├── bonus_outcome_rate    "5 de 7" — taxa crua, NUNCA nota de 0 a 100 (U7/§7.5)
└── no_bonus + motivo + quem marcou + quando   "não mandar mais", manual (U11)
```

Estados do B000: `enviado → chegou → aguardando → (silêncio | meia-boca | divulgou | arrasou)`.

⚠️ **`aguardando` ≠ `silêncio`.** Enquanto a janela não fecha, é cedo para julgar — quem recebeu
ontem não pode aparecer como fracasso hoje. O estado envelhece sozinho quando a janela vence.

⚠️ **Três falhas diferentes**, e confundi-las causa erro caro (`UX.md` §7.2): **não chegou**
(logística → **reenviar**, não punir) · **não confirmou** (prova fraca, quase todo mundo ignora
follow-up) · **silêncio** (chegou, janela fechou, nada — *este* é sinal). O "não mandar mais"
pendura no terceiro.

Operação — o que faz a lista servir para alguma coisa:

- **Importação de membros** — CSV/planilha. É assim que uma lista de imprensa nasce na vida real.
- **Emissão de etiquetas** — relatório de etiquetas de endereçamento a partir dos B000 de uma
  remessa. Sem isso ninguém posta 200 livros.
- **Follow-up de chegada** — o B000 tem estado de entrega: enviado → **chegou?** Código de
  rastreio, data de confirmação, atividade de cobrança. *"O livro chegou"* é a pergunta que fecha
  o ciclo, e hoje ninguém sabe responder.

E a regra que ele fez questão de dizer: ***"não podemos mandar todo livro que sai para todas as
pessoas."*** A lista **não** é "todo mundo recebe tudo". Cada remessa escolhe título e
subconjunto. O assistente de geração nasce com essa fricção, não contra ela.

## 7. Qual é o "custo" de dar um livro?

Dois números legítimos, e confundi-los envenena a análise:

1. **Custo** — o que saiu do caixa: impressão, papel, frete. É o `standard_price`.
2. **Receita não realizada** — o que se deixou de ganhar: preço de venda × quantidade.

Para o **marketing**, o número certo é o **(1)**. "Livro vs. mídia paga" só fecha em caixa:
*"mandei 40 livros a R$ 12 = R$ 480; o anúncio equivalente custaria R$ 4.000"*. A preço de capa a
mesma conta infla a bonificação em 3–4× e faz a mídia parecer barata.

O (2) é outro relatório (editorial: "de quanta receita a casa abriu mão"). Não misturar.

⚠️ **Mas custo é só metade da conta.** "Gastei R$ 480 em livros" não é melhor que "gastei R$ 4.000
em anúncio" — é só mais barato, e barato e inútil perde de caro e eficaz. A frase que justifica o
módulo (*"às vezes dar um livro é mais vantajoso que pagar mídia"*) só fecha com o **retorno**:
*"40 livros · R$ 480 · 22 divulgações, 3 em veículo nacional"*. Ver `UX.md` §7 — **retorno não é
enfeite, é a outra metade da razão de existir**. É o que exige o `product.bonus.outcome` (§6b).

⚠️ Cuidado com o INV: **o valor da nota de remessa não é o custo.** A nota vai a valor comercial
(é o que o fisco quer ver); o analítico tem de receber o **custo**. São dois números no mesmo
documento — não deixar o segundo virar o primeiro.

**Custo congela no envio.** Nunca computado ao vivo — o custo muda com a próxima tiragem e o
histórico de 2024 passaria a mentir.

## 8. Analítico e orçamento

O módulo `liber_budget` já faz orçamento aberto sobre analítico. Logo o orçamento de marketing **não
precisa de código novo** — precisa de conta analítica e de um `budget.analytic` em cima. O módulo
só tem de *postar no lugar certo*.

- **Destino "marketing"**: conta analítica por motivo, configurável em Ajustes.
- **Destino "livro"**: aqui há um problema real. O analítico existente
  (`liber_copyright_contracts_analytics`) é **por linha de royalty (obra × beneficiário)**, no plano
  "Copyright Contracts" — **não é um analítico por título**. "Analítico do livro" e "analítico do
  contrato da obra" não são a mesma conta. → **D2**.

⚠️ Memória `budget-analytic-plan-mismatch`: a view `budget_report` hardcodeia `account_id`. Plano
diferente → relatório lê zero. Testar de fato.

## 9. O que o repo já tem

| Já existe | Onde | O que dá |
|---|---|---|
| CFOP 5910/6910 → `document_kind='bonus'` | `liber_nfe_xml/models/nfe_cfop.py:18` | Classificação fiscal pronta |
| *"A bonus is a gift — an expense, never revenue"* | `liber_soc_fiscal_br/models/sale_order.py:61` | A tese já está escrita no código |
| Bonus não é Pedido C | `liber_soc_fiscal_br/models/sale_order.py:51` | Já fora da consignação |
| `consignment_effect` sem valor `bonus` | `liber_nfe_xml/models/nfe_cfop.py:58` | Nunca toca a prateleira |
| `account.move` ↔ XML por `nfe_key` | `liber_nfe_xml/models/account_move.py:10-34` | A junção com a nota (§3) |
| Valor sem recebível (`move_type='entry'`) | `liber_soc_audit/models/consignment_move.py:132-144` | A saída (b) do D9 |
| Tipo de operação próprio por empresa | `liber_soc_moves/models/res_company.py:32-64` | Receita do `BON/` |
| Expedição com validação imediata | `liber_soc_settlement/models/consignment_settlement.py:636` | Receita do MOV |
| Orçamento sobre analítico | módulo `liber_budget` | Verba de marketing já tem casa |

**Bonificação hoje existe só como proibição** — bloqueia fatura, bloqueia Pedido C. Nada posta a
despesa, nada emite, nada registra. Este módulo é a implementação de um contrato já escrito.

Não existe: entitlement no contrato, meta de doação, listas, rastreio de lote/edição, **`cfop_id`
em `account.move`**, nem configuração de CFOP/posição fiscal de bonificação em `res.company`
(só há shipment/sale/return — `liber_soc_fiscal_br/models/res_company.py:8-41`).

## 10. Fronteiras — o que este módulo NÃO faz

- **Não transmite XML.** Produz o **INV** de que a emissão futura vai ler; a transmissão é do
  adaptador (`liber_olist`) ou vem por importação (`liber_nfe_xml`). Mesma regra do `liber_olist/NOTES.md`: o Odoo é
  o razão canônico, emissão é adaptador plugável.
- **Não mexe com evento.** O `event_out`/`event_return` (a caixa que vai à feira **e volta**) é
  outro fluxo e fica fora. → `LOG.md`: *"não misturar evento com essa história"*.
- **Não mexe em consignação.** Bonificação não vai para a prateleira.
- **Não escreve `stock.quant`.** Invariante do repo (`liber_soc_moves/__manifest__.py`).
- **Não calcula royalty.** Se exemplar de autor abate royalty, é assunto do
  `liber_copyright_contracts_analytics` via `_edlab_accrual_entry_domain()`.

## 11. Decisões em aberto

| # | Decisão | Opções | Inclinação |
|---|---|---|---|
| **D9** | **Como o INV existe sem recebível?** (§3) | (a) `out_invoice` com contrapartida em despesa × (b) `entry` com CFOP × (c) fatura+baixa. CFOP DE SIMPLES REMESSA | **(a)** — o alvo é invoice-xml, e (b) empurra o problema pro emissor. **Passa pela contabilidade antes de virar código.** Trava a Fase 4 |
| D1 | Tiragem por título ou por edição/impressão? | agregada por título (nada novo) × por lote (`stock.lot`, trabalho grande) POR ESTOQUE IMPRESSO ATÉ A CAMPANHA INICIAL | agregada por título; lote só se ele precisar mesmo (§5) |
| D2 | O que é "analítico do livro"? | plano novo por título × reusar obra×beneficiário do contrato É TUDO QUE SAI E ENTRA DO LIVRO E FALA SE ELE DEU LUCRO | plano novo "Títulos" (§8) |
| D4 | Sequência | `B00001` × `BON/2026/00001` (convenção da casa: CR/, CO/, CP/) A CONVENÇÃO DE DUAS LETRAS É PARA OS DISPARADORES. ACHO QUE TEMOS AQUI MAIS UMA SITUAÇÃO DE DISPARO. "BO"? | ele já disse B000 duas vezes → **B** |
| D5 | Entitlement no contrato ou na linha de royalty | contrato × linha (obra×beneficiário) | linha — contrato multi-obra quebra o campo no header |
| D7 | Lista gera 1 B000 por pessoa ou 1 por remessa? | por pessoa × por remessa | **por pessoa** — o histórico e a etiqueta são por pessoa (§6) POR PESSOA |
| D10 | Metas: só por título×balde, ou também por lista? | só título × título + lista | ambas — ele citou "meta inicial de doação" nos dois contextos (§5, §6) AMBAS |

**Resolvidas por ele em 2026-07-16** (`LOG.md` + conversa):
- ~~D3~~ Autor cai em marketing? **Não** — três baldes distintos (§4).
- ~~D6~~ Quem aprova? **O responsável da lista** (§6).
- ~~D8~~ Evento? **Fora** (§10).
- Tiragem = estoque, não cadastro (§5).
- Nota existe e é obrigatória (§2).
- INV = invoice de verdade, futuro invoice-xml — **não** um `entry` de conveniência (§3).

---

## Apêndice — nome e forma

- Pasta/módulo: `liber_product_bonus`. Modelos: `product.bonus*`.
  (`edlab` está reservado para módulos específicos, como o de migração — `LOG.md`.)
- Categoria: `Marketing`. `application: True`.
- Depends: `base`, `mail`, `contacts`, `product`, `stock`, `stock_account`, `analytic`, `account`,
  `liber_nfe_xml`. (`liber_copyright_contracts` fica em módulo-ponte — Fase 5 — para não amarrar marketing a
  contratos.)
- Esqueleto: espelhar `liber_soc_moves`.

### O teste dos campos burros (18/07)

`test_no_dumb_config_fields` varre os campos que o módulo põe em `res.company` e
os `config_parameter` de Settings, e falha se algum nunca é lido em Python.
Motivo: o liber_soc_fiscal_br declara 9 campos fiscais de consignação que ninguém lê.
Rodando a mesma lógica sobre ele hoje:

    consignment_stock_account_id             LIDO (valuation_account_id)
    consignment_shipment_fiscal_position_id  MORTO
    consignment_shipment_cfop_in/out_id      MORTO
    consignment_sale_fiscal_position_id      MORTO
    consignment_sale_cfop_in/out_id          MORTO
    consignment_return_fiscal_position_id    MORTO
    consignment_return_cfop_in/out_id        MORTO

### O conserto NÃO é apagar (corrigido em 18/07)

Minha primeira leitura foi: "o Odoo já aplica posição fiscal no create do acerto
(`sale.order.fiscal_position_id` é compute/store/precompute a partir do
parceiro), logo os 9 campos são duplicata morta -- apagar". ERRADO, e o Jorge
apontou o porquê.

O Odoo aplica UMA posição fiscal, não A posição fiscal certa.
`res.partner.property_account_position_id` é campo ÚNICO: a livraria tem uma
posição fiscal só, a do regime e do estado dela. A mesma livraria recebe remessa
de consignação (5917) e pode comprar em firme (5102). O parceiro não codifica as
duas porque aqui **a posição fiscal é ditada pela OPERAÇÃO, não pelo cliente** --
eixo ortogonal ao que o mecanismo padrão sabe derivar.

E a falha é silenciosa e fiscal: campo morto não faz nada e a gente descobre; o
padrão do Odoo faz algo -- põe posição fiscal de venda numa remessa -- e ninguém
vê até a nota sair errada.

Então os 9 campos são configuração LEGÍTIMA do eixo-operação, nunca fiada. O
conserto é lê-los no código, não apagá-los. E o padrão já existe de um lado: o
B000 seta `fiscal_position_id` a partir de `bonus_fiscal_position_id` em
`_book_entry`. Falta o outro lado (C000/S000).

Pendente, em branch próprio (mexe em liber_soc_fiscal_br + liber_soc_settlement):
- `_create_sale_order` do acerto passa a setar a posição fiscal de consignação,
  sobrepondo a derivada do parceiro
- o mesmo teste dos campos burros instalado dentro do liber_soc_fiscal_br
- em aberto: trava dura ou default editável? ("uma C000 não pode usar outra
  posição fiscal") -- aguardando decisão
- os CFOPs ficam sem consumidor por ora: nada neste repo emite XML, e a solução
  de XML está sendo pensada em separado. NÃO antecipar desenho em cima disso.

Lição do erro: o teste dos campos burros acertou (os campos SÃO mortos). Quem
errou foi o remédio que eu tirei do achado. O teste diz "ninguém lê" -- não diz
"apague".

### A nota vira documento REM/ — o desenho fechado com o Jorge (18/07)

"Bastava criar um documento totalmente separado" — o paralelo dele com SO/SOC.
E a lição do product.bonus.note é que documento separado ≠ MODELO separado: o
jeito Odoo é mesmo motor (account.move), DIÁRIO próprio.

**O achado que destravou tudo**: a produção (Odoo 15, hedra_legacy) resolve
"nota sem pagamento" com o módulo proprietário `edoo_invoice_paid` — dois
campos na posição fiscal (`auto_invoice_paid` + conta) que TROCAM a conta da
linha de recebível. Um documento só, sem contra-lançamento; 11 posições
fiscais usam (inclusive uma conta chamada BONI). O Odoo 19 proíbe essa troca
por construção (account_move_line.py:1472 — payment_term ⟺ recebível, XOR
duro). O equivalente legal: lançar normal e BAIXAR na hora, conciliado.

**O que ficou** (módulo `liber_nfe_remessa`):
- Diário REM/ (tipo venda, `is_remessa`), criado no primeiro uso por empresa.
- Os MESMOS dois campos do O15 na posição fiscal → migração 1:1 das 11.
- Hook no `action_post`: diário de remessa + posição auto-paga → baixa +
  conciliação. Nota fica Paga, resíduo zero, nada a cobrar. Sem posição
  auto-paga, RECUSA — remessa que cobra pagamento é contradição.
- A baixa vai no diário Miscellaneous: sequência fiscal REM/ SEM buracos
  (a primeira versão comia números pares com as baixas).
- Faturas exclui `is_remessa`; menu Faturamento > Remessas mostra todas as
  notas de movimentação juntas (bonificação, consignação, futuros eventos).
- COM/ agora é a logística da consignação (era REM/) — dois documentos de
  naturezas diferentes não dividem prefixo.

**No liber_product_bonus**: morreu o `account.move` tipo `entry` ("poderia me
apontar onde está a nota aqui?" — um lançamento não é nota). `note_move_id`
é uma out_invoice no REM/, a valor comercial (o custo analítico continua nas
linhas da B000 — dois números, duas casas). Settings enxugou: caíram diário +
contas (o diário é o REM/ compartilhado; as contas moram no mapeamento da
posição fiscal). O teste dos campos burros foi quem cobrou a limpeza.

**Pendente**: o lado C000 (remessa de consignação gerando nota REM/ com a
posição fiscal de consignação — os 9 campos "mortos" ganham consumidor) e o
menu Remessas dentro de Consignação/Bonificações com filtro restritivo.

### O lado C000 fechou no mesmo dia (18/07, tarde)

Ele deu o "vai" na prática, com três apontamentos de tela:
1. **C00003 entregava em WH/OUT** ("Pedidos de entrega") — remessa de
   consignação parecia venda que esqueceram de faturar. Agora o Pedido C
   entrega em tipo próprio (Consignment Delivery, outgoing), compartilhando a
   numeração COM/ com os fluxos de prateleira (stock.rule troca só a perna
   outgoing; pick/pack de armazém multi-etapa ficam nos seus tipos).
2. **"Criar fatura" num Pedido C morria** em "quantia da entrada deve ser
   positiva" — não há o que faturar. O botão some em Pedido C; entra "Gerar
   nota", que cria a REM/ com a posição fiscal de consignação de Settings —
   **o campo morto `consignment_shipment_fiscal_position_id` ganhou seu
   consumidor**, e os testes o mantêm consumido.
3. **Remessas separáveis por origem**: `remessa_origin` plugável
   (selection_add) — bonus / consignment / futuro event. Lista própria no menu
   Remessas com filtro e agrupamento; cada módulo traz seu filtro.

Prova ponta a ponta no consig_demo: C00017 → COM/2026/00009 (Consignment
Delivery) → REM/2026/00001 paga, resíduo 0, origem consignment, posição
"Consignação — Remessa".

Pendências herdadas: CFOPs de consignação em Settings continuam sem consumidor
(a nota não carimba CFOP — decisão adiada junto com a solução de XML); o tour
do acerto segue exigindo Chrome real; "Consignment Delivery" sem tradução no
liber_soc_moves/i18n (po está em WIP do Jorge, não mexi).

### nota_remessa vira liber_nfe_remessa (19/07)

"nota_remessa é um nome estranho no universo dos nossos módulos."

E era: o único sem prefixo de família, ao lado de liber_nfe_xml, soc_*, edlab_*,
copyright_contracts_*. Virou **liber_nfe_remessa**, que entra na família fiscal já
existente e diz o que ele é — documento fiscal brasileiro.

**Mas ele NÃO é do ecossistema do liber_product_bonus**, ao contrário do que a
pergunta supunha. Dependem dele DOIS módulos:

    liber_soc_fiscal_br  → liber_nfe_remessa   (a nota do Pedido C)
    liber_product_bonus  → liber_nfe_remessa   (a nota da B000)

Se fosse absorvido pelo liber_product_bonus, a consignação passaria a depender do
módulo de bonificação para emitir a nota da remessa dela — hierarquia
invertida: o soc é a linha principal da casa, o bonus é o recém-chegado. E o
módulo de eventos, quando vier, dependeria dos dois.

Renomear módulo exige migrar o BANCO, não só o código: `ir_module_module.name`,
`ir_model_data.module` e os XML ids que carregavam o nome antigo. Sem isso o
Odoo trata como módulo novo, instala do zero e deixa o velho instalado ao
lado — com dois menus "Remessas" e dois diários. Feito em bonus_demo e
consig_demo; os modelos são todos herdados (`account.move`, `account.journal`),
então não houve migração de dados.

Fonte do módulo passou para inglês (convenção da casa: UI em inglês +
pt_BR.po). "Simples remessa" ficou como está na faixa: é termo fiscal
brasileiro, como CFOP — traduzir seria inventar um nome que a nota não tem.
