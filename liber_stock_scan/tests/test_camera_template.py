# -*- coding: utf-8 -*-
"""A câmera abria e o quadro ficava preto, no telefone (12/10/2026).

O <video> estava sob t-if="state.camera": só nascia no render DEPOIS do
clique, e o código o entregava ao ZXing antes disso. Com null, o ZXing cria
um <video> solto, fora da página -- a câmera lia por baixo e o quadro visível
nunca recebia imagem. O tour roda num Chrome sem câmera e não pega isto; o
que se guarda aqui é a forma do template: o vídeo existe sempre, escondido.
"""
from lxml import etree

from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path


@tagged('post_install', '-at_install')
class TestCameraTemplate(TransactionCase):

    def setUp(self):
        super().setUp()
        caminho = file_path('liber_stock_scan/static/src/scan/scan.xml')
        self.arvore = etree.parse(caminho)

    def _video(self):
        videos = self.arvore.xpath('//video[@t-ref="video"]')
        self.assertEqual(len(videos), 1, "o template tem um e só um <video>")
        return videos[0]

    def test_o_video_existe_antes_do_clique(self):
        condicionais = [a for a in self._video().iterancestors()
                        if a.get('t-if') or a.get('t-elif') or a.get('t-else') is not None]
        self.assertFalse(
            condicionais,
            "o <video> não pode depender de t-if: nasce depois do clique e "
            "chega null ao ZXing, que filma num vídeo invisível")

    def test_o_video_toca_no_telefone(self):
        video = self._video()
        for atributo in ('playsinline', 'muted', 'autoplay'):
            self.assertTrue(video.get(atributo),
                            "sem %s o navegador do telefone não toca" % atributo)

    def test_desligada_a_area_some(self):
        caixa = self._video().getparent()
        self.assertIn('d-none', caixa.get('t-att-class') or '',
                      "câmera desligada: a área fica escondida, não removida")
