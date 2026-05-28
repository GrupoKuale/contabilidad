import requests
import logging
from odoo import models, fields
from odoo.exceptions import ValidationError,UserError
from odoo import api
import re
import unicodedata
from datetime import datetime
import json
import base64
import qrcode
from io import BytesIO
_logger = logging.getLogger(__name__)

#TODO: TERMINAR DE VALIDAR TODOS LOS DATOS ANTES DE ENVIARLO - ***
###### VALIDACIÓN DE CUENTAS ######
def _validar_cuenta(cuenta, tipo_cuenta):
    if not cuenta or not tipo_cuenta:
        return

    cuenta = cuenta.strip()

    if not cuenta.isdigit():
        raise ValidationError("La cuenta unicamente debe contener solo números.")

    if tipo_cuenta.clave == '40':  # CLABE
        if not cuenta.isdigit() or len(cuenta) != 18:
            raise ValidationError(
                "La CLABE debe contener exactamente 18 dígitos numéricos."
            )

    elif tipo_cuenta.clave == '3':  # Tarjeta débito
        if not cuenta.isdigit() or not len(cuenta) != 16:
            raise ValidationError(
                "La tarjeta de débito debe contener entre 16  dígitos."
            )

    elif tipo_cuenta.clave == '10':  # Teléfono celular
        if not cuenta.isdigit() or len(cuenta) != 10:
            raise ValidationError(
                "El teléfono celular debe contener exactamente 10 dígitos."
            )

def _validar_cuentas_ordenante(cuenta):
    if not cuenta:
        raise ValidationError("Debe ingresar una cuenta para realizar la consulta.")

    cuenta = cuenta.strip()

    if not cuenta.isdigit():
        raise ValidationError("La cuenta únicamente debe contener números.")

    longitud = len(cuenta)

    if longitud == 18 :
        return

    elif longitud == 16:
        return

    elif longitud == 10:
        return

    else:
        raise ValidationError(
            "La cuenta debe tener:\n"
            "- 18 dígitos (CLABE)\n"
            "- 16 dígitos (Tarjeta)\n"
            "- 10 dígitos (Teléfono celular)"
        )
###### VALIDACIÓN DE CURP ######
def _validar_rfc_curp(valor):
    if not valor:
        raise ValidationError("El RFC ó CURP es obligatorio para realizar la orden.")

    valor = valor.strip().upper()

    # Solo letras y números
    if not re.fullmatch(r'[A-Z0-9]+', valor):
        raise ValidationError(
            f"El RFC ó CURP solo debe contener letras y números, sin espacios ni caracteres especiales."
        )

    # RFC persona moral (12)
    # RFC persona física (13)
    # CURP (18)
    if len(valor) not in (12, 13, 18):
        raise ValidationError(
            f"El RFC ó CURP debe tener 12, 13 (RFC) o 18 (CURP) caracteres."
        )

class STPOrderRegister(models.Model):
    _name = 'stp.order.register.wizard'
    _description = 'STP Order Register'
    _rec_name = 'clave_rastreo'
    _sql_constraints = [
        (
            'unique_stp_operation',
            'unique(clave_rastreo, fecha_operacion, institucion_operante)',
            'La Clave de Rastreo debe ser única por Fecha de Operación e Institución Operante.'
        )
    ]
    _index = True

    empresa_id = fields.Many2one('stp.empresa', string="Empresa",required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    clave_rastreo_preview = fields.Char(string="Clave Rastreo",readonly=True, help="Clave de rastreo asociada a la orden de pago. Debe ser única por operación y por día. La longitud mínima debe ser de 8 caracteres.", index=True)
    clave_rastreo = fields.Char(string="Clave Rastreo", readonly=True)
    monto = fields.Float(string="Monto",required=True, help="El monto máximo por orden de Transferencia de la orden de pago que se manejará en el SPEI será de: 999999999999.99", default=9999.99)
    referencia_numerica = fields.Char(string="Referencia Numerica",required=True, help="Una referencia numérica asociada al pago de maximo 7 digitos.")
    fecha_operacion = fields.Date(string="Fecha de Operación",required=True,default=fields.Date.context_today, index=True)
    estado = fields.Selection([
        ('registrada', 'Registrada'),
        ('liquidada', 'Liquidada'),
        ('devuelta', 'Devuelta'),
        ('cancelada', 'Cancelada'),
    ], default='registrada', string="Estado")
    concepto_pago = fields.Char(string="Concepto Pago", default="Esto es una prueba")

    institucion_operante_id = fields.Many2one('stp.institucion',string="Institución Operante",required=True, help="La clave de la institución que genera el pago", index=True)
    tipo_cuenta_ordenante_id = fields.Many2one('stp.tipo.cuenta', string="Tipo de Cuenta del Ordenante", required=True, help="Tipo de cuenta ordenante")
    nombre_ordenante = fields.Char(string="Nombre del Ordenante",required=True, help="El nombre del ordenante asociado a ésta orden de pago.", default="Nombre Prueba")
    cuenta_ordenante = fields.Char(string="Cuenta del Ordenante",required=True, help="La cuenta del ordenante.", default="646180693400000003")
    rfc_curp_ordenante = fields.Char(string="RFC ó CURP del Ordenante",required=True, help="El RFC o CURP del ordenante.", default="PROB0908074R4")

    institucion_contraparte_id = fields.Many2one('stp.institucion', string="Institución Contraparte",required=True, help="La clave de la institución a la que va dirigida el pago de acuerdo con el Catálogo Instituciones")
    tipo_cuenta_beneficiario_id = fields.Many2one('stp.tipo.cuenta', string="Tipo de Cuenta del Beneficiario",required=True, help="La clave del tipo cuenta del beneficiario según el Catalogó Tipo Cuenta.")
    nombre_beneficiario = fields.Char(string="Nombre del Beneficiario",required=True, help="El nombre del beneficiario de la orden de pago.", default="Nombre Prueba")
    cuenta_beneficiario = fields.Char(string="Cuenta del Beneficiario",required=True, help="La cuenta del beneficiario.", default="646180693400000001")
    rfc_curp_beneficiario = fields.Char(string="RFC ó CURP del Beneficiario",required=True, help="El RFC o CURP del beneficiario.", default="PRUE0908074R4")

    latitud = fields.Char(required=True, help="Coordenada correspondiente a la longitud.", default="19.370312")
    longitud = fields.Char(required=True, help="Coordenada correspondiente a la latitud.", default="-99.180617")

    stp_id = fields.Char(string="STP ID", help="El ID del STP")
    stp_descripcionError = fields.Text(string="Descripción STP")

    ######## CLAVE DE RASTREO ########
    def _limpiar_texto_stp(self, texto):
        if not texto:
            return ""

        texto = unicodedata.normalize("NFKD", texto)
        texto = texto.encode("ascii", "ignore").decode("ascii")
        texto = re.sub(r"[^A-Za-z0-9]", "", texto)
        return texto.upper()

    @api.onchange('empresa_id')
    def _onchange_preview_clave(self):
        for record in self:
            if record.empresa_id:
                empresa_clean = record._limpiar_texto_stp(record.empresa_id.nombre)
                fecha = datetime.today().strftime("%Y%m%d")
                secuencia = self.env['ir.sequence'].next_by_code(
                    'stp.clave.rastreo'
                )

                record.clave_rastreo_preview = f"{empresa_clean}{fecha}{secuencia}"

    @api.model
    def create(self, vals):
        if not vals.get('clave_rastreo'):

            empresa_clean = ""

            if vals.get('empresa_id'):
                empresa = self.env['stp.empresa'].browse(vals['empresa_id'])
                empresa_clean = self._limpiar_texto_stp(empresa.nombre)

            fecha = datetime.today().strftime("%Y%m%d")

            secuencia = self.env['ir.sequence'].next_by_code(
                'stp.clave.rastreo'
            )

            vals['clave_rastreo'] = f"{empresa_clean}{fecha}{secuencia}"

        return super().create(vals)

    @api.constrains('clave_rastreo')
    def _check_clave_rastreo(self):
        for record in self:
            if not record.clave_rastreo:
                continue

            if len(record.clave_rastreo) < 8:
                raise ValidationError("La Clave de Rastreo debe tener mínimo 8 caracteres.")

            if not re.match(r'^[A-Za-z0-9]+$', record.clave_rastreo):
                raise ValidationError(
                    "La Clave de Rastreo solo puede contener letras y números (sin espacios ni símbolos)."
                )

    ######## REFERENCIA NUMERICA ########
    @api.constrains('referencia_numerica')
    def _check_referencia_numerica(self):
        for record in self:
            if not record.referencia_numerica:
                if not re.fullmatch(r'\d{1,7}', record.referencia_numerica):
                    raise ValidationError(
                        "La referencia numérica debe contener únicamente números y máximo 7 dígitos."
                    )

    ######## VALIDACIÓN DE CUENTAS ########
    @api.constrains('cuenta_beneficiario','tipo_cuenta_beneficiario_id','cuenta_ordenante','tipo_cuenta_ordenante_id')
    def _check_cuentas(self):
        for record in self:
            # Validar beneficiario
            _validar_cuenta(record.cuenta_beneficiario,record.tipo_cuenta_beneficiario_id)

            # Validar ordenante
            _validar_cuenta(record.cuenta_ordenante,record.tipo_cuenta_ordenante_id)

    @api.onchange('cuenta_beneficiario', 'cuenta_ordenante')
    def _onchange_limpiar_cuentas(self):
        if self.cuenta_beneficiario:
            self.cuenta_beneficiario = self.cuenta_beneficiario.strip()

        if self.cuenta_ordenante:
            self.cuenta_ordenante = self.cuenta_ordenante.strip()

    ######## RFC o CURP ########
    @api.onchange('rfc_curp_ordenante', 'rfc_curp_beneficiario')
    def _onchange_rfc_curp(self):
        if self.rfc_curp_ordenante:
            self.rfc_curp_ordenante = self.rfc_curp_ordenante.strip().upper()

        if self.rfc_curp_beneficiario:
            self.rfc_curp_beneficiario = self.rfc_curp_beneficiario.strip()

    @api.constrains('rfc_curp_ordenante', 'rfc_curp_beneficiario')
    def _validar_rfc_curp(self):
        for record in self:
            _validar_rfc_curp(record.rfc_curp_ordenante)
            _validar_rfc_curp(record.rfc_curp_beneficiario,)

    ########  ########
    def actualizar_estado(self, nuevo_estado):
        for record in self:
            if record.estado in ['devuelta', 'cancelada'] and nuevo_estado == 'liquidada':
                return  # Ignorar actualización inválida

            record.estado = nuevo_estado
    # =========================
    # MÉTODO BOTÓN
    # =========================
    def action_enviar_stp(self):
        self.ensure_one()

        # =========================
        # VALIDACIONES EXTRA
        # =========================
        if self.monto <= 0:
            raise UserError("El monto debe ser mayor a 0.")

        if len(self.referencia_numerica) > 7:
            raise UserError("La referencia numérica no puede exceder 7 dígitos.")

        #Aqui creo el Payload que voy a enviar
        payload = {
            "empresa": self.empresa_id.nombre,
            "conceptoPago": self.concepto_pago,
            "claveRastreo": self.clave_rastreo,
            "monto": "{:.2f}".format(self.monto),
            "referenciaNumerica": self.referencia_numerica,
            "institucionOperante": self.institucion_operante_id.clave,
            "tipoCuentaOrdenante": self.tipo_cuenta_ordenante_id.clave,
            "nombreOrdenante": self.nombre_ordenante,
            "cuentaOrdenante": self.cuenta_ordenante,
            "rfcCurpOrdenante": self.rfc_curp_ordenante,
            "institucionContraparte": self.institucion_contraparte_id.clave,
            "tipoCuentaBeneficiario": self.tipo_cuenta_beneficiario_id.clave,
            "nombreBeneficiario": self.nombre_beneficiario,
            "cuentaBeneficiario": self.cuenta_beneficiario,
            "rfcCurpBeneficiario": self.rfc_curp_beneficiario,
            "latitud": self.latitud,
            "longitud": self.longitud,
            "tipoPago": "1"
        }

        try:
            respuesta = self.env['stp.service'].registrar_orden(payload)
        except Exception as e:
            raise UserError(f"Error al conectar con STP:\n{str(e)}")

        # =========================
        # PROCESAMIENTO RESPUESTA
        # =========================
        if not respuesta:
            raise UserError("No se recibió respuesta de STP.")

        resultado = respuesta.get("resultado") or respuesta

        stp_id = resultado.get("Id") or resultado.get("id")

        self.stp_id = stp_id
        self.stp_descripcionError = resultado.get("descripcionError")

        # =========================
        # VALIDACIÓN ÉXITO
        # =========================
        if stp_id and int(stp_id) > 0:
            self.estado = 'registrada'
            mensaje = "Operación correcta."
            tipo = "success"
        else:
            self.estado = 'cancelada'
            mensaje = f"Error en STP: {resultado.get('descripcionError') or 'Error desconocido'}"
            tipo = "danger"

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Resultado STP',
                'message': mensaje,
                'type': tipo,
                'sticky': False,
            }
        }
