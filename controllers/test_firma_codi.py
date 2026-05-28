# test_firma_codi.py
import base64
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

PEM_PATH = 'C:\Program Files\Odoo 17.0.20251203\server\custom_addons\Llave\dwit.pem'

cadena = "||5531211229|1.00|1234567|646180693400000003|SISTEMA DE TRANSFERENCIAS Y PAGOS STP SA|40|prueba GRUPO_KUALE|GRUPO_KUALE|2500|20||"

with open(PEM_PATH, "rb") as f:
    private_key = serialization.load_pem_private_key(
        f.read(), password=None, backend=default_backend()
    )

payload_base = {
    "numeroCelularCliente": "5531211229",
    "concepto":             "prueba GRUPO_KUALE",
    "minutosLimite":        "2500",
    "monto":                1.00,
    "nombreBeneficiario2":  "SISTEMA DE TRANSFERENCIAS Y PAGOS STP SA",
    "tipoCuentaBeneficiario2": "40",
    "cuentaBeneficiario2":  "646180693400000003",
    "empresa":              "GRUPO_KUALE",
    "tipoPagoDeSpei":       "20",
    "numeroReferenciaComercio": "1234567",
}

# ── Prueba 1: SHA1withRSA ──────────────────────────────────────────────────
firma_sha1 = private_key.sign(
    cadena.encode("utf-8"),
    padding.PKCS1v15(),
    hashes.SHA1()       # ← SHA1
)
firma_sha1_b64 = base64.b64encode(firma_sha1).decode("utf-8")

# ── Prueba 2: SHA256withRSA (la que ya tienes) ────────────────────────────
firma_sha256 = private_key.sign(
    cadena.encode("utf-8"),
    padding.PKCS1v15(),
    hashes.SHA256()     # ← SHA256
)
firma_sha256_b64 = base64.b64encode(firma_sha256).decode("utf-8")

print(f"SHA1   firma: {firma_sha1_b64[:60]}...")
print(f"SHA256 firma: {firma_sha256_b64[:60]}...")

# ── Envía ambas y observa cuál responde diferente ─────────────────────────
for nombre, firma in [
    ("SHA1+UTF8",    base64.b64encode(private_key.sign(cadena.encode("utf-8"),   padding.PKCS1v15(), hashes.SHA1())).decode()),
    ("SHA256+UTF8",  base64.b64encode(private_key.sign(cadena.encode("utf-8"),   padding.PKCS1v15(), hashes.SHA256())).decode()),
    ("SHA1+Latin1",  base64.b64encode(private_key.sign(cadena.encode("latin-1"), padding.PKCS1v15(), hashes.SHA1())).decode()),
    ("SHA256+Latin1",base64.b64encode(private_key.sign(cadena.encode("latin-1"), padding.PKCS1v15(), hashes.SHA256())).decode()),
]:
    payload = {**payload_base, "firma": firma}
    resp = requests.post(
        "https://demo.stpmex.com:7024/codi/registraCobro",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=10, verify=False
    )
    print(f"[{nombre:<16}] {resp.text}")