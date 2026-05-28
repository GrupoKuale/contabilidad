import pandas as pd
from meteostat import Point, daily as Daily

from odoo import api, fields, models, _
from io import BytesIO
import base64
import xlsxwriter
from datetime import datetime

from odoo.exceptions import UserError


class SalesSystemSummary(models.Model):
    _name = 'contabilidad_kuale.sales_system_summary'
    _description = 'Sales System Summary review'

    company_id = fields.Many2one('res.company', string='Empresa',
                                 domain="[('is_branch', '=', False)]")
    branch_id = fields.Many2one('res.company', string='Sucursal',
                                domain="['|', ('parent_id', '=', company_id), ('id', '=', company_id)]")

    date = fields.Date(string='Fecha')
    gross_sale = fields.Float(string='Venta Bruta', required=True)
    net_sale = fields.Float(string='Venta Neta', required=True)
    tax_iva = fields.Float(string='Venta IVA', required=True)
    discount = fields.Float(string='Descuento', required=True, default=0)
    sale_status = fields.Selection([
        ('concil', 'Conciliado'),
        ('no_concil', 'No Conciliado'),
    ], string='Estatus de Venta', required=True, default='no_concil')
    iva_percent = fields.Float(string='IVA / Venta Neta (%)', compute='_compute_iva_percent', store=False)

    merma_cash = fields.Float(string='Merma $', required=True)
    merma_percentage = fields.Float(string='Merma %', required=True)
    # day details
    weather_avg = fields.Float(string='Temperatura promedio del dia')
    weather_details = fields.Text(string='Detalles de la temperatura')
    incidents_type = fields.Selection([
        ('none', 'Ninguno'),
        ('electricity', 'Fallo electrico'),
        ('system', 'Fallo en el sistema'),
        ('personal', 'Falta de personal'),
        ('payments', 'Fallo en sistema de pago'),
        ('offers', 'Problema con promociones'),
        ('weather', 'Clima'),
        ('others', 'Otros'),
    ], string='Tipo de Incidente presentado', help='Factor que pudo afectar negativamente las ventas del dia')
    incident_details = fields.Text(string='Detalles de incidentes durante el dia')
    opportunities = fields.Selection([
        ('none', 'Ninguno'),
        ('day_off', 'Dias festivos'),
        ('offers', 'Promociones'),
        ('weather', 'Clima'),
        ('others', 'Otros'),
    ], string='Oportunidades de Venta', help="Factor que pudo afectar positivamente las ventas del dia")
    opportunities_details = fields.Text(string='Detalles de las Oportunidades de Venta')

    def describe_weather(self, df):
        if df.empty:
            raise UserError(
                "No se encontraron o se presentaron errores en los datos meteorológicos, intente nuevamente mas tarde.")
        row = df.iloc[0]
        descripcion = []
        tavg = row['tavg'] if not pd.isna(row.get('tavg')) else 0.0
        if not pd.isna(row.get('tavg')):
            descripcion.append(f"La temperatura promedio fue de {row['tavg']}°C.")
        if not pd.isna(row.get('tmin')) and not pd.isna(row.get('tmax')):
            descripcion.append(f"La temperatura mínima fue de {row['tmin']}°C y la máxima de {row['tmax']}°C.")
        if not pd.isna(row.get('prcp')) and row['prcp'] > 0:
            descripcion.append(f"Hubo una precipitación de {row['prcp']} mm.")
        else:
            descripcion.append("No se registraron precipitaciones.")
        if not pd.isna(row.get('wspd')):
            descripcion.append(f"La velocidad promedio del viento fue de {row['wspd']} km/h.")
        if not pd.isna(row.get('pres')):
            descripcion.append(f"La presión atmosférica fue de {row['pres']} hPa.")

        return tavg, " ".join(descripcion)

    @api.onchange('date', 'branch_id')
    def _compute_weather(self):
        for record in self:
            location = self.env['hr.work.location'].search(
                [('address_id', '=', record.branch_id.id)], limit=1)
            if not record.date or not location:
                record.weather_avg = 0.0
                record.weather_details = "Sin datos climáticos por falta de ubicación asociada."
                return
            start_date = datetime.combine(record.date, datetime.min.time())
            end_date = datetime.combine(record.date, datetime.min.time())
            place = Point(location.latitude, location.longitude)
            data = Daily(place, start_date, end_date)
            data = data.fetch()
            record.weather_avg, record.weather_details = self.describe_weather(data)

    sales_system_summary_itemization_ids = fields.One2many('contabilidad_kuale.sales_system_summary_itemization',
                                                           'summary_id', string='Desglose')
    sales_system_summary_itemization_fp_ids = fields.One2many('contabilidad_kuale.sales_system_summary_itemization_fp',
                                                              'summary_id', string='Desglose FP')
    sales_system_summary_itemization_cancellation_ids = fields.One2many(
        'contabilidad_kuale.sales_system_summary_itemization_cancel', 'summary_id', string='Desglose Cancelaciones')
    sales_system_summary_itemization_groups_ids = fields.One2many(
        'contabilidad_kuale.sales_system_summary_itemization_groups', 'summary_id', string='Desglose Grupos')
    sales_system_summary_itemization_uses_ids = fields.One2many(
        'contabilidad_kuale.sales_system_summary_itemization_uses', 'summary_id', string='Desglose Usos')
    sales_system_summary_itemization_sbh_ids = fields.One2many(
        'contabilidad_kuale.sales_system_summary_itemization_s_by_h', 'summary_id', string='Desglose Venta por Hora')
    water_measurement = fields.One2many('contabilidad_kuale.sales_system_summary_water', 'summary_id',
                                        string='Lectura agua')
    additional_files = fields.One2many('contabilidad_kuale.additional_file', 'sale_system_summary_id',
                                       string='Archivos digitales')
    sales_system_summary_sell_types_ids = fields.One2many('contabilidad_kuale.sales_system_summary_sells_types',
                                                          'summary_id', string='Desglose Tipo de Venta')

    @api.depends('tax_iva', 'net_sale')
    def _compute_iva_percent(self):
        for rec in self:
            rec.iva_percent = (rec.tax_iva / rec.net_sale * 100) if rec.net_sale else 0.0

    def action_concil(self):
        print('concil action')
        tolerance = 0.01
        start_datetime = datetime.combine(self.date, datetime.min.time())
        end_datetime = datetime.combine(self.date, datetime.max.time())
        tickets = self.env['contabilidad_kuale.ticket_monitor'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('branch_id', '=', self.branch_id.id),
            ('date', '>=', start_datetime),
            ('date', '<=', end_datetime),
        ])

        if not tickets:
            print('no tickets')
            self._notify_error_concil()
            return

        total_tickets = sum(tickets.mapped('total'))
        subtotal_tickets = sum(tickets.mapped('subtotal'))
        iva_tickets = sum(tickets.mapped('iva'))
        discount_tickets = sum(tickets.mapped('discount'))
        print('total:', total_tickets)
        print('subtotal:', subtotal_tickets)
        print('iva:', iva_tickets)
        print('discount:', discount_tickets)
        # Comparar con valores en el resumen
        if (
                abs(total_tickets - self.gross_sale) > tolerance or
                abs(subtotal_tickets - self.net_sale) > tolerance or
                abs(iva_tickets - self.tax_iva) > tolerance or
                abs(discount_tickets - self.discount) > tolerance):
            self._notify_error_concil()
            print('concil action failed')
            return


        else:
            print('concil action succeeded')
            self.write({
                'sale_status': 'concil'
            })

    def _notify_error_concil(self):
        body_msg = (
            f"<b>Conciliación fallida</b><br/>"
            f"Fecha: {self.date or 'Sin fecha'}<br/>"
            f"Sucursal: {self.branch_id.name or 'Sin sucursal'}<br/>"
            f"Empresa: {self.company_id.name or 'Sin empresa'}"
        )

        # Obtener partner de OdooBot
        odoodbot_partner = self.env['res.partner'].search([('name', '=', 'OdooBot')], limit=1)

        # Buscar usuarios administradores relacionados a la empresa o sucursal
        admin_users = self.env['res.users'].search([
            '|',
            ('company_id', '=', self.company_id.id),
            ('company_ids', 'in', [self.branch_id.id]),
            ('groups_id', 'in', self.env.ref('base.group_system').id),
        ])

        if not admin_users:
            return  # O podrías loggear o notificar que no se encontraron admins

        # Crear el mensaje como OdooBot
        message = self.env['mail.message'].create({
            'model': 'res.users',
            'res_id': self.env.user.id,  # no afecta realmente aquí
            'message_type': 'notification',
            'subtype_id': self.env.ref('mail.mt_note').id,
            'body': body_msg,
            'subject': "Conciliación no completada",
            'author_id': odoodbot_partner.id,
        })

        # Crear una notificación para cada administrador
        notifications = []
        for user in admin_users:
            if user.partner_id:
                notifications.append({
                    'mail_message_id': message.id,
                    'res_partner_id': user.partner_id.id,
                    'notification_type': 'inbox',
                    'notification_status': 'sent',
                })

        if notifications:
            self.env['mail.notification'].create(notifications)

    @api.model
    def cron_conciliate_all_companies(self):
        today = datetime.today()
        companies = self.env['res.company'].search([])
        for company in companies:
            branches = self.env['res.company'].search([
                '|',
                ('id', '=', company.id),
                ('parent_id', '=', company.id),
            ])
            for branch in branches:
                summary = self.env['contabilidad_kuale.sales_system_summary'].search([
                    ('company_id', '=', company.id),
                    ('branch_id', '=', branch.id),
                    ('date', '=', today)
                ], limit=1)

                if not summary:
                    self._notify_error_concil()
                try:
                    summary.action_concil()
                except Exception as e:
                    self._notify_error_concil()
                    continue

    def get_account(self, company_id, account_code):
        account = self.env['account.account'].search([
            ('company_id', '=', company_id),
            ('code', '=', account_code),
        ])
        if not account:
            raise UserError(f'La cuenta {account_code} no existe en el sistema')
        return account


    def create_sell_account_move(self):
        self.ensure_one()

        Journal = self.env['account.journal']
        Move = self.env['account.move']
        Partner = self.env['res.partner']
        PaymentType = self.env['payment.account.types']

        partner = Partner.sudo().search([('name', '=', 'Venta al Público')], limit=1)

        journal = Journal.search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'general')
        ], limit=1)
        if not journal:
            raise UserError('No hay un diario configurado para esta compañía.')

        branch_id = self.branch_id.id

        # 🔹 Obtener catálogo de tipos de cuenta activos
        account_types = {rec.account_concept.strip().upper(): rec for rec in
                         PaymentType.search([('active', '=', True)])}

        # 🔹 Desglose de pagos
        detail_totals = {}

        for p in self.sales_system_summary_itemization_fp_ids:
            key = (p.description or '').strip().upper()
            detail_totals[key] = detail_totals.get(key, 0.0) + p.amount

        gross = self.gross_sale or 0.0
        net = self.net_sale or 0.0
        iva = self.tax_iva or 0.0
        disc = self.discount or 0.0

        lines = []

        # 🔹 Generar líneas dinámicas con base en catálogo
        for concept, amount in detail_totals.items():
            if not amount:
                continue
            acc_type = account_types.get(concept)
            if not acc_type:
                continue
                # raise UserError(_(f"No se encontró una cuenta configurada para el concepto '{concept}'."))

            account_id = self.get_account(branch_id, acc_type.account)
            lines.append((0, 0, {
                'name': acc_type.description or concept,
                'account_id': account_id.id,
                'debit': amount,
                'credit': 0.0,
            }))

        # 🔹 Ingresos, IVA y descuentos (también dinámicos)
        for fixed_concept, (amount, is_credit) in {
            'VENTA': (net, True),
            'IVA': (iva, True),
            'DESCUENTO': (disc if self.branch_id.rfc == "HMA041124FS9" else 0.0, False)
        }.items():
            if not amount:
                continue
            acc_type = account_types.get(fixed_concept)
            if not acc_type:
                continue
                # raise UserError(_(f"No se encontró una cuenta configurada para '{fixed_concept}'."))

            account_id = self.get_account(branch_id, acc_type.account)
            lines.append((0, 0, {
                'name': acc_type.description or fixed_concept.title(),
                'account_id': account_id.id,
                'debit': 0.0 if is_credit else amount,
                'credit': amount if is_credit else 0.0,
            }))

        # 🔹 Ajuste por redondeo
        EPS = 0.01
        total_debit = round(sum(l[2]['debit'] for l in lines), 2)
        total_credit = round(sum(l[2]['credit'] for l in lines), 2)
        diff = round(total_debit - total_credit, 2)

        if abs(diff) >= EPS:
            acc_type = account_types.get('DIFERENCIA')
            if not acc_type:
                raise UserError(_('No se encontró una cuenta configurada para "DIFERENCIA".'))
            diff_cta = self.get_account(branch_id, acc_type.account)
            lines.append((0, 0, {
                'name': acc_type.description or 'Ajuste por redondeo',
                'account_id': diff_cta.id,
                'debit': -diff if diff < 0 else 0.0,
                'credit': diff if diff > 0 else 0.0,
            }))

        # 🔹 Crear póliza
        move_vals = {
            'company_id': self.company_id.id,
            'date': self.date or fields.Date.context_today(self),
            'journal_id': journal.id,
            'ref': f'Póliza de venta {self.branch_id.name or ""} - {self.date or ""}',
            'move_type': 'entry',
            'partner_id': partner.id if partner else False,
            'line_ids': lines,
        }

        move = Move.sudo().create(move_vals)
        # move.action_post()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': move.id,
            'target': 'current',
        }

