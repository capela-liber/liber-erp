# -*- coding: utf-8 -*-
from odoo import models


class ReportPickingSheet(models.AbstractModel):
    """A folha de quem separa: o passeio primeiro, os pedidos depois.

    O relatório do core imprime uma folha por pedido, e quem coleta anda o
    galpão uma vez por pedido — três pedidos com o mesmo título são três idas
    à mesma prateleira. Aqui a seleção inteira vira primeiro UMA folha
    ("Picking") com os títulos somados e ordenados pela prateleira, e só
    depois vêm as folhas dos pedidos, para conferir e embalar.

    A prateleira não é campo novo: é o local de origem da linha do movimento
    (``EL-000137``), que a migração endereçou e a reserva escolhe. Por isso a
    quantidade que vale aqui é a RESERVADA — é ela que sabe de onde o livro
    sai.

    O que NÃO foi reservado não entra na tabela, e isso é decisão, não
    esquecimento: linha com quadradinho é ordem de coletar, e mandar buscar
    o que o sistema não separou dá em uma de duas — o sujeito não acha nada
    na prateleira (a posição seria palpite), ou acha, embala, e a entrega
    leva um exemplar que não está nela. Sem contar a balança, que confere
    contra um peso que não conta essas linhas. Item sem reserva é problema de
    quem prepara, e se resolve antes de a folha ir para a bancada. A folha só
    AVISA, numa linha, que a entrega está incompleta.
    """
    _name = 'report.liber_transport.report_picking_sheet'
    _description = 'Picking'

    # ------------------------------------------------------------------
    # Posição
    # ------------------------------------------------------------------
    def _position_code(self, location, root):
        """O código da prateleira, ou vazio quando o item não tem endereço.

        A raiz do armazém (``EL-VG/Stock``) não é endereço: é o "ainda não
        arrumado". Sai como ``—`` na folha, e no fim da lista.
        """
        if not location or location == root:
            return ''
        return location.name or ''

    # ------------------------------------------------------------------
    # Linhas
    # ------------------------------------------------------------------
    def _picking_lines(self, picking):
        """As linhas de uma entrega, agrupadas por (título, prateleira).

        Uma linha por título e posição — nunca a quebra em branco que o core
        imprime quando o movimento tem várias linhas. Título que mora em duas
        prateleiras sai duas vezes de propósito: são duas paradas do passeio.
        """
        root = picking.location_id
        grouped = {}
        for move_line in picking.move_line_ids:
            qty = move_line.quantity
            if not qty:
                continue
            product = move_line.product_id
            position = self._position_code(move_line.location_id, root)
            self._add(grouped, product, position, qty)
        return self._sorted(grouped.values())

    def _shortfall(self, picking):
        """Quanto foi pedido e a reserva não prendeu — para o aviso, só.

        `quantity` da linha é o que a reserva prendeu; a diferença para a
        demanda é o que a entrega vai deixar para trás.
        """
        qty = titles = 0
        for move in picking.move_ids:
            missing = move.product_uom_qty - sum(
                move.move_line_ids.mapped('quantity'))
            if move.product_uom.compare(missing, 0.0) <= 0:
                continue
            qty += missing
            titles += 1
        return {'qty': qty, 'titles': titles}

    def _add(self, grouped, product, position, qty):
        key = (product.id, position)
        line = grouped.get(key)
        if line:
            line['qty'] += qty
            line['weight'] += (product.weight or 0.0) * qty
            return
        grouped[key] = {
            'product': product,
            'position': position,
            'qty': qty,
            'weight': (product.weight or 0.0) * qty,
            'has_weight': bool(product.weight),
        }

    def _sorted(self, lines):
        """Ordem do passeio: prateleira crescente, sem endereço por último."""
        return sorted(lines, key=lambda line: (
            not line['position'], line['position'],
            line['product'].display_name))

    def _merge(self, all_lines):
        """As linhas de várias entregas somadas — a folha do passeio."""
        grouped = {}
        for line in all_lines:
            self._add(grouped, line['product'], line['position'], line['qty'])
        return self._sorted(grouped.values())

    # ------------------------------------------------------------------
    def _sheet(self, picking, lines, shortfall):
        """Os números do rodapé de uma folha.

        O peso é a soma do catálogo, NÃO o ``_liber_peso_para_transporte()``:
        aquele prefere o peso de expedição digitado, que é a medida da
        balança — conferir uma medida contra ela mesma não confere nada. E o
        que falta de cadastro é dito na folha: peso que não fecha, dito que
        não fecha, ainda serve; calado, mente.
        """
        return {
            'picking': picking,
            'lines': lines,
            'shortfall': shortfall,
            'qty_total': sum(line['qty'] for line in lines),
            'weight_total': sum(line['weight'] for line in lines),
            'titles_total': len({line['product'].id for line in lines}),
            'no_weight': len({line['product'].id for line in lines
                              if not line['has_weight']}),
        }

    def _get_report_values(self, docids, data=None):
        pickings = self.env['stock.picking'].browse(docids)
        sheets, every_line, incompletas = [], [], 0
        for picking in pickings:
            lines = self._picking_lines(picking)
            shortfall = self._shortfall(picking)
            incompletas += 1 if shortfall['titles'] else 0
            every_line.extend(lines)
            sheets.append(self._sheet(picking, lines, shortfall))
        # Uma entrega só não tem o que agrupar: a folha do passeio seria a
        # cópia da folha do pedido, com uma página a mais para gastar.
        batch = False
        if len(pickings) > 1:
            batch = self._sheet(pickings, self._merge(every_line), None)
            # No lote o aviso é de contagem: quem monta o lote ainda pode
            # mandar reservar antes de o coletador sair da cadeira.
            batch['incomplete_pickings'] = incompletas
        return {
            'doc_ids': docids,
            'doc_model': 'stock.picking',
            'docs': pickings,
            'sheets': sheets,
            'batch': batch,
        }
