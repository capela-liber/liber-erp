# Liber ERP

Módulos [Odoo 19 Community](https://github.com/odoo/odoo) para editoras: contratos de
direito autoral, consignação (SOC), documentos fiscais a partir do XML da NF-e,
bonificação e integração com a Metabooks.

Nasceram da operação de uma editora brasileira e são publicados aqui na esperança de
que sirvam a outras. Não há versão paga, plano de suporte nem roadmap comercial.

## Estado

Em desenvolvimento ativo contra Odoo 19. Alguns módulos rodam em produção, outros são
ensaio. Leia o `NOTES.md` de cada pasta antes de confiar nele — é lá que estão as
ressalvas honestas sobre o que ainda não está pronto.

## Módulos

### Direito autoral

| Módulo | O que faz |
|---|---|
| `liber_copyright_contracts` | Contratos, beneficiários, obras e royalties por faixa |
| `liber_copyright_contracts_analytics` | Contas analíticas e acompanhamento de pagamento |
| `liber_copyright_contracts_payments` | Gera contas a pagar para quitar royalties em aberto |
| `liber_copyright_contracts_reports` | Extrato de royalties enviado ao autor (PDF + e-mail) |
| `liber_copyright_contracts_taxes` | Retenção de IRRF sobre o pagamento de royalties |

### Consignação (SOC)

| Módulo | O que faz |
|---|---|
| `liber_soc_agreements` | Núcleo: acordos e o mapa da estante do cliente |
| `liber_soc_moves` | Remessa, reposição, devolução e renovação simbólica |
| `liber_soc_settlement` | Acerto: transforma o que o cliente vendeu em venda real |
| `liber_soc_fiscal_br` | Valoriza o consignado em conta de ativo própria |
| `liber_soc_audit` | Reconstrói o saldo esperado a partir dos XMLs e concilia com o mapa |

### Fiscal, catálogo e outros

| Módulo | O que faz |
|---|---|
| `liber_nfe_xml` | Painel de NF-e a partir do XML importado (**não emite** — só importa) |
| `liber_nfe_remessa` | Documentos fiscais que não geram cobrança (simples remessa) |
| `liber_metabooks_integration` | Metadados de livros via Metabooks/MVB, exportação ONIX |
| `liber_product_bonus` | Exemplares de cortesia com cota, histórico e devolução |
| `liber_budget` | Orçamentos sobre a contabilidade analítica, sem Enterprise |
| `liber_site` | Site de apresentação servido em `/liber` |
| `liber_roles` | Perfis por função da casa, e a conta `visitante` que vê tudo sem gravar |

## Instalação

```sh
git clone https://github.com/capela-liber/liber-erp.git
odoo-bin --addons-path=/caminho/do/odoo/addons,/caminho/do/liber-erp -d suabase -i liber_copyright_contracts
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
