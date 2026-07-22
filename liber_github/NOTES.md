# liber_github — notas de implantação

Corpo do GitHub sobre o chassi `liber_cloud_files` — o desenho geral
(portão, ACL por pasta, multiempresa) está no NOTES do chassi e no manual.

## Setup único (por empresa)

1. Na conta GitHub da empresa: **Settings → Developer settings →
   Fine-grained personal access tokens** → gerar um token com acesso aos
   repositórios que serão mapeados e permissão **Contents: Read and write**.
2. Preencher **GitHub → Configuração → Conta** e usar **Testar conexão**.

## O vocabulário traduzido

- **"Pasta" é um repositório**: External ID = `owner/repositório`; o campo
  Caminho é a subpasta dentro dele (`/` = raiz); Branch vazio = branch padrão.
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
