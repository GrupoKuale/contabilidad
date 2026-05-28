import json
import base64
from odoo import http
from odoo.http import request
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from ..services.stp_service import (enviar_orden_pago_stp, consulta_fecha_actual, consulta_fecha_historica,
                                    consulta_fecha_natural, consulta_saldo, consulta_orden_claverastreo,
                                    consulta_comprobante_stp,consulta_conciliacion_saldo_actual,
                                    consulta_conciliacion_saldo_historica, consulta_conciliacion_instituciones,
                                    codi_consulta_estado, codi_registro_cobro,codi_registro_cobro_qr,
                                    consulta_catalogo_servicio,pago_servicios_sin_referencia, pago_servicios_con_referencia,
                                    verificacion_referencia, valida_pago_servicio, reimpresion_tickets, historico_pagos)

#Contrucción de Cadena
def build_cadena_original(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('institucionContraparte')}|" #Obligatoria
        f"{v('empresa')}|" #Obligatoria
        f"{v('fechaOperacion')}|"
        f"{v('folioOrigen')}|"
        f"{v('claveRastreo')}|" #Obligatoria
        f"{v('institucionOperante')}|" #Obligatoria
        f"{v('monto')}|" #Obligatoria
        f"{v('tipoPago')}|" #Obligatoria
        f"{v('tipoCuentaOrdenante')}|" #Obligatoria
        f"{v('nombreOrdenante')}|" #Obligatoria
        f"{v('cuentaOrdenante')}|" #Obligatoria
        f"{v('rfcCurpOrdenante')}|" #Obligatoria
        f"{v('tipoCuentaBeneficiario')}|" #Obligatoria
        f"{v('nombreBeneficiario')}|" #Obligatoria
        f"{v('cuentaBeneficiario')}|" #Obligatoria 
        f"{v('rfcCurpBeneficiario')}|" #Obligatoria
        f"{v('emailBeneficiario')}|" 
        f"{v('tipoCuentaBeneficiario2')}|"
        f"{v('nombreBeneficiario2')}|"
        f"{v('cuentaBeneficiario2')}|"
        f"{v('rfcCurpBeneficiario2')}|" 
        f"{v('conceptoPago')}|" #Obligatoria
        f"{v('conceptoPago2')}|"
        f"{v('claveCatUsuario1')}|"
        f"{v('claveCatUsuario2')}|"
        f"{v('clavePago')}|"
        f"{v('referenciaCobranza')}|"
        f"{v('referenciaNumerica')}|" #Obligatoria
        f"{v('tipoOperacion')}|"
        f"{v('topologia')}|"
        f"{v('usuario')}|"
        f"{v('medioEntrega')}|"
        f"{v('prioridad')}|"
        f"{v('iva')}||"
    )

    return cadena

def build_cadena_consulta_fecha_actual(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}||" #Obligatorio
    )

    return cadena

def build_cadena_consulta_fecha_historica(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}|" #Obligatorio
        f"{v('fechaOperacion')}||"  # Obligatorio
    )

    return cadena

def build_cadena_consulta_fecha_natural(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}|" #Obligatorio
        f"{v('fechaNatural')}|" #Obligatorio
        f"{v('horaCapturaInicio')}|" #Obligatorio
        f"{v('horaCapturaFin')}||"  # Obligatorio
    )

    return cadena

def build_cadena_consulta_saldo_cuenta(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}|" #Obligatorio
        f"{v('cuentaOrdenante')}|||"  # Obligatorio
    )

    return cadena

def build_cadena_consulta_saldo_cuenta_historico(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}|" #Obligatorio
        f"{v('cuentaOrdenante')}|" #Obligatorio
        f"{v('fecha')}||"  # Obligatorio
    )

    return cadena
####PENDIENTE#####
def build_cadena_consulta_claverastreo_fecha_operacion(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}|" #Obligatorio
        f"{v('claveRastreo')}|" #Obligatorio
        f"{v('tipoOrden')}|" #Obligatorio
        "|"
        f"{v('fechaOperacion')}||"  # Obligatorio
    )

    return cadena

def build_cadena_consulta_claverastreo_fecha_natural(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}|" #Obligatorio
        f"{v('claveRastreo')}|" #Obligatorio
        f"{v('tipoOrden')}|" #Obligatorio
        f"{v('fechaNatural')}|||"  # Obligatorio
    )

    return cadena
####PENDIENTE#####
def build_cadena_consulta_comprobante_stp_fecha_natural(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}|" #Obligatorio
        f"{v('claveRastreo')}|" #Obligatorio
        f"{v('fechaNatural')}|||"  # Obligatorio
    )

    return cadena

