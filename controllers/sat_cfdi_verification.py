from odoo import http
from odoo.http import request
import json
import requests
from lxml import etree
from xml.sax.saxutils import escape


SAT_URL = "https://consultaqr.facturaelectronica.sat.gob.mx/ConsultaCFDIService.svc"

class CfdiValidationController(http.Controller):

    @http.route('/api/cfdi/validate', type='http', auth='none', methods=['POST'], csrf=False)
    def validate_cfdi(self, **kw):
        payload = json.loads(request.httprequest.data)

        # EXPRESION PARA EL SAT
        expresion_raw = (
            f"?re={payload['rfc_emisor']}"
            f"&rr={payload['rfc_receptor']}"
            f"&tt={float(payload['total']):.6f}"
            f"&id={payload['uuid']}"
            f"&fe={payload['sello'][-8:]}"
        )

        expresion = escape(expresion_raw)

        # SOAP válido (una sola línea)
        soap_body = (
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:tem="http://tempuri.org/">'
            '<soapenv:Header/>'
            '<soapenv:Body>'
            '<tem:Consulta>'
            f'<tem:expresionImpresa>{expresion}</tem:expresionImpresa>'
            '</tem:Consulta>'
            '</soapenv:Body>'
            '</soapenv:Envelope>'
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "http://tempuri.org/IConsultaCFDIService/Consulta",
        }

        # LLAMADA AL SAT
        response = requests.post(
            SAT_URL,
            data=soap_body.encode("utf-8"),
            headers=headers,
            timeout=15
        )
        response.raise_for_status()

        # RESPUESTA
        xml = etree.fromstring(response.content)
        ns = {
            "a": "http://schemas.datacontract.org/2004/07/Sat.Cfdi.Negocio.ConsultaCfdi.Servicio"
        }

        return self._json_response({
            "success": True,
            "estado": xml.findtext(".//a:Estado", namespaces=ns),
            "codigo_estatus": xml.findtext(".//a:CodigoEstatus", namespaces=ns),
            "es_cancelable": xml.findtext(".//a:EsCancelable", namespaces=ns),
            "validacion_efos": xml.findtext(".//a:ValidacionEFOS", namespaces=ns),
        })

    def _json_response(self, data, status=200):
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
            status=status
        )
