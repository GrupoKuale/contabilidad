from odoo import models, fields, api
from mimetypes import guess_type


class AdditionalFile(models.Model):
    _name = 'contabilidad_kuale.additional_file'
    _description = 'Gestor de archivos mixin'

    file = fields.Binary(string='Archivo', required=True, attachment=True, attachment_name=lambda self: self.file_name)
    file_name = fields.Char(string='Nombre del archivo')
    description = fields.Char(string='Descripción')
    file_type = fields.Selection([
        ('pdf', 'PDF'),
        ('xml', 'XML'),
        ('image', 'Imagen'),
        ('other', 'Otro')
    ], string='Tipo de Archivo', readonly=True)

    @api.onchange('file', 'file_name')
    def _onchange_file(self):
        for record in self:
            if record.file_name:
                mime_type, _ = guess_type(record.file_name)
                if mime_type:
                    if mime_type.startswith('application/pdf'):
                        record.file_type = 'pdf'
                    elif mime_type.startswith('application/xml'):
                        record.file_type = 'xml'
                    elif mime_type.startswith('image'):
                        record.file_type = 'image'
                    else:
                        record.file_type = 'other'


    @api.model
    def delete_temporary_pdfs(self):
        print('deleting...')
        temp_files = self.search([('file_name', '=', 'temporaly_pdf.pdf')])
        count = len(temp_files)
        temp_files.unlink()
        print(f"Se eliminaron {count} archivos temporales 'temporaly_pdf.pdf'.")

    def action_view_file(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/contabilidad_kuale.additional_file/{self.id}/file/{self.file_name}',
            'target': 'new',
        }

    invoice_complaint_id = fields.Many2one(
        'contabilidad_kuale.invoice_complaint_ticket',
        string='Problemas de Facturacion',
        ondelete='cascade'
    )

    invoice_id = fields.Many2one(
        'account.move',
        string = 'Factura',
        ondelete='cascade'
    )

    ticket_monitor_id = fields.Many2one(
        'contabilidad_kuale.ticket_monitor',
        string='Ticket Monitor',
        ondelete='cascade'
    )

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Orden de Compra',
        ondelete='cascade'
    )


    sale_system_summary_id = fields.Many2one(
        'contabilidad_kuale.sales_system_summary',
        string='Ticket Monitor',
        ondelete='cascade'
    )

