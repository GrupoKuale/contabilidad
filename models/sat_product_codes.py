# -*- coding: utf-8 -*-

from odoo import api, fields, models
from datetime import datetime, timedelta
import base64

class ProductSATCodes(models.Model):
    _name = 'sat.product.codes'
    _description = "SAT Product Codes"

    name = fields.Char('Producto', required=True)
    code = fields.Char('Clave SAT', required=True)
    account_ids = fields.One2many('sat.product.account', 'sat_product_id', string = 'Cuentas')
    
    @api.depends('name', 'code')
    def _compute_display_name(self):
        for template in self:
            template.display_name = '{}{}'.format('%s - ' % template.code, template.name)

class ProductSATCodes(models.Model):
    _name = 'sat.product.account'
    _description = "SAT Product Codes Account"

    sat_product_id = fields.Many2one('sat.product.codes', string='Producto SAT')
    company_id = fields.Many2one('res.company', string='Empresa')
    account_in = fields.Many2one('account.account', string='Cuenta Ingreso')
    account_out = fields.Many2one('account.account', string='Cuenta Egreso')

class TipoTerceroSAT(models.Model):
    _name = 'sat.tipo.tercero'
    _description = "Tipo Tercero SAT"

    name = fields.Char('Descripcion', required=True)
    code = fields.Char('Valor', required=True)



class TipoOperacionSAT(models.Model):
    _name = 'sat.tipo.operacion'
    _description = "Tipo de Operacion SAT"

    name = fields.Char('Descripcion', required=True)
    code = fields.Char('Valor', required=True)
    supplier = fields.Selection([
        ('nacional', 'Nacional'),
        ('extranjero','Extranjero'),
        ('global','Global'),
    ], default='nacional',required=True, string="Tipo proveedor")

class PaisRecidenciaSAT(models.Model):
    _name = 'sat.pais.residencia'
    _description = "Pais de residencia SAT"

    name = fields.Char('Descripcion', required=True)
    code = fields.Char('Valor', required=True)

class DiotCFDIsSAT(models.Model):
    _name = 'sat.diot.cfdis'
    _description = "CFDIs del DIOT SAT"

    diot_id = fields.Many2one('sat.diot', string='DIOT', required=True)
    name = fields.Char('RFC', required=True)
    cfdi_id = fields.Many2one('sat.xml.invoices', string='CFDI', required=True)
    linea = fields.Char('Linea DIOT', required=True)

