# -*- coding: utf-8 -*-
"""O serviço por trás da tela de bipagem.

Três perguntas e uma ação, todas chamadas pela tela por RPC:

- `scan(code, origin_id)`: o que é este código -- uma prateleira, um livro,
  nada. Devolve um dicionário com `kind`; erro de operação (livro que não
  está na prateleira, código desconhecido) vem como `kind = 'error'` com a
  mensagem, para a tela mostrar na linha e manter o foco no campo -- uma
  caixa de diálogo exigiria um clique de quem está com o leitor na mão.
- `transfer(origin_id, dest_id, lines)`: cria a transferência interna do
  armazém, reserva, confere que reservou tudo e valida. Passa pelas guardas
  do liber_stock_shelves como qualquer outra.
"""
from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class ShelfScan(models.AbstractModel):
    _name = 'liber.shelf.scan'
    _description = 'Shelf Scan Service'

    # -- leitura ---------------------------------------------------------

    @api.model
    def _find_location(self, code):
        Loc = self.env['stock.location']
        code = (code or '').strip()
        if not code:
            return Loc
        companies = self.env.companies.ids
        for campo in ('barcode', 'name', 'complete_name'):
            loc = Loc.search([(campo, '=', code), ('usage', '=', 'internal'),
                              ('company_id', 'in', companies)], limit=1)
            if loc:
                return loc
        return Loc

    @api.model
    def _find_product(self, code):
        Prod = self.env['product.product']
        code = (code or '').strip()
        if not code:
            return Prod
        prod = Prod.search([('barcode', '=', code)], limit=1)
        if not prod:
            prod = Prod.search([('default_code', '=', code)], limit=1)
        return prod

    @api.model
    def _location_vals(self, loc):
        return {
            'kind': 'location', 'id': loc.id, 'name': loc.name,
            'complete_name': loc.complete_name,
            'warehouse': loc.warehouse_id.name,
        }

    @api.model
    def _on_hand(self, product, location):
        return self.env['stock.quant']._get_available_quantity(
            product, location, strict=True)

    @api.model
    def scan(self, code, origin_id=False):
        """Classifica o bipe. `origin_id` é a prateleira já aberta, para
        conferir se o livro está nela."""
        loc = self._find_location(code)
        if loc:
            if not loc._liber_is_shelf():
                return {'kind': 'error', 'message': _(
                    "%(location)s is not a warehouse shelf.",
                    location=loc.complete_name)}
            return self._location_vals(loc)
        prod = self._find_product(code)
        if prod:
            vals = {'kind': 'product', 'id': prod.id,
                    'name': prod.display_name, 'barcode': prod.barcode,
                    'on_hand': 0.0}
            if origin_id:
                origem = self.env['stock.location'].browse(origin_id)
                vals['on_hand'] = self._on_hand(prod, origem)
                if float_compare(vals['on_hand'], 0,
                                 precision_rounding=prod.uom_id.rounding) <= 0:
                    onde = self.env['stock.quant'].search([
                        ('product_id', '=', prod.id),
                        ('location_id.usage', '=', 'internal'),
                        ('location_id.warehouse_id', '=',
                         origem.warehouse_id.id),
                        ('quantity', '>', 0)])
                    lugares = ', '.join(
                        '%s (%d)' % (q.location_id.name, q.quantity)
                        for q in onde[:6]) or _("nowhere in this warehouse")
                    return {'kind': 'error', 'message': _(
                        "%(product)s is not on %(shelf)s. It is on: %(where)s.",
                        product=prod.display_name, shelf=origem.name,
                        where=lugares)}
            return vals
        return {'kind': 'error',
                'message': _("Unknown code: %(code)s", code=code)}

    # -- a transferência -------------------------------------------------

    @api.model
    def transfer(self, origin_id, dest_id, lines):
        """`lines` = [{'product_id': id, 'qty': n}, ...]. Cria, reserva,
        confere e valida a transferência interna. Falha inteira ou passa
        inteira: nada de validação parcial no bipe."""
        Loc = self.env['stock.location']
        origem, destino = Loc.browse(origin_id), Loc.browse(dest_id)
        if not lines:
            raise UserError(_("No books were scanned."))
        if not (origem._liber_is_shelf() and destino._liber_is_shelf()):
            raise UserError(_("Origin and destination must be warehouse shelves."))
        if origem == destino:
            raise UserError(_("Origin and destination are the same shelf."))
        armazem = origem.warehouse_id
        if destino.warehouse_id != armazem:
            raise UserError(_("%(dest)s is not a shelf of %(warehouse)s.",
                              dest=destino.name, warehouse=armazem.name))
        tipo = armazem.int_type_id
        if not tipo or not tipo.active:
            raise UserError(_("Internal transfers are not active on %(warehouse)s.",
                              warehouse=armazem.name))
        por_produto = {}
        for l in lines:
            por_produto[l['product_id']] = por_produto.get(l['product_id'], 0) + l['qty']
        moves = []
        Prod = self.env['product.product']
        for pid, qty in por_produto.items():
            prod = Prod.browse(pid)
            moves.append((0, 0, {
                'product_id': prod.id, 'product_uom_qty': qty,
                'product_uom': prod.uom_id.id,
                'location_id': origem.id, 'location_dest_id': destino.id}))
        picking = self.env['stock.picking'].create({
            'picking_type_id': tipo.id,
            'location_id': origem.id, 'location_dest_id': destino.id,
            'origin': _("Scan"),
            'move_ids': moves,
        })
        picking.action_confirm()
        picking.action_assign()
        faltas = [m for m in picking.move_ids
                  if float_compare(m.quantity, m.product_uom_qty,
                                   precision_rounding=m.product_uom.rounding) < 0]
        if faltas:
            texto = '; '.join(
                _("%(product)s: %(have)d of %(want)d on %(shelf)s",
                  product=m.product_id.display_name, have=m.quantity,
                  want=m.product_uom_qty, shelf=origem.name) for m in faltas)
            picking.action_cancel()
            raise UserError(_("Not enough on the shelf -- %(detail)s", detail=texto))
        picking.move_ids.picked = True
        picking.with_context(skip_backorder=True,
                             skip_sms=True).button_validate()
        if picking.state != 'done':
            raise UserError(_("The transfer did not validate (%(state)s).",
                              state=picking.state))
        return {'picking_id': picking.id, 'name': picking.name,
                'qty': sum(por_produto.values()),
                'origin': origem.name, 'dest': destino.name}
