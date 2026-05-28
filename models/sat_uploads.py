# -*- coding: utf-8 -*-
import calendar

from odoo import api, fields, models
import base64
import io
import time
import zipfile
import logging
from cfdiclient import (
    Fiel, 
    Autenticacion, 
    VerificaSolicitudDescarga, 
    DescargaMasiva, 
    SolicitaDescargaEmitidos,
    SolicitaDescargaRecibidos,
)
import datetime

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SATUploads(models.Model):
    _name = 'sat.uploads'
    _description = "SAT Uploads"

    name = fields.Char('Referencia', required=True)
    file = fields.Binary(string='Archivo')
    file_name = fields.Char('Archivo')

    month = fields.Selection(
        [(str(i), datetime.date(2025, i, 1).strftime('%B')) for i in range(1, 13)],
        string="Mes", help='Mes de factura'
    )
    year = fields.Selection(
        [(str(y), str(y)) for y in range(2020, datetime.date.today().year + 1)],
        string="Ejercicio", help="Año de factura")

    @api.model
    def create(self, values):
        # Se procesa el archivo segun tipo ZIP o XML...
        filename = values.get('file_name') or ''
        document_type = self.env.context.get('document_type', 'recibido')
        
        if filename.endswith(".zip"):
            # Decompresion and XML extraction...
            file_data = base64.b64decode(values.get('file'))
            with zipfile.ZipFile(io.BytesIO(file_data), 'r') as zip_data:
                # Create XML registry for each file...
                for _files in zip_data.filelist:
                    if _files.filename.endswith(".xml"):
                        _b64file = base64.b64encode(zip_data.read(_files.filename))
                        self.env['sat.xml.invoices'].with_context(skip_oc_creation=True).create({
                            'name': filename,
                            'rfc_emisor': 'EMISOR',
                            'rfc_receptor': 'RECEPTOR',
                            'xml_file': _b64file,
                            'xml_file_name': _files.filename,
                            'document_type': document_type,  # NUEVO
                        })
        
        if filename.endswith(".xml"):
            # Create XML registry...
            self.env['sat.xml.invoices'].with_context(skip_oc_creation=True).create({
                'name': filename,
                'rfc_emisor': 'EMISOR',
                'rfc_receptor': 'RECEPTOR',
                'xml_file': values.get('file'),
                'xml_file_name': filename,
                'document_type': document_type,  # NUEVO
            })
        
        return super(SATUploads, self).create(values)


    def action_download_xml(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Descarga Masiva de XML',
            'res_model': 'sat.uploads.wizard',
            'view_mode': 'form',
            'target': 'new'
        }


