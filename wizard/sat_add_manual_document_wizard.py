from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SatAddExternalDocumentWizard(models.TransientModel):
    _name = 'sat.add.external.document.wizard'
    _description = 'Wizard para agregar documentos externos al ADD'

    file = fields.Binary(string="Archivo", required=True, help="Archivo a adjuntar (PDF, XLSX, DOCX, etc.)")

    file_name = fields.Char(string="Nombre del Archivo", required=True)

    @api.constrains('file_name')
    def _check_extension(self):
        for rec in self:
            if not rec.file_name:
                continue
            ext = rec.file_name.split('.')[-1].lower()
            allowed = ('pdf', 'xlsx', 'xls', 'docx', 'doc', 'xml')
            if ext not in allowed:
                raise UserError(_(
                    'Formato no permitido: %s\n\nSolo se permiten: PDF, XLSX, XLS, DOCX, DOC, XML'
                ) % ext)

    def action_create_document(self):
        """Crea un registro en sat.xml.invoices para que aparezca en 'Documentos Disponibles'"""
        self.ensure_one()

        if not self.file or not self.file_name:
            raise UserError(_('Debes seleccionar un archivo.'))

        ext = self.file_name.split('.')[-1].lower()

        vals = {
            'name': self.file_name,
            'xml_file': self.file, #Guardamos el binario aunque no sea XML
            'xml_file_name': self.file_name,
            'document_type': 'documento_externo',
            'add_status': 'available',
            'add_user_id': False,
            'is_external_document': True,
        }

        self.env['sat.xml.invoices'].create(vals)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Documento agregado'),
                'message': _('El documento se ha agregado correctamente a Documentos Disponibles.'),
                'type': 'success',
                'sticky': False,
            }
        }