def build_cadena_consulta_comprobante_stp_fecha_operacion(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}|" #Obligatorio
        f"{v('claveRastreo')}||" #Obligatorio
        f"{v('fechaOperacion')}||"  # Obligatorio
    )

    return cadena

def build_cadena_consulta_conciliacion_saldo_fecha_actual(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}||" #Obligatorio
    )

    return cadena

def build_cadena_consulta_conciliacion_saldo_fecha_historica(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}|" #Obligatorio
        f"{v('fechaOperacion')}||"  # Obligatorio
    )

    return cadena

def build_cadena_consulta_instituciones(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}||"  # Obligatorio
    )

    return cadena

def build_cadena_codi_consulta_estado(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('folioCodi')}|"  # Obligatorio
        f"{v('empresa')}||"  # Obligatorio
    )

    return cadena
##TODO:PENDIENTE
def build_cadena_codi_registro_cobro_no_presencial(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    monto = float(data.get("monto", 0))
    monto_str = f"{monto:.2f}"

    cadena = (
        "||"
        f"{v('numeroCelularCliente')}|"
        f"{monto_str}|"
        f"{v('numeroReferenciaComercio')}|"
        f"{v('cuentaBeneficiario2')}|"
        f"{v('nombreBeneficiario2')}|"
        f"{v('tipoCuentaBeneficiario2')}|"
        f"{v('concepto')}|"
        f"{v('empresa')}|"
        f"{v('minutosLimite')}|"
        f"{v('tipoPagoDeSpei')}||"
    )

    return cadena
###TODO:PENDIENTE DEL CERT
def build_cadena_codi_registro_cobro_qr(data: dict) -> str:
    return f"||{data['numeroReferenciaComercio']}|{data['concepto']}|{data['minutosLimite']}|{data['monto']}|{data['nombreBeneficiario']}|{data['bancoBeneficiario']}|{data['tipoCuentaBeneficiario']}|{data['cuentaBeneficiario']}|{data['empresa']}|{data['tipoPagoDeSpei']}||"
    # def v(key):
    #     val = data.get(key)
    #     return "" if val is None else str(val)
    #
    # cadena = (
    #     "||"
    #     f"{v('numeroReferenciaComercio')}|"  # Obligatorio
    #     f"{v('concepto')}|"  # Obligatorio
    #     f"{v('minutosLimite')}|"  # Obligatorio
    #     f"{v('monto')}|"  # Obligatorio
    #     f"{v('nombreBeneficiario')}|"  # Obligatorio
    #     f"{v('bancoBeneficiario')}|"  # Obligatorio
    #     f"{v('tipoCuentaBeneficiario')}|"  # Obligatorio
    #     f"{v('cuentaBeneficiario')}|"  # Obligatorio
    #     f"{v('empresa')}|"  # Obligatorio
    #     f"{v('tipoPagoDeSpei')}||"  # Obligatorio
    # )
    #
    # return cadena
#####
def build_cadena_consulta_catalogo_servicios(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}||"  # Obligatorio
    )

    return cadena

def build_cadena_pago_servicios_sin_referencia(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('catalogo')}|"  # Obligatorio
        f"{v('empresa')}|"  # Obligatorio
        f"{v('idProducto')}|"  # Obligatorio
        f"{float(v('monto')):.2f}|"  # Obligatorio
        f"{v('servicio')}|"  # Obligatorio
        f"{v('cuentaOrdenante')}|"  # Obligatorio
        f"{v('telefono')}||"  # Obligatorio
    )

    return cadena

def build_cadena_pago_servicios_con_referencia(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('catalogo')}|"  # Obligatorio
        f"{v('empresa')}|"  # Obligatorio
        f"{v('idProducto')}|"  # Obligatorio
        f"{float(v('monto')):.2f}|"  # Obligatorio
        f"{v('referencia')}|"  # Obligatorio
        f"{v('cuentaOrdenante')}|"  # Obligatorio
        f"{v('servicio')}||"  # Obligatorio
    )

    return cadena

def build_cadena_verificacion_referencia(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('empresa')}|"  # Obligatorio
        f"{v('idServicio')}|"  # Obligatorio
        f"{v('referencia')}||"  # Obligatorio
    )

    return cadena

def build_cadena_validacion_pago_servicio(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('claveRastreo')}|"  # Obligatorio
        f"{v('empresa')}|"  # Obligatorio
        f"{v('fechaOperacion')}|"  # Obligatorio
        f"{v('referenciaTelefono')}||"  # Obligatorio
    )

    return cadena

