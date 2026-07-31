# -*- coding: utf-8 -*-
"""Testes da reconciliação do endereço com a localização brasileira.

O módulo lê `street_name`/`street_number`/`district` quando esses campos
existem no registry e cai nos seus próprios (`nfe_numero`/`nfe_bairro`) quando
não existem. São dois caminhos, e cada um só pode ser exercido no banco certo:

- ``TestEnderecoSemLocalizacao`` roda em banco sem `l10n_br_base`;
- ``TestEnderecoComLocalizacao`` e ``TestCepPreencheEndereco`` rodam em banco
  com `l10n_br_base`/`l10n_br_zip`.

O que sobrar pula com uma mensagem dizendo por quê -- teste que pula calado é
teste que ninguém percebe que nunca rodou.

``TestEnderecoEscolheAFonte`` não depende de banco nenhum: entra dicionário,
sai dicionário, e por isso cobre os dois caminhos de uma vez.
"""

from unittest import SkipTest
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..models.res_partner import endereco_para_nfe

# Onde o l10n_br_zip fala com a rede. É esta função que os testes trocam: de
# rede nenhum teste pode depender, e o CEP dos Correios muda quando quer.
CONSULTA_CEP = 'odoo.addons.l10n_br_zip.models.l10n_br_zip.get_address_from_cep'


def _tem_localizacao(env):
    """A localização da OCA está instalada neste banco?"""
    return 'district' in env['res.partner']._fields


@tagged('post_install', '-at_install', 'focus_nfe')
class TestEnderecoEscolheAFonte(TransactionCase):
    """A escolha da fonte de cada campo, sem ORM."""

    def test_sem_localizacao_o_numero_sai_do_fim_do_logradouro(self):
        endereco = endereco_para_nfe({
            'street': 'Rua dos Ipês, 915',
            'nfe_numero': '915',
            'nfe_bairro': 'Pinheiros',
        })
        self.assertEqual(endereco['logradouro'], 'Rua dos Ipês')
        self.assertEqual(endereco['numero'], '915')
        self.assertEqual(endereco['bairro'], 'Pinheiros')

    def test_sem_localizacao_e_sem_numero_o_logradouro_vai_inteiro(self):
        """'Rodovia Anhanguera km 12' não tem número: o km não é número."""
        endereco = endereco_para_nfe({
            'street': 'Rodovia Anhanguera km 12',
            'nfe_numero': 'S/N',
            'nfe_bairro': 'Perus',
        })
        self.assertEqual(endereco['logradouro'], 'Rodovia Anhanguera km 12')
        self.assertEqual(endereco['numero'], 'S/N')

    def test_com_localizacao_os_campos_dela_ganham(self):
        endereco = endereco_para_nfe({
            'street': 'Rua das Acácias, 100',
            'street_name': 'Rua das Acácias',
            'street_number': '100',
            'district': 'Centro',
            # Sobras de antes da localização: têm de ser ignoradas.
            'nfe_numero': '999',
            'nfe_bairro': 'Bairro Que Nao Existe',
        })
        self.assertEqual(endereco['logradouro'], 'Rua das Acácias')
        self.assertEqual(endereco['numero'], '100')
        self.assertEqual(endereco['bairro'], 'Centro')

    def test_virgula_do_street_split_nao_vai_para_a_nota(self):
        """O `street_split` do core devolve "Rua X," com a vírgula grudada."""
        endereco = endereco_para_nfe({
            'street': 'Rua das Acácias, 100',
            'street_name': 'Rua das Acácias,',
            'street_number': '100',
        })
        self.assertEqual(endereco['logradouro'], 'Rua das Acácias')

    def test_localizacao_sem_numero_cai_no_campo_proprio(self):
        """O CEP preenche logradouro e bairro, nunca o número."""
        endereco = endereco_para_nfe({
            'street': 'Avenida Paulista,',
            'street_name': 'Avenida Paulista',
            'street_number': False,
            'district': 'Bela Vista',
            'nfe_numero': '1578',
        })
        self.assertEqual(endereco['logradouro'], 'Avenida Paulista')
        self.assertEqual(endereco['numero'], '1578')

    def test_endereco_vazio_ainda_devolve_sem_numero(self):
        """Caso de borda: nada preenchido. 'S/N' é o que a SEFAZ espera."""
        endereco = endereco_para_nfe({})
        self.assertEqual(endereco['logradouro'], '')
        self.assertEqual(endereco['numero'], 'S/N')
        self.assertEqual(endereco['bairro'], '')
        self.assertEqual(endereco['inscricao_estadual'], '')

    def test_inscricao_estadual_do_modulo_ganha_da_localizacao(self):
        """A IE inverte a ordem: o campo deste módulo continua na tela."""
        endereco = endereco_para_nfe({
            'nfe_inscricao_estadual': '111222333444',
            'l10n_br_ie_code': '111222333444',
        })
        self.assertEqual(endereco['inscricao_estadual'], '111222333444')

    def test_inscricao_estadual_da_localizacao_serve_de_reserva(self):
        endereco = endereco_para_nfe({
            'nfe_inscricao_estadual': False,
            'l10n_br_ie_code': '111222333444',
        })
        self.assertEqual(endereco['inscricao_estadual'], '111222333444')