###### CONSULTA FECHA ACTUAL ######
class STPOrderConsultCurrentDate(models.TransientModel):
    _name = 'stp.consult.order.current.date'
    _description = 'STP Order Consult Current Date'

    company_id = fields.Many2one('stp.empresa', string="Empresa",required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    page = fields.Float(string="Pagina", default=0)

    response = fields.Text(string="Resultado", readonly=True)
    line_ids = fields.One2many('stp.consult.order.current.date.line','wizard_id',string="Operaciones")
    total = fields.Integer("Total")
    pagina = fields.Integer("Página")
    total_paginas = fields.Integer("Total Páginas")
    ts_captura = fields.Datetime("Fecha Captura")

    def action_consult_current_date(self):
        self.ensure_one()

        # Contrucción del payload
        payload = {
            "empresa": self.company_id.nombre,
            "pagina": int(self.page),
        }

        try:
            service = self.env['stp.service']
            data = service.consult_order_current_date(payload)

            self.line_ids.unlink()

            self.total = data.get('total')
            self.pagina = data.get('pagina')
            self.total_paginas = data.get('totalPaginas')

            for item in data.get('datos', []):
                fecha_raw = item.get('fechaOperacion')
                fecha_convertida = False

                if fecha_raw:
                    fecha_convertida = datetime.strptime(
                        str(fecha_raw),
                        "%Y%m%d"
                    ).date()

                ts_raw = item.get('tsCaptura')
                fecha_captura = False

                if ts_raw:
                    fecha_captura = datetime.fromtimestamp(
                        ts_raw / 1000
                    )

                self.env['stp.consult.order.current.date.line'].create({
                    'wizard_id': self.id,
                    'clave_rastreo': item.get('claveRastreo'),
                    'monto': item.get('monto'),
                    'estado': item.get('estado'),
                    'nombre_beneficiario': item.get('nombreBeneficiario'),
                    'cuenta_beneficiario': item.get('cuentaBeneficiario'),
                    'fecha_operacion': fecha_convertida,
                    'ts_captura': fecha_captura,
                    'url_cep': item.get('urlCEP'),
                })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"Error inesperado: {str(e)}")

class STPOrderConsultCurrentDateLine(models.TransientModel):
    _name = 'stp.consult.order.current.date.line'
    _description = 'STP Consult Current Date Line'

    wizard_id = fields.Many2one(
        'stp.consult.order.current.date',
        ondelete='cascade'
    )

    clave_rastreo = fields.Char("Clave Rastreo")
    monto = fields.Float("Monto")
    estado = fields.Char("Estado")
    nombre_beneficiario = fields.Char("Beneficiario")
    cuenta_beneficiario = fields.Char("Cuenta Beneficiario")
    fecha_operacion = fields.Date("Fecha Operación")
    url_cep = fields.Char("CEP")

    ts_captura = fields.Datetime("Fecha Captura")


    def action_open_cep(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_url',
            'url': self.url_cep,
            'target': 'new',
        }
###### CONSULTA HISTORICO ######
class STPOrderConsultHistorical(models.TransientModel):
    _name = 'stp.consult.order.historical'
    _description = 'STP Order Consult Historical'

    operation_date = fields.Date(string="Fecha de Operación",required=True, default=fields.Date.context_today, index=True)
    company_id = fields.Many2one('stp.empresa', string="Empresa",required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    page = fields.Integer(string="Pagina", default=0)

    response = fields.Text(string="Resultado", readonly=True)
    #Datos Response
    line_ids = fields.One2many('stp.consult.order.historical.date.line','wizard_id',string="Operaciones")
    total = fields.Integer("Total")
    pagina = fields.Integer("Página")
    total_paginas = fields.Integer("Total Páginas")
    ts_captura = fields.Datetime("Fecha Captura")

    def action_consult_historical_date(self):
        self.ensure_one()

        fecha_int = int(self.operation_date.strftime('%Y%m%d'))

        # Contrucción del payload
        payload = {
            "fechaOperacion": fecha_int,
            "empresa": self.company_id.nombre,
            "pagina": int(self.page),
        }

        try:
            service = self.env['stp.service']
            data = service.consult_order_historical_date(payload)
            # Si STP responde error funcional
            if data.get('estado') != 0:
                raise UserError(data.get('mensaje') or "Error en consulta STP")

            self.line_ids.unlink()

            self.total = data.get('total')
            self.pagina = data.get('pagina')
            self.total_paginas = data.get('totalPaginas')

            for item in data.get('datos', []):
                fecha_raw = item.get('fechaOperacion')
                fecha_convertida = False

                if fecha_raw:
                    fecha_convertida = datetime.strptime(
                        str(fecha_raw),
                        "%Y%m%d"
                    ).date()

                ts_raw = item.get('tsCaptura')
                fecha_captura = False

                if ts_raw:
                    fecha_captura = datetime.fromtimestamp(
                        ts_raw / 1000
                    )

                self.env['stp.consult.order.historical.date.line'].create({
                    'wizard_id': self.id,
                    'clave_rastreo': item.get('claveRastreo'),
                    'monto': item.get('monto'),
                    'estado': item.get('estado'),
                    'nombre_beneficiario': item.get('nombreBeneficiario'),
                    'cuenta_beneficiario': item.get('cuentaBeneficiario'),
                    'fecha_operacion': fecha_convertida,
                    'ts_captura': fecha_captura,
                    'url_cep': item.get('urlCEP'),
                })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"{str(e)}")

