# `liber_product_bonus` — UX

> Como isso se usa. Companheiro do `NOTES.md` (o quê e por quê) e do `TODO.md` (a ordem).
> Conversa de 2026-07-16.

---

## 1. A tensão que organiza tudo

Ele disse as duas coisas na mesma respiração, e as duas são verdade:

> *"Tenho que definir um jeito para não sair dando livro a torto e a direito."*
> *"Também não mandar livro é ruim."*

Um sistema que só atende a primeira é fácil de fazer e destrói a segunda: põe aprovação em tudo,
e o marketing para de mandar livro. Um que só atende a segunda é o que existe hoje: não existe.

**A saída não é achar o meio-termo entre os dois. É notar que "o oposto de dar a torto e a direito
não é dar pouco — é dar bem".** Dois jornalistas com 22 livros cada e 22 jornalistas com 1 livro
cada gastam a mesma tiragem e produzem resultados opostos. O volume não distingue os dois casos.
Só a **escolha** distingue. Então o sistema não deve mirar em reduzir volume; deve mirar em
melhorar a escolha.

## 2. O princípio: o freio é orçamento, não permissão

Esta é a decisão de UX mais importante do módulo, e ela decide se a ferramenta é usada ou burlada.

| | **Permissão** ("peça autorização") | **Orçamento** ("você tem 90, usou 47") |
|---|---|---|
| O que produz | Medo. A pessoa desiste, ou pede e espera | Escolha. A pessoa prioriza |
| Falha para que lado | **Não manda livro** — o problema #2 | Manda, e manda melhor |
| Onde aparece | Na hora de **salvar** | Na hora de **escolher** |

**A mesma meta gera os dois comportamentos — o que muda é *quando* ela aparece na tela.**

- Meta que aparece **ao salvar** é punição. A pessoa já montou a remessa, já gastou o trabalho, e
  leva um "não" na cara. Ela aprende a odiar o sistema e a contorná-lo.
- Meta que aparece **enquanto escolhe**, como um contador vivo no topo, é orientação. A pessoa se
  autorregula sem nunca bater na parede.

Corolário prático que responde ao "não mandar é ruim": **meta não gasta é um lembrete, não uma
economia.** Se sobram 43 exemplares da meta de marketing de um título, isso é uma pendência, não
uma virtude. A tela tem de dizer isso.

O bloqueio duro (`NOTES.md` §5) continua existindo — mas ele é a **rede**, não o método. Se a UX
funcionar, quase ninguém chega nele.

## 3. Duas portas, não uma tela

> *"Uma coisa é o marketing/comercial e outra é o que está no contrato. Contrato é mais simples:
> define-se o número de exemplares e gera-se uma B0000."*

Ele está certo, e isso é uma decisão de UX, não só de modelo. **Forçar os dois no mesmo formulário
estraga os dois.** São problemas diferentes:

| | **Contrato** | **Marketing / Comercial** |
|---|---|---|
| Quantas pessoas | 1 | dezenas |
| Tem decisão? | **Não** — o contrato já decidiu | **Sim, é só isso** |
| O trabalho é | executar | **escolher** |
| A interface é | **um botão** | **uma tela de triagem** |

### Porta 1 — Contrato: um botão, não uma tela

Não merece assistente, não merece menu. Mora **dentro do contrato**, onde a pessoa já está:

```
┌─ Contrato 2026/014 · A Casa do Sol · Marina Vaz ────────────────┐
│                                                                 │
│  Exemplares do autor    10                                      │
│  Entregues               4   (B00231 · B00298)                  │
│  Faltam                  6                    [ Gerar B000 ]    │
└─────────────────────────────────────────────────────────────────┘
```

Um clique gera o B000 com motivo Autor, destinatário e quantidade preenchidos, sem aprovação
(o contrato já aprovou — `NOTES.md` §4). Se `faltam = 0`, o botão some. Se alguém tentar passar
de 10, avisa e deixa passar com registro — contrato tem aditivo, cortesia acontece.

### Porta 2 — Marketing: a tela de triagem

É o coração do módulo. Tudo abaixo é sobre ela.

## 4. A tela de triagem

