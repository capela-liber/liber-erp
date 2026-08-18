# liber_olist — integração Olist/Tiny ⇆ Odoo

O Olist é um serviço pago e fechado; este módulo conversa com ele assim mesmo — e é por
essa ponte que a operação alcança marketplaces como o **Mercado Livre**. O Odoo é o
livro-razão canônico; o Olist é **um adaptador**: a venda desce de lá (pedido, canal,
cliente, nota e fatura) e o estoque da prateleira sobe daqui. Desinstalar o módulo
remove a integração e deixa o razão intacto — que é o ponto (ver `NOTES.md` §1).

Não existe conector Odoo↔Olist pronto (Apps Store, OCA, terceiros) — daí este módulo.
Arquitetura e lições de API: **`NOTES.md`**.

## Como usar

1. No Olist: *Extensões → Token API* → gerar o token da API v2.
2. No Odoo: **Olist → Configurações → Contas → novo**: nome, empresa e token.
   A empresa **precisa ter CNPJ** (`vat`) — é ele que prova que a nota é dela.
3. A conta nasce em **somente leitura**: dá para ler catálogo, saldos, pedidos e notas
   sem risco nenhum. Liberar a escrita é decisão explícita, na ficha da conta.

Uma conta por empresa: cada empresa com sua conta Olist. **Uma nota só entra se o XML
citar o CNPJ da empresa daquela conta** — um token apontado para a empresa errada não
consegue arquivar documento nela.

## O que o módulo faz

| Tela | Pergunta que responde |
|---|---|
| **Estoque** | quantos? — saldo do Olist, estoque do armazém e divergência, lado a lado; sincronizar é ação sobre linhas escolhidas |
| **Produtos** | é o mesmo livro? — a ficha do Olist espelhada e editável, com de-para manual onde o ISBN não casa |
| **Pedidos** | o que vendeu lá? — pedido com canal de venda, importável para o Odoo com fatura nascida do XML da nota |
| **Canais** | o nome de lá aponta para qual canal da casa? — descoberta automática, mapeamento humano |
| **NFes** | as notas da conta, ingeridas no painel do `liber_nfe_xml` |

Só entra **XML de NFe autorizada**; o `liber_nfe_xml` parseia, deduplica por chave de
acesso, e a nota autorizada-e-depois-cancelada é marcada pelo sync (senão o razão
superestimaria o faturamento). Os crons de leitura mantêm espelho e notas frescos; o
push de estoque tem cron próprio, **desarmado** por padrão.

## Scripts de bancada (fora do Odoo, descartáveis)

- `extract.py` — extrator read-only da API para `_dump/` (notas, XMLs, pedidos).
- `ingest.py` — carrega os XMLs de `_dump/` num banco, via odoo shell.
- `snapshot_estoque.py` — fotografa os saldos da conta (e devolve, com `--restore`).
- `conferir_estoque.py` — cruza a foto do Olist com o estoque do Odoo, por ISBN.

`_dump/` é dado fiscal real com PII: está no `.gitignore` e **não deve** ser commitado.
