from datetime import datetime
import paramiko
from io import StringIO
from odoo import models, fields, api
from odoo.exceptions import UserError


class BankTransaction(models.Model):
    _name = 'contabilidad_kuale.bank_transaction'
    _description = 'Bank Transaction'

    company_id = fields.Many2one('res.company', string='Empresa',
                                 domain="[('is_branch', '=', False)]")
    branch_id = fields.Many2one('res.company', string='Sucursal',
                                domain="['|', ('parent_id', '=', company_id), ('id', '=', company_id)]")

    date = fields.Date(string='Fecha')
    file_reference = fields.Char(string='Referencia del archivo')
    transaction_line = fields.One2many('contabilidad_kuale.bank_transaction_line', 'transaction_id', string='Transacciones')


class BankTransactionLine(models.Model):
    _name = 'contabilidad_kuale.bank_transaction_line'
    _description = 'Bank Transaction Line'

    transaction_id = fields.Many2one('contabilidad_kuale.bank_transaction', string='Estado de Cuenta')

    operation_number = fields.Char(string='No. Operación')  # 0
    branch_code = fields.Char(string='Sucursal')            # 1
    reference = fields.Char(string='Referencia')            # 2
    user = fields.Char(string='Usuario')                    # 3
    usr_trx = fields.Char(string='UsrTrx')                  # 4
    payment_type = fields.Char(string='Tipo de Pago')       # 5
    batch = fields.Char(string='Lote')                      # 6
    file_name = fields.Char(string='Nombre del Archivo')    # 7
    card_number = fields.Char(string='Terminación Tarjeta') # 8
    card_holder = fields.Char(string='Nombre del Tarjetahabiente')  # 9
    authorization = fields.Char(string='Autorización')      # 10
    affiliation = fields.Char(string='Afiliación')          # 11
    affiliation_name = fields.Char(string='Nombre Afiliación')  # 12
    amount = fields.Float(string='Importe')                 # 13
    currency = fields.Many2one('cfdi.clavemoneda', string='Moneda')  # 14
    operation_datetime = fields.Datetime(string='Fecha y Hora de Operación')  # 15+16
    card_type = fields.Selection([
        ('d', 'Débito'),
        ('c', 'Crédito'),
    ], string='Tipo de Tarjeta')                            # 17
    card_brand = fields.Selection([
        ('mastercard', 'Mastercard'),
        ('visa', 'Visa'),
        ('amex', 'American Express'),
        ('stp', 'STP'),
        ('discover', 'Discover'),
        ('carnet', 'Carnet'),
    ], string='Marca de Tarjeta')                           # 18
    issuing_bank = fields.Char(string='Banco Emisor')       # 19
    operation_type = fields.Char(string='Tipo de Operación')  # 20
    deposit_date = fields.Date(string='Fecha de Depósito')  # 21
    fee_amount = fields.Float(string='Importe Tasa')        # 22
    fee_tax = fields.Float(string='IVA Tasa')               # 23
    surcharge = fields.Float(string='Importe sobre Tasa')   # 24
    surcharge_tax = fields.Float(string='IVA sobre Tasa')   # 25
    net_amount = fields.Float(string='Importe Neto')        # 26
    net_type = fields.Selection([
        ('abono', 'Abono'),
        ('venta', 'Venta'),
        ('otro', 'Otro'),
    ], string='Tipo de Importe Neto')                       # 27
    payment_reference = fields.Char(string='Referencia de Pago')  # 28