Responde de uma vez ao *"mandar para quem? como filtrar rápido?"*, ao *"vou ter que decidir se vai
ou não vai"* e ao freio do §2 — porque põe os três na mesma tela.

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  Enviar bonificação                                                            │
│                                                                                │
│  Título  [A Casa do Sol            ▾]    Motivo [Imprensa ▾] → verba Marketing │
│                                                                                │
│  DE ONDE VEM ESTA GENTE  (as fontes somam)                                     │
│    Listas VIP        [Imprensa literária ×] [Todo mundo em SP ×]               │
│    Disparo anterior  [BO/2026/00003 ×]                                         │
│    Com etiqueta      [influencer ×]              …e na UF  [SP ▾]              │
│    E mais, a dedo    [Marina Vaz ×]                                            │
│    24 nomes somados · 7 repetidos · 17 candidatos                              │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ META · marketing · A Casa do Sol   ▓▓▓▓▓▓▓▓▓▓░░░░░░░░   47 de 90         │  │
│  │                                                          restam 43       │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│   ✓  Quem                 De onde veio      Já tem? Recebeu  Rendeu   Endereço │
│  ────────────────────────────────────────────────────────────────────────────  │
│  [x] Ana Prado · Folha    Imprensa + SP        —       7     5 de 7       ✓    │
│  [ ] Bruno Lima · Estadão Imprensa          ⚠ SIM      3     2 de 3       ✓    │
│  [x] Carla Nunes · 4C5    BO/2026/00003        —       1     1 de 1       ✓    │
│  [ ] Davi Reis · free     Imprensa             —      22   0 de 22 ⚠      ✓    │
│  [x] Elis Rocha · Cult    a dedo               —       0       —     ⚠ sem CEP │
│                                                                                │
│  47 selecionados · cabe na meta ✓          [Salvar seleção como lista]         │
│                                            [ Conferir e enviar ▸ ]             │
└────────────────────────────────────────────────────────────────────────────────┘
```

**As colunas *são* a decisão.** Não são enfeite — cada uma existe para responder um "vai ou não
vai?" em menos de um segundo:

| Coluna | Responde |
|---|---|
| **Já tem?** | O erro mais caro e mais burro: mandar o mesmo livro duas vezes |
| **Recebeu** | *É este o "torto e a direito"*. Davi com 22 livros aparece **sem ser bloqueado** |
| **Rendeu** | O que os 22 do Davi viraram. **É a coluna que desfaz a ambiguidade** — ver §7 |
| **De onde veio** | Com quatro fontes somando, *"por que fulano está aqui?"* deixa de ser óbvio — e é a primeira pergunta quando um nome surpreende |
| **Último** | Davi recebeu há 6 dias. Ana há 2 meses. Contexto, não regra |
| **Endereço** | Sem CEP não sai etiqueta (§6). Melhor saber agora que na hora de postar |

**O caso Davi Reis é o desenho inteiro em uma linha.** Ele tem 22 livros e **zero divulgações**. O
sistema **não** o bloqueia — mostra os dois números e deixa a pessoa decidir. Talvez ele seja o
crítico mais influente do país; talvez seja amigo de alguém. **O sistema não sabe qual dos dois é —
a pessoa sabe.** O trabalho do software é botar os números na frente dela no momento da decisão, e
calar a boca. Isso é "não dar a torto e a direito" sem uma única regra de bloqueio.

*(Sem a coluna **Rendeu**, o "22" é ambíguo e a decisão trava. Com ela, resolve em meio segundo.
Foi essa a pergunta dele, e a resposta está no §7.)*

### As quatro fontes — e elas **somam**

> *"Seria legal ele deixar juntar filter contact com as listas e até o manual."*
> *"Acho que vale poder colocar alguma outra seleção prévia (outras BOs)."*

O rádio forçava uma escolha artificial. *"A lista de imprensa **mais** os jornalistas de SP que
não estão nela **mais** o Fulano que pediu"* é um pedido normal — e com uma fonte só ele virava
três disparos, três aprovações e três chances de mandar dois livros para a mesma pessoa.

```
┌─ De onde vem esta gente ───────────────────────────────────────────┐
│  Listas VIP          [Imprensa literária ×] [Todo mundo em SP ×]   │
│  Disparo anterior    [BO/2026/00003 ×]                             │
│  Contatos com etiq.  [influencer ×]        …e na UF  [SP ▾]        │
│  E mais, a dedo      [Marina Vaz ×]                                │
│                                                                    │
│  ● Imprensa literária — 11        ↻ BO/2026/00003 — 6              │
│  ⚑ filtro: influencer — 6         ✎ a dedo — 1                     │
│  ─────────────────────────────────────────────────                 │
│  24 nomes somados · 7 repetidos · 17 candidatos                    │
│  — quem aparece em duas fontes recebe um livro só                  │
└────────────────────────────────────────────────────────────────────┘
```

**Mostrar a conta é o ponto.** Quatro fontes que somam só ficam claras se der para ver somando, e
o dedup é trabalho invisível: *"24 nomes, 7 repetidos, 17 candidatos"* é a diferença entre confiar
na tela e conferir na mão.

| Fonte | Para quê |
|---|---|
| **Listas VIP** | O caso normal. Várias de uma vez, sem criar lista nova |
| **Disparo anterior** | *"Quem recebeu o livro anterior"* — o BO **já é** uma seleção curada; alguém sentou e decidiu aquelas pessoas. É a base de mala direta mais natural que a editora tem, e torna quase desnecessário congelar campanha em lista |
| **Filtro** | Ad-hoc: etiqueta jornalista, UF |
| **A dedo** | O autor pediu mais um. Sempre tem |

⚠️ **Filtro vazio adiciona ninguém.** Antes ele caía em "todos os que recebem bonificação" — o que
com as fontes somando despejaria a agenda inteira em cima da sua lista. Silêncio tem de somar zero.

E a linha ganha **"de onde veio"**: com quatro fontes, *"por que fulano está aqui?"* deixa de ser
óbvio — e é a primeira coisa que se pergunta quando um nome surpreende.

**E a saída vira entrada:** `[Salvar seleção como lista]`. É assim que lista VIP nasce na vida
real — alguém fez uma triagem boa e ela merece durar. A lista é tanto **resultado** de curadoria
quanto insumo (`NOTES.md` §6).

### Centenas de listas — e por que a resposta quase nunca é "faça outra"

> *"Podemos ter centenas de listas VIP. Como fazer para selecionar um grupo e fazer uma nova?"*

Primeiro, uma confissão: **o botão `[Salvar seleção como lista]` é uma fábrica de listas.** Se
toda campanha virar uma lista permanente, em dois anos são 300 — cada uma usada uma vez, e nenhuma
achável. O problema que ele viu eu ajudei a criar.

A disciplina que segura isso: **o BO já é o registro da campanha.** Quem recebeu *A Casa do Sol*
em março está no BO/2026/00007, para sempre. Não precisa virar lista. **Lista é só para o que se
repete.**

Daí saem três respostas, em ordem de frequência:

| Você quer | Faça | Não faça |
|---|---|---|
| Mandar esta campanha para 3 listas | **O disparo aceita várias listas** e não duplica ninguém | Uma quarta lista que morre depois do lançamento |
| Uma combinação que vai **voltar** ("imprensa de poesia") | **Combinar em nova lista** — união, interseção ou diferença | Refazer a mão toda vez |
| Achar entre centenas | **Etiquetas**, busca, "nunca usadas", arquivar | Rolar |

#### Disparar para várias listas: o caso comum

```
De onde  (•) Listas VIP  [Imprensa literária ×] [Todo mundo em SP ×]
         → 2 listas somam 17 membros · 13 candidatos · 4 estavam nas duas
