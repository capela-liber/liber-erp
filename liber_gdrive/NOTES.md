# liber_gdrive — notas de implantação

Corpo do Google Drive sobre o chassi `liber_cloud_files` — o desenho geral
(portão, ACL por pasta, share com prazo, multiempresa) está no NOTES do
chassi e no manual do site.

## Setup único (por empresa)

1. **Criar o projeto** em https://console.cloud.google.com — ativar a
   *Google Drive API* e criar uma credencial *OAuth client ID* (tipo
   Desktop app). Guardar Client ID e Client Secret.
2. **Autorizar e obter o refresh token** (logado na conta Google da empresa):
   - No navegador:
     `https://accounts.google.com/o/oauth2/v2/auth?client_id=CLIENT_ID&redirect_uri=urn:ietf:wg:oauth:2.0:oob&response_type=code&scope=https://www.googleapis.com/auth/drive&access_type=offline&prompt=consent`
   - Com o código exibido:
     ```sh
     curl https://oauth2.googleapis.com/token \
          -d code=CODIGO -d grant_type=authorization_code \
          -d client_id=CLIENT_ID -d client_secret=CLIENT_SECRET \
          -d redirect_uri=urn:ietf:wg:oauth:2.0:oob
     ```
   - Guardar o `refresh_token` da resposta.
3. Preencher **Drive → Configuração → Conta** e usar **Testar conexão**.

## Peculiaridades assumidas

- **Pasta é ID, não caminho**: abra a pasta no navegador e copie o ID da
  URL (`drive.google.com/drive/folders/<ID>`) para o campo External ID.
- **Download passa pelo Odoo** (o Drive não tem link anônimo de 4h como o
  Dropbox); o portão é conferido antes de cada byte.
- **Miniaturas de graça**, inclusive de PDF — melhor que o Dropbox aqui.
- **Expiração de link** exige Google Workspace pago; a recusa sai explicada.
- O upload nunca sobrescreve: nome repetido vira `arquivo (1).ext`.
