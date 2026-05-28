import base64
from io import BytesIO
from odoo import models, fields, _
from odoo.exceptions import UserError
import openpyxl

class TicketExteriorWizard(models.TransientModel):
    _name = 'contabilidad_kuale.ticket_exterior_wizard'
    _description = 'Asistente para carga de Timbrado Externo'

    file = fields.Binary(string='Archivo Excel', required=True)
    filename = fields.Char(string='Nombre del Archivo')
    state = fields.Selection([
        ('upload', 'Carga de Archivo'),
        ('done', 'Resumen')
    ], string='Estado', default='upload')
    summary_html = fields.Html(string='Resumen Odoo', readonly=True)

    def action_process_file(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_("Por favor, seleccione un archivo."))

        try:
            wb = openpyxl.load_workbook(filename=BytesIO(base64.b64decode(self.file)), read_only=True, data_only=True)
        except Exception as e:
            raise UserError(_("Error al leer el archivo. Asegúrese de que es un archivo Excel válido. Detalle: %s" % str(e)))

        sheet = wb.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            raise UserError(_("El archivo está vacío."))

        # Buscar índices
        headers = [str(h).lower().strip() if h else '' for h in rows[0]]
        
        try:
            idx_sucursal = next(i for i, h in enumerate(headers) if 'sucursal' in h)
            idx_ticket = next(i for i, h in enumerate(headers) if 'ticket' in h)
            idx_monto = next(i for i, h in enumerate(headers) if 'monto' in h)
        except StopIteration:
            raise UserError(_("No se encontraron las columnas esperadas: 'sucursal', 'número de ticket' o 'monto' en la primera fila."))

        success_count = 0
        error_list = []

        # Caché de sucursales permitidas
        allowed_companies = self.env.companies | self.env.companies.mapped('child_ids') | self.env.companies.mapped('parent_id')
        allowed_branches_dict = {c.name.strip().lower(): c for c in allowed_companies if c.name}
        all_branches_dict = {c.name.strip().lower(): c for c in self.env['res.company'].sudo().search([]) if c.name}

        # Process rows
        for index, row in enumerate(rows[1:], start=2):
            if not any(row):
                continue
            
            sucursal_val = str(row[idx_sucursal]).strip() if row[idx_sucursal] else ''
            ticket_val = str(row[idx_ticket]).strip() if row[idx_ticket] else ''
            try:
                monto_val = float(row[idx_monto]) if row[idx_monto] is not None else 0.0
            except ValueError:
                monto_val = 0.0

            if not sucursal_val or not ticket_val:
                error_list.append(f"Fila {index}: Datos incompletos (Sucursal o Ticket vacío).")
                continue

            sucursal_clean = sucursal_val.lower()

            if sucursal_clean not in allowed_branches_dict:
                if sucursal_clean in all_branches_dict:
                    error_list.append(f"Fila {index}: La sucursal '{sucursal_val}' existe, pero no está dentro de la(s) empresa(s) seleccionada(s) actualmente.")
                else:
                    error_list.append(f"Fila {index}: La sucursal '{sucursal_val}' no existe en Odoo. Asegúrate de escribirla correctamente.")
                continue

            branch_id = allowed_branches_dict[sucursal_clean].id

            tickets = self.env['contabilidad_kuale.ticket_monitor'].search([
                ('ticket_folio', '=ilike', ticket_val),
                ('branch_id', '=', branch_id)
            ])
            
            if not tickets:
                error_list.append(f"Fila {index} Folio {ticket_val}: No se encontró el ticket en Odoo bajo la sucursal '{sucursal_val}'.")
                continue
            if len(tickets) > 1:
                error_list.append(f"Fila {index} Folio {ticket_val}: Se encontraron múltiples tickets para la sucursal '{sucursal_val}'.")
                continue
            
            ticket = tickets[0]
            if abs(ticket.total - monto_val) > 0.01:
                error_list.append(f"Fila {index} Folio {ticket_val}: El monto del ticket en Odoo ({ticket.total}) no coincide con el archivo ({monto_val}).")
                continue
            
            # Cambiar estado a timbrado_externo y marcar como facturado
            ticket.write({
                'ticket_status': 'timbrado_externo',
                'invoiced': True,
                'invoiced_type': 'externa',
            })
            success_count += 1

        # Generar HTML de resumen
        html = f"<div style='font-family: \"Segoe UI\", Roboto, \"Helvetica Neue\", sans-serif;'>"
        html += f"<h3 style='color: #2c3e50;'>Procesamiento finalizado</h3>"
        html += f"<p style='font-size: 14px;'><b>Tickets actualizados correctamente a <span style='color: #016b80;'>Timbrado Externo</span>:</b> <span style='font-size: 16px; font-weight: bold;'>{success_count}</span></p>"
        if error_list:
            html += f"<h4 style='color: #8a6d3b; margin-top: 20px;'>Desglose de incidentes ({len(error_list)}):</h4>"
            html += "<ul style='color: #d9534f; font-size: 14px; background-color: #fdf2f2; padding: 15px 15px 15px 35px; border-radius: 5px; border-left: 4px solid #d9534f; list-style-type: disc;'>"
            for err in error_list:
                html += f"<li style='margin-bottom: 8px;'>{err}</li>"
            html += "</ul>"
        else:
            html += "<p style='color: #5cb85c; font-weight: bold; font-size: 14px; margin-top: 15px;'>¡Todos los tickets del archivo fueron procesados de manera exitosa sin errores!</p>"
        html += "</div>"

        self.write({
            'state': 'done',
            'summary_html': html
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Resumen de Carga Timbrado Externo',
            'res_model': 'contabilidad_kuale.ticket_exterior_wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