```

**O dedup é a parte séria.** Quem está em duas listas recebe **um livro**, não dois. Mandar o
mesmo livro duas vezes para a mesma pessoa na mesma campanha é o vexame mais barato de evitar e o
mais caro de explicar.

#### Combinar: só quando a união se repete

```
┌─ Combinar listas ──────────────────────────────────────────┐
│  Listas  [Imprensa literária ×] [Todo mundo em SP ×]       │
│                                                            │
│  Modo    (•) União — quem está em qualquer uma             │
│          ( ) Interseção — só quem está em TODAS            │
│          ( ) Diferença — a primeira, menos as outras       │
│                                                            │
│  · Imprensa literária — 11 membros                         │
│  · Todo mundo em SP — 6 membros                            │
│  ──────────────────────────────────────                    │
│  17 membros somados · 4 em mais de uma lista               │
│  → a nova lista fica com 13 pessoas                        │
└────────────────────────────────────────────────────────────┘
```

**A sobreposição é a informação.** *"4 pessoas estão em mais de uma lista"* responde uma pergunta
que ninguém fez em voz alta: estas duas listas são coisas diferentes, ou a mesma coisa com dois
nomes? Se de 11 e 6 a união dá 13, elas se sobrepõem pouco e são de fato coisas diferentes. Se
desse 11, uma delas é supérflua.

Os três modos ganham o seu sustento:
- **União** — "imprensa + influencers para o lançamento grande".
- **Interseção** — *"imprensa de SP"*: quem é imprensa **e** está em SP. É o recorte que a mão
  faria errado.
- **Diferença** — *"imprensa fora de SP"*, ou "a lista toda menos quem já recebeu".

E a nova lista **lembra de onde veio**: `montada a partir de Imprensa literária ∩ Todo mundo em SP`.
Daqui a um ano alguém vai olhar essa lista e perguntar por que fulano está nela — e a resposta tem
de estar no registro, não na memória de quem já saiu da empresa.

#### Achar entre centenas

- **Etiquetas** na lista (`imprensa`, `poesia`, `SP`, `2026`) — o único jeito de navegar 300 nomes.
- **"Nunca usadas"** — o filtro que separa patrimônio de peso morto. Lista que nunca despachou um
  livro em três anos não é uma lista, é um arquivo morto com pretensão.
- **Arquivar, não apagar** — lista que mandou livro é história.

### O lado positivo do freio ("não mandar é ruim")

A mesma tela tem de empurrar para mandar, não só para segurar. Duas peças:

- **A barra de meta com folga** é um convite: *restam 43*. Meta não gasta é pendência.
- **Sugestão**: *"12 jornalistas receberam o último livro deste selo e não receberam este"* →
  `[ver]`. É o motor do problema #2, e sai de graça do mesmo histórico que alimenta a coluna
  "Recebeu".

## 5. A conferência — *"podemos mandar mesmo?"*

Um passo antes de gerar. **Nunca um pop-up de erro** — uma lista do que está torto, com o conserto
ao lado:

```
┌─ Conferência · 47 bonificações de "A Casa do Sol" ──────────────┐
│                                                                 │
│  ✓  44 prontas                                                  │
│  ⚠   2 sem endereço completo    [corrigir]  [tirar da remessa]  │
│  ⚠   1 já recebeu este título   [mandar assim mesmo]  [tirar]   │
│                                                                 │
│  ✓  Meta      47 de 90 · sobram 43                              │
│  ✓  Estoque   47 de 380 disponíveis                             │
│  ✓  Verba     R$ 564 · orçamento do mês: R$ 4.000               │
│                                                                 │
│                    [◂ Voltar]     [Gerar 44 B000 e enviar]      │
└─────────────────────────────────────────────────────────────────┘
```

Regra: **o botão nunca fica cinza sem dizer por quê**, e todo ⚠ tem uma saída ao lado. Um "não"
sem conserto é como se perde um usuário.

## 6. As coisas pequenas que enchem o saco

> *"E coisas pequenas podem encher o saco: importar listas VIP, fazer etiquetas, lembrar de ligar
> para as pessoas que receberam para saber se chegou."*

**Ele tem razão e isso não é rodapé — é onde o módulo é adotado ou abandonado.** Ninguém abandona
um sistema porque o modelo de dados está errado; abandona porque teve que digitar 128 contatos à
mão.

### Importar lista

Colar de planilha ou CSV. O que faz a diferença: **casar com contato existente por e-mail** e
mostrar o resultado antes de gravar — *"128 linhas: 94 já são contatos, 31 novos, 3 duplicados na
própria planilha"*. Importação que cria 94 contatos repetidos é pior que não ter importação.

### Etiquetas

Relatório de etiquetas de endereçamento, em lote, a partir dos B000 de uma remessa. Botão em massa
na lista: seleciona → **Imprimir etiquetas** → PDF na folha padrão. Some da tela de "a imprimir"
depois de impressa (senão ninguém sabe o que já saiu).

Depende do endereço — por isso a coluna Endereço aparece lá atrás, na triagem (§4), e não aqui,
quando já é tarde.

### *"Chegou?"* — o follow-up

O ciclo só fecha aqui, e hoje ninguém sabe responder. **Não pode ser um formulário** — se custar
mais que um clique, não é feito:

```
Acompanhamento › A confirmar                          [Imprimir etiquetas]
────────────────────────────────────────────────────────────────────────────
B00412  Ana Prado · Folha       A Casa do Sol   enviado há 9 dias   [Chegou] [Não]
B00413  Carla Nunes · 4C5       A Casa do Sol   enviado há 9 dias   [Chegou] [Não]
B00414  Elis Rocha · Cult       A Casa do Sol   enviado há 12 dias  [Chegou] [Não]
```

Dois botões por linha. Um clique e sai da lista. **"Não" abre atividade** para o responsável da
lista — é o "lembrar de ligar" virando trabalho agendado em vez de peso na consciência.

A lembrança é do Odoo, não da pessoa: N dias após o envio (configurável), atividade automática
para o responsável da lista. **É o sistema que lembra, não você.**

## 7. O retorno — a metade que faltava

> *"O contato divulgou, divulgou maravilhosamente bem ou meia boca. Como posso ir criando uma
> maneira simples para que na próxima decisão a gente tenha uma maneira de decidir mais rápida?
> Pense no contexto de influencers. Não vejo UX pra isso."*

Ele está certo: não existia. E o buraco é maior do que parece.

### 7.1 Isto não é um extra — é a outra metade da tese

O módulo existe porque *"às vezes dar um livro é mais vantajoso do que pagar por mídia"*. O §7 do
`NOTES.md` deu o **custo** dessa conta. Mas **custo não prova nada sozinho**: "gastei R$ 480 em
livros" não é melhor que "gastei R$ 4.000 em anúncio" — é só mais barato. Barato e inútil é pior
que caro e eficaz.

**A frase só fecha com o retorno.** *"40 livros · R$ 480 · 22 divulgações, 3 em veículo nacional
— o anúncio equivalente custaria R$ 4.000."* Sem a segunda metade, o módulo mede o que gastou e
nunca o que ganhou. Retorno não é enfeite: é a razão de existir.

### 7.2 Duas coisas viraram uma — e é preciso separar

> *"O que acontece quando um contato não confirma que recebeu (e consequentemente, não queremos
> mais mandar)."*

Aqui há **duas falhas diferentes coladas numa frase**, e tratá-las igual causa um erro caro:

| O que houve | O que significa | O que fazer |
|---|---|---|
| **Não chegou** — voltou, o Correios perdeu | Falha **logística**. Não é culpa dele | **Reenviar.** ⚠️ Punir o jornalista porque o Correios sumiu com o livro é exatamente o avesso |
| **Não confirmou** — não respondeu ao follow-up | Prova **fraca**. A maioria das pessoas simplesmente não responde e-mail | Nada. Mostra, não pune |
| **Silêncio** — chegou, a janela fechou, não divulgou | **Este sim é sinal** | É daqui que sai o "não mandar mais" |

**O "não queremos mais mandar" pendura no silêncio, não no "não confirmou".** Não responder ao
follow-up é falta de educação, no máximo — não é falta de retorno.

### 7.3 A escada continua, não começa de novo

O follow-up de chegada (§6) já existe. **Retorno é o degrau seguinte da mesma escada** — não um
segundo fluxo, não uma segunda tela:

```
enviado ─→ chegou? ─→ aguardando ─→ ┬─ Silêncio      (a janela fechou, nada)
   │           │                     ├─ Meia-boca     (um story de 3 segundos)
   │           │                     ├─ Divulgou      (fez o trabalho)
   │           │                     └─ Arrasou       (capa, ou o vídeo que virou)
   │           └─ não chegou ─→ [Reenviar]
   └─ (sem confirmação) ─→ segue para aguardando assim mesmo
