# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import base64
import io
import zipfile
import logging
import json

_logger = logging.getLogger(__name__)


class SATUserADD(models.Model):
    _name = 'sat.user.add'
    _description = 'ADD Usuario - Administrador de Documentos Digitales'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'
    _order = 'user_id'

    
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        required=True,
        default=lambda self: self.env.user,
        ondelete='cascade',
        tracking=True,
        help='Usuario propietario de este ADD'
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )
    
    active = fields.Boolean(
        'Activo',
        default=True,
        tracking=True
    )
    
    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True
    )
    
    
    invoice_ids = fields.One2many(
        'sat.xml.invoices',
        'add_user_id',
        string='Documentos en ADD',
        domain=[('add_status', 'in', ['locked', 'processed'])],
        help='Todos los documentos asignados a este usuario'
    )
    
    
    total_documents = fields.Integer(
        string='Total Documentos',
        compute='_compute_statistics',
        store=True
    )
    
    total_recibidos = fields.Integer(
        string='Total Recibidos',
        compute='_compute_statistics',
        store=True
    )
    
    total_emitidos = fields.Integer(
        string='Total Emitidos',
        compute='_compute_statistics',
        store=True
    )
    
    total_facturas = fields.Integer(
        string='Total Facturas',
        compute='_compute_statistics',
        store=True
    )
    
    total_pagos = fields.Integer(
        string='Total Pagos',
        compute='_compute_statistics',
        store=True
    )
    
    total_nominas = fields.Integer(
        string='Total Nóminas',
        compute='_compute_statistics',
        store=True
    )
    
    total_amount = fields.Float(
        string='Importe Total',
        compute='_compute_statistics',
        store=True,
        help='Suma total de importes de documentos'
    )
    
    total_locked = fields.Integer(
        string='Documentos Bloqueados',
        compute='_compute_statistics',
        store=True,
        help='Documentos en estado bloqueado (en proceso)'
    )
    
    total_processed = fields.Integer(
        string='Documentos Procesados',
        compute='_compute_statistics',
        store=True,
        help='Documentos ya procesados completamente'
    )
    
    
    date_created = fields.Datetime(
        string='Fecha Creación',
        default=fields.Datetime.now,
        readonly=True,
        tracking=True
    )
    
    last_update = fields.Datetime(
        string='Última Actualización',
        compute='_compute_last_update',
        store=True
    )
    
    
    auto_process = fields.Boolean(
        string='Procesamiento Automático',
        default=False,
        tracking=True,
        help='Procesar automáticamente los documentos al agregarlos al ADD'
    )
    
    notes = fields.Text(
        string='Notas',
        tracking=True,
        help='Notas personales sobre el uso del ADD'
    )

    # ========== RESTRICCIONES SQL ==========
    
    _sql_constraints = [
        ('user_company_unique', 
         'UNIQUE(user_id, company_id)', 
         'Ya existe un ADD para este usuario en esta compañía.'),
    ]

    
    @api.depends('user_id', 'company_id')
    def _compute_display_name(self):
        """Genera el nombre del ADD"""
        for record in self:
            if record.user_id:
                record.display_name = f"ADD - {record.user_id.name}"
            else:
                record.display_name = "ADD - Sin Usuario"
    
    @api.depends('invoice_ids', 'invoice_ids.add_status', 'invoice_ids.document_type', 
                 'invoice_ids.document_group', 'invoice_ids.factura_total')
    def _compute_statistics(self):
        """Calcula las estadísticas del ADD"""
        for record in self:
            invoices = record.invoice_ids
            
            record.total_documents = len(invoices)
            record.total_recibidos = len(invoices.filtered(lambda x: x.document_type == 'recibido'))
            record.total_emitidos = len(invoices.filtered(lambda x: x.document_type == 'emitido'))
            record.total_facturas = len(invoices.filtered(lambda x: x.document_group == 'factura'))
            record.total_pagos = len(invoices.filtered(lambda x: x.document_group == 'pago'))
            record.total_nominas = len(invoices.filtered(lambda x: x.document_group == 'nomina'))
            record.total_locked = len(invoices.filtered(lambda x: x.add_status == 'locked'))
            record.total_processed = len(invoices.filtered(lambda x: x.add_status == 'processed'))
            record.total_amount = sum(invoices.mapped('factura_total'))
    
    @api.depends('invoice_ids.add_date')
    def _compute_last_update(self):
        """Calcula la fecha de última actualización"""
        for record in self:
            if record.invoice_ids:
                dates = record.invoice_ids.mapped('add_date')
                dates_filtered = [d for d in dates if d]
                record.last_update = max(dates_filtered) if dates_filtered else False
            else:
                record.last_update = False

    
    @api.model
    def create(self, vals):
        """Override create para asegurar que exista solo un ADD por usuario/compañía"""
        user_id = vals.get('user_id', self.env.user.id)
        company_id = vals.get('company_id', self.env.company.id)
        
        # Buscar ADD existente
        existing = self.search([
            ('user_id', '=', user_id),
            ('company_id', '=', company_id)
        ], limit=1)
        
        if existing:
            _logger.info(f'ADD ya existe para usuario {user_id}, retornando existente')
            return existing
        
        record = super(SATUserADD, self).create(vals)
        _logger.info(f'ADD creado para usuario: {record.user_id.name}')
        
        return record

    
    def action_add_documents(self, invoice_ids=None):
        """
        Agrega múltiples documentos al ADD del usuario
        """
        self.ensure_one()
        
        if not invoice_ids:
            raise UserError(_('Debe seleccionar al menos un documento para agregar.'))
        
        invoices = self.env['sat.xml.invoices'].browse(invoice_ids)
        
        # Validar que todos estén disponibles
        unavailable = invoices.filtered(lambda x: x.add_status != 'available' or x.add_user_id)
        if unavailable:
            raise UserError(_(
                'Los siguientes documentos no están disponibles:\n%s'
            ) % '\n'.join(unavailable.mapped('tfd_uuid')))
        
        # Agregar al ADD
        invoices.write({
            'add_user_id': self.user_id.id,
            'add_status': 'locked',
            'add_date': fields.Datetime.now(),
        })
        
        _logger.info(f' {len(invoices)} documentos agregados al ADD de {self.user_id.name}')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Documentos Agregados'),
                'message': _('%s documentos agregados a su ADD correctamente.') % len(invoices),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_remove_documents(self, invoice_ids=None):
        """
        Remueve múltiples documentos del ADD
        """
        self.ensure_one()
        
        if not invoice_ids:
            raise UserError(_('Debe seleccionar al menos un documento para remover.'))
        
        invoices = self.env['sat.xml.invoices'].browse(invoice_ids)
        
        # Validar que pertenezcan a este usuario
        not_owned = invoices.filtered(lambda x: x.add_user_id.id != self.user_id.id)
        if not_owned:
            raise UserError(_('Solo puede remover documentos de su propio ADD.'))
        
        # Remover del ADD
        invoices.write({
            'add_user_id': False,
            'add_status': 'available',
            'add_date': False,
        })
        
        _logger.info(f' {len(invoices)} documentos removidos del ADD de {self.user_id.name}')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Documentos Removidos'),
                'message': _('%s documentos removidos de su ADD.') % len(invoices),
                'type': 'info',
                'sticky': False,
            }
        }
    
    def action_mark_as_processed(self, invoice_ids=None):
        """
        Marca documentos como procesados
        """
        self.ensure_one()
        
        if not invoice_ids:
            raise UserError(_('Debe seleccionar al menos un documento.'))
        
        invoices = self.env['sat.xml.invoices'].browse(invoice_ids)
        
        # Validar que pertenezcan a este usuario
        not_owned = invoices.filtered(lambda x: x.add_user_id.id != self.user_id.id)
        if not_owned:
            raise UserError(_('Solo puede procesar documentos de su propio ADD.'))
        
        # Marcar como procesado
        invoices.write({'add_status': 'processed'})
        
        _logger.info(f' {len(invoices)} documentos marcados como procesados')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Documentos Procesados'),
                'message': _('%s documentos marcados como procesados.') % len(invoices),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_export_xmls(self, invoice_ids=None):
        """
        Exporta los XMLs seleccionados como archivo ZIP
        """
        self.ensure_one()
        
        if not invoice_ids:
            raise UserError(_('Debe seleccionar al menos un documento para exportar.'))
        
        invoices = self.env['sat.xml.invoices'].browse(invoice_ids)
        
        # Validar que pertenezcan a este usuario
        not_owned = invoices.filtered(lambda x: x.add_user_id.id != self.user_id.id)
        if not_owned:
            raise UserError(_('Solo puede exportar documentos de su propio ADD.'))
        
        # Filtrar solo los que tienen XML
        invoices_with_xml = invoices.filtered(lambda x: x.xml_file)
        
        if not invoices_with_xml:
            raise UserError(_('Los documentos seleccionados no tienen archivos XML.'))
        
        # Crear archivo ZIP en memoria
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for invoice in invoices_with_xml:
                xml_content = base64.b64decode(invoice.xml_file)
                filename = invoice.xml_file_name or f'{invoice.tfd_uuid}.xml'
                zip_file.writestr(filename, xml_content)
        
        zip_buffer.seek(0)
        zip_data = base64.b64encode(zip_buffer.read())
        
        # Crear attachment
        attachment = self.env['ir.attachment'].create({
            'name': f'XMLs_ADD_{self.user_id.name}_{fields.Date.today()}.zip',
            'type': 'binary',
            'datas': zip_data,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/zip',
        })
        
        _logger.info(f'ZIP creado con {len(invoices_with_xml)} XMLs para {self.user_id.name}')
        
        # Retornar acción de descarga
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
    
    def action_open_my_add(self):
        """
        Abre el ADD del usuario actual
        """
        user_add = self.search([
            ('user_id', '=', self.env.user.id),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not user_add:
            # Crear ADD si no existe
            user_add = self.create({
                'user_id': self.env.user.id,
                'company_id': self.env.company.id,
            })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mi ADD',
            'res_model': 'sat.user.add',
            'view_mode': 'form',
            'res_id': user_add.id,
            'target': 'current',
        }
    
    def action_view_documents(self):
        """
        Abre la vista de documentos del ADD
        """
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Documentos - {self.display_name}',
            'res_model': 'sat.xml.invoices',
            'view_mode': 'tree,form',
            'domain': [('add_user_id', '=', self.user_id.id)],
            'context': {
                'search_default_my_add': 1,
                'default_add_user_id': self.user_id.id,
            },
        }
    
    def action_refresh_statistics(self):
        """
        Refresca las estadísticas del ADD
        """
        self._compute_statistics()
        self._compute_last_update()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Estadísticas Actualizadas'),
                'message': _('Las estadísticas del ADD han sido actualizadas.'),
                'type': 'info',
                'sticky': False,
            }
        }
    
    @api.model
    def get_or_create_user_add(self, user_id=None):
        """
        Obtiene o crea el ADD del usuario
        Retorna el ID del registro
        """
        if not user_id:
            user_id = self.env.user.id
        
        user_add = self.search([
            ('user_id', '=', user_id),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not user_add:
            user_add = self.create({
                'user_id': user_id,
                'company_id': self.env.company.id,
            })
        
        return {
            'id': user_add.id,
            'user_id': user_add.user_id.id,
            'display_name': user_add.display_name,
        }

class SatAddViewPreset(models.Model):
    _name = 'sat.add.view.preset'
    _description = "Presets de Vistas del ADD"

    name = fields.Char('Nombre de la Vista', required=True)
    user_id = fields.Many2one('res.users', string='Usuario', required=True, default=lambda self: self.env.user)
    fields_json = fields.Text('Campos JSON', required=True, help="Lista de campos en formato JSON")

    @api.model
    def create_preset(self, name, fields_list):
        """Crea un nuevo preset para el usuario actual"""
        return self.create({
            'name': name,
            'user_id': self.env.user.id,
            'fields_json': json.dumps(fields_list)
        }).id

    @api.model
    def get_user_presets(self):
        """Obtiene los presets del usuario actual"""
        presets = self.search([('user_id', '=', self.env.user.id)])
        return [{'id': p.id, 'name': p.name, 'fields': json.loads(p.fields_json)} for p in presets]

    @api.model
    def delete_preset(self, preset_id):
        """Elimina un preset"""
        preset = self.browse(preset_id)
        if preset.user_id != self.env.user:
            raise UserError(_("No puedes eliminar un preset que no es tuyo."))
        preset.unlink()
        return True