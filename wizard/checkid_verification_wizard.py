# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
from datetime import datetime


class CheckidVerificationWizard(models.TransientModel):
    _name = 'checkid.verification.wizard'
    _description = 'Wizard para Verificación CheckID'

    partner_id = fields.Many2one('res.partner', 'Contacto', required=True)
    search_term = fields.Char('RFC o CURP', required=True, help='RFC o CURP a verificar')
    verification_type = fields.Selection([
        ('auto', 'Detectar Automáticamente'),
        ('rfc', 'Solo RFC'),
        ('curp', 'Solo CURP'),
        ('both', 'RFC y CURP')
    ], 'Tipo de Verificación', default='auto', required=True)

    # Opciones de búsqueda
    get_rfc = fields.Boolean('Obtener RFC', default=True)
    get_curp = fields.Boolean('Obtener CURP', default=True)
    get_69 = fields.Boolean('Verificar Lista Negra (69/69B)', default=True)
    get_nss = fields.Boolean('Obtener NSS', default=True)
    get_regimen = fields.Boolean('Obtener Régimen Fiscal', default=True)
    get_cp = fields.Boolean('Obtener Código Postal', default=True)
    get_weeks = fields.Boolean('Obtener Semanas Cotizadas', default=False)

    # Resultados
    verification_result = fields.Text('Resultado', readonly=True)
    verification_successful = fields.Boolean('Verificación Exitosa', readonly=True)

    def action_verify(self):
        """Ejecutar la verificación con CheckID API"""
        self.ensure_one()

        # Buscar configuración activa
        checkid_config = self.env['checkid.api'].search([('active', '=', True)], limit=1)
        if not checkid_config:
            raise UserError(_('No hay configuración activa de CheckID API'))

        try:
            # Ejecutar búsqueda
            result = checkid_config.search_data(
                search_term=self.search_term,
                get_rfc=self.get_rfc,
                get_curp=self.get_curp,
                get_69=self.get_69,
                get_nss=self.get_nss,
                get_regimen=self.get_regimen,
                get_cp=self.get_cp,
                get_weeks=self.get_weeks
            )

            # Crear registro de verificación
            verification_vals = self._prepare_verification_vals(result)
            verification = self.env['checkid.verification'].create(verification_vals)

            # Actualizar wizard con resultado
            self.verification_result = self._format_result(result)
            self.verification_successful = True

            # Actualizar datos del contacto si es exitoso
            self._update_partner_data(result)

            # Mostrar resultado
            return {
                'name': _('Resultado de Verificación'),
                'type': 'ir.actions.act_window',
                'res_model': 'checkid.verification',
                'res_id': verification.id,
                'view_mode': 'form',
                'target': 'new',
            }

        except Exception as e:
            # En caso de error, crear registro de error
            error_vals = {
                'partner_id': self.partner_id.id,
                'search_term': self.search_term,
                'verification_date': fields.Datetime.now(),
                'verification_type': self.verification_type,
                'error_message': str(e),
                'full_result': json.dumps({'error': str(e)})
            }
            self.env['checkid.verification'].create(error_vals)
            raise UserError(_('Error en la verificación: %s') % str(e))

    def _prepare_verification_vals(self, result):
        """Preparar valores para crear el registro de verificación"""
        vals = {
            'partner_id': self.partner_id.id,
            'search_term': self.search_term,
            'verification_date': fields.Datetime.now(),
            'verification_type': self.verification_type if self.verification_type != 'auto' else 'both',
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
                'email_contacto': rfc_data.get('emailContacto', ''),
            })

            # Convertir fecha válido hasta
            valid_until = rfc_data.get('validoHasta')
            if valid_until:
                try:
                    vals['rfc_valido_hasta'] = datetime.fromisoformat(valid_until.replace('T', ' ')).date()
                except:
                    pass

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
                'municipio_registro': curp_data.get('municipioRegistro', ''),
            })

            # Convertir fecha de nacimiento
            birth_date = curp_data.get('fechaNacimiento')
            if birth_date:
                try:
                    vals['fecha_nacimiento'] = datetime.fromisoformat(birth_date.replace('T', ' ')).date()
                except:
                    pass

        # Otros datos
        cp_data = result.get('codigoPostal', {})
        if cp_data and cp_data.get('exitoso'):
            vals['codigo_postal'] = cp_data.get('codigoPostal', '')

        regimen_data = result.get('regimenFiscal', {})
        if regimen_data and regimen_data.get('exitoso'):
            vals['regimen_fiscal'] = regimen_data.get('regimenesFiscales', '')

        nss_data = result.get('nss', {})
        if nss_data and nss_data.get('exitoso'):
            vals['nss'] = nss_data.get('nss', '')

        weeks_data = result.get('semanasCotizadas', {})
        if weeks_data and weeks_data.get('exitoso'):
            vals['total_semanas_cotizadas'] = weeks_data.get('totalSemanasCotizadas', 0)

        # Estado 69/69B
        estado_69_data = result.get('estado69o69B', {})
        if estado_69_data and estado_69_data.get('exitoso'):
            vals['estado_69_con_problema'] = estado_69_data.get('conProblema', False)
            detalles = estado_69_data.get('detalles', {})
            if detalles:
                vals['estado_69_situacion'] = detalles.get('situacionContribuyente', '')
                vals['estado_69_status'] = detalles.get('statusContribuyente', '')

        return vals

    def _format_result(self, result):
        """Formatear resultado para mostrar"""
        lines = []

        # RFC
        rfc_data = result.get('rfc', {})
        if rfc_data:
            lines.append("=== DATOS RFC ===")
            if rfc_data.get('exitoso'):
                lines.append(f"RFC: {rfc_data.get('rfc', '')}")
                lines.append(f"Razón Social: {rfc_data.get('razonSocial', '')}")
                lines.append(f"Válido: {'Sí' if rfc_data.get('valido') else 'No'}")
                if rfc_data.get('validoHasta'):
                    lines.append(f"Válido hasta: {rfc_data.get('validoHastaText', '')}")
                if rfc_data.get('emailContacto'):
                    lines.append(f"Email: {rfc_data.get('emailContacto', '')}")
            else:
                lines.append(f"Error: {rfc_data.get('error', '')}")
            lines.append("")

        # CURP
        curp_data = result.get('curp', {})
        if curp_data:
            lines.append("=== DATOS CURP ===")
            if curp_data.get('exitoso'):
                lines.append(f"CURP: {curp_data.get('curp', '')}")
                lines.append(
                    f"Nombre: {curp_data.get('nombres', '')} {curp_data.get('primerApellido', '')} {curp_data.get('segundoApellido', '')}")
                lines.append(f"Fecha Nacimiento: {curp_data.get('fechaNacimientoText', '')}")
                lines.append(f"Sexo: {curp_data.get('sexo', '')}")
                lines.append(f"Nacionalidad: {curp_data.get('nacionalidad', '')}")
                lines.append(f"Entidad: {curp_data.get('entidad', '')}")
            else:
                lines.append(f"Error: {curp_data.get('error', '')}")
            lines.append("")

        # Estado 69/69B
        estado_69_data = result.get('estado69o69B', {})
        if estado_69_data:
            lines.append("=== LISTA NEGRA SAT ===")
            if estado_69_data.get('exitoso'):
                con_problema = estado_69_data.get('conProblema', False)
                lines.append(f"Con problemas: {'Sí' if con_problema else 'No'}")
                if con_problema:
                    detalles = estado_69_data.get('detalles', {})
                    if detalles:
                        lines.append(f"Situación: {detalles.get('situacionContribuyente', '')}")
                        lines.append(f"Status: {detalles.get('statusContribuyente', '')}")
            lines.append("")

        return "\n".join(lines)

    def _update_partner_data(self, result):
        """Actualizar datos del contacto con información verificada"""
        update_vals = {}

        # Actualizar RFC si se obtuvo
        rfc_data = result.get('rfc', {})
        if rfc_data and rfc_data.get('exitoso') and rfc_data.get('rfc'):
            update_vals['rfc'] = rfc_data['rfc']
            if rfc_data.get('razonSocial') and not self.partner_id.name:
                update_vals['name'] = rfc_data['razonSocial']

        # Actualizar CURP si se obtuvo
        curp_data = result.get('curp', {})
        if curp_data and curp_data.get('exitoso') and curp_data.get('curp'):
            update_vals['curp'] = curp_data['curp']

        # Actualizar código postal
        cp_data = result.get('codigoPostal', {})
        if cp_data and cp_data.get('exitoso') and cp_data.get('codigoPostal'):
            update_vals['zip'] = cp_data['codigoPostal']

        # Actualizar estado de lista negra
        estado_69_data = result.get('estado69o69B', {})
        if estado_69_data and estado_69_data.get('exitoso'):
            update_vals['rfc_blacklist'] = estado_69_data.get('conProblema', False)

        if update_vals:
            self.partner_id.write(update_vals)