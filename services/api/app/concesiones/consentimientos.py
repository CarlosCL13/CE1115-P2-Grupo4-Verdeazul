"""O7 Consentimientos y autorizaciones a terceros. Contrato 04.

    GET   /consentimientos             los que el sujeto puede ver
    GET   /consentimientos/opciones    fincas y terceros para el formulario (C)
    GET   /consentimientos/{id}        uno
    POST  /consentimientos             autorizar a un tercero (C)
    PATCH /consentimientos/{id}        extender o revocar (M)

La matriz sobre O7:

    Direccion General              L
    Personal Administrativo        L, C
    Dueno de finca                 L.C8, C.C8, M.C8
    los demas roles                nada
    ningun rol                     E

Una fila de aqui dice: «el dueno de esta finca autoriza a este tercero a ver
sus certificados hasta esta fecha». Es lo unico que le da algo a un Tercero
Autorizado: O5 L.C9 lee esta tabla (app/certificados/consultas.py). Es la
regla LG-03 de P1 (Ley 8968, art. 14: un tercero solo ve lo que el dueno
autorizo) y CU-09 (toda autorizacion vence y el dueno la revoca cuando
quiera).

Quien otorga es siempre el dueno de la finca. Si el Personal Administrativo
registra la autorizacion por el (la matriz le da C), `otorgado_por` sigue
siendo el dueno, y quien la registro queda en el evento de la bitacora.

Revocar quita el acceso en la siguiente peticion del tercero: C9 se evalua en
cada lectura y una autorizacion revocada ya no se le manda al motor. Es el
«se revocan los accesos el mismo dia» del enunciado (§4). Al vencer deja de
servir sola (C9 compara hoy < vence), y la tarea `vencer` del transmisor
ademas la marca revocada.

Crear y extender piden reautenticacion: es entregarle informacion del dueno a
otra persona. Revocar no: es la accion que protege, y no debe costar nada
(D-21).
"""

import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, model_validator

from app import bd
from app.auth.dependencias import (SesionCompleta, autorizar, consultar,
                                   exigir_reautenticacion)
from app.bitacora import registrar
from app.certificacion.fincas import inexistente
from app.errores import ErrorAPI

router = APIRouter(tags=["consentimientos"])

# Igual que las asignaciones (CU-07): una autorizacion de mas de tres anos ya no es temporal.
MAXIMO_DIAS = 3 * 366

# Vigente es lo mismo que C9: sin revocar y hoy < vence. El dia que vence ya no sirve.
SELECT_CONSENTIMIENTO = (
    "SELECT k.id, k.finca, f.nombre AS finca_nombre, f.propietario, "
    "       k.tercero, t.usuario AS tercero_usuario, k.otorgado_por, "
    "       k.vence, k.otorgado_en, k.revocado_en, "
    "       (k.revocado_en IS NULL AND k.vence > CURRENT_DATE) AS vigente "
    "FROM consentimientos k "
    "JOIN fincas f ON f.id = k.finca "
    "JOIN cuentas t ON t.id = k.tercero ")


class NuevoConsentimiento(BaseModel):
    finca: int = Field(gt=0)
    tercero: int = Field(gt=0)
    vence: datetime.date


class CambioConsentimiento(BaseModel):
    vence: datetime.date | None = None
    revocar: bool = False

    @model_validator(mode="after")
    def _algo_cambia(self):
        if self.revocar and self.vence:
            raise ValueError("revocar va solo: no se extiende y se revoca a la vez")
        if not (self.revocar or self.vence):
            raise ValueError("no hay nada que cambiar")
        return self


def _atributos(fila: dict) -> dict:
    # C8: el dueno de la finca del consentimiento.
    return {"finca.propietario_id": str(fila["propietario"])}


def _json(fila: dict) -> dict:
    return {
        "id": fila["id"],
        "finca": fila["finca"],
        "finca_nombre": fila["finca_nombre"],
        "tercero": fila["tercero"],
        "tercero_usuario": fila["tercero_usuario"],
        "otorgado_por": fila["otorgado_por"],
        "vence": fila["vence"].isoformat(),
        "otorgado_en": fila["otorgado_en"].isoformat(),
        "revocado_en": (fila["revocado_en"].isoformat()
                        if fila["revocado_en"] else None),
        "vigente": fila["vigente"],
    }


