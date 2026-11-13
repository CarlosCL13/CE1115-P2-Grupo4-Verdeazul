"""Tarea `volcado`: copia la bitacora a Cloud Storage. BI-03, BI-04, LG-06.

La bitacora vive en Neon, que en plan gratuito restaura solo las ultimas seis
horas. Diez anos de trazabilidad (BI-04, LG-06) no pueden depender de eso. Esta
tarea deja una copia completa fuera de Neon, en un deposito con politica de
retencion: mientras dure, nadie puede borrar ni reemplazar la copia, ni
siquiera el transmisor que la subio (D-07).

Solo la bitacora, no la base principal (D-07): es lo que exige diez anos, y
se lee con log_reader, que ya existe. Copiar la base principal pediria un rol
con lectura de todo el esquema, incluidos los datos personales cifrados.

Cada corrida sube dos objetos con el mismo prefijo de fecha y hora:

    bitacora/AAAA/MM/DD/bitacora-AAAAMMDDTHHMMSSZ.jsonl.gz    los eventos
    bitacora/AAAA/MM/DD/bitacora-AAAAMMDDTHHMMSSZ.json        el manifiesto

Los eventos van uno por linea, con su secuencia y su eslabon, y la hora en el
mismo formato que usa la forma canonica. Con la llave de la cadena, quien
tenga el archivo puede recalcular cada eslabon sin acceso a Neon: es la
«copia periodica externa que permite comparar» de D-03.

El manifiesto dice cuantos eventos hay, de que secuencia a cual, el ultimo
eslabon, el SHA-256 del archivo y si la cadena cuadraba al copiarla (la misma
comprobacion de `cadena`). El volcado no se detiene si la cadena esta rota:
precisamente entonces conviene tener la copia, y el manifiesto lo dice.
"""

import datetime
import gzip
import hashlib
import io
import json
import logging

from app import almacen, bd, config, eslabon
from app.tareas.cadena import _lotes, _llave
from app.tareas.transmitir import CANDADO

log = logging.getLogger("transmisor.volcado")


def _linea(fila: dict) -> bytes:
    datos = {
        "secuencia": fila["secuencia"],
        "id": str(fila["id"]),
        "momento": eslabon._momento(fila["momento"]),
        "accion": fila["accion"],
        "sujeto": fila["sujeto"],
        "objeto": fila["objeto"],
        "resultado": fila["resultado"],
        "motivo": fila["motivo"],
        "detalle": fila["detalle"],
        "eslabon": fila["eslabon"],
    }
    return json.dumps(datos, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8") + b"\n"


def empaquetar(llave: bytes, lotes) -> tuple[bytes, dict]:
    """Los eventos en JSON Lines comprimido, y lo que dice el manifiesto.

    Recalcula la cadena mientras escribe, igual que `cadena`: el manifiesto
    deja constancia de si la copia salio de una cadena intacta.
    """
    salida = io.BytesIO()
    anterior = eslabon.INICIO
    eventos, rotos = 0, 0
    primera = ultima = None
    # mtime=0: el mismo contenido da el mismo gzip, y el mismo SHA-256.
    with gzip.GzipFile(fileobj=salida, mode="wb", mtime=0) as gz:
        for filas in lotes:
            for fila in filas:
                if not eslabon.coincide(fila["eslabon"],
                                        eslabon.calcular(llave, anterior, fila)):
                    rotos += 1
                anterior = fila["eslabon"]
                gz.write(_linea(fila))
                eventos += 1
                primera = fila["secuencia"] if primera is None else primera
                ultima = fila["secuencia"]
    contenido = salida.getvalue()
    return contenido, {
        "eventos": eventos,
        "secuencia_primera": primera,
        "secuencia_ultima": ultima,
        "ultimo_eslabon": anterior,
        "cadena_intacta": rotos == 0,
        "eslabones_rotos": rotos,
        "sha256": hashlib.sha256(contenido).hexdigest(),
        "bytes": len(contenido),
    }


def ejecutar(*, llave: bytes | None = None, abrir_bandeja=None,
             abrir_lectura=None, subir=None, ahora=None) -> dict:
    llave = llave if llave is not None else _llave()
    abrir_bandeja = abrir_bandeja or bd.bandeja
    abrir_lectura = abrir_lectura or bd.lectura
    subir = subir or almacen.subir
    ahora = ahora or datetime.datetime.now(datetime.timezone.utc)

    sello = ahora.strftime("%Y%m%dT%H%M%SZ")
    base = "bitacora/%s/bitacora-%s" % (ahora.strftime("%Y/%m/%d"), sello)

    with abrir_bandeja() as bandeja:
        # El mismo candado que transmitir y cadena: la copia sale de una
        # bitacora que nadie esta extendiendo en ese momento.
        bandeja.execute("SELECT pg_advisory_xact_lock(%s)", (CANDADO,))

        with abrir_lectura() as lectura:
            contenido, manifiesto = empaquetar(llave, _lotes(lectura, 1000))

        manifiesto = {
            "formato": "verdeazul-bitacora-jsonl-v1",
            "generado_en": ahora.isoformat(),
            "archivo": base + ".jsonl.gz",
            **manifiesto,
        }
        # Primero los datos y despues el manifiesto: un manifiesto nunca
        # describe un archivo que no llego.
        datos = subir(base + ".jsonl.gz", contenido, "application/gzip")
        subir(base + ".json",
              json.dumps(manifiesto, indent=2, ensure_ascii=False).encode(),
              "application/json")

        resultado = {"tarea": "volcado", "deposito": config.VOLCADO_DEPOSITO,
                     "generacion": datos.get("generation"), **manifiesto}
        bd.anotar(bandeja, [("VOLCADO_REALIZADO", "O11:*", {
            "archivo": manifiesto["archivo"],
            "eventos": manifiesto["eventos"],
            "sha256": manifiesto["sha256"],
            "cadena_intacta": manifiesto["cadena_intacta"],
        })])

    log.info("volcado: %s eventos en %s (sha256 %s)",
             manifiesto["eventos"], manifiesto["archivo"],
             manifiesto["sha256"][:16])
    return resultado
