"""O9 Cuentas, roles y permisos. Contrato 04, persona 2.

    GET   /cuentas                          ver cuentas y roles
    POST  /cuentas                          aplicar un alta ya aprobada
    PATCH /cuentas/{id}                     aplicar un cambio de rol o una baja

    GET   /solicitudes-rol                  las solicitudes y su estado
    POST  /solicitudes-rol                  pedir un alta, un cambio o una baja
    POST  /solicitudes-rol/{id}/aprobar     Direccion General aprueba
    POST  /solicitudes-rol/{id}/rechazar    Direccion General rechaza

La matriz sobre O9:

    Direccion General          L
    Personal Administrativo    L.C10, C.C10, M.C10
    los otros seis             nada

C10 es la separacion de deberes de SR-04 y CU-03: quien crea cuentas no decide
los permisos. El administrativo solo puede tocar una cuenta si existe una
solicitud aprobada por Direccion General para ese cambio, y quien aprobo no
puede ser quien lo ejecuta. Asi nadie se da permisos a si mismo: el
administrativo no puede aprobar, y Direccion General no puede ejecutar.

El flujo, para el alta de una cuenta:

    1. PA   POST /solicitudes-rol            {"tipo": "ALTA", ...}   PENDIENTE
    2. DG   POST /solicitudes-rol/7/aprobar                          APROBADA
    3. PA   POST /cuentas {"solicitud": 7}   la cuenta nace          APLICADA

El paso 3 es el que el motor decide con C10. Sin el paso 2, el motor niega, el
intento queda en la bitacora y el administrativo recibe 403.

Las solicitudes no son un objeto de la matriz (contrato 01): son la tabla que
hace evaluable a C10. Quien las crea y quien las aprueba lo decidimos con
CU-01 y CU-03 de P1, y va en docs/P2_Desviaciones_respecto_P1.md.
"""

import re

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import bd
from app.auth import contrasenas, sesiones
from app.auth.dependencias import (SesionCompleta, SesionReautenticada,
                                   autorizar, consultar, exigir_rol)
from app.authz.Modelos_opa import ROLES
from app.bitacora import registrar
from app.errores import ErrorAPI

router = APIRouter(tags=["cuentas"])

USUARIO_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")


class NuevaSolicitud(BaseModel):
    tipo: str = Field(pattern="^(ALTA|CAMBIO_ROL|BAJA)$")
    # CAMBIO_ROL y BAJA: la cuenta que cambia
    usuario: str | None = Field(default=None, max_length=64)
    # ALTA: la cuenta que va a nacer
    usuario_nuevo: str | None = Field(default=None, max_length=32)
    nombre_nuevo: str | None = Field(default=None, min_length=3, max_length=200)
    # ALTA y CAMBIO_ROL
    rol: str | None = Field(default=None, max_length=40)
    justificacion: str = Field(min_length=5, max_length=500)


