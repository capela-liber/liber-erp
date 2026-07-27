# -*- coding: utf-8 -*-
"""A regra que uma máquina confere: nenhuma ferramenta escreve como superusuário.

O guarda em `ir.model.access.check` deixa `sudo()` passar, e isso é deliberado
-- sem essa brecha o Odoo não conseguiria gravar a sequência e o chatter ao
criar um documento. O preço é que a promessa "o agente nunca faz mais do que a
pessoa poderia fazer" deixa de ser garantida pelo ORM dentro do código de
ferramenta, e passa a depender de quem revisa.

Este teste move essa dependência de volta para a máquina. Ele é grosseiro de
propósito: procura o texto `.sudo(` nos arquivos de ferramenta e falha. Não
entende o código, não julga a intenção, não abre exceção para o caso legítimo
-- porque no diretório `tools/` não existe caso legítimo, e uma regra sem
exceção é uma regra que ninguém precisa interpretar às onze da noite.

`models/` fica de fora, e ali sudo aparece por bons motivos: gravar o estado de
um plano que falhou, carimbar o resultado numa linha imutável, ler os grupos de
um usuário. São escritas do próprio módulo sobre os próprios registros dele,
não ações do agente sobre dados de negócio.
"""

import os

from odoo.tests.common import TransactionCase, tagged

FORBIDDEN = '.sudo('
TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools')


@tagged('post_install', '-at_install')
class TestNoSudoInTools(TransactionCase):

    def test_nenhuma_ferramenta_usa_sudo(self):
        ofensores = []
        for filename in sorted(os.listdir(TOOLS_DIR)):
            if not filename.endswith('.py'):
                continue
            caminho = os.path.join(TOOLS_DIR, filename)
            with open(caminho, encoding='utf-8') as handle:
                for numero, linha in enumerate(handle, start=1):
                    # O docstring deste próprio módulo cita o texto proibido;
                    # nos arquivos de ferramenta, comentários também contam --
                    # é mais simples explicar a regra do que explicar a exceção.
                    if FORBIDDEN in linha:
                        ofensores.append(f'{filename}:{numero}: {linha.strip()}')

        self.assertFalse(ofensores, (
            "Ferramenta usando sudo(). O agente herda os limites de quem pediu "
            "justamente por rodar como essa pessoa; sudo desfaz isso em "
            "silêncio, e o ORM não vai reclamar. Se a operação realmente exige "
            "privilégio, ela não é uma ferramenta -- é código de módulo, e mora "
            "em models/.\n" + '\n'.join(ofensores)
        ))

    def test_o_diretorio_de_ferramentas_existe(self):
        """Se alguém mover `tools/`, este teste passa a testar o vazio."""
        self.assertTrue(os.path.isdir(TOOLS_DIR))
        arquivos = [f for f in os.listdir(TOOLS_DIR) if f.endswith('.py')]
        self.assertGreater(len(arquivos), 1, "Esperava encontrar ferramentas em tools/.")