class SalesSystemSummaryItemization(models.Model):
    _name = 'contabilidad_kuale.sales_system_summary_itemization'
    _description = 'Sales System Summary Itemization'

    quantity = fields.Float(string='Cantidad', required=True)
    amount = fields.Float(string='Importe', required=True)
    iva_amount = fields.Float(string='Importe IVA', required=True)
    description = fields.Char(string='Descripcion', required=True)
    summary_id = fields.Many2one('contabilidad_kuale.sales_system_summary', string="Resumen", required=True,
                                 ondelete='cascade')

class SalesSystemSummaryItemizationFP(models.Model):
    _name = 'contabilidad_kuale.sales_system_summary_itemization_fp'
    _description = 'Sales System Summary Itemization'

    quantity = fields.Float(string='Cantidad', required=True)
    amount = fields.Float(string='Importe', required=True)
    description = fields.Char(string='Descripcion', required=True)
    summary_id = fields.Many2one('contabilidad_kuale.sales_system_summary', string="Resumen", required=True,
                                 ondelete='cascade')

class SalesSystemSummaryItemizationCancellation(models.Model):
    _name = 'contabilidad_kuale.sales_system_summary_itemization_cancel'
    _description = 'Sales System Summary Itemization'

    quantity = fields.Float(string='Cantidad', required=True)
    amount = fields.Float(string='Importe', required=True)
    description = fields.Char(string='Descripcion', required=True)
    summary_id = fields.Many2one('contabilidad_kuale.sales_system_summary', string="Resumen", required=True,
                                 ondelete='cascade')

