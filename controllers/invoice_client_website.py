import base64
import re
from datetime import datetime, timedelta

import pytz
from unicodedata import normalize

from odoo import http 
from odoo.http import request
from PyPDF2 import PdfReader
import urllib.parse

import logging

# !TODO: UPDATE MAIL SENDER
class InvoiceClientWebsite(http.Controller):

    @http.route('/mi-factura', type='http', auth='public', website=True)
    def mi_factura(self, **kw):
        # Buscar solo compañías principales (sin parent_id)
        parent_companies = request.env['res.company'].sudo().search([('parent_id', '=', False)])
        
        return request.render('contabilidad_kuale.custom_invoice_template', {
            'companies': parent_companies,
        })

    @http.route('/create_invoice_complaint_ticket', type='http', auth='none', methods=['POST'], csrf=False)
    def create_invoice_complaint_ticket(self, **kwargs):
        _logger = logging.getLogger(__name__)
        try:
            _logger.info("Recibiendo reporte de problema de facturación: %s", kwargs)

            # Obtener los datos del formulario
            complaint_type = kwargs.get('complaint_type')
            rfc = kwargs.get('rfc')
            cp = kwargs.get('cp')
            receiver = kwargs.get('receiver')
            clave_tax_regime = kwargs.get('tax_regime')
            clave_cfdi_use = kwargs.get('cfdi_use')
            email = kwargs.get('email')
            num_ticket = kwargs.get('numticket')
            empresa_id = kwargs.get('empresa')
            sucursal_id = kwargs.get('sucursal')

            # Validar los datos obligatorios
            required_fields = {
                'complaint_type': complaint_type,
                'rfc': rfc,
                'cp': cp,
                'receiver': receiver,
                'tax_regime': clave_tax_regime,
                'cfdi_use': clave_cfdi_use,
                'email': email,
                'numTicket': num_ticket,
                'company2': empresa_id,
                'branch2': sucursal_id,
            }

            missing = [k for k, v in required_fields.items() if not v]
            if missing:
                _logger.warning("Faltan campos obligatorios: %s", missing)
                return request.make_json_response(
                    {'status': 400, 'message': f'Faltan campos obligatorios: {", ".join(missing)}'},
                    status=400
                )

            # Buscar régimen y uso de CFDI
            tax_regime = request.env['cfdi.claveregimenfiscal'].sudo().search(
                [('Clave_regimenFiscal', '=', clave_tax_regime)], limit=1)
            cfdi_use = request.env['cfdi.claveusocfdi'].sudo().search(
                [('Clave_UsoCFDI', '=', clave_cfdi_use)], limit=1)

            # Convertir IDs a entero
            empresa_id = int(empresa_id)
            sucursal_id = int(sucursal_id)
            
            # Obtener nombres de empresa y sucursal
            empresa = request.env['res.company'].sudo().browse(empresa_id)
            sucursal = request.env['res.company'].sudo().browse(sucursal_id)

            empresa_name = empresa.name if empresa else str(empresa_id)
            sucursal_name = sucursal.name if sucursal else str(sucursal_id)

            # Buscar el ticket real por folio + empresa + sucursal
            ticket_monitor = request.env['contabilidad_kuale.ticket_monitor'].sudo().search([
                ('ticket_folio', '=', num_ticket),
                ('company_id', '=', empresa_id),
                ('branch_id', '=', sucursal_id),
            ], limit=1)

            if not ticket_monitor:
                _logger.warning("Ticket no encontrado: folio=%s empresa=%s sucursal=%s", 
                            num_ticket, empresa_id, sucursal_id)
                return request.make_json_response(
                    {'status': 404, 'message': 'Número de ticket no encontrado para esta empresa y sucursal'},
                    status=404
                )

            # Crear el registro
            ticket = request.env['contabilidad_kuale.invoice_complaint_ticket'].sudo().create({
                'complaint_type': complaint_type,
                'rfc': rfc,
                'cp': cp,
                'receiver': receiver,
                'taxRegime': tax_regime.id,
                'cfdiUse': cfdi_use.id,
                'email': email,
                'empresa': empresa_id,
                'sucursal': sucursal_id,
                'ticket_id': ticket_monitor.id,
            })

            # Procesar archivos adjuntos
            files = {
                'invoice': request.httprequest.files.get('invoice'),
                'ticket': request.httprequest.files.get('ticket_t')
            }

            for file_key, file_obj in files.items():
                if file_obj:
                    file_data = file_obj.read()
                    file_extension = file_obj.filename.split('.')[-1].lower()
                    file_name = f"{file_key}.{file_extension}"
                    file_type = 'pdf' if file_extension == 'pdf' else 'image'

                    request.env['contabilidad_kuale.additional_file'].sudo().create({
                        'file': base64.b64encode(file_data),
                        'file_name': file_name,
                        'description': f"Archivo adjunto: {file_key}",
                        'file_type': file_type,
                        'invoice_complaint_id': ticket.id,
                    })

            # Enviar correo de notificación
            _logger.info("Iniciando preparación de correo de notificación...")
            subject = "Nuevo problema de facturación reportado"
            
            # Obtener descripciones legibles
            tax_regime_name = tax_regime.Descripcion if tax_regime else clave_tax_regime
            cfdi_use_name = cfdi_use.Descripcion if cfdi_use else clave_cfdi_use
            
            # Obtener el label del tipo de problema
            selection = request.env['contabilidad_kuale.invoice_complaint_ticket']._fields['complaint_type'].selection
            complaint_label = dict(selection).get(complaint_type, complaint_type)

            body = f"""
                <h3>Se ha reportado un nuevo problema de facturación</h3>
                <p><strong>Tipo de problema:</strong> {complaint_label}</p>
                
                <p><strong>Numero de ticket:</strong> {num_ticket}</p>
                <p><strong>Empresa:</strong> {empresa_name}</p>
                <p><strong>Sucursal:</strong> {sucursal_name}</p>
                <p><strong>RFC:</strong> {rfc}</p>
                <p><strong>Receptor:</strong> {receiver}</p>
                <p><strong>Régimen Fiscal:</strong> {tax_regime_name}</p>
                <p><strong>Uso CFDI:</strong> {cfdi_use_name}</p>
                <p><strong>Correo de contacto:</strong> {email}</p>
                
                <br/>
                <p>Por favor, revise la solicitud en el portal de Odoo.</p>
            """
            
            # Intentar obtener un remitente válido desde la compañía o servidor
            mail_server = request.env['ir.mail_server'].sudo().search([], limit=1)
            email_from = mail_server.smtp_user or request.env.company.email or 'facturacion@grupokuale.com.mx'

            mail_values = {
                'subject': subject,
                'body_html': body,
                'email_to': 'contactanos@grupokuale.com.mx',
                'email_from': email_from,
            }
            _logger.info("Enviando correo desde: %s a contactanos@grupokuale.com.mx", email_from)
            request.env['mail.mail'].sudo().create(mail_values).send()
            _logger.info("Proceso de envío de correo finalizado.")

            return request.make_json_response({
                'status': 200,
                'message': 'Su información ha sido recibida, en breve nos pondremos en contacto con usted. Gracias por su comprensión.',
            })

        except Exception as e:
            return request.make_json_response({
                'status': 400,
                'message': str(e),
            }, status=400)

    @http.route('/get_branches', type='http', auth='none', methods=['POST'], csrf=False)
    def get_branches(self, **kwargs):
        _logger = logging.getLogger(__name__)
        company_id = request.httprequest.json.get('company_id')
        
        _logger.info("COMPANY ID RECIBIDO: %s", company_id)
        
        # aqui quiero hacer la consulta para traer el RFC 
        
        if not company_id:
            return request.make_json_response({
                'status': 400,
                'message': 'company_id is required and must be valid'
            }, status=400)

        company_id = int(company_id)
        branches = request.env['res.company'].sudo().search([('parent_id', '=', company_id)])

        RFC_TINTO = 'TIN1008261J7'
        company = request.env['res.company'].sudo().browse(company_id)
        facturaCorreo = (company.rfc or '').upper() == RFC_TINTO.upper()
        
        
        # Si no hay sucursales, incluir la compañía principal
        if not branches:
            _logger.info("**************************not branches:",)
            parent_company = request.env['res.company'].sudo().browse(company_id)
            branches_data = [{'id': parent_company.id, 'name': parent_company.name}]
        else:
            _logger.info("**************************si branches:",)
            
            branches_data = [{'id': branch.id, 'name': branch.name, 'cp_branch': branch.cp_invoice_web} for branch in branches]

        return request.make_json_response({
            'status': 200,
            'data': branches_data,
            'company': company_id,
            'message': 'success',
            'facturaCorreo': facturaCorreo,
        }, status=200)

    @http.route('/get_img_ticket', type='http', auth='none', methods=['POST'], csrf=False)
    def get_img_ticket(self, **kwargs):
        _logger = logging.getLogger(__name__)
        company_id = request.httprequest.json.get('company_id')
        company_id = int(company_id)
        _logger.info("COMPANY ID RECIBIDO img: %s", company_id)

        if not company_id:
            return request.make_json_response({
                'status': 400,
                'message': 'company_id is required and must be valid'
            }, status=400)

        company = request.env['res.company'].sudo().browse(company_id)

        if not company.exists():
            return request.make_json_response({
                'status': 404,
                'message': 'Company not found'
            }, status=404)

        rfc = (company.rfc or "").strip().upper()

        if rfc == "HMA080617QV4":
            ruta = "/contabilidad_kuale/static/src/img/TICKET-CJR.png"
            ruta2 = "/contabilidad_kuale/static/src/img/Logo Carls Jr.svg"

        elif rfc == "TIN1008261J7":
            ruta = "/contabilidad_kuale/static/src/img/TICKET-TINTO.png"
            ruta2 = "/contabilidad_kuale/static/src/img/Logo Tinto.svg"

        elif rfc == "HMA041124FS9":
            ruta = "/contabilidad_kuale/static/src/img/TICKET-DQ.png"
            ruta2 = "/contabilidad_kuale/static/src/img/Logo DQ.svg"

        else:
            ruta = "/contabilidad_kuale/static/src/img/ejemplo_ticket.png"
            ruta2 = ""
        

        return request.make_json_response({
            'status': 200,
            'ticket_image': ruta,
            'company_image': ruta2
        }, status=200)

    @http.route('/upload', type='http', auth='public', methods=['POST'], csrf=False)
    def upload_pdf(self, **kwargs):
        try:
            # Obtener el archivo PDF desde la solicitud
            pdf_file = kwargs.get('pdf')
            if not pdf_file:
                return http.Response("No se recibió ningún archivo", status=400)
            # Leer el contenido del archivo PDF
            pdf_content = pdf_file.read()
            pdf_reader = PdfReader(pdf_file)
            # Extraer el texto del PDF
            extracted_data = []
            for page in pdf_reader.pages:
                extracted_data.append(page.extract_text())

            data = extract_fiscal_data("\n".join(extracted_data))
            # Construir la respuesta
            return request.make_json_response({
                'status': 200,
                'data': data,
                'message': 'success'
            }, status=200)

        except Exception as e:
            return http.Response(f"Error procesando el archivo: {str(e)}", status=500)

    def _get_friendly_error_message(self, error_msg):
        """
        Traduce errores técnicos del PAC a mensajes amigables para el cliente.
        """
        if not error_msg:
            return "Error durante la facturación, intente mas tarde"

        # Diccionario de errores basado en códigos del SAT (CFDI 4.0)
        error_map = {
            '40143': "El RFC ingresado no está registrado ante el SAT. Por favor, revísalo e intenta de nuevo.",
            '40144': "El Nombre o Razón Social no coincide con el RFC. Asegúrate de escribirlo tal cual aparece en la Constancia de Situación Fiscal (sin S.A. de C.V.).",
            '40145': "El Nombre o Razón Social no coincide con el RFC. Asegúrate de escribirlo tal cual aparece en la Constancia de Situación Fiscal (sin S.A. de C.V.).",
            '40147': "El Código Postal del domicilio fiscal es incorrecto para este RFC.",
            '40157': "El Régimen Fiscal seleccionado no es válido. Por favor, verifica tu Constancia de Situación Fiscal.",
            '40161': "El \"Uso de CFDI\" elegido no es compatible con tu Régimen Fiscal. Intenta con otro o consulta a tu contador.",
        }

        for code, message in error_map.items():
            if code in error_msg:
                return message

        return "Error durante la facturación, intente mas tarde"

    @http.route('/invoice/data', type='http', auth='none', methods=['POST'], csrf=False)
    def invoice_data(self, **kw):
        # Recibir los datos del formulario
        data = request.httprequest.json
        print('Data received:', data)

        company_id, branch_id, ticket, date, amount, rfc, receiver, address, tax_regime, cfdi_use, client_email, client_phone, extra_address = (
            data.get(key) for key in [
            'company_id', 'branch_id', 'ticket', 'date', 'amount',
            'rfc', 'receiver', 'address', 'tax_regime',
            'cfdi_use', 'client_email', 'client_phone', 'extra_address'
        ]
        )
        print('extra address: ', data.get('extra_address'))

        # Convertir a rango de fecha amplio para ignorar problemas de zona horaria o del POS
        if date:
            date = date[:10]
        base_dt = datetime.strptime(date, '%Y-%m-%d')
        start_dt = base_dt - timedelta(days=2)
        end_dt = base_dt + timedelta(days=3)

        # Buscar el ticket en el modelo contabilidad_kuale.ticket_monitor
        ticket_record = request.env['contabilidad_kuale.ticket_monitor'].sudo().search([
            ('company_id', '=', int(company_id)),
            ('branch_id', '=', int(branch_id)),
            ('ticket_folio', '=', ticket),
            ('total', '>=', float(amount) - 0.01),
            ('total', '<=', float(amount) + 0.01),
            ('date', '>=', start_dt),
            ('date', '<', end_dt),
        ], limit=1)

        if not ticket_record:
            return request.make_json_response({
                'status': 400,
                'message': 'No se encontró un ticket con los datos proporcionados',
            }, status=400)

        if ticket_record.invoiced:
            print('Ticket ya facturado')
            return request.make_json_response({
                'status': 400,
                'message': 'El ticket ya ha sido facturado',
            }, status=400)
        else:
            print('Ticket no facturado, generando XML...')
            xml = self._generate_xml(ticket_record, data)
            print('xml generado, en proceso de timbrar')
            if data.get('extra_address'):
                extra_address = data.get('extra_address')
                domicilio_fiscal_receptor = f"{extra_address.get('street01')}, {extra_address.get('street02')}, {extra_address.get('city')}, CP {data.get('address')}"
                response = ticket_record.action_timbrar(xml, domicilio_fiscal_receptor)
            else:
                response = ticket_record.action_timbrar(xml)
            if response.get('status') == 'success':
                print('XML generado y timbrado exitosamente')

                # Actualizamos los datos del cliente en el ticket antes de enviar el correo
                tax_regime_record = request.env['cfdi.claveregimenfiscal'].sudo().search([('Clave_regimenFiscal', '=', tax_regime)], limit=1)
                cfdi_use_record = request.env['cfdi.claveusocfdi'].sudo().search([('Clave_UsoCFDI', '=', cfdi_use)], limit=1)

                ticket_record.sudo().write({
                    'client_rfc': rfc,
                    'client_email': client_email,
                    'client_tax_regimen_id': tax_regime_record.id if tax_regime_record else False,
                    'client_cfdi_use_id': cfdi_use_record.id if cfdi_use_record else False,
                    'client_cp': address,
                    'client_name': receiver,
                    'invoiced': True,
                    'invoiced_type': 'web'
                })

                # IMPORTANTE: Llamada al método que definimos en ticket_monitor.py
                try:
                    # Usamos sudo() para evitar problemas de permisos con usuarios públicos del website
                    ticket_record.sudo().send_invoice_email(client_email)
                except Exception as e:
                    # Logeamos el error pero no detenemos el proceso, ya que la factura ya se timbró
                    print(f"Error al enviar el correo: {e}")

                return request.make_json_response({
                    'status': 200,
                    'message': 'Ticket facturado y enviado correctamente',
                    'data': data
                }, status=200)
            else:
                raw_error = response.get('message', '')
                print('XML no timbrado por error en sistema: \n', raw_error,
                      '\n Intente mas tarde nuevamente:',)
                
                friendly_message = self._get_friendly_error_message(raw_error)
                
                return request.make_json_response({
                    'status': 417,
                    'message': friendly_message,
                    'error': raw_error
                }, status=417)

    @http.route('/send_email_to',type='http', auth='none', methods=['POST'], csrf=False)
    def send_email_to(self, **kw):
        data = request.httprequest.json
        ticket_folio = data.get('ticket_folio')
        email = data.get('email')
        company_id = data.get('company_id')
        branch_id = data.get('branch_id')
        amount = data.get('amount')
        date = data.get('date')

        if not ticket_folio or not email:
            return request.make_json_response({
                'status': 400,
                'data':[],
                'message':'Error al mandar los datos intente nuevamente en un momento'
            },status=400)
        if date:
            date = date[:10]
        base_dt = datetime.strptime(date, '%Y-%m-%d')
        start_dt = base_dt - timedelta(days=2)
        end_dt = base_dt + timedelta(days=3)
        
        ticket_record = request.env['contabilidad_kuale.ticket_monitor'].sudo().search([
            ('company_id', '=', int(company_id)),
            ('branch_id', '=', int(branch_id)),
            ('ticket_folio', '=', ticket_folio),
            ('total', '>=', float(amount) - 0.01),
            ('total', '<=', float(amount) + 0.01),
            ('date', '>=', start_dt),
            ('date', '<', end_dt),
        ], limit=1)
        if not ticket_record:
            return request.make_json_response({
                'status': 417,
                'data':[],
                'message':'Error al mandar los datos intente nuevamente'
            })
        ticket_record.sudo().send_invoice_email(email)
        return request.make_json_response({
            'status': 200,
            'data': [],
            'message': 'Factura enviada correctamente',
        })

    @http.route('/download_xml/<int:ticket_id>', type='http', auth='none', website=True, csrf=False)
    def download_ticket_xml(self, ticket_id, **kwargs):
        ticket = request.env['contabilidad_kuale.ticket_monitor'].sudo().browse(ticket_id)

        if not ticket.exists():
            return request.not_found()

        xml_file = request.env['contabilidad_kuale.additional_file'].sudo().search([
            ('ticket_monitor_id', '=', ticket.id),
            ('file_type', '=', 'xml')
        ], order='id desc', limit=1)

        if not xml_file or not xml_file.file:
            return request.not_found()

        file_data = base64.b64decode(xml_file.file)
        filename = xml_file.file_name or 'archivo.xml'
        quoted_name = urllib.parse.quote(filename)

        headers = [
            ('Content-Type', 'application/xml'),
            ('Content-Disposition', f"attachment; filename*=UTF-8''{quoted_name}")
        ]

        return request.make_response(file_data, headers=headers)

    @http.route('/download_pdf/<int:ticket_id>', type='http', auth='none', website=True, csrf=False)
    def download_ticket_pdf(self, ticket_id, **kwargs):
        ticket = request.env['contabilidad_kuale.ticket_monitor'].sudo().browse(ticket_id)  

        if not ticket.exists():
            return request.not_found()

        pdf_file = request.env['contabilidad_kuale.additional_file'].sudo().search([
            ('ticket_monitor_id', '=', ticket.id),
            ('file_type', '=', 'pdf')
        ], order='id desc', limit=1)

        if not pdf_file or not pdf_file.file:
            # Fallback: regenerar el PDF si el ticket está timbrado y tiene XML
            if ticket.invoiced and ticket.ticket_status == 'timbrado':
                try:
                    ticket.action_generate_invoice_pdf()
                    pdf_file = request.env['contabilidad_kuale.additional_file'].sudo().search([
                        ('ticket_monitor_id', '=', ticket.id),
                        ('file_type', '=', 'pdf')
                    ], order='id desc', limit=1)
                except Exception:
                    pass

            if not pdf_file or not pdf_file.file:
                return request.not_found()

        file_data = base64.b64decode(pdf_file.file)
        filename = pdf_file.file_name or 'archivo.pdf'
        quoted_name = urllib.parse.quote(filename)

        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f"attachment; filename*=UTF-8''{quoted_name}")
        ]

        return request.make_response(file_data, headers=headers)

    @http.route('/check/ticket/<string:ticket_folio>', type='http', auth='none', website=True, csrf=False)
    def check_ticket(self, ticket_folio):
        ticket = request.env['contabilidad_kuale.ticket_monitor'].sudo().search([('ticket_folio', '=', ticket_folio)],
                                                                                limit=1)
        if ticket:
            if not ticket.invoiced:
                return request.make_json_response({
                    'status': 200,
                    'data': [{
                        'invoiced': False
                    }],
                    'message': 'Ticket no facturado',
                })
            else:
                return request.make_json_response({
                    'status': 200,
                    'data': [{
                        'invoiced': True
                    }],
                    'message': 'Ticket facturado',
                })

    @http.route('/validate/ticket', type='http', auth='none', methods=['POST'], csrf=False)
    def validate_ticket(self, **kwargs):
        data = request.httprequest.json
        print('dat: ', data)
        ticket_folio = data.get('ticket_folio')
        branch_id = int(data.get('branch_id'))
        date_str = data.get('date')
        amount = float(data.get('amount', 0.0))

        # Convertir la fecha recibida a rango amplio, omitiendo la hora y problemas del POS
        if date_str:
            date_str = date_str[:10]
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        start_dt = date_obj - timedelta(days=2)
        end_dt = date_obj + timedelta(days=3)

        # Buscar tickets del mismo día ignorando hora
        tickets = request.env['contabilidad_kuale.ticket_monitor'].sudo().search([
            ('ticket_folio', '=', ticket_folio),
            ('branch_id', '=', branch_id),
            ('total', '>=', amount - 0.01),
            ('total', '<=', amount + 0.01),
            ('date', '>=', start_dt),
            ('date', '<', end_dt),
        ], limit=1)

        print('ticket encontrado:', tickets, tickets.date)

        if not tickets:
            return request.make_json_response({
                'status': 417,
                'message': f'No se encontró el ticket. Verifique los datos e intente nuevamente.',
                'error': "Not Found"
            }, status=417)

        return request.make_json_response({
            'status': 200,
            'message': 'Ticket encontrado en el sistema',
            'data': [{
                'id': tickets.id,
                'ticket_folio': tickets.ticket_folio,
                'amount': tickets.total,
                'branch_id': tickets.branch_id.id,
                'date': tickets.date,
                'invoiced': tickets.invoiced,
                'payment_type_clave': tickets.payment_type.Clave_forma_de_pago or '',
                'payment_type_descripcion': tickets.payment_type.Descripcion or '',
            }]
        }, status=200)

    @http.route('/search/by/rfc/<string:rfc>', type='http', auth="none", methods=['GET'], website=True, csrf=False)
    def search_by_rfc(self, rfc):
        rfc = rfc.strip().upper()  # Normalizar RFC
        if not rfc or len(rfc) not in [12, 13]:
            return request.make_json_response({'error': 'RFC no encontrado'}, status=404)

        '''
        # Buscar en res.partner (clientes)
        cliente = request.env['res.partner'].sudo().search([('vat', '=', rfc)], limit=1)
        if cliente:
            return {
                'name': cliente.name,
                'zip': cliente.zip or '',
                'tax_regime': cliente.l10n_mx_edi_fiscal_regime or '',
                'cfdi_use': cliente.l10n_mx_edi_usage or '',
                'email': cliente.email or '',
            }
'''
        # Buscar en el modelo de tickets
        ticket = request.env['contabilidad_kuale.ticket_monitor'].sudo().search([('client_rfc', '=', rfc)], limit=1)
        if ticket:
            data = {
                'name': ticket.client_name or '',
                'zip': ticket.client_cp or '',
                'tax_regime': ticket.client_tax_regimen_id.Clave_regimenFiscal if ticket.client_tax_regimen_id else '',
                'cfdi_use': ticket.client_cfdi_use_id.Clave_UsoCFDI if ticket.client_cfdi_use_id else '',
                'email': ticket.client_email or '',
            }
            return request.make_json_response(data, status=200)

        return request.make_json_response({'error': 'RFC no encontrado'}, status=404)

    def _generate_xml(self, ticket_monitor, data):
        fecha_emision = str(ticket_monitor.date).replace(" ", "T")[:19]
        forma_pago = ticket_monitor.payment_type.Clave_forma_de_pago
        metodo_pago = ticket_monitor.payment_method.Clave_metodo_de_pago
        exportacion = "01"
        print('branch: ', ticket_monitor.branch_id)
        matriz = request.env['res.company'].sudo().browse([int(ticket_monitor.company_id)])
        company = request.env['res.company'].sudo().browse([int(ticket_monitor.branch_id)])
        if not company:
            return request.make_json_response({
                'status': 400,
                'data': [],
                'error': 'Error en datos de facturación, revise su información de compra'
            }, status=400)
        rfc_emisor = company.rfc
        lugar_expedicion = company.zip if company.zip else '10000'
        print("RFC EMISOR: ", company.rfc)

        nombre_emisor = cfdi_escape(company.business_name)
        regimen_fiscal = company.regimen_fiscal.Clave_regimenFiscal

        serie = cfdi_escape(company.client_serial_number or '')
        folio = company.client_folio_number
        folio = str(folio).zfill(4)

        rfc_receptor = data.get("rfc", "XAXX010101000")
        nombre_receptor = cfdi_escape(data.get("receiver", "PUBLICO EN GENERAL"))
        domicilio_fiscal_receptor = cfdi_escape(data.get("address", "XXXXX"))
        regimen_fiscal_receptor = data.get("tax_regime") or "616"
        uso_cfdi = data.get("cfdi_use") or "S01"

        subtotal = 0.0
        total_iva = 0.0
        total_descuento = 0.0
        conceptos_xml = ""

        # single_concept = matriz.single_concept
        single_concept = company.single_concept

        if single_concept:
            print("single_concept")
            # Concepto único
            total_amount = sum(line.unit_price * line.quantity for line in ticket_monitor.product_line)
            total_discount = sum(line.discount for line in ticket_monitor.product_line if line.discount > 0)
            base_iva = total_amount - total_discount
            importe_iva = round(base_iva * 0.16, 6)

            subtotal = base_iva
            subtotal_no_desc = total_amount
            total_iva = importe_iva
            total_descuento = total_discount
            concepto_descuento = f' Descuento="{total_descuento:.2f}"' if total_descuento > 0 else ""

            # !TODO: DEFINE CARLS AND TITO IDs
            if matriz.client_invoice_color == "4" or company.client_invoice_color == "4":
                # datos de lo de CARLS
                clave_prod_serv = '90101500'
                clave_unidad = 'E48'
                descripcion = cfdi_escape(f'Consumo de alimentos - Número de ticket {ticket_monitor.ticket_folio} - Fecha de consumo {ticket_monitor.date.strftime("%d/%m/%Y")}')
            else:
                # datos de lo de TINTO
                clave_prod_serv = '91111500'
                clave_unidad = 'E48'
                descripcion = cfdi_escape(f'Servicio de tintorería - Número de ticket {ticket_monitor.ticket_folio} - Fecha {ticket_monitor.date.strftime("%d/%m/%Y")}')
            descripcion = remove_non_ascii(descripcion)
            conceptos_xml = f'''
                <cfdi:Concepto ClaveProdServ="{clave_prod_serv}" NoIdentificacion="{cfdi_escape(ticket_monitor.ticket_folio)}" Cantidad="1"
                ClaveUnidad="{clave_unidad}" Descripcion="{descripcion}" ValorUnitario="{round(total_amount, 2):.2f}" Importe="{round(total_amount, 2):.2f}"
                {concepto_descuento} ObjetoImp="02">
                    <cfdi:Impuestos>
                        <cfdi:Traslados>
                            <cfdi:Traslado Base="{round(subtotal, 2):.2f}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{round(importe_iva, 2):.2f}"/>
                        </cfdi:Traslados>
                    </cfdi:Impuestos>
                </cfdi:Concepto>
            '''
        else:
            # Un concepto por producto
            for line in ticket_monitor.product_line:
                product = request.env['product.template'].sudo().search([('third_party_id', '=', line.third_party_id)],
                                                                        limit=1)
                clave_prod_serv = product.sat_code_id.code if product else '01010101'
                no_identificacion = cfdi_escape(product.identification_number if product else ticket_monitor.ticket_folio)
                cantidad = str(line.quantity) if line.quantity else '1'
                clave_unidad = product.unit_clave.Clave_unidad if product else "ACT"
                descripcion = cfdi_escape(product.name if product else "Venta")
                descripcion = remove_non_ascii(descripcion)

                descuento = round(line.discount, 2) if line.discount and line.discount > 0 else 0.0
                valor_unitario = round(line.unit_price, 6)
                importe = round(line.unit_price * line.quantity, 6)
                base_iva = round(importe - descuento, 6)
                importe_iva = round(base_iva * 0.16, 6)

                subtotal += importe
                total_iva += importe_iva
                total_descuento += descuento

                concepto_descuento = f' Descuento="{descuento:.2f}"' if descuento > 0 else ""
                descripcion_final = cfdi_escape(f'Productos destinados a la alimentación {descripcion} - Número de ticket {ticket_monitor.ticket_folio} - Fecha de consumo {ticket_monitor.date.strftime("%d/%m/%Y")}')
                descripcion_final = remove_non_ascii(descripcion_final)
                conceptos_xml += f'''<cfdi:Concepto ClaveProdServ="{clave_prod_serv}" NoIdentificacion="{no_identificacion}" Cantidad="{cantidad}"
                    ClaveUnidad="{clave_unidad}" Descripcion="{descripcion_final}" ValorUnitario="{valor_unitario}" Importe="{importe}"
                    {concepto_descuento} ObjetoImp="02">
                        <cfdi:Impuestos>
                            <cfdi:Traslados>
                                <cfdi:Traslado Base="{base_iva}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{importe_iva}"/>
                            </cfdi:Traslados>
                        </cfdi:Impuestos>
                    </cfdi:Concepto>'''

        if single_concept:
            if total_descuento > 0:
                total = subtotal + total_iva
                descuento_attr = f' Descuento="{round(total_descuento, 2):.2f}"'
            else:
                subtotal_no_desc = subtotal
                total = subtotal + total_iva
                descuento_attr = ""
        else:
            if total_descuento > 0:
                subtotal_no_desc = subtotal
                subtotal = subtotal - total_descuento
                total = subtotal + total_iva
                descuento_attr = f' Descuento="{round(total_descuento, 2):.2f}"'
            else:
                subtotal_no_desc = subtotal
                total = subtotal + total_iva
                descuento_attr = ""

        xml = f'''
        <cfdi:Comprobante Version="4.0" Serie="{serie}" Folio="{folio}" Fecha="{datetime.now(pytz.timezone('America/Mexico_City')).strftime('%Y-%m-%dT%H:%M:%S')}" SubTotal="{round(subtotal_no_desc, 2):.2f}" Total="{round(total, 2):.2f}" 
        Moneda="MXN" TipoDeComprobante="I" LugarExpedicion="{lugar_expedicion}" FormaPago="{forma_pago}" MetodoPago="{metodo_pago}"
        Exportacion="{exportacion}" {descuento_attr}
        xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd">
            <cfdi:Emisor Rfc="{rfc_emisor}" Nombre="{nombre_emisor}" RegimenFiscal="{regimen_fiscal}"/>
            <cfdi:Receptor Rfc="{rfc_receptor}" Nombre="{nombre_receptor}" DomicilioFiscalReceptor="{domicilio_fiscal_receptor}"
            RegimenFiscalReceptor="{regimen_fiscal_receptor}" UsoCFDI="{uso_cfdi}"/>
            <cfdi:Conceptos>
                {conceptos_xml}
            </cfdi:Conceptos>
            <cfdi:Impuestos TotalImpuestosTrasladados="{round(total_iva, 2):.2f}">
                <cfdi:Traslados>
                    <cfdi:Traslado Base="{round(subtotal, 2):.2f}" Impuesto="002" TipoFactor="Tasa" 
                    TasaOCuota="0.160000" Importe="{round(total_iva, 2):.2f}"/>
                </cfdi:Traslados>
            </cfdi:Impuestos>
        </cfdi:Comprobante>
        '''
        return xml

    @http.route('/custom/invoice/delete_temp_pdf/<int:file_id>', type='json', auth='none')
    def delete_temp_pdf(self, file_id, **kwargs):
        record = request.env['contabilidad_kuale.additional_file'].sudo().browse(file_id)
        if record.exists():
            record.unlink()
            return {'status': 'ok'}
        return {'status': 'not found'}


