# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class clavetipopermiso(models.Model):
    _name = 'cfdi.clavetipopermiso'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'Descripcion'

    Clave_Tipopermiso = fields.Char(string='Clave tipo permiso', required=True)
    Descripcion = fields.Char(string='Descripción', required=True)
    Clave_Transporte = fields.Char(string='Clave transporte', required=True)

