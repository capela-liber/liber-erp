# liber_github — notas de implantação

Corpo do GitHub sobre o chassi `liber_cloud_files` — o desenho geral
(portão, ACL por pasta, multiempresa) está no NOTES do chassi e no manual.

## Setup único (por empresa)

O token *fine-grained* **não nasce na organização** — o "Developer settings" de
uma organização só tem OAuth Apps, GitHub Apps e Publisher Verification. Ele
nasce na conta **pessoal** de alguém que é membro da organização, e é no
formulário do token que se aponta a organização como dona dos repositórios.

1. Logado com o usuário pessoal, ir direto em
   <https://github.com/settings/personal-access-tokens/new> (o caminho pelo
   menu: foto do perfil no canto superior direito → **Settings** → fim da barra
   lateral → **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**).
2. No formulário:
   - **Resource owner**: escolher a **organização**, não a conta pessoal — é o
     que faz o token alcançar os repositórios da empresa.
   - **Repository access**: *Only select repositories* → os que serão mapeados.
   - **Permissions → Repository permissions → Contents: Read and write**
     (*Metadata: Read-only* entra sozinho junto).
   - **Expiration**: anotar a data. Vencido, sync e envio param até colar um
     token novo na Conta.
3. Se a organização aparecer bloqueada, ou se o token ficar pendente, um *owner*
   precisa liberar em **Organização → Settings → Third-party Access → Personal
   access tokens**: em *Settings*, permitir o acesso via fine-grained tokens;
   em *Pending requests*, aprovar o token.
4. Preencher **GitHub → Configuração → Conta** e usar **Testar conexão**.

## Quando o envio dá 403

`Resource not accessible by personal access token` no `PUT .../contents/...`
significa token válido **sem Contents: Read and write** naquele repositório
(repositório fora da seleção do token daria 404, não 403). Corrigir a permissão
no token — e lembrar que **editar as permissões de um token cujo Resource owner
é a organização o devolve à fila**: ele volta a ler e segue recusando escrita
até um *owner* aprovar outra vez em *Pending requests*. O cabeçalho
`x-accepted-github-permissions` da resposta diz exatamente o que faltou.

## O vocabulário traduzido

- **"Pasta" é um repositório**: External ID = `owner/repositório`; o campo
  Caminho é a subpasta dentro dele (`/` sozinho = a raiz do repositório, o
  único caminho que pode terminar em barra); Branch vazio = branch padrão.
- **Enviar é commitar**: cada upload vira um commit `liber: <arquivo>` na
  branch da pasta. Nunca sobrescreve: nome repetido vira `arquivo (1).ext`.
- **Revisão é o SHA** do blob — versionamento de graça.
- **O "link compartilhado" NÃO fura o portão**: é a página do arquivo no
  GitHub, que só abre para quem enxerga o repositório. Por isso ele também
  não expira — o prazo configurado na conta é ignorado, e a ficha registra
  honestamente "sem validade".

## Limites assumidos

- **Sem miniaturas** (baixar cada imagem só para encolher não vale a banda).
- **Sem data de modificação por arquivo** no espelho (seria uma chamada de
  API por arquivo; o SHA já denuncia mudança).
- Download passa pelo Odoo (o raw do GitHub exige o token).
- Arquivos via LFS aparecem com o tamanho do ponteiro, não do conteúdo.