```

**O vocabulário é o dele, e isso é de propósito.** "Meia-boca" e "arrasou" são palavras que a
pessoa já usa no corredor. Escala com nome de gente é preenchida; escala com nome de sistema
("Nível 2 — Engajamento Parcial") não é.

### 7.4 Relógios diferentes — o ponto dos influencers

*"Pense no contexto de influencers."* Pois é: **influencer e crítico de jornal não têm o mesmo
relógio.**

| | Janela típica | Se a janela for única |
|---|---|---|
| **Influencer** | posta em 1 semana, ou nunca | — |
| **Crítico de jornal** | a resenha sai em 3 meses | ⚠️ **vira "silêncio" injustamente** |

Com janela única de 30 dias, **o Estadão vira "silêncio" e você para de mandar livro para o
Estadão.** Uma regra bem-intencionada destruindo a coisa mais valiosa que a editora tem.

→ **A janela é por motivo** (Influencer 21 dias · Imprensa 120 dias · Comercial 60). É o mesmo
cadastro de motivo que já roteia verba e aprovação (`NOTES.md` §4) — ganha mais um campo.

E o corolário: **`aguardando` ≠ `silêncio`.** Enquanto a janela não fechou, é cedo demais para
julgar. Quem recebeu ontem não pode aparecer como fracasso hoje. O estado envelhece sozinho.

### 7.5 Taxa, não nota — o score é uma armadilha

A tentação óbvia: `arrasou=3, divulgou=2, meia-boca=1, silêncio=0` → **"Score do influencer: 68"**,
com ranking. **Não fazer.** Parece inteligente e é chute com casas decimais:

- **Lava julgamento em número.** 68 não significa nada, e ninguém consegue discordar de 68.
- **Esconde o n.** Um sujeito com 1 livro e 1 "arrasou" tem score 100 e não provou nada.
- **Vira meta, e meta vira jogo.** No dia em que alguém for cobrado pelo score médio da lista, a
  lista some dos nomes difíceis — que são justamente os que valem.

**Mostrar a taxa crua: `5 de 7`.** É fato, não nota. Todo mundo entende, e dá para discordar dela
olhando os links.

### 7.6 O link é a prova

*"Divulgou"* sem link é opinião. **Com link é fato** — e da próxima vez você clica e vê o que a
pessoa fez, em vez de confiar na memória de alguém que já saiu da empresa.

O artefato natural da divulgação é uma **URL**: o post, a resenha, o vídeo. Colar leva 2 segundos e
torna o "arrasou" auditável — se alguém marcou arrasou e o link é um story de 3 segundos, isso se
descobre e se recalibra.

### 7.7 Onde se registra (o problema difícil de verdade)

**O retorno chega depois e sem avisar.** Você vê o post numa terça-feira, no celular. Se registrar
isso custar abrir o Odoo, buscar o contato e preencher um formulário, **não acontece nunca** — e um
histórico com metade dos retornos é pior que nenhum, porque parece completo.

Três momentos, todos de um clique:

**No acompanhamento** — a mesma lista do §6, agora com duas abas:

```
Acompanhamento › Rendeu?                          Janela: Imprensa · 120 dias
────────────────────────────────────────────────────────────────────────────────
B00412  Ana Prado · Folha      A Casa do Sol   chegou há 40 d
        [Silêncio] [Meia-boca] [Divulgou] [Arrasou]     🔗 colar link
────────────────────────────────────────────────────────────────────────────────
B00414  Elis Rocha · Cult      A Casa do Sol   chegou há 118 d  ⚠ janela fecha em 2 d
        [Silêncio] [Meia-boca] [Divulgou] [Arrasou]     🔗 colar link
```

**Na ficha do contato** — de onde você já está quando lembra da pessoa.
**Em lote** — seleciona 5, marca "Divulgou". A resenha coletiva existe.

### 7.8 Como isso volta para a decisão — a resposta à pergunta

A triagem (§4) ganha **uma coluna**, e é só isso:

```
 ✓   Quem                     Já tem?  Recebeu   Rendeu        Último
