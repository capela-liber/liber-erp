# -*- coding: utf-8 -*-
import logging

from markupsafe import Markup

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """Leva a DANFE até a transferência, para a logística não abrir a fatura.

    O gancho é o ``_focus_guardar_documentos`` do ``liber_nfe_focus``: é ele
    que roda quando a SEFAZ autoriza (ou cancela) a nota, e é ele que já
    baixou o PDF da DANFE para a fatura — daqui só se copia o anexo para o
    chatter de cada transferência do pedido.
    """
    _inherit = 'account.move'

    def _focus_guardar_documentos(self, resposta):
        super()._focus_guardar_documentos(resposta)
        # Falha aqui não derruba a emissão: a nota já está autorizada na
        # SEFAZ, e o _focus_guardar_documentos roda de novo a cada consulta —
        # o que não propagou agora propaga na próxima.
        try:
            if self.focus_status == 'autorizado':
                self._liber_danfe_para_pickings()
            elif self.focus_status == 'cancelado':
                self._liber_avisar_cancelamento_nos_pickings()
        except Exception:
            _logger.exception(
                "NFe %s: falha ao levar a DANFE às transferências",
                self.display_name)

    def _liber_pedidos_da_nota(self):
        """Os pedidos por trás desta nota.

        Duas pernas, porque a casa emite por dois caminhos:

        - venda (S000): a fatura nasce do Criar-fatura e as linhas apontam
          para as linhas do pedido;
        - consignação (C000) e remessa (REM): a nota nasce sem linha ligada
          (o gerador cria as linhas cruas), mas carimba ``invoice_origin``
          com o nome do pedido.

        O acerto entra pela primeira perna — a venda S dele fatura como
        qualquer venda. Quem o distingue é ``_liber_pickings_da_nota``: a
        única transferência do S é a baixa da prateleira, que não é carga.
        """
        self.ensure_one()
        orders = self.invoice_line_ids.sale_line_ids.order_id
        if not orders and self.invoice_origin:
            orders = self.env['sale.order'].search([
                ('name', '=', self.invoice_origin),
                ('company_id', '=', self.company_id.id)])
        return orders

    def _liber_carimbar_pickings_do_xml(self):
        """Leva a nota nascida de XML (Olist e afins) às suas transferências.

        O carimbo normal acontece no gancho da autorização Focus -- que uma
        nota emitida FORA nunca atravessa. O elo existe do outro lado (a
        fatura aponta o painel do XML pela chave de acesso); este método o
        traz para o mov, para a logística imprimir a DANFE e o filtro "Sem
        nota fiscal" dizer a verdade.
        """
        for move in self:
            # Pela chave de acesso (o elo canônico) ou, para XML legado sem
            # chave, pelo apontamento direto do painel para a fatura.
            painel = move.nfe_xml_panel_id or self.env['nfe.xml.panel'].search(
                [('invoice_id', '=', move.id)], limit=1)
            if not painel or painel.is_cancelled or move.state != 'posted':
                continue
            for picking in move._liber_pickings_da_nota().filtered(
                    lambda p: not p.nfe_move_id):
                picking.nfe_move_id = move

    def _liber_pickings_da_nota(self):
        """As transferências DE CARGA do pedido por trás desta nota.

        A baixa de prateleira do acerto fica de fora: ela é a transferência
        de propriedade dos livros que o cliente já tem, e nada dela — caixa,
        peso, transportadora — pode vazar para a nota. Filtrada aqui, o
        acerto sai como sempre saiu: modalidade 9, sem ocorrência de
        transporte.
        """
        pickings = self._liber_pedidos_da_nota().picking_ids
        if not pickings and self.invoice_origin:
            # Nem todo documento que gera remessa é um pedido de venda, e o
            # caminho de cima só sabe procurar pedido. A bonificação é o caso
            # que descobriu isto (31/08/2026): a ficha B000 cria a sua própria
            # transferência BON/ e a sua própria nota REM-B, sem pedido nenhum
            # no meio -- e a logística ficava embalando o pacote sem DANFE no
            # chatter, com o filtro "Sem nota fiscal" mentindo sobre ele.
            #
            # O elo já existia no dado, sem ninguém precisar declarar nada: os
            # dois documentos carimbam o mesmo nome de origem. Procurar por ele
            # é uma regra geral -- serve para qualquer documento futuro que
            # gere remessa sem ser pedido -- e não custa nada a quem TEM
            # pedido, porque só roda quando o caminho de cima volta vazio.
            pickings = self.env['stock.picking'].search([
                ('origin', '=', self.invoice_origin),
                ('company_id', '=', self.company_id.id),
            ])
        return pickings.filtered(
            lambda p: p.state != 'cancel'
            and not p._liber_baixa_de_prateleira())

    # ------------------------------------------------------------------
    # volumes e peso: nascem na movimentação, morrem na nota
    # ------------------------------------------------------------------
    def _liber_volumes_da_movimentacao(self):
        """(caixas, peso) somados das transferências desta nota.

        O peso do Odoo é o dos produtos (``stock_delivery`` soma
        quantidade x peso cadastrado); quando o livro não tem peso na ficha,
        sai zero — e aí quem fatura digita. A caixa nunca é calculada:
        vem da contagem de quem embalou.
        """
        self.ensure_one()
        pickings = self._liber_pickings_da_nota()
        caixas = sum(pickings.mapped('box_count'))
        peso = sum(p._liber_peso_para_transporte() for p in pickings)
        return caixas, peso

    def action_liber_puxar_volumes(self):
        """Botão: traz caixas e peso da movimentação, por cima do que houver."""
        for move in self:
            caixas, peso = move._liber_volumes_da_movimentacao()
            move.write({'nfe_volumes': caixas, 'nfe_peso_bruto': peso})
        return True

    def _liber_preencher_volumes_vazios(self):
        """Traz da movimentação o que estiver VAZIO. Devolve True se mexeu.

        "Vazio" e não "diferente": quem fatura confere a caixa fechada na
        bancada e é a última palavra. Sobrescrever um número digitado seria
        trocar a contagem de quem viu pela soma de quem calculou.
        """
        self.ensure_one()
        if not self._liber_pickings_da_nota():
            return False
        caixas, peso = self._liber_volumes_da_movimentacao()
        valores = {}
        if not self.nfe_volumes and caixas:
            valores['nfe_volumes'] = caixas
        if not self.nfe_peso_bruto and peso:
            valores['nfe_peso_bruto'] = peso
        if valores:
            self.write(valores)
        return bool(valores)

    # ------------------------------------------------------------------
    # frete e transportadora: nascem no cadastro e no pedido (12/08/2026)
    # ------------------------------------------------------------------
    def _liber_preencher_frete_vazio(self):
        """Modalidade e transportadora, trazidos de onde nasceram.

        A modalidade desce em cascata: pedido (negociada caso a caso),
        cadastro do cliente (padrão comercial), e por fim o padrão da casa
        — CIF, o remetente contrata (decisão de 12/08/2026). A
        transportadora vem do método de entrega da transferência, que o
        liber_transport já herda do cadastro do cliente.

        Só para nota com movimentação física, e só no que estiver VAZIO,
        pela mesma regra dos volumes: quem fatura é a última palavra. O
        acerto de consignação não passa por aqui e sai como 9 — sem
        ocorrência de transporte.
        """
        self.ensure_one()
        pickings = self._liber_pickings_da_nota()
        if not pickings:
            return False
        valores = {}
        if not self.nfe_modalidade_frete:
            pedidos = self._liber_pedidos_da_nota()
            negociada = next(
                (p.nfe_modalidade_frete for p in pedidos
                 if p.nfe_modalidade_frete), False)
            padrao_cliente = \
                self.partner_id.commercial_partner_id.nfe_modalidade_frete
            valores['nfe_modalidade_frete'] = (
                negociada or padrao_cliente or '0')
        if not self.nfe_transportadora_id:
            transportadora = next(
                (p.carrier_id.partner_id for p in pickings
                 if p.carrier_id.partner_id), None)
            if transportadora:
                valores['nfe_transportadora_id'] = transportadora.id
        if valores:
            self.write(valores)
        return bool(valores)

    def _liber_tem_produto_contavel(self):
        """A nota carrega coisa que ocupa caixa?

        `is_storable` é o critério, escolhido pela direção em 10/08/2026: é o
        que move estoque. Serviço, frete e desconto não pedem caixa nem peso.

        É de propósito mais largo que "tem movimentação": pega também a nota
        de mercadoria feita à mão, sem picking nenhum -- que é justamente a
        que ninguém lembra de conferir.
        """
        self.ensure_one()
        return any(linha.product_id.is_storable
                   for linha in self.invoice_line_ids
                   if linha.product_id)

    def _liber_volumes_faltando(self):
        """O que falta declarar nesta nota, em linguagem de quem vai corrigir.

        Lista vazia = nada a avisar. Só vale para documento de VENDA: numa
        fatura de fornecedor a caixa é problema de quem enviou.
        """
        self.ensure_one()
        if not self.is_sale_document() or not self._liber_tem_produto_contavel():
            return []
        # O acerto de consignação: há um pedido atrás da nota e nenhuma
        # transferência DE CARGA -- ou porque toda a movimentação é baixa de
        # prateleira (acerto novo), ou porque não há movimentação nenhuma
        # (acerto do legado, e são milhares). Livro que já está com o cliente
        # não tem caixa nem peso a declarar, e a emissão (que confere por
        # picking de carga) passa direto; avisar aqui seria prometer um
        # bloqueio que não existe. A nota de mercadoria feita à mão -- SEM
        # pedido nenhum -- continua avisando: é justamente a que ninguém
        # lembra de conferir.
        if self._liber_pedidos_da_nota() and not self._liber_pickings_da_nota():
            return []
        faltando = []
        if not self.nfe_volumes:
            faltando.append(_("volumes (caixas)"))
        if not self.nfe_peso_bruto:
            faltando.append(_("peso bruto"))
        return faltando

    def action_post(self):
        """Confirmar a fatura é o momento de trazer a contagem da Logística.

        Antes desta mudança (11/08/2026) caixas e peso só chegavam à nota na
        hora de EMITIR, dentro do `_liber_conferir_volumes`. Quem abria a
        fatura provisória via zero, achava que a integração não existia e
        digitava por cima -- ou emitia e levava um erro que podia ter sido
        avisado muito antes.

        Agora são dois momentos, com pesos diferentes:

          confirmar   preenche o que está vazio e AVISA se ainda faltar
          emitir      barra, porque a SEFAZ não aceita a nota sem os dois

        O aviso não bloqueia por decisão da direção: fatura se confirma o dia
        inteiro, e a caixa pode ser contada depois. O que não se admite é
        chegar na emissão sem saber que faltava.
        """
        for move in self:
            if move.is_sale_document():
                move._liber_preencher_volumes_vazios()
                move._liber_preencher_frete_vazio()

        resultado = super().action_post()

        avisar = self.filtered(
            lambda m: m.state == 'posted' and m._liber_volumes_faltando())
        for move in avisar:
            faltando = move._liber_volumes_faltando()
            move.message_post(body=Markup('<p>%s</p><ul>%s</ul><p>%s</p>') % (
                _("Esta nota leva mercadoria e ainda não declara:"),
                Markup('').join(
                    Markup('<li>%s</li>') % item for item in faltando),
                _("Preencha na aba NFe antes de emitir — a SEFAZ recusa a "
                  "nota sem isso, e a transportadora confere na coleta."),
            ))

        # O core devolve um assistente em alguns casos (valor fora do padrão,
        # autopost de contas). Se ele quer abrir alguma coisa, não atropelo:
        # a notificação é conveniência, o assistente dele é fluxo.
        if resultado:
            return resultado
        if len(self) == 1 and avisar:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'warning',
                    'title': _("Faltam volumes nesta nota"),
                    'message': _(
                        "%(fatura)s não declara %(faltando)s. Dá para "
                        "confirmar assim, mas a emissão da NFe vai barrar.",
                        fatura=self.display_name,
                        faltando=', '.join(self._liber_volumes_faltando())),
                    'sticky': False,
                    # Sem o next, esta devolução SUBSTITUI o recarregamento
                    # padrão do formulário: a fatura lançava no servidor, a
                    # tela seguia em "Rascunho", e o segundo Confirmar levava
                    # "deve estar em rascunho" (visto na operação, 17/08/2026).
                    'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
                },
            }
        return resultado

    def _liber_conferir_volumes(self):
        """Nota que carrega caixa não sai sem dizer quantas e quanto pesa.

        A exigência vale só para nota com movimentação física: o acerto de
        consignação fatura livro que já está na prateleira do cliente, não
        move volume nenhum, e passa direto (``_liber_pickings_da_nota``
        devolve vazio para ele, de propósito).

        O que estiver vazio é preenchido da movimentação antes de conferir —
        assim ninguém precisa clicar em nada quando o cadastro tem os dados.
        """
        self.ensure_one()
        pickings = self._liber_pickings_da_nota()
        if pickings:
            self._liber_preencher_volumes_vazios()

            faltando = []
            if not self.nfe_volumes:
                faltando.append(_(
                    "- volumes (caixas): conte na transferência (%s) ou "
                    "preencha na aba NFe desta fatura",
                    ', '.join(pickings.mapped('name'))))
            if not self.nfe_peso_bruto:
                faltando.append(_(
                    "- peso bruto: o cadastro dos livros não tem peso, "
                    "então preencha na aba NFe desta fatura"))
            if faltando:
                raise UserError(_(
                    "%(fatura)s move mercadoria e a nota precisa declarar o "
                    "que vai na caixa:\n\n%(faltando)s\n\n"
                    "Esses dois valores viajam no DANFE e são o que a "
                    "transportadora confere na coleta.",
                    fatura=self.display_name,
                    faltando='\n'.join(faltando)))

    def _focus_build_payload(self):
        self.ensure_one()
        self._liber_conferir_volumes()
        # Fatura confirmada antes desta integração existir não passou pelo
        # gancho do action_post: a emissão completa o que estiver vazio.
        self._liber_preencher_frete_vazio()
        return super()._focus_build_payload()

    def _liber_danfe_para_pickings(self):
        """Posta o PDF da DANFE no chatter das transferências da nota."""
        self.ensure_one()
        pickings = self._liber_pickings_da_nota()
        if not pickings:
            return
        nome = '%s.pdf' % self.focus_ref
        danfe = self.env['ir.attachment'].search([
            ('res_model', '=', 'account.move'), ('res_id', '=', self.id),
            ('name', '=', nome)], limit=1)
        for picking in pickings:
            if picking.nfe_move_id != self:
                picking.nfe_move_id = self
            # Sem PDF não há o que postar: o download falhou e a próxima
            # consulta refaz este caminho com o anexo já na fatura.
            if not danfe:
                continue
            # Mesma idempotência do liber_nfe_focus: o anexo com este nome já
            # está na transferência, então a mensagem já foi postada.
            if self.env['ir.attachment'].search_count([
                    ('res_model', '=', 'stock.picking'),
                    ('res_id', '=', picking.id), ('name', '=', nome)]):
                continue
            copia = danfe.copy(
                {'res_model': 'stock.picking', 'res_id': picking.id})
            corpo = Markup(_(
                "<p><b>NFe nº %(numero)s autorizada pela SEFAZ</b> — a DANFE "
                "segue anexa.</p>"
                "<p>É o documento que viaja com esta transferência "
                "(nota %(nota)s).</p>")) % {
                    'numero': self.focus_numero or '?',
                    'nota': self.name or self.focus_ref}
            picking.message_post(
                body=corpo, attachment_ids=copia.ids,
                subtype_xmlid='mail.mt_note')

    def _liber_avisar_cancelamento_nos_pickings(self):
        """Avisa no chatter que a DANFE anexada deixou de valer.

        O PDF postado não se apaga — histórico não se reescreve — mas também
        não pode ficar mentindo sozinho: quem abrir a transferência precisa
        ver que aquela nota caiu.
        """
        self.ensure_one()
        pickings = self.env['stock.picking'].search([
            ('nfe_move_id', '=', self.id),
            ('nfe_cancel_notified', '=', False)])
        for picking in pickings:
            picking.message_post(
                body=Markup(_(
                    "<p><b>A NFe nº %(numero)s desta transferência foi "
                    "cancelada na SEFAZ.</b> A DANFE anexada acima não vale "
                    "mais como documento de transporte.</p>")) % {
                        'numero': self.focus_numero or '?'},
                subtype_xmlid='mail.mt_note')
            picking.nfe_cancel_notified = True