class BankTransactionFtpWizard(models.TransientModel):
    _name = 'contabilidad_kuale.bank_transaction_ftp_wizard'
    _description = 'FTP Wizard for Bank Transactions'

    ftp_host = fields.Char(string='FTP Host', required=True)
    ftp_user = fields.Char(string='FTP Usuario', required=True)
    ftp_pass = fields.Char(string='FTP Contraseña', required=True)
    ftp_port = fields.Integer(string='FTP Puerto', default=22)
    ftp_dir = fields.Char(string='FTP Directorio', default='/Outbox')

    def action_download_and_process(self):
        print("🔐 Conectando a SFTP...")
        try:
            transport = paramiko.Transport((self.ftp_host, self.ftp_port))
            transport.connect(username=self.ftp_user, password=self.ftp_pass)
            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp.chdir(self.ftp_dir)
            archivos = sftp.listdir_attr()

            if not archivos:
                raise UserError("No se encontraron archivos en el directorio SFTP.")

            # Ordenar por fecha (st_mtime)
            archivo_mas_reciente = sorted(archivos, key=lambda x: x.st_mtime, reverse=True)[0]
            nombre_archivo = archivo_mas_reciente.filename
            print(f"📥 Archivo más reciente: {nombre_archivo}")

            # Descargar archivo como string
            with sftp.open(nombre_archivo, 'r') as remote_file:
                contenido = remote_file.read().decode('utf-8')

            # Procesar contenido
            agrupado_por_sucursal = {}
            for linea in contenido.strip().splitlines():
                campos = linea.strip().split('|')
                if len(campos) < 29:
                    print(f"⚠️ Línea incompleta: {linea}")
                    continue
                no_store = campos[1].strip()
                agrupado_por_sucursal.setdefault(no_store, []).append(campos)

            for no_store, registros in agrupado_por_sucursal.items():
                branch = self.env['res.company'].search([('no_store', '=', no_store)], limit=1)
                print(f"🏢 Sucursal para {no_store}: {branch.name if branch else 'No encontrada'}")
                self.env['contabilidad_kuale.bank_transaction'].create({
                    'date': datetime.today().date(),
                    'file_reference': nombre_archivo,
                    'branch_id': branch.id if branch else None,
                    'company_id': branch.parent_id.id if branch and branch.parent_id else None,
                    'transaction_line': [
                        (0, 0, self._prepare_line_values(line, branch.id if branch else None)) for line in registros
                    ]
                })

            sftp.close()
            transport.close()
            print("✅ SFTP cerrado correctamente.")

        except Exception as e:
            print(f"❌ Error durante la conexión o procesamiento SFTP: {e}")
            raise UserError(f"Error de SFTP: {str(e)}")

    def _prepare_line_values(self, campos, branch_id):
        def parse_float(val):
            return float(val or 0.0)

        def parse_date(val):
            return datetime.strptime(val, "%d/%m/%Y").date() if val else False

        def parse_datetime(date_str, time_str):
            try:
                return datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M:%S")
            except Exception:
                return False

        return {
            'operation_number': campos[0],
            'branch_code': campos[1],
            'reference': campos[2],
            'user': campos[3],
            'usr_trx': campos[4],
            'payment_type': campos[5],
            'batch': campos[6],
            'file_name': campos[7],
            'card_number': campos[8],
            'card_holder': campos[9],
            'authorization': campos[10],
            'affiliation': campos[11],
            'affiliation_name': campos[12],
            'amount': parse_float(campos[13]),
            'currency': self._get_moneda_id(campos[14]),
            'operation_datetime': parse_datetime(campos[15], campos[16]),
            'card_type': campos[17].lower() if campos[17] else '',
            'card_brand': campos[18].lower() if campos[18].lower() in [
                'mastercard', 'visa', 'amex', 'stp', 'discover', 'carnet'
            ] else False,
            'issuing_bank': campos[19],
            'operation_type': campos[20],
            'deposit_date': parse_date(campos[21]),
            'fee_amount': parse_float(campos[22]),
            'fee_tax': parse_float(campos[23]),
            'surcharge': parse_float(campos[24]),
            'surcharge_tax': parse_float(campos[25]),
            'net_amount': parse_float(campos[26]),
            'net_type': campos[27].lower() if campos[27].lower() in ['abono', 'venta', 'otro'] else '',
            'payment_reference': campos[28],
        }

    def _get_moneda_id(self, clave):
        moneda = self.env['cfdi.clavemoneda'].search([('Clave_moneda', '=', clave)], limit=1)
        return moneda.id if moneda else False