class STPOrderConsultHistoricalDateLine(models.TransientModel):
    _name = 'stp.consult.order.historical.date.line'
    _description = 'STP Consult Historical Date Line'

    wizard_id = fields.Many2one(
        'stp.consult.order.historical',
        ondelete='cascade'
    )

    clave_rastreo = fields.Char("Clave Rastreo")
    monto = fields.Float("Monto")
    estado = fields.Char("Estado")
    nombre_beneficiario = fields.Char("Beneficiario")
    cuenta_beneficiario = fields.Char("Cuenta Beneficiario")
    fecha_operacion = fields.Date("Fecha Operación")
    url_cep = fields.Char("CEP")

    ts_captura = fields.Datetime("Fecha Captura")


    def action_open_cep_historical(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_url',
            'url': self.url_cep,
            'target': 'new',
        }
###### CONSULTA NATURAL ######
class STPOrderConsultNatural(models.TransientModel):
    _name = 'stp.consult.order.natural'
    _description = 'STP Order Consult Natural'

    natural_date = fields.Date(string="Fecha Natural",required=True, default=fields.Date.context_today, index=True)
    time_capture_start = fields.Float(string="Hora Captura Inicio", required=True,default=0.0)
    time_capture_end = fields.Float(string="Hora Captura Final", required=True,default=23.9997)
    company_id = fields.Many2one('stp.empresa', string="Empresa",required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    page = fields.Float(string="Pagina", default=0)

    response = fields.Text(string="Resultado", readonly=True)
    #Datos Response
    line_ids = fields.One2many('stp.consult.order.natural.line','wizard_id',string="Operaciones")
    total = fields.Integer("Total")
    pagina = fields.Integer("Página")
    total_paginas = fields.Integer("Total Páginas")
    ts_captura = fields.Datetime("Fecha Captura")

    def _float_to_hms(self, value):
        hours = int(value)
        minutes = int((value - hours) * 60)
        seconds = int(round((((value - hours) * 60) - minutes) * 60))
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def action_consult_natural(self):
        self.ensure_one()

        fecha_int = int(self.natural_date.strftime("%Y%m%d"))

        hora_inicio = self._float_to_hms(self.time_capture_start)
        hora_fin = self._float_to_hms(self.time_capture_end)

        payload = {
            "fechaNatural": fecha_int,
            "horaCapturaInicio": hora_inicio,
            "horaCapturaFin": hora_fin,
            "empresa": self.company_id.nombre,
            "pagina": int(self.page),
        }

        try:
            service = self.env['stp.service']
            data = service.consult_order_natural_date(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta, espera unos minutos e intenta consultar nuevamente.")
            # Si STP responde error funcional
            if data.get('estado') != 0:
                raise UserError(data.get('mensaje') or "Error en consulta STP")

            self.line_ids.unlink()

            self.total = data.get('total')
            self.pagina = data.get('pagina')
            self.total_paginas = data.get('totalPaginas')

            for item in data.get('datos', []):
                fecha_raw = item.get('fechaOperacion')
                fecha_convertida = False

                if fecha_raw:
                    fecha_convertida = datetime.strptime(
                        str(fecha_raw),
                        "%Y%m%d"
                    ).date()

                ts_raw = item.get('tsCaptura')
                fecha_captura = False

                if ts_raw:
                    fecha_captura = datetime.fromtimestamp(
                        ts_raw / 1000
                    )

                self.env['stp.consult.order.natural.line'].create({
                    'wizard_id': self.id,
                    'clave_rastreo': item.get('claveRastreo'),
                    'monto': item.get('monto'),
                    'estado': item.get('estado'),
                    'nombre_beneficiario': item.get('nombreBeneficiario'),
                    'cuenta_beneficiario': item.get('cuentaBeneficiario'),
                    'fecha_operacion': fecha_convertida,
                    'ts_captura': fecha_captura,
                    'url_cep': item.get('urlCEP'),
                })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"{str(e)}")

class STPOrderConsultNaturalLine(models.TransientModel):
    _name = 'stp.consult.order.natural.line'
    _description = 'STP Consult Natural Line'

    wizard_id = fields.Many2one(
        'stp.consult.order.natural',
        ondelete='cascade'
    )

    clave_rastreo = fields.Char("Clave Rastreo")
    monto = fields.Float("Monto")
    estado = fields.Char("Estado")
    nombre_beneficiario = fields.Char("Beneficiario")
    cuenta_beneficiario = fields.Char("Cuenta Beneficiario")
    fecha_operacion = fields.Date("Fecha Operación")
    url_cep = fields.Char("CEP")
    ts_captura = fields.Datetime("Fecha Captura")

    def action_open_cep_natural(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_url',
            'url': self.url_cep,
            'target': 'new',
        }
###### CONSULTA SALDO EN CUENTA ######
class STPOrderConsultAccountBalance(models.TransientModel):
    _name = 'stp.consult.account.balance'
    _description = 'STP Order Consult Account Balance'

    company_id = fields.Many2one('stp.empresa', string="Empresa",required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    ordering_account = fields.Char(string="Cuenta del Ordenante",required=True, help="La cuenta del ordenante.", default="646180693400000003")

    response = fields.Text(string="Resultado", readonly=True)
    line_ids = fields.One2many('stp.consult.account.balance.line','wizard_id',string="Operaciones")

    ######## VALIDACIÓN DE CUENTAS ########
    @api.constrains('ordering_account')
    def _check_cuentas(self):
        for record in self:
            # Validar Cuenta
            _validar_cuentas_ordenante(record.ordering_account)

    @api.onchange('ordering_account')
    def _onchange_limpiar_cuentas(self):
        if self.ordering_account:
            self.ordering_account = self.ordering_account.strip()

    ######## CONSULTA ########
    def action_consult_account_balance(self):
        self.ensure_one()

        # Contrucción del payload
        payload = {
            "empresa": self.company_id.nombre,
            "cuentaOrdenante": self.ordering_account,
        }

        try:
            service = self.env['stp.service']
            data = service.consult_account_balance(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta, espera unos minutos e intenta consultar nuevamente.")
            # Si STP responde error funcional
            if data.get('estado') != 0:
                raise UserError(data.get('mensaje') or "Error en consulta STP")

            self.line_ids.unlink()

            respuesta = data.get('respuesta')

            if not respuesta:
                raise UserError("No se recibió información de saldo.")

            self.env['stp.consult.account.balance.line'].create({
                'wizard_id': self.id,
                'cargos_pendientes': respuesta.get('cargosPendientes'),
                'saldo': respuesta.get('saldo'),
            })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"Error inesperado: {str(e)}")

class STPOrderConsultAccountBalanceLine(models.TransientModel):
    _name = 'stp.consult.account.balance.line'
    _description = 'STP Consult Acoount Balance Line'

    wizard_id = fields.Many2one(
        'stp.consult.account.balance',
        ondelete='cascade'
    )

    cargos_pendientes = fields.Float(string="Cargos Pendientes")
    saldo = fields.Float(string="Saldo")

    def action_open_cep_account_balance(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
        }
###### CONSULTA SALDO EN CUENTA HISTORICO ######
class STPOrderConsultAccountBalanceHistorical(models.TransientModel):
    _name = 'stp.consult.account.balance.historical'
    _description = 'STP Order Consult Account Balance Historical'

    company_id = fields.Many2one('stp.empresa', string="Empresa",required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    ordering_account = fields.Char(string="Cuenta del Ordenante",required=True, help="La cuenta del ordenante.", default="646180693400000003")
    date = fields.Date(string="Fecha",required=True, default=fields.Date.context_today, index=True)

    response = fields.Text(string="Resultado", readonly=True)
    line_ids = fields.One2many('stp.consult.account.balance.historical.line','wizard_id',string="Operaciones")

    ######## VALIDACIÓN DE CUENTAS ########
    @api.constrains('ordering_account')
    def _check_cuentas(self):
        for record in self:
            # Validar Cuenta
            _validar_cuentas_ordenante(record.ordering_account)

    @api.onchange('ordering_account')
    def _onchange_limpiar_cuentas(self):
        if self.ordering_account:
            self.ordering_account = self.ordering_account.strip()

    ######## CONSULTA ########
    def action_consult_account_balance_historical(self):
        self.ensure_one()

        fecha_int = int(self.date.strftime('%Y%m%d'))

        # Contrucción del payload
        payload = {
            "empresa": self.company_id.nombre,
            "cuentaOrdenante": self.ordering_account,
            "fecha": fecha_int,
        }

        try:
            service = self.env['stp.service']
            data = service.consult_account_balance_historical(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta, espera unos minutos e intenta consultar nuevamente.")
            # Si STP responde error funcional
            if data.get('estado') != 0:
                raise UserError(data.get('mensaje') or "Error en consulta STP")

            self.line_ids.unlink()

            respuesta = data.get('respuesta')

            if not respuesta:
                raise UserError("No se recibió información de saldo histórico.")

            self.line_ids.unlink()

            self.env['stp.consult.account.balance.historical.line'].create({
                'wizard_id': self.id,
                'cargos_pendientes': respuesta.get('cargosPendientes'),
                'saldo': respuesta.get('saldo'),
                'date': self.date,
            })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"Error inesperado: {str(e)}")

class STPOrderConsultAccountBalanceHistoricalLine(models.TransientModel):
    _name = 'stp.consult.account.balance.historical.line'
    _description = 'STP Consult Acoount Balance Historical Line'

    wizard_id = fields.Many2one(
        'stp.consult.account.balance.historical',
        ondelete='cascade'
    )

    cargos_pendientes = fields.Float(string="Cargos Pendientes")
    saldo = fields.Float(string="Saldo")
    date = fields.Date(string="Fecha",required=True, default=fields.Date.context_today, index=True)

    def action_open_cep_account_balance(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
        }
###### CONSULTA COMPROBANTE STP FECHA NATURAL ######
class STPOrderConsultReceiptNaturalDate(models.TransientModel):
    _name = 'stp.consult.receipt.naturaldate'
    _description = 'STP Consult Receipt Natural Date'

    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    tracking_key = fields.Char(string="Clave Rastreo", required=True , help="Clave de rastreo asociada a la orden de pago. Debe ser única por operación y por día. La longitud mínima debe ser de 8 caracteres.", index=True)
    natural_date = fields.Date(string="Fecha Natural",required=True, default=fields.Date.context_today, index=True)

    response = fields.Text(string="Resultado", readonly=True)

    ######## CONSULTA ########
    def action_consult_receipt_naturaldate(self):
        self.ensure_one()

        fecha_int = int(self.natural_date.strftime('%Y%m%d'))

        # Construcción del payload
        payload = {
            "empresa": self.company_id.nombre,
            "claveRastreo": self.tracking_key,
            "fechaNatural": fecha_int,
        }

        try:
            service = self.env['stp.service']
            data = service.consult_receipt_natural_date(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta.")

            if data.get('estado') != 0:
                raise UserError(data.get('mensaje') or "Error en consulta STP")

            pdf_base64 = data.get('bytesComprobante')

            if not pdf_base64:
                raise UserError("No se recibió el comprobante")

            attachment = self.env['ir.attachment'].create({
                'name': 'Comprobante_STP.pdf',
                'type': 'binary',
                'datas': pdf_base64,
                'mimetype': 'application/pdf',
            })

            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=false',
                'target': 'new',
            }

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"Error inesperado: {str(e)}")
###### CONSULTA COMPROBANTE STP FECHA OPERATIVA ######
class STPOrderConsultReceiptOperationDate(models.TransientModel):
    _name = 'stp.consult.receipt.operation.date'
    _description = 'STP Consult Receipt Operation Date'

    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    tracking_key = fields.Char(string="Clave Rastreo", required=True , help="Clave de rastreo asociada a la orden de pago. Debe ser única por operación y por día. La longitud mínima debe ser de 8 caracteres.", index=True)
    operation_date = fields.Date(string="Fecha Operación",required=True, default=fields.Date.context_today, index=True)

    response = fields.Text(string="Resultado", readonly=True)

    ######## CONSULTA ########
    def action_consult_receipt_operation_date(self):
        self.ensure_one()

        fecha_int = int(self.operation_date.strftime('%Y%m%d'))

        #Construccion del Payload
        payload = {
            "empresa": self.company_id.nombre,
            "claveRastreo": self.tracking_key,
            "fechaOperacion": fecha_int,
        }

        try:
            service = self.env['stp.service']
            data = service.consult_receipt_operation_date(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta.")

            if data.get('estado') != 0:
                raise UserError(data.get('mensaje') or "Error en consulta STP")

            pdf_base64 = data.get('bytesComprobante')

            if not pdf_base64:
                raise UserError('No se recibió el comprobante')

            attachment = self.env['ir.attachment'].create({
                'name': 'Comprobante_STP.pdf',
                'type': 'binary',
                'datas': pdf_base64,
                'mimetype': 'application/pdf',
            })

            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=false',
                'target': 'new',
            }

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"Error inesperado: {str(e)}")
###### CONSULTA CONCILIACIÓN SALDO HISTORICO ######
class STPOrderConsultBalanceConciliationHistorical(models.TransientModel):
    _name = 'stp.consult.balance.conciliation.historical'
    _description = 'STP Consult Balance Conciliation Historical'

    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    operation_date = fields.Date(string="Fecha Operación",required=True, default=fields.Date.context_today, index=True)
    page = fields.Integer(string="Pago", default=0)

    response = fields.Text(string="Resultado", readonly=True)
    line_ids = fields.One2many('stp.consult.balance.conciliation.historical.line','wizard_id',string="Operaciones")
    total = fields.Integer(string="Total")
    pagina = fields.Integer(string="Página")
    total_paginas = fields.Integer(string="Total Páginas")
    saldo_inicial = fields.Float(string="Saldo Inicial")
    ts_captura = fields.Datetime(string="Fecha Captura")

    ######## CONSULTA ########
    def action_consult_balance_conciliation_historical(self):
        self.ensure_one()

        fecha_int = int(self.operation_date.strftime('%Y%m%d'))

        # Contrucción del Payload
        payload = {
            "fechaOperacion": fecha_int,
            "empresa": self.company_id.nombre,
            "pagina": int(self.page),
        }

        try:
            service = self.env['stp.service']
            data = service.consult_balance_conciliation_historical(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta.")
            # Si STP responde error funcional
            if data.get('estado') != 0:
                raise UserError(data.get('mensaje') or "Error en consulta STP")

            self.line_ids.unlink()

            self.total = data.get('total')
            self.pagina = data.get('pagina')
            self.total_paginas = data.get('totalPaginas')
            self.saldo_inicial = data.get('saldoInicial')

            for item in data.get('datos') or []:

                # Fecha Operación (YYYYMMDD)
                fecha_operacion = False
                if item.get('fechaOperacion'):
                    fecha_operacion = datetime.strptime(
                        str(item.get('fechaOperacion')),
                        "%Y%m%d"
                    ).date()

                # Fecha Natural
                fecha_natural = False
                if item.get('fechaNatural'):
                    fecha_natural = datetime.strptime(
                        str(item.get('fechaNatural')),
                        "%Y%m%d"
                    ).date()

                # Timestamp Liquidación (milisegundos reales)
                fecha_liquidacion = False
                if item.get('tsLiquidacion'):
                    fecha_liquidacion = datetime.fromtimestamp(
                        item.get('tsLiquidacion') / 1000
                    )

                self.env['stp.consult.balance.conciliation.historical.line'].create({
                    'wizard_id': self.id,
                    'clave_rastreo': item.get('claveRastreo'),
                    'tipo_orden': item.get('tipoOrden'),
                    'concepto_pago': item.get('conceptoPago'),
                    'estado': item.get('estado'),
                    'fecha_operacion': fecha_operacion,
                    'fecha_natural': fecha_natural,
                    'fecha_liquidacion': fecha_liquidacion,
                    'cargo': item.get('cargo'),
                    'abono': item.get('abono'),
                    'saldo': item.get('saldo'),
                })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"{str(e)}")

class STPOrderConsultBalanceConciliationHistoricalLine(models.TransientModel):
    _name = 'stp.consult.balance.conciliation.historical.line'
    _description = 'STP Consult Balance Conciliation Historical Line'

    wizard_id = fields.Many2one(
        'stp.consult.balance.conciliation.historical',
        ondelete='cascade'
    )

    clave_rastreo = fields.Char("Clave Rastreo")
    tipo_orden = fields.Char("Tipo Orden")
    concepto_pago = fields.Char("Concepto Pago")
    estado = fields.Char("Estado")

    fecha_operacion = fields.Date("Fecha Operación")
    fecha_natural = fields.Date("Fecha Natural")
    fecha_liquidacion = fields.Datetime("Fecha Liquidación")

    cargo = fields.Float("Cargo")
    abono = fields.Float("Abono")
    saldo = fields.Float("Saldo")


    def action_open_cep_historical(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
        }
###### CONSULTA CONCILIACIÓN SALDO ACTUAL ######
class STPOrderConsultBalanceConciliation(models.TransientModel):
    _name = 'stp.consult.balance.conciliation'
    _description = 'STP Consult Balance Conciliation'

    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    page = fields.Integer(string="Pago", default=0)

    response = fields.Text(string="Resultado", readonly=True)
    line_ids = fields.One2many('stp.consult.balance.conciliation.line','wizard_id',string="Operaciones")
    total = fields.Integer(string="Total")
    pagina = fields.Integer(string="Página")
    total_paginas = fields.Integer(string="Total Páginas")
    saldo_inicial = fields.Float(string="Saldo Inicial")
    ts_captura = fields.Datetime(string="Fecha Captura")

    ######## CONSULTA ########
    def action_consult_balance_conciliation(self):
        self.ensure_one()

        # Contrucción del Payload
        payload = {
            "empresa": self.company_id.nombre,
            "pagina": int(self.page),
        }

        try:
            service = self.env['stp.service']
            data = service.consult_balance_conciliation(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta.")
            # Si STP responde error funcional
            if data.get('estado') != 0:
                raise UserError(data.get('mensaje') or "Error en consulta STP")

            self.line_ids.unlink()

            self.total = data.get('total')
            self.pagina = data.get('pagina')
            self.total_paginas = data.get('totalPaginas')
            self.saldo_inicial = data.get('saldoInicial')

            for item in data.get('datos') or []:

                # Fecha Operación (YYYYMMDD)
                fecha_operacion = False
                if item.get('fechaOperacion'):
                    fecha_operacion = datetime.strptime(
                        str(item.get('fechaOperacion')),
                        "%Y%m%d"
                    ).date()

                # Fecha Natural
                fecha_natural = False
                if item.get('fechaNatural'):
                    fecha_natural = datetime.strptime(
                        str(item.get('fechaNatural')),
                        "%Y%m%d"
                    ).date()

                # Timestamp Liquidación (milisegundos reales)
                fecha_liquidacion = False
                if item.get('tsLiquidacion'):
                    fecha_liquidacion = datetime.fromtimestamp(
                        item.get('tsLiquidacion') / 1000
                    )

                self.env['stp.consult.balance.conciliation.line'].create({
                    'wizard_id': self.id,
                    'clave_rastreo': item.get('claveRastreo'),
                    'tipo_orden': item.get('tipoOrden'),
                    'concepto_pago': item.get('conceptoPago'),
                    'estado': item.get('estado'),
                    'fecha_operacion': fecha_operacion,
                    'fecha_natural': fecha_natural,
                    'fecha_liquidacion': fecha_liquidacion,
                    'cargo': item.get('cargo'),
                    'abono': item.get('abono'),
                    'saldo': item.get('saldo'),
                })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }


        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"{str(e)}")

