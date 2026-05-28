import requests

STP_DEMO_URL = "https://demo.stpmex.com:7024/speiws/rest/ordenPago/registra"
STP_CONSULTA_ACTUAL = "https://efws-dev.stpmex.com/consultasws/API/operaciones/actual"
STP_CONSULTA_HISTORICA = "https://efws-dev.stpmex.com/consultasws/API/operaciones/historica"
STP_CONSULTA_NATURAL = "https://efws-dev.stpmex.com/consultasws/API/operaciones/fechaNatural"
STP_CONSULTA_SALDO = "https://efws-dev.stpmex.com/efws/API/consultaSaldoCuenta"
###########PEDIENTE#############
STP_CONSULTA_CLAVERASTREO = "https://efws-dev.stpmex.com/consultasws/API/orden/clave-rastreo"
################################
STP_CONSULTA_COMPROBANTE = "https://efws-dev.stpmex.com/consultasws/API/comprobante"
#################################
STP_CONSULTA_SALDO_ACTUAL = "https://efws-dev.stpmex.com/consultasws/API/conciliacion/actual"
STP_CONSULTA_SALDO_HISTORICO = "https://efws-dev.stpmex.com/consultasws/API/conciliacion/historica"
#################################
STP_CONSULTA_INSTITUCIONES = "https://efws-dev.stpmex.com/efws/API/consultaInstituciones"
#################################
STP_CODI_CONSULTA_ESTADO = "https://demo.stpmex.com:7024/codi/cadenaConsultaEstadoOperacion"
STP_CODI_REGISTRA_COBRO = "https://demo.stpmex.com:7024/codi/registraCobro"
STP_CODI_REGISTRA_QR = "https://demo.stpmex.com:7024/codi/registraCobroQR"
##################################
STP_CATALOGO_SERVICIOS = "https://efws-dev.stpmex.com/API/v1/PASE/pagoServicio/catalogos-servicios"
STP_SERVICIOS_SIN_REFERENCIA = "https://efws-dev.stpmex.com/API/v1/PASE/pagoServicio/pago-servicios-sin-referencia"
STP_SERVICIOS_CON_REFERENCIA = "https://efws-dev.stpmex.com/API/v1/PASE/pagoServicio/pago-servicios-con-referencia"
STP_VERIFICACION_REFERENCIA = "https://efws-dev.stpmex.com/API/v1/PASE/pagoServicio/verificacion-referencia"
STP_VALIDACION_PAGO_SERVICIO = "https://efws-dev.stpmex.com/API/v1/PASE/pagoServicio/valida-pago-servicio"
STP_REIMPRESION_TICKETS = "https://efws-dev.stpmex.com/API/v1/PASE/pagoServicio/reimprime-ticket"
STP_HISTORICO_PAGOS = "https://efws-dev.stpmex.com/API/v1/PASE/pagoServicio/lista-historico-pago-servicios"

def enviar_orden_pago_stp(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.put(
        STP_DEMO_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def consulta_fecha_actual(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CONSULTA_ACTUAL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def consulta_fecha_historica(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CONSULTA_HISTORICA,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def consulta_fecha_natural(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CONSULTA_NATURAL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def consulta_saldo(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CONSULTA_SALDO,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

#TODO: ***PENDIENTE***
def consulta_orden_claverastreo(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CONSULTA_CLAVERASTREO,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def consulta_comprobante_stp(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CONSULTA_COMPROBANTE,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def consulta_conciliacion_saldo_actual(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CONSULTA_SALDO_ACTUAL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def consulta_conciliacion_saldo_historica(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CONSULTA_SALDO_HISTORICO,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def consulta_conciliacion_instituciones(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CONSULTA_INSTITUCIONES,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def codi_consulta_estado(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CODI_CONSULTA_ESTADO,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=5,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def codi_registro_cobro(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CODI_REGISTRA_COBRO,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=10,
        verify=False  # Solo ambiente demo
    )

    print("STATUS:", response.status_code)
    print("RESPUESTA STP:", response.text)

    try:
        data = response.json()
    except Exception:
        raise Exception(f"Respuesta inválida STP:\n{response.text}")

    #
    if response.status_code not in (200, 401):
        raise Exception(f"Error HTTP {response.status_code}:\n{response.text}")

    return data
###TODO:PEDIENTE DE CERT
def codi_registro_cobro_qr(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CODI_REGISTRA_QR,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=5,
        verify=False  # Solo ambiente demo
    )

    print("STATUS:", response.status_code)
    print("RESPUESTA STP:", response.text)

    try:
        data = response.json()
    except Exception:
        raise Exception(f"Respuesta inválida STP:\n{response.text}")

    #
    if response.status_code not in (200, 401):
        raise Exception(f"Error HTTP {response.status_code}:\n{response.text}")

    return data

def consulta_catalogo_servicio(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_CATALOGO_SERVICIOS,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=5,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

#TODO: REVISAR QUE MARCA A LA EMPRESA COMO INHABILITADA
def pago_servicios_sin_referencia(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_SERVICIOS_SIN_REFERENCIA,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=5,
        verify=False  # Solo ambiente demo
    )

    try:
        data = response.json()
    except Exception:
        raise Exception(f"Respuesta inválida STP:\n{response.text}")

    #
    if response.status_code not in (200, 401):
        raise Exception(f"Error HTTP {response.status_code}:\n{response.text}")

    return data

#TODO: REVISAR QUE MARCA A LA EMPRESA COMO INHABILITADA
def pago_servicios_con_referencia(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_SERVICIOS_CON_REFERENCIA,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=5,
        verify=False  # Solo ambiente demo
    )

    try:
        data = response.json()
    except Exception:
        raise Exception(f"Respuesta inválida STP:\n{response.text}")

    #
    if response.status_code not in (200, 401):
        raise Exception(f"Error HTTP {response.status_code}:\n{response.text}")

    return data

def verificacion_referencia(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_VERIFICACION_REFERENCIA,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=5,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def valida_pago_servicio(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_VALIDACION_PAGO_SERVICIO,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=5,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def reimpresion_tickets(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_REIMPRESION_TICKETS,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=5,
        verify=False  # Solo ambiente demo
    )

    response.raise_for_status()  # error HTTP si algo falla

    return response.json()

def historico_pagos(payload: dict) -> dict:
    """
    Envía una orden de pago al endpoint DEMO de STP
    """
    response = requests.post(
        STP_HISTORICO_PAGOS,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=5,
        verify=False  # Solo ambiente demo
    )

    try:
        data = response.json()
    except Exception:
        raise Exception(f"Respuesta inválida STP:\n{response.text}")

    #
    if response.status_code not in (200, 401):
        raise Exception(f"Error HTTP {response.status_code}:\n{response.text}")

    return data
