import sys
import os

odoo_path = r"c:\Odoo17\odoo17"
sys.path.append(odoo_path)
import odoo

if __name__ == "__main__":
    odoo.tools.config.parse_config(['-c', r'c:\Odoo17\odoo17\odoo.conf', '-d', 'odoo'])
    registry = odoo.registry('odoo')
    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        tickets = env['contabilidad_kuale.ticket_monitor'].search([])
        for t in tickets[:5]:
            print(f"Folio: {t.ticket_folio}")
            print(f"Company name: {t.company_id.name}")
            print(f"Branch ID name: {t.branch_id.name if t.branch_id else 'None'}")
            print(f"Business Name: {t.business_name}")
            print("---")