def extract_fiscal_data(text):
    text = text.replace('\\n', '\n').replace('\\r', '')

    # 🔥 NORMALIZACIÓN CLAVE
    text = re.sub(r'\s+', ' ', text)

    print('text limpio:', text)

    # =========================
    # RFC
    # =========================
    rfc = ""
    rfc_match = re.search(r"RFC:\s*([A-Z0-9]{12,13})", text)
    if rfc_match:
        rfc = rfc_match.group(1)

    # =========================
    # Nombre / Razón Social (desde cédula)
    # =========================
    razon_social = ""

    razon_pattern = r"Registro Federal de Contribuyentes\s+(.+?)\s+Nombre, denominaci[oó]n o raz[oó]n\s+social"
    razon_match = re.search(razon_pattern, text, re.DOTALL)

    if razon_match:
        razon_social = razon_match.group(1).strip()
        razon_social = re.sub(r'\s+', ' ', razon_social)

    # =========================
    # Código Postal
    # =========================
    cp = ""
    cp_match = re.search(r"CódigoPostal:\s*(\d{5})", text)
    if cp_match:
        cp = cp_match.group(1)
    else:
        cp = "No encontrado"

    # =========================
    # Nombre final
    # =========================
    nombre_resultado = razon_social

    # fallback (por si falla la cédula)
    if not nombre_resultado:
        nombre = ""
        apellido_pat = ""
        apellido_mat = ""

        nombre_match = re.search(r"Nombre\(s\):\s*([A-ZÑ\s]+)", text)
        if nombre_match:
            nombre = nombre_match.group(1)

        ap_pat_match = re.search(r"PrimerApellido:\s*([A-ZÑ\s]+)", text)
        if ap_pat_match:
            apellido_pat = ap_pat_match.group(1)

        ap_mat_match = re.search(r"Segundo Apellido:\s*([A-ZÑ\s]+)", text)
        if ap_mat_match:
            apellido_mat = ap_mat_match.group(1)

        nombre_resultado = f"{nombre} {apellido_pat} {apellido_mat}".strip()
        nombre_resultado = re.sub(r'\s+', ' ', nombre_resultado)

    # =========================
    # Detectar tipo de persona
    # =========================
    es_persona_fisica = "Nombre(s):" in text

    # =========================
    # Régimen Fiscal
    # =========================
    regimen_fiscal = "No encontrado"

    if es_persona_fisica:
        regimenes_fisica = {
            '612': 'Personas Físicas con Actividades Empresariales y Profesionales',
            '621': 'Incorporación Fiscal',
            '626': 'Régimen Simplificado de Confianza',
            '625': 'Régimen de las Actividades Empresariales con ingresos a través de Plataformas Tecnológicas',
            '606': 'Arrendamiento',
            '605': 'Sueldos y Salarios e Ingresos Asimilados a Salarios',
            '607': 'Régimen de Enajenación o Adquisición de Bienes',
            '611': 'Ingresos por Dividendos (socios y accionistas)',
            '610': 'Residentes en el Extranjero sin Establecimiento Permanente en México',
            '614': 'Ingresos por intereses',
            '615': 'Régimen de los ingresos por obtención de premios',
            '616': 'Sin obligaciones fiscales',
            '608': 'Demás ingresos',
        }

        for clave, nombre_reg in regimenes_fisica.items():
            if nombre_reg in text:
                regimen_fiscal = nombre_reg
                break

    else:
        regimenes_moral = {
            '601': 'General de Ley Personas Morales',
            '603': 'Personas Morales con Fines no Lucrativos',
            '620': 'Sociedades Cooperativas de Producción que optan por diferir sus ingresos',
            '622': 'Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras',
            '623': 'Opcional para Grupos de Sociedades',
            '624': 'Coordinados',
            '626': 'Régimen Simplificado de Confianza',
            '610': 'Residentes en el Extranjero sin Establecimiento Permanente en México',
        }

        for clave, nombre_reg in regimenes_moral.items():
            if nombre_reg in text:
                regimen_fiscal = nombre_reg
                break

    # =========================
    # RESULTADO FINAL
    # =========================
    extracted_data = {
        "RFC": rfc,
        "Nombre o Razón Social": nombre_resultado,
        "Código Postal": cp,
        "Régimen Fiscal": regimen_fiscal,
    }

    print('extracted_data:', extracted_data)

    return extracted_data

def remove_non_ascii(text):
    return ''.join(c for c in normalize('NFKD', text) if ord(c) < 128)

def cfdi_escape(text):
    """Escapa caracteres especiales para atributos XML según el estándar SAT."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return (text.replace("&", "&amp;")
                .replace('"', "&quot;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("'", "&apos;"))
