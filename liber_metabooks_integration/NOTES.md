# Metabooks: mandar dados daqui para lá

O módulo sempre foi só de entrada — puxa metadados da API por ISBN ou catálogo.
Isto é a volta: editar um livro no Odoo e mandar a alteração para a Metabooks,
com checagem humana no meio.

## O ciclo

1. Alguém edita um livro. Se o campo é um que a Metabooks conhece, o livro fica
   **pendente** (`metabooks_export_pending`).
2. **Metabooks ▸ Envios ▸ Envios para a Metabooks**, criar um envio, botão
   **Buscar alterações**: traz todo livro pendente com o de/para de cada campo,
   lido do chatter.
3. Desmarcar o que não vai. **Verificar** valida ISBN, duplicidade e, para
   cadastro novo, os campos obrigatórios.
4. **Gerar planilha** produz o `.xlsx` com o nome que a Metabooks espera, já como
   anexo. **As células alteradas saem em vermelho** — o arquivo é o próprio
   documento de conferência.
5. Baixar, subir para a Metabooks, e só então **Marcar como enviada**. É isso que
   tira os livros da fila.

O envio automático **não existe ainda** (`_deliver()` está vazio de propósito).
Enquanto não temos a API, o upload é manual.

## Por que "marcar como enviada" é um passo separado

Se gerar o arquivo já limpasse a fila, um upload que falhasse perderia as
alterações em silêncio. Só quem subiu o arquivo sabe se deu certo.

## O que a documentação da Metabooks diz

Fontes em `docs/`, versionadas para não depender do site deles:

- `Metabooks_Modelo-Padrao_2025.xlsx` — 74 colunas
- `Metabooks_Modelo-Padrao_Campos-Obrigatorios_2025.xlsx` — as 19 obrigatórias
- `Orientacoes_preenchimento_planilha-Metabooks_2025-1.pdf` — preenchimento campo a campo

**Atualização é incremental.** Textualmente: *"Conteúdos e/ou campos não serão
apagados, desde que não estejam contidos na tabela de Excel."* É isso que permite
mandar só GTIN + o que mudou. Apagar de propósito exige marca explícita: `$$` em
texto, `-1` em número/preço, `11/11/1111` em data (ainda não exposto na tela).

**Nome do arquivo carrega a tarefa:** `V_<MB ID>_<AAAAMMDD>_<texto>.xlsx`.
`Z` cadastro novo, `V` alteração, `X` arquivamento, `R` reativação. A página em
português mostra um exemplo legado com `A`; o guia de 2025 corrige para `V`, e no
VLB alemão `A` significa outra coisa. Seguimos o guia de 2025.

**Formatos, do exemplo do template deles:** data como serial do Excel (44545),
autor `Sobrenome, Nome; Sobrenome, Nome`, formato como código ONIX (`BC`), NCM
pontuado (`4901.99.00`), idioma ISO-639 (`por`), BISAC `LAN025030`.

**Canal:** FTP documentado — `ftp.metabooks.com`, credenciais do portal, modo
passivo, portas 20000–20500, pasta `upload`. O usuário precisa ser liberado para
FTP pelo atendimento. Feedback deles vem por e-mail consolidado à meia-noite.

## O kit de 2024 está desatualizado

Existe em `_temp/Ferramentas_Metabooks_atualizada_2024.zip` o kit oficial que a
Metabooks distribuía em 2024. **Não use o template dele.** Comparando o
`Metabooks_Modelo-Padrao.xlsx` de 2024 com o de 2025 (baixado do site deles em
20/07/2026, em `docs/`), as colunas mudaram de nome:

| 2024 | 2025 (o que geramos) |
|---|---|
| `EAN13` | **`GTIN`** |
| `Conteúdo do thema` | `Categoria Thema` |
| `Adição de thema` | `Qualificador Thema` |
| `Sem autor`, `Formato E-book`, `Referência de produto 4 *` | — (saíram) |
| — | `Autor ISNI`, `Link de vídeo 2`, `Link de vídeo 3` (entraram) |

Como o cabeçalho é o que identifica a coluna, isso não é cosmético: uma planilha
com `EAN13` e outra com `GTIN` são arquivos diferentes para o importador deles.
Seguimos o de 2025. **Vale confirmar com o atendimento se o importador ainda
aceita os cabeçalhos de 2024** — se aceitar os dois, não há pressa; se não, quem
tiver planilha antiga em uso precisa saber.

O resto do kit continua útil e não tem equivalente no que baixamos:
`Upload_Configuração_FTP_Programa_FileZilla.pdf` (o passo a passo do FTP),
`Midias_Especificacao-Upload-FTP.pdf`, `Listas_Onix.xlsx` e o
`BISAC 2021 to Thema 1.5 Mapping.xlsx` — este último é o caminho para preencher
as duas colunas Thema, que hoje **não** mapeamos (só mandamos BISAC).

## Onde está o quê

| Arquivo | Papel |
|---|---|
| `services/metabooks_sheet.py` | As 74 colunas, o nome do arquivo, e a escrita do `.xlsx`. Sem Odoo. |
| `services/metabooks_mapping.py` | Qual campo nosso alimenta qual coluna deles. **A seam**: mexer aqui é o que faz um campo passar a ser exportado. |
| `models/metabooks_export.py` | A fila, o envio, as linhas e o log. |
| `views/metabooks_export_views.xml` | A tela. |

Mapeamos 31 das 74 colunas — as que temos de fato. As outras nunca são escritas,
então a Metabooks mantém o que já tem nelas.

## Duas armadilhas que custaram tempo

**O eco.** O conector escreve nos produtos quando importa. Sem trava, cada
importação marcaria o livro como pendente e mandaria os dados deles de volta para
eles. Daí o contexto `metabooks_from_sync` em `_upsert`.

**O marco do histórico.** A primeira versão lia o chatter a partir de um
*timestamp* (`metabooks_export_last`). Mas `mail.message.date` só tem resolução
de segundo: uma edição no mesmo segundo do envio anterior parecia mais velha que
ele, nenhum histórico era encontrado, e o fallback mandava **todas** as colunas em
vez da que mudou. Hoje o marco é `metabooks_export_last_track`, o maior id de
`mail.tracking.value` no momento do envio — exato, sem depender de relógio.
Coberto por `test_a_second_round_carries_only_the_new_change`.

## Pendente de resposta da Metabooks

`atendimentobr@mvb-online.com` / +55 11 3572 0190:

1. **A API REST tem endpoints de escrita?** A documentação é fechada ("consulte-nos").
   Se tiver, dispensa o FTP e dá resposta na hora em vez de e-mail à meia-noite.
   É a pergunta de maior valor.
2. Liberação do nosso usuário para FTP (sem isso não dá nem para testar).
3. `ftp.metabooks.com` aceita SFTP? A MVB alemã desligou FTP puro no 1º tri/2026.
4. Limite de tamanho de arquivo e de linhas — não documentado em lugar nenhum.

## Não implementado

- Envio automático (`_deliver()`).
- Marcas de exclusão (`$$`, `-1`, `11/11/1111`) na tela.
- Tarefas `X` (arquivamento) e `R` (reativação): o modelo aceita, a tela oferece,
  mas ninguém exercitou.
- Fechamento do ciclo com o e-mail de retorno deles.
