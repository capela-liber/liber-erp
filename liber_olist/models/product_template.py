# -*- coding: utf-8 -*-

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from . import olist_client

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    """The write-back side of the adapter: push our stock UP to Olist.

    Everything else in this module reads (notas, catalogue); this is the first
    recurring WRITE. It grew from a one-product pilot button into three entry
    points that all share one core (`_push_stock_to_olist`):

    * the per-product button / list action (`action_push_stock_to_olist`),
    * the account's "push now" button, and the nightly cron (olist.account).

    Only products already in Olist (with an `olist_produto_id`) are ever
    pushed - the stock endpoint updates an existing product, it never creates
    one, which is the explicit rule: Odoo does not populate Olist's catalogue.
    The raw exchange of the last push is kept on the record so it can be read
    back without digging through the server log. See liber_olist/NOTES.md
    sections 10 and 10.5.

    Everything here is per COMPANY, never per database: on-hand is read in the
    account's company alone, and the Olist id is a company-dependent value,
    because the same book is a different record in each Olist account.
    """
    _inherit = 'product.template'

    olist_produto_id = fields.Char(
        string="ID do produto no Olist", company_dependent=True,
        help="O id INTERNO do produto no Olist/Tiny. É por ele que o endpoint "
             "de estoque atende, não pelo ISBN: por isso ele é resolvido uma "
             "vez (na leitura do catálogo ou por busca de ISBN) e guardado "
             "aqui. Ter este id é o que significa 'este produto está no Olist' "
             "— daí os filtros de busca, e nenhum booleano à parte para manter "
             "em dia.\n"
             "Por EMPRESA: cada empresa tem sua conta Olist, e o mesmo ISBN é "
             "um id interno diferente em cada uma. Um id só, compartilhado, "
             "faria o envio de uma empresa cair no produto de outra.")
    olist_stock_log = fields.Text(
        string="Log de estoque do Olist", readonly=True, company_dependent=True,
        help="A requisição e a resposta cruas do último envio de estoque ao "
             "Olist. Ficam no próprio registro para que um envio se confira sem "
             "garimpar o log do servidor. Por empresa, como o id de que fala.")

    # ------------------------------------------------------------------
    # O sentido inverso: o que É nosso e ainda NÃO está no Olist
    # ------------------------------------------------------------------
    olist_mirror_ids = fields.One2many(
        'olist.product', 'product_tmpl_id', string="No espelho do Olist")
    olist_absent = fields.Boolean(
        string="Fora do Olist", compute='_compute_olist_absent', store=True,
        help="Não existe linha do catálogo do Olist casada com este livro — "
             "ou seja, ele não está à venda no marketplace.\n"
             "É a pergunta inversa da tela de Produtos: lá se olha o que o "
             "Olist tem e o Odoo não conhece; aqui, o que é nosso e ainda não "
             "chegou lá. Foi assim que apareceram 9.459 exemplares parados em "
             "80 títulos que ninguém estava oferecendo.\n"
             "Vale para QUALQUER conta Olist: com mais de uma empresa "
             "espelhando, 'está no Olist' quer dizer 'em alguma delas'.")

    @api.depends('olist_mirror_ids')
    def _compute_olist_absent(self):
        for template in self:
            template.olist_absent = not template.olist_mirror_ids

    # ------------------------------------------------------------------
    # Stock push
    # ------------------------------------------------------------------
    def action_push_stock_to_olist(self):
        """Button / list action: push the selected product(s) to Olist.

        Works on one record (the form button) or many (the list action). The
        account is resolved once; each product's push is independent, so one
        rejected product never aborts the rest - the notification summarises.
        """
        if not self:
            return False
        account = self._olist_account()
        ok, errors = 0, []
        for product in self:
            status, detail = product._push_stock_to_olist(account)
            if status == 'OK':
                ok += 1
            else:
                errors.append("%s: %s" % (
                    product.default_code or product.barcode
                    or product.display_name, detail))

        if not errors:
            msg = (_("Saldo no Olist: %s", detail) if len(self) == 1
                   else _("%s produto(s) atualizados no Olist.", ok))
            kind, sticky = 'success', False
        else:
            head = "\n".join(errors[:8])
            more = _("\n... e mais %s.", len(errors) - 8) if len(errors) > 8 else ""
            msg = _("%(ok)s ok, %(err)s com erro:\n%(head)s%(more)s",
                    ok=ok, err=len(errors), head=head, more=more)
            kind, sticky = 'warning', True
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Olist: estoque"),
                'message': msg,
                'type': kind,
                'sticky': sticky,
            },
        }

    def _olist_account(self):
        """The Olist account to push through, for the CURRENT company.

        No fallback to "whatever account exists". Falling back would send this
        company's on-hand to another company's Olist account - a silent
        cross-company write into a live fiscal account, which is precisely the
        failure the one-account-per-company design exists to prevent.
        """
        company = self.env.company
        account = self.env['olist.account'].search(
            [('company_id', '=', company.id)], limit=1)
        if not account:
            raise UserError(_(
                "A empresa %s não tem conta Olist. Estoque nunca sobe pela "
                "conta de outra empresa: crie uma em Olist > Configurações > "
                "Contas.",
                company.display_name))
        return account

    def _in_olist_company(self, company):
        """This product, read and written strictly inside `company`.

        `with_company()` is NOT enough: by its own contract it UNIONS the
        company into env.companies, and `qty_available` with no warehouse in
        context sums every warehouse of env.companies. Under a multi-company
        user - or a cron running as root with every company enabled - that
        quietly sends the whole group's stock to one company's Olist account.
        Pinning allowed_company_ids to the single company is what makes on-hand
        mean "on hand HERE", and it also selects the right company key for the
        company-dependent fields.
        """
        return self.with_context(allowed_company_ids=[company.id])

    def _olist_stock_qty(self, account):
        """Quanto oferecer ao Olist: o estoque do ARMAZÉM, menos a margem.

        Não é `qty_available` ("Em mãos"), e a diferença não é sutil: em mãos
        soma tudo que é interno da empresa — o que está no recebimento, o que
        está separado para expedir, o que já saiu da prateleira. O que se pode
        vender num marketplace é o que está na área de estoque do armazém. É o
        mesmo número que a ficha do produto mostra em "Estoque", ao lado de
        "Consignado" (liber_soc_moves.soc_qty_wh) — o que está na tela é o que
        sobe, senão ninguém consegue conferir um push.

        Sem armazém na empresa não há o que oferecer: zero, não "tudo".

        E desconta o RESERVADO: entrega confirmada e ainda não validada — o
        pacote de marketplace que espera coleta na prateleira, a remessa de
        consignação em separação — é exemplar com dono. Ele ainda conta no
        armazém (não saiu), mas oferecê-lo ao Olist é vender duas vezes o
        mesmo livro no intervalo entre a importação e a coleta.
        """
        self.ensure_one()
        return max(0.0, self._olist_wh_qty(account)
                   - self._olist_reservado_qty(account)
                   - account.stock_reserve)

    def _olist_reservado_qty(self, account):
        """Quanto do armazém já tem dono (reservado por saídas abertas)."""
        self.ensure_one()
        company = account.company_id
        product = self._in_olist_company(company)
        warehouses = self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', company.id)])
        if not warehouses:
            return 0.0
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', 'in', product.product_variant_ids.ids),
            ('location_id', 'child_of', warehouses.lot_stock_id.ids)])
        return sum(quants.mapped('reserved_quantity'))

    def _olist_wh_qty(self, account):
        """O estoque do armazém, cru — antes da margem.

        Separado do de cima porque o log precisa dos dois números: com o piso
        em zero, `enviado + margem` não devolve o estoque (1 exemplar com
        margem 3 envia 0, e 0+3 diria "3"). Um log que não bate com a
        prateleira não serve para conferir nada.
        """
        self.ensure_one()
        company = account.company_id
        product = self._in_olist_company(company)
        warehouses = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)])
        if not warehouses:
            return 0.0
        # Pelo caminho do próprio Odoo (contexto `location`), e não somando
        # quants à mão: assim as sublocalizações - as prateleiras endereçadas -
        # entram pela mesma regra que a tela usa.
        #
        # Nas VARIANTES, e não no template, por uma armadilha do core: o
        # `_compute_quantities` do product.template declara
        # `@api.depends_context('warehouse_id')` e NÃO inclui 'location'
        # (o do product.product inclui). Num template, portanto, a chave de
        # cache do qty_available ignora a localização: se alguém já tiver lido
        # "Em mãos" nesta transação, a leitura com `location=` devolve o valor
        # cacheado - e subiria o número errado para o Olist, calado, dependendo
        # só da ordem das leituras. Na variante a chave está completa.
        variants = product.product_variant_ids.with_context(
            location=warehouses.lot_stock_id.ids)
        return sum(variants.mapped('qty_available'))

    def _push_stock_to_olist(self, account):
        """Push ONE product's on-hand to Olist as balanco. Returns (status, detail).

        No UI and - deliberately - no raise on a per-product problem (no ISBN,
        not found in Olist, Olist rejection, another company's product): the
        bulk button and the cron call this in a loop and one bad product must
        not stop the others. A genuine configuration error (no token) still
        raises, because it dooms every push.
        """
        self.ensure_one()
        account._check_writable()
        token = account.sudo().token
        if not token:
            raise UserError(_("A conta Olist %s não tem token da API.",
                              account.name))

        company = account.company_id
        # A product owned by another company is not ours to report on: its
        # on-hand belongs to that company's ledger and its Olist id to that
        # company's account. Company-less (shared) products are everyone's.
        if self.company_id and self.company_id != company:
            return 'ERR', _("é da empresa %s", self.company_id.display_name)

        product = self._in_olist_company(company)
        id_produto = product.olist_produto_id
        if not id_produto:
            # Resolve-and-remember, but never CREATE in Olist: find_produto_id
            # only matches an existing catalogue entry by ISBN. Remembered
            # under THIS company - the same ISBN has a different internal id
            # in every other Olist account.
            if not product.barcode:
                return 'ERR', _("sem código de barras (ISBN)")
            id_produto = olist_client.find_produto_id(token, product.barcode)
            if not id_produto:
                return 'ERR', _("não encontrado no Olist")
            product.olist_produto_id = id_produto

        qty = product._olist_stock_qty(account)
        request_body, raw = olist_client.update_estoque(
            token, id_produto, qty, tipo='B',
            observacoes=_("Odoo push: %s") % (product.default_code
                                              or product.barcode or ''))

        # Keep the RAW exchange no matter what: a malformed or throttled
        # response is exactly the case worth being able to read back. The
        # company is named in it because the same product line reads
        # differently in each company.
        status, detail = self._read_estoque_response(raw)
        product.olist_stock_log = (
            "== Olist stock push ==\n"
            "company: %s (conta %s)\n"
            "product: %s (ISBN %s)\n"
            "idProduto: %s\n"
            "estoque do armazém: %s | reservado: %s | margem: %s | "
            "em mãos (referência): %s\n"
            "qty sent (tipo=B): %s\n\n"
            "REQUEST estoque=%s\n\n"
            "RESPONSE %s"
        ) % (company.display_name, account.name,
             product.display_name, product.barcode or '-', id_produto,
             product._olist_wh_qty(account),
             product._olist_reservado_qty(account), account.stock_reserve,
             product.qty_available, qty,
             request_body, raw)
        _logger.info("Olist stock push [%s] %s -> idProduto %s (qty %s): %s",
                     company.name, product.display_name, id_produto, qty, status)
        return status, detail

    @staticmethod
    def _read_estoque_response(raw):
        """(status, human_detail) from the raw response text.

        Never raises: the point is to SEE what came back, so an unparseable
        body is reported as such rather than blowing up.
        """
        try:
            retorno = json.loads(raw).get("retorno", {})
        except (ValueError, AttributeError):
            return 'ERR', raw[:200]
        if retorno.get("status") == "OK":
            registros = retorno.get("registros") or []
            if isinstance(registros, dict):
                registros = [registros]
            saldo = None
            if registros:
                saldo = registros[0].get("registro", {}).get("saldoEstoque")
            return 'OK', saldo if saldo is not None else _("atualizado")
        return 'ERR', retorno.get("erros") or retorno.get("codigo_erro") or raw[:200]

    def action_publish_in_olist(self):
        """Cria no Olist os livros escolhidos que ainda não estão lá.

        O caminho inverso do resto do módulo, e o único que CRIA cadastro no
        Olist. Existe porque a conta tem 446 pbooks nossos ausentes — 80 deles
        com estoque parado no armazém, 9.459 exemplares que ninguém estava
        oferecendo.

        Manda o essencial e nada mais: código (o ISBN), nome, preço, unidade,
        NCM e peso. O que é do marketplace — categoria, SEO, imagens, descrição
        de vitrine — se decide lá, e sobrescrever isso daqui seria o Odoo
        opinando sobre a loja. O saldo NÃO vai junto: quem manda estoque é o
        push, com a margem de segurança e a regra de empresa (§10.5).
        """
        account = self._olist_account()
        account._check_writable()
        token = account.sudo().token
        criados, erros = 0, []
        for template in self:
            if template.olist_mirror_ids:
                erros.append("%s: %s" % (template.display_name[:40],
                                         _("já está no Olist")))
                continue
            if not template.barcode:
                erros.append("%s: %s" % (template.display_name[:40],
                                         _("sem ISBN — é a identidade do livro lá")))
                continue
            ficha = {
                'sequencia': 1,
                'codigo': template.barcode,
                'gtin': template.barcode,
                'nome': template.name,
                'unidade': 'UN',
                'preco': template.list_price,
                'situacao': 'A',
                'tipo': 'P',
                'origem': '0',
            }
            if template.weight:
                ficha['peso_liquido'] = template.weight
                ficha['peso_bruto'] = template.weight
            ncm = getattr(template, 'l10n_br_ncm_code_id', False)
            if ncm and getattr(ncm, 'code', False):
                ficha['ncm'] = ncm.code
            corpo, raw = olist_client.create_produto(token, ficha)
            status, detalhe = self.env['olist.product']._read_alterar_response(raw)
            if status == 'OK':
                criados += 1
            else:
                erros.append("%s: %s" % (template.barcode, detalhe))
            _logger.info("Olist publicar %s (%s): %s | %s",
                         template.display_name, template.barcode, status, corpo[:120])

        notificacao = self.env['olist.product']._notificacao
        if not erros:
            return notificacao(
                _("Publicado no Olist"),
                _("%s livro(s) criados. Leia o catálogo para espelhá-los.",
                  criados), 'success')
        return notificacao(
            _("Publicação parcial"),
            _("%(n)s criados, %(e)s com erro:\n%(lista)s",
              n=criados, e=len(erros), lista="\n".join(erros[:8])),
            'warning', sticky=True)
