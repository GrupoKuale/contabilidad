# -*- codigo: utf-8 -*-

import binascii
import logging
import os
import tempfile

import xlrd
import pandas as pd

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class update_prodserv_cp(models.Model):
    _name = 'cfdi.update_prodserv_cp'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    archivo = fields.Binary(string='Upload File')

    @api.model_create_multi
    def create(self, values):
        res = super(update_prodserv_cp, self).create(values)
        return res

    def action_procesar_archivo(self):
        fp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        fp.write(binascii.a2b_base64(self.archivo))  # self.xls_file is your binary field
        fp.seek(0)
        fp.close()
        df = pd.read_excel(fp.name, dtype={'c_ClaveProdServ': str, 'Descripción': str, 'Material Peligroso': str})

        claveprodservcp_model = self.env['cfdi.claveprodservcp']
        for row in df.values:

            existe_el_producto = claveprodservcp_model.sudo().search([('Clave_producto', '=', row[0])], limit=1)
            if existe_el_producto:
                existe_el_producto.write({'Material_peligroso': row[3]})
            else:
                existe_el_producto.create({'Clave_producto': row[0],
                                           'Descripcion': row[1],
                                           'Material_peligroso': row[3]}
                                          )
        fp.close()
        os.remove(fp.name)
