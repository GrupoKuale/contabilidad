from odoo import http
from odoo.http import request
from datetime import datetime
from pytz import timezone, utc

class SaleSummaryCreationError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def _to_utc(datetime_str, tz_name='America/Mexico_City'):
    if not datetime_str:
        return False
    local = timezone(tz_name)
    try:
        dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            dt = datetime.fromisoformat(datetime_str)
        except ValueError:
            raise SaleSummaryCreationError(400, f"Formato de fecha inválido: {datetime_str}")
    local_dt = local.localize(dt, is_dst=None)
    utc_dt = local_dt.astimezone(utc)
    return utc_dt.replace(tzinfo=None)


def _get_company(company_id):
    return request.env['res.company'].sudo().search([
        ('company_clave', '=', company_id)
    ], limit=1)

def _create_summary(data):
    company = _get_company(data.get('company_id'))
    branch = _get_company(data.get('branch_id'))
    date = data.get('Fecha')

    if not company:
        raise SaleSummaryCreationError(400,
                                       f"No se encontró ninguna empresa vinculada con la clave = {data.get('company_id')}")
    if not branch:
        raise SaleSummaryCreationError(400,
                                       f"No se encontró ninguna sucursal vinculada con la clave = {data.get('branch_id')}")
    summary_vals = {
        'company_id': company.id,
        'branch_id': branch.id,
        'date': date,
        'gross_sale': data.get('Venta Bruta'),
        'net_sale': data.get('Venta Neta'),
        'tax_iva': data.get('TAX IVA'),
        # not yet in json
        'discount': data.get('Descuento'),
        'merma_cash': data.get('Merma $'),
        'merma_percentage': data.get('Merma %'),
        # 'weather_avg': data.get('weather_avg', 0),
    }

    summary = request.env['contabilidad_kuale.sales_system_summary'].sudo().create(summary_vals)

    return summary
 # Crear desglose (itemization)
def _associate_itemize(data, summary):
    try:
        for item in data.get('Desglose', []):
            request.env['contabilidad_kuale.sales_system_summary_itemization'].sudo().create({
                'quantity': item.get('sQUAN', 0),
                'amount': item.get('importe', 0),
                'iva_amount': item.get('importeIVA', 0),
                'description': item.get('DESCRIPT', ''),
                'summary_id': summary.id,
            })
    except Exception:
        raise SaleSummaryCreationError(400, 'Error durante lectura de datos de desglose')

def _associate_itemize_fp(data, summary):
    try:
        for item in data.get('DesgloseFP', []):
            request.env['contabilidad_kuale.sales_system_summary_itemization_fp'].sudo().create({
                'quantity': item.get('quan', 0),
                'amount': item.get('importe', 0),
                'description': item.get('DESCRIPT', ''),
                'summary_id': summary.id,
            })
    except Exception:
        raise SaleSummaryCreationError(400, 'Error durante lectura de datos de desgloseFP')

def _associate_itemize_cancel(data, summary):
    try:
        for item in data.get('DesgloseCancel', []):
            request.env['contabilidad_kuale.sales_system_summary_itemization_cancel'].sudo().create({
                'quantity': item.get('quan', 0),
                'amount': item.get('importe', 0),
                'description': item.get('DESCRIPT', ''),
                'summary_id': summary.id,
            })
    except Exception:
        raise SaleSummaryCreationError(400, 'Error durante lectura de datos de desglose de cancelaciones')

def _associate_itemize_group(data, summary):
    try:
        for item in data.get('DesgloseGrupos', []):
            request.env['contabilidad_kuale.sales_system_summary_itemization_groups'].sudo().create({
                'quantity': item.get('sQUAN', 0),
                'amount': item.get('importe', 0),
                'description': item.get('DESCRIPT', ''),
                'summary_id': summary.id,
            })
    except Exception:
        raise SaleSummaryCreationError(400, 'Error durante lectura de datos de desglose de grupos')

