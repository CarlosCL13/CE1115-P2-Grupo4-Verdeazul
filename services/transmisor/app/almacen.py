"""Subir un archivo al deposito de volcados en Cloud Storage.

Solo la biblioteca estandar: la API JSON de Cloud Storage es un POST, y una
dependencia mas (google-cloud-storage y sus veinte paquetes) es mas
superficie para Dependabot que lo que ahorra.

El token sale del servidor de metadatos de Cloud Run, que lo entrega para la
cuenta de servicio del transmisor: ninguna llave en el contenedor ni en el
repositorio. En local no hay servidor de metadatos, y el token se pasa por
VOLCADO_TOKEN (`gcloud auth print-access-token`), que vive una hora.

La cuenta del transmisor tiene solo roles/storage.objectCreator sobre ese
deposito: puede crear objetos, no leerlos, reemplazarlos ni borrarlos. Y cada
subida pide ifGenerationMatch=0, que falla si el nombre ya existe: un volcado
nunca pisa a otro.
"""

import json
import os
import urllib.parse
import urllib.request

from app import config

_METADATOS = ("http://metadata.google.internal/computeMetadata/v1/instance/"
              "service-accounts/default/token")
_SUBIDA = "https://storage.googleapis.com/upload/storage/v1/b/%s/o"
TIEMPO_LIMITE = 60


class SinDeposito(RuntimeError):
    """Falta el nombre del deposito o la forma de autenticarse."""


def _token() -> str:
    if config.ENTORNO == "nube":
        pedido = urllib.request.Request(_METADATOS,
                                        headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(pedido, timeout=10) as r:
            return json.load(r)["access_token"]
    token = os.environ.get("VOLCADO_TOKEN", "").strip()
    if not token:
        raise SinDeposito(
            "En local falta VOLCADO_TOKEN. Sacalo con: "
            "gcloud auth print-access-token")
    return token


def subir(nombre: str, contenido: bytes, tipo: str) -> dict:
    """Crea el objeto `nombre`. Falla si ya existe. Devuelve lo que responde
    Cloud Storage: generation, md5Hash, size, etc."""
    deposito = config.VOLCADO_DEPOSITO
    if not deposito:
        raise SinDeposito("Falta VOLCADO_DEPOSITO, el nombre del deposito.")
    url = (_SUBIDA % urllib.parse.quote(deposito, safe="") + "?" +
           urllib.parse.urlencode({"uploadType": "media", "name": nombre,
                                   "ifGenerationMatch": "0"}))
    pedido = urllib.request.Request(
        url, data=contenido, method="POST",
        headers={"Authorization": "Bearer " + _token(),
                 "Content-Type": tipo})
    with urllib.request.urlopen(pedido, timeout=TIEMPO_LIMITE) as r:
        return json.load(r)
