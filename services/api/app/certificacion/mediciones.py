"""O3 Mediciones de biomasa. Contrato 04.

    GET  /mediciones               lo que el sujeto puede ver
    GET  /mediciones/exportar      CSV para el auditor (X.C7)
    GET  /mediciones/{id}          una medicion
    POST /mediciones               registrar (TC, VF)
    POST /mediciones/{id}/aprobar  el verificador la acepta (A.C3)
    POST /mediciones/{id}/devolver el verificador la rechaza (D.C3)

La matriz sobre O3:

    Direccion General, Direccion de Certificacion    L
    Tecnico de campo     L.C1, C.C2
    Verificador          L, C.(C1 y C2), A.C3, D.C3
    Auditor externo      L.C7, X.C7
    Dueno de finca       L.C8
    ningun rol           M

Nadie modifica una medicion. Una vez registrada solo cambia de estado, y eso
lo impone la base: app_rw tiene UPDATE solo sobre las columnas de la
decision (migracion 006). Corregir una medicion ya decidida es una enmienda
(O4).

C3 es la separacion de deberes central. El motor compara el autor con quien
aprueba, pero que el sujeto haya medido OTRA vez esa finca en ese periodo
mira otras filas, asi que lo calcula este modulo y lo manda como contexto.

El tecnico de campo ademas tiene que ser de la zona de la finca al registrar.
La matriz solo le pide C2 en C, pero registrar una medicion de una finca que
no le toca no tiene sentido y el motor ya sabe decidirlo con C1 (L sobre O1).
Es parte de D-17.
"""

import csv
import io
from decimal import Decimal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import bd
from app.auth.dependencias import (SesionCompleta, SesionReautenticada,
                                   autorizar, consultar)
from app.bitacora import registrar
from app.certificacion import consultas as q
from app.certificacion import estados
from app.certificacion.fincas import inexistente
from app.errores import ErrorAPI

router = APIRouter(tags=["mediciones"])



