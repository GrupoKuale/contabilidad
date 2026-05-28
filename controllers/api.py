# -*- coding: utf-8 -*-
from itertools import groupby
from odoo import http, fields
from odoo.http import Controller, route, request, content_disposition
import logging
import datetime
import json
import base64
import hashlib
import os
import requests
from random import seed
from random import randint
from hashlib import sha256
from datetime import datetime, timedelta
from tokenize import group
from base64 import *

# from IDD_CMP_1 import IDD_CMP_1_middleware
_logger = logging.getLogger(__name__)


class APIcfdi(http.Controller):
    # Login...
    @http.route('/login', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def login(self, **kw):
        params_user = request.params.get('user')
        params_psw = request.params.get('psw')
        if params_user:
            # Se revisa que no este ya registrado el celular...
            existe = request.env['cfdi.usuariosapp'].sudo().search([('user', '=', params_user), ('password', '=', params_psw)])
            token = ""
            if not existe:
                resp = {"success": False, "status": "NOK", "code": 200, "message": "Error de autenticación", "data": {"token": token}}
            else:
                # Se genera el Token...
                strsha = params_user + "_" + datetime.now().strftime("%m/%d/%Y, %H:%M:%S")
                if not existe.lastlogin:
                    token = sha256(strsha.encode('utf-8')).hexdigest()
                    # Se actualiza el token en el usuario...
                    existe.update({'token': token, 'lastlogin': datetime.now()})
                else:
                    if (existe.lastlogin + timedelta(hours=24)) < datetime.now():
                        token = sha256(strsha.encode('utf-8')).hexdigest()
                        # Se actualiza el token en el usuario...
                        existe.update({'token': token, 'lastlogin': datetime.now()})
                    else:
                        token = existe.token
                        existe.update({'lastlogin': datetime.now()})
                resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": {"token": token}}
        return resp

    # Obtener mercancias...
    @http.route('/mercancias', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def mercancias(self, **kw):
        params_token = request.params.get('token')
        params_idInterno = request.params.get('Id_interno')
        params_nombreUsado = request.params.get('Nombre_usado')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            producto_servicio = []

            if params_idInterno != "":
                objs = request.env['cfdi.mercancias'].sudo().search([('Id_interno', 'ilike', params_idInterno)])
                for obj in objs:
                    producto_servicio.append(
                        {"id": obj.id, "valor": obj.Nombre_usado + "-" + obj.Unidad_medida_conocida})
            elif params_nombreUsado != "":
                objs = request.env['cfdi.mercancias'].sudo().search([('Nombre_usado', 'ilike', params_nombreUsado)])
                for obj in objs:
                    producto_servicio.append(
                        {"id": obj.id, "valor": obj.Nombre_usado + "-" + obj.Unidad_medida_conocida})
            else:
                objs = request.env['cfdi.mercancias'].sudo().search([])
                for obj in objs:
                    producto_servicio.append(
                        {"id": obj.id, "valor": obj.Nombre_usado + "-" + obj.Unidad_medida_conocida})

            resp["data"] = {"claveprodservcp": producto_servicio}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Obtener Transportistas...
    @http.route('/transportistas', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def transportistas(self, **kw):
        params_token = request.params.get('token')
        params_Transportistas = request.params.get('Transportistas')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            rutas = []

            if params_Transportistas != "":
                objs = request.env['cfdi.Transportistas'].sudo().search([('Transportistas', 'ilike', params_Transportistas)])
            else:
                objs = request.env['cfdi.Transportistas'].sudo().search([])

            resp["data"] = {"Transportistas": rutas}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Obtener Rutas...
    @http.route('/rutas', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def rutas(self, **kw):
            params_token = request.params.get('token')
            params_Ruta = request.params.get('Ruta')

            resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
            # Se revisa que el usuario exista...
            existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
            if existe:
                rutas = []

                if params_Ruta != "":
                    objs = request.env['cfdi.rutas'].sudo().search([('Ruta', 'ilike', params_Ruta)])
                    for obj in objs:
                        rutas.append({"id": obj.id, "valor": obj.Ruta + "-" + str(obj.Distancia_recorrida)})
                else:
                    objs = request.env['cfdi.rutas'].sudo().search([])
                    for obj in objs:
                        rutas.append({"id": obj.id, "valor": obj.Ruta + "-" + str(obj.Distancia_recorrida)})

                resp["data"] = {"rutas": rutas}
                resp["success"] = True
                resp["status"] = "OK"
                resp["code"] = 200
                resp["message"] = ""
            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "Error de Token."
            return resp

    # Obtener Operadores...
    @http.route('/operadores', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def operadores(self, **kw):
        params_token = request.params.get('token')
        params_NombreOperador = request.params.get('Nombre_operador')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            operadores = []

            if params_NombreOperador != "":
                objs = request.env['cfdi.operadores'].sudo().search(
                    [('Nombre_operador', 'ilike', params_NombreOperador)])
                for obj in objs:
                    operadores.append({"id": obj.id, "valor": obj.Nombre_operador})
            else:
                objs = request.env['cfdi.operadores'].sudo().search([])
                for obj in objs:
                    operadores.append({"id": obj.id, "valor": obj.Nombre_operador})

            resp["data"] = {"operadores": operadores}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Obtener Autotransportes...
    @http.route('/autotransportes', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def autotrasnportes(self, **kw):
        params_token = request.params.get('token')
        params_NombreAutotransporte = request.params.get('Nombre_autotransporte')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            vehiculos = []

            if params_NombreAutotransporte != "":
                objs = request.env['cfdi.autotransportes'].sudo().search(
                    [('Nombre_autotransporte', 'ilike', params_NombreAutotransporte)])
                for obj in objs:
                    vehiculos.append({"id": obj.id, "valor": obj.Nombre_autotransporte})
            else:
                objs = request.env['cfdi.autotransportes'].sudo().search([])
                for obj in objs:
                    vehiculos.append({"id": obj.id, "valor": obj.Nombre_autotransporte})

            resp["data"] = {"autotransportes": vehiculos}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Obtener Remolques...
    @http.route('/remolques', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def remolques(self, **kw):
        params_token = request.params.get('token')
        params_Nombre_remolque = request.params.get('Nombre_remolque')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            remolques = []

            if params_Nombre_remolque != "":
                objs = request.env['cfdi.remolques'].sudo().search([('Nombre_remolque', 'ilike', params_Nombre_remolque)])
                for obj in objs:
                    remolques.append({"id": obj.id, "valor": obj.Nombre_remolque})
            else:
                objs = request.env['cfdi.remolques'].sudo().search([])
                for obj in objs:
                    remolques.append({"id": obj.id, "valor": obj.Nombre_remolque})

            resp["data"] = {"remolques": remolques}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Crear Viaje (CFDI)
    @http.route('/createcfdi', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def createcfdi(self, **kw):
        params_token = request.params.get('token')

        params_nombre_viaje = request.params.get('nombre_viaje')

        params_mercancia = request.params.get('mercancias')

        params_id_ruta = request.params.get('id_ruta')

        hours = 6
        hours_added = timedelta(hours=hours)

        params_hora_salida = request.params.get('hora_salida')
        hora_salida = datetime.strptime(params_hora_salida, '%Y-%m-%d %H:%M:%S')
        odoo_hora_salida = hora_salida + hours_added

        params_hora_llegada = request.params.get('hora_llegada')
        hora_llegada = datetime.strptime(params_hora_llegada, '%Y-%m-%d %H:%M:%S')
        odoo_hora_llegada = hora_llegada + hours_added

        params_id_autotransporte = request.params.get('id_autotransporte')
        params_id_chofer = request.params.get('id_chofer')

        params_necesita_remolque = request.params.get('necesita_remolque')
        params_id_remolque = request.params.get('id_remolque')

        params_necesita_segundo_remolque = request.params.get('necesita_segundo_remolque')
        params_id_remolque2 = request.params.get('id_remolque2')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:

            if params_id_ruta != "" and params_hora_salida != "" and params_hora_llegada != "" and params_id_autotransporte != "" and params_id_chofer != "" and params_nombre_viaje != "":

                ruta = request.env['cfdi.rutas'].sudo().search([('id', '=', params_id_ruta)])
                # Se guardan los datos en cfdi...
                cfdi = request.env['cfdi.cfdiprueba'].sudo().create({
                    'nombre_viaje': params_nombre_viaje,
                    'ruta': ruta.id,
                    'TotalDistRec': ruta.Distancia_recorrida,
                    'FechaHoraSalida': odoo_hora_salida,
                    'FechaHoraProgLlegada': odoo_hora_llegada,
                    'autotransporte': params_id_autotransporte,
                    'operadores': params_id_chofer
                })

                PesoBrutoTotal = 0
                PesoNetoTotal = 0

                for merca in params_mercancia:
                    concepto = request.env['cfdi.mercancias'].sudo().search([('id', '=', merca['id_mercancia'])])

                    PesoBrutoTotal = PesoBrutoTotal + (concepto.Peso_kilos * int(merca['cantidad_mercancia']))
                    PesoNetoTotal = PesoNetoTotal + (concepto.Peso_kilos * int(merca['cantidad_mercancia']))

                    cfdi.write({'concepto': [(0, 0, {'claveprodserv': concepto.id, 'cantidad_unidad_medida_conocida': merca['cantidad_mercancia']})],
                                'mercancia': [(0, 0, {'claveprodserv': concepto.id, 'cantidad_unidad_medida_conocida': merca['cantidad_mercancia']})]
                                })

                cfdi.write({'NumTotalMercancias': len(params_mercancia), 'PesoBrutoTotal': PesoBrutoTotal,
                            'PesoNetoTotal': PesoNetoTotal})

                if params_necesita_remolque and params_id_remolque != "":
                    cfdi.write({
                        'necesita_remolque': params_necesita_remolque,
                        'remolque': int(params_id_remolque)
                    })
                else:
                    cfdi.write({
                        'necesita_remolque': params_necesita_remolque,
                        'remolque': False
                    })

                if params_necesita_segundo_remolque and params_id_remolque2 != "":
                    cfdi.write({
                        'necesita_segundo_remolque': params_necesita_segundo_remolque,
                        'remolque2': int(params_id_remolque2)
                    })
                else:
                    cfdi.write({
                        'necesita_segundo_remolque': params_necesita_segundo_remolque,
                        'remolque2': False
                    })

            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "Faltan datos."

            resp["data"] = {"cfdi": cfdi}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Editar Viaje (CFDI)
    @http.route('/updatecfdi', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def updatecfdi(self, **kw):
        params_token = request.params.get('token')

        params_folio = request.params.get('folio')

        params_nombre_viaje = request.params.get('nombre_viaje')

        params_mercancia = request.params.get('mercancias')

        params_id_ruta = request.params.get('id_ruta')

        hours = 6
        hours_added = timedelta(hours=hours)

        params_hora_salida = request.params.get('hora_salida')
        hora_salida = datetime.strptime(params_hora_salida, '%Y-%m-%d %H:%M:%S')
        odoo_hora_salida = hora_salida + hours_added

        params_hora_llegada = request.params.get('hora_llegada')
        hora_llegada = datetime.strptime(params_hora_llegada, '%Y-%m-%d %H:%M:%S')
        odoo_hora_llegada = hora_llegada + hours_added

        params_id_autotransporte = request.params.get('id_autotransporte')
        params_id_chofer = request.params.get('id_chofer')

        params_necesita_remolque = request.params.get('necesita_remolque')
        params_id_remolque = request.params.get('id_remolque')

        params_necesita_segundo_remolque = request.params.get('necesita_segundo_remolque')
        params_id_remolque2 = request.params.get('id_remolque2')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:

            if params_folio != "":
                viaje = request.env['cfdi.cfdiprueba'].sudo().search([('id', '=', params_folio)])
                if viaje:

                    if params_id_ruta != "" and params_hora_salida != "" and params_hora_llegada != "" and params_id_autotransporte != "" and params_id_chofer != "" and params_nombre_viaje != "":
                        ruta = request.env['cfdi.rutas'].sudo().search([('id', '=', params_id_ruta)])
                        # Se guardan los datos en cfdi...
                        viaje.write({
                            'nombre_viaje': params_nombre_viaje,
                            'ruta': ruta.id,
                            'FechaHoraSalida': odoo_hora_salida,
                            'FechaHoraProgLlegada': odoo_hora_llegada,
                            'autotransporte': int(params_id_autotransporte),
                            'operadores': int(params_id_chofer)
                        })

                    viaje.write({'concepto': [(5, 0, 0)], 'mercancia': [(5, 0, 0)]})

                    PesoBrutoTotal = 0
                    PesoNetoTotal = 0

                    for merca in params_mercancia:
                        concepto = request.env['cfdi.mercancias'].sudo().search([('id', '=', merca['id_mercancia'])])

                        PesoBrutoTotal = PesoBrutoTotal + (concepto.Peso_kilos * int(merca['cantidad_mercancia']))
                        PesoNetoTotal = PesoNetoTotal + (concepto.Peso_kilos * int(merca['cantidad_mercancia']))

                        viaje.write({'concepto': [(0, 0, {'claveprodserv': concepto.id, 'cantidad_unidad_medida_conocida': merca['cantidad_mercancia']})],
                                    'mercancia': [(0, 0, {'claveprodserv': concepto.id, 'cantidad_unidad_medida_conocida': merca['cantidad_mercancia']})]
                                    })

                    viaje.write({'NumTotalMercancias': len(params_mercancia), 'PesoBrutoTotal': PesoBrutoTotal,
                                'PesoNetoTotal': PesoNetoTotal})

                    if params_necesita_remolque and params_id_remolque != "":
                        viaje.write({
                            'necesita_remolque': params_necesita_remolque,
                            'remolque': int(params_id_remolque)
                        })
                    else:
                        viaje.write({
                            'necesita_remolque': params_necesita_remolque,
                            'remolque': False
                        })

                    if params_necesita_segundo_remolque and params_id_remolque2 != "":
                        viaje.write({
                            'necesita_segundo_remolque': params_necesita_segundo_remolque,
                            'remolque2': int(params_id_remolque2)
                        })
                    else:
                        viaje.write({
                            'necesita_segundo_remolque': params_necesita_segundo_remolque,
                            'remolque2': False
                        })

            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "Faltan datos."

            resp["data"] = {"cfdi": viaje}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # GET CFDI... (Pantalla principal)
    @http.route('/getcfdi', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def getcfdi(self, **kw):
        params_token = request.params.get('token')

        params_fecha_creacion = request.params.get('fecha_creacion')
        params_estatus_viaje = request.params.get('estatus_viaje')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            cfdis = []

            if params_fecha_creacion != "":
                objs = request.env['cfdi.cfdiprueba'].sudo().search(
                    [('fecha_creacion', 'ilike', params_fecha_creacion)], order='id desc')
                contador = 0
                for obj in objs:
                    conceptos = []
                    remolques = []

                    for concep in obj.concepto:
                        conceptos.append({"id_mercancia": concep.claveprodserv.id,
                                          "descripcion": concep.descripcion,
                                          "PesoEnKg": concep.PesoEnKg})

                    cfdis.append({"id": obj.id, "folio": obj.folio,
                                  "nombre_viaje": obj.nombre_viaje,
                                  "uuid": obj.UUIDSAT,
                                  "estatus_viaje": obj.estatus_viaje,
                                  "fecha_creacion": obj.fecha_creacion,
                                  "id_operador": obj.operadores.id,
                                  "operadores": obj.operadores.Nombre_operador,
                                  "id_autotransporte": obj.autotransporte.id,
                                  "autotransporte": obj.autotransporte.Nombre_autotransporte,
                                  "id_ruta": obj.ruta.id,
                                  "ruta": obj.ruta.Ruta,
                                  "FechaHoraSalida": obj.FechaHoraSalida,
                                  "FechaHoraProgLlegada": obj.FechaHoraProgLlegada,
                                  "conceptos": conceptos})

                    if obj.necesita_remolque:
                        remolques.append({"id": obj.remolque.id, "nombre": obj.nombre_remolque,
                                          "subtipo": obj.subtipo_remolque.Nombre_remolque, "placa": obj.placa_remolque})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    if obj.necesita_segundo_remolque:
                        remolques.append({"id": obj.remolque2.id, "nombre": obj.nombre_remolque2,
                                          "subtipo": obj.subtipo_remolque2.Nombre_remolque, "placa": obj.placa_remolque2})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    contador = contador + 1

            elif params_estatus_viaje != "":
                objs = request.env['cfdi.cfdiprueba'].sudo().search([('estatus_viaje', 'ilike', params_estatus_viaje)], order='id desc')
                contador = 0
                for obj in objs:
                    conceptos = []
                    remolques = []

                    for concep in obj.concepto:
                        conceptos.append({"id_mercancia": concep.claveprodserv.id,
                                          "descripcion": concep.descripcion,
                                          "PesoEnKg": concep.PesoEnKg})

                    cfdis.append({"id": obj.id, "folio": obj.folio,
                                  "nombre_viaje": obj.nombre_viaje,
                                  "uuid": obj.UUIDSAT,
                                  "estatus_viaje": obj.estatus_viaje,
                                  "fecha_creacion": obj.fecha_creacion,
                                  "id_operador": obj.operadores.id,
                                  "operadores": obj.operadores.Nombre_operador,
                                  "id_autotransporte": obj.autotransporte.id,
                                  "autotransporte": obj.autotransporte.Nombre_autotransporte,
                                  "id_ruta": obj.ruta.id,
                                  "ruta": obj.ruta.Ruta,
                                  "FechaHoraSalida": obj.FechaHoraSalida,
                                  "FechaHoraProgLlegada": obj.FechaHoraProgLlegada,
                                  "conceptos": conceptos})

                    if obj.necesita_remolque:
                        remolques.append({"id": obj.remolque.id, "nombre": obj.nombre_remolque,
                                          "subtipo": obj.subtipo_remolque.Nombre_remolque, "placa": obj.placa_remolque})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    if obj.necesita_segundo_remolque:
                        remolques.append({"id": obj.remolque2.id, "nombre": obj.nombre_remolque2,
                                          "subtipo": obj.subtipo_remolque2.Nombre_remolque, "placa": obj.placa_remolque2})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    contador = contador + 1
            else:
                objs = request.env['cfdi.cfdiprueba'].sudo().search([], order='id desc')
                contador = 0
                for obj in objs:
                    conceptos = []
                    remolques = []

                    for concep in obj.concepto:
                        conceptos.append({"id_mercancia": concep.claveprodserv.id,
                                          "descripcion": concep.descripcion,
                                          "PesoEnKg": concep.PesoEnKg})

                    cfdis.append({"id": obj.id, "folio": obj.folio,
                                  "nombre_viaje": obj.nombre_viaje,
                                  "uuid": obj.UUIDSAT,
                                  "estatus_viaje": obj.estatus_viaje,
                                  "fecha_creacion": obj.fecha_creacion,
                                  "id_operador": obj.operadores.id,
                                  "operadores": obj.operadores.Nombre_operador,
                                  "id_autotransporte": obj.autotransporte.id,
                                  "autotransporte": obj.autotransporte.Nombre_autotransporte,
                                  "id_ruta": obj.ruta.id,
                                  "ruta": obj.ruta.Ruta,
                                  "FechaHoraSalida": obj.FechaHoraSalida,
                                  "FechaHoraProgLlegada": obj.FechaHoraProgLlegada,
                                  "conceptos": conceptos})

                    if obj.necesita_remolque:
                        remolques.append({"id": obj.remolque.id, "nombre": obj.nombre_remolque,
                                          "subtipo": obj.subtipo_remolque.Nombre_remolque, "placa": obj.placa_remolque})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    if obj.necesita_segundo_remolque:
                        remolques.append({"id": obj.remolque2.id, "nombre": obj.nombre_remolque2,
                                          "subtipo": obj.subtipo_remolque2.Nombre_remolque, "placa": obj.placa_remolque2})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    contador = contador + 1

            resp["data"] = {"cfdis": cfdis}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Crear Viaje (RECEIVE)
    @http.route('/createreceive', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def createreceive(self, **kw):
        params_token = request.params.get('token')

        params_nombre_viaje = request.params.get('nombre_viaje')

        params_mercancia = request.params.get('mercancias')

        params_id_ruta = request.params.get('id_ruta')

        hours = 6
        hours_added = timedelta(hours=hours)

        params_hora_salida = request.params.get('hora_salida')
        hora_salida = datetime.strptime(params_hora_salida, '%Y-%m-%d %H:%M:%S')
        odoo_hora_salida = hora_salida + hours_added

        params_hora_llegada = request.params.get('hora_llegada')
        hora_llegada = datetime.strptime(params_hora_llegada, '%Y-%m-%d %H:%M:%S')
        odoo_hora_llegada = hora_llegada + hours_added

        params_id_autotransporte = request.params.get('id_autotransporte')
        params_id_chofer = request.params.get('id_chofer')

        params_necesita_remolque = request.params.get('necesita_remolque')
        params_id_remolque = request.params.get('id_remolque')

        params_necesita_segundo_remolque = request.params.get('necesita_segundo_remolque')
        params_id_remolque2 = request.params.get('id_remolque2')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:

            if params_id_ruta != "" and params_hora_llegada != "" and params_id_autotransporte != "" and params_id_chofer != "" and params_nombre_viaje != "":

                ruta = request.env['cfdi.rutas'].sudo().search([('id', '=', params_id_ruta)])
                # Se guardan los datos en cfdi...
                cfdi = request.env['cfdi.receive'].sudo().create({
                    'nombre_viaje': params_nombre_viaje,
                    'ruta': ruta.id,
                    'TotalDistRec': ruta.Distancia_recorrida,
                    'FechaHoraSalida': odoo_hora_salida,
                    'FechaHoraProgLlegada': odoo_hora_llegada,
                    'autotransporte': params_id_autotransporte,
                    'operadores': params_id_chofer
                })

                PesoBrutoTotal = 0
                PesoNetoTotal = 0

                for merca in params_mercancia:
                    concepto = request.env['cfdi.mercancias'].sudo().search([('id', '=', merca['id_mercancia'])])

                    PesoBrutoTotal = PesoBrutoTotal + (concepto.Peso_kilos * int(merca['cantidad_mercancia']))
                    PesoNetoTotal = PesoNetoTotal + (concepto.Peso_kilos * int(merca['cantidad_mercancia']))

                    cfdi.write({'concepto': [(0, 0, {'claveprodserv': concepto.id,
                                                     'cantidad_unidad_medida_conocida': merca['cantidad_mercancia']})],
                                'mercancia': [(0, 0, {'claveprodserv': concepto.id,
                                                      'cantidad_unidad_medida_conocida': merca['cantidad_mercancia']})]
                                })

                cfdi.write({'NumTotalMercancias': len(params_mercancia), 'PesoBrutoTotal': PesoBrutoTotal,
                            'PesoNetoTotal': PesoNetoTotal})

                if params_necesita_remolque and params_id_remolque != "":
                    cfdi.write({
                        'necesita_remolque': params_necesita_remolque,
                        'remolque': int(params_id_remolque)
                    })
                else:
                    cfdi.write({
                        'necesita_remolque': params_necesita_remolque,
                        'remolque': False
                    })

                if params_necesita_segundo_remolque and params_id_remolque2 != "":
                    cfdi.write({
                        'necesita_segundo_remolque': params_necesita_segundo_remolque,
                        'remolque2': int(params_id_remolque2)
                    })
                else:
                    cfdi.write({
                        'necesita_segundo_remolque': params_necesita_segundo_remolque,
                        'remolque2': False
                    })

            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "Faltan datos."

            resp["data"] = {"cfdi": cfdi}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Editar Viaje (RECEIVE)
    @http.route('/updatereceive', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def updatereceive(self, **kw):
        params_token = request.params.get('token')

        params_folio = request.params.get('folio')

        params_nombre_viaje = request.params.get('nombre_viaje')

        params_mercancia = request.params.get('mercancias')

        params_id_ruta = request.params.get('id_ruta')

        hours = 6
        hours_added = timedelta(hours=hours)

        params_hora_salida = request.params.get('hora_salida')
        hora_salida = datetime.strptime(params_hora_salida, '%Y-%m-%d %H:%M:%S')
        odoo_hora_salida = hora_salida + hours_added

        params_hora_llegada = request.params.get('hora_llegada')
        hora_llegada = datetime.strptime(params_hora_llegada, '%Y-%m-%d %H:%M:%S')
        odoo_hora_llegada = hora_llegada + hours_added

        params_id_autotransporte = request.params.get('id_autotransporte')
        params_id_chofer = request.params.get('id_chofer')

        params_necesita_remolque = request.params.get('necesita_remolque')
        params_id_remolque = request.params.get('id_remolque')

        params_necesita_segundo_remolque = request.params.get('necesita_segundo_remolque')
        params_id_remolque2 = request.params.get('id_remolque2')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:

            if params_folio != "":
                viaje = request.env['cfdi.receive'].sudo().search([('id', '=', params_folio)])
                if viaje:

                    if params_id_ruta != "" and params_hora_llegada != "" and params_id_autotransporte != "" and params_id_chofer != "" and params_nombre_viaje != "":
                        ruta = request.env['cfdi.rutas'].sudo().search([('id', '=', params_id_ruta)])
                        # Se guardan los datos en cfdi...
                        viaje.write({
                            'nombre_viaje': params_nombre_viaje,
                            'ruta': ruta.id,
                            'FechaHoraSalida': odoo_hora_salida,
                            'FechaHoraProgLlegada': odoo_hora_llegada,
                            'autotransporte': int(params_id_autotransporte),
                            'operadores': int(params_id_chofer)
                        })

                    viaje.write({'concepto': [(5, 0, 0)], 'mercancia': [(5, 0, 0)]})

                    PesoBrutoTotal = 0
                    PesoNetoTotal = 0

                    for merca in params_mercancia:
                        concepto = request.env['cfdi.mercancias'].sudo().search([('id', '=', merca['id_mercancia'])])

                        PesoBrutoTotal = PesoBrutoTotal + (concepto.Peso_kilos * int(merca['cantidad_mercancia']))
                        PesoNetoTotal = PesoNetoTotal + (concepto.Peso_kilos * int(merca['cantidad_mercancia']))

                        viaje.write({'concepto': [(0, 0, {'claveprodserv': concepto.id,
                                                          'cantidad_unidad_medida_conocida': merca[
                                                              'cantidad_mercancia']})],
                                     'mercancia': [(0, 0, {'claveprodserv': concepto.id,
                                                           'cantidad_unidad_medida_conocida': merca[
                                                               'cantidad_mercancia']})]
                                     })

                    viaje.write({'NumTotalMercancias': len(params_mercancia), 'PesoBrutoTotal': PesoBrutoTotal,
                                 'PesoNetoTotal': PesoNetoTotal})

                    if params_necesita_remolque and params_id_remolque != "":
                        viaje.write({
                            'necesita_remolque': params_necesita_remolque,
                            'remolque': int(params_id_remolque)
                        })
                    else:
                        viaje.write({
                            'necesita_remolque': params_necesita_remolque,
                            'remolque': False
                        })

                    if params_necesita_segundo_remolque and params_id_remolque2 != "":
                        viaje.write({
                            'necesita_segundo_remolque': params_necesita_segundo_remolque,
                            'remolque2': int(params_id_remolque2)
                        })
                    else:
                        viaje.write({
                            'necesita_segundo_remolque': params_necesita_segundo_remolque,
                            'remolque2': False
                        })

            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "Faltan datos."

            resp["data"] = {"cfdi": viaje}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # GET RECEIVE... (Pantalla principal)
    @http.route('/getreceive', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def getreceive(self, **kw):
        params_token = request.params.get('token')

        params_fecha_creacion = request.params.get('fecha_creacion')
        params_estatus_viaje = request.params.get('estatus_viaje')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            cfdis = []

            if params_fecha_creacion != "":
                objs = request.env['cfdi.receive'].sudo().search(
                    [('fecha_creacion', 'ilike', params_fecha_creacion)], order='id desc')
                contador = 0
                for obj in objs:
                    conceptos = []
                    remolques = []

                    for concep in obj.concepto:
                        conceptos.append({"id_mercancia": concep.claveprodserv.id,
                                          "descripcion": concep.descripcion,
                                          "PesoEnKg": concep.PesoEnKg})

                    cfdis.append({"id": obj.id, "folio": obj.folio,
                                  "nombre_viaje": obj.nombre_viaje,
                                  "uuid": obj.UUIDSAT,
                                  "estatus_viaje": obj.estatus_viaje,
                                  "fecha_creacion": obj.fecha_creacion,
                                  "id_operador": obj.operadores.id,
                                  "operadores": obj.operadores.Nombre_operador,
                                  "id_autotransporte": obj.autotransporte.id,
                                  "autotransporte": obj.autotransporte.Nombre_autotransporte,
                                  "id_ruta": obj.ruta.id,
                                  "ruta": obj.ruta.Ruta,
                                  "FechaHoraSalida": obj.FechaHoraSalida,
                                  "FechaHoraProgLlegada": obj.FechaHoraProgLlegada,
                                  "conceptos": conceptos})

                    if obj.necesita_remolque:
                        remolques.append({"id": obj.remolque.id, "nombre": obj.nombre_remolque,
                                          "subtipo": obj.subtipo_remolque.Nombre_remolque, "placa": obj.placa_remolque})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    if obj.necesita_segundo_remolque:
                        remolques.append({"id": obj.remolque2.id, "nombre": obj.nombre_remolque2,
                                          "subtipo": obj.subtipo_remolque2.Nombre_remolque,
                                          "placa": obj.placa_remolque2})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    contador = contador + 1

            elif params_estatus_viaje != "":
                objs = request.env['cfdi.receive'].sudo().search([('estatus_viaje', 'ilike', params_estatus_viaje)],
                                                                    order='id desc')
                contador = 0
                for obj in objs:
                    conceptos = []
                    remolques = []

                    for concep in obj.concepto:
                        conceptos.append({"id_mercancia": concep.claveprodserv.id,
                                          "descripcion": concep.descripcion,
                                          "PesoEnKg": concep.PesoEnKg})

                    cfdis.append({"id": obj.id, "folio": obj.folio,
                                  "nombre_viaje": obj.nombre_viaje,
                                  "uuid": obj.UUIDSAT,
                                  "estatus_viaje": obj.estatus_viaje,
                                  "fecha_creacion": obj.fecha_creacion,
                                  "id_operador": obj.operadores.id,
                                  "operadores": obj.operadores.Nombre_operador,
                                  "id_autotransporte": obj.autotransporte.id,
                                  "autotransporte": obj.autotransporte.Nombre_autotransporte,
                                  "id_ruta": obj.ruta.id,
                                  "ruta": obj.ruta.Ruta,
                                  "FechaHoraSalida": obj.FechaHoraSalida,
                                  "FechaHoraProgLlegada": obj.FechaHoraProgLlegada,
                                  "conceptos": conceptos})

                    if obj.necesita_remolque:
                        remolques.append({"id": obj.remolque.id, "nombre": obj.nombre_remolque,
                                          "subtipo": obj.subtipo_remolque.Nombre_remolque, "placa": obj.placa_remolque})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    if obj.necesita_segundo_remolque:
                        remolques.append({"id": obj.remolque2.id, "nombre": obj.nombre_remolque2,
                                          "subtipo": obj.subtipo_remolque2.Nombre_remolque,
                                          "placa": obj.placa_remolque2})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    contador = contador + 1
            else:
                objs = request.env['cfdi.receive'].sudo().search([], order='id desc')
                contador = 0
                for obj in objs:
                    conceptos = []
                    remolques = []

                    for concep in obj.concepto:
                        conceptos.append({"id_mercancia": concep.claveprodserv.id,
                                          "descripcion": concep.descripcion,
                                          "PesoEnKg": concep.PesoEnKg})

                    cfdis.append({"id": obj.id, "folio": obj.folio,
                                  "nombre_viaje": obj.nombre_viaje,
                                  "uuid": obj.UUIDSAT,
                                  "estatus_viaje": obj.estatus_viaje,
                                  "fecha_creacion": obj.fecha_creacion,
                                  "id_operador": obj.operadores.id,
                                  "operadores": obj.operadores.Nombre_operador,
                                  "id_autotransporte": obj.autotransporte.id,
                                  "autotransporte": obj.autotransporte.Nombre_autotransporte,
                                  "id_ruta": obj.ruta.id,
                                  "ruta": obj.ruta.Ruta,
                                  "FechaHoraSalida": obj.FechaHoraSalida,
                                  "FechaHoraProgLlegada": obj.FechaHoraProgLlegada,
                                  "conceptos": conceptos})

                    if obj.necesita_remolque:
                        remolques.append({"id": obj.remolque.id, "nombre": obj.nombre_remolque,
                                          "subtipo": obj.subtipo_remolque.Nombre_remolque, "placa": obj.placa_remolque})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    if obj.necesita_segundo_remolque:
                        remolques.append({"id": obj.remolque2.id, "nombre": obj.nombre_remolque2,
                                          "subtipo": obj.subtipo_remolque2.Nombre_remolque,
                                          "placa": obj.placa_remolque2})
                        cfdis[contador].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdis[contador].update({"remolques": remolques})

                    contador = contador + 1

            resp["data"] = {"cfdis": cfdis}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # GET viajes... (Este es de Armando)
    @http.route('/getviajes', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def getviajes(self, **kw):
        params_token = request.params.get('token')

        params_uuid_referencia = request.params.get('uuid_referencia')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            viajes = []

            if params_uuid_referencia != "":
                objs = request.env['cfdi.cfdiprueba'].sudo().search([('uuid_referencia', '=', params_uuid_referencia)])
                for obj in objs:
                    conceptos = []
                    for concep in obj.concepto:
                        conceptos.append({"descripcion": concep.descripcion, "PesoEnKg": concep.PesoEnKg})

                    viajes.append({"id": obj.id,
                                   "folio": obj.folio,
                                   "nombre_viaje": obj.nombre_viaje,
                                   "uuid": obj.uuid,
                                   "uuid_referencia": obj.uuid_referencia,
                                   "estatus_viaje": obj.estatus_viaje,
                                   "fecha_creacion": obj.fecha_creacion,
                                   "operadores": obj.operadores.Nombre_operador,
                                   "autotransporte": obj.autotransporte.Id_autotransporte,
                                   "ruta": obj.ruta.Ruta,
                                   "conceptos": conceptos})
            else:
                objs = request.env['cfdi.cfdiprueba'].sudo().search([('uuid_referencia', '=', None)])
                for obj in objs:
                    conceptos = []
                    for concep in obj.concepto:
                        conceptos.append({"descripcion": concep.descripcion, "PesoEnKg": concep.PesoEnKg})

                    viajes.append({"id": obj.id,
                                   "folio": obj.folio,
                                   "nombre_viaje": obj.nombre_viaje,
                                   "uuid": obj.uuid,
                                   "uuid_referencia": obj.uuid_referencia,
                                   "estatus_viaje": obj.estatus_viaje,
                                   "fecha_creacion": obj.fecha_creacion,
                                   "operadores": obj.operadores.Nombre_operador,
                                   "autotransporte": obj.autotransporte.Id_autotransporte,
                                   "ruta": obj.ruta.Ruta,
                                   "conceptos": conceptos})

            resp["data"] = {"viajes": viajes}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # GET viajes por placas... (Este es de Armando)
    @http.route('/getviajesplacas', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def getviajesplacas(self, **kw):
        params_token = request.params.get('token')

        params_placa = request.params.get('placa')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            viajes = []

            if params_placa != "":
                objs = request.env['cfdi.cfdiprueba'].sudo().search(
                    [('autotransporte.Placa_vehiculo_motor', '=', params_placa)], order='fecha_creacion desc')
                for obj in objs:
                    conceptos = []
                    for concep in obj.concepto:
                        conceptos.append({"descripcion": concep.descripcion, "PesoEnKg": concep.PesoEnKg})

                    viajes.append({"id": obj.id,
                                   "folio": obj.folio,
                                   "nombre_viaje": obj.nombre_viaje,
                                   "uuid": obj.UUIDSAT,
                                   "estatus_viaje": obj.estatus_viaje,
                                   "fecha_creacion": obj.fecha_creacion,
                                   "operadores": obj.operadores.Nombre_operador,
                                   "autotransporte": obj.autotransporte.Id_autotransporte,
                                   "ruta": obj.ruta.Ruta,
                                   "conceptos": conceptos})
            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "NO se encontraron coincidencias."

            resp["data"] = {"viajes": viajes}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # GET detalle CFDI...
    @http.route('/getdetalleviaje', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def getdetalleviaje(self, **kw):
        params_token = request.params.get('token')

        params_folio = request.params.get('folio')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            cfdi = []

            if params_folio != "":
                objs = request.env['cfdi.cfdiprueba'].sudo().search([('folio', '=', params_folio)])
                for obj in objs:
                    conceptos = []
                    operador = []
                    ruta = []
                    imagenes = []
                    remolques = []
                    autotransporte = []

                    operador.append({"id_operador": obj.operadores.id,
                                     "Nombre_operador": obj.operadores.Nombre_operador,
                                     "RFC_operador": obj.operadores.RFC_operador,
                                     "Numero_licencia_operador": obj.operadores.Numero_licencia,
                                     "Calle_operador": obj.operadores.Calle,
                                     "Num_exterior_operador": obj.operadores.Num_exterior,
                                     "Codigo_postal_operador": obj.operadores.Codigo_postal.Codigo_postal,
                                     "Colonia_operador": obj.operadores.Codigo_postal.Nombre,
                                     "Localidad_operador": obj.operadores.Localidad.Descripcion,
                                     "Municipio_operador": obj.operadores.Municipio.Descripcion,
                                     "Estado_operador": obj.operadores.Estado.Nombre,
                                     "Pais_operador": obj.operadores.Pais.Nombre})

                    ruta.append({"id_ruta": obj.ruta.id,
                                 "ruta": obj.ruta.Ruta,
                                 "Origen": obj.ruta.Origen.Apodo,
                                 "Destino": obj.ruta.Destino.Apodo,
                                 "Distancia_recorrida": obj.ruta.Distancia_recorrida,
                                 "FechaHoraSalida": obj.FechaHoraSalida,
                                 "FechaHoraProgLlegada": obj.FechaHoraProgLlegada})

                    for concep in obj.concepto:
                        conceptos.append({"id_mercancia": concep.claveprodserv.id,
                                          "Nombre_usado": concep.claveprodserv.Nombre_usado,
                                          "Unidades": str(
                                              concep.cantidad_unidad_medida_conocida) + " " + concep.unidad_medida_conocida,
                                          "Bienes_transportados": concep.claveprodserv.Bienes_transportados.Clave_producto + " - " + concep.descripcion,
                                          "Cantidad": str(
                                              concep.cantidad_mercancias) + " " + concep.claveprodserv.Clave_unidad.Clave_unidad + " - " + concep.claveprodserv.Clave_unidad.Nombre,
                                          "PesoEnKg": concep.PesoEnKg})

                    for imagen in objs.imagenes:
                        imagenes.append({"Nombre": imagen.Nombre, "Imagen": imagen.Imagen})

                    autotransporte.append({"Id": obj.autotransporte.id,
                                           "Nombre": obj.autotransporte.Nombre_autotransporte,
                                           "Id_autotransporte": obj.autotransporte.Id_autotransporte,
                                           "Permiso_SCT": obj.autotransporte.Permiso_SCT.Descripcion,
                                           "Numero_permiso_SCT": obj.autotransporte.Numero_permiso_SCT,
                                           "Nombre_aseguradora": obj.autotransporte.Nombre_aseguradora,
                                           "Numero_poliza_seguro": obj.autotransporte.Numero_poliza_seguro,
                                           "Configuracion_vehicular": obj.autotransporte.Configuracion_vehicular.Descripcion,
                                           "Placa_vehiculo_motor": obj.autotransporte.Placa_vehiculo_motor,
                                           "Anio_modelo": obj.autotransporte.Anio_modelo,
                                           "figura_transporte": obj.autotransporte.figura_transporte,
                                           "rfc": obj.autotransporte.rfc,
                                           })

                    cfdi.append({"id": obj.id, "folio": obj.folio,
                                 "nombre_viaje": obj.nombre_viaje,
                                 "estatus_viaje": obj.estatus_viaje,
                                 "uuid": obj.UUIDSAT,
                                 "fecha_creacion": obj.fecha_creacion,
                                 "datos_operador": operador,
                                 "ruta": ruta,
                                 "autotransporte": autotransporte,
                                 "conceptos": conceptos,
                                 "imagenes": imagenes})

                    if obj.necesita_remolque:
                        remolques.append({"id": obj.remolque.id, "nombre": obj.nombre_remolque,
                                          "subtipo": obj.subtipo_remolque.Nombre_remolque, "placa": obj.placa_remolque})
                        cfdi[0].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdi[0].update({"remolques": remolques})

                    if obj.necesita_segundo_remolque:
                        remolques.append({"id": obj.remolque2.id, "nombre": obj.nombre_remolque2,
                                          "subtipo": obj.subtipo_remolque2.Nombre_remolque, "placa": obj.placa_remolque2})
                        cfdi[0].update({"remolques": remolques})
                    else:
                        remolques.append({"id": 0, "nombre": False, "subtipo": False, "placa": False})
                        cfdi[0].update({"remolques": remolques})

            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "No se encontro el folio."

            resp["data"] = {"cfdi": cfdi}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Update estatus viaje...
    @http.route('/updateestatusviaje', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def updateestatusviaje(self, **kw):
        params_token = request.params.get('token')

        params_id_viaje = request.params.get('id_viaje')
        params_estatus_viaje = request.params.get('estatus_viaje')

        #('Creado', 'Creado'),
        #('Timbrado', 'Timbrado'),
        #('Iniciado', 'Iniciado'),
        #('Cancelado', 'Cancelado'),
        #('Terminado', 'Terminado')]

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            cfdi = []

            if params_id_viaje != "":
                viaje = request.env['cfdi.cfdiprueba'].sudo().search([('id', '=', params_id_viaje)])
                if viaje:
                    if params_estatus_viaje == 'Timbrado':
                        viaje.action_timbrar()
                    viaje.write({'estatus_viaje': params_estatus_viaje})

            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "No se encontro el folio."

            resp["data"] = {"viaje": viaje.folio, "estatus_viaje": viaje.estatus_viaje}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # GET geolocalizacion...
    @http.route('/getgeolocalizacion', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def getgeolocalizacion(self, **kw):
        params_token = request.params.get('token')

        params_id_viaje = request.params.get('id_viaje')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            viajes = []

            if params_id_viaje != "":
                objs = request.env['cfdi.cfdiprueba'].sudo().search([('id', '=', params_id_viaje)])
                for obj in objs:
                    localizaion = []
                    for geo in obj.geolocalizacion:
                        localizaion.append({"latitud": geo.latitud, "longitud": geo.longitud,
                                            "tipo": geo.tipo, "fecha_hora": geo.fecha_hora})

                    viajes.append({"id": obj.id,
                                   "folio": obj.folio,
                                   "nombre_viaje": obj.nombre_viaje,
                                   "uuid": obj.UUIDSAT,
                                   "estatus_viaje": obj.estatus_viaje,
                                   "fecha_creacion": obj.fecha_creacion,
                                   "operadores": obj.operadores.Nombre_operador,
                                   "autotransporte": obj.autotransporte.Id_autotransporte,
                                   "ruta": obj.ruta.Ruta,
                                   "geolocalizacion": localizaion})
            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "Id no encontrado."

            resp["data"] = {"viajes": viajes}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Write geolocalizacion...
    @http.route('/writegeolocalizacion', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def writegeolocalizacion(self, **kw):
        params_token = request.params.get('token')

        params_id_viaje = request.params.get('id_viaje')
        params_latitud = request.params.get('latitud')
        params_longitud = request.params.get('longitud')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            if params_id_viaje != "":
                objs = request.env['cfdi.cfdiprueba'].sudo().search([('id', '=', params_id_viaje)])
                for obj in objs:
                    localizacion = []
                    for geo in obj.geolocalizacion:
                        if geo.tipo == "Actual":
                            geo.write({'tipo': "Punto"})

                    if params_latitud != "" and params_longitud != "":
                        obj.write({'geolocalizacion': [(0, 0, {"latitud": params_latitud, "longitud": params_longitud,
                                   "tipo": "Actual", "fecha_hora": fields.datetime.now()})]})

            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "Id no encontrado."

            resp["data"] = {}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Get imagenes en CFDI...
    @http.route('/getimageviaje', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def getimageviaje(self, **kw):
        params_token = request.params.get('token')

        params_id_viaje = request.params.get('id_viaje')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:
            datos = []
            imagenes = []

            if params_id_viaje != "":
                viaje = request.env['cfdi.cfdiprueba'].sudo().search([('id', '=', params_id_viaje)])

                for imagen in viaje.imagenes:
                    imagenes.append({"Nombre": imagen.Nombre, "Imagen": imagen.Imagen})

                datos.append({"Imagenes": imagenes})

            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "Id incorrecto."

            resp["data"] = {"datos": datos}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    # Guardar imagen en CFDI...
    @http.route('/saveimageviaje', type='json', methods=['POST'], auth="public", website=True, csrf=False)
    def saveimageviaje(self, **kw):
        params_token = request.params.get('token')

        params_id_viaje = request.params.get('id_viaje')
        params_imagen = request.params.get('imagen')

        resp = {"success": True, "status": "OK", "code": 200, "message": "", "data": ""}
        # Se revisa que el usuario exista...
        existe = request.env['cfdi.usuariosapp'].sudo().search([('token', '=', params_token)])
        if existe:

            if params_id_viaje != "":
                viaje = request.env['cfdi.cfdiprueba'].sudo().search([('id', '=', params_id_viaje)])

                viaje.write({'imagenes': [(0, 0, {
                    'Nombre': "",
                    'Imagen': params_imagen})]})

            else:
                resp["success"] = False
                resp["status"] = "NOK"
                resp["code"] = 402
                resp["message"] = "Id incorrecto."

            resp["data"] = {}
            resp["success"] = True
            resp["status"] = "OK"
            resp["code"] = 200
            resp["message"] = ""
        else:
            resp["success"] = False
            resp["status"] = "NOK"
            resp["code"] = 402
            resp["message"] = "Error de Token."
        return resp

    @http.route('/getcartaporte/<int:id_viaje>', type='http', auth="public", website=True, csrf=False)
    def getcartaporte(self, id_viaje, **kw):
        viaje = request.env['cfdi.cfdiprueba'].sudo().search([('id', '=', id_viaje)], limit=1)

        pdf, _ = request.env['ir.actions.report']._get_report_from_name('cfdi.report_cfdi_cfdiprueba').sudo()._render_qweb_pdf([int(id_viaje)])
        pdf_http_headers = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf))]
        return request.make_response(pdf, headers=pdf_http_headers)

    @http.route('/getcartaportexml/<int:id_viaje>', type='http', auth="public", website=True, csrf=False)
    def getcartaportexml(self, id_viaje, **kw):
        viaje = request.env['cfdi.cfdiprueba'].sudo().search([('id', '=', id_viaje)], limit=1)

        xml64 = viaje.archivo

        xml = b64decode(xml64)

        xml_http_headers = [('Content-Type', 'application/xml'), ('Content-Length', len(xml))]
        return request.make_response(xml, headers=xml_http_headers)

    @http.route('/getcfdicp/<int:id_viaje>', type='http', auth="public", website=True, csrf=False)
    def getcartaporte(self, id_viaje, **kw):
        viaje = request.env['cfdi.cfdiprueba'].sudo().search([('id', '=', id_viaje)], limit=1)

        pdf, _ = request.env['ir.actions.report']._get_report_from_name('cfdi.report_cfdi_cfdi_ingreso').sudo()._render_qweb_pdf([int(id_viaje)])
        pdf_http_headers = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf))]
        return request.make_response(pdf, headers=pdf_http_headers)

    @http.route('/getcfdiingreso/<int:id_viaje>', type='http', auth="public", website=True, csrf=False)
    def getcartaporte_ingreso(self, id_viaje, **kw):
        viaje = request.env['cfdi.cfdi_ingreso'].sudo().search([('id', '=', id_viaje)], limit=1)

        pdf, _ = request.env['ir.actions.report']._get_report_from_name(
            'cfdi.report_cfdi_cfdi_ingreso').sudo()._render_qweb_pdf([int(id_viaje)])
        pdf_http_headers = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf))]
        return request.make_response(pdf, headers=pdf_http_headers)

    @http.route('/getcfditraslado/<int:id_viaje>', type='http', auth="public", website=True, csrf=False)
    def getcartaporte_trslado(self, id_viaje, **kw):
        viaje = request.env['cfdi.cfdi_traslado'].sudo().search([('id', '=', id_viaje)], limit=1)

        pdf, _ = request.env['ir.actions.report']._get_report_from_name(
            'cfdi.report_cfdi_cfdi_traslado').sudo()._render_qweb_pdf([int(id_viaje)])
        pdf_http_headers = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf))]
        return request.make_response(pdf, headers=pdf_http_headers)

    @http.route('/getcfdi40ingreso/<int:id_viaje>', type='http', auth="public", website=True, csrf=False)
    def getcartaporte40_ingreso(self, id_viaje, **kw):
        pdf, _ = request.env['ir.actions.report']._get_report_from_name(
            'cfdi.report_cfdi_cfdi40_ingreso').sudo()._render_qweb_pdf([int(id_viaje)])
        pdf_http_headers = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf))]
        return request.make_response(pdf, headers=pdf_http_headers)

    @http.route('/getcfdi40_complementopago/<int:id_viaje>', type='http', auth="public", website=True, csrf=False)
    def get_complementopago_pdf(self, id_viaje, **kw):
        complemento = request.env['cfdi.cfdi40_complemento_pago'].sudo().search([('id', '=', id_viaje)], limit=1)
        nombre_archivo = str(complemento.folio) + '.pdf'

        pdf, _ = request.env['ir.actions.report']._get_report_from_name( 'cfdi.report_cfdi_complemento').sudo()._render_qweb_pdf([int(id_viaje)])
        pdf_http_headers = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf)),
                            ('Content-Disposition', 'attachment; filename="%s"' % nombre_archivo)]
        return request.make_response(pdf, headers=pdf_http_headers)