class SATUploadsWizard(models.TransientModel):
    _name = 'sat.uploads.wizard'
    _description = 'SAT Upload Wizard'
    
    month = fields.Selection(
        [(str(i), datetime.date(2026, i, 1).strftime('%B')) for i in range(1, 13)],
        string="Mes", help='Mes de factura')
    
    year = fields.Selection(
        [(str(y), str(y)) for y in range(2020, datetime.date.today().year + 1)],
        string="Ejercicio", help="Año de factura")
    
    download_type = fields.Selection([
        ('recibido', 'Solo Recibidos'),
        ('emitido', 'Solo Emitidos'),
        ('both', 'Ambos (Recibidos y Emitidos)'),
    ], string="Tipo de Descarga", default='both', required=True,
       help='Seleccione qué tipo de CFDIs desea descargar')

    def action_download_xml(self, start_date=None, end_date=None, document_type='recibido'):
        """
        Descarga XMLs del SAT
        :param document_type: 'recibido' o 'emitido' o 'both'
        """
        company = self.env.company
        print('Empresa:', company.name)
        rfc = company.rfc
        cer_der = base64.b64decode(company.fiel_cert) if company.fiel_cert else b""
        key_der = base64.b64decode(company.fiel_key) if company.fiel_key else b""
        password = company.fiel_password
        
        if not cer_der or not key_der or not password:
            raise ValueError("Faltan los certificados FIEL en la configuración de la empresa.")
        
        # Fechas del período
        if not start_date or not end_date:
            start_date = datetime.date.today()
            end_date = start_date
        
        print('start_date:', start_date)
        print('end_date:', end_date)
        
        # Convertir los binarios a formato DER
        fiel = Fiel(cer_der, key_der, password)
        auth = Autenticacion(fiel)
        
        # Obtener token de autenticación
        token = auth.obtener_token()
        print(f'TOKEN: {token}')
        
        # Lista para almacenar los tipos de descarga a realizar
        download_types = []
        
        if document_type == 'both':
            download_types = ['recibido', 'emitido']
        else:
            download_types = [document_type]
        
        # Procesar cada tipo de descarga
        for dtype in download_types:
            separator = '=' * 50
            print(f'\n{separator}')
            print(f'Descargando CFDIs {dtype.upper()}')
            print(f'{separator}\n')
            
            # Crear la solicitud según el tipo
            if dtype == 'recibido':
                download_sat = SolicitaDescargaRecibidos(fiel)
                request_sat = download_sat.solicitar_descarga(
                    token,
                    rfc,
                    fecha_inicial=start_date,
                    fecha_final=end_date,
                    rfc_receptor=rfc,
                    tipo_solicitud='CFDI',
                    estado_comprobante='Vigente'
                )
            else:  # emitido
                download_sat = SolicitaDescargaEmitidos(fiel)
                request_sat = download_sat.solicitar_descarga(
                    token,
                    rfc,
                    fecha_inicial=start_date,
                    fecha_final=end_date,
                    rfc_emisor=rfc,
                    tipo_solicitud='CFDI',
                    estado_comprobante='Vigente'
                )
            
            print(f'SOLICITUD {dtype.upper()}: {request_sat}')
            request_id = request_sat.get('id_solicitud')
            cod_estatus = request_sat.get('cod_estatus')
            mensaje = request_sat.get('mensaje')
            
            print(f'ID Solicitud: {request_id}')
            print(f'Código Estatus: {cod_estatus}')
            print(f'Mensaje: {mensaje}')
            
            if not request_id:
                _logger.error(f"Error en solicitud {dtype}: Código {cod_estatus}, Mensaje: {mensaje}")
                continue
            
            # Verificar estado de la solicitud con reintento
            verification = VerificaSolicitudDescarga(fiel)
            interval = 60 * 20  # Esperar 20 min. entre cada intento
            timeout = (60 * 60) * 3  # Máximo 3 horas esperando
            elapsed_time = 0
            
            while True:
                if elapsed_time >= timeout:
                    _logger.warning(f"La solicitud {dtype} no se completó después de 3 horas.")
                    break
                
                time.sleep(interval)
                elapsed_time += interval
                
                token = auth.obtener_token()  # Renovar el token
                verification_res = verification.verificar_descarga(token, rfc, request_id)
                request_state = int(verification_res.get('estado_solicitud', -1))
                
                print(f'Tiempo transcurrido: {elapsed_time // 60} min - Estado de solicitud: {request_state}')
                
                if request_state == 3:  # Terminada
                    break
            
            # Descargar paquetes
            sat_packages = verification_res.get('paquetes', [])
            
            if not sat_packages:
                _logger.warning(f"No se encontraron paquetes para {dtype}.")
                continue
            
            for pakage_sat in sat_packages:
                print(f"Descargando paquete {dtype}: {pakage_sat}")
                
                # Descargar el paquete usando DescargaMasiva
                download_sat = DescargaMasiva(fiel)
                download_package = download_sat.descargar_paquete(token, rfc, pakage_sat)
                
                # Decodificar el paquete base64
                package_b64 = base64.b64decode(download_package['paquete_b64'])
                
                # Generar referencia
                if start_date == end_date - datetime.timedelta(days=1) and end_date == datetime.date.today():
                    package_ref = f'{dtype.upper()}_{start_date}'
                else:
                    package_ref = f'{dtype.upper()}_{start_date}_{end_date}'
                
                # Crear registro de upload con contexto para identificar el tipo
                self.with_context(document_type=dtype).env['sat.uploads'].create({
                    'name': package_ref,
                    'file': base64.b64encode(package_b64),
                    'file_name': f'{pakage_sat}.zip',
                })
            
            print(f" Descarga de {dtype} completada con éxito.\n")
        
        print("Proceso de descarga finalizado.")


    def action_download_xml_monthly(self):
        if not self.month or not self.year:
            raise UserError("Debe seleccionar un mes y un año antes de descargar.")
        
        year = int(self.year)
        month = int(self.month)
        today = datetime.date.today()
        selected_date = datetime.date(year, month, 1)
        
        if selected_date > today.replace(day=1):
            raise UserError("No puedes descargar XML de meses futuros.")
        
        first_day = datetime.date(year, month, 1)
        
        if year == today.year and month == today.month:
            last_day = today
        else:
            last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
        
        print('1st day: ', first_day)
        print('last day: ', last_day)
        
        # Pasar el tipo de descarga
        self.action_download_xml(
            start_date=first_day, 
            end_date=last_day,
            document_type=self.download_type  # NUEVO
        )

    def _cron_action_download_xml(self):
        today_date = datetime.date.today()
        yesterday_date = today_date - datetime.timedelta(days=1)

        companies = self.env['res.company'].search([
            ('rfc', '!=', False),
            ('fiel_cert', '!=', False),
            ('fiel_key', '!=', False),
            ('fiel_password', '!=', False),
        ])

        failed_companies = []
        successful_companies = []

        for company in companies:
            try:
                print(f"Iniciando descarga para: {company.name} ({company.rfc})")
                self.with_company(company).sudo().action_download_xml(
                    start_date=yesterday_date,
                    end_date=today_date
                )
                successful_companies.append(company.name)
            except Exception as e:
                print(f"Error en {company.name} ({company.rfc}): {str(e)}")
                failed_companies.append(company)

        # Intentar de nuevo con las empresas que fallaron
        if failed_companies:
            print("\nReintentando descarga para empresas que fallaron...")
            for company in failed_companies[:]:  # Copia de la lista para modificarla dentro del loop
                try:
                    print(f"Reintentando descarga para: {company.name} ({company.rfc})")
                    self.with_company(company).sudo().action_download_xml(
                        start_date=yesterday_date,
                        end_date=today_date
                    )
                    successful_companies.append(company.name)
                    failed_companies.remove(company)  # Eliminar de la lista si tuvo éxito
                except Exception as e:
                    print(f"Error persistente en {company.name} ({company.rfc}): {str(e)}")

        # Enviar notificaciones
        if successful_companies:
            message = f"Descarga masiva de XML completada con éxito para: {', '.join(successful_companies)}"
        else:
            message = "Ninguna empresa pudo completar la descarga masiva de XML."

        self.env['bus.bus']._sendone(
            'res.partner',  
            'notification', 
            {
                'message': message,
                'title': 'Descarga Masiva de XML',
                'sticky': True 
            }
        )

        print("Proceso de descarga finalizado.")

