# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class CheckidApi(models.Model):
    _name = 'checkid.api'
    _description = 'CheckID API Configuration'
    _rec_name = 'api_name'

    api_name = fields.Char('Nombre de Configuración', required=True, default='CheckID API')
    api_key = fields.Char('API Key', required=True, help='API Key proporcionada por CheckID')
    api_url = fields.Char('URL Base', default='https://www.checkid.mx/api/', required=True)
    active = fields.Boolean('Activo', default=True)
    available_requests = fields.Integer('Solicitudes Disponibles', readonly=True)
    last_update = fields.Datetime('Última Actualización', readonly=True)

    def _get_headers(self):
        return {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def check_available_requests(self):
        if not self.api_key:
            raise UserError(_('API Key no configurada'))

        url = f"{self.api_url}SolicitudesRestantes"
        payload = {
            "ApiKey": self.api_key
        }

        try:
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)

            if response.status_code == 404:
                raise UserError(_('API Key inválida o no encontrada'))
            elif response.status_code != 200:
                raise UserError(_('Error en la petición: %s') % response.status_code)

            data = response.json()

            if data.get('exitoso'):
                self.available_requests = data.get('resultado', 0)
                self.last_update = fields.Datetime.now()
                return data.get('resultado', 0)
            else:
                error_msg = data.get('error', 'Error desconocido')
                error_code = data.get('codigoError', '')
                raise UserError(_('Error en CheckID API (%s): %s') % (error_code, error_msg))

        except requests.RequestException as e:
            _logger.error(f"Error de conexión con CheckID API: {str(e)}")
            raise UserError(_('Error de conexión con CheckID API: %s') % str(e))

    def search_data(self, search_term, get_rfc=True, get_curp=True, get_69=True,
                    get_nss=True, get_regimen=True, get_cp=True, get_weeks=True):
        if not self.api_key:
            raise UserError(_('API Key no configurada'))

        if not search_term:
            raise UserError(_('Término de búsqueda requerido'))

        url = f"{self.api_url}Busqueda"
        payload = {
            "ApiKey": self.api_key,
            "TerminoBusqueda": search_term,
            "ObtenerRFC": get_rfc,
            "ObtenerCURP": get_curp,
            "Obtener69o69B": get_69,
            "ObtenerNSS": get_nss,
            "ObtenerRegimenFiscal": get_regimen,
            "ObtenerCP": get_cp,
            "ObtenerSemanasCotizadas": get_weeks
        }

        try:
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)

            if response.status_code == 404:
                raise UserError(_('API Key inválida o no encontrada'))
            elif response.status_code != 200:
                raise UserError(_('Error en la petición: %s') % response.status_code)

            data = response.json()

            if not data.get('exitoso'):
                error_msg = data.get('error', 'Error desconocido')
                error_code = data.get('codigoError', '')
                raise UserError(_('Error en CheckID API (%s): %s') % (error_code, error_msg))

            return data.get('resultado', {})

        except requests.RequestException as e:
            _logger.error(f"Error de conexión con CheckID API: {str(e)}")
            raise UserError(_('Error de conexión con CheckID API: %s') % str(e))


