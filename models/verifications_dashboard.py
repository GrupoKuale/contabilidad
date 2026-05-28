import json
from odoo import models, fields


class VerificationsDashboard(models.Model):
    _name = "verifications.dashboard"
    _description = "Dashboard de Validaciones"

    name = fields.Char()
    module_type = fields.Selection([
        ('product', 'Productos'),
        ('discount', 'Descuentos'),
        ('employee', 'Empleados'),
        ('payment_form', 'Formas de pago'),
        ('payment_method', 'Métodos de pago'),
        ('sell_type', 'Tipos de venta'),
    ], required=True)

    kanban_dashboard = fields.Text(compute="_compute_kanban_dashboard")

    def _compute_kanban_dashboard(self):
        for rec in self:
            stats = {}

            if rec.module_type == "product":
                Model = self.env["product.template"]
                stats["title"] = "Productos"
                stats["total"] = Model.search_count([("sale_ok", "=", True)])
                stats["missing"] = Model.search_count(["&", "&", ("type", "in", ["consu", "product"]), ("third_party_id", "=", False), ("sale_ok", "=", True)])
                stats["valid"] = stats["total"] - stats["missing"]

            if rec.module_type == "discount":
                Model = self.env["contabilidad_kuale.ticket_discount"]
                stats["title"] = "Descuentos"
                stats["total"] = Model.search_count([])
                stats["missing"] = Model.search_count([("clave", "=", False)])
                stats["valid"] = stats["total"] - stats["missing"]

            if rec.module_type == "employee":
                Model = self.env["hr.employee"]
                stats["title"] = "Empleados"
                stats["total"] = Model.search_count([])
                stats["missing"] = Model.search_count([("cashier_code", "=", False)])
                stats["valid"] = stats["total"] - stats["missing"]

            if rec.module_type == "payment_form":
                Model = self.env["cfdi.claveformadepago"]
                stats["title"] = "Formas de pago"
                stats["total"] = Model.search_count([])
                stats["missing"] = Model.search_count([("third_party_id", "=", False)])
                stats["valid"] = stats["total"] - stats["missing"]

            if rec.module_type == "payment_method":
                Model = self.env["cfdi.clavemetododepago"]
                stats["title"] = "Métodos de pago"
                stats["total"] = Model.search_count([])
                stats["missing"] = Model.search_count([("Clave_metodo_de_pago", "=", False)])
                stats["valid"] = stats["total"] - stats["missing"]

            if rec.module_type == "sell_type":
                Model = self.env["contabilidad_kuale.ticket_sell_types"]
                stats["title"] = "Tipos de venta"
                stats["total"] = Model.search_count([])
                stats["missing"] = Model.search_count([("clave", "=", False)])
                stats["valid"] = stats["total"] - stats["missing"]

            rec.kanban_dashboard = json.dumps(stats)


    def open_records(self):
        self.ensure_one()
        model = self._get_model()

        return {
            "type": "ir.actions.act_window",
            "display_name": self.name,
            "res_model": model,
            "view_mode": "tree,form",
            "domain": [],
        }

    def open_missing(self):
        self.ensure_one()
        model, domain = self._get_missing_domain()
        return {
            "type": "ir.actions.act_window",
            "display_name": f"{self.name} sin clave",
            "res_model": model,
            "view_mode": "tree,form",
            "domain": domain,
        }

    def open_valid(self):
        self.ensure_one()
        model, domain = self._get_valid_domain()
        return {
            "type": "ir.actions.act_window",
            "display_name": f"{self.name} con clave",
            "res_model": model,
            "view_mode": "tree,form",
            "domain": domain,
        }

    def _get_model(self):
        models = {
            "product": "product.template",
            "discount": "contabilidad_kuale.ticket_discount",
            "employee": "hr.employee",
            "payment_form": "cfdi.claveformadepago",
            "payment_method": "cfdi.clavemetododepago",
            "sell_type": "contabilidad_kuale.ticket_sell_types",
        }
        return models[self.module_type]

    def _get_missing_domain(self):
        missing = {
            "product": [("third_party_id", "=", False)],
            "discount": [("clave", "=", False)],
            "employee": [("cashier_code", "=", False)],
            "payment_form": [("third_party_id", "=", False)],
            "payment_method": [("Clave_metodo_de_pago", "=", False)],
            "sell_type": [("clave", "=", False)],
        }
        return self._get_model(), missing[self.module_type]

    def _get_valid_domain(self):
        valid = {
            "product": [("third_party_id", "!=", False)],
            "discount": [("clave", "!=", False)],
            "employee": [("cashier_code", "!=", False)],
            "payment_form": [("third_party_id", "!=", False)],
            "payment_method": [("Clave_metodo_de_pago", "!=", False)],
            "sell_type": [("clave", "!=", False)],
        }
        return self._get_model(), valid[self.module_type]