@tagged('post_install', '-at_install', 'focus_nfe')
class TestEnderecoSemLocalizacao(TransactionCase):
    """O caminho de quem só instalou este módulo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _tem_localizacao(cls.env):
            raise SkipTest(
                "l10n_br_base instalado: este banco exerce o outro caminho")

    def test_parceiro_usa_os_campos_do_modulo(self):
        parceiro = self.env['res.partner'].create({
            'name': 'Livraria Exemplo',
            'street': 'Rua dos Ipês, 915',
            'nfe_bairro': 'Pinheiros',
            'city': 'São Paulo',
        })
        endereco = parceiro._nfe_endereco()
        self.assertEqual(endereco['logradouro'], 'Rua dos Ipês')
        self.assertEqual(endereco['numero'], '915')
        self.assertEqual(endereco['bairro'], 'Pinheiros')
        self.assertEqual(endereco['municipio'], 'São Paulo')

    def test_destinatario_leva_o_endereco_resolvido(self):
        parceiro = self.env['res.partner'].create({
            'name': 'Livraria Exemplo',
            'vat': '98765432000198',
            'street': 'Rua dos Ipês, 915',
            'nfe_bairro': 'Pinheiros',
            'city': 'São Paulo',
            'nfe_inscricao_estadual': '111222333444',
        })
        dados = parceiro._focus_destinatario_data()
        self.assertEqual(dados['numero'], '915')
        self.assertEqual(dados['bairro'], 'Pinheiros')
        self.assertEqual(dados['inscricao_estadual'], '111222333444')


@tagged('post_install', '-at_install', 'focus_nfe')
class TestEnderecoComLocalizacao(TransactionCase):
    """O caminho de quem instalou a localização da OCA por cima."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not _tem_localizacao(cls.env):
            raise SkipTest("l10n_br_base não instalado neste banco")

    def test_numero_e_bairro_da_localizacao_ganham_dos_campos_do_modulo(self):
        parceiro = self.env['res.partner'].create({
            'name': 'Livraria Exemplo',
            'street_name': 'Rua dos Ipês',
            'street_number': '915',
            'district': 'Pinheiros',
            'city': 'São Paulo',
            # Sobra de antes de instalar a localização.
            'nfe_numero': '999',
            'nfe_bairro': 'Bairro Que Nao Existe',
        })
        endereco = parceiro._nfe_endereco()
        self.assertEqual(endereco['logradouro'], 'Rua dos Ipês')
        self.assertEqual(endereco['numero'], '915')
        self.assertEqual(endereco['bairro'], 'Pinheiros')

    def test_municipio_sai_do_city_id_quando_o_texto_esta_vazio(self):
        """O `city` só acompanha o `city_id` por onchange, que não roda em create."""
        cidade = self.env['res.city'].search(
            [('name', '=', 'São Paulo'), ('state_id.code', '=', 'SP')], limit=1)
        self.assertTrue(cidade, "res.city de São Paulo deveria vir com l10n_br_base")
        parceiro = self.env['res.partner'].create({
            'name': 'Livraria Exemplo',
            'street_name': 'Rua dos Ipês',
            'street_number': '915',
            'city_id': cidade.id,
        })
        self.assertFalse(parceiro.city)
        self.assertEqual(parceiro._nfe_endereco()['municipio'], 'São Paulo')

    def test_ie_da_localizacao_entra_quando_a_do_modulo_esta_vazia(self):
        parceiro = self.env['res.partner'].create({
            'name': 'Livraria Exemplo',
            'is_company': True,
            'state_id': self.env.ref('base.state_br_sp').id,
            'l10n_br_ie_code': '111222333444',
        })
        self.assertEqual(
            parceiro._focus_destinatario_data()['inscricao_estadual'],
            '111222333444')