class CheckidVerification(models.Model):
    _name = 'checkid.verification'
    _description = 'Verificación CheckID'
    _rec_name = 'partner_id'
    _order = 'verification_date desc'

    partner_id = fields.Many2one('res.partner', 'Contacto', required=True, ondelete='cascade')
    search_term = fields.Char('Término Búsqueda', required=True)
    verification_date = fields.Datetime('Fecha Verificación', default=fields.Datetime.now)
    verification_type = fields.Selection([
        ('rfc', 'RFC'),
        ('curp', 'CURP'),
        ('both', 'RFC y CURP')
    ], 'Tipo Verificación', required=True, default='both')

    # Campos de resultado RFC
    rfc_exitoso = fields.Boolean('RFC Exitoso')
    rfc_valido = fields.Boolean('RFC Válido')
    rfc_encontrado = fields.Char('RFC Encontrado')
    razon_social = fields.Char('Razón Social')
    rfc_valido_hasta = fields.Date('RFC Válido Hasta')
    email_contacto = fields.Char('Email Contacto')

    # Campos de resultado CURP
    curp_exitoso = fields.Boolean('CURP Exitoso')
    curp_encontrado = fields.Char('CURP Encontrado')
    nombres = fields.Char('Nombres')
    primer_apellido = fields.Char('Primer Apellido')
    segundo_apellido = fields.Char('Segundo Apellido')
    fecha_nacimiento = fields.Date('Fecha Nacimiento')
    sexo = fields.Char('Sexo')
    nacionalidad = fields.Char('Nacionalidad')
    entidad = fields.Char('Entidad')
    municipio_registro = fields.Char('Municipio Registro')

    # Datos NSS (Número de Seguridad Social)
    nss_verified = fields.Boolean('NSS Verificado')
    nss_number = fields.Char('NSS')
    nss_weeks = fields.Integer('Semanas Cotizadas NSS')

    # Datos Código Postal
    postal_code_verified = fields.Boolean('Código Postal Verificado')
    postal_code = fields.Char('Código Postal')
    municipality = fields.Char('Municipio')
    state = fields.Char('Estado')

    # Estado 69/69B (Lista Negra SAT)
    blacklist_verified = fields.Boolean('Lista Negra Verificada')
    is_blacklisted = fields.Boolean('Está en Lista Negra')
    estado_69_con_problema = fields.Boolean('Con Problemas en Lista')
    estado_69_situacion = fields.Char('Situación Contribuyente')
    estado_69_status = fields.Char('Status Contribuyente')

    # Otros datos - campos antiguos para compatibilidad
    codigo_postal = fields.Char('Código Postal (Legacy)')
    regimen_fiscal = fields.Text('Régimen Fiscal')
    nss = fields.Char('NSS (Legacy)')
    total_semanas_cotizadas = fields.Integer('Total Semanas Cotizadas (Legacy)')

    # Campos de error
    error_code = fields.Char('Código Error')
    error_message = fields.Text('Mensaje Error')

    # Datos JSON completos para referencia
    full_result = fields.Text('Resultado Completo JSON')

    # Campo computado para mostrar resultado formateado
    formatted_result = fields.Html(
        string="Resultado Formateado",
        compute="_compute_formatted_result",
        store=True,
        help="Campo computado para mostrar resultado formateado"
    )

    @api.depends('full_result', 'rfc_exitoso', 'curp_exitoso', 'rfc_encontrado', 'curp_encontrado',
                 'razon_social', 'nombres', 'primer_apellido', 'segundo_apellido')
    def _compute_formatted_result(self):
        """Computar resultado formateado para mostrar en la vista"""
        for record in self:
            if not record.full_result:
                record.formatted_result = "Sin datos disponibles"
                continue

            try:
                import json
                data = json.loads(record.full_result)

                lines = []

                if record.error_message:
                    lines.append(f"ERROR: {record.error_message}")
                else:
                    # RFC
                    if data.get('rfc', {}).get('exitoso'):
                        lines.append("RFC VERIFICADO")
                        rfc_data = data['rfc']
                        if rfc_data.get('rfc'):
                            lines.append(f"   RFC: {rfc_data['rfc']}")
                        if rfc_data.get('razonSocial'):
                            lines.append(f"   Razón Social: {rfc_data['razonSocial']}")
                        if rfc_data.get('valido'):
                            lines.append("   Estado: RFC Válido")
                        else:
                            lines.append("   Estado: RFC No Válido")
                        if rfc_data.get('validoHastaText'):
                            lines.append(f"   Válido hasta: {rfc_data['validoHastaText']}")

                    # CURP
                    if data.get('curp', {}).get('exitoso'):
                        lines.append("")
                        lines.append("CURP VERIFICADO")
                        curp_data = data['curp']
                        if curp_data.get('curp'):
                            lines.append(f"   CURP: {curp_data['curp']}")

                        # Nombre completo
                        nombre_parts = []
                        if curp_data.get('nombres'):
                            nombre_parts.append(curp_data['nombres'])
                        if curp_data.get('primerApellido'):
                            nombre_parts.append(curp_data['primerApellido'])
                        if curp_data.get('segundoApellido'):
                            nombre_parts.append(curp_data['segundoApellido'])

                        if nombre_parts:
                            lines.append(f"   Nombre: {' '.join(nombre_parts)}")

                        if curp_data.get('fechaNacimientoText'):
                            lines.append(f"   Fecha Nacimiento: {curp_data['fechaNacimientoText']}")
                        if curp_data.get('sexo'):
                            lines.append(f"   Sexo: {curp_data['sexo']}")
                        if curp_data.get('entidad'):
                            lines.append(f"   Entidad: {curp_data['entidad']}")

                    # Código Postal
                    if data.get('codigoPostal', {}).get('exitoso'):
                        cp_data = data['codigoPostal']
                        if cp_data.get('codigoPostal'):
                            lines.append("")
                            lines.append(f"CÓDIGO POSTAL: {cp_data['codigoPostal']}")

                    # Régimen Fiscal
                    if data.get('regimenFiscal', {}).get('exitoso'):
                        rf_data = data['regimenFiscal']
                        if rf_data.get('regimenesFiscales'):
                            lines.append("")
                            lines.append("RÉGIMEN FISCAL:")
                            lines.append(f"   {rf_data['regimenesFiscales']}")

                    # NSS
                    if data.get('nss', {}).get('exitoso'):
                        nss_data = data['nss']
                        if nss_data.get('nss'):
                            lines.append("")
                            lines.append(f"NSS: {nss_data['nss']}")

                    # Estado 69
                    if data.get('estado69o69B', {}).get('exitoso'):
                        estado_data = data['estado69o69B']
                        lines.append("")
                        if estado_data.get('conProblema'):
                            lines.append("LISTA NEGRA SAT: SI APARECE")
                            if estado_data.get('detalles'):
                                lines.append(f"   Detalles: {estado_data['detalles']}")
                        else:
                            lines.append("LISTA NEGRA SAT: NO APARECE")

                record.formatted_result = "\n".join(lines) if lines else "Sin datos disponibles"

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                record.formatted_result = f"Error al procesar datos: {str(e)}"

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.partner_id.name} - {record.search_term} ({record.verification_date.strftime('%d/%m/%Y')})"
            result.append((record.id, name))
        return result

    @api.model
    def cleanup_duplicate_actions(self):
        """Método para limpiar acciones duplicadas de CheckID"""
        try:
            # Eliminar acciones window duplicadas
            duplicate_actions = self.env['ir.actions.act_window'].search([
                ('res_model', '=', 'checkid.mass.verification.wizard'),
                ('name', 'ilike', 'checkid')
            ])

            # Mantener solo la acción principal del server action
            main_server_action = self.env.ref('contabilidad_kuale.server_action_checkid_mass_verification',
                                              raise_if_not_found=False)
            if main_server_action:
                duplicate_actions = duplicate_actions.filtered(lambda a: a.id != main_server_action.id)

            if duplicate_actions:
                duplicate_actions.unlink()
                _logger.info(f"Eliminadas {len(duplicate_actions)} acciones window duplicadas")

            # Eliminar server actions duplicadas
            duplicate_servers = self.env['ir.actions.server'].search([
                ('model_id.model', '=', 'res.partner'),
                ('name', 'ilike', 'checkid')
            ])

            # Mantener solo la principal
            if main_server_action:
                duplicate_servers = duplicate_servers.filtered(lambda s: s.id != main_server_action.id)

            if duplicate_servers:
                duplicate_servers.unlink()
                _logger.info(f"Eliminadas {len(duplicate_servers)} server actions duplicadas")

            return True
        except Exception as e:
            _logger.error(f"Error limpiando acciones duplicadas: {str(e)}")
            return False