────────────────────────────────────────────────────────────────────────
[x]  Ana Prado · Folha           —        7      5 de 7        há 2 meses
[ ]  Bruno Lima · Estadão     ⚠ SIM       3      2 de 3        há 1 ano
[x]  Carla Nunes · 4C5           —        1      1 de 1        há 3 anos
[ ]  Davi Reis · freelance       —       22    0 de 22 ⚠       há 6 dias
[x]  Elis Rocha · Cult           —        0        —           nunca
```

**E aqui o caso Davi Reis finalmente fecha.** Antes, o "22" era ambíguo — *"talvez ele seja o
crítico mais influente do país e mereça os 22"*. Agora são **22 livros e zero divulgações**. A
ambiguidade acabou.

Repare no que **não** mudou: o sistema continua **não bloqueando** o Davi. A decisão continua sendo
sua. O que mudou é que ela deixou de levar cinco segundos e passou a levar meio. **O retorno não
adicionou uma regra — tirou a ambiguidade do número que já estava lá.** É exatamente isso que ele
pediu: *"uma maneira de decidir mais rápida"*.

### 7.9 ⚠️ O cold start — o erro que fossiliza a lista

Olhe a Elis Rocha: **`—`, não `0 de 0`.** Isso não é detalhe visual, é o desenho:

**Se "sem histórico" parecer ruim, ninguém novo recebe o primeiro livro — e sem o primeiro livro
nunca há histórico.** A lista congela nos mesmos 30 nomes de 2019 e a editora para de descobrir
gente. O jornalista que entrou este ano nunca entra.

**`—` tem que ler como "novo", não como "ruim".** É convite, não demérito. Se der para ir além:
uma linha na tela — *"12 nomes ainda sem histórico. Alguém tem que ser o primeiro."*

### 7.10 "Não mandar mais" — fora deste módulo (revisto 17/07)

Este protótipo teve por um tempo um flag `no_bonus` no contato, marcável da triagem. Ele mandou
**tirar**, e a razão é de escopo: *decidir que um autor sai da lista para sempre é uma decisão
editorial/de relacionamento, não escrituração de bonificação.* Um módulo que registra o que foi
doado não é o lugar onde se decreta que alguém está queimado.

O que este módulo faz — e é o suficiente — é **informar** essa decisão: o histórico e a taxa de
retorno estão na ficha do contato (22 livros, zero retorno). Quem olha decide. Onde a decisão é
registrada, se em algum lugar, é problema de outro módulo.

> A distinção que ficou clara: *mostrar o número* é papel deste módulo (a coluna "Rendeu" na
> triagem faz isso). *Vetar a pessoa* não é. O primeiro informa; o segundo governa relacionamento.

### 7.11 O que isso abre de graça

Com retorno registrado, três números que hoje não existem:

- **Por lista** — *"Imprensa literária: 128 pessoas · 340 livros · taxa 41%"*. Diz qual lista vale
  a pena e qual virou mala direta.
- **Por campanha** — fecha a conta da §7.1 e ganha a discussão com mídia paga.
- **Por motivo/balde** — *"Influencer rende 60%, Imprensa 25% — mas 1 imprensa vale 10 influencer"*.
  O número não decide; ele informa quem decide.

## 8. Onde mora cada coisa

```
Bonificações
├── Bonificações            todos os B000 · filtros por balde, campanha, título
├── Enviar bonificação      ← a tela de triagem (§4). É por aqui que se começa
├── Listas VIP              o cadastro (NOTES §6) · importar, ver histórico
├── Acompanhamento
│   ├── A confirmar         "chegou?" (§6)
│   └── Etiquetas a imprimir
├── Metas                   por título × balde · o que se permite doar
└── Configuração
    ├── Motivos             cadastro → balde, verba, se exige aprovação
    └── Contas e CFOP
