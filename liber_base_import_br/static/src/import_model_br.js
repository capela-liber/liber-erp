/** @odoo-module **/

import { BaseImportModel } from "@base_import/import_model";
import { patch } from "@web/core/utils/patch";

/**
 * Brazilian defaults for the import options.
 *
 * The core hardcodes thousands="," decimal="." (import_model.js, in
 * _getCSVFormattingOptions) regardless of language, and the client ALWAYS
 * sends the options along - so the server's auto-detector
 * (base_import.py _infer_separators) never gets to run on the normal path.
 * A price written "59,90" then has its comma stripped as a thousands mark and
 * lands as 5990.00. Values carrying both separators ("1.234,56") are inferred
 * correctly by value, which makes the damage mixed and easy to miss.
 *
 * Same story for dates: with the guess starting from the user's language, an
 * en_US session reads "05/03/2026" as 3 May. A file whose preview rows all
 * have day <= 12 imports entirely transposed, silently.
 *
 * These are only DEFAULTS: the three widgets stay on screen and stay
 * editable, so an American file is still one dropdown away.
 */
patch(BaseImportModel.prototype, {
    _getCSVFormattingOptions() {
        const options = super._getCSVFormattingOptions(...arguments);
        options.float_thousand_separator.value = ".";
        options.float_decimal_separator.value = ",";
        options.date_format.value = "DD/MM/YYYY";
        return options;
    },
});