class STPOrderConsultBalanceConciliationLine(models.TransientModel):
    _name = 'stp.consult.balance.conciliation.line'
    _description = 'STP Consult Balance Conciliation Line'

    wizard_id = fields.Many2one(
        'stp.consult.balance.conciliation',
        ondelete='cascade'
    )

    clave_rastreo = fields.Char("Clave Rastreo")
    tipo_orden = fields.Char("Tipo Orden")
    concepto_pago = fields.Char("Concepto Pago")
    estado = fields.Char("Estado")

    fecha_operacion = fields.Date("Fecha Operación")
    fecha_natural = fields.Date("Fecha Natural")
    fecha_liquidacion = fields.Datetime("Fecha Liquidación")

    cargo = fields.Float("Cargo")
    abono = fields.Float("Abono")
    saldo = fields.Float("Saldo")


    def action_open_cep_conciliation(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
        }
###### CONSULTA INSTITUCIONES ######
class STPOrderConsultInstitutions(models.TransientModel):
    _name = 'stp.consult.institutions'
    _description = 'STP Consult Institutions'

    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")

    response = fields.Text(string="Resultado", readonly=True)
    line_ids = fields.One2many('stp.consult.institutions.line','wizard_id',string="Operaciones")

    ######## CONSULTA ########
    def action_consult_intitutions(self):
        self.ensure_one()

        # Contrucción del Payload
        payload = {
            "empresa": self.company_id.nombre,
        }

        try:
            service = self.env['stp.service']
            data = service.consult_institutions(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta.")
            # Si STP responde error funcional
            if data.get('estado') != 0:
                raise UserError(data.get('mensaje') or "Error en consulta STP")

            self.line_ids.unlink()

            for item in data.get('datos') or []:

                self.env['stp.consult.institutions.line'].create({
                    'wizard_id': self.id,
                    'estado': item.get('estado'),
                    'clave': item.get('clave'),
                    'participante': item.get('participante'),
                })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }


        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"{str(e)}")

