# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class usuariosapp(models.Model):
    _name = 'cfdi.usuariosapp'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _description = 'Usuarios de la app'

    name = fields.Char(string="Nombre", required=True)
    user = fields.Char(string="Usuario", required=True)
    password = fields.Char(string="Contraseña", required=True)
    token = fields.Char(string="Token", required=False)
    lastlogin = fields.Datetime(string="Ultimo Login")

    active = fields.Boolean(string="Active", default=True)

    """def tab(self):
        menu = self.env['ir.model.data'].get_object_reference('cfdi', 'cfdi_menu_root')
        return {
            'name': 'New tab',
            'type': 'ir.actions.act_url',
            "url":  "web#id="+str(self.id)+"&model=cfdi.autotransportes&view_type=form&menu_id="+str(menu[1])
        }"""