def _associate_itemize_uses(data, summary):
    try:
        for item in data.get('DesgloseUsos', []):
            raw_date = item.get('fecha')
            parsed_date = _to_utc(raw_date) if raw_date else None
            request.env['contabilidad_kuale.sales_system_summary_itemization_uses'].sudo().create({
                'date': parsed_date,
                'clave': item.get('clave', ''),
                'name': item.get('nombre', ''),
                'quantity': item.get('cantidad', 0),
                'price_a': item.get('PRICEA', 0),
                'price_b': item.get('PRICEB', 0),
                'price_c': item.get('PRICEC', 0),
                'amount': item.get('Importe', 0),
                'summary_id': summary.id,
            })
    except Exception:
        raise SaleSummaryCreationError(400, 'Error durante lectura de datos de desglose de usos')

def _associate_itemize_vxh(data, summary):
    try:
        for item in data.get('DesgloseVxH', []):
            item_vxh = request.env['contabilidad_kuale.sales_system_summary_itemization_s_by_h'].sudo().create({
                'time_range': item.get('RangoHorario', ''),
                'tickets_number': item.get('NumeroTickets', 0),
                'gross_sale': item.get('VentaBruta', 0),
                'net_sale': item.get('VentaNeta', 0),
                'summary_id': summary.id,
            })

            for prod in item.get('Productos', []):
                third_party_id = prod.get('IdTerceros', 0)
                qty = prod.get('Cantidad', 0)

                product = request.env['product.product'].sudo().search([
                    ('product_tmpl_id.third_party_id', '=', third_party_id)
                ], limit=1)

                if not product:
                    raise SaleSummaryCreationError(400,
                                                   f"Producto con código de terceros ='{third_party_id}' no encontrado.")

                request.env['contabilidad_kuale.sales_summary_product_items_sbyh'].sudo().create({
                    'product_id': product.id,
                    'qty': qty,
                    'itemization_id': item_vxh.id,
                })



    except Exception:
        raise SaleSummaryCreationError(400, 'Error durante lectura de datos de desglose vxh')

def _associate_itemize_sell_type(data,summary):
    try:
        for item in data.get('DesgloseTipoVenta', []):
            sell_type = request.env['contabilidad_kuale.ticket_sell_types'].sudo().search([
                ('clave','=',item.get('TipoVenta'))
            ])
            request.env['contabilidad_kuale.sales_system_summary_sells_types'].sudo().create({
                'sell_type': sell_type.id,
                'ticket_amount':item.get('NumTickets'),
                'gross_sale':item.get('VentaBruta'),
                'net_sale':item.get('VentaNeta'),
                'summary_id': summary.id,
            })
    except Exception:
        raise SaleSummaryCreationError(400 , 'Error durante lectura de datos de tipo de venta')



class SaleSystemSummaryController(http.Controller):

    @http.route('/api/upload/sale/summary', type='http', auth='none', methods=['POST'], csrf=False)
    def upload_summary_file(self, **kwargs):
        summary = None
        try:
            data = request.httprequest.json
            summary = _create_summary(data)
            _associate_itemize(data,summary)
            _associate_itemize_fp(data,summary)
            _associate_itemize_cancel(data,summary)
            _associate_itemize_group(data,summary)
            _associate_itemize_uses(data,summary)
            _associate_itemize_vxh(data,summary)
            _associate_itemize_sell_type(data,summary)
            return request.make_json_response({
                'status': '201',
                'data':  [],
                'message': 'Resumen de ventas diario subido con exito',
            }, status=201)
        except SaleSummaryCreationError as e:
            if summary:
                summary.sudo().unlink()
            return request.make_json_response({
                'status': e.status,
                'message': e.message,
            }, status=e.status)
        except Exception as e:
            if summary:
                summary.sudo().unlink()
            return request.make_json_response({
                'status': 500,
                'message': str(e),
            })






