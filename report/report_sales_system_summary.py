import base64
import locale
import os

from odoo import models

class SalesSystemSummaryReport(models.AbstractModel):
    _name = 'report.contabilidad_kuale.sales_system_summary_pdf_template'
    _description = 'Reporte PDF Resumen de Ventas'

    def _get_report_values(self, docids, data=None):
        wizard = self.env['sales.system.summary.report.wizard'].browse(docids)
        domain = []
        logo_paths = {
            1: "C:/Program Files/Odoo 17/server/custom_addons/contabilidad_kuale/static/src/img/DQ.png",
            2: "C:/Program Files/Odoo 17/server/custom_addons/contabilidad_kuale/static/src/img/Tinto.png",
            4: "C:/Program Files/Odoo 17/server/custom_addons/contabilidad_kuale/static/src/img/CJR.png",
        }
        dias_semana = {
            0: 'Lunes',
            1: 'Martes',
            2: 'Miércoles',
            3: 'Jueves',
            4: 'Viernes',
            5: 'Sábado',
            6: 'Domingo',
        }

        # Obtener el logo basado en el company_id
        logo_path = logo_paths.get(wizard.company_id.id)
        logo_base64 = ""

        # Comprobar si la ruta del logo es válida
        if logo_path and os.path.exists(logo_path):
            with open(logo_path, "rb") as image_file:
                logo_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        else:
            print(f"Error: No se encontró la imagen en la ruta: {logo_path}")

        if wizard.company_id:
            domain.append(('company_id', '=', wizard.company_id.id))
        if wizard.branch_id:
            domain.append(('branch_id', '=', wizard.branch_id.id))
        if wizard.date_from:
            domain.append(('create_date', '>=', wizard.date_from))
        if wizard.date_to:
            domain.append(('create_date', '<=', wizard.date_to))

        records = self.env['contabilidad_kuale.sales_system_summary'].search(domain)
        print('records: ', records)

        custom_record = []
        for record in records:
            day_name = dias_semana.get(record.date.weekday()) if record.date else ''

            item = {
                'date_day': day_name,
                'date': record.date.strftime('%d/%m/%Y') if record.date else '',
                'gross_sale': record.gross_sale,
                'net_sale': record.net_sale,
                'tax_iva': record.tax_iva,
                'iva_percent': round(record.iva_percent, 2),


            }
            custom_record.append(item)


        return {
            'doc_ids': docids,
            'doc_model': 'sales.system.summary.report.wizard',
            'docs': wizard,
            'records': custom_record,
            'logo': logo_base64,
        }
