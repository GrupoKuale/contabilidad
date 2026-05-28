# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class CheckidMassVerificationWizard(models.TransientModel):
    _name = 'checkid.mass.verification.wizard'
    _description = 'Wizard para Verificación Masiva CheckID'

    partner_ids = fields.Many2many('res.partner', string='Contactos a Verificar')
    verification_type = fields.Selection([
        ('rfc', 'Solo RFC'),
        ('curp', 'Solo CURP'),
        ('both', 'RFC y CURP')
    ], 'Tipo de Verificación', default='both', required=True)

    # Campos de estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('processing', 'Procesando'),
        ('done', 'Completado')
    ], 'Estado', default='draft', readonly=True)

    progress = fields.Float('Progreso', readonly=True, help='Porcentaje de progreso de la verificación')
    current_partner_name = fields.Char('Contacto Actual', readonly=True)

    # Opciones de búsqueda
    get_rfc = fields.Boolean('Obtener RFC', default=True)
    get_curp = fields.Boolean('Obtener CURP', default=True)
    get_69 = fields.Boolean('Verificar Lista Negra (69/69B)', default=True)
    get_nss = fields.Boolean('Obtener NSS', default=True)
    get_regimen = fields.Boolean('Obtener Régimen Fiscal', default=True)
    get_cp = fields.Boolean('Obtener Código Postal', default=True)
    get_weeks = fields.Boolean('Obtener Semanas Cotizadas', default=False)

    # Resultados
    verification_summary = fields.Text('Resumen de Verificación', readonly=True)
    total_partners = fields.Integer('Total de Contactos', readonly=True)
    partner_count = fields.Integer('Número de Contactos', compute='_compute_partner_count', readonly=True)
    processed_count = fields.Integer('Contactos Procesados', readonly=True)
    successful_verifications = fields.Integer('Verificaciones Exitosas', readonly=True)
    successful_count = fields.Integer('Exitosas', readonly=True)
    failed_verifications = fields.Integer('Verificaciones Fallidas', readonly=True)
    failed_count = fields.Integer('Fallidas', readonly=True)

    # Campos adicionales para evitar errores
    error_count = fields.Integer('Errores', readonly=True)
    warning_count = fields.Integer('Advertencias', readonly=True)
    completed = fields.Boolean('Completado', readonly=True)
    start_time = fields.Datetime('Hora de Inicio', readonly=True)
    end_time = fields.Datetime('Hora de Finalización', readonly=True)

    @api.model
    def default_get(self, fields_list):
        """Obtener contactos seleccionados del contexto"""
        result = super().default_get(fields_list)

        # Obtener IDs de contactos del contexto
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            result['partner_ids'] = [(6, 0, active_ids)]
            result['total_partners'] = len(active_ids)

        return result

    @api.depends('partner_ids')
    def _compute_partner_count(self):
        """Calcular el número de contactos seleccionados"""
        for record in self:
            record.partner_count = len(record.partner_ids)

    def action_verify_mass(self):
        """Ejecutar la verificación masiva con CheckID API"""
        self.ensure_one()

        if not self.partner_ids:
            raise UserError(_('No hay contactos seleccionados para verificar'))

        # Inicializar estado
        self.state = 'processing'
        self.start_time = fields.Datetime.now()
        self.progress = 0.0
        self.processed_count = 0

        # Buscar configuración activa
        checkid_config = self.env['checkid.api'].search([('active', '=', True)], limit=1)
        if not checkid_config:
            raise UserError(_('No hay configuración activa de CheckID API'))

        successful = 0
        failed = 0
        summary_lines = []

        for partner in self.partner_ids:
            try:
                # Determinar qué verificar según los datos del contacto
                search_term = None
                debug_info = f"Partner {partner.name}: RFC={partner.rfc}, CURP={partner.curp}, VAT={partner.vat}"

                if partner.rfc and self.verification_type in ['rfc', 'both']:
                    search_term = partner.rfc
                    debug_info += f" -> Usando RFC: {search_term}"
                elif partner.curp and self.verification_type in ['curp', 'both']:
                    search_term = partner.curp
                    debug_info += f" -> Usando CURP: {search_term}"
                elif partner.vat and self.verification_type in ['rfc', 'both']:
                    search_term = partner.vat
                    debug_info += f" -> Usando VAT: {search_term}"
                else:
                    # Si no hay RFC o CURP, usar el VAT si existe
                    if partner.vat:
                        search_term = partner.vat
                        debug_info += f" -> Usando VAT fallback: {search_term}"
                    else:
                        summary_lines.append(f"❌ {partner.name}: Sin RFC/CURP para verificar ({debug_info})")
                        failed += 1
                        continue

                # Ejecutar búsqueda
                result = checkid_config.search_data(
                    search_term=search_term,
                    get_rfc=self.get_rfc,
                    get_curp=self.get_curp,
                    get_69=self.get_69,
                    get_nss=self.get_nss,
                    get_regimen=self.get_regimen,
                    get_cp=self.get_cp,
                    get_weeks=self.get_weeks
                )

                # Crear registro de verificación
                verification_vals = self._prepare_verification_vals(partner, search_term, result)
                verification = self.env['checkid.verification'].create(verification_vals)

                # Verificar si la verificación fue exitosa
                is_successful = False
                rfc_data = result.get('rfc', {})
                curp_data = result.get('curp', {})

                # Debug info simplificado
                debug_info += f" -> RFC exitoso: {rfc_data.get('exitoso', False)}"
                debug_info += f" -> CURP exitoso: {curp_data.get('exitoso', False)}"

                # Lógica simplificada: si cualquier dato existe y es exitoso
                if self.verification_type == 'rfc':
                    is_successful = bool(rfc_data.get('exitoso'))
                elif self.verification_type == 'curp':
                    is_successful = bool(curp_data.get('exitoso'))
                elif self.verification_type == 'both':
                    is_successful = bool(rfc_data.get('exitoso')) or bool(curp_data.get('exitoso'))

                # Si no hay éxito directo, revisar si hay datos válidos
                if not is_successful:
                    if rfc_data.get('rfc') or curp_data.get('curp'):
                        is_successful = True
                        debug_info += " -> Exitoso por datos encontrados"

                # Log para debugging
                _logger.info(f"DEBUG CheckID: {debug_info} -> Success: {is_successful}")

                if is_successful:
                    # Actualizar datos del contacto si es exitoso
                    self._update_partner_data(partner, result)
                    status = self._get_verification_status(result)
                    summary_lines.append(f"✅ {partner.name}: {status}")
                    successful += 1
                else:
                    # Verificación falló
                    error_msg = "Sin datos válidos encontrados"
                    if result.get('mensaje'):
                        error_msg = result['mensaje']
                    summary_lines.append(f"❌ {partner.name}: {error_msg}")
                    failed += 1

            except Exception as e:
                # En caso de error, crear registro de error
                error_vals = {
                    'partner_id': partner.id,
                    'search_term': search_term or '',
                    'verification_date': fields.Datetime.now(),
                    'verification_type': self.verification_type,
                    'error_message': str(e),
                    'full_result': json.dumps({'error': str(e)})
                }
                self.env['checkid.verification'].create(error_vals)

                summary_lines.append(f"❌ {partner.name}: Error - {str(e)}")
                failed += 1

        # Actualizar resumen
        self.successful_verifications = successful
        self.successful_count = successful  # Sincronizar campo
        self.failed_verifications = failed
        self.failed_count = failed  # Sincronizar campo
        self.processed_count = successful + failed
        self.error_count = failed
        self.warning_count = 0
        self.verification_summary = "\n".join(summary_lines)
        self.state = 'done'
        self.progress = 100.0
        self.completed = True
        self.end_time = fields.Datetime.now()
        self.current_partner_name = False

        # Mostrar resultado
        return {
            'name': _('Resultado de Verificación Masiva'),
            'type': 'ir.actions.act_window',
            'res_model': 'checkid.mass.verification.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _prepare_verification_vals(self, partner, search_term, result):
        """Preparar valores para crear el registro de verificación"""
        vals = {
            'partner_id': partner.id,
            'search_term': search_term,
            'verification_date': fields.Datetime.now(),
            'verification_type': self.verification_type,
            'full_result': json.dumps(result, default=str)
        }

        # Datos RFC
        rfc_data = result.get('rfc', {})
        if rfc_data:
            vals.update({
                'rfc_exitoso': rfc_data.get('exitoso', False),
                'rfc_valido': rfc_data.get('valido', False),
                'rfc_encontrado': rfc_data.get('rfc', ''),
                'razon_social': rfc_data.get('razonSocial', ''),
                'regimen_fiscal': str(rfc_data.get('regimenFiscal', '')),
                'email_contacto': rfc_data.get('email', ''),
            })

        # Datos CURP
        curp_data = result.get('curp', {})
        if curp_data:
            vals.update({
                'curp_exitoso': curp_data.get('exitoso', False),
                'curp_encontrado': curp_data.get('curp', ''),
                'nombres': curp_data.get('nombres', ''),
                'primer_apellido': curp_data.get('primerApellido', ''),
                'segundo_apellido': curp_data.get('segundoApellido', ''),
                'sexo': curp_data.get('sexo', ''),
                'nacionalidad': curp_data.get('nacionalidad', ''),
                'entidad': curp_data.get('entidad', ''),
            })

        # Datos NSS (usar campos legacy compatibles)
        nss_data = result.get('nss', {})
        if nss_data:
            vals.update({
                'nss': nss_data.get('nss', ''),
                'total_semanas_cotizadas': nss_data.get('semanasCotizadas', 0),
            })

        # Datos código postal (usar campo legacy compatible)
        cp_data = result.get('codigoPostal', {})
        if cp_data:
            vals.update({
                'codigo_postal': cp_data.get('codigoPostal', ''),
                'municipio_registro': cp_data.get('municipio', ''),
            })

        # Estado 69/69B (usar campos existentes)
        estado_69_data = result.get('estado69o69B', {})
        if estado_69_data:
            vals.update({
                'estado_69_con_problema': estado_69_data.get('conProblema', False),
                'estado_69_situacion': estado_69_data.get('situacion', ''),
                'estado_69_status': estado_69_data.get('status', ''),
            })

        return vals

    def _get_verification_status(self, result):
        """Obtener estado de verificación para el resumen"""
        status_parts = []

        rfc_data = result.get('rfc', {})
        if rfc_data and rfc_data.get('exitoso'):
            status_parts.append("RFC OK")

        curp_data = result.get('curp', {})
        if curp_data and curp_data.get('exitoso'):
            status_parts.append("CURP OK")

        estado_69_data = result.get('estado69o69B', {})
        if estado_69_data and estado_69_data.get('exitoso'):
            if estado_69_data.get('conProblema'):
                status_parts.append("Lista Negra")
            else:
                status_parts.append("Sin Problemas SAT")

        return ", ".join(status_parts) if status_parts else "Verificado"

    def _update_partner_data(self, partner, result):
        """Actualizar datos del contacto con información verificada"""
        update_vals = {}

        # Actualizar RFC si se obtuvo
        rfc_data = result.get('rfc', {})
        if rfc_data and rfc_data.get('exitoso') and rfc_data.get('rfc'):
            if not partner.rfc:
                update_vals['rfc'] = rfc_data['rfc']
            if rfc_data.get('razonSocial') and not partner.name:
                update_vals['name'] = rfc_data['razonSocial']

        # Actualizar CURP si se obtuvo
        curp_data = result.get('curp', {})
        if curp_data and curp_data.get('exitoso') and curp_data.get('curp'):
            if not partner.curp:
                update_vals['curp'] = curp_data['curp']

        # Actualizar código postal
        cp_data = result.get('codigoPostal', {})
        if cp_data and cp_data.get('exitoso') and cp_data.get('codigoPostal'):
            if not partner.zip:
                update_vals['zip'] = cp_data['codigoPostal']

        # Actualizar estado de lista negra
        estado_69_data = result.get('estado69o69B', {})
        if estado_69_data and estado_69_data.get('exitoso'):
            update_vals['rfc_blacklist'] = estado_69_data.get('conProblema', False)

        if update_vals:
            partner.write(update_vals)

    def action_view_verifications(self):
        """Ver todas las verificaciones creadas"""
        verification_ids = self.env['checkid.verification'].search([
            ('partner_id', 'in', self.partner_ids.ids),
            ('verification_date', '>=', fields.Datetime.now().replace(hour=0, minute=0, second=0))
        ]).ids

        return {
            'name': _('Verificaciones CheckID'),
            'type': 'ir.actions.act_window',
            'res_model': 'checkid.verification',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', verification_ids)],
        }