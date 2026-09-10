/** @odoo-module **/
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { reactive } from "@odoo/owl";

/* A MESA, AO VIVO.
 *
 * O número de exemplares não pode ser o que veio no carregamento do produto:
 * o balcão do 19 guarda produto no navegador e só rebusca quando o produto
 * MUDA -- e descarregar caixa de livro não escreve nada no produto. Quem
 * abriu o caixa antes de a mercadoria chegar ficava com zero para sempre,
 * mesmo fechando a sessão, movendo e abrindo de novo.
 *
 * Aqui a mesa se pergunta ao servidor: na abertura, de dois em dois minutos e
 * depois de cada venda sincronizada. Se a rede cair -- e feira é lugar de
 * rede ruim -- fica valendo o último número conhecido, que é melhor do que
 * um zero inventado. */
const INTERVALO = 120000;

patch(PosStore.prototype, {
    async setup() {
        this.fairShelf = reactive({ qty: {} });
        await super.setup(...arguments);
        if (this.config?.fair_id) {
            this.refreshFairShelf();
            setInterval(() => this.refreshFairShelf(), INTERVALO);
        }
    },

    async refreshFairShelf() {
        if (!this.config?.fair_id || !this.session?.id) {
            return;
        }
        try {
            const mesa = await this.data.call(
                "pos.session", "get_fair_shelf_qty", [[this.session.id]]);
            for (const chave of Object.keys(this.fairShelf.qty)) {
                if (!(chave in mesa)) {
                    delete this.fairShelf.qty[chave];
                }
            }
            Object.assign(this.fairShelf.qty, mesa);
        } catch {
            // Sem rede o balcão continua vendendo. O número envelhece, e é
            // isso mesmo: inventar zero seria pior.
        }
    },

    async syncAllOrders() {
        const resultado = await super.syncAllOrders(...arguments);
        this.refreshFairShelf();
        return resultado;
    },
});