class SalesSystemSummaryItemizationGroups(models.Model):
    _name = 'contabilidad_kuale.sales_system_summary_itemization_groups'
    _description = 'Sales System Summary Itemization'

    quantity = fields.Float(string='Cantidad', required=True)
    amount = fields.Float(string='Importe', required=True)
    description = fields.Char(string='Descripcion', required=True)
    summary_id = fields.Many2one('contabilidad_kuale.sales_system_summary', string="Resumen", required=True,
                                 ondelete='cascade')

class SalesSystemSummaryItemizationUses(models.Model):
    _name = 'contabilidad_kuale.sales_system_summary_itemization_uses'
    _description = 'Sales System Summary Itemization'

    date = fields.Datetime(string='Fecha', required=True)
    clave = fields.Char(string='Clave', required=True)
    name = fields.Char(string='Nombre', required=True)
    quantity = fields.Float(string='Cantidad', required=True)
    price_a = fields.Float(string='Precio A', required=True)
    price_b = fields.Float(string='Precio B', required=True)
    price_c = fields.Float(string='Precio C', required=True)
    amount = fields.Float(string='Importe', required=True)
    summary_id = fields.Many2one('contabilidad_kuale.sales_system_summary', string="Resumen", required=True,
                                 ondelete='cascade')

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record.update_product_prices()
        return record

    def update_product_prices(self):
        for rec in self:
            if not rec.clave:
                continue

            product = self.env['product.template'].sudo().search([
                ('third_party_id', '=', rec.clave)
            ], limit=1)

            if not product:
                continue
            product.sudo().write({
                'pixl_price_a': rec.price_a,
                'pixl_price_b': rec.price_b,
                'pixl_price_c': rec.price_c,
            })

