"""O8 Asignaciones tecnico-zona. Contrato 04.

    GET   /asignaciones             las que el sujeto puede ver
    GET   /asignaciones/opciones    zonas y cuentas para el formulario (C)
    GET   /asignaciones/{id}        una asignacion
    POST  /asignaciones             Direccion de Certificacion asigna (C)
    PATCH /asignaciones/{id}        cambiar zona, extender o revocar (M)

La matriz sobre O8:

    Direccion General              L
    Direccion de Certificacion     L, C, M
    Tecnico de campo, Verificador  L.C1
    los demas roles                nada
    ningun rol                     E

Este objeto alimenta C1, la condicion mas usada (O1, O3, O4 y O8): las zonas
de una persona son sus asignaciones sin revocar y sin vencer, y se leen en
cada peticion (contrato 05). Por eso revocar aqui quita el acceso en el
siguiente clic, sin esperar a que la persona salga: es el «se revocan los
accesos el mismo dia» de las politicas (CU-11) con reflejo tecnico.

Toda asignacion tiene fecha de fin (CU-07, HBAC-03). Al vencer deja de dar
acceso sola, porque C1 compara con la fecha de hoy; la tarea `vencer` del
transmisor ademas la marca revocada.

No se borra nada (nadie tiene E): revocar deja la fila con su fecha, para
que se sepa quien tuvo que zona y hasta cuando (CU-13).

Crear y modificar piden reautenticacion: dar o quitar una zona es dar o
quitar acceso a los datos de esa zona, igual que un cambio de rol.
"""

import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, model_validator

from app import bd
from app.auth.dependencias import (SesionCompleta, SesionReautenticada,
                                   autorizar, consultar)
from app.bitacora import registrar
from app.certificacion import consultas as qc
from app.certificacion.fincas import inexistente
from app.errores import ErrorAPI

router = APIRouter(tags=["asignaciones"])

# Solo estos roles trabajan por zona. Asignarle una zona a otro rol no le da
# nada (C1 solo aplica a ellos) y confundiria a quien lea la tabla.
ROLES_CON_ZONA = ("TECNICO_CAMPO", "VERIFICADOR")

# Una cobertura de mas de tres anos ya no es temporal (CU-07).
MAXIMO_DIAS = 3 * 366

SELECT_ASIGNACION = (
    "SELECT a.id, a.sujeto, a.zona, z.nombre AS zona_nombre, a.vence, "
    "       a.asignada_en, a.revocada_en, c.usuario, c.rol::text AS rol, "
    "       (a.revocada_en IS NULL AND a.vence >= CURRENT_DATE) AS vigente "
    "FROM asignaciones_zona a "
    "JOIN zonas z ON z.id = a.zona "
    "JOIN cuentas c ON c.id = a.sujeto ")


class NuevaAsignacion(BaseModel):
    sujeto: int = Field(gt=0)
    zona: str = Field(min_length=1, max_length=8, pattern="^[A-Z]+$")
    vence: datetime.date


class CambioAsignacion(BaseModel):
    zona: str | None = Field(default=None, min_length=1, max_length=8,
                             pattern="^[A-Z]+$")
    vence: datetime.date | None = None
    revocar: bool = False

    @model_validator(mode="after")
    def _algo_cambia(self):
        if self.revocar and (self.zona or self.vence):
            raise ValueError("revocar va solo: no se cambia y se revoca a la vez")
        if not (self.revocar or self.zona or self.vence):
            raise ValueError("no hay nada que cambiar")
        return self


def _atributos(fila: dict) -> dict:
    # Contrato 02: C1 en O8 manda la zona de la asignacion bajo finca.zona.
    return {"finca.zona": fila["zona"]}


def _json(fila: dict) -> dict:
    return {
        "id": fila["id"],
        "sujeto": fila["sujeto"],
        "usuario": fila["usuario"],
        "rol": fila["rol"],
        "zona": fila["zona"],
        "zona_nombre": fila["zona_nombre"],
        "vence": fila["vence"].isoformat(),
        "asignada_en": fila["asignada_en"].isoformat(),
        "revocada_en": (fila["revocada_en"].isoformat()
                        if fila["revocada_en"] else None),
        "vigente": fila["vigente"],
    }


