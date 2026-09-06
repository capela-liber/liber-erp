-- Uma base neutralizada não emite nota de verdade.
--
-- O `odoo neutralize` do core desliga cron e e-mail, mas não sabe o que é uma
-- NFe: o ambiente da emissão é campo nosso, e viaja no dump. Em 27/08/2026 o
-- dev acordou de um clone do prod com `producao` em três das seis empresas, e
-- o token de produção preenchido -- crons desligados, mas um clique em
-- "Emitir NFe" na tela teria emitido nota válida na SEFAZ. Ver o mesmo
-- acidente, do lado do staging, em TESTING.md.
--
-- O token não se apaga: trocar de ambiente é mudar UM campo, e quem restaurar
-- este banco para virar produção de novo não deveria ter de recolar
-- credencial. Quem decide a emissão é o ambiente.
UPDATE res_company
   SET focus_ambiente = 'homologacao'
 WHERE focus_ambiente IS DISTINCT FROM 'homologacao';