class DiotSAT(models.Model):
    _name = 'sat.diot'
    _description = "Generacion de DIOT SAT"

    name = fields.Char('Referencia', required=True)
    fecha_inicio = fields.Date('Inicio', required=True)
    fecha_fin = fields.Date('Fin', required=True)
    
    cfdi_ids = fields.One2many('sat.diot.cfdis', 'diot_id', string = 'Lineas')
    
    diot_file_name = fields.Char(string='DIOT')
    diot_file = fields.Binary(string='Download DIOT', readonly=True)
    
    @api.model
    def create(self, values):
        # Se genera el archivo DIOT...
        _cfdis = self.env['sat.xml.invoices'].search(['&',('factura_fecha','>=',values['fecha_inicio']),('factura_fecha','<=',values['fecha_fin'])], order='partner_id')
        _lines = []
        _filename = "diot_" + datetime.now().strftime("%Y%m%d") + ".txt"
        _filecontent = ""
        _lastitem = False
        _calc = 0
        _factura_subtotal = 0
        for cfdi in _cfdis:
            if cfdi.partner_id:
                if _lastitem:
                    if cfdi.partner_id != _lastitem.partner_id:
                        line = _lastitem.partner_id.sat_tipo_tercero.code + "|" + _lastitem.partner_id.sat_tipo_operacion.code + "|" + (_lastitem.partner_id.vat if _lastitem.partner_id.sat_tipo_tercero.code == "04" else "") + "|" + (_lastitem.partner_id.vat if _lastitem.partner_id.sat_tipo_tercero.code == "05" else "") + "|" + (_lastitem.partner_id.sat_nombre_extranjero if _lastitem.partner_id.sat_nombre_extranjero else "") + "|" + (_lastitem.partner_id.sat_pais_residencia.code if _lastitem.partner_id.sat_pais_residencia else "") + "|" + (_lastitem.partner_id.sat_nacionalidad if _lastitem.partner_id.sat_nacionalidad else "") + "|"
                        # Datos impuestos...
                        line += str(round(_factura_subtotal)) + "|" # 08 - Valor de los actos o actividades pagados a la tasa del 15% � 16% de IVA
                        line += "" + "|" # 09 - Valor de los actos o actividades pagados a la tasa del 15% de IVA
                        line += "" + "|" # 10 - Monto del IVA pagado no acreditable a la tasa del 15% � 16%  (correspondiente en la proporci�n de las deducciones autorizadas)
                        line += "" + "|" # 11 - Valor de los actos o actividades pagados a la tasa del 10% u 11% de IVA
                        line += "" + "|" # 12 - Valor de los actos o actividades pagados a la tasa del 10% de IVA
                        line += "" + "|" # 13 - Valor de los actos o actividades pagados sujeto al estimulo de la region fronteriza norte
                        line += "" + "|" # 14 - Monto del IVA pagado no acreditable a la tasa del 10% u 11% (correspondiente en la proporci�n de las deducciones autorizadas)
                        line += "" + "|" # 15 - Monto del IVA pagado no acreditable sujeto al estimulo de la region fronteriza norte (correspondiente en la proporcion de las deducciones autorizadas)
                        line += "" + "|" # 16 - Valor de los actos o actividades pagados en la importaci�n de bienes y servicios  a la tasa del 15% � 16% de  IVA
                        line += "" + "|" # 17 - Monto del IVA pagado no acreditable por la importaci�n  a la tasa del 15% � 16% (correspondiente en la proporci�n de las deducciones autorizadas)
                        line += "" + "|" # 18 - Valor de los actos o actividades pagados en la importaci�n de bienes y servicios a la tasa del 10% u 11% de IVA
                        line += "" + "|" # 19 - Monto del IVA pagado no acreditable por la importaci�n a la tasa del 10% u 11% (correspondiente en la proporci�n de las deducciones autorizadas)
                        line += "" + "|" # 20 - Valor de los actos o actividades pagados en la importaci�n de bienes y servicios por los que no se parag� el IVA (Exentos)
                        line += "" + "|" # 21 - Valor de los dem�s actos o actividades pagados a la tasa del 0% de IVA
                        line += "" + "|" # 22 - Valor de los actos o actividades pagados por los que no se pagar� el IVA (Exentos)
                        line += (str(round(_calc)) if _calc > 0.0 else "") + "|" # 23 - IVA Retenido por el contribuyente
                        line += "" + "|" # 24 - IVA correspondiente a las devoluciones, descuentos y bonificaciones sobre compras
                        _lines.append((0,0,{"name": _lastitem.partner_id.vat, "cfdi_id": _lastitem.id, "linea": line}))
                        _filecontent += line + "\n"
                        _calc = 0
                        _factura_subtotal = 0
                _lastitem = cfdi
                # Subtotal para IVA 16% o 15%...
                _factura_subtotal += _lastitem.factura_subtotal
                # Impuestos retenidos para IVA 16%...
                for _i in _lastitem.concepts_ids.retenciones_ids:
                    if _i.name == "002":
                        _calc += _i.importe
        if _lastitem:
            line = _lastitem.partner_id.sat_tipo_tercero.code + "|" + _lastitem.partner_id.sat_tipo_operacion.code + "|" + (_lastitem.partner_id.vat if _lastitem.partner_id.sat_tipo_tercero.code == "04" else "") + "|" + (_lastitem.partner_id.vat if _lastitem.partner_id.sat_tipo_tercero.code == "05" else "") + "|" + (_lastitem.partner_id.sat_nombre_extranjero if _lastitem.partner_id.sat_nombre_extranjero else "") + "|" + (_lastitem.partner_id.sat_pais_residencia.code if _lastitem.partner_id.sat_pais_residencia else "") + "|" + (_lastitem.partner_id.sat_nacionalidad if _lastitem.partner_id.sat_nacionalidad else "") + "|"
            # Datos impuestos...
            line += str(round(_factura_subtotal)) + "|" # 08 - Valor de los actos o actividades pagados a la tasa del 15% � 16% de IVA
            line += "" + "|" # 09 - Valor de los actos o actividades pagados a la tasa del 15% de IVA
            line += "" + "|" # 10 - Monto del IVA pagado no acreditable a la tasa del 15% � 16%  (correspondiente en la proporci�n de las deducciones autorizadas)
            line += "" + "|" # 11 - Valor de los actos o actividades pagados a la tasa del 10% u 11% de IVA
            line += "" + "|" # 12 - Valor de los actos o actividades pagados a la tasa del 10% de IVA
            line += "" + "|" # 13 - Valor de los actos o actividades pagados sujeto al estimulo de la region fronteriza norte
            line += "" + "|" # 14 - Monto del IVA pagado no acreditable a la tasa del 10% u 11% (correspondiente en la proporci�n de las deducciones autorizadas)
            line += "" + "|" # 15 - Monto del IVA pagado no acreditable sujeto al estimulo de la region fronteriza norte (correspondiente en la proporcion de las deducciones autorizadas)
            line += "" + "|" # 16 - Valor de los actos o actividades pagados en la importaci�n de bienes y servicios  a la tasa del 15% � 16% de  IVA
            line += "" + "|" # 17 - Monto del IVA pagado no acreditable por la importaci�n  a la tasa del 15% � 16% (correspondiente en la proporci�n de las deducciones autorizadas)
            line += "" + "|" # 18 - Valor de los actos o actividades pagados en la importaci�n de bienes y servicios a la tasa del 10% u 11% de IVA
            line += "" + "|" # 19 - Monto del IVA pagado no acreditable por la importaci�n a la tasa del 10% u 11% (correspondiente en la proporci�n de las deducciones autorizadas)
            line += "" + "|" # 20 - Valor de los actos o actividades pagados en la importaci�n de bienes y servicios por los que no se parag� el IVA (Exentos)
            line += "" + "|" # 21 - Valor de los dem�s actos o actividades pagados a la tasa del 0% de IVA
            line += "" + "|" # 22 - Valor de los actos o actividades pagados por los que no se pagar� el IVA (Exentos)
            line += (str(round(_calc)) if _calc > 0.0 else "") + "|" # 23 - IVA Retenido por el contribuyente
            line += "" + "|" # 24 - IVA correspondiente a las devoluciones, descuentos y bonificaciones sobre compras
            _lines.append((0,0,{"name": _lastitem.partner_id.vat, "cfdi_id": _lastitem.id, "linea": line}))
            _filecontent += line + "\n"
            _calc = 0
            _factura_subtotal = 0
        values['cfdi_ids'] = _lines
        values['diot_file_name'] = _filename
        values['diot_file'] = base64.b64encode(bytes(_filecontent, 'utf-8'))
        return super(DiotSAT, self).create(values)
