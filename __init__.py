from . import controllers
from . import models
from . import report
from . import wizard
from odoo.api import Environment
from odoo import api, SUPERUSER_ID

def post_init_create_production_locations(env):

    env['res.company'].create_production_locations()