class SalesSystemSummaryItemizationSbyH(models.Model):
    _name = 'contabilidad_kuale.sales_system_summary_itemization_s_by_h'
    _description = 'Sales System Summary Itemization'

    time_range = fields.Char(string='Rango de horario', required=True)
    tickets_number = fields.Integer(string='Numero de tickets', required=True)
    gross_sale = fields.Float(string='Venta Bruta', required=True)
    net_sale = fields.Float(string='Venta Neta', required=True)
    summary_id = fields.Many2one('contabilidad_kuale.sales_system_summary', string="Resumen", required=True,
                                 ondelete='cascade')
    product_itemization_id = fields.One2many('contabilidad_kuale.sales_summary_product_items_sbyh',
                                             'itemization_id', string='Productos mas vendidos')

class SalesSystemSummaryProductItemizationSbyH(models.Model):
    _name = 'contabilidad_kuale.sales_summary_product_items_sbyh'
    _description = 'Sales System Summary Itemization VxH products'

    product_id = fields.Many2one('product.product', required=True)
    name = fields.Char(string='Nombre', related='product_id.display_name')
    qty = fields.Integer(string='Cantidad')
    itemization_id = fields.Many2one('contabilidad_kuale.sales_system_summary_itemization_s_by_h',
                                     string='Descripcion de productos', )

