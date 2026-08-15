# Lab Budget (Open)

Orçamentos abertos (**AGPL-3**) para Odoo 19 Community, construídos sobre a
Contabilidade Analítica do core — **sem depender de módulos Enterprise**
(`accountant`, `account_reports`, `account_budget`).

## Recursos

- **Orçamentos** (`budget.analytic`): máquina de estados
  (draft → open → revised → done/canceled), **revisões** vinculadas, **Group** e
  **Tags** para organizar, `mail.thread` (tracking).
- **Linhas** (`budget.line`) com dois modos de realizado, por linha:
  - **Posição Orçamentária (GL)** — soma direto do Razão (`account.move.line`).
    Funciona **retroativo**, sem preparo (estilo Odoo 15).
  - **Analítico** — soma de `account.analytic.line` (estilo Odoo 17+).
- **Medidas:** **Planned**, **Theoretical** (rateio por dias decorridos),
  **Programmed** (draft + posted) e **Practical** (só posted).
- **Sinal P&L:** receita **+**, despesa **−**, total = resultado líquido (bate com o Razão).
- **UX:** reordenar por arrastar, **cores** Planned×Practical (vermelho abaixo / azul
  acima), **drill-down** por linha para os Journal/Analytic Items.
- **Análise** (`budget.report`): view SQL com **pivot / graph / list** em
  *Budgets → Reporting*.
- **Demonstrativo de Resultado** (`budget.pnl.report`): view SQL sobre o Razão,
  em *Budgets → Reporting → Profit & Loss*. O Community traz o motor
  `account.report` mas nenhum demonstrativo montado nem tela — este preenche a
  lacuna pelo caminho barato: **pivot nativo**, com exportação e drill-down de graça.
  - **Linhas pelo tipo de conta do próprio Odoo**, com os rótulos do core:
    *Income*, *Other Income*, *Cost of Revenue*, *Expenses*, *Other Expenses*,
    *Depreciation* — e as três filtragens de sempre (Receita / Custo / Despesa)
    recortando esses seis. Nenhuma nomenclatura nova da casa.
  - O valor guardado leva **prefixo de ordenação** (`1_income`, não `income`):
    o pivot ordena os grupos pela coluna do `GROUP BY`, e sem isso `expense`
    viria antes de `income` e o demonstrativo abriria invertido. Consequência
    prática: para filtrar por tipo use as filtragens da tela, não o valor cru
    num domínio escrito à mão.
  - **Desdobramento pelo plano de contas**: o campo *Account Group* resolve o
    prefixo do código (`account.group`) em SQL, porque `account_account.group_id`
    é compute sem store. Fica vazio enquanto não houver grupos configurados.
  - **Colunas por período**: mês/trimestre/ano pelo próprio pivot; abre no ano
    corrente e só com lançamentos *posted*.
  - Mesmo sinal do resto do módulo: total geral **é** o resultado do período.
- **Configuração:** Budgetary Positions, Budget Groups, Budget Tags (menus próprios).

## Dependências
`analytic`, `account` (core Community).

## Segurança
Grupos **Budget: User** / **Budget: Manager**; record rules multiempresa.

## Testes
`TransactionCase` cobrindo estados, revisão, Teórico, Practical/Programmed (GL e
analítico, sinal P&L) e o `budget.report`.
```bash
odoo -d <db> -u liber_budget --test-enable --test-tags /liber_budget --stop-after-init
```

## Licença
AGPL-3.

## Limitações / roadmap
- Casamento analítico hoje usa o **plano principal** (`account_id`); multi-plano é evolução.
- O P&L é **só realizado**. Não tem coluna *Previsto* porque a chave não casa: o
  realizado é por conta do Razão e o orçado é por Posição Orçamentária (1:N) ou
  conta analítica — o previsto não se reparte entre as contas da posição. Se um
  dia for preciso, o lugar é uma coluna no nível da posição, não da conta.
- Pivot só soma: não há linha calculada (*Lucro Bruto*, *Resultado Operacional*).
  Isso pede uma tela própria, dobrável.
- Demo data, ícone e traduções `pt_BR`: pendentes (opcionais).