class NuevaMedicion(BaseModel):
    finca: int = Field(gt=0)
    periodo: int = Field(gt=0)
    biomasa_toneladas: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class Devolucion(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


def _una(cur, medicion_id: int, bloquear: bool = False) -> dict | None:
    cur.execute(q.SELECT_MEDICION + "WHERE m.id = %s" +
                (" FOR UPDATE OF m" if bloquear else ""), (medicion_id,))
    return cur.fetchone()


@router.get("/mediciones")
def listar_mediciones(sesion: SesionCompleta,
                      periodo: int | None = Query(default=None, gt=0),
                      finca: int | None = Query(default=None, gt=0),
                      estado: str | None = Query(
                          default=None,
                          pattern="^(REGISTRADA|APROBADA|DEVUELTA)$")) -> dict:
    with bd.transaccion() as cur:
        propios = q.atributos_sujeto(cur, sesion)
        general = consultar(sesion, "L", "O3", propios)
        # El auditor no filtra fila por fila: su unica condicion (C7) es de
        # el y no de la fila. Sin ventana vigente no hay permiso que filtrar.
        if not general.permitido and (
                general.condicion is None or sesion.rol == "AUDITOR_EXTERNO"):
            autorizar(sesion, "L", "O3", objeto="O3:*", atributos=propios)

        filtro, parametros = q.previo_por_rol(sesion, "O3")
        # Las condiciones del usuario van como parametros. Los fragmentos de
        # texto son fijos, escritos aqui.
        for columna, valor in (("m.periodo", periodo), ("m.finca", finca),
                               ("m.estado::text", estado)):
            if valor is not None:
                filtro += " AND %s = %%s" % columna
                parametros += (valor,)
        cur.execute(q.SELECT_MEDICION + "WHERE true" + filtro +
                    " ORDER BY m.id LIMIT %s", (*parametros, q.LIMITE_LISTADO))
        visibles = []
        for fila in cur.fetchall():
            if not general.permitido and not consultar(
                    sesion, "L", "O3",
                    {**propios, **q.atributos_medicion(fila)}).permitido:
                continue
            visibles.append(q.medicion_json(fila))
        registrar(accion="MEDICIONES_LISTADAS", sujeto=sesion.sujeto.id,
                  objeto="O3:*", resultado="PERMITIDO",
                  detalle={"resultados": len(visibles)})
    return {"mediciones": visibles}


# Antes de /mediciones/{id}: si no, "exportar" se tomaria por un id.
@router.get("/mediciones/exportar")
def exportar_mediciones(sesion: SesionCompleta) -> Response:
    """Todas las mediciones, en CSV. Solo el auditor, y solo en su ventana."""
    with bd.transaccion() as cur:
        autorizar(sesion, "X", "O3", objeto="O3:*",
                  atributos=q.atributos_sujeto(cur, sesion))
        cur.execute(q.SELECT_MEDICION + "ORDER BY m.id")
        filas = cur.fetchall()
        registrar(accion="MEDICIONES_EXPORTADAS", sujeto=sesion.sujeto.id,
                  objeto="O3:*", resultado="PERMITIDO",
                  detalle={"filas": len(filas)})

    salida = io.StringIO()
    escritor = csv.writer(salida, lineterminator="\n")
    escritor.writerow(["id", "finca", "periodo", "autor", "biomasa_toneladas",
                       "estado", "registrada_en"])
    for f in filas:
        escritor.writerow([f["id"], f["finca"], f["periodo_etiqueta"],
                           f["autor"], f["biomasa_toneladas"], f["estado"],
                           f["registrada_en"].isoformat()])
    return Response(
        salida.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="mediciones.csv"'})


@router.get("/mediciones/{medicion_id}")
def ver_medicion(medicion_id: int, sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        fila = _una(cur, medicion_id)
        objeto = "O3:%d" % medicion_id
        if fila is None:
            inexistente(cur, sesion, "L", "O3", objeto)
        autorizar(sesion, "L", "O3", objeto=objeto, atributos={
            **q.atributos_sujeto(cur, sesion), **q.atributos_medicion(fila)})
    return q.medicion_json(fila)


@router.post("/mediciones", status_code=201)
def registrar_medicion(datos: NuevaMedicion, sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        # El periodo se bloquea para que no se cierre entre la pregunta al
        # motor y el INSERT (C2 dejaria de ser cierta sin que nadie se entere).
        cur.execute("SELECT estado::text AS estado FROM periodos_medicion "
                    "WHERE id = %s FOR SHARE", (datos.periodo,))
        periodo = cur.fetchone()
        cur.execute("SELECT id, zona, propietario FROM fincas WHERE id = %s",
                    (datos.finca,))
        finca = cur.fetchone()
        objeto = "O3:nueva"
        if periodo is None or finca is None:
            inexistente(cur, sesion, "C", "O3", objeto)

        atributos = {**q.atributos_finca(finca),
                     "periodo.estado": periodo["estado"]}
        autorizar(sesion, "C", "O3", objeto=objeto, atributos=atributos)
        if sesion.rol == "TECNICO_CAMPO":
            autorizar(sesion, "L", "O1", objeto="O1:%d" % finca["id"],
                      atributos=q.atributos_finca(finca))

        cur.execute(
            "INSERT INTO mediciones (finca, periodo, autor, biomasa_toneladas) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (datos.finca, datos.periodo, sesion.cuenta,
             datos.biomasa_toneladas))
        nueva = cur.fetchone()["id"]
        registrar(accion="MEDICION_REGISTRADA", sujeto=sesion.sujeto.id,
                  objeto="O3:%d" % nueva, resultado="PERMITIDO",
                  detalle={"finca": datos.finca, "periodo": datos.periodo})
    return {"id": nueva, "estado": estados.REGISTRADA}


def _decidir(medicion_id: int, sesion, operacion: str, nuevo: str,
             accion: str, motivo: str | None = None) -> dict:
    with bd.transaccion() as cur:
        fila = _una(cur, medicion_id, bloquear=True)
        objeto = "O3:%d" % medicion_id
        if fila is None:
            inexistente(cur, sesion, operacion, "O3", objeto)

        atributos = {
            **q.atributos_medicion(fila),
            "contexto.sujeto_midio_en_finca_periodo":
                q.sujeto_midio_en_finca_periodo(
                    cur, sesion, fila["finca"], fila["periodo"], fila["id"]),
        }
        autorizar(sesion, operacion, "O3", objeto=objeto, atributos=atributos)
        estados.exigir_transicion_medicion(fila["estado"], nuevo)

        cur.execute(
            "UPDATE mediciones SET estado = %s, revisada_por = %s, "
            "revisada_en = now(), motivo_devolucion = %s WHERE id = %s",
            (nuevo, sesion.cuenta, motivo, medicion_id))
        registrar(accion=accion, sujeto=sesion.sujeto.id, objeto=objeto,
                  resultado="PERMITIDO",
                  detalle={"finca": fila["finca"], "periodo": fila["periodo"]})
    return {"id": medicion_id, "estado": nuevo}


@router.post("/mediciones/{medicion_id}/aprobar")
def aprobar_medicion(medicion_id: int, sesion: SesionReautenticada) -> dict:
    return _decidir(medicion_id, sesion, "A", estados.APROBADA,
                    "MEDICION_APROBADA")


@router.post("/mediciones/{medicion_id}/devolver")
def devolver_medicion(medicion_id: int, datos: Devolucion,
                      sesion: SesionCompleta) -> dict:
    return _decidir(medicion_id, sesion, "D", estados.DEVUELTA,
                    "MEDICION_DEVUELTA", datos.motivo)