class SalesSystemSummarySellsTypeItemization(models.Model):
    _name = 'contabilidad_kuale.sales_system_summary_sells_types'
    _description = 'Sales System Summary Itemization by sell type'

    sell_type = fields.Many2one('contabilidad_kuale.ticket_sell_types', string="Tipo de venta", required=True)
    ticket_amount = fields.Integer(string='No de tickets', required=True)
    gross_sale = fields.Float(string='Venta Bruta', required=True)
    net_sale = fields.Float(string='Venta Neta', required=True)
    summary_id = fields.Many2one('contabilidad_kuale.sales_system_summary', string="Resumen", required=True,
                                 ondelete='cascade')

class SalesSystemSummaryTransactions(models.Model):
    _name = 'contabilidad_kuale.sales_system_summary_transactions'
    _description = 'Sales System Summary Transactions'
    front_desk = fields.Integer(string='Mostrador', required=True)
    pick_up = fields.Integer(string='Llevar', required=True)
    drive = fields.Integer(string='Drive', required=True)
    uber = fields.Integer(string='Uber', required=True)
    rappi = fields.Integer(string='Rappi', required=True)
    app_reparto = fields.Integer(string='App Reparto', required=True)
    app_pickup = fields.Integer(string='App Pickup', required=True)
    total = fields.Integer(string='Total', compute='_total', store=True, required=True)

    def _total(self):
        total = self.front_desk + self.pick_up + self.drive + self.uber + self.rappi + self.app_reparto + self.app_pickup