@tagged('post_install', '-at_install', 'focus_nfe')
class TestCepPreencheEndereco(TransactionCase):
    """O CEP preenchendo o endereço, com a consulta externa trocada por mock."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'l10n_br.zip' not in cls.env:
            raise SkipTest("l10n_br_zip não instalado neste banco")

    def setUp(self):
        super().setUp()
        # Nada de dados de demonstração: o parceiro nasce aqui.
        self.parceiro = self.env['res.partner'].create({
            'name': 'Livraria Exemplo',
            'country_id': self.env.ref('base.br').id,
            'zip': '01310-100',
        })

    def _resposta(self, **kw):
        """O que o brazilcep devolve para um CEP que existe."""
        dados = {
            'district': 'Bela Vista',
            'cep': '01310100',
            'city': 'São Paulo',
            'street': 'Avenida Paulista',
            'uf': 'SP',
            'complement': '',
        }
        dados.update(kw)
        return dados

    def test_cep_preenche_logradouro_bairro_cidade_e_uf(self):
        with patch(CONSULTA_CEP, return_value=self._resposta()) as consulta:
            self.assertTrue(self.parceiro.zip_search())

        consulta.assert_called_once()
        self.assertEqual(self.parceiro.street_name, 'Avenida Paulista')
        self.assertEqual(self.parceiro.district, 'Bela Vista')
        self.assertEqual(self.parceiro.city_id.name, 'São Paulo')
        self.assertEqual(self.parceiro.state_id.code, 'SP')

    def test_o_numero_continua_sendo_trabalho_humano(self):
        """Nenhuma API de CEP sabe o número. A nota sai 'S/N' até alguém digitar."""
        with patch(CONSULTA_CEP, return_value=self._resposta()):
            self.parceiro.zip_search()

        endereco = self.parceiro._nfe_endereco()
        self.assertEqual(endereco['logradouro'], 'Avenida Paulista')
        self.assertEqual(endereco['bairro'], 'Bela Vista')
        self.assertEqual(endereco['numero'], 'S/N')

        self.parceiro.street_number = '1578'
        self.assertEqual(self.parceiro._nfe_endereco()['numero'], '1578')

    def test_cep_de_logradouro_com_numero_separa_os_dois(self):
        """Alguns CEPs vêm "Avenida Paulista, 509": o número é de quadra, não do prédio."""
        with patch(CONSULTA_CEP,
                   return_value=self._resposta(street='Avenida Paulista, 509')):
            self.parceiro.zip_search()

        self.assertEqual(self.parceiro.street_name, 'Avenida Paulista')
        self.assertEqual(self.parceiro.street_number, '509')

    def test_cep_ja_conhecido_nao_bate_na_api(self):
        """A segunda busca do mesmo CEP sai da tabela local."""
        with patch(CONSULTA_CEP, return_value=self._resposta()):
            self.parceiro.zip_search()

        outro = self.env['res.partner'].create({
            'name': 'Outra Livraria',
            'country_id': self.env.ref('base.br').id,
            'zip': '01310-100',
        })
        with patch(CONSULTA_CEP) as consulta:
            outro.zip_search()

        consulta.assert_not_called()
        self.assertEqual(outro.district, 'Bela Vista')

    def test_cep_inexistente_nao_preenche_nada(self):
        """Resposta vazia: o endereço fica como estava, sem inventar."""
        vazio = dict.fromkeys(
            ('district', 'cep', 'city', 'street', 'uf', 'complement'), '')
        with patch(CONSULTA_CEP, return_value=vazio):
            self.assertFalse(self.parceiro.zip_search())

        self.assertFalse(self.parceiro.street_name)
        self.assertFalse(self.parceiro.district)

    def test_api_fora_do_ar_vira_erro_legivel(self):
        with patch(CONSULTA_CEP, side_effect=ConnectionError('timeout')):
            with self.assertRaises(UserError):
                self.parceiro.zip_search()