def _uno(cur, consentimiento_id: int, bloquear: bool = False) -> dict | None:
    cur.execute(SELECT_CONSENTIMIENTO + "WHERE k.id = %s" +
                (" FOR UPDATE OF k" if bloquear else ""), (consentimiento_id,))
    return cur.fetchone()


def _exigir_vence(vence: datetime.date) -> None:
    hoy = datetime.date.today()
    if vence <= hoy:
        raise ErrorAPI(422, "vence_en_el_pasado",
                       "La fecha de fin tiene que ser posterior a hoy.")
    if (vence - hoy).days > MAXIMO_DIAS:
        raise ErrorAPI(422, "vence_muy_lejos",
                       "Una autorización dura como máximo tres años")


@router.get("/consentimientos")
def listar_consentimientos(sesion: SesionCompleta,
                           finca: int | None = Query(default=None, gt=0),
                           solo_vigentes: bool = False) -> dict:
    with bd.transaccion() as cur:
        general = consultar(sesion, "L", "O7")
        if not general.permitido and general.condicion is None:
            autorizar(sesion, "L", "O7", objeto="O7:*")

        filtro, parametros = "", ()
        # Optimizacion, no control: el motor decide cada fila abajo.
        if not general.permitido:
            filtro += " AND f.propietario = %s"
            parametros += (sesion.cuenta,)
        if finca is not None:
            filtro += " AND k.finca = %s"
            parametros += (finca,)
        if solo_vigentes:
            filtro += " AND k.revocado_en IS NULL AND k.vence > CURRENT_DATE"
        cur.execute(SELECT_CONSENTIMIENTO + "WHERE true" + filtro +
                    " ORDER BY k.revocado_en IS NOT NULL, k.vence DESC, "
                    "k.id DESC LIMIT 500", parametros)
        visibles = [_json(f) for f in cur.fetchall()
                    if general.permitido or consultar(
                        sesion, "L", "O7", _atributos(f)).permitido]
        registrar(accion="CONSENTIMIENTOS_LISTADOS", sujeto=sesion.sujeto.id,
                  objeto="O7:*", resultado="PERMITIDO",
                  detalle={"resultados": len(visibles)})
    return {"consentimientos": visibles}


# Antes de /consentimientos/{id}: si no, "opciones" se tomaria por un id.
@router.get("/consentimientos/opciones")
def opciones(sesion: SesionCompleta) -> dict:
    """Lo que el formulario de autorizar necesita: las fincas sobre las que
    el sujeto puede otorgar y las cuentas de terceros autorizados.

    Solo para quien tiene C sobre O7. El dueno ve solo sus fincas (C8); el
    administrativo, todas. De los terceros sale solo id y usuario: nada de
    O6 ni de O9, que el dueno no tiene.
    """
    with bd.transaccion() as cur:
        general = consultar(sesion, "C", "O7")
        if not general.permitido and general.condicion is None:
            autorizar(sesion, "C", "O7", objeto="O7:opciones")
        if general.permitido:
            cur.execute("SELECT id, nombre FROM fincas ORDER BY id")
        else:
            cur.execute("SELECT id, nombre FROM fincas WHERE propietario = %s "
                        "ORDER BY id", (sesion.cuenta,))
        fincas = cur.fetchall()
        cur.execute("SELECT id, usuario FROM cuentas WHERE activa "
                    "AND rol::text = 'TERCERO_AUTORIZADO' ORDER BY usuario")
        terceros = cur.fetchall()
    return {"fincas": fincas, "terceros": terceros}


