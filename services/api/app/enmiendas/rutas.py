"""O4 Enmiendas. Contrato 04.

    GET  /enmiendas                 lo que el sujeto puede ver
    GET  /enmiendas/exportar        CSV para el auditor (X.C7)
    GET  /enmiendas/{id}            una enmienda
    POST /enmiendas                 el tecnico la pide (C.C11)
    POST /enmiendas/{id}/aprobar    el verificador la acepta (A.C4)
    POST /enmiendas/{id}/devolver   el verificador la rechaza (D.C4)
    POST /enmiendas/{id}/cerrar     Direccion de Certificacion la cierra (Cr.C5)

La matriz sobre O4:

    Direccion General                  L
    Direccion de Certificacion         L, Cr.C5
    Tecnico de campo                   L.C1, C.C11
    Verificador                        L, A.C4, D.C4
    Auditor externo                    L.C7, X.C7
    Dueno de finca                     L.C8
    Personal Administrativo, Tercero   nada
    ningun rol                         M, E

Una enmienda es lo que reemplaza a editar una medicion despues del cierre
(AI-02). La medicion no cambia: la enmienda deja el rastro formal de la
correccion, con tres personas distintas (SR-03). Si la medicion ya tenia
certificado, Direccion de Certificacion lo anula y se emite otro (O5); esa
parte es de certificados, no de aqui.

Aprobar y cerrar piden reautenticacion (P1, Tabla 7.1): son las dos firmas
que hacen valer la correccion.
"""

import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import bd
from app.auth.dependencias import (SesionCompleta, SesionReautenticada,
                                   autorizar, consultar)
from app.bitacora import registrar
from app.certificacion import consultas as qc
from app.certificacion.fincas import inexistente
from app.enmiendas import consultas as q
from app.enmiendas import estados
from app.errores import ErrorAPI

router = APIRouter(tags=["enmiendas"])

LIMITE_LISTADO = 200


class NuevaEnmienda(BaseModel):
    medicion: int = Field(gt=0)
    justificacion: str = Field(min_length=10, max_length=1000)