class STPOrderConsultIntitutionsLine(models.TransientModel):
    _name = 'stp.consult.institutions.line'
    _description = 'STP Consult Intitutions Line'

    wizard_id = fields.Many2one(
        'stp.consult.institutions',
        ondelete='cascade'
    )

    estado = fields.Char("Estado")
    clave = fields.Char("Clave")
    participante = fields.Char("Participante")
###### CONSULTA WS CATALOGO SERVICIOS ######
class STPConsultWSServices(models.Model):
    _name = 'stp.consult.ws.services.catalog'
    _description = 'STP Consult WS Services Catalog'
    _order = 'catalog_title, servicio_nombre'
    _rec_name = 'producto_nombre'

    empresa_id = fields.Many2one('stp.empresa', string="Empresa", required=True)

    # Catálogo
    catalog_id = fields.Integer("Id Catálogo")
    catalog_title = fields.Char("Catálogo")
    catalog_icon = fields.Char("Icono Catálogo")

    # Servicio
    id_servicio = fields.Integer("Id Servicio", required=True)
    servicio_nombre = fields.Char("Servicio")
    servicio_ubicacion = fields.Char("Ubicación Servicio")

    # Producto
    producto_nombre = fields.Char("Producto")
    id_producto = fields.Integer("Id Producto")
    precio = fields.Float("Precio")

    tipo_referencia = fields.Char("Tipo Referencia")
    tipo_dato_referencia = fields.Char("Tipo Dato Ref.")
    longitud_referencia = fields.Char("Longitud Ref.")

    show_ayuda = fields.Boolean("Mostrar ayuda")
    legend = fields.Text("Leyenda")

    producto_logo = fields.Binary("Logo", attachment=True)

    active = fields.Boolean(default=True)