class Rechazo(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


class Aplicacion(BaseModel):
    solicitud: int


def _objeto_solicitud(solicitud_id: int | str) -> str:
    return "O9:solicitud-%s" % solicitud_id


# ---------------------------------------------------------------------------
# Solicitudes
# ---------------------------------------------------------------------------

@router.get("/solicitudes-rol")
def ver_solicitudes(sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        exigir_rol(sesion, {"PERSONAL_ADMINISTRATIVO", "DIRECCION_GENERAL"},
                   "ver solicitudes de cambio de rol", _objeto_solicitud("*"))
        cur.execute(
            "SELECT s.id, s.tipo::text AS tipo, s.estado::text AS estado, "
            "       s.rol_solicitado::text AS rol, s.usuario_nuevo, "
            "       s.cuenta_afectada, "
            "       s.nombre_nuevo, s.justificacion, s.motivo_rechazo, "
            "       s.solicitada_en, s.aprobada_en, s.aplicada_en, "
            "       s.rechazada_en, "
            "       afectada.usuario AS usuario, afectada.rol::text AS rol_actual, "
            "       pide.usuario AS solicitante, aprueba.usuario AS aprobador, "
            "       aplica.usuario AS aplicada_por "
            "FROM solicitudes_rol s "
            "JOIN cuentas pide ON pide.id = s.solicitante "
            "LEFT JOIN cuentas afectada ON afectada.id = s.cuenta_afectada "
            "LEFT JOIN cuentas aprueba ON aprueba.id = s.aprobador "
            "LEFT JOIN cuentas aplica ON aplica.id = s.aplicada_por "
            "ORDER BY s.id DESC LIMIT 200")
        filas = cur.fetchall()

    for fila in filas:
        for campo in ("solicitada_en", "aprobada_en", "aplicada_en",
                      "rechazada_en"):
            if fila[campo] is not None:
                fila[campo] = fila[campo].isoformat()
    return {"solicitudes": filas}


@router.post("/solicitudes-rol", status_code=201)
def pedir_cambio(datos: NuevaSolicitud, sesion: SesionCompleta) -> dict:
    """El administrativo registra lo que la jefatura pidio (CU-01).

    Pedir no cambia nada. La cuenta sigue igual hasta que Direccion General
    apruebe y el administrativo aplique.
    """
    if datos.tipo in ("ALTA", "CAMBIO_ROL") and datos.rol not in ROLES:
        raise ErrorAPI(422, "rol_invalido", "Ese rol no existe en la matriz.")
    if datos.tipo == "BAJA" and datos.rol is not None:
        raise ErrorAPI(422, "rol_sobra", "Una baja no lleva rol.")

    with bd.transaccion() as cur:
        exigir_rol(sesion, {"PERSONAL_ADMINISTRATIVO"},
                   "pedir un cambio de cuenta", _objeto_solicitud("nueva"))

        afectada = None
        if datos.tipo == "ALTA":
            usuario = (datos.usuario_nuevo or "").strip().lower()
            if not USUARIO_VALIDO.match(usuario) or not datos.nombre_nuevo:
                raise ErrorAPI(422, "datos_de_alta",
                               "El alta lleva usuario (minúsculas, números, "
                               "punto o guion) y nombre.")
            cur.execute("SELECT 1 FROM cuentas WHERE usuario = %s", (usuario,))
            if cur.fetchone() is not None:
                raise ErrorAPI(409, "usuario_ocupado", "Ese usuario ya existe.")
        else:
            cur.execute("SELECT id, rol::text AS rol, activa FROM cuentas "
                        "WHERE usuario = %s", (datos.usuario,))
            afectada = cur.fetchone()
            if afectada is None:
                raise ErrorAPI(404, "cuenta_inexistente",
                               "No existe una cuenta con ese usuario.")
            if afectada["id"] == sesion.cuenta:
                # CU-03. La base tambien lo impide (nadie_pide_para_si).
                raise ErrorAPI(422, "para_si_mismo",
                               "Nadie puede pedir cambios sobre su propia cuenta.")
            if not afectada["activa"]:
                raise ErrorAPI(409, "cuenta_inactiva",
                               "Esa cuenta ya está dada de baja.")
            if datos.tipo == "CAMBIO_ROL" and datos.rol == afectada["rol"]:
                raise ErrorAPI(422, "mismo_rol", "La cuenta ya tiene ese rol.")

        cur.execute(
            "INSERT INTO solicitudes_rol (tipo, cuenta_afectada, rol_solicitado, "
            " solicitante, usuario_nuevo, nombre_nuevo, justificacion) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (datos.tipo, afectada["id"] if afectada else None,
             datos.rol if datos.tipo != "BAJA" else None, sesion.cuenta,
             (datos.usuario_nuevo or "").strip().lower() or None
             if datos.tipo == "ALTA" else None,
             datos.nombre_nuevo if datos.tipo == "ALTA" else None,
             datos.justificacion))
        solicitud = cur.fetchone()["id"]
        registrar(accion="SOLICITUD_ROL_CREADA", sujeto=sesion.sujeto.id,
                  objeto=_objeto_solicitud(solicitud), resultado="PERMITIDO",
                  detalle={"tipo": datos.tipo, "rol": datos.rol,
                           "cuenta": afectada["id"] if afectada else None})

    return {"solicitud": solicitud, "estado": "PENDIENTE"}


def _solicitud_para_resolver(cur, solicitud_id: int, sesion) -> dict:
    cur.execute("SELECT id, estado::text AS estado, solicitante, cuenta_afectada "
                "FROM solicitudes_rol WHERE id = %s FOR UPDATE", (solicitud_id,))
    fila = cur.fetchone()
    if fila is None:
        raise ErrorAPI(404, "no_existe")
    if fila["estado"] != "PENDIENTE":
        raise ErrorAPI(409, "ya_resuelta", "Esa solicitud ya fue resuelta.")
    if sesion.cuenta in (fila["solicitante"], fila["cuenta_afectada"]):
        # Contradice CU-03 aunque el rol sea el correcto. Es un intento que
        # vale la pena dejar en la bitacora.
        registrar(accion="ACCESO_DENEGADO", sujeto=sesion.sujeto.id,
                  objeto=_objeto_solicitud(solicitud_id), resultado="DENEGADO",
                  motivo="CU-03: nadie resuelve una solicitud propia o sobre "
                         "su propia cuenta")
        raise bd.Denegado(None)
    return fila


@router.post("/solicitudes-rol/{solicitud_id}/aprobar")
def aprobar_cambio(solicitud_id: int, sesion: SesionReautenticada) -> dict:
    """Direccion General aprueba. Pide reautenticacion (Tabla 7.1 de P1)."""
    with bd.transaccion() as cur:
        exigir_rol(sesion, {"DIRECCION_GENERAL"}, "aprobar un cambio de cuenta",
                   _objeto_solicitud(solicitud_id))
        _solicitud_para_resolver(cur, solicitud_id, sesion)
        cur.execute("UPDATE solicitudes_rol SET estado = 'APROBADA', "
                    "aprobador = %s, aprobada_en = now() WHERE id = %s",
                    (sesion.cuenta, solicitud_id))
        registrar(accion="SOLICITUD_ROL_APROBADA", sujeto=sesion.sujeto.id,
                  objeto=_objeto_solicitud(solicitud_id), resultado="PERMITIDO")
    return {"solicitud": solicitud_id, "estado": "APROBADA"}


@router.post("/solicitudes-rol/{solicitud_id}/rechazar")
def rechazar_cambio(solicitud_id: int, datos: Rechazo,
                    sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        exigir_rol(sesion, {"DIRECCION_GENERAL"}, "rechazar un cambio de cuenta",
                   _objeto_solicitud(solicitud_id))
        _solicitud_para_resolver(cur, solicitud_id, sesion)
        cur.execute("UPDATE solicitudes_rol SET estado = 'RECHAZADA', "
                    "rechazada_en = now(), motivo_rechazo = %s WHERE id = %s",
                    (datos.motivo, solicitud_id))
        registrar(accion="SOLICITUD_ROL_RECHAZADA", sujeto=sesion.sujeto.id,
                  objeto=_objeto_solicitud(solicitud_id), resultado="PERMITIDO")
    return {"solicitud": solicitud_id, "estado": "RECHAZADA"}


# ---------------------------------------------------------------------------
# Cuentas
# ---------------------------------------------------------------------------

def _atributos_c10(solicitud: dict | None) -> dict:
    """Lo que C10 mira: quien aprobo y con que rol, si esta aprobada.

    Si la solicitud no existe o no esta APROBADA no se manda nada, y el motor
    niega por C10. No se decide aqui: se le deja la decision al motor para que
    el intento quede registrado con su motivo.
    """
    if solicitud is None or solicitud["estado"] != "APROBADA":
        return {}
    return {"cambio.aprobador_id": str(solicitud["aprobador"]),
            "cambio.aprobador_rol": solicitud["aprobador_rol"]}


def _solicitud_para_aplicar(cur, solicitud_id: int) -> dict | None:
    cur.execute(
        "SELECT s.id, s.tipo::text AS tipo, s.estado::text AS estado, "
        "       s.cuenta_afectada, s.rol_solicitado::text AS rol, "
        "       s.usuario_nuevo, s.nombre_nuevo, s.aprobador, "
        "       a.rol::text AS aprobador_rol "
        "FROM solicitudes_rol s LEFT JOIN cuentas a ON a.id = s.aprobador "
        "WHERE s.id = %s FOR UPDATE OF s",
        (solicitud_id,))
    return cur.fetchone()


@router.get("/cuentas")
def ver_cuentas(sesion: SesionCompleta) -> dict:
    """L sobre O9.

    Direccion General ve todas. El administrativo tiene L.C10: ve una cuenta
    solo cuando tiene un cambio aprobado por Direccion General pendiente de
    aplicar, que es justo cuando la necesita ver. Es la lectura literal de la
    matriz: sin aprobacion previa, el administrativo no lee cuentas.
    """
    with bd.transaccion() as cur:
        general = consultar(sesion, "L", "O9")
        if not general.permitido and general.condicion is None:
            autorizar(sesion, "L", "O9", objeto="O9:*")

        cur.execute(
            "SELECT c.id, c.usuario, c.nombre, c.rol::text AS rol, c.activa, "
            "       c.creada_en, c.desactivada_en, "
            "       (c.bloqueada_hasta IS NOT NULL AND c.bloqueada_hasta > now()) "
            "         AS bloqueada, "
            "       coalesce(cr.totp_activo, false) AS segundo_factor, "
            "       s.id AS solicitud, s.tipo::text AS tipo, "
            "       s.estado::text AS estado, s.aprobador, "
            "       s.rol_solicitado::text AS rol_solicitado, "
            "       a.rol::text AS aprobador_rol "
            "FROM cuentas c "
            "LEFT JOIN credenciales cr ON cr.cuenta = c.id "
            "LEFT JOIN solicitudes_rol s "
            "       ON s.cuenta_afectada = c.id AND s.estado = 'APROBADA' "
            "LEFT JOIN cuentas a ON a.id = s.aprobador "
            "ORDER BY c.id")
        filas = cur.fetchall()

        visibles = []
        for fila in filas:
            if not general.permitido and not consultar(
                    sesion, "L", "O9", _atributos_c10(fila)).permitido:
                continue
            visibles.append({
                "id": fila["id"], "usuario": fila["usuario"],
                "nombre": fila["nombre"], "rol": fila["rol"],
                "activa": fila["activa"], "bloqueada": fila["bloqueada"],
                "segundo_factor": fila["segundo_factor"],
                "creada_en": fila["creada_en"].isoformat(),
                "solicitud_aprobada": (
                    {"id": fila["solicitud"], "tipo": fila["tipo"],
                     "rol": fila["rol_solicitado"]}
                    if fila["solicitud"] else None),
            })

        registrar(accion="CUENTAS_CONSULTADAS", sujeto=sesion.sujeto.id,
                  objeto="O9:*", resultado="PERMITIDO",
                  detalle={"resultados": len(visibles)})

    # Una cuenta con dos solicitudes aprobadas sale dos veces del JOIN.
    unicas = {c["id"]: c for c in visibles}
    return {"cuentas": list(unicas.values())}


@router.post("/cuentas", status_code=201)
def crear_cuenta(datos: Aplicacion, sesion: SesionReautenticada) -> dict:
    """C sobre O9, con C10. Aplica un alta que Direccion General aprobo.

    La cuenta nace con una clave temporal aleatoria que se devuelve UNA vez,
    para entregarsela a la persona. Nace con debe_cambiar: hasta que la cambie,
    la sesion no sirve para nada mas. Asi quien la creo no puede usarla.
    """
    with bd.transaccion() as cur:
        solicitud = _solicitud_para_aplicar(cur, datos.solicitud)
        autorizar(sesion, "C", "O9", objeto="O9:nueva",
                  atributos=_atributos_c10(solicitud))

        if solicitud["tipo"] != "ALTA":
            raise ErrorAPI(422, "no_es_alta",
                           "Esa solicitud no es de alta. Use PATCH /cuentas/{id}.")
        cur.execute("SELECT 1 FROM cuentas WHERE usuario = %s",
                    (solicitud["usuario_nuevo"],))
        if cur.fetchone() is not None:
            raise ErrorAPI(409, "usuario_ocupado", "Ese usuario ya existe.")

        cur.execute(
            "INSERT INTO cuentas (usuario, nombre, rol) VALUES (%s, %s, %s) "
            "RETURNING id",
            (solicitud["usuario_nuevo"], solicitud["nombre_nuevo"],
             solicitud["rol"]))
        cuenta = cur.fetchone()["id"]

        temporal = contrasenas.generar_temporal()
        cur.execute(
            "INSERT INTO credenciales (cuenta, hash_argon2, debe_cambiar) "
            "VALUES (%s, %s, true)",
            (cuenta, contrasenas.hashear(temporal)))

        cur.execute(
            "UPDATE solicitudes_rol SET estado = 'APLICADA', aplicada_por = %s, "
            "aplicada_en = now(), cuenta_afectada = %s WHERE id = %s",
            (sesion.cuenta, cuenta, solicitud["id"]))

        registrar(accion="CUENTA_CREADA", sujeto=sesion.sujeto.id,
                  objeto="O9:%d" % cuenta, resultado="PERMITIDO",
                  detalle={"solicitud": solicitud["id"], "rol": solicitud["rol"],
                           "aprobador": str(solicitud["aprobador"])})

    return {"cuenta": cuenta, "usuario": solicitud["usuario_nuevo"],
            "rol": solicitud["rol"], "clave_temporal": temporal}


@router.patch("/cuentas/{cuenta_id}")
def cambiar_cuenta(cuenta_id: int, datos: Aplicacion,
                   sesion: SesionReautenticada) -> dict:
    """M sobre O9, con C10. Aplica un cambio de rol o una baja aprobados.

    En los dos casos se cierran todas las sesiones de la cuenta en el mismo
    instante (SE-01, CU-11): la persona tiene que volver a entrar, y al entrar
    ya tiene el rol nuevo, o no entra.

    En un cambio de rol se revocan tambien sus asignaciones de zona (CU-10:
    "primero se revoca y despues se asigna"). Si el rol nuevo necesita zonas,
    Direccion de Certificacion se las asigna de nuevo; nada se arrastra del
    puesto anterior.
    """
    with bd.transaccion() as cur:
        solicitud = _solicitud_para_aplicar(cur, datos.solicitud)
        if solicitud is not None and solicitud["cuenta_afectada"] != cuenta_id:
            # Una aprobacion para otra cuenta no sirve para esta.
            solicitud = None
        autorizar(sesion, "M", "O9", objeto="O9:%d" % cuenta_id,
                  atributos=_atributos_c10(solicitud))

        if solicitud["tipo"] not in ("CAMBIO_ROL", "BAJA"):
            raise ErrorAPI(422, "no_es_cambio",
                           "Esa solicitud es de alta. Use POST /cuentas.")

        cur.execute("SELECT rol::text AS rol, activa FROM cuentas "
                    "WHERE id = %s FOR UPDATE", (cuenta_id,))
        actual = cur.fetchone()
        if actual is None:
            raise ErrorAPI(404, "no_existe")
        if not actual["activa"]:
            raise ErrorAPI(409, "cuenta_inactiva", "Esa cuenta ya está de baja.")

        cur.execute("UPDATE asignaciones_zona SET revocada_en = now() "
                    "WHERE sujeto = %s AND revocada_en IS NULL", (cuenta_id,))
        revocadas = cur.rowcount

        if solicitud["tipo"] == "CAMBIO_ROL":
            cur.execute("UPDATE cuentas SET rol = %s WHERE id = %s",
                        (solicitud["rol"], cuenta_id))
            accion = "CUENTA_ROL_CAMBIADO"
        else:
            cur.execute("UPDATE cuentas SET activa = false, "
                        "desactivada_en = now() WHERE id = %s", (cuenta_id,))
            accion = "CUENTA_DESACTIVADA"

        cerradas = sesiones.cerrar_todas(cur, cuenta_id)
        cur.execute(
            "UPDATE solicitudes_rol SET estado = 'APLICADA', aplicada_por = %s, "
            "aplicada_en = now() WHERE id = %s",
            (sesion.cuenta, solicitud["id"]))

        registrar(accion=accion, sujeto=sesion.sujeto.id,
                  objeto="O9:%d" % cuenta_id, resultado="PERMITIDO",
                  detalle={"solicitud": solicitud["id"],
                           "rol_anterior": actual["rol"],
                           "rol_nuevo": solicitud["rol"],
                           "aprobador": str(solicitud["aprobador"]),
                           "sesiones_cerradas": cerradas,
                           "asignaciones_revocadas": revocadas})

    return {"cuenta": cuenta_id, "aplicada": solicitud["tipo"],
            "sesiones_cerradas": cerradas}
