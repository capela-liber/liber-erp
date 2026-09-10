/** @odoo-module **/
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { patch } from "@web/core/utils/patch";
import { formatCurrency } from "@web/core/currency";

/* O de-por também NA LINHA e no cupom.
 *
 * O cartão mostra "de R$ 100 por R$ 50" antes de o livro entrar no pedido;
 * depois de entrar, o cliente vê só o preço com desconto e o desconto some
 * de vista. Como na feira o abatimento vem de LISTA DE PREÇOS (e não do
 * campo de desconto da linha), o aviso de "% de desconto" do núcleo nunca
 * aparece -- ele só sabe olhar o campo.
 *
 * Aqui se compara o preço da linha com o preço cheio do próprio produto. Sem
 * desconto, os dois são iguais e nada é mostrado. */
patch(Orderline.prototype, {
    get fairFullPrice() {
        const linha = this.line;
        const modelo = linha?.product_id?.product_tmpl_id;
        if (!modelo || linha.price_type === "manual") {
            return null;
        }
        const cheio = modelo.getPrice(false, 1, 0, false, linha.product_id);
        const unitario = linha.price_unit;
        if (!(cheio > unitario)) {
            return null;
        }
        const abatimento = Math.round((1 - unitario / cheio) * 100);
        return {
            full: formatCurrency(cheio, linha.currency.id),
            off: abatimento,
        };
    },
});
