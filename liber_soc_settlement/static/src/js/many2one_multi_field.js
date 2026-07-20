/**
 * widget="many2one_multi"
 *
 * A Many2one whose "Search more..." dialog lets you tick SEVERAL records and
 * turns each one into a line of the x2many it lives in.
 *
 * Why this is not a flag we forgot to switch on:
 *
 *   1. SelectCreateDialog only draws the checkboxes when `multiSelect` is true,
 *      and web/views/fields/relational_utils.js computes it as
 *          multiSelect: "link" in activeActions ? activeActions.link : false
 *      A Many2one never puts `link` in activeActions -- only a Many2many does.
 *      (Odoo's own comment on that line reads "// LPE Fixme".)
 *
 *   2. Even with the checkboxes, Many2One.many2XAutocompleteProps.update() does
 *      `records[0]` and throws the rest of the selection away, BY CONSTRUCTION:
 *      one field, one value.
 *
 * So both ends have to be reopened: declare `link` to get the checkboxes, and
 * catch the multi-selection before the field discards it.
 *
 * The first record fills the row you are already on; the others become new rows.
 * The parent list is found by looking for the x2many of the parent record that
 * actually contains this row -- never by hardcoding a field name, so the widget
 * works on any x2many.
 */
import { registry } from "@web/core/registry";
import { computeM2OProps, Many2One } from "@web/views/fields/many2one/many2one";
import {
    buildM2OFieldDescription,
    Many2OneField,
} from "@web/views/fields/many2one/many2one_field";

/** many2one.js keeps this private; same shape, our copy. */
function extractData(record) {
    let name;
    if ("display_name" in record) {
        name = record.display_name;
    } else if ("name" in record) {
        name = record.name.id ? record.name.display_name : record.name;
    }
    return { id: record.id, display_name: name };
}

export class Many2OneMulti extends Many2One {
    static props = {
        ...Many2One.props,
        updateMany: { type: Function, optional: true },
    };

    get activeActions() {
        // `link` is the switch that draws the checkboxes.
        return { ...super.activeActions, link: true };
    }

    get many2XAutocompleteProps() {
        const props = super.many2XAutocompleteProps;
        const updateOne = props.update;
        props.update = (records) => {
            if (this.props.updateMany && records && records.length > 1) {
                return this.props.updateMany(records);
            }
            return updateOne(records);
        };
        return props;
    }
}

export class Many2OneMultiField extends Many2OneField {
    static components = { Many2One: Many2OneMulti };

    get m2oProps() {
        return {
            ...computeM2OProps(this.props),
            updateMany: (records) => this.addLines(records),
        };
    }

    /** Find the x2many list of the parent record that holds this very row. */
    get siblingList() {
        const record = this.props.record;
        const parent = record._parentRecord;
        if (!parent) {
            return null;
        }
        return (
            Object.values(parent.data).find(
                (value) => value && value.records && value.records.includes(record)
            ) || null
        );
    }

    async addLines(records) {
        const fieldName = this.props.name;
        const list = this.siblingList;

        // The row we are standing on takes the first pick.
        await this.props.record.update({ [fieldName]: extractData(records[0]) });

        if (!list) {
            // Not inside an x2many (a plain form field): behave like a Many2one
            // and keep the first, rather than pretending we did more.
            return;
        }
        for (const record of records.slice(1)) {
            const line = await list.addNewRecord({ position: "bottom", mode: "readonly" });
            await line.update({ [fieldName]: extractData(record) });
        }
    }
}

registry.category("fields").add("many2one_multi", {
    ...buildM2OFieldDescription(Many2OneMultiField),
});