class SalesSystemSummaryPersonal(models.Model):
    _name = 'contabilidad_kuale.sales_system_summary_personal'
    _description = 'Sales System Summary Personal'

    expert = fields.Char(string='Expertos', required=True)
    coord_an = fields.Integer(string='Coord anfitrionas', required=True)
    trainers = fields.Integer(string='Entrenadores', required=True)
    star_trainers_guide = fields.Integer(string='Guias en entrenamiento star', required=True)
    super_trainers_guide = fields.Integer(string='Guias en entrenamiento super star', required=True)
    general_guide = fields.Integer(string='Guia general', required=True)
    quantity_plantilla = fields.Integer(string='Plantilla completa', required=True)
    labor_cash = fields.Float(string='Labor $', required=True)
    labor_percentage = fields.Float(string='Labor %', required=True)
    losses = fields.Integer(string='Bajas', required=True)
    rotation = fields.Float(string='Rotacion %', required=True)

class SalesSystemSummaryWaterMeasure(models.Model):
    _name = 'contabilidad_kuale.sales_system_summary_water'
    _description = 'Sales System Summary Water'

    day_lecture = fields.Date(string='Lectura Dia', required=True)
    day_consumption = fields.Date(string='Consumo Dia', required=True)
    day_name = fields.Char(string='Día', compute='_compute_day_name', store=True)
    lecture = fields.Float(string='Lectura', required=True)
    consumption = fields.Float(string='Consumo m3', required=True)
    price = fields.Float(string='Precio m3', required=True)
    water_cost = fields.Float(string='Costo Agua')
    sewage_cost = fields.Float(string='Costo Drenaje')
    total_cost = fields.Float(string='Costo Total')
    summary_id = fields.Many2one('contabilidad_kuale.sales_system_summary', string="Resumen", required=True,
                                 ondelete='cascade')

    @api.onchange('day_lecture')
    def _compute_day_name(self):
        dias_semana = {
            0: 'LUNES',
            1: 'MARTES',
            2: 'MIÉRCOLES',
            3: 'JUEVES',
            4: 'VIERNES',
            5: 'SÁBADO',
            6: 'DOMINGO',
        }
        for rec in self:
            rec.day_name = dias_semana.get(rec.day_lecture.weekday()) if rec.day_lecture else ''