class STPOrderConsultWSServices(models.TransientModel):
    _name = 'stp.consult.ws.services'
    _description = 'STP Consult WS Services'

    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")

    response = fields.Text(string="Resultado", readonly=True)
    line_ids = fields.One2many('stp.consult.ws.services.line','wizard_id',string="Servicios / Productos")

    filter_catalog = fields.Selection(
        [
            ('Recargas', 'Recargas'),
            ('Servicios', 'Servicios'),
            ('Tesoreria', 'Tesoreria'),
        ],
        string="Filtrar por Catálogo"
    )

    def action_save_catalog(self):
        self.ensure_one()

        catalog_model = self.env['stp.consult.ws.services.catalog']

        # Elimina catálogo previo de esa empresa
        catalog_model.search([
            ('empresa_id', '=', self.company_id.id)
        ]).unlink()

        for line in self.line_ids:
            catalog_model.create({
                'empresa_id': self.company_id.id,

                'catalog_id': line.catalog_id,
                'catalog_title': line.catalog_title,

                'id_servicio': line.id_servicio,
                'servicio_nombre': line.servicio_nombre,
                'servicio_ubicacion': line.servicio_ubicacion,

                'producto_nombre': line.producto_nombre,
                'id_producto': line.id_producto,
                'precio': line.precio,

                'tipo_referencia': line.tipo_referencia,
                'tipo_dato_referencia': line.tipo_dato_referencia,
                'longitud_referencia': line.longitud_referencia,

                'show_ayuda': line.show_ayuda,
                'legend': line.legend,

                'producto_logo': line.producto_logo,
            })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stp.consult.ws.services.catalog',
            'view_mode': 'tree,form',
            'domain': [('empresa_id', '=', self.company_id.id)],
            'target': 'current',
        }

    ######## CONSULTA ########
    def action_consult_ws_services(self):
        self.ensure_one()

        # Contrucción del Payload
        payload = {
            "empresa": self.company_id.nombre,
        }

        try:
            service = self.env['stp.service']
            data = service.consult_ws_services(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta.")

            # Este WS regresa un LIST de catálogos, validamos eso
            if not isinstance(data, list):
                raise UserError("Formato de respuesta inesperado del WS Catálogo de Servicios.")

            # Guardar respuesta cruda para debugging
            try:
                self.response = json.dumps(data, indent=2, ensure_ascii=False)
            except Exception:
                self.response = str(data)

            self.line_ids.unlink()

            # Recorrer estructura:
            # data -> lista de catálogos
            # catálogo -> serviciosDTOS -> productoDTOList
            for catalog in data:
                catalog_id = catalog.get('id')
                catalog_title = catalog.get('titulo')
                catalog_icon = catalog.get('icono')

                for servicio in catalog.get('serviciosDTOS') or []:
                    id_servicio = servicio.get('idServicio')
                    servicio_nombre = servicio.get('servicio')
                    servicio_ubicacion = servicio.get('ubicacion')
                    servicio_logo = servicio.get('logoSrc')

                    for prod in servicio.get('productoDTOList') or []:

                        vals = {
                            'wizard_id': self.id,

                            # Catálogo
                            'catalog_id': catalog_id,
                            'catalog_title': catalog_title,
                            'catalog_icon': catalog_icon,

                            # Servicio
                            'id_servicio': id_servicio,
                            'servicio_nombre': servicio_nombre,
                            'servicio_ubicacion': servicio_ubicacion,
                            'servicio_logo_src': servicio_logo,

                            # Producto
                            'producto_nombre': prod.get('producto'),
                            'id_producto': prod.get('idProducto'),
                            'id_cat_tipo_servicio': prod.get('idCatTipoServicio'),
                            'tipo_front': prod.get('tipoFront'),
                            'precio': prod.get('precio'),

                            'has_digito_verificador': prod.get('hasDigitoVerificador'),
                            'tipo_referencia': prod.get('tipoReferencia'),
                            'tipo_dato_referencia': prod.get('tipoDatoReferencia'),
                            'longitud_referencia': prod.get('longitudReferencia'),

                            'show_ayuda': prod.get('showAyuda'),
                            'legend': prod.get('legend'),

                            'producto_logo_src': prod.get('logoSrc'),
                            'producto_ref_src': prod.get('refSrc'),
                            'producto_ubicacion': prod.get('ubicacion') or servicio_ubicacion,
                        }

                        #
                        logo_url = vals.get('producto_logo_src')
                        if logo_url:
                            try:
                                response = requests.get(
                                    logo_url,
                                    timeout=5,
                                    headers={"User-Agent": "Mozilla/5.0"}
                                )
                                response.raise_for_status()

                                if "image" in response.headers.get("Content-Type", ""):
                                    vals['producto_logo'] = base64.b64encode(response.content)
                            except Exception:
                                pass  # no rompemos el flujo si falla el logo

                        self.env['stp.consult.ws.services.line'].create(vals)

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")
        except Exception as e:
            raise UserError(f"{str(e)}")

class STPOrderConsultWSServicesLine(models.TransientModel):
    _name = 'stp.consult.ws.services.line'
    _description = 'STP Consult WS Services Line'

    wizard_id = fields.Many2one(
        'stp.consult.ws.services',
        ondelete='cascade'
    )

    # --------- Catálogo ----------
    catalog_id = fields.Integer("Id Catálogo")
    catalog_title = fields.Char("Catálogo")        # Recargas / Servicios / Tesorería
    catalog_icon = fields.Char("Icono Catálogo")   # URL

    # --------- Servicio ----------
    id_servicio = fields.Integer("Id Servicio")
    servicio_nombre = fields.Char("Servicio")
    servicio_ubicacion = fields.Char("Ubicación Servicio")
    servicio_logo_src = fields.Char("Logo Servicio (URL)")

    # --------- Producto ----------
    producto_nombre = fields.Char("Producto")
    id_producto = fields.Integer("Id Producto")
    id_cat_tipo_servicio = fields.Integer("Id Cat Tipo Servicio")
    tipo_front = fields.Integer("Tipo Front")
    precio = fields.Float("Precio")

    has_digito_verificador = fields.Boolean("¿Tiene dígito verificador?")
    tipo_referencia = fields.Char("Tipo Referencia")
    tipo_dato_referencia = fields.Char("Tipo Dato Ref.")
    longitud_referencia = fields.Char("Longitud Ref.")

    show_ayuda = fields.Boolean("Mostrar ayuda")
    legend = fields.Text("Leyenda / Ayuda")

    producto_logo_src = fields.Char("Logo Producto (URL)")
    producto_ref_src = fields.Char("Imagen Referencia (URL)")
    producto_ubicacion = fields.Char("Ubicación Producto")

    producto_logo = fields.Binary(string="Logo Producto",attachment=True)

    def action_fetch_logo(self):
        for rec in self:
            if not rec.producto_logo_src:
                raise UserError("No hay URL de logo definida.")

            try:
                response = requests.get(
                    rec.producto_logo_src,
                    timeout=10,
                    headers={
                        "User-Agent": "Mozilla/5.0"
                    }
                )
                response.raise_for_status()

                # 🔥 Validamos que realmente sea imagen
                content_type = response.headers.get("Content-Type", "")
                if "image" not in content_type:
                    raise UserError(
                        f"La URL no devolvió una imagen válida.\nContent-Type: {content_type}"
                    )

                rec.producto_logo = base64.b64encode(response.content)

            except Exception as e:
                raise UserError(f"No se pudo descargar el logo:\n{e}")

###### WS PAGO DE SERVICIOS SIN REFERENCIA ######
class STPWSPaymentServiceWithoutReference(models.Model):
    _name = 'stp.payment.service.without.reference'
    _description = 'STP WS Payment Service Without Reference'
    _rec_name = 'company_id'

    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Alias de la empresa registrado dentro de Enlace Financiero.")
    product_id = fields.Many2one('stp.consult.ws.services.catalog', string="Producto", required=True, help="Identificador del producto.")
    service_id = fields.Many2one('stp.consult.ws.services.catalog', string="Servicio", help="Identificador del servicio.")
    catalog = fields.Many2one('stp.ws.type.catalog', string="Catalogo", required=True, help="Identificador del catalogo", default=1, domain="[('id_catalog', 'in', [1])]")
    monto = fields.Float(string="Monto",required=True, help="Importe de la operación (en pesos).")
    phone = fields.Char(string="Telefono", required=True, help="	Número el cual será abonado la recarga telefónica, o numero del servicio a pagar(Tag,Gift -Card)", default="5523354853") #PRUEBA
    ordering_account = fields.Char(string="Cuenta Ordenante", required=True, help="Número de cuenta ordenante. La Cuenta Clabe asociada a la empresa ordenante.", default="646180693400000003") #PRUEBA
    latitud = fields.Char(required=True, help="Coordenada correspondiente a la longitud.", default="19.370312")
    longitud = fields.Char(required=True, help="Coordenada correspondiente a la latitud.", default="-99.180617")

    #RESPUESTA DE LA OPERACIÓN
    response = fields.Text(string="Respuesta STP", readonly=True)
    estado = fields.Integer("Estado", readonly=True)
    mensaje = fields.Char("Mensaje", readonly=True)
    num_autorizacion = fields.Char("Número Autorización", readonly=True)
    leyenda = fields.Text("Leyenda", readonly=True)
    cuenta_respuesta = fields.Char("Cuenta Respuesta", readonly=True)
    referencia_respuesta = fields.Char("Referencia", readonly=True)
    servicio_respuesta = fields.Char("Servicio", readonly=True)
    fecha_respuesta = fields.Char("Fecha", readonly=True)
    hora_respuesta = fields.Char("Hora", readonly=True)
    clave_rastreo = fields.Char("Clave Rastreo", readonly=True)
    upc = fields.Char("UPC", readonly=True)
    pin = fields.Char("PIN", readonly=True)

    # =========================
    # ENVIAR
    # =========================
    def action_send_ws_payment(self):
        self.ensure_one()

        if not self.product_id:
            raise UserError("Debe seleccionar un producto.")

        payload = {
            "catalogo": str(self.catalog.id_catalog),
            "empresa": self.company_id.nombre,
            "idProducto": str(self.product_id.id_producto),
            "monto": self.monto,
            "servicio": str(self.product_id.id_servicio),
            "cuentaOrdenante": self.ordering_account,
            "telefono": self.phone,
            "latitud": self.latitud or "",
            "longitud": self.longitud or "",
        }

        try:
            service = self.env['stp.service']
            data = service.consult_ws_payment_services_without_reference(payload)

            if not data:
                raise UserError("No hubo respuesta del servicio.")

            self.response = json.dumps(data, indent=2, ensure_ascii=False)

            self.estado = data.get('estado')
            self.mensaje = data.get('mensaje')
            self.num_autorizacion = data.get('numAutorizacion')
            self.leyenda = data.get('leyenda')
            self.cuenta_respuesta = data.get('cuenta')
            self.referencia_respuesta = data.get('referencia')
            self.servicio_respuesta = data.get('servicio')
            self.fecha_respuesta = data.get('fecha')
            self.hora_respuesta = data.get('hora')
            self.clave_rastreo = data.get('claveRastreo')
            self.upc = data.get('upc')
            self.pin = data.get('pin')

            if self.estado != 0:
                raise UserError(self.mensaje or "Error en el pago.")

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(str(e))
###### WS PAGO DE SERVICIOS CON REFERENCIA ######
class STPWSPaymentServiceWithReference(models.Model):
    _name = 'stp.payment.service.with.reference'
    _description = 'STP WS Payment Service With Reference'
    _rec_name = 'company_id'

    catalog_id = fields.Many2one('stp.ws.type.catalog', required=True,string="Catalogo", help="Identificador del catalogo", domain="[('id_catalog', 'in', [2,3])]")
    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Alias de la empresa registrado dentro de Enlace Financiero.")
    product_id = fields.Many2one('stp.consult.ws.services.catalog', string="Producto", required=True, help="Identificador del producto.", domain="[('catalog_id', '=', catalog_id)]")
    monto = fields.Float(string="Monto",required=True, help="Importe de la operación (en pesos).")
    reference = fields.Char(string="Referencia", required=True, help="Identificador del referencia.")
    ordering_account = fields.Char(string="Cuenta Ordenante", required=True, help="Número de cuenta ordenante. La Cuenta Clabe asociada a la empresa ordenante.", default="646180693400000003") #PRUEBA
    service_id = fields.Many2one('stp.consult.ws.services.catalog',string="Servicio", help="Identificador del servicio.")
    latitud = fields.Char(required=True, help="Coordenada correspondiente a la longitud.", default="19.370312")
    longitud = fields.Char(required=True, help="Coordenada correspondiente a la latitud.", default="-99.180617")

    #RESPUESTA DE LA OPERACIÓN
    response = fields.Text(string="Respuesta STP", readonly=True)
    estado = fields.Integer("Estado", readonly=True)
    mensaje = fields.Char("Mensaje", readonly=True)
    num_autorizacion = fields.Char("Número Autorización", readonly=True)
    leyenda = fields.Text("Leyenda", readonly=True)
    cuenta_respuesta = fields.Char("Cuenta Respuesta", readonly=True)
    monto_respuesta = fields.Float("Monto Respuesta", readonly=True)
    referencia_respuesta = fields.Char("Referencia", readonly=True)
    servicio_respuesta = fields.Char("Servicio", readonly=True)
    fecha_respuesta = fields.Char("Fecha", readonly=True)
    hora_respuesta = fields.Char("Hora", readonly=True)
    clave_rastreo = fields.Char("Clave Rastreo", readonly=True)
    upc = fields.Char("UPC", readonly=True)

    # =========================
    # ENVIAR
    # =========================
    def action_send_ws_payment(self):
        self.ensure_one()

        if not self.product_id:
            raise UserError("Debe seleccionar un producto.")

        payload = {
            "catalogo": str(self.catalog_id.id_catalog),
            "empresa": self.company_id.nombre,
            "idProducto": str(self.product_id.id_producto),
            "monto": self.monto,
            "referencia": self.reference,
            "cuentaOrdenante": self.ordering_account,
            "servicio": str(self.product_id.id_servicio),
            "latitud": self.latitud or "",
            "longitud": self.longitud or "",
        }

        try:
            service = self.env['stp.service']
            data = service.consult_ws_payment_services_with_reference(payload)

            # Guardar JSON completo
            self.response = json.dumps(data, indent=2, ensure_ascii=False)

            # Mapear campos
            self.estado = data.get('estado')
            self.mensaje = data.get('mensaje')
            self.num_autorizacion = str(data.get('numAutorizacion') or "")
            self.leyenda = data.get('leyenda')
            self.cuenta_respuesta = data.get('cuenta')
            self.monto_respuesta = data.get('monto')
            self.referencia_respuesta = data.get('referencia')
            self.servicio_respuesta = data.get('servicio')
            self.fecha_respuesta = data.get('fecha')
            self.hora_respuesta = data.get('hora')
            self.clave_rastreo = data.get('claveRastreo')
            self.upc = data.get('upc')

            if self.estado != 0:
                self.state = 'error'
                raise UserError(self.mensaje or "Error en el pago.")
            else:
                self.state = 'done'

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(str(e))
###### WS VERIFICACIÓN DE REFERENCIA ######
class STPWSReferenceVerification(models.TransientModel):
    _name = 'stp.consult.ws.reference.verification'
    _description = 'STP Consult WS Reference Verification'

    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Alias de la empresa registrado dentro de Enlace Financiero.")
    id_service = fields.Many2one('stp.consult.ws.services.catalog',string="Servicio", requerid=True, default=107)
    reference = fields.Char(string="Referencia", required=True, help="Referencia por verificar")

    response = fields.Text(string="Resultado", readonly=True)
    line_ids = fields.One2many('stp.consult.ws.reference.verification.line','wizard_id',string="Servicios / Productos")

    ######## CONSULTA ########
    def action_consult_ws_reference_verification(self):
        self.ensure_one()

        # Contrucción del Payload
        payload = {
            "empresa": self.company_id.nombre,
            "idServicio": self.id_service.id_servicio,
            "referencia": self.reference,
        }

        try:
            service = self.env['stp.service']
            data = service.consult_ws_reference_verification(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta.")

            result = data.get('result') or {}
            respuesta = result.get('respuesta_stp') or {}
            if not respuesta:
                raise UserError("No se recibió información de la referencia.")

            self.line_ids.unlink()

            self.env['stp.consult.ws.reference.verification.line'].create({
                'wizard_id': self.id,
                'mensaje': respuesta.get('mensaje'),
                'estado': respuesta.get('estado'),
                'monto': respuesta.get('monto'),
            })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")
        except Exception as e:
            raise UserError(f"{str(e)}")

class STPWSReferenceVerificationLine(models.TransientModel):
    _name = 'stp.consult.ws.reference.verification.line'
    _description = 'STP Consult WS Reference Verification Line'

    wizard_id = fields.Many2one(
        'stp.consult.ws.reference.verification',
        ondelete='cascade'
    )

    mensaje = fields.Char(string="Mensaje", help="Muestra el mensaje de la transacción.")
    estado = fields.Char(string="Estado", help="Código de estado.")
    monto = fields.Float(string="Monto", help="Muestra el saldo a pagar, puede ser opcional.")
###### WS VALIDA PAGO DE SERVICIO (ESTATUS) ######
class STPWSConsultPaymentServiceValidation(models.TransientModel):
    _name = 'stp.consult.ws.payment.service.validation'
    _description = 'STP WS Consult Payment Service Validation'

    tracking_key = fields.Char(string="Clave de Rastreo", required=True, help="Clave de seguimiento asociada a la orden de pago.")
    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    operation_date = fields.Date(string="Fecha Operación",required=True, default=fields.Date.context_today, index=True, help="Fecha en la que se realizó la operación a consultar.")
    phone_reference = fields.Char(string="Telefono", required=True, help="Referencia del servicio (o teléfono) que se pagó.", default="5523354853") #PRUEBA

    response = fields.Text(string="Resultado", readonly=True)
    line_ids = fields.One2many('stp.consult.ws.payment.service.validation.line','wizard_id',string="Operaciones")

    ######## CONSULTA ########
    def action_ws_consult(self):
        self.ensure_one()

        # Contrucción del Payload
        payload = {
            "claveRastreo": self.tracking_key,
            "empresa": self.company_id.nombre,
            "fechaOperacion": self.operation_date.strftime('%Y%m%d'),
            "referenciaTelefono": self.phone_reference,
        }

        try:
            service = self.env['stp.service']
            data = service.consult_ws_service_payment_validation(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta.")

            if data.get('estado') != 10:
                raise UserError(data.get('mensaje'))

            result = data.get('result') or {}
            respuesta = result.get('respuesta_stp') or {}

            if not respuesta:
                raise UserError("No se recibió información de la referencia.")

            self.line_ids.unlink()

            self.env['stp.consult.ws.payment.service.validation.line'].create({
                'wizard_id': self.id,
                'mensaje': respuesta.get('mensaje'),
                'estado': respuesta.get('estado'),
                'numAutorizacion': respuesta.get('numAutorizacion'),
                'leyenda': respuesta.get('leyenda'),
                'cuenta': respuesta.get('cuenta'),
                'monto': respuesta.get('monto'),
                'referencia': respuesta.get('referencia'),
                'servicio': respuesta.get('servicio'),
                'fecha': respuesta.get('fecha'),
                'hora': respuesta.get('hora'),
                'claveRastreo': respuesta.get('claveRastreo'),
                'upc': respuesta.get('upc'),
                'descripcion': respuesta.get('descripcion'),
                'producto': respuesta.get('producto'),
            })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }


        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"{str(e)}")

class STPWSConsultPaymentServiceValidationLine(models.TransientModel):
    _name = 'stp.consult.ws.payment.service.validation.line'
    _description = 'STP Consult Intitutions Line'

    wizard_id = fields.Many2one(
        'stp.consult.ws.payment.service.validation',
        ondelete='cascade'
    )

    mensaje = fields.Char("Mensaje")
    estado = fields.Integer("Estado WS")

    num_autorizacion = fields.Char("Número Autorización")
    leyenda = fields.Text("Leyenda")

    cuenta = fields.Char("Cuenta")
    monto = fields.Float("Monto")

    referencia = fields.Char("Referencia")
    servicio = fields.Char("Servicio")

    fecha = fields.Char("Fecha")
    hora = fields.Char("Hora")

    clave_rastreo = fields.Char("Clave Rastreo")
    upc = fields.Char("UPC")

    descripcion = fields.Char("Estatus Pago")
    producto = fields.Char("Producto")
###### WS REIMPRESIÓN DE TICKET ######
class STPWSConsultTicketReprint(models.TransientModel):
    _name = 'stp.consult.ws.ticket.reprint'
    _description = 'STP WS Consult Ticket Reprint'

    tracking_key = fields.Char(string="Clave de Rastreo", required=True, help="Clave de seguimiento asociada a la orden de pago.", default="EMPRESA1PRUEBA1000999965701771")
    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    operation_date = fields.Date(string="Fecha Operación",required=True, default=fields.Date.context_today, index=True, help="Fecha en la que se realizó la operación a consultar.")
    authorization_number = fields.Char(string="Numero de Autorización", required=True, help="Número de autorización del pago con referencia.", default="100099996") #PRUEBA #TODO REVISAR

    response = fields.Text(string="Resultado", readonly=True)
    line_ids = fields.One2many('stp.consult.ws.ticket.reprint.line','wizard_id',string="Operaciones")

    ######## CONSULTA ########
    def action_ws_consult(self):
        self.ensure_one()

        # Contrucción del Payload
        payload = {
            "claveRastreo": self.tracking_key,
            "empresa": self.company_id.nombre,
            "fechaOperacion": self.operation_date.strftime('%Y%m%d'),
            "numeroAutorizacion": self.authorization_number,
        }

        try:
            service = self.env['stp.service']
            data = service.consult_ws_ticket_reprint(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta.")

            if data.get('estado') != 10:
                raise UserError(data.get('mensaje'))

            result = data.get('result') or {}
            respuesta = result.get('respuesta_stp') or {}

            if not respuesta:
                raise UserError("No se recibió información de la referencia.")

            self.line_ids.unlink()

            self.env['stp.consult.ws.ticket.reprint.line'].create({
                'wizard_id': self.id,
                'mensaje': respuesta.get('mensaje'),
                'estado': respuesta.get('estado'),
                'numAutorizacion': respuesta.get('numAutorizacion'),
                'leyenda': respuesta.get('leyenda'),
                'cuenta': respuesta.get('cuenta'),
                'monto': respuesta.get('monto'),
                'referencia': respuesta.get('referencia'),
                'servicio': respuesta.get('servicio'),
                'fecha': respuesta.get('fecha'),
                'hora': respuesta.get('hora'),
                'claveRastreo': respuesta.get('claveRastreo'),
                'upc': respuesta.get('upc'),
            })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }


        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"{str(e)}")

