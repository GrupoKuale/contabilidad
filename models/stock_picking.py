# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _update_sales_prices_on_incoming(self):
        """
        Actualiza los precios de venta solo para los productos del picking recibido.
        IMPORTANTE: NO usar _scheduler_update_sales_prices() aquí porque ese método
        itera sobre TODAS las empresas x TODOS los productos y está diseñado para
        ejecutarse como tarea programada (cron), no de forma síncrona en un botón.
        """
        for picking in self:
            if (
                picking.picking_type_id.code == 'incoming' and
                picking.origin and picking.origin.startswith('P') and
                picking.state == 'done'
            ):
                # Obtener solo los productos de este picking
                product_ids = picking.move_ids.mapped('product_id.product_tmpl_id')
                if not product_ids:
                    continue

                _logger.info(
                    '🔄 Actualizando precios para %s producto(s) del picking %s',
                    len(product_ids), picking.name
                )

                company = picking.company_id
                for product in product_ids:
                    # Buscar la última línea de compra para este producto en esta empresa
                    last_purchase_line = self.env['purchase.order.line'].sudo().search([
                        ('product_id.product_tmpl_id', '=', product.id),
                        ('order_id.company_id', '=', company.id),
                        ('order_id.state', 'in', ['purchase', 'done']),
                    ], order='create_date desc', limit=1)

                    if last_purchase_line:
                        product.sudo().with_company(company.id).standard_price = last_purchase_line.price_unit
                        if product.price_increase_percentage:
                            product.sudo().with_company(company.id).list_price = last_purchase_line.price_unit * (
                                1 + product.price_increase_percentage / 100
                            )
                        _logger.info(
                            '   ✔ Producto "%s": costo=%.4f, precio=%.4f',
                            product.name,
                            last_purchase_line.price_unit,
                            product.with_company(company.id).list_price
                        )

    def _check_purchase_order_completion(self):
        """
        Verifica si el picking pertenece a una orden de compra y,
        si todos los pickings están validados, cambia la orden a 'approved'.
        """
        for picking in self:
            # Solo procesar pickings de tipo 'incoming' (recepciones)
            if picking.picking_type_id.code == 'incoming' and picking.purchase_id:
                purchase = picking.purchase_id

                _logger.info(
                    '📦 PICKING VALIDADO: %s | OC: %s | Estado OC: %s | '
                    'Pickings totales: %s | Pickings done: %s',
                    picking.name, purchase.name, purchase.state,
                    len(purchase.picking_ids),
                    len([p for p in purchase.picking_ids if p.state == 'done'])
                )

                # Llamar al método de verificación en la orden de compra
                purchase._check_all_pickings_done()

    def button_validate(self):
        """
        Override del botón de validación para:
        1. Validar el picking (método estándar)
        2. Actualizar precios de venta solo para los productos recibidos
        3. Verificar si la orden de compra debe pasar a 'approved'
        """
        _logger.info("🔘 BUTTON_VALIDATE llamado para picking(s): %s", self.mapped('name'))

        # ========== 1. VALIDAR PICKING (Método Original) ==========
        res = super(StockPicking, self.with_context(
            mail_create_nosubscribe=True
        )).button_validate()

        # ========== 2. ACTUALIZAR PRECIOS DE VENTA (solo productos de este picking) ==========
        # NOTA: Se hace DESPUÉS del super() para que picking.state ya sea 'done'
        self._update_sales_prices_on_incoming()

        # ========== 3. VERIFICAR ESTADO DE ÓRDENES DE COMPRA ==========
        self._check_purchase_order_completion()

        return res
