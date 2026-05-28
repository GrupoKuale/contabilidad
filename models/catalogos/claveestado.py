# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class claveestado(models.Model):
    _name = 'cfdi.claveestado'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'Nombre'

    Clave_estado = fields.Char(string='Clave estado', required=True)
    Clave_pais = fields.Char(string='Clave pais', required=True)
    Nombre = fields.Char(string='Nombre', required=True)

