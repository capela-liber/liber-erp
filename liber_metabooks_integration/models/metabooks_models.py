from odoo import fields, models, api

class MetaBooksBISACCodes(models.Model):
    _name = 'biblio.bisac.codes'
    _description = "BISAC Codes"
    _rec_name = 'bisac_category'
    _order = "sequence, bisac_category"

    bisac_code = fields.Char('Bisac Code')
    bisac_prefix = fields.Char('Bisac Prefix')
    bisac_category = fields.Char('Bisac Categories', translate=True)
    bisac_product_category = fields.Many2one('product.category', string="Product Category")
    sequence = fields.Integer(help="Gives the sequence order when displaying a list of bisac categories.")

    # Remove old functionality: Through bisac update product category
    # def update_bisac_categories(self):
    #     for rec in self:
    #         bisac_categories = rec.bisac_category.split('/')
    #         if rec.bisac_code:
    #             codes = [rec.bisac_code[i*3:(i+1)*3] for i in range(int(len(rec.bisac_code)/3))]
    #             parent_categ_id = False
    #             for i in range(len(bisac_categories)):
    #                 category_name = bisac_categories[i]
    #                 if len(codes) < i+1:
    #                     code = '000'
    #                 else:
    #                     code = codes[i]
    #                 category_name += "[" + code + "]"
    #                 if category_name:
    #                     categ_id = rec.env['product.category'].search([('name', '=', category_name),
    #                                                                    ('parent_id', '=', parent_categ_id)
    #                                                                    ], limit=1)
    #                     if not categ_id:
    #                         categ_id = rec.env['product.category'].create({
    #                             'name': category_name,
    #                             'parent_id': parent_categ_id
    #                         })
    #                     parent_categ_id = categ_id.id
    #             rec.bisac_product_category = parent_categ_id


class MetabooksBookSubjects(models.Model):
    _name = 'metabooks.book.subjects'
    _description = "Metabooks Subjects"
    _rec_name = 'metabooks_subject_code'

    name = fields.Char('Subject Heading')
    metabooks_subject_code = fields.Char('Subject Code')
    metabooks_subject_scheme_version = fields.Char('Subject Scheme Version')
    metabooks_subject_source_name = fields.Char('Source name')
    metabooks_subject_identifier = fields.Char('Subject Identifier')
    metabooks_main_subject = fields.Boolean('Main Subject')
    metabooks_bisac_code = fields.Many2one('biblio.bisac.codes', string='Bisac', compute='get_bisac_code', store=True)

    @api.depends('metabooks_subject_code')
    def get_bisac_code(self):
        for rec in self:
            bisac_code = rec.env['biblio.bisac.codes'].search([
                ('bisac_code', '=', rec.metabooks_subject_code)], limit=1).id
            if not bisac_code:
                bisac_code = rec.env['biblio.bisac.codes'].create({
                    'bisac_code': rec.metabooks_subject_code,
                    'bisac_prefix': rec.metabooks_subject_code[0:3],
                })
            rec.metabooks_bisac_code = bisac_code


class MetabooksProductType(models.Model):
    _name = 'metabooks.book.type'
    _description = "Metabooks Type"

    name = fields.Char('Product Type')


class MetabooksAuthorRole(models.Model):
    _name = 'author.contributor.role'
    _description = "Metabooks Author Contributor"

    name = fields.Char('Author Code')
    header_role = fields.Char('Heading Role')


class MetabooksAuthorPublisherInherit(models.Model):
    _name = 'metabooks.auther.publiser'

    name = fields.Char("Name")
    is_auther = fields.Boolean("Is Auther")
    is_publiser = fields.Boolean("Is Publiser")

    author_last_name = fields.Char('Last Name')
    auhor_biographical_note = fields.Char('Biographical note')
    author_contributor_role = fields.Many2one('author.contributor.role', string='Contributor Role')
    author_professional_position = fields.Char('Professional Position')
    author_sequence_number = fields.Integer('Sequence Number')
    author_full_name = fields.Char(string='Contributor', compute='get_contributor_full_name', store=True)
    author_role = fields.Char(related='author_contributor_role.header_role', string='Role')

    @api.depends('name', 'author_last_name')
    def get_contributor_full_name(self):
        for rec in self:
            rec.author_full_name = (rec.name if rec.name else "") + " " + (rec.author_last_name if rec.author_last_name
                                                                           else "")


class MetabooksIsbnSubjects(models.Model):
    _name = 'isbn.book.subjects'
    _description = 'metabooks book subjects'

    name = fields.Char('Subjects')


class MetabooksProductIdentifierType(models.Model):
    _name = 'metabooks.product.identifier'
    _description = 'Identifier Type'

    id_value = fields.Char('Identifier ID')
    metabooks_identifier_type = fields.Char('Identifier Type')


class MetabooksProductAvalaibility(models.Model):
    _name = 'metabooks.avalaibility.definition'
    _description = "Metabooks Avalaibility"
    _rec_name = 'product_definition'
    _order = 'identify_number'

    identify_number = fields.Char('Availability Code')
    product_definition = fields.Char('Description')
    product_notes = fields.Text('Notes')
