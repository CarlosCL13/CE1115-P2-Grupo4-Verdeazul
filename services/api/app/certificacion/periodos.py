"""O2 Periodos de medicion. Contrato 04.

    GET  /periodos                lista
    GET  /periodos/{id}           uno
    POST /periodos                abrir un periodo nuevo (Ab)
    POST /periodos/{id}/abrir     reabrir uno cerrado (Ab)
    POST /periodos/{id}/cerrar    cerrarlo (Cr)

La matriz sobre O2:

    Direccion de Certificacion   L, Ab, Cr
    Auditor externo              L.C7
    los otros cinco con acceso   L
    Tercero autorizado           nada

Abrir y cerrar piden reautenticacion (Tabla 7.1 de P1). El contrato solo
listaba `/abrir` y `/cerrar`, pero un periodo no puede abrirse si no existe, y
ningun otro endpoint lo crea. Por eso `POST /periodos` nace ABIERTO bajo la
operacion Ab y `/abrir` queda para reabrir. Es la desviacion D-17.

`periodo.estado` es lo que miran C2 y C11. El cierre y el registro de
mediciones se serializan con un bloqueo sobre la fila del periodo, para que
una medicion no entre justo mientras el periodo se cierra.
"""

import re

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import bd
from app.auth.dependencias import (SesionCompleta, SesionReautenticada,
                                   autorizar)
from app.bitacora import registrar
from app.certificacion import consultas as q
from app.certificacion import estados
from app.certificacion.fincas import inexistente
from app.errores import ErrorAPI

router = APIRouter(tags=["periodos"])

_ETIQUETA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{1,18}[A-Za-z0-9]$")

SELECT_PERIODO = ("SELECT id, etiqueta, estado::text AS estado, abierto_en, "
                  "cerrado_en FROM periodos_medicion ")


class NuevoPeriodo(BaseModel):
    etiqueta: str = Field(min_length=3, max_length=20)


@router.get("/periodos")
def listar_periodos(sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        propios = q.atributos_sujeto(cur, sesion)
        # Los periodos no tienen dueno ni zona: la unica condicion posible es
        # C7, y el sujeto entero la cumple o no. Una sola pregunta basta.
        autorizar(sesion, "L", "O2", objeto="O2:*", atributos=propios)
        cur.execute(SELECT_PERIODO + "ORDER BY id DESC")
        filas = cur.fetchall()
        registrar(accion="PERIODOS_LISTADOS", sujeto=sesion.sujeto.id,
                  objeto="O2:*", resultado="PERMITIDO",
                  detalle={"resultados": len(filas)})
    return {"periodos": [q.periodo_json(f) for f in filas]}


@router.get("/periodos/{periodo_id}")
def ver_periodo(periodo_id: int, sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        objeto = "O2:%d" % periodo_id
        propios = q.atributos_sujeto(cur, sesion)
        cur.execute(SELECT_PERIODO + "WHERE id = %s", (periodo_id,))
        fila = cur.fetchone()
        if fila is None:
            inexistente(cur, sesion, "L", "O2", objeto)
        autorizar(sesion, "L", "O2", objeto=objeto, atributos=propios)
    return q.periodo_json(fila)


@router.post("/periodos", status_code=201)
def abrir_periodo_nuevo(datos: NuevoPeriodo,
                        sesion: SesionReautenticada) -> dict:
    if not _ETIQUETA.match(datos.etiqueta):
        raise ErrorAPI(422, "etiqueta_invalida",
                       "La etiqueta usa letras, números y guiones, como 2027-Q1.")
    with bd.transaccion() as cur:
        autorizar(sesion, "Ab", "O2", objeto="O2:nuevo")
        cur.execute("SELECT 1 FROM periodos_medicion WHERE etiqueta = %s",
                    (datos.etiqueta,))
        if cur.fetchone() is not None:
            raise ErrorAPI(409, "etiqueta_repetida",
                           "Ya existe un período con esa etiqueta.")
        cur.execute("INSERT INTO periodos_medicion (etiqueta) VALUES (%s) "
                    "RETURNING id", (datos.etiqueta,))
        nuevo = cur.fetchone()["id"]
        registrar(accion="PERIODO_ABIERTO", sujeto=sesion.sujeto.id,
                  objeto="O2:%d" % nuevo, resultado="PERMITIDO",
                  detalle={"etiqueta": datos.etiqueta, "nuevo": True})
    return {"id": nuevo, "estado": estados.PERIODO_ABIERTO}


def _cambiar(periodo_id: int, sesion, operacion: str, desde: str, hacia: str,
             accion: str) -> dict:
    with bd.transaccion() as cur:
        objeto = "O2:%d" % periodo_id
        cur.execute(SELECT_PERIODO + "WHERE id = %s FOR UPDATE", (periodo_id,))
        fila = cur.fetchone()
        if fila is None:
            inexistente(cur, sesion, operacion, "O2", objeto)
        autorizar(sesion, operacion, "O2", objeto=objeto)
        estados.exigir_periodo_en(fila["estado"], desde)

        if hacia == estados.PERIODO_CERRADO:
            pendientes = estados.mediciones_sin_aprobar(cur, periodo_id)
            if pendientes:
                raise ErrorAPI(409, "mediciones_pendientes",
                               "Quedan %d mediciones sin aprobar o devolver."
                               % pendientes, pendientes=pendientes)
            cur.execute("UPDATE periodos_medicion SET estado = 'CERRADO', "
                        "cerrado_en = now() WHERE id = %s", (periodo_id,))
        else:
            cur.execute("UPDATE periodos_medicion SET estado = 'ABIERTO', "
                        "cerrado_en = NULL WHERE id = %s", (periodo_id,))
        registrar(accion=accion, sujeto=sesion.sujeto.id, objeto=objeto,
                  resultado="PERMITIDO",
                  detalle={"etiqueta": fila["etiqueta"]})
    return {"id": periodo_id, "estado": hacia}


@router.post("/periodos/{periodo_id}/abrir")
def reabrir_periodo(periodo_id: int, sesion: SesionReautenticada) -> dict:
    return _cambiar(periodo_id, sesion, "Ab", estados.PERIODO_CERRADO,
                    estados.PERIODO_ABIERTO, "PERIODO_ABIERTO")


@router.post("/periodos/{periodo_id}/cerrar")
def cerrar_periodo(periodo_id: int, sesion: SesionReautenticada) -> dict:
    return _cambiar(periodo_id, sesion, "Cr", estados.PERIODO_ABIERTO,
                    estados.PERIODO_CERRADO, "PERIODO_CERRADO")