class Devolucion(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


def _una(cur, enmienda_id: int, bloquear: bool = False) -> dict | None:
    cur.execute(q.SELECT_ENMIENDA + "WHERE e.id = %s" +
                (" FOR UPDATE OF e" if bloquear else ""), (enmienda_id,))
    return cur.fetchone()


@router.get("/enmiendas")
def listar_enmiendas(sesion: SesionCompleta,
                     estado: str | None = Query(
                         default=None,
                         pattern="^(SOLICITADA|REVISADA|CERRADA|DEVUELTA)$"),
                     medicion: int | None = Query(default=None, gt=0)) -> dict:
    with bd.transaccion() as cur:
        propios = qc.atributos_sujeto(cur, sesion)
        general = consultar(sesion, "L", "O4", propios)
        # Igual que en O3: el auditor no filtra fila por fila, su condicion
        # (C7) es de el. Si el rol no tiene L, es un intento denegado.
        if not general.permitido and (
                general.condicion is None or sesion.rol == "AUDITOR_EXTERNO"):
            autorizar(sesion, "L", "O4", objeto="O4:*", atributos=propios)

        filtro, parametros = qc.previo_por_rol(sesion, "O4")
        for columna, valor in (("e.estado::text", estado),
                               ("e.medicion", medicion)):
            if valor is not None:
                filtro += " AND %s = %%s" % columna
                parametros += (valor,)
        cur.execute(q.SELECT_ENMIENDA + "WHERE true" + filtro +
                    " ORDER BY e.id DESC LIMIT %s",
                    (*parametros, LIMITE_LISTADO))
        visibles = []
        for fila in cur.fetchall():
            if not general.permitido and not consultar(
                    sesion, "L", "O4",
                    {**propios, **q.atributos_enmienda(fila)}).permitido:
                continue
            visibles.append(q.enmienda_json(fila))
        registrar(accion="ENMIENDAS_LISTADAS", sujeto=sesion.sujeto.id,
                  objeto="O4:*", resultado="PERMITIDO",
                  detalle={"resultados": len(visibles)})
    return {"enmiendas": visibles}


# Antes de /enmiendas/{id}: si no, "exportar" se tomaria por un id.
@router.get("/enmiendas/exportar")
def exportar_enmiendas(sesion: SesionCompleta) -> Response:
    """Todas las enmiendas, en CSV. Solo el auditor, y solo en su ventana.
    Mismo formato que GET /mediciones/exportar: una fila por registro."""
    with bd.transaccion() as cur:
        autorizar(sesion, "X", "O4", objeto="O4:*",
                  atributos=qc.atributos_sujeto(cur, sesion))
        cur.execute(q.SELECT_ENMIENDA + "ORDER BY e.id")
        filas = cur.fetchall()
        registrar(accion="ENMIENDAS_EXPORTADAS", sujeto=sesion.sujeto.id,
                  objeto="O4:*", resultado="PERMITIDO",
                  detalle={"filas": len(filas)})

    salida = io.StringIO()
    escritor = csv.writer(salida, lineterminator="\n")
    escritor.writerow(["id", "medicion", "finca", "periodo", "solicitante",
                       "justificacion", "estado", "revisor", "revisada_en",
                       "cerrada_por", "cerrada_en", "solicitada_en"])
    for f in filas:
        escritor.writerow([
            f["id"], f["medicion"], f["finca"], f["periodo_etiqueta"],
            f["solicitante"], f["justificacion"], f["estado"],
            f["revisor"] or "",
            f["revisada_en"].isoformat() if f["revisada_en"] else "",
            f["cerrada_por"] or "",
            f["cerrada_en"].isoformat() if f["cerrada_en"] else "",
            f["solicitada_en"].isoformat()])
    return Response(
        salida.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="enmiendas.csv"'})


@router.get("/enmiendas/{enmienda_id}")
def ver_enmienda(enmienda_id: int, sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        fila = _una(cur, enmienda_id)
        objeto = "O4:%d" % enmienda_id
        if fila is None:
            inexistente(cur, sesion, "L", "O4", objeto)
        autorizar(sesion, "L", "O4", objeto=objeto, atributos={
            **qc.atributos_sujeto(cur, sesion), **q.atributos_enmienda(fila)})
    return q.enmienda_json(fila)


@router.post("/enmiendas", status_code=201)
def solicitar_enmienda(datos: NuevaEnmienda, sesion: SesionCompleta) -> dict:
    justificacion = datos.justificacion.strip()
    if len(justificacion) < 10:
        raise ErrorAPI(422, "justificacion_corta",
                       "Explique la corrección en al menos 10 caracteres.")

    with bd.transaccion() as cur:
        # La medicion y su periodo, bloqueando el periodo para que no se
        # reabra entre la pregunta al motor y el INSERT. C11 se revalida
        # dentro de la misma transaccion de escritura (P1, 6.1).
        cur.execute(qc.SELECT_MEDICION + "WHERE m.id = %s FOR SHARE OF p",
                    (datos.medicion,))
        medicion = cur.fetchone()
        objeto = "O4:nueva"
        if medicion is None:
            inexistente(cur, sesion, "C", "O4", objeto)

        autorizar(sesion, "C", "O4", objeto=objeto, atributos={
            **qc.atributos_finca(medicion),
            "medicion.autor_id": str(medicion["autor"]),
            "periodo.estado": medicion["periodo_estado"],
        })

        # Una sola enmienda abierta por medicion: dos correcciones en vuelo
        # sobre el mismo dato no se sabe en que orden valen.
        cur.execute("SELECT id FROM enmiendas WHERE medicion = %s "
                    "AND estado::text = ANY(%s) LIMIT 1",
                    (datos.medicion, list(estados.ABIERTAS)))
        abierta = cur.fetchone()
        if abierta is not None:
            raise ErrorAPI(409, "enmienda_abierta",
                           "Esa medición ya tiene la enmienda %d sin cerrar."
                           % abierta["id"])

        cur.execute(
            "INSERT INTO enmiendas (medicion, solicitante, justificacion) "
            "VALUES (%s, %s, %s) RETURNING id",
            (datos.medicion, sesion.cuenta, justificacion))
        nueva = cur.fetchone()["id"]
        # La justificacion no va al evento: es texto libre y el contrato 03
        # no admite datos personales. Queda en la enmienda.
        registrar(accion="ENMIENDA_SOLICITADA", sujeto=sesion.sujeto.id,
                  objeto="O4:%d" % nueva, resultado="PERMITIDO",
                  detalle={"medicion": str(datos.medicion),
                           "finca": str(medicion["finca"]),
                           "periodo": str(medicion["periodo"])})
    return {"id": nueva, "estado": estados.SOLICITADA}


def _decidir(enmienda_id: int, sesion, operacion: str, nuevo: str,
             accion: str, columnas: str, detalle: dict | None = None) -> dict:
    """Aprobar, devolver o cerrar: misma forma, distinta columna de persona.

    Se bloquea la fila antes de preguntar al motor: dos verificadores a la
    vez no pueden revisar la misma enmienda, y nadie la cierra mientras otro
    la esta revisando.
    """
    with bd.transaccion() as cur:
        fila = _una(cur, enmienda_id, bloquear=True)
        objeto = "O4:%d" % enmienda_id
        if fila is None:
            inexistente(cur, sesion, operacion, "O4", objeto)

        autorizar(sesion, operacion, "O4", objeto=objeto,
                  atributos=q.atributos_enmienda(fila))
        estados.exigir_transicion(fila["estado"], nuevo)

        # `columnas` es fijo, escrito en este archivo; los valores van como %s.
        cur.execute("UPDATE enmiendas SET estado = %%s, %s WHERE id = %%s"
                    % columnas, (nuevo, sesion.cuenta, enmienda_id))
        registrar(accion=accion, sujeto=sesion.sujeto.id, objeto=objeto,
                  resultado="PERMITIDO",
                  detalle={"medicion": str(fila["medicion"]),
                           "solicitante": str(fila["solicitante"]),
                           **(detalle or {})})
    return {"id": enmienda_id, "estado": nuevo}


_REVISION = "revisor = %s, revisada_en = now()"
_CIERRE = "cerrada_por = %s, cerrada_en = now()"


@router.post("/enmiendas/{enmienda_id}/aprobar")
def aprobar_enmienda(enmienda_id: int, sesion: SesionReautenticada) -> dict:
    return _decidir(enmienda_id, sesion, "A", estados.REVISADA,
                    "ENMIENDA_APROBADA", _REVISION)


@router.post("/enmiendas/{enmienda_id}/devolver")
def devolver_enmienda(enmienda_id: int, datos: Devolucion,
                      sesion: SesionCompleta) -> dict:
    # La tabla no tiene columna para el motivo (migracion 008): queda en el
    # evento, que es justo donde un auditor lo busca.
    return _decidir(enmienda_id, sesion, "D", estados.DEVUELTA,
                    "ENMIENDA_DEVUELTA", _REVISION,
                    detalle={"motivo": datos.motivo.strip()})


@router.post("/enmiendas/{enmienda_id}/cerrar")
def cerrar_enmienda(enmienda_id: int, sesion: SesionReautenticada) -> dict:
    return _decidir(enmienda_id, sesion, "Cr", estados.CERRADA,
                    "ENMIENDA_CERRADA", _CIERRE)
