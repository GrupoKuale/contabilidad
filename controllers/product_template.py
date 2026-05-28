import json
from odoo import http, SUPERUSER_ID
from odoo.http import request

def _get_company(company_id):
    return request.env['res.company'].sudo().search([
        ('company_clave', '=', company_id)
    ], limit=1)

class ProductTemplateAPI(http.Controller):

    @http.route('/api/upload/pixl/price', auth='none', methods=['POST'], type='http', csrf=False)
    def upload_pixl_price(self, **kw):
        try:
            data = request.httprequest.get_json()
            company = _get_company(data.get('company_id'))
            branch = _get_company(data.get('branch_id'))

            if not company or not branch:
                return request.make_json_response({
                    'status': 404,
                    'message': 'Empresa o sucursal no encontrada',
                })

            products_data = data.get('products', [])
            not_found = []

            for item in products_data:
                code = item.get('third_party_code')
                if not code:
                    continue

                product_variant = request.env['product.product'].sudo().search([
                    ('third_party_id', '=', code)
                ], limit=1)

                if not product_variant:
                    not_found.append(code)
                    continue

                # Escribir en el template
                tmpl = product_variant.product_tmpl_id
                tmpl.sudo().with_company(branch.id).write({
                    'pixl_price_a': float(item.get('price_a', 0)),
                    'pixl_price_b': float(item.get('price_b', 0)),
                    'pixl_price_c': float(item.get('price_c', 0)),
                })

            return request.make_json_response({
                'status': 200,
                'message': 'Carga de precios completada',
                'not_found': not_found,
            })

        except Exception as e:
            return request.make_json_response({
                'status': 500,
                'message': str(e),
            })
