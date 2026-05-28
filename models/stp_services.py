import base64
import requests
from odoo import models
from odoo.tools import config
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

class STPService(models.AbstractModel):
    _name = 'stp.service'
    _description = 'Servicio STP'

    # =========================
    # CADENA ORIGINAL
    # =========================
    def _build_cadena_original(self, data: dict) -> str:
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

    def _build_cadena_consult_current_date(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}||"  # Obligatorio
        )

        return cadena

    def _build_cadena_consult_historical_date(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}|"  # Obligatorio
            f"{v('fechaOperacion')}||"  # Obligatorio
        )

        return cadena

    def _build_cadena_consult_natural_date(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}|"  # Obligatorio
            f"{v('fechaNatural')}|"  # Obligatorio
            f"{v('horaCapturaInicio')}|"  # Obligatorio
            f"{v('horaCapturaFin')}||"  # Obligatorio
        )

        return cadena

    def _build_cadena_consult_account_balance(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}|"  # Obligatorio
            f"{v('cuentaOrdenante')}|||"  # Obligatorio
        )

        return cadena

    def _build_cadena_consult_account_balance_historical(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}|"  # Obligatorio
            f"{v('cuentaOrdenante')}|"  # Obligatorio
            f"{v('fecha')}||"  # Obligatorio
        )

        return cadena

    def _build_cadena_consult_receipt_natural_date(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}|"  # Obligatorio
            f"{v('claveRastreo')}|"  # Obligatorio
            f"{v('fechaNatural')}|||"  # Obligatorio
        )

        return cadena

    def _build_cadena_consult_receipt_operation_date(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}|"  # Obligatorio
            f"{v('claveRastreo')}||"  # Obligatorio
            f"{v('fechaOperacion')}||"  # Obligatorio
        )

        return cadena

    def _build_cadena_consult_balance_conciliation_historical(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}|"  # Obligatorio
            f"{v('fechaOperacion')}||"  # Obligatorio
        )

        return cadena

    def _build_cadena_consult_balance_conciliation(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}||"  # Obligatorio
        )

        return cadena

    def _build_cadena_consult_institutions(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}||"  # Obligatorio
        )

        return cadena

    def _build_cadena_consult_ws_services(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}||"  # Obligatorio
        )

        return cadena

    def _build_cadena_ws_payment_services_without_reference(self, data: dict) -> str:
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

    def _build_cadena_ws_payment_services_with_reference(self, data: dict) -> str:
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

    def _build_cadena_ws_reference_verification(self, data: dict) -> str:
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

    def _build_cadena_ws_service_payment_validation(self, data: dict) -> str:
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

    def _build_cadena_ws_ticket_reprint(self, data: dict) -> str:
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

    def _build_cadena_ws_payment_historical(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('empresa')}|"  # Obligatorio
            f"{v('fechaPago')}|"  # Obligatorio
            f"{v('page')}||"  # Obligatorio
        )

        return cadena

    def _build_cadena_codi_consult(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('folioCodi')}|"  # Obligatorio
            f"{v('empresa')}||"  # Obligatorio
        )

        return cadena

    def _build_cadena_codi_register_qr(self, data: dict) -> str:
        def v(key):
            val = data.get(key)
            return "" if val is None else str(val)

        cadena = (
            "||"
            f"{v('numeroReferenciaComercio')}|"  # Obligatorio
            f"{v('concepto')}|"  # Obligatorio
            f"{v('minutosLimite')}|"  # Obligatorio
            f"{v('monto')}|"  # Obligatorio
            f"{v('nombreBeneficiario')}|"  # Obligatorio
            f"{v('bancoBeneficiario')}|"  # Obligatorio
            f"{v('tipoCuentaBeneficiario')}|"  # Obligatorio
            f"{v('cuentaBeneficiario')}|"  # Obligatorio
            f"{v('empresa')}|"  # Obligatorio
            f"{v('tipoPagoDeSpei')}||"  # Obligatorio
        )

        return cadena

    # =========================
    # FIRMA
    # =========================
    def _sign_cadena(self, cadena: str) -> str:

        pem_path = config.get('stp_private_key_path')
        if not pem_path:
            raise Exception("No está configurado stp_private_key_path en odoo.conf")

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

    # =========================
    # ENVÍO STP
    # =========================
    def registrar_orden(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_original(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_url')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.put(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_order_current_date(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_consult_current_date(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_current_date')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_order_historical_date(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_consult_historical_date(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_historical_date')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_order_natural_date(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_consult_natural_date(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_natural_date')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_account_balance(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_consult_account_balance(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_account_balance')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_account_balance_historical(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_consult_account_balance_historical(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_account_balance')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_receipt_natural_date(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_consult_receipt_natural_date(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_receipt')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_receipt_operation_date(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_consult_receipt_operation_date(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_receipt')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_balance_conciliation_historical(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_consult_balance_conciliation_historical(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_balance_conciliation_historical')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_balance_conciliation(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_consult_balance_conciliation(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_balance_conciliation')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_institutions(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_consult_institutions(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_institutions')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_ws_services(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_consult_ws_services(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_ws_services')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_ws_payment_services_without_reference(self, payload: dict):

        payload["monto"] = f"{float(payload['monto']):.2f}"
        # Construir cadena
        cadena = self._build_cadena_ws_payment_services_without_reference(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_ws_payment_services_without_reference')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        try:
            data = response.json()
        except Exception:
            raise Exception(f"Respuesta inválida STP:\n{response.text}")

        # ⚠️ Solo error técnico real
        if response.status_code not in (200, 401):
            raise Exception(f"Error HTTP {response.status_code}:\n{response.text}")

        return data

    def consult_ws_payment_services_with_reference(self, payload: dict):
        payload["monto"] = f"{float(payload['monto']):.2f}"

        # Construir cadena
        cadena = self._build_cadena_ws_payment_services_with_reference(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_ws_payment_services_with_reference')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        try:
            data = response.json()
        except Exception:
            raise Exception("Respuesta inválida del servicio STP")

        # Si el servicio respondió con error funcional
        if response.status_code != 200:
            mensaje = data.get("mensaje", "Error desconocido en STP")
            raise Exception(mensaje)

        return data

    def consult_ws_reference_verification(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_ws_reference_verification(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_ws_reference_verification')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_ws_service_payment_validation(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_ws_service_payment_validation(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_ws_service_payment_validation')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_ws_ticket_reprint(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_ws_ticket_reprint(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_ws_ticket_reprint')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_ws_payment_historical(self, payload: dict):

        # Construir cadena
        cadena = self._build_cadena_ws_payment_historical(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_consult_ws_payment_historical')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def consult_codi(self, payload: dict):
        # Construir cadena
        cadena = self._build_cadena_codi_consult(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_codi_consult')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    def register_codi_qr(self, payload: dict):
        # Construir cadena
        cadena = self._build_cadena_codi_register_qr(payload)

        # Firmar
        firma = self._sign_cadena(cadena)

        payload['firma'] = firma

        # URL desde config
        url = config.get('stp_api_codi_qr')
        if not url:
            raise Exception("No está configurado stp_url en odoo.conf")

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()