def _una(cur, asignacion_id: int, bloquear: bool = False) -> dict | None:
    cur.execute(SELECT_ASIGNACION + "WHERE a.id = %s" +
                (" FOR UPDATE OF a" if bloquear else ""), (asignacion_id,))
    return cur.fetchone()


def _exigir_vence(vence: datetime.date) -> None:
    hoy = datetime.date.today()
    if vence < hoy:
        raise ErrorAPI(422, "vence_en_el_pasado",
                       "La fecha de fin no puede ser anterior a hoy.")
    if (vence - hoy).days > MAXIMO_DIAS:
        raise ErrorAPI(422, "vence_muy_lejos",
                       "Una asignación dura como máximo tres años (CU-07).")


def _exigir_zona(cur, zona: str) -> None:
    cur.execute("SELECT 1 FROM zonas WHERE id = %s", (zona,))
    if cur.fetchone() is None:
        raise ErrorAPI(422, "zona_invalida", "Esa zona no existe.")


def _sin_otra_abierta(cur, sujeto: int, zona: str, excepto: int = 0) -> None:
    """El indice unico de la migracion 007 admite una sola sin revocar por
    persona y zona. Se pregunta antes para dar un mensaje util en vez de un
    error de la base."""
    cur.execute("SELECT id, vence < CURRENT_DATE AS vencida "
                "FROM asignaciones_zona WHERE sujeto = %s AND zona = %s "
                "AND revocada_en IS NULL AND id <> %s", (sujeto, zona, excepto))
    otra = cur.fetchone()
    if otra is not None:
        raise ErrorAPI(409, "ya_asignada",
                       "Esa persona ya tiene la asignación %d en esa zona%s: "
                       "extiéndala en vez de crear otra."
                       % (otra["id"], " (vencida)" if otra["vencida"] else ""))


@router.get("/asignaciones")
def listar_asignaciones(sesion: SesionCompleta,
                        zona: str | None = Query(default=None, max_length=8,
                                                 pattern="^[A-Z]+$"),
                        sujeto: int | None = Query(default=None, gt=0),
                        solo_vigentes: bool = False) -> dict:
    with bd.transaccion() as cur:
        general = consultar(sesion, "L", "O8")
        if not general.permitido and general.condicion is None:
            autorizar(sesion, "L", "O8", objeto="O8:*")

        filtro, parametros = "", ()
        # Optimizacion, no control: el motor decide cada fila abajo.
        if not general.permitido:
            filtro += " AND a.zona = ANY(%s)"
            parametros += (list(sesion.zonas),)
        for columna, valor in (("a.zona", zona), ("a.sujeto", sujeto)):
            if valor is not None:
                filtro += " AND %s = %%s" % columna
                parametros += (valor,)
        if solo_vigentes:
            filtro += " AND a.revocada_en IS NULL AND a.vence >= CURRENT_DATE"
        cur.execute(SELECT_ASIGNACION + "WHERE true" + filtro +
                    " ORDER BY a.revocada_en IS NOT NULL, a.zona, a.vence DESC, "
                    "a.id DESC LIMIT 500", parametros)
        visibles = [_json(f) for f in cur.fetchall()
                    if general.permitido or consultar(
                        sesion, "L", "O8", _atributos(f)).permitido]
        registrar(accion="ASIGNACIONES_LISTADAS", sujeto=sesion.sujeto.id,
                  objeto="O8:*", resultado="PERMITIDO",
                  detalle={"resultados": len(visibles)})
    return {"asignaciones": visibles}


# Antes de /asignaciones/{id}: si no, "opciones" se tomaria por un id.
@router.get("/asignaciones/opciones")
def opciones(sesion: SesionCompleta) -> dict:
    """Lo que el formulario de asignar necesita: las zonas y las cuentas
    activas que trabajan por zona. Solo para quien puede crear (C sobre O8).

    Va aparte de GET /cuentas a proposito: Direccion de Certificacion no
    tiene L sobre O9, y no hace falta darsela. Esto devuelve solo id,
    usuario y rol de tecnicos y verificadores, nada de O6 ni de O9.
    """
    with bd.transaccion() as cur:
        autorizar(sesion, "C", "O8", objeto="O8:opciones")
        cur.execute("SELECT id, nombre FROM zonas ORDER BY id")
        zonas = cur.fetchall()
        cur.execute("SELECT id, usuario, rol::text AS rol FROM cuentas "
                    "WHERE activa AND rol::text = ANY(%s) ORDER BY usuario",
                    (list(ROLES_CON_ZONA),))
        cuentas = cur.fetchall()
    return {"zonas": zonas, "cuentas": cuentas}