def build_cadena_reimpresion_tickets(data: dict) -> str:
    def v(key):
        val = data.get(key)
        return "" if val is None else str(val)

    cadena = (
        "||"
        f"{v('claveRastreo')}|"  # Obligatorio
        f"{v('empresa')}|"  # Obligatorio
        f"{v('fechaOperacion')}|"  # Obligatorio
        f"{v('numeroAutorizacion')}||"  # Obligatorio
    )

    return cadena

def build_cadena_historico_pagos(data: dict) -> str:
    return f"||{data['empresa']}|{data['fechaPago']}|{data['page']}||"

#Firma de Cadena
def sign_cadena(cadena: str, pem_path: str) -> str:
    with open(pem_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None,
            backend=default_backend()
        )

    signature = private_key.sign(
        cadena.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )

    return base64.b64encode(signature).decode('utf-8')

class STPSignature(http.Controller):
    @http.route('/stp/registra_orden',type='json',auth='public',methods=['PUT'],csrf=False)
    def registra_orden(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_original(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)

        #De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        #En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        #En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = enviar_orden_pago_stp(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/consulta_actual',type='json',auth='public',methods=['POST'],csrf=False)
    def consulta_actual(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_consulta_fecha_actual(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)

        #De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        #En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        #En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = consulta_fecha_actual(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/consulta_historica',type='json',auth='public',methods=['POST'],csrf=False)
    def consulta_historica(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_consulta_fecha_historica(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)

        #De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        #En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        #En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = consulta_fecha_historica(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/consulta_natural',type='json',auth='public',methods=['POST'],csrf=False)
    def consulta_natural(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_consulta_fecha_natural(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)

        #De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        #En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        #En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = consulta_fecha_natural(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/consulta_saldo_cuenta',type='json',auth='public',methods=['POST'],csrf=False)
    def consulta_saldo_cuenta(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_consulta_saldo_cuenta(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)

        #De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        #En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        #En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = consulta_saldo(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/consulta_saldo_historico',type='json',auth='public',methods=['POST'],csrf=False)
    def consulta_saldo_historico(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_consulta_saldo_cuenta_historico(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)

        #De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        #En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        #En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = consulta_saldo(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    #TODO: ***QUEDA PENDIENTE POR QUE PARECE QUE CAMBIO EL ORDEN DE LA CADENA ORIGINAL PARA ESTA CONSULTA***
    @http.route('/stp/consulta_claverastreo_operacion', type='json', auth='public', methods=['POST'], csrf=False)
    def consulta_claverastreo_fecha_operacion(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_consulta_claverastreo_fecha_operacion(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = consulta_orden_claverastreo(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/consulta_comprobante_stp', type='json', auth='public', methods=['POST'], csrf=False)
    def consulta_comprobante_stp(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        if "fechaOperacion" in payload and "fechaNatural" in payload:
            raise ValueError(
                "No se puede enviar 'fechaOperacion' y 'fechaNatural' al mismo tiempo"
            )

        if "fechaOperacion" in payload:
            cadena = build_cadena_consulta_comprobante_stp_fecha_operacion(payload)

        elif "fechaNatural" in payload:
            cadena = build_cadena_consulta_comprobante_stp_fecha_natural(payload)

        else:
            raise ValueError(
                "El payload debe contener 'fechaOperacion' o 'fechaNatural'"
            )


        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = consulta_comprobante_stp(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/consulta_conciliacion_saldo', type='json', auth='public', methods=['POST'], csrf=False)
    def consulta_conciliacion_saldo(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        if "fechaOperacion" in payload:
            cadena = build_cadena_consulta_conciliacion_saldo_fecha_historica(payload)
        else:
            cadena = build_cadena_consulta_conciliacion_saldo_fecha_actual(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        if "fechaOperacion" in payload:
            respuesta_stp = consulta_conciliacion_saldo_historica(payload)
        else:
            respuesta_stp = consulta_conciliacion_saldo_actual(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/consulta_instituciones', type='json', auth='public', methods=['POST'], csrf=False)
    def consulta_instituciones(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_consulta_instituciones(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = consulta_conciliacion_instituciones(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/codi/consulta_estado', type='json', auth='public', methods=['POST'], csrf=False)
    def codi_consulta_estado(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_codi_consulta_estado(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = codi_consulta_estado(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/codi/registro_cobro_no_presencial', type='json', auth='public', methods=['POST'], csrf=False)
    def codi_registro_cobro_no_presencial(self):
        payload = request.get_json_data()

        # ✓ Guarda el monto numérico por separado para el payload final
        # monto_float = float(payload['monto'])

        # ✓ Para construir la cadena, usa una copia con monto como string formateado
        # payload_cadena = dict(payload)
        # payload_cadena["monto"] = f"{monto_float:.2f}"

        cadena = build_cadena_codi_registro_cobro_no_presencial(payload)
        #print('CADENA>>>>>>>>>> ', cadena)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        #print('FIRMA>>>>>>>>>> ', firma)

        # Agregar firma al payload
        payload['firma'] = firma

        # ✓ Armar el payload final con monto como número, NO como string
        # payload_stp = {
        #     "numeroCelularCliente": payload["numeroCelularCliente"],
        #     "concepto": payload["concepto"],
        #     "minutosLimite": str(payload["minutosLimite"]),  # STP lo espera como string
        #     "monto": monto_float,  # ← número, no string
        #     "nombreBeneficiario2": payload["nombreBeneficiario2"],
        #     "tipoCuentaBeneficiario2": str(payload["tipoCuentaBeneficiario2"]),
        #     "cuentaBeneficiario2": payload["cuentaBeneficiario2"],
        #     "empresa": payload["empresa"],
        #     "tipoPagoDeSpei": str(payload["tipoPagoDeSpei"]),
        #     "numeroReferenciaComercio": str(payload["numeroReferenciaComercio"]),
        #     "firma": firma
        # }

        #print("PAYLOAD FINAL:", payload_stp)

        respuesta_stp = codi_registro_cobro(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/codi/registro_cobro_qr', type='json', auth='public', methods=['POST'], csrf=False)
    def codi_registro_cobro_qr(self):
        payload = request.get_json_data()

        # Construir cadena
        cadena = build_cadena_codi_registro_cobro_qr(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = codi_registro_cobro_qr(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/servicio/consulta_catalogo', type='json', auth='public', methods=['POST'], csrf=False)
    def consulta_catalogo_servicios(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_consulta_catalogo_servicios(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = consulta_catalogo_servicio(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    #TODO: REVISAR QUE MARCA A LA EMPRESA COMO INHABILITADA
    @http.route('/stp/servicio/pago_sin_referencia', type='json', auth='public', methods=['POST'], csrf=False)
    def pago_sin_referencia(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))
        payload["monto"] = f"{float(payload['monto']):.2f}"

        # Construir cadena
        cadena = build_cadena_pago_servicios_sin_referencia(payload)
        print("CADENA >>>", repr(cadena))

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print("FIRMA >>>", firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = pago_servicios_sin_referencia(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    #TODO: REVISAR QUE MARCA A LA EMPRESA COMO INHABILITADA
    @http.route('/stp/servicio/pago_con_referencia', type='json', auth='public', methods=['POST'], csrf=False)
    def pago_con_referencia(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        payload["monto"] = f"{float(payload['monto']):.2f}"

        # Construir cadena
        cadena = build_cadena_pago_servicios_con_referencia(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = pago_servicios_con_referencia(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/servicio/verificacion_referencia', type='json', auth='public', methods=['POST'], csrf=False)
    def verificacion_referencia(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_verificacion_referencia(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = verificacion_referencia(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/servicio/validacion_pago_servicio', type='json', auth='public', methods=['POST'], csrf=False)
    def validacion_pago_servicio(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_validacion_pago_servicio(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = valida_pago_servicio(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/servicio/reimpresion_tickets', type='json', auth='public', methods=['POST'], csrf=False)
    def reimpresion_tickets(self):
        payload = json.loads(request.httprequest.data.decode('utf-8'))

        # Construir cadena
        cadena = build_cadena_reimpresion_tickets(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = reimpresion_tickets(payload)

        return {
            'respuesta_stp': respuesta_stp
        }

    @http.route('/stp/servicio/historico_pagos', type='json', auth='public', methods=['POST'], csrf=False)
    def historico_pagos(self):
        payload = request.get_json_data()

        # Construir cadena
        cadena = build_cadena_historico_pagos(payload)

        # Firmar
        pem_path = 'custom_addons/Llave/dwit.pem'
        firma = sign_cadena(cadena, pem_path)
        print(firma)
        # De mientras para pruebas queda como esta arriba, para producción se sigue lo siguiente:
        # En odoo.conf
        # [options]
        # stp_private_key_path = C:\odoo_keys\dwit.pem
        #
        # En Python
        # from odoo.tools import config
        #
        # pem_path = config.get('stp_private_key_path')

        # Agregar firma al payload
        payload['firma'] = firma

        # Enviar a STP
        respuesta_stp = historico_pagos(payload)

        return {
            'respuesta_stp': respuesta_stp
        }