```

**"Enviar bonificação" é um item de menu, não um botão escondido dentro de um formulário.** É a
ação mais frequente do módulo; enterrá-la atrás de "criar registro → preencher → salvar → agora
adicionar linhas" é o jeito clássico do Odoo de tornar uma tarefa de 30 segundos numa de 10
minutos.

E o histórico que ele mais quer aparece **onde ele já vai estar** — na ficha do contato:

```
┌─ Ana Prado · Folha de S.Paulo ─────────────────────────┐
│  [ 7 Bonificações ]   última há 2 meses   R$ 84 total  │
└────────────────────────────────────────────────────────┘
```

Um botão-caixa. Abre os 7 livros, com data, título e motivo. *"Abrir o jornalista e ver os 14
livros que ele já recebeu"* — `NOTES.md` §6.

## 9. O que NÃO fazer

Erros que este desenho evita de propósito. Vale reler antes de codar:

- **Aprovação em tudo.** Mata o problema #2. Aprovação só onde o motivo pede (`NOTES.md` §4).
- **Bloquear o Davi Reis.** Mostrar o 22 e deixar a pessoa decidir. Regra rígida vira contorno.
- **A meta só no fim.** Freio na hora de salvar é punição; na hora de escolher é orientação (§2).
- **Um formulário para gerar 47 documentos.** Triagem é uma tela de triagem, não 47 formulários.
- **Contrato e marketing na mesma tela.** Um é botão, o outro é tela (§3).
- **Botão cinza sem explicação.** Todo ⚠ tem conserto ao lado (§5).
- **Confirmar chegada em formulário.** Dois botões na linha, ou não é feito (§6).
- **Importar sem casar por e-mail.** 94 contatos duplicados é pior que nenhuma importação (§6).
- **Score de influencer.** Taxa crua (`5 de 7`), nunca nota (`68`). Nota lava julgamento em
  número, esconde o n e vira jogo (§7.5).
- **Punir quem o Correios sumiu com o livro.** "Não chegou" é logística → **reenviar**, não
  rebaixar (§7.2).
- **Janela única de retorno.** O crítico de jornal viraria "silêncio" e a editora pararia de mandar
  livro para o Estadão (§7.4).
- **`—` parecendo `0`.** Se sem histórico parecer ruim, ninguém novo recebe o primeiro livro e a
  lista fossiliza (§7.9).
- **Vetar a pessoa dentro deste módulo.** Mostrar o número é papel dele; decretar que alguém
  está queimado é decisão editorial, e mora em outro lugar (§7.10).

## 10. Decisões de UX em aberto

| # | Decisão | Opções | Inclinação |
|---|---|---|---|
| U1 | A triagem é wizard ou tela cheia? | wizard modal × action de tela cheia | tela cheia — 128 linhas não cabem num modal confortável OK |
| U2 | Meta estourada: bloqueia ou avisa? | bloqueia (gestor libera) × só avisa e registra | bloqueia OK — é o *"travado"* que ele pediu (`NOTES.md` §5). Mas a rede, não o método (§2) |
| U3 | "Chegou?" é estado ou campo? | estado do B000 (`enviado → chegou`) × campo booleano + data | estado — dá filtro, gráfico e cara de ciclo fechado OK |
| U4 | Prazo do follow-up | fixo × por lista × global em Ajustes | global em Ajustes, com override por lista OK |
| U5 | Sugestão "quem não recebeu" entra na v1? | sim × depois | depois — é o §4 "lado positivo", mas não bloqueia o resto OK |
| U6 | Etiqueta: qual folha? | Pimaco A4 padrão × configurável | **perguntar a ele** — depende do que a casa já usa OK |

Retorno (§7) — novas:

| # | Decisão | Opções | Inclinação |
|---|---|---|---|
| U7 | A escala de retorno | 4 níveis (Silêncio · Meia-boca · Divulgou · Arrasou) × 3 × só booleano | **4, com as palavras dele** — vocabulário de corredor é preenchido (§7.3) |
| U8 | Janela de retorno mora onde? | por **motivo** × por lista × global | por motivo — influencer 21 d, imprensa 120 d (§7.4). Mesmo cadastro que já roteia verba |
| U9 | Link da divulgação | campo URL simples × anexo × m2m de "mídias" | URL simples na v1. Um campo, dois segundos (§7.6) |
| U10 | Retorno entra na v1 ou depois? | v1 × v2 | **v1** — é a outra metade da tese (§7.1). Mas depois da triagem funcionar |
| ~~U11~~ | "Não mandar mais" mora onde? | — | **Resolvido: fora deste módulo** (§7.10). É decisão editorial, não escrituração de bonificação |

## §8 O Score do parceiro: nível e direção (18/07)

O gatilho foi ele olhando a coluna "Rendeu" e dizendo "isso não está muito
claro pra mim":

    5 de 7  |  2 de 3  |  1 de 1  |  0 de 22  |  —

Dois defeitos na mesma tela. `0 de 22` é a linha mais importante e tem o mesmo
peso visual das outras. E `1 de 1` PARECE a melhor de todas, quando é a que
menos informa. Fração obriga a fazer a conta e o julgamento de amostra de
cabeça, linha a linha, com 200 nomes na lista.

A ideia da nota é dele, com escala Fibonacci (0/5/8/13) — e ele mesmo achou o
defeito: "se uma pessoa recebeu muitas vezes vai pontuar mais". Pontos
acumulados medem volume, não rendimento.

O caso que ele deu resolve o desenho: 10 livros, 2 arrasou, 5 meia-boca, depois
silêncio. Média 5,1 — que lê como "meia-boca constante" e é MENTIRA: a pessoa
começou ótima e morreu. **Nenhum número único, somado ou médio, sobrevive a
esse caso.** Daí nível E direção:

    9 →   |  6 ↓  |  em teste (1/3)  |  0 ↓  |  novo

Três mecanismos (código e porquês em `models/bonus_rating.py`):

1. **Média ponderada por recência**, nunca soma — mata o viés de volume que ele
   apontou, e faz "divulgou bem em 2019" parar de sustentar quem sumiu.
2. **"Em teste" (a etapa de testes que ele pediu)** — abaixo de N avaliações não
   há nota. Amostra de 1 não é avaliação, é sorte. Acima do limiar a nota nasce
   encolhida para a média da casa e se solta conforme o histórico cresce.
3. **Direção** — metade recente contra a anterior. É a seta, não a nota, que
   diz "esse acabou".

Onde aparece: coluna na seleção do BO, nos membros das Listas (curar sem ver o
retorno é escolher no escuro) e na ficha do contato — lá com a fração crua e o
histórico inteiro embaixo, porque **a nota tem que ser auditável, não um
oráculo**.

No relatório, uma sutileza que quase passou: o pivot cruza pela situação
**congelada no envio** (`partner_band_at_send`), não a de hoje. Hoje a pessoa é
"Sem retorno" PORQUE mandamos; cruzar custo com a situação atual leria o
passado com informação que só existe por causa dele. Congelado, dá para
perguntar "quanto apostamos em quem já estava frio?" — que é a pergunta útil.

**O que a nota deliberadamente NÃO faz**: ordenar a lista. No dia em que a tela
ordenar por melhor nota, os "novo" e "em teste" caem para o fim, ninguém rola
até lá, e em dois anos a lista é os mesmos 30 nomes. Mostrar, filtrar, agrupar:
sim. Ranquear por padrão: não — e se for para fazer, que seja escolha explícita
dele.

Os três cortes (pontos, limiar do teste, meia-vida) são julgamento da casa e
moram em Definições > Bonificações — "parametriza em definições essas coisas".

### Ícone, não só cor (18/07, tarde)

⚘ (nunca recebeu) e ⚗ n/N (em teste) são **só o ícone, sem palavra** — cor
sozinha não diz O QUE uma célula é, e justamente estes dois precisam ser lidos
como *convite*, não como score baixo.

Os glifos vêm do bloco Miscellaneous Symbols e foram escolhidos por **não
terem variante emoji**: renderizam monocromáticos (pretos) por definição, sem
depender de seletor de variação nem da fonte do sistema. Font Awesome seria o
natural, mas um campo Char não renderiza HTML — e do jeito que ficou o símbolo
ainda sobrevive à exportação e ao PDF.

A explicação da escala inteira mora no `help` do campo (aparece ao passar o
mouse), não numa legenda ao lado: escala que precisa de manual na tela é escala
que ninguém usa.

"Nota" virou **Score** — em PT também, por decisão dele. A coluna "Rendeu" saiu
da aba Membros das Listas: o Score já a resume, e a fração crua continua na
ficha do contato para quem quiser auditar.

### Rótulo curto não basta: coluna numérica encolhe (18/07)

O teste de rótulos passava verde com a tela cortada. Motivo: ele media só o
comprimento, e **coluna numérica encolhe até o conteúdo** — "Bonificações" (12
caracteres) sobre um "67" trunca de qualquer jeito. Agora são dois limites: 22
para colunas de texto, **10 para numéricas**. Na primeira execução o limite
novo pegou mais três colunas que estavam cortando em silêncio.

Vocabulário unificado no caminho: "Taxa de retorno" virou **Rendeu** (a palavra
que o módulo já usava em toda outra tela) e a contagem de fichas virou
**Envios** — "Fichas" reintroduziria o termo que ele mandou aposentar quando
pediu que "Fichas B" se chamasse "Bonificações".

### A avaliação vira statusbar (18/07, noite)

"será que o botão de avaliação poderia ser assim?" — apontando para a
statusbar do documento. Sim, e é melhor: os quatro botões coloridos nunca
mostravam **qual** avaliação já tinha sido dada; a statusbar clicável mostra.
O que se perde é a cor por estágio, que os badges das listas mantêm.

Isso obrigou a mover o carimbo: data, autor e encerramento saíam de
`_set_outcome` (o botão). Com a statusbar gravando o campo direto, avaliar por
qualquer outro caminho — statusbar, importação, API — deixaria a avaliação
órfã: resultado sem quando nem por quem. O carimbo agora é do `write`, ou
seja, **do campo**. Uma avaliação sem autor não se discute em reunião nenhuma.

Vocabulário: "Rendeu?" virou **Avaliação** (aba, rótulo e ação) e o menu virou
**Avaliações**. A coluna "Rendeu" das listas continua — ela mostra a fração
("19 de 58"), que é outra coisa: quantas avaliações foram positivas.

### Ícones do Font Awesome (18/07, noite)

`fa-flask` (teste) e `fa-pagelines` (broto) — escolha dele, ambos existem no
Font Awesome 4.7 que o Odoo empacota. Exigiu trocar o campo de exibição de
Char para **Html** (Char escapa marcação), e daí veio um ganho: o `title` no
próprio `<i>` dá tooltip **por célula**, que é a "explicação no foco" de
verdade — o `help` do campo só aparece no cabeçalho da coluna. O rótulo em
texto (⚘ / ⚗ n/N) continua existindo para exportação, PDF e testes.

### Seleção em massa: de Contatos para a lista (18/07, noite)

"dá um jeito de selecionarmos vários ao mesmo tempo (quero por exemplo fazer
filtros e colocar vários na lista)".

O caminho é de **Contatos para cá**, não o contrário: os filtros bons já moram
lá (busca, etiquetas, agrupamentos, tudo que o Odoo dá de graça), e reconstruir
isso dentro do módulo seria refazer pior o que já existe. Marca-se o resultado
do filtro e **Ação > Adicionar à lista VIP**. Um botão na aba Membros abre o
mesmo assistente para quem já está com a lista aberta.

O assistente diz o que VAI acontecer antes de acontecer ("12 novos, 3 de
volta, 25 já na lista"). Sem isso, "adicionei 40 e a lista cresceu 3" vira
mistério — quando a explicação é banal: 37 já estavam lá.

**O bug que o teste pegou na primeira execução**: `member_ids` é um One2many e
**esconde os inativos**, então quem tinha saído da lista ficava invisível na
verificação, o `create` era tentado de novo e estourava a restrição de
unicidade. Só aparece na segunda rodada — que é o caso normal, porque se filtra
de novo e a maioria já está lá. `active_test=False` resolve.

### "O que é esse Saiu em?" — a data que nunca era gravada

A data em que a pessoa saiu da lista, o par de "Entrou em". Estava sempre
vazia: só o botão "Saiu" da tela avulsa de membros a preenchia, e na aba
Membros — onde se trabalha — tira-se alguém pelo toggle Ativo, que não gravava
nada. O carimbo virou do campo `active` (no `write`), como o da avaliação:
qualquer caminho grava. A lista é um modelo e não um m2m justamente para ter
essa história; perdê-la esvaziaria a razão de ser do modelo.

## §9 Importar planilha (18/07) — "o buraco mais feio", fechado

O difícil nunca foi ler o arquivo: é **não criar duzentos contatos
duplicados**. Uma lista de imprensa é quase toda gente que já está na base, e
um import ingênuo cria um segundo "Ana Prado" — que leva junto o histórico, o
Score e a checagem de quem já recebeu o título. Todos passam a olhar para o
cadastro errado, e ninguém percebe até alguém receber o mesmo livro duas vezes.

Três decisões:

**Prévia antes de gravar.** Sai do MESMO código que a importação executa —
prever por um caminho e executar por outro é como se produz a prévia que mente.
Ela diz "18 já na base, 7 novos, 3 repetidos na planilha, 4 sem endereço".

**Casamento por e-mail normalizado**, e por nome só quando não há e-mail (com
chave para desligar, porque homônimo é real). Na dúvida, cria — é o erro mais
fácil de desfazer.

**Sinônimos de cabeçalho.** A planilha do assessor não tem os títulos do modelo
nem a ordem dele: "Contato", "Celular", "Veículo", "e-mail". Exigir formato
exato é o jeito mais rápido de ninguém usar a ferramenta.

**O modelo é gerado pelo código que o lê** (`COLUMNS`), nunca um .xlsx escrito
à mão: arquivo estático envelhece calado, alguém muda um cabeçalho e o exemplo
passa a ensinar o formato errado. E o teste faz o ida-e-volta — gera, sobe,
importa — porque comparar constantes provaria pouco.

Detalhe que veio de graça: a prévia avisa quantos vêm **sem endereço
completo**. O pacote não sai do depósito sem rua, cidade e CEP, e é melhor
saber disso com a planilha na mão do que no dia da expedição.

### Ordenar por Score e por Envios (19/07)

Coluna de campo calculado não vira `ORDER BY`, então ordenar exigiu **armazenar**
`bonus_count` e `bonus_rating`. Isso resolve a ordenação e cria um problema
novo, que é o interessante: **o Score depende do tempo**.

Ele pondera por recência (uma avaliação de treze meses vale menos hoje do que
valia ontem) e encolhe contra a média da casa, que muda quando OUTRAS pessoas
são avaliadas. Nada disso toca os registros de um contato específico — então um
campo armazenado envelheceria calado: quem esfriou continuaria aparecendo
quente até receber outro livro, que é exatamente o que não vai acontecer.

Dois consertos, e nenhum é opcional:
- **cron diário** recalculando quem tem histórico (a base tem dezenas de
  milhares de contatos e a esmagadora maioria nunca recebeu nada);
- **`set_values` de Definições** recalcula na hora: sem isso, mudar os pontos
  na tela não mudaria nada até cada pessoa receber outro livro, e a
  configuração pareceria quebrada. "É cache" não é explicação para ninguém.

### Pivô contato × lista

Não precisou de modelo novo: o **membro da lista** já é a linha que liga os
dois. Pivô sobre ele responde "em quais listas está fulano" e "quem se repete
entre duas listas", e clicar numa célula abre exatamente aqueles vínculos — de
onde se chega à lista. Agrupa também por tipo de parceiro e por data de
entrada.

O Score centralizou de verdade quando o `text-align` foi para dentro do próprio
HTML: a classe da célula não atravessa o widget `html`.

## §10 Os menus e o pivô que demorava (19/07)

> "precisamos organizar melhor os menus. juntar relatórios. Contatos × listas
> não é um bom nome. e ele deve também abrir com as listas fechadas. tá
> demorando pra abrir."

Três coisas na mesma frase, e as três são a mesma coisa: a raiz do menu tinha
virado uma gaveta. **Análise**, **Contatos × listas** e **Contatos por lista**
moravam soltos, intercalados com as telas de trabalho (Disparos, Bonificações,
Listas) — e os dois últimos eram vizinhos com nomes quase iguais, o que é o
jeito mais barato de fazer alguém abrir o relatório errado, concluir que ele
não serve, e não voltar. Os três foram para um **Relatórios**.

O nome: "Contatos × listas" descrevia os eixos do pivô, não a pergunta que ele
responde. Virou **Sobreposição de listas** — que também é o que o distingue do
irmão "Contatos por lista" (esse conta em quantas listas cada contato está;
aquele mostra quem se repete entre duas).

**A lentidão era o desenho, não o banco.** O pivô abria com contatos nas linhas
e listas nas colunas: a tela nascia montando a matriz inteira — dezenas de
milhares de contatos × todas as listas — para mostrar de saída justamente a
visão que quase ninguém quer. Agora abre com **uma linha por lista, fechada**:
a consulta é um group by, e a expansão passa a ser escolha de quem olha. Abrir
uma lista por Contato responde "quem está nela"; abrir as colunas por Lista
responde "quem se repete entre duas". Nada se perdeu — só deixou de ser
cobrado adiantado de todo mundo que abre o menu.

**E o "Importar contatos" se perdeu no caminho** — duas vezes, o que é a parte
interessante. Ele era irmão de "Listas", não filho: um menu com filhos deixa de
abrir a própria ação, e a lista de listas sumiria. Só que sendo irmão, **a única
coisa que dizia que ele pertence às Listas era a vizinhança** — "Listas" desceu
de 30 para 20 e ele ficou parado em 35, sozinho entre Acompanhamento e
Relatórios. Recolei em 25, e ele continuou perdido: mesma linha do menu, mesmo
peso visual de "Metas" e "Disparos", nada dizendo a que ele serve.

> "vamos colocar importar contatos como uma action dentro de listas? alguma
> ideia melhor?"

**Action foi tentador e está errado, por um motivo que não é de gosto:** o menu
"Ação" do Odoo só aparece com registro selecionado. E o importador serve
justamente para os casos em que não há o que selecionar — a lista **vazia**, e
sobretudo a planilha com coluna "Lista", que cria e povoa dezenas de listas de
uma vez (as SOBs do Odoo 15 saem com 132 títulos). Pendurar o importador atrás
de uma seleção o esconderia de quem mais precisa dele. Importar para UMA lista
já tem porta em contexto, e é a certa: o botão na aba Membros.

**"Listas" virou grupo**, com o cadastro como primeiro filho — que é o padrão do
próprio Odoo (Produtos > Produtos). O receio antigo ("a lista de listas sumiria")
não se realiza: ela não some, ela vira o primeiro item. A lição geral: **item cuja
única âncora é o vizinho não tem âncora.** Ou ele está dentro do pai certo, ou
vai se perder na próxima vez que alguém mexer nas sequências.

Um detalhe de migração no caminho: tirar o `action` de um `<menuitem>` **não
limpa a coluna** numa base já instalada. O menu ficaria com a ação velha
pendurada — invisível, porque menu com filhos não abre a própria ação, mas
diferente do que uma instalação limpa produz. Zerado explicitamente com um
`<record>`, senão é o tipo de divergência que só aparece meses depois, num banco
novo, sem ninguém lembrar por quê.

### O "Registro ausente" ao adicionar contatos (19/07)

Print dele: abrir **Adicionar vários contatos** pela aba Membros da lista "A
floresta de cristal" e levar um *"Registro não existe ou foi apagado —
res.partner(2074)"*.

Não era dado corrompido: **2074 é o id da própria lista.** O assistente
semeava a seleção com `active_ids` do contexto, e `active_ids` não quer dizer
"contatos marcados" — quer dizer *"os registros da tela de onde eu vim"*. Vindo
de Contatos > Ação, são contatos e está certo. Vindo do botão da ficha da
lista, é a lista — lida ali como se fosse contato.

**O crash foi a sorte, não o problema.** A base tem dezenas de milhares de
contatos com ids esparsos; na maioria das listas o id colide com um contato que
existe, e aí o assistente abre calado com um estranho já marcado. Alguém
confirma sem reparar e o intruso entra na lista de imprensa, sem nenhum
registro de onde saiu. Por isso a guarda é pelo **modelo** (`active_model !=
'res.partner'` → não herda nada), e não um `try/except` em volta da leitura:
try/except cura o dia em que o id não existe e deixa passar o dia em que ele
existe, que é o caro.

O teste guarda os dois casos — e o segundo, o da colisão, é o que importa.

### "Adicionar vários contatos" é 'incluir lista'? (19/07)

Pergunta dele, e a resposta é não — mas a tela pedia a confusão. O assistente
serve a **duas portas opostas**:

| De onde vem | O que já está decidido | O que se escolhe |
|---|---|---|
| Contatos > filtrar > Ação | os contatos | **para qual lista** vão |
| Botão da aba Membros | **a lista** | quais contatos entram |

A tela era a mesma nas duas, com o campo **Lista** em primeiro lugar. Aberto de
dentro de "A floresta de cristal", o diálogo mostrava como item mais destacado
um *seletor de lista* — e um seletor de lista no topo de uma janela aberta
dentro de uma lista lê como **"incluir lista"**, que é outra função.

Agora, quando a lista vem decidida, ela é **título e não pergunta**, e os
contatos sobem para o lugar de honra. Vindo de Contatos, nada muda: lá escolher
a lista É a pergunta, e o campo continua sendo a primeira coisa.

**"Incluir lista"** — puxar os membros de outra lista para dentro desta — segue
não existindo, e ele sabe: os vizinhos são *Combinar em nova lista* (que cria
uma **terceira**) e o disparo, que aceita várias listas sem juntar nada. Fica
anotado como pedido em potencial, não como falta.
