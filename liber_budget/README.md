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
- Demo data, ícone e traduções `pt_BR`: pendentes (opcionais).