@router.get("/consentimientos/{consentimiento_id}")
def ver_consentimiento(consentimiento_id: int, sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        fila = _uno(cur, consentimiento_id)
        objeto = "O7:%d" % consentimiento_id
        if fila is None:
            inexistente(cur, sesion, "L", "O7", objeto)
        autorizar(sesion, "L", "O7", objeto=objeto, atributos=_atributos(fila))
    return _json(fila)


@router.post("/consentimientos", status_code=201)
def crear_consentimiento(datos: NuevoConsentimiento,
                         sesion: SesionCompleta) -> dict:
    exigir_reautenticacion(sesion)
    with bd.transaccion() as cur:
        cur.execute("SELECT id, propietario FROM fincas WHERE id = %s",
                    (datos.finca,))
        finca = cur.fetchone()
        objeto = "O7:nuevo"
        if finca is None:
            inexistente(cur, sesion, "C", "O7", objeto)
        # Primero el permiso: quien no puede otorgar sobre esa finca no se
        # entera de si el tercero existe.
        autorizar(sesion, "C", "O7", objeto=objeto,
                  atributos={"finca.propietario_id": finca["propietario"]})
        _exigir_vence(datos.vence)

        cur.execute("SELECT 1 FROM cuentas WHERE id = %s AND activa "
                    "AND rol::text = 'TERCERO_AUTORIZADO'", (datos.tercero,))
        if cur.fetchone() is None:
            raise ErrorAPI(422, "tercero_invalido",
                           "Solo se autoriza a cuentas activas de terceros "
                           "autorizados.")
        cur.execute("SELECT id FROM consentimientos WHERE finca = %s "
                    "AND tercero = %s AND revocado_en IS NULL "
                    "AND vence > CURRENT_DATE", (datos.finca, datos.tercero))
        otra = cur.fetchone()
        if otra is not None:
            raise ErrorAPI(409, "ya_autorizado",
                           "Ese tercero ya tiene la autorización %d vigente "
                           "sobre esa finca: extiéndala en vez de crear otra."
                           % otra["id"])

        cur.execute("INSERT INTO consentimientos (finca, tercero, otorgado_por, "
                    "vence) VALUES (%s, %s, %s, %s) RETURNING id",
                    (datos.finca, datos.tercero, finca["propietario"],
                     datos.vence))
        nuevo = cur.fetchone()["id"]
        registrar(accion="CONSENTIMIENTO_OTORGADO", sujeto=sesion.sujeto.id,
                  objeto="O7:%d" % nuevo, resultado="PERMITIDO",
                  detalle={"finca": str(datos.finca),
                           "tercero": str(datos.tercero),
                           "dueno": str(finca["propietario"]),
                           "registrado_por_rol": sesion.rol,
                           "vence": datos.vence.isoformat()})
        fila = _uno(cur, nuevo)
    return _json(fila)


@router.patch("/consentimientos/{consentimiento_id}")
def modificar_consentimiento(consentimiento_id: int,
                             datos: CambioConsentimiento,
                             sesion: SesionCompleta) -> dict:
    # Revocar protege al dueno y no pide nada mas. Extender entrega acceso
    # por mas tiempo, asi que pide lo mismo que crear.
    if not datos.revocar:
        exigir_reautenticacion(sesion)
    with bd.transaccion() as cur:
        fila = _uno(cur, consentimiento_id, bloquear=True)
        objeto = "O7:%d" % consentimiento_id
        if fila is None:
            inexistente(cur, sesion, "M", "O7", objeto)
        autorizar(sesion, "M", "O7", objeto=objeto, atributos=_atributos(fila))

        if fila["revocado_en"] is not None:
            raise ErrorAPI(409, "ya_revocado",
                           "La autorización ya fue revocada: cree una nueva.")

        if datos.revocar:
            cur.execute("UPDATE consentimientos SET revocado_en = now() "
                        "WHERE id = %s", (consentimiento_id,))
            registrar(accion="CONSENTIMIENTO_REVOCADO", sujeto=sesion.sujeto.id,
                      objeto=objeto, resultado="PERMITIDO",
                      detalle={"finca": str(fila["finca"]),
                               "tercero": str(fila["tercero"])})
        else:
            _exigir_vence(datos.vence)
            cur.execute("UPDATE consentimientos SET vence = %s WHERE id = %s",
                        (datos.vence, consentimiento_id))
            registrar(accion="CONSENTIMIENTO_MODIFICADO",
                      sujeto=sesion.sujeto.id, objeto=objeto,
                      resultado="PERMITIDO",
                      detalle={"finca": str(fila["finca"]),
                               "tercero": str(fila["tercero"]),
                               "vence_antes": fila["vence"].isoformat(),
                               "vence": datos.vence.isoformat()})
        fila = _uno(cur, consentimiento_id)
    return _json(fila)