class STPWSConsultTicketReprintLine(models.TransientModel):
    _name = 'stp.consult.ws.ticket.reprint.line'
    _description = 'STP WS Consult Ticket Reprint Line'

    wizard_id = fields.Many2one(
        'stp.consult.ws.ticket.reprint',
        ondelete='cascade'
    )

    mensaje = fields.Char("Mensaje")
    estado = fields.Integer("Estado WS")

    num_autorizacion = fields.Char("Número Autorización")
    leyenda = fields.Text("Leyenda")

    cuenta = fields.Char("Cuenta")
    monto = fields.Float("Monto")

    referencia = fields.Char("Referencia")
    servicio = fields.Char("Servicio")

    fecha = fields.Char("Fecha")
    hora = fields.Char("Hora")

    clave_rastreo = fields.Char("Clave Rastreo")
    upc = fields.Char("UPC")

###### WS HITORICO PAGOS CON O SIN REFERENCIA ######

###### CODI CONSULTA DE ESTADO ######
class STPCODIConsult(models.TransientModel):
    _name = 'stp.codi.consult'
    _description = 'STP CoDi Consult'

    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    folio_codi = fields.Char(string="Folio Codi", required=True, help="Folio del Mensaje de Cobro asignado por Banco de México.")

    response = fields.Text(string="Resultado", readonly=True)
    line_ids = fields.One2many('stp.codi.consult.line','wizard_id',string="Operaciones")

    ######## CONSULTA ########
    def action_consult(self):
        self.ensure_one()

        # Contrucción del Payload
        payload = {
            "empresa": self.company_id.nombre,
            "folioCodi": self.folio_codi,
        }

        try:
            service = self.env['stp.service']
            data = service.consult_codi(payload)

            if not data:
                raise UserError("El servicio STP no devolvió respuesta.")

            estado_peticion = data.get('estadoPeticion')
            estado_codi = data.get('estadoCodi')

            if estado_peticion != "0":
                raise UserError(data.get('descripcionError') or "Error en la petición STP")

            if estado_codi != "0":
                raise UserError(data.get('descripcionError') or "Error en CoDi")

            # Limpias líneas
            self.line_ids.unlink()

            # Aquí ya no hay lista, es solo un registro
            self.env['stp.codi.consult.line'].create({
                'wizard_id': self.id,
                'estado_codi': estado_codi,
                'folio_codi': data.get('folioCodi'),
                'estado_peticion': estado_peticion,
            })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'view_mode': 'form',
                'res_id': self.id,
                'target': 'new',
            }

        except requests.exceptions.HTTPError as e:
            raise UserError(f"Error HTTP: {str(e)}")

        except Exception as e:
            raise UserError(f"{str(e)}")

