# Liber ERP

Módulos [Odoo 19 Community](https://github.com/odoo/odoo) para editoras: consignação
(SOC), direitos autorais, feiras, emissão de NF-e e documentos fiscais a partir do
XML, marketplaces (Olist, Amazon Vendor), painéis de vendas e recebíveis, atendimento
comercial, estoque endereçado, arquivos na nuvem — e os manuais e cursos que explicam tudo isso.

Nasceram da operação de uma editora brasileira e são publicados aqui na esperança de
que sirvam a outras. Não há versão paga, plano de suporte nem roadmap comercial —
veja `SUPPORT.md` para onde perguntar.

## Ver funcionando

A vitrine em **[liber.edlab.press](https://liber.edlab.press)** roda estes 52 módulos
com dados de demonstração. O menu **Demo** explica como entrar com a conta de
demonstração, que vê tudo e **não grava nada**. Lá dentro:

- o app **Manual**, com o manual de cada módulo (também publicados em
  [liber.edlab.press/liber/docs/](https://liber.edlab.press/liber/docs/));
- o tile **Treinamento**, com os cursos em vídeo, tema por tema, em
  [/slides](https://liber.edlab.press/slides).

## Estado

Em desenvolvimento ativo contra Odoo 19, em produção na editora de origem. Onde a
pasta traz um `NOTES.md`, leia-o antes de confiar no módulo — é lá que estão as
ressalvas honestas sobre o que ainda não está pronto.

O que muda a cada publicação está nas
[issues com a etiqueta `changelog`](https://github.com/capela-liber/liber-erp/issues?q=label%3Achangelog):
uma issue por frente e uma "visão geral" por período.

## Módulos

### Consignação (SOC)

| Módulo | O que faz |
|---|---|
| `liber_soc_agreements` | Núcleo: acordos e o mapa da estante do cliente |
| `liber_soc_moves` | Remessa, reposição, devolução e renovação simbólica |
| `liber_soc_settlement` | Acerto: transforma o que o cliente vendeu em venda real; o mapa mensal sai sozinho |
| `liber_soc_fiscal_br` | Valoriza o consignado em conta de ativo própria; a nota de remessa do Pedido C |
| `liber_soc_audit` | Reconstrói o saldo esperado a partir dos XMLs e concilia com o mapa |

### Direitos autorais

| Módulo | O que faz |
|---|---|
| `liber_copyright_contracts` | Contratos, beneficiários, obras e royalties por faixa |
| `liber_copyright_contracts_analytics` | Contas analíticas e apuração dos royalties sobre as vendas |
| `liber_copyright_contracts_payments` | Gera contas a pagar para quitar royalties em aberto |
| `liber_copyright_contracts_reports` | Prestação de contas enviada ao autor (PDF + e-mail) |
| `liber_copyright_contracts_taxes` | Retenção de IRRF sobre o pagamento de royalties |
| `liber_copyright_contracts_intercompany` | Cobra da empresa irmã os royalties apurados sobre as vendas dela |
| `liber_copyright_contracts_cloud` | O contrato aponta para os seus documentos no Dropbox, Drive ou GitHub |

### Feiras

Uma feira não é venda: é remessa temporária. O estoque sai, vende em parte na praça
e volta incompleto — e o que não volta ganha nome.

| Módulo | O que faz |
|---|---|
| `liber_fairs` | O evento: grade, carga, chegada, conferência e retorno |
| `liber_fairs_pos` | Um caixa de Ponto de Venda por feira, vendendo o estoque que está na mesa |
| `liber_fairs_nfe` | A carga sai com nota: remessa para exposição ou feira, emitida para nós mesmos |
| `liber_fairs_metabooks` | Monta a grade da feira pelos campos do catálogo (assunto Thema, data de publicação) |

### Fiscal

| Módulo | O que faz |
|---|---|
| `liber_nfe_xml` | Painel de NF-e a partir do XML importado (**não emite** — só importa) |
| `liber_nfe_focus` | Emissão de NF-e modelo 55 pela API da FocusNFe, a partir da fatura |
| `liber_nfe_remessa` | Documentos fiscais que não geram cobrança (simples remessa) |
| `liber_nfe_picking` | A logística vê a DANFE no próprio movimento, sem abrir o Faturamento |
| `liber_in_payment` | O estado "Em pagamento" da fatura, que só o Enterprise tinha |

### Vendas, marketplaces e cadastro

| Módulo | O que faz |
|---|---|
| `liber_olist` | Pedidos e notas do Olist/Tiny: espelho dos pedidos, fila de despacho, XMLs para o painel |
| `liber_amazon_vendor` | Pedidos do Amazon Vendor Central viram cotação com o preço da casa (só leitura na Amazon) |
| `liber_partner_commercial` | Canal de vendas no cadastro do cliente, grade de canais e desconto visível |
| `liber_partner_group` | O grupo comercial (rede) acima da filial: um eixo de agrupamento para relatórios |
| `liber_transport` | A transportadora do cliente chega ao movimento, e a coleta sai por e-mail |
| `liber_print_quote` | A ficha técnica do livro viaja no pedido de cotação à gráfica |
| `liber_metabrasil` | Impressão sob demanda pela MetaBrasil: envia o pedido e o acompanha |
| `liber_metabooks_integration` | Metadados de livros via Metabooks/MVB, exportação ONIX |

### Financeiro e painéis

| Módulo | O que faz |
|---|---|
| `liber_budget` | Orçamentos sobre a contabilidade analítica, sem Enterprise; impressão em PDF |
| `liber_aged_receivable` | A receber por cliente e faixa de idade, com salto ao documento e à conciliação |
| `liber_aged_payable` | A pagar por fornecedor e faixa de idade, idem |
| `liber_receivables_dashboard` | Foto mensal da carteira de recebíveis por faixa |
| `liber_sales_dashboard` | O painel de Vendas lê dois relógios: o pedido e a nota fiscal |
| `liber_dashboard_top` | Gráfico com limite de grupos: o Top que não estoura a tela |
| `liber_geo_brasil` | Região "Brasil (UF)" nos gráficos geo, e vendas por UF |
| `liber_account_group_panel` | Plano de contas filtrado por grupo de contas |
| `liber_intercompany_mirror` | Ver e abrir o documento espelho criado na empresa irmã |
| `liber_base_import_br` | Planilhas com `59,90` e `05/03/2026` importam como estão escritas |

### Estoque endereçado

| Módulo | O que faz |
|---|---|
| `liber_stock_shelves` | A prateleira volta à tela, e o livro passa a poder mudar de prateleira |
| `liber_stock_scan` | Bipe a prateleira, bipe os livros, bipe a prateleira nova: a transferência interna nasce validada |
| `liber_stock_count` | A contagem física é de quem está no depósito; mudar a quantidade em mãos é do administrador do Inventário |

### Atendimento

| Módulo | O que faz |
|---|---|
| `liber_support` | Atendimento comercial: e-mail que vira chamado, triagem em kanban, SLA, vínculo com o pedido |
| `liber_support_soc` | Liga o chamado à CO de consignação e responde com o mapa; importa a venda digital (Bookwire) |

### Arquivos na nuvem

O chassi e as três estantes: a conta é por empresa e por provedor, as pastas
são do administrador, e o Odoo é o porteiro de quem baixa o quê.

| Módulo | O que faz |
|---|---|
| `liber_cloud_files` | O chassi sob Dropbox, Drive e GitHub: conta, pasta, ACL e vínculo |
| `liber_dropbox` | A estante do Dropbox sobre o chassi |
| `liber_gdrive` | A estante do Google Drive sobre o chassi |
| `liber_github` | A estante do GitHub: repositório vira pasta, envio vira commit |

### Manuais, treinamento, papéis e site

| Módulo | O que faz |
|---|---|
| `liber_knowledge` | O app Manual: os manuais do Liber dentro do Odoo, num wiki editável (sobre o `document_page` da OCA) |
| `liber_training` | O tile Treinamento, que leva todo usuário aos cursos em vídeo |
| `liber_roles` | Perfis por função da casa, e o Visitante, que vê tudo sem gravar |
| `liber_site` | Site de apresentação servido em `/liber`, com os manuais em `/liber/docs/` |

Cada módulo traz o próprio manual na tela **Aplicativos → Module Info** do Odoo,
no app **Manual** e no site.

## Dependências

Além do Odoo 19 Community, quatro módulos pedem código da
[OCA](https://github.com/OCA), que não está neste repositório:

| Módulo da OCA | Repositório | Quem usa |
|---|---|---|
| `account_reconcile_oca` | OCA/account-reconcile | `liber_aged_receivable` |
| `account_invoice_inter_company` | OCA/multi-company | `liber_intercompany_mirror` |
| `document_page`, `document_page_access_group` | OCA/knowledge | `liber_knowledge` |

## Instalação

```sh
git clone https://github.com/capela-liber/liber-erp.git
odoo-bin --addons-path=/caminho/do/odoo/addons,/caminho/da/oca,/caminho/do/liber-erp \
         -d suabase -i liber_soc_settlement,liber_copyright_contracts
```

Os módulos declaram suas dependências entre si; instalar o de cima puxa os de baixo.

## Licença

Todo o repositório é **AGPL-3** — veja `LICENSE`. Copyright © EdLab Press.

Uma atribuição de terceiro é preservada: a geração do DANFE em
`liber_nfe_xml/report/` se apoia na biblioteca `pytrustnfe`, de Danimar Ribeiro
(Trustcode), e mantém o cabeçalho de crédito original — também AGPL-3.

## Contribuindo

Issues e pull requests são bem-vindos. Duas regras práticas:

- **Nunca commite dados reais.** Nem XML de NF-e de produção, nem planilha de cliente,
  nem certificado A1/A3. Os dados de demonstração usam CPF/CNPJ sintéticos e
  `example.com`. O `.gitignore` cobre os caminhos conhecidos, mas ele é a segunda
  linha de defesa, não a primeira.
- **Credenciais vêm de `ir.config_parameter` ou variável de ambiente**, nunca do
  código.
