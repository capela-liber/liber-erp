# SOC — o que falta

## O CFOP decide o documento (feito em 14/07/2026, falta o efeito físico)

A regra está viva e testada, e mora em três lugares — cada peça onde ela pertence:

| onde | o quê |
|---|---|
| `liber_nfe_xml/models/nfe_cfop.py` | **a regra**: `document_kind` por código de CFOP (é dono do modelo) |
| `liber_soc_moves/models/sale_order.py` | **a guarda do Pedido C**: consignação não fatura (é dono do `is_consignment`) |
| `liber_soc_fiscal_br/models/sale_order.py` | **a guarda fiscal**: bonificação e feira não são Pedido C, e não faturam |

O que ela já corrigiu: dos 3.124 pedidos migrados como consignação, só **1.797 eram
consignação**. **1.212 eram bonificação** e 64 eram feira — se o acerto rodasse assim,
cobraríamos da livraria por livros que foram **dados de presente**.

### Falta: o efeito no estoque e na contabilidade

- [ ] **Bonificação (5910/6910)**: hoje ela é um documento distinto e não fatura, mas
      ainda **não baixa o estoque**. Precisa sair do estoque **contra uma conta de
      despesa** — o livro foi dado: é despesa, nunca receita, e nunca volta.
- [ ] **Feira (5914/6914)**: precisa virar **transferência para uma localização de
      evento** (estoque nosso, em trânsito), com o **retorno pelo 1914/2914** trazendo
      de volta o que não vendeu. Hoje ela só não fatura.
- [ ] **Simples remessa (5949/6949)**: fica *indefinida* de propósito — a operação é
      ambígua por natureza e **um humano decide** o que ela é. Falta a tela onde ele
      decide (hoje só existe a lista de CFOPs em Configurações).

### Falta: uma tela

- [ ] **Frontend do CFOP → documento.** Hoje a classificação é código e a conferência é
      SQL. Deveria haver uma tela onde se vê, por CFOP: que documento ele gera, se
      fatura, se mexe na prateleira, e quantos documentos existem de cada tipo. É o
      lugar natural para o humano resolver os `5949` indefinidos.