class STPCODIConsultLine(models.TransientModel):
    _name = 'stp.codi.consult.line'
    _description = 'STP Consult Intitutions Line'

    wizard_id = fields.Many2one(
        'stp.codi.consult',
        ondelete='cascade'
    )

    estado_codi = fields.Char("Estado de CoDi", help="Resultado del procesamiento del mensaje de cobro")
    folio_codi = fields.Char("Folio de CoDi", help="Folio del Mensaje de Cobro asignado por Banco de México")
    estado_peticion = fields.Char("Estado Peticion", help="Estado de la consulta del mensaje de cobro")

###### CODI REGISTRO DE COBRO QR ######
class STPCodiRegisterQR(models.Model):
    _name = 'stp.codi.register.qr'
    _description = 'STP CoDi Register QR'
    _rec_name = 'commerce_reference'
    _index = True

    company_id = fields.Many2one('stp.empresa', string="Empresa", required=True, help="Nombre de la empresa que envía las operaciones y que está configurada en “STP”.")
    commerce_reference = fields.Char(string="Numero Referencia de Comercio", required=True, help="Referencia numérica asignada por el comercio/cliente que sirve para identificar la operación.")
    concept = fields.Char(string="Concepto", required=True, help="Motivo por el que se instruye el Mensaje de Cobro al beneficiario.")
    time_limit_minutes = fields.Integer(string="Minutos Limite", required=True, help="Minutos límite para que el comprador pueda realizar el pago una vez que el Mensaje de Cobro se haya enviado. Su valor mínimo es 5 min y máximo el equivalente a 30 días.")
    amount = fields.Float(string="Monto", required=True, help="Dato numérico que indica el monto del cobro. El monto deber ser mayor a cero y menor o igual a 999,999,999,999.99, colocando los 2 decimales.")
    beneficiary_name = fields.Char(string="Nombre del Beneficiario", required=True, help="Nombre del beneficiario final de los fondos recibidos.")
    beneficiary_bank = fields.Char(string="Banco Beneficiario", required=True, help="Banco al que pertenece la cuenta del beneficiario.")
    beneficiary_account_type = fields.Char(string="Tipo de cuenta del Beneficiario", required=True, help="Tipo de cuenta beneficiario.")
    beneficiary_account = fields.Char(string="Cuenta de Beneficiario", required=True, help="Cuenta registrada para la recepción de pagos.")
    spei_payment_type = fields.Selection([('20', 'CoDi'),('21', 'CoDi Charge'),],string="Tipo de Pago SPEI",required=True,default='21', help="Tipo de pago a emplear cuando la transferencia de fondos sea interbancaria: 20 = Cobros de una ocasión. 21 = Cobros recurrentes.")

    stp_id = fields.Char(string="STP ID", help="El ID del STP")
    stp_descripcionError = fields.Text(string="Descripción STP")
    qr_image = fields.Binary(string="QR Code")

    def action_enviar(self):
        self.ensure_one()

        # =========================
        # VALIDACIONES
        # =========================
        if self.amount <= 0:
            raise UserError("Monto no puede ser menor a 0.")

        if len(self.concept) > 40:
            raise UserError("El concepto excede mas de 40 caracteres.")

        # =========================
        # PAYLOAD CODI
        # =========================
        payload = {
            "numeroReferenciaComercio": self.commerce_reference,
            "concepto": self.concept,
            "minutosLimite": str(self.time_limit_minutes),
            "monto": "{:.2f}".format(self.amount),
            "nombreBeneficiario": self.beneficiary_name,
            "bancoBeneficiario": self.beneficiary_bank,
            "tipoCuentaBeneficiario": self.beneficiary_account_type,
            "cuentaBeneficiario": self.beneficiary_account,
            "empresa": self.company_id.nombre,
            "tipoPagoDeSpei": self.spei_payment_type,
        }

        try:
            respuesta = self.env['stp.service'].register_codi_qr(payload)
        except Exception as e:
            raise UserError(f"Error connecting to STP:\n{str(e)}")

        if not respuesta:
            raise UserError("No response received from STP.")

        # VALIDACIÓN BÁSICA DE ESTRUCTURA QR
        if not respuesta.get("TYP") or not respuesta.get("ic") or not respuesta.get("CRY"):
            raise UserError("Invalid STP QR response.")

        # Convertir TODO el objeto a JSON para generar el QR
        qr_data = json.dumps(respuesta, separators=(',', ':'))

        qr = qrcode.make(qr_data)
        buffer = BytesIO()
        qr.save(buffer, format="PNG")

        self.qr_image = base64.b64encode(buffer.getvalue())

        # Guardar identificador útil
        self.stp_id = respuesta.get("ic", {}).get("IDC")
        self.stp_descripcionError = "QR Generado existosamente"

        return {
            'type': 'ir.actions.act_window',
            'name': 'Escanea el QR para Pagar',
            'res_model': self._name,
            'view_mode': 'form',
            'view_id': self.env.ref('contabilidad_kuale.view_stp_codi_qr_popup_form').id,
            'res_id': self.id,
            'target': 'new',
        }
