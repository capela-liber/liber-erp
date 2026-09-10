/** @odoo-module **/
import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { patch } from "@web/core/utils/patch";

/* Duas informações que faltam no cartão de quem vende numa feira:
 *
 *   - QUANTOS exemplares ainda há na mesa. Contar a pilha com fila na frente
 *     não é opção, e o estoque que o PDV mostra é o do armazém. O número vem
 *     da leitura viva da mesa (`fairShelf`), e não do produto carregado: o
 *     produto fica em cache no navegador e não envelhece quando o estoque
 *     anda;
 *   - QUANTO o livro custa sem o desconto. "De R$ 100 por R$ 50" é o que faz
 *     o desconto da feira valer alguma coisa para quem está do outro lado do
 *     balcão -- e some sozinho nas feiras sem desconto, porque o de-por só
 *     aparece quando a lista de preços do evento realmente abaixa o preço. */
patch(ProductCard.prototype, {
    setup() {
        super.setup(...arguments);
        try {
            this.pos = usePos();
        } catch {
            this.pos = null;
        }
    },

    get fairQty() {
        const produto = this.props.product;
        if (!produto || !this.pos?.config?.fair_id) {
            return null;
        }
        const mesa = this.pos.fairShelf?.qty;
        const quantidade = mesa && produto.id in mesa
            ? mesa[produto.id]
            : produto.fair_qty;
        if (quantidade === undefined || quantidade === null) {
            return null;
        }
        return this.env.utils
            ? this.env.utils.formatProductQty(quantidade, false)
            : String(quantidade);
    },

    /** Zerou a mesa: a etiqueta fica vermelha. */
    get fairQtyIsZero() {
        const mesa = this.pos?.fairShelf?.qty;
        const produto = this.props.product;
        const quantidade = mesa && produto && produto.id in mesa
            ? mesa[produto.id]
            : produto?.fair_qty;
        return !(quantidade > 0);
    },

    /** O preço como a LINHA do pedido o mostra: com ou sem imposto,
     * conforme a configuração do caixa. Mostrar "de 89,90 por 44,95" no
     * cartão e cobrar 51,69 na linha é a mesma reclamação de sempre. */
    _preco(lista) {
        // A lista de preços vai DENTRO de `overridedValues`: passada solta,
        // o núcleo a ignora e os dois preços saem iguais -- o de-por some
        // sem erro nenhum, que foi exatamente o que aconteceu.
        const detalhes = this.props.product.getTaxDetails({
            overridedValues: { pricelist: lista } });
        return this.pos.config.iface_tax_included === "total"
            ? detalhes.total_included
            : detalhes.total_excluded;
    },

    /** "De X por Y", só quando a lista de preços da feira abaixa o preço. */
    get fairPrices() {
        const produto = this.props.product;
        if (!produto || !this.pos?.config?.fair_id) {
            return null;
        }
        const lista = this.pos.getOrder()?.pricelist_id
            || this.pos.config.pricelist_id;
        if (!lista) {
            return null;
        }
        let cheio, agora;
        try {
            cheio = this._preco(false);
            agora = this._preco(lista);
        } catch {
            return null;
        }
        if (!(cheio > agora)) {
            return null;
        }
        return {
            full: this.env.utils.formatCurrency(cheio),
            now: this.env.utils.formatCurrency(agora),
        };
    },
});
