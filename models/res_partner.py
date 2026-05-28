import pytz
import requests
from odoo import fields, models, api, _
from datetime import date, timedelta,datetime
from odoo.exceptions import ValidationError, UserError


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    is_default = fields.Boolean(string='Establecer como predeterminada')

    @api.constrains('is_default')
    def _check_default_bank(self):
        for record in self:
            if record.is_default:
                # Verificar que solo haya una cuenta predeterminada por partner
                partner_banks = self.search([
                    ('partner_id', '=', record.partner_id.id),
                    ('is_default', '=', True)
                ])
                if len(partner_banks) > 1:
                    raise ValidationError("Solo puede haber una cuenta bancaria predeterminada por partner.")

class ResPartner(models.Model):
    _inherit = "res.partner"

    #SAT GENERAL
    rfc = fields.Char(string="RFC", )
    tax_regime = fields.Many2one('cfdi.claveregimenfiscal', string='Regimen fiscal')
    Use_CFDI = fields.Many2one('cfdi.claveusocfdi',string='Uso de CFDI')

    rfc_blacklist = fields.Boolean(string='Lista negra SAT')

    # CheckID Fields
    curp = fields.Char(string="CURP", help="Clave Única de Registro de Población")
    checkid_verification_ids = fields.One2many('checkid.verification', 'partner_id', 'Verificaciones CheckID')
    checkid_verification_count = fields.Integer('Total Verificaciones', compute='_compute_checkid_count')

    # Campos derivados de CheckID
    checkid_last_verification = fields.Datetime('Última Verificación', compute='_compute_checkid_last_verification')
    checkid_rfc_valid = fields.Boolean('RFC Válido CheckID', compute='_compute_checkid_status')
    checkid_curp_valid = fields.Boolean('CURP Válido CheckID', compute='_compute_checkid_status')
    checkid_blacklist_status = fields.Boolean('En Lista Negra', compute='_compute_checkid_status')

    @api.depends('checkid_verification_ids')
    def _compute_checkid_count(self):
        for partner in self:
            partner.checkid_verification_count = len(partner.checkid_verification_ids)

    @api.depends('checkid_verification_ids')
    def _compute_checkid_last_verification(self):
        for partner in self:
            if partner.checkid_verification_ids:
                partner.checkid_last_verification = max(partner.checkid_verification_ids.mapped('verification_date'))
            else:
                partner.checkid_last_verification = False

    @api.depends('checkid_verification_ids')
    def _compute_checkid_status(self):
        for partner in self:
            partner.checkid_rfc_valid = False
            partner.checkid_curp_valid = False
            partner.checkid_blacklist_status = False

            if partner.checkid_verification_ids:
                last_verification = partner.checkid_verification_ids.sorted('verification_date', reverse=True)[0]
                partner.checkid_rfc_valid = last_verification.rfc_exitoso and last_verification.rfc_valido
                partner.checkid_curp_valid = last_verification.curp_exitoso
                partner.checkid_blacklist_status = last_verification.estado_69_con_problema

    @api.constrains('rfc')
    def _check_duplicate_rfc(self):
        for rec in self:
            if rec.rfc:
                existing = self.search([
                    ('rfc', '=', rec.rfc),
                    ('id', '!=', rec.id)
                ], limit=1)
                if existing:
                    raise ValidationError(_('El RFC "%s" ya está registrado en otro contacto.') % rec.rfc)

    def action_verify_checkid(self):
        self.ensure_one()
        checkid_config = self.env['checkid.api'].search([('active', '=', True)], limit=1)
        if not checkid_config:
            raise UserError(_('No hay configuración activa de CheckID API'))

        search_term = self.rfc or self.curp
        if not search_term:
            raise UserError(_('El contacto debe tener RFC o CURP para verificar'))
        return {
            'name': _('Verificar con CheckID'),
            'type': 'ir.actions.act_window',
            'res_model': 'checkid.verification.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
                'default_search_term': search_term,
            }
        }

    def action_view_checkid_verifications(self):
        """Ver historial de verificaciones CheckID"""
        self.ensure_one()
        return {
            'name': _('Verificaciones CheckID'),
            'type': 'ir.actions.act_window',
            'res_model': 'checkid.verification',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id}
        }

    # SAT
    sat_tipo_tercero = fields.Many2one('sat.tipo.tercero', string='Tipo de tercero')
    sat_tipo_operacion = fields.Many2one('sat.tipo.operacion', string='Tipo de operacion')
    sat_nombre_extranjero = fields.Char('Nombre del extranjero')
    sat_pais_residencia = fields.Many2one('sat.pais.residencia', string='Pais de residencia')
    sat_invoices = fields.One2many('sat.xml.invoices', 'partner_id', string="Facturas SAT", readonly=True)
    sat_nacionalidad = fields.Char('Nacionalidad', required=False)
    
    invoice_list = fields.One2many('account.move', 'partner_id', string="Invoice Details",
                                   readonly=True, domain=(
                                   [('payment_state', '=', 'not_paid'),
                                    ('move_type', '=', 'out_invoice')]))
    total_due = fields.Monetary(compute='_compute_for_followup', store=False,
                                readonly=True)
    next_reminder_date = fields.Date(compute='_compute_for_followup',
                                     store=False, readonly=True)
    total_overdue = fields.Monetary(compute='_compute_for_followup',
                                    store=False, readonly=True)
    followup_status = fields.Selection(
        [('in_need_of_action', 'In need of action'),
         ('with_overdue_invoices', 'With overdue invoices'),
         ('no_action_needed', 'No action needed')],
        string='Followup status',
        )

    comercial_name = fields.Char(string='Nombre Comercial')

    def _compute_for_followup(self):
        """
        Compute the fields 'total_due', 'total_overdue' ,
        'next_reminder_date' and 'followup_status'
        """
        for record in self:
            total_due = 0
            total_overdue = 0
            today = fields.Date.today()
            for am in record.invoice_list:
                if am.company_id == self.env.company:
                    amount = am.amount_residual
                    total_due += amount

                    is_overdue = today > am.invoice_date_due \
                        if am.invoice_date_due else today > am.date
                    if is_overdue:
                        total_overdue += amount or 0
            min_date = record.get_min_date()
            action = record.action_after()
            if min_date:
                date_reminder = min_date + timedelta(days=action)
                if date_reminder:
                    record.next_reminder_date = date_reminder
            else:
                date_reminder = today
                record.next_reminder_date = date_reminder
            if total_overdue > 0 and date_reminder > today:
                followup_status = "with_overdue_invoices"
            elif total_due > 0 and date_reminder <= today:
                followup_status = "in_need_of_action"
            else:
                followup_status = "no_action_needed"
            record.total_due = total_due
            record.total_overdue = total_overdue
            record.followup_status = followup_status

    def get_min_date(self):
        today = date.today()
        for this in self:
            if this.invoice_list:
                min_list = this.invoice_list.mapped('invoice_date_due')
                while False in min_list:
                    min_list.remove(False)
                return min(min_list)
            else:
                return today

    def get_delay(self):
        delay = """SELECT fl.id, fl.delay
                    FROM followup_line fl
                    JOIN account_followup af ON fl.followup_id = af.id
                    WHERE af.company_id = %s
                    ORDER BY fl.delay;

                    """
        self._cr.execute(delay, [self.env.company.id])
        record = self._cr.dictfetchall()
        return record

    def action_after(self):
        lines = self.env['followup.line'].search([(
            'followup_id.company_id', '=', self.env.company.id)])
        if lines:
            record = self.get_delay()
            for i in record:
                return i['delay']

    @api.model
    def create(self, vals):
        if 'rfc' in vals and vals['rfc']:
            vals['rfc'] = vals['rfc'].upper()
        if vals.get('rfc') and vals.get('rfc') != "XAXX010101000":
            self._validate_rfc_api(vals['rfc'])
        return super().create(vals)

    def write(self, vals):
        if 'rfc' in vals and vals['rfc']:
            vals['rfc'] = vals['rfc'].upper()
        if vals.get('rfc') and vals.get('rfc') != "XAXX010101000":
            self._validate_rfc_api(vals['rfc'])
        return super().write(vals)

    @api.onchange('rfc')
    def _onchange_rfc(self):
        if self.rfc:
            self.rfc = self.rfc.upper()

    def _validate_rfc_api(self, rfc_value):
        url = "https://www.checkid.mx/api/Busqueda"
        headers = {"Content-Type": "application/json"}
        payload = {
            "ApiKey": "v5ul8AoN+AzM7NrP/QtO5drcEyQUghHHYFDHHD/2K6A=",
            "TerminoBusqueda": rfc_value,
            "ObtenerRFC": True,
            "Obtener69o69B": True,
            "ObtenerRegimenFiscal": True
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=25)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            raise ValidationError(_('Error al conectar con el servicio CheckID: %s') % str(e))

        if not data.get('exitoso'):
            raise ValidationError(_('El servicio CheckID respondió con error: %s') % data.get('error', ''))

        resultado = data.get('resultado', {})
        rfc_info = resultado.get('rfc', {})
        blacklist_info = resultado.get('estado69o69B', {})

        # Verifica si está en lista negra
        if blacklist_info.get('conProblema'):
            self.rfc_blacklist = True
            # raise ValidationError(_('El RFC "%s" está listado en el 69/69B del SAT.') % rfc_value)
        if not rfc_info.get('valido', False):
            raise ValidationError(_('El RFC "%s" no es válido, revise que este escrito correctamente e intente de nuevo.') % rfc_value)
        return None

    def check_rfc_blacklist_cron(self):
        url = "https://www.checkid.mx/api/Busqueda"
        headers = {"Content-Type": "application/json"}
        api_key = "v5ul8AoN+AzM7NrP/QtO5drcEyQUghHHYFDHHD/2K6A="

        partners = self.search([('rfc', '!=', False)])
        for partner in partners:
            try:
                payload = {
                    "ApiKey": api_key,
                    "TerminoBusqueda": partner.rfc,
                    "ObtenerRFC": True,
                    "Obtener69o69B": True,
                    "ObtenerRegimenFiscal": False,
                }

                response = requests.post(url, json=payload, headers=headers, timeout=25)
                response.raise_for_status()
                data = response.json()

                if data.get('exitoso') and data.get('resultado'):
                    blacklist_info = data['resultado'].get('estado69o69B', {})
                    in_blacklist = blacklist_info.get('conProblema', False)
                    if partner.rfc_blacklist != in_blacklist:
                        partner.rfc_blacklist = in_blacklist
                        print("RFC %s actualizado. Lista negra: %s", partner.rfc, in_blacklist)
                else:
                    print("No se pudo validar RFC %s. Respuesta inválida: %s", partner.rfc, data)
            except Exception as e:
                print("Error al verificar RFC %s: %s", partner.rfc, str(e))


    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', '|',('rfc', operator, name), ('name', operator, name),('comercial_name',operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)