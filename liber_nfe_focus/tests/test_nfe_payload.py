# -*- coding: utf-8 -*-
"""Testes da regra fiscal. Sem banco: entra dicionário, sai dicionário."""

from odoo.tests import TransactionCase, tagged

from ..models import nfe_payload


@tagged('post_install', '-at_install', 'focus_nfe')
class TestNfePayload(TransactionCase):
    """A montagem do JSON não toca no ORM, mas roda no runner do Odoo para
    entrar na mesma suíte que o resto do módulo."""

    def _emitente(self, **kw):
        dados = {
            'cnpj': '12.345.678/0001-95',
            'nome': 'EdLab Press',
            'inscricao_estadual': '111.222.333.444',
            'regime_tributario': nfe_payload.CRT_NORMAL,
            'logradouro': 'Rua das Acácias',
            'numero': '100',
            'bairro': 'Centro',
            'municipio': 'São Paulo',
            'uf': 'SP',
            'cep': '02055-060',
        }
        dados.update(kw)
        return dados

    def _destinatario(self, **kw):
        dados = {
            'nome': 'Livraria Exemplo',
            'cnpj': '98.765.432/0001-98',
            'inscricao_estadual': '111222333444',
            'logradouro': 'Rua dos Ipês',
            'numero': '915',
            'bairro': 'Pinheiros',
            'municipio': 'São Paulo',
            'uf': 'SP',
            'cep': '05416-011',
        }
        dados.update(kw)
        return dados

    def _nota(self, **kw):
        dados = {
            'natureza_operacao': 'Venda de mercadoria',
            'data_emissao': '2026-07-30T10:00:00-03:00',
        }
        dados.update(kw)
        return dados

    def _itens(self):
        return [{
            'codigo': 'LIV-001',
            'descricao': 'Grande Sertão: Veredas',
            'ncm': '4901.99.00',
            'cfop': '5102',
            'unidade': 'UN',
            'quantidade': 3,
            'valor_unitario': 89.90,
        }]

    # -- caminho feliz -------------------------------------------------
    def test_payload_completo_passa_na_validacao(self):
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(nfe_payload.missing_fields(payload), [])
        # Pontuação some: a SEFAZ só aceita dígitos nesses campos.
        self.assertEqual(payload['cnpj_emitente'], '12345678000195')
        self.assertEqual(payload['cep_emitente'], '02055060')
        self.assertEqual(payload['inscricao_estadual_emitente'], '111222333444')
        self.assertEqual(payload['cnpj_destinatario'], '98765432000198')
        # Mesma UF nos dois lados: operação interna.
        self.assertEqual(payload['local_destino'], nfe_payload.DESTINO_INTERNA)
        self.assertEqual(payload['items'][0]['codigo_ncm'], '49019900')
        self.assertEqual(payload['items'][0]['cfop'], '5102')

    def test_totais_batem_com_a_soma_dos_itens(self):
        """3 x 89,90 = 269,70. O total da nota é a soma dos brutos JÁ
        arredondados -- é isso que a SEFAZ confere."""
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(payload['items'][0]['valor_bruto'], '269.70')
        self.assertEqual(payload['valor_produtos'], '269.70')
        self.assertEqual(payload['valor_total'], '269.70')

    def test_frete_e_desconto_entram_no_total(self):
        payload = nfe_payload.build_payload(
            self._nota(valor_frete=20, valor_desconto=9.70),
            self._emitente(), self._destinatario(), self._itens())

        # 269,70 + 20,00 - 9,70
        self.assertEqual(payload['valor_total'], '280.00')

    # -- arredondamento ------------------------------------------------
    def test_arredondamento_e_meio_para_cima_como_a_sefaz(self):
        """`round()` do Python arredonda 1.005 para 1.00 (banker's rounding) e
        a nota fecha com um centavo a menos que a soma dos itens, que é
        rejeição. `money()` usa ROUND_HALF_UP."""
        self.assertEqual(nfe_payload.money('1.005'), '1.01')
        self.assertEqual(nfe_payload.money('2.675'), '2.68')
        self.assertEqual(nfe_payload.money(0), '0.00')

    # -- edge cases ----------------------------------------------------
    def test_pessoa_fisica_vai_como_cpf_e_nao_contribuinte(self):
        payload = nfe_payload.build_payload(
            self._nota(),
            self._emitente(),
            self._destinatario(cnpj=None, cpf='123.456.789-09',
                              inscricao_estadual=None),
            self._itens())

        self.assertEqual(payload['cpf_destinatario'], '12345678909')
        self.assertNotIn('cnpj_destinatario', payload)
        self.assertEqual(payload['indicador_inscricao_estadual_destinatario'],
                         nfe_payload.IE_NAO_CONTRIBUINTE)
        # Sem IE: mandar o campo vazio junto do indicador 9 é erro de schema.
        self.assertNotIn('inscricao_estadual_destinatario', payload)

    def test_venda_para_outro_estado_e_interestadual(self):
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(),
            self._destinatario(uf='rj'), self._itens())

        self.assertEqual(payload['local_destino'], nfe_payload.DESTINO_INTERESTADUAL)

    def test_simples_nacional_usa_csosn_e_normal_usa_cst(self):
        """O campo tem o mesmo nome nos dois regimes mas carrega tabelas
        diferentes; trocar uma pela outra é rejeição 'CST inválido'."""
        simples = nfe_payload.build_payload(
            self._nota(),
            self._emitente(regime_tributario=nfe_payload.CRT_SIMPLES),
            self._destinatario(), self._itens())
        normal = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(simples['items'][0]['icms_situacao_tributaria'],
                         nfe_payload.CSOSN_SIMPLES_IMUNE)
        self.assertEqual(normal['items'][0]['icms_situacao_tributaria'],
                         nfe_payload.CST_ICMS_NAO_TRIBUTADA)

    def test_descricao_longa_e_cortada_no_limite_da_sefaz(self):
        itens = self._itens()
        itens[0]['descricao'] = 'x' * 300
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), itens)

        self.assertEqual(len(payload['items'][0]['descricao']), 120)

    def test_nota_imune_nao_manda_aliquota_de_icms(self):
        """Numa nota de livro (imune) o grupo de tributação do ICMS não tem
        alíquota; mandar `icms_aliquota: 0` faz a SEFAZ reclamar do grupo."""
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), self._itens())

        self.assertNotIn('icms_aliquota', payload['items'][0])
        self.assertNotIn('icms_valor', payload['items'][0])

    # -- cBenef (código de benefício fiscal) ---------------------------
    def test_cbenef_acompanha_o_cst_41(self):
        """SP exige o cBenef desde abril/2026 e a imunidade do livro conta como
        benefício. Sem ele a SEFAZ devolve a rejeição 930 -- foi exatamente o
        que aconteceu na primeira emissão real em homologação."""
        itens = self._itens()
        itens[0]['codigo_beneficio_fiscal'] = nfe_payload.CBENEF_SP_LIVRO
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), itens)

        item = payload['items'][0]
        self.assertEqual(item['icms_situacao_tributaria'], '41')
        self.assertEqual(item['codigo_beneficio_fiscal'], 'SP070130')

    def test_cbenef_nao_vai_em_cst_tributado(self):
        """O espelho da 930: mandar cBenef junto de um CST que não admite
        benefício é rejeição por campo indevido."""
        itens = self._itens()
        itens[0]['codigo_beneficio_fiscal'] = nfe_payload.CBENEF_SP_LIVRO
        itens[0]['icms_situacao_tributaria'] = '00'  # tributada integralmente
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), itens)

        self.assertNotIn('codigo_beneficio_fiscal', payload['items'][0])

    def test_sem_cbenef_configurado_o_campo_simplesmente_nao_vai(self):
        """Estados que não exigem cBenef não podem receber o campo vazio."""
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), self._itens())

        self.assertNotIn('codigo_beneficio_fiscal', payload['items'][0])

    # -- sentido da nota e notas referenciadas -------------------------
    def test_cfop_de_entrada_e_de_saida_pelo_primeiro_digito(self):
        """1918 (devolução de consignação) é ENTRADA mesmo sendo nós a emitir."""
        self.assertEqual(nfe_payload.tipo_documento_por_cfop('1918'),
                         nfe_payload.ENTRADA)
        self.assertEqual(nfe_payload.tipo_documento_por_cfop('2918'),
                         nfe_payload.ENTRADA)
        self.assertEqual(nfe_payload.tipo_documento_por_cfop('5102'),
                         nfe_payload.SAIDA)
        self.assertEqual(nfe_payload.tipo_documento_por_cfop('6917'),
                         nfe_payload.SAIDA)
        self.assertIsNone(nfe_payload.tipo_documento_por_cfop(None))

    def test_nota_de_entrada_nao_e_acusada_de_campo_faltando(self):
        """`tipo_documento: 0` é entrada e é falsy: um `not valor` na validação
        reprovaria toda nota de entrada, devolução inclusive."""
        payload = nfe_payload.build_payload(
            self._nota(tipo_documento=nfe_payload.ENTRADA),
            self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(payload['tipo_documento'], 0)
        self.assertEqual(nfe_payload.missing_fields(payload), [])

    def test_notas_referenciadas_entram_como_lista_de_chaves(self):
        payload = nfe_payload.build_payload(
            self._nota(notas_referenciadas=['9' * 44]),
            self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(payload['notas_referenciadas'],
                         [{'chave_nfe': '9' * 44}])

    def test_referencia_por_item_exclui_a_do_cabecalho(self):
        """Os dois níveis são mutuamente exclusivos: juntos dão 'NF-e com
        referenciamento de documento a nível de nota e a nível de item'. Como
        a devolução exige o item, é o cabeçalho que sai."""
        itens = self._itens()
        itens[0]['chave_dfe_referenciado'] = '9' * 44
        itens[0]['numero_item_dfe_referenciado'] = 1

        payload = nfe_payload.build_payload(
            self._nota(notas_referenciadas=['9' * 44]),
            self._emitente(), self._destinatario(), itens)

        self.assertNotIn('notas_referenciadas', payload)
        self.assertEqual(payload['items'][0]['chave_acesso_dfe_referenciado'],
                         '9' * 44)

    def test_chave_referenciada_malformada_e_descartada(self):
        """Chave torta na referência é rejeição; melhor não mandar."""
        payload = nfe_payload.build_payload(
            self._nota(notas_referenciadas=['123', '']),
            self._emitente(), self._destinatario(), self._itens())

        self.assertNotIn('notas_referenciadas', payload)

    # -- casos de erro -------------------------------------------------
    def test_missing_fields_aponta_o_que_falta_na_nota(self):
        payload = nfe_payload.build_payload(
            self._nota(),
            self._emitente(inscricao_estadual=None, cep=None),
            self._destinatario(), self._itens())

        faltando = nfe_payload.missing_fields(payload)
        self.assertIn('inscricao_estadual_emitente', faltando)
        self.assertIn('cep_emitente', faltando)

    def test_missing_fields_aponta_o_item_pelo_numero(self):
        itens = self._itens()
        itens.append({
            'codigo': 'LIV-002', 'descricao': 'Sem NCM',
            'cfop': '5102', 'quantidade': 1, 'valor_unitario': 10,
        })
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), itens)

        self.assertIn('items[2].codigo_ncm', nfe_payload.missing_fields(payload))

    def test_nota_sem_destinatario_identificado_e_recusada(self):
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(),
            self._destinatario(cnpj=None, cpf=None), self._itens())

        self.assertIn('cnpj_destinatario/cpf_destinatario',
                      nfe_payload.missing_fields(payload))

    def test_icms_origem_zero_nao_conta_como_faltando(self):
        """Origem 0 (nacional) é o caso comum e é falsy em Python: um `not
        valor` na validação reprovaria toda nota de produto nacional."""
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(payload['items'][0]['icms_origem'], 0)
        self.assertEqual(nfe_payload.missing_fields(payload), [])

    # -- IBS/CBS (reforma tributária) ----------------------------------
    def test_grupo_ibs_cbs_entra_no_item(self):
        """A SEFAZ-SP passou a exigir o grupo em 30/07/2026: o mesmo payload
        autorizado duas horas antes voltou com 'Rejeição 1115: IBS/CBS não
        informado'. 410/410008 é o que o sistema em produção emite para livro."""
        itens = self._itens()
        itens[0]['ibs_cbs_situacao_tributaria'] = nfe_payload.CST_IBS_CBS_IMUNE
        itens[0]['ibs_cbs_classificacao_tributaria'] = nfe_payload.CLASS_TRIB_LIVRO

        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), itens)

        item = payload['items'][0]
        self.assertEqual(item['ibs_cbs_situacao_tributaria'], '410')
        self.assertEqual(item['ibs_cbs_classificacao_tributaria'], '410008')

    def test_sem_ibs_cbs_configurado_o_grupo_nao_vai(self):
        """Campo vazio não pode ir: a SEFAZ recusa o grupo incompleto."""
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), self._itens())

        self.assertNotIn('ibs_cbs_situacao_tributaria', payload['items'][0])

    # -- o primeiro dígito diz o destino -------------------------------
    def test_cfop_troca_o_primeiro_digito_conforme_o_destino(self):
        """5 dentro do estado, 6 interestadual, 7 exterior — e 1/2/3 nas
        entradas. É o que torna 5101 e 6101 a mesma operação."""
        self.assertEqual(nfe_payload.cfop_para_destino(
            '5101', nfe_payload.DESTINO_INTERESTADUAL), '6101')
        self.assertEqual(nfe_payload.cfop_para_destino(
            '6917', nfe_payload.DESTINO_INTERNA), '5917')
        self.assertEqual(nfe_payload.cfop_para_destino(
            '5101', nfe_payload.DESTINO_EXTERIOR), '7101')
        # Entradas seguem a mesma lógica, numa faixa própria.
        self.assertEqual(nfe_payload.cfop_para_destino(
            '1918', nfe_payload.DESTINO_INTERESTADUAL), '2918')

    def test_cfop_ja_certo_nao_muda(self):
        self.assertIsNone(nfe_payload.cfop_para_destino(
            '6101', nfe_payload.DESTINO_INTERESTADUAL))
        self.assertIsNone(nfe_payload.cfop_para_destino(
            '5101', nfe_payload.DESTINO_INTERNA))

    def test_codigo_torto_nao_vira_cfop_inventado(self):
        for torto in (None, '', '51', 'abcd', '51011'):
            self.assertIsNone(nfe_payload.cfop_para_destino(
                torto, nfe_payload.DESTINO_INTERESTADUAL))

    # -- desconto ------------------------------------------------------
    def test_desconto_do_item_soma_no_total_da_nota(self):
        """A SEFAZ confere que o vDesc da nota é a soma do vDesc dos itens — e
        é isso que faz o desconto aparecer no DANFE."""
        itens = self._itens()
        itens[0]['valor_desconto'] = 26.97          # 10% de 269,70

        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), itens)

        self.assertEqual(payload['items'][0]['valor_desconto'], '26.97')
        self.assertEqual(payload['valor_desconto'], '26.97')
        # vProd continua o BRUTO; o desconto é abatido no total.
        self.assertEqual(payload['valor_produtos'], '269.70')
        self.assertEqual(payload['valor_total'], '242.73')

    def test_descontos_de_varios_itens_se_somam(self):
        itens = self._itens() + [{
            'codigo': 'LIV-002', 'descricao': 'Sagarana', 'ncm': '49019900',
            'cfop': '5102', 'unidade': 'UN', 'quantidade': 1,
            'valor_unitario': 50.00, 'valor_desconto': 5.00}]
        itens[0]['valor_desconto'] = 26.97

        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), itens)

        self.assertEqual(payload['valor_desconto'], '31.97')
        self.assertEqual(payload['valor_produtos'], '319.70')
        self.assertEqual(payload['valor_total'], '287.73')

    def test_desconto_de_cabecalho_nao_disputa_com_o_dos_itens(self):
        """Um número solto no total que não corresponde à soma dos itens é
        rejeitado: quando o item tem desconto, é ele que manda."""
        itens = self._itens()
        itens[0]['valor_desconto'] = 26.97

        payload = nfe_payload.build_payload(
            self._nota(valor_desconto=999), self._emitente(),
            self._destinatario(), itens)

        self.assertEqual(payload['valor_desconto'], '26.97')

    def test_desconto_com_frete_fecha_a_conta(self):
        itens = self._itens()
        itens[0]['valor_desconto'] = 26.97

        payload = nfe_payload.build_payload(
            self._nota(valor_frete=30), self._emitente(),
            self._destinatario(), itens)

        # 269,70 - 26,97 + 30,00
        self.assertEqual(payload['valor_total'], '272.73')

    # -- cobrança e forma de pagamento ---------------------------------
    def test_duplicatas_viram_cobranca_e_fatura(self):
        """Venda a prazo sem duplicata é documento incompleto, ainda que a
        SEFAZ aceite."""
        payload = nfe_payload.build_payload(
            self._nota(duplicatas=[
                {'numero': '001', 'data_vencimento': '2026-08-30', 'valor': 134.85},
                {'numero': '002', 'data_vencimento': '2026-09-30', 'valor': 134.85}],
                numero_fatura='INV/2026/00001'),
            self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(len(payload['duplicatas']), 2)
        self.assertEqual(payload['duplicatas'][0]['valor'], '134.85')
        self.assertEqual(payload['duplicatas'][1]['data_vencimento'], '2026-09-30')
        self.assertEqual(payload['numero_fatura'], 'INV/2026/00001')
        self.assertEqual(payload['valor_liquido_fatura'], '269.70')

    def test_com_duplicata_a_forma_e_duplicata_mercantil(self):
        """A Focus assume 01 (dinheiro) quando nada se diz — e isso numa venda a
        prazo é declaração falsa de forma de pagamento."""
        payload = nfe_payload.build_payload(
            self._nota(duplicatas=[
                {'numero': '001', 'data_vencimento': '2026-08-30', 'valor': 269.70}]),
            self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(payload['formas_pagamento'][0]['forma_pagamento'],
                         nfe_payload.FORMA_DUPLICATA)

    def test_sem_duplicata_a_forma_e_sem_pagamento(self):
        """Remessa, consignação e bonificação não se pagam."""
        payload = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(payload['formas_pagamento'][0]['forma_pagamento'],
                         nfe_payload.FORMA_SEM_PAGAMENTO)
        self.assertNotIn('duplicatas', payload)

    def test_parcela_zerada_nao_vira_duplicata(self):
        payload = nfe_payload.build_payload(
            self._nota(duplicatas=[{'numero': '001', 'valor': 0}]),
            self._emitente(), self._destinatario(), self._itens())

        self.assertNotIn('duplicatas', payload)

    # -- o centavo do arredondamento global ----------------------------
    #
    # Rejeição 866: "Ausência de troco quando o valor dos pagamentos informados
    # for maior que o total da nota". Aconteceu na n-1 em 14/08/2026, com duas
    # notas: o Odoo soma os valores exatos das linhas e arredonda no fim
    # (`round_globally`), a NFe soma os itens já arredondados, e o rodapé
    # divergiu em um centavo -- para cima.
    def test_pagamento_maior_que_a_nota_cai_para_o_total(self):
        payload = nfe_payload.build_payload(
            self._nota(formas_pagamento=[
                {'forma_pagamento': nfe_payload.FORMA_DUPLICATA,
                 'valor_pagamento': 269.71}]),
            self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(payload['valor_total'], '269.70')
        self.assertEqual(payload['formas_pagamento'][0]['valor_pagamento'], '269.70')

    def test_duplicata_maior_que_a_nota_e_ajustada_na_ultima(self):
        """A sobra sai da última parcela, que é onde o comércio a põe."""
        payload = nfe_payload.build_payload(
            self._nota(duplicatas=[
                {'numero': '001', 'data_vencimento': '2026-08-30', 'valor': 134.85},
                {'numero': '002', 'data_vencimento': '2026-09-30', 'valor': 134.86}],
                formas_pagamento=[{'forma_pagamento': nfe_payload.FORMA_DUPLICATA,
                                   'valor_pagamento': 269.71}]),
            self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(payload['duplicatas'][0]['valor'], '134.85')
        self.assertEqual(payload['duplicatas'][1]['valor'], '134.85')
        self.assertEqual(payload['valor_liquido_fatura'], '269.70')
        self.assertEqual(payload['formas_pagamento'][0]['valor_pagamento'], '269.70')

    def test_a_nota_de_verdade_da_n1_fecha(self):
        """28 x 89,15 com 52% de desconto: 1.198,176 exatos. O item arredondado
        dá 1.198,18 e o Odoo cobra 1.198,19 -- é a divergência que a SEFAZ
        recusou."""
        itens = [{
            'codigo': 'LIV-020',
            'descricao': 'Título com desconto de livraria',
            'ncm': '4901.99.00',
            'cfop': '5102',
            'unidade': 'UN',
            'quantidade': 28,
            'valor_unitario': 89.15,
            'valor_bruto': 2496.20,
            'valor_desconto': 1298.02,
        }]
        payload = nfe_payload.build_payload(
            self._nota(duplicatas=[
                {'numero': '001', 'data_vencimento': '2026-11-12', 'valor': 1198.19}],
                formas_pagamento=[{'forma_pagamento': nfe_payload.FORMA_DUPLICATA,
                                   'valor_pagamento': 1198.19}]),
            self._emitente(), self._destinatario(), itens)

        self.assertEqual(payload['valor_total'], '1198.18')
        self.assertEqual(payload['duplicatas'][0]['valor'], '1198.18')
        self.assertEqual(payload['formas_pagamento'][0]['valor_pagamento'], '1198.18')

    def test_sem_pagamento_continua_zerado_contra_nota_cheia(self):
        """Remessa e consignação pagam MENOS que o total, e isso é legítimo: a
        regra só proíbe pagar mais. É o que a fatura manda (forma 90, valor
        zero) contra uma nota de valor cheio."""
        payload = nfe_payload.build_payload(
            self._nota(formas_pagamento=[
                {'forma_pagamento': nfe_payload.FORMA_SEM_PAGAMENTO,
                 'valor_pagamento': 0.0}]),
            self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(payload['valor_total'], '269.70')
        self.assertEqual(payload['formas_pagamento'][0]['forma_pagamento'],
                         nfe_payload.FORMA_SEM_PAGAMENTO)
        self.assertEqual(payload['formas_pagamento'][0]['valor_pagamento'], '0.00')

    def test_duplicata_menor_que_a_nota_nao_e_inflada(self):
        """Metade à vista, metade a prazo: só a parcela que vence depois vira
        duplicata, e ela continua sendo o que é. Completar até o total da nota
        seria inventar cobrança a prazo que ninguém combinou."""
        payload = nfe_payload.build_payload(
            self._nota(duplicatas=[
                {'numero': '001', 'data_vencimento': '2026-09-30', 'valor': 134.85}]),
            self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(payload['duplicatas'][0]['valor'], '134.85')
        self.assertEqual(payload['valor_total'], '269.70')

    def test_parcela_que_nao_cabe_na_nota_some(self):
        """Caso de borda: a sobra come a última parcela inteira. Ela não entra
        na nota em vez de entrar negativa."""
        payload = nfe_payload.build_payload(
            self._nota(duplicatas=[
                {'numero': '001', 'data_vencimento': '2026-08-30', 'valor': 269.70},
                {'numero': '002', 'data_vencimento': '2026-09-30', 'valor': 0.01}]),
            self._emitente(), self._destinatario(), self._itens())

        self.assertEqual(len(payload['duplicatas']), 1)
        self.assertEqual(payload['duplicatas'][0]['valor'], '269.70')

    # -- ISBN ----------------------------------------------------------
    def test_isbn_vai_como_codigo_de_barras(self):
        itens = self._itens()
        itens[0]['codigo_barras_comercial'] = '9780000000002'
        itens[0]['codigo_barras_tributavel'] = '9780000000002'

        item = nfe_payload.build_payload(
            self._nota(), self._emitente(), self._destinatario(), itens)['items'][0]

        self.assertEqual(item['codigo_barras_comercial'], '9780000000002')
        self.assertEqual(item['codigo_barras_tributavel'], '9780000000002')

    # --- volumes e peso (grupo transp/vol) --------------------------------

    def test_volumes_e_peso_entram_no_payload(self):
        payload = nfe_payload.build_payload(
            nota=self._nota(volumes=3, peso_bruto=4.5),
            emitente=self._emitente(),
            destinatario=self._destinatario(),
            itens=self._itens(),
        )
        # LISTA `volumes`, não campos soltos: campo solto a Focus descarta
        # calada, e foi assim que a primeira nota de produção saiu sem o
        # grupo de transporte.
        self.assertEqual(payload['volumes'], [{
            'quantidade': 3, 'especie': 'CAIXA', 'peso_bruto': '4.500'}])
        self.assertNotIn('quantidade_volumes', payload)
        self.assertNotIn('peso_bruto', payload)

    def test_especie_de_volume_pode_ser_outra(self):
        payload = nfe_payload.build_payload(
            nota=self._nota(volumes=1, especie_volumes='FARDO'),
            emitente=self._emitente(),
            destinatario=self._destinatario(),
            itens=self._itens(),
        )
        self.assertEqual(payload['volumes'][0]['especie'], 'FARDO')

    def test_nota_sem_volume_nao_declara_transporte(self):
        """O acerto fatura livro que já está com o cliente: não move caixa."""
        payload = nfe_payload.build_payload(
            nota=self._nota(),
            emitente=self._emitente(),
            destinatario=self._destinatario(),
            itens=self._itens(),
        )
        self.assertNotIn('volumes', payload)

    def test_peso_arredonda_meio_para_cima(self):
        payload = nfe_payload.build_payload(
            nota=self._nota(volumes=1, peso_bruto=1.0005),
            emitente=self._emitente(),
            destinatario=self._destinatario(),
            itens=self._itens(),
        )
        self.assertEqual(payload['volumes'][0]['peso_bruto'], '1.001')

    # -- transportadora --------------------------------------------------
    def _transportador(self, **kw):
        dados = {
            'nome': 'Transportes Andorinha',
            'cnpj': '11.222.333/0001-81',
            'inscricao_estadual': '111.222.333.555',
            'endereco': 'Rua das Gaivotas, 10',
            'municipio': 'São Paulo',
            'uf': 'sp',
        }
        dados.update(kw)
        return dados

    def test_transportador_entra_no_payload(self):
        payload = nfe_payload.build_payload(
            nota=self._nota(modalidade_frete=nfe_payload.FRETE_EMITENTE),
            emitente=self._emitente(),
            destinatario=self._destinatario(),
            itens=self._itens(),
            transportador=self._transportador(),
        )
        self.assertEqual(payload['modalidade_frete'],
                         nfe_payload.FRETE_EMITENTE)
        self.assertEqual(payload['nome_transportador'],
                         'Transportes Andorinha')
        # Pontuação some, como em todo documento do payload.
        self.assertEqual(payload['cnpj_transportador'], '11222333000181')
        self.assertNotIn('cpf_transportador', payload)
        self.assertEqual(payload['inscricao_estadual_transportador'],
                         '111222333555')
        self.assertEqual(payload['endereco_transportador'],
                         'Rua das Gaivotas, 10')
        self.assertEqual(payload['municipio_transportador'], 'São Paulo')
        self.assertEqual(payload['uf_transportador'], 'SP')

    def test_transportador_autonomo_vai_por_cpf(self):
        payload = nfe_payload.build_payload(
            nota=self._nota(modalidade_frete=nfe_payload.FRETE_TERCEIROS),
            emitente=self._emitente(),
            destinatario=self._destinatario(),
            itens=self._itens(),
            transportador=self._transportador(
                cnpj=None, cpf='123.456.789-09', inscricao_estadual=None),
        )
        self.assertEqual(payload['cpf_transportador'], '12345678909')
        self.assertNotIn('cnpj_transportador', payload)
        self.assertNotIn('inscricao_estadual_transportador', payload)

    def test_sem_transportador_o_grupo_nao_viaja(self):
        payload = nfe_payload.build_payload(
            nota=self._nota(),
            emitente=self._emitente(),
            destinatario=self._destinatario(),
            itens=self._itens(),
        )
        self.assertEqual(payload['modalidade_frete'], nfe_payload.FRETE_SEM)
        for campo in ('nome_transportador', 'cnpj_transportador',
                      'cpf_transportador', 'endereco_transportador',
                      'municipio_transportador', 'uf_transportador'):
            self.assertNotIn(campo, payload)