class SalesSystemSummaryReportWizard(models.TransientModel):
    _name = 'sales.system.summary.report.wizard'
    _description = 'Asistente para reporte de resumen de ventas'

    company_id = fields.Many2one('res.company', string='Empresa')
    branch_id = fields.Many2one('res.company', string='Sucursal',
                                domain="['|', ('parent_id', '=', company_id), ('id', '=', company_id)]")
    date_from = fields.Date(string='Desde')
    date_to = fields.Date(string='Hasta')

    def generate_xlsx_report(self):
        records = self.env['contabilidad_kuale.sales_system_summary'].search([
            ('company_id', '=', self.company_id.id),
            ('branch_id', '=', self.branch_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])

        dias_semana = {
            0: 'LUNES',
            1: 'MARTES',
            2: 'MIÉRCOLES',
            3: 'JUEVES',
            4: 'VIERNES',
            5: 'SÁBADO',
            6: 'DOMINGO',
        }

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet("REPORTE VENTAS")

        # Encabezado
        worksheet.write('B2', 'SUCURSAL:')
        worksheet.write('C2', self.branch_id.name or '')
        worksheet.write('B3', 'MES:')
        worksheet.write('C3', self.date_from.strftime('%B').upper() if self.date_from else '')
        worksheet.write('B4', 'AÑO:')
        worksheet.write('C4', self.date_from.year if self.date_from else '')
        worksheet.write('B5', 'GUÍA GENERAL:')
        worksheet.write('C5', 'CARLA CONTRERAS')  # Puedes reemplazar esto si tienes el dato real

        # Encabezado tabla resumen
        headers = ['DÍA', 'FECHA', 'VENTA BRUTA', 'VENTA NETA', 'IVA', 'IVA / VENTA NETA (%)']
        for col, header in enumerate(headers):
            worksheet.write(6, col, header)  # fila 7 (índice 6)

        row = 7
        for record in records:
            day_name = dias_semana.get(record.date.weekday()) if record.date else ''
            worksheet.write(row, 0, day_name)
            worksheet.write(row, 1, record.date.strftime('%d/%m/%Y') if record.date else '')
            worksheet.write(row, 2, record.gross_sale)
            worksheet.write(row, 3, record.net_sale)
            worksheet.write(row, 4, record.tax_iva)
            iva_percent = (record.tax_iva / record.net_sale * 100) if record.net_sale else 0.0
            worksheet.write(row, 5, round(iva_percent, 2))
            row += 1

        # Función auxiliar para escribir desglose en hoja
        def write_detail_sheet(sheet_name, records, headers, row_data_func):
            ws = workbook.add_worksheet(sheet_name)
            for col, header in enumerate(headers):
                ws.write(0, col, header)
            for i, rec in enumerate(records):
                row_values = row_data_func(rec)
                for j, value in enumerate(row_values):
                    ws.write(i + 1, j, value)

        # Desglose por forma de pago
        fp_recs = self.env['contabilidad_kuale.sales_system_summary_itemization_fp'].search([
            ('summary_id', 'in', records.ids)
        ])
        write_detail_sheet("DESGLOSE FP", fp_recs,
                           ['DESCRIPCIÓN', 'CANTIDAD', 'IMPORTE'],
                           lambda r: [r.description, r.quantity, r.amount])

        # Cancelaciones
        cancel_recs = self.env['contabilidad_kuale.sales_system_summary_itemization_cancel'].search([
            ('summary_id', 'in', records.ids)
        ])
        write_detail_sheet("CANCELACIONES", cancel_recs,
                           ['DESCRIPCIÓN', 'CANTIDAD', 'IMPORTE'],
                           lambda r: [r.description, r.quantity, r.amount])

        # Grupos
        group_recs = self.env['contabilidad_kuale.sales_system_summary_itemization_groups'].search([
            ('summary_id', 'in', records.ids)
        ])
        write_detail_sheet("GRUPOS", group_recs,
                           ['DESCRIPCIÓN', 'CANTIDAD', 'IMPORTE'],
                           lambda r: [r.description, r.quantity, r.amount])

        # Usos
        uses_recs = self.env['contabilidad_kuale.sales_system_summary_itemization_uses'].search([
            ('summary_id', 'in', records.ids)
        ])
        write_detail_sheet("USOS", uses_recs,
                           ['FECHA', 'CLAVE', 'CANTIDAD', 'PRECIO', 'IMPORTE'],
                           lambda r: [r.date.strftime('%d/%m/%Y %H:%M:%S'), r.clave, r.quantity, r.price, r.amount])

        # Venta por hora
        sbh_recs = self.env['contabilidad_kuale.sales_system_summary_itemization_s_by_h'].search([
            ('summary_id', 'in', records.ids)
        ])
        write_detail_sheet("VENTA POR HORA", sbh_recs,
                           ['RANGO DE HORARIO', 'NÚMERO DE TICKETS', 'VENTA BRUTA', 'VENTA NETA'],
                           lambda r: [r.time_range, r.tickets_number, r.gross_sale, r.net_sale])

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': 'REPORTE_VENTAS.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    def generate_pdf_report(self):
        return self.env.ref('contabilidad_kuale.action_sales_system_summary_report').report_action(self)
