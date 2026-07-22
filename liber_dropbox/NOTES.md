# liber_dropbox — notas de implantação

## O desenho em uma frase

O Dropbox é a estante, o Odoo é o porteiro: o token é um só (a conta da
editora), ninguém recebe credencial do Dropbox, e quem lê ou grava cada pasta
é decidido pasta a pasta dentro do Odoo (record rules + checagem explícita em
todo método que toca a API).

Dois poderes deliberadamente separados: **mapear pastas** (criar/alterar/
excluir mapeamentos) é só de administrador do sistema (`base.group_system`);
**escrever no Dropbox** (enviar, compartilhar) exige grupo de escrita na
pasta, mesmo para gerentes e administradores. O gerente do módulo vê tudo,
cura tags e credenciais — mas não configura a estante nem escreve sem ACL.

## Setup único (uma vez por instância)

1. **Criar o app** em https://www.dropbox.com/developers/apps
   — *Scoped access*; *Full Dropbox* ou *App folder* (App folder confina tudo
   a `/Aplicativos/<nome>` e é o mais seguro para começar).
2. **Permissions** (aba Permissions do app, salvar antes de gerar o token):
   `account_info.read`, `files.metadata.read`, `files.content.read`,
   `files.content.write`, `sharing.read`, `sharing.write`.
3. **Autorizar e obter o refresh token** (fluxo offline, um único uso):
   - No navegador, logado na conta da editora:
     `https://www.dropbox.com/oauth2/authorize?client_id=APP_KEY&response_type=code&token_access_type=offline`
   - Com o código exibido:
     ```sh
     curl https://api.dropboxapi.com/oauth2/token \
          -d code=CODIGO -d grant_type=authorization_code \
          -u APP_KEY:APP_SECRET
     ```
   - Guardar o `refresh_token` da resposta (não expira; o access token é
     derivado dele a cada operação e nunca é armazenado).
4. Preencher **Settings → Dropbox** (App Key, App Secret, Refresh Token) e
   usar **Test Connection**.

## Limites assumidos (fase 0)

- **Espelho é só metadado**: nome, tamanho, rev, hash. Nenhum byte entra no
  Odoo; download sai por link temporário que o Dropbox expira em 4 horas.
- **Link compartilhado fura o portão** — é a natureza dele. Por isso criar o
  link exige ACL de escrita, pede confirmação, assina quem pediu
  (`shared_by`, `shared_on`) e **nasce com prazo**: padrão 30 dias
  (Settings → Dropbox → Link Expiration; 0 = sem prazo). Compartilhar de
  novo renova o prazo. Atenção: o Dropbox só honra expiração de link em
  plano pago (Plus/Professional/Business); em conta gratuita a API recusa
  e o erro sai explicado. Revogação manual/senha do link: fase 1.
- **Sync é manual** (botão na pasta). Cron e webhook do Dropbox: fase 1.
- **Subpastas**: por padrão cada pasta mapeada é um nível; a flag
  "Incluir subpastas" espelha a árvore toda sob a ACL da pasta-mãe.
  Subpasta mapeada à parte é **pulada** pelo sync recursivo — a ACL
  própria dela (em geral mais estrita) continua mandando.
- Upload nunca sobrescreve em silêncio (`autorename`); conflito vira
  `arquivo (1).ext`, visível no próximo sync.