@router.get("/asignaciones/{asignacion_id}")
def ver_asignacion(asignacion_id: int, sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        fila = _una(cur, asignacion_id)
        objeto = "O8:%d" % asignacion_id
        if fila is None:
            inexistente(cur, sesion, "L", "O8", objeto)
        autorizar(sesion, "L", "O8", objeto=objeto, atributos=_atributos(fila))
    return _json(fila)


@router.post("/asignaciones", status_code=201)
def crear_asignacion(datos: NuevaAsignacion,
                     sesion: SesionReautenticada) -> dict:
    with bd.transaccion() as cur:
        # Primero el permiso: quien no puede crear no se entera de si la
        # cuenta o la zona existen.
        autorizar(sesion, "C", "O8", objeto="O8:nueva",
                  atributos={"finca.zona": datos.zona})
        _exigir_zona(cur, datos.zona)
        _exigir_vence(datos.vence)

        cur.execute("SELECT id, rol::text AS rol FROM cuentas "
                    "WHERE id = %s AND activa", (datos.sujeto,))
        cuenta = cur.fetchone()
        if cuenta is None or cuenta["rol"] not in ROLES_CON_ZONA:
            raise ErrorAPI(422, "sujeto_invalido",
                           "Solo se asignan zonas a técnicos de campo y "
                           "verificadores con cuenta activa.")
        _sin_otra_abierta(cur, datos.sujeto, datos.zona)

        cur.execute("INSERT INTO asignaciones_zona (sujeto, zona, vence) "
                    "VALUES (%s, %s, %s) RETURNING id",
                    (datos.sujeto, datos.zona, datos.vence))
        nueva = cur.fetchone()["id"]
        registrar(accion="ASIGNACION_CREADA", sujeto=sesion.sujeto.id,
                  objeto="O8:%d" % nueva, resultado="PERMITIDO",
                  detalle={"asignado": str(datos.sujeto), "zona": datos.zona,
                           "vence": datos.vence.isoformat()})
        fila = _una(cur, nueva)
    return _json(fila)


@router.patch("/asignaciones/{asignacion_id}")
def modificar_asignacion(asignacion_id: int, datos: CambioAsignacion,
                         sesion: SesionReautenticada) -> dict:
    with bd.transaccion() as cur:
        fila = _una(cur, asignacion_id, bloquear=True)
        objeto = "O8:%d" % asignacion_id
        if fila is None:
            inexistente(cur, sesion, "M", "O8", objeto)
        autorizar(sesion, "M", "O8", objeto=objeto, atributos=_atributos(fila))

        if fila["revocada_en"] is not None:
            raise ErrorAPI(409, "ya_revocada",
                           "La asignación ya fue revocada: cree una nueva.")

        if datos.revocar:
            cur.execute("UPDATE asignaciones_zona SET revocada_en = now() "
                        "WHERE id = %s", (asignacion_id,))
            registrar(accion="ASIGNACION_REVOCADA", sujeto=sesion.sujeto.id,
                      objeto=objeto, resultado="PERMITIDO",
                      detalle={"asignado": str(fila["sujeto"]),
                               "zona": fila["zona"]})
        else:
            zona = datos.zona or fila["zona"]
            vence = datos.vence or fila["vence"]
            if datos.zona and datos.zona != fila["zona"]:
                _exigir_zona(cur, zona)
                _sin_otra_abierta(cur, fila["sujeto"], zona,
                                  excepto=asignacion_id)
            if datos.vence:
                _exigir_vence(vence)
            cur.execute("UPDATE asignaciones_zona SET zona = %s, vence = %s "
                        "WHERE id = %s", (zona, vence, asignacion_id))
            registrar(accion="ASIGNACION_MODIFICADA", sujeto=sesion.sujeto.id,
                      objeto=objeto, resultado="PERMITIDO",
                      detalle={"asignado": str(fila["sujeto"]),
                               "zona_antes": fila["zona"], "zona": zona,
                               "vence_antes": fila["vence"].isoformat(),
                               "vence": vence.isoformat()})
        fila = _una(cur, asignacion_id)
    return _json(fila)
