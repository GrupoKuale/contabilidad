import json
from odoo import models, fields


class ApprovalDashboard(models.Model):
    _name = "approvals.dashboard"
    _description = "Dashboard de Aprobaciones"

    name = fields.Char()
    module_type = fields.Selection([
        ('purchase', 'Compras'),
        ('sale', 'Ventas'),
        ('expense', 'Gastos'),
        ('payment_supplier', 'Pagos a proveedores'),
        ('payment_customer', 'Pagos de clientes'),
    ], required=True)

    kanban_dashboard = fields.Text(compute="_compute_kanban_dashboard")


    def _compute_kanban_dashboard(self):
        for rec in self:
            stats = {}

            if rec.module_type == "purchase":
                Model = self.env["purchase.order"]
                stats["title"] = "Compras"
                stats["total"] = Model.search_count([])
                stats["pending"] = Model.search_count([("state", "=", "to_approve")])
                stats["approved"] = Model.search_count([("state", "=", "approved")])

            if rec.module_type == "sale":
                Model = self.env["sale.order"]
                stats["title"] = "Ventas"
                stats["total"] = Model.search_count([])
                stats["pending"] = Model.search_count([("state", "=", "to_approve")])
                stats["approved"] = Model.search_count([("state", "=", "approved")])

            if rec.module_type == "expense":
                Model = self.env["hr.expense"]
                stats["title"] = "Gastos"
                stats["total"] = Model.search_count([])
                stats["pending"] = Model.search_count([("state", "=", "submitted")])
                stats["approved"] = Model.search_count([("state", "=", "approved")])

            if rec.module_type == "payment_supplier":
                Model = self.env["account.payment"]
                supplier_domain = [
                    ("partner_type", "=", "supplier"),
                    ("is_internal_transfer", "=", False)
                ]
                stats["title"] = "Pagos a proveedores"
                stats["total"] = Model.search_count(supplier_domain)
                stats["pending"] = Model.search_count(supplier_domain + [("state", "=", "to_approve")])
                stats["approved"] = Model.search_count(supplier_domain + [("state", "=", "approved")])

            if rec.module_type == "payment_customer":
                Model = self.env["account.payment"]
                customer_domain = [
                    ("partner_type", "=", "customer"),
                    ("is_internal_transfer", "=", False)
                ]
                stats["title"] = "Pagos de clientes"
                stats["total"] = Model.search_count(customer_domain)
                stats["pending"] = Model.search_count(customer_domain + [("state", "=", "to_approve")])
                stats["approved"] = Model.search_count(customer_domain + [("state", "=", "approved")])

            rec.kanban_dashboard = json.dumps(stats)


    def open_records(self):
        self.ensure_one()

        if self.module_type == "purchase":
            return {
                "type": "ir.actions.act_window",
                "name": "Órdenes de compra",
                "display_name": "Órdenes de compra",
                "res_model": "purchase.order",
                "view_mode": "tree,form",
                "domain": [],
            }

        if self.module_type == "sale":
            return {
                "type": "ir.actions.act_window",
                "name": "Órdenes de venta",
                "display_name": "Órdenes de venta",
                "res_model": "sale.order",
                "view_mode": "tree,form",
                "domain": [],
            }

        if self.module_type == "expense":
            return {
                "type": "ir.actions.act_window",
                "name": "Gastos",
                "display_name": "Gastos",
                "res_model": "hr.expense",
                "view_mode": "tree,form",
                "domain": [],
            }

        if self.module_type == "payment_supplier":
            return {
                "type": "ir.actions.act_window",
                "name": "Pagos a proveedores",
                "display_name": "Pagos a proveedores",
                "res_model": "account.payment",
                "view_mode": "tree,form",
                "domain": [
                    ("partner_type", "=", "supplier"),
                    ("is_internal_transfer", "=", False)
                ],
            }

        if self.module_type == "payment_customer":
            return {
                "type": "ir.actions.act_window",
                "name": "Pagos de clientes",
                "display_name": "Pago de clientes",
                "res_model": "account.payment",
                "view_mode": "tree,form",
                "domain": [
                    ("partner_type", "=", "customer"),
                    ("is_internal_transfer", "=", False)
                ],
            }


    def open_total(self):
        return self._open_by_state(domain=[])

    def open_pending(self):
        return self._open_by_state(state="pending")

    def open_approved(self):
        return self._open_by_state(state="approved")

    def _open_by_state(self, domain=None, state=None):
        self.ensure_one()
        model = None
        view_name = None

        if self.module_type == "purchase":
            model = "purchase.order"
            view_name = "Órdenes de compra"
            base = []

        if self.module_type == "sale":
            model = "sale.order"
            view_name = "Órdenes de venta"
            base = []

        if self.module_type == "expense":
            model = "hr.expense"
            view_name = "Gastos"
            base = []

        if self.module_type == "payment_supplier":
            model = "account.payment"
            view_name = "Pago a proveedores"
            base = [("partner_type", "=", "supplier"), ("is_internal_transfer", "=", False)]

        if self.module_type == "payment_customer":
            view_name = "Pago de clientes"
            model = "account.payment"
            base = [("partner_type", "=", "customer"), ("is_internal_transfer", "=", False)]

        # filter by approval state
        if state == "pending":
            if self.module_type != "expense":
                base += [("state", "=", "to_approve")]
            else:
                base += [("state", "=", "submitted")]
        elif state == "approved":
            base += [("state", "=", "approved")]

        return {
            "type": "ir.actions.act_window",
            "res_model": model,
            "display_name":view_name,
            "view_mode": "tree,form",
            "domain": base,
        }


    def action_import_purchase_xml(self):
        Purchase = self.env["purchase.order"]
        return Purchase.action_import_invoice_xml()
