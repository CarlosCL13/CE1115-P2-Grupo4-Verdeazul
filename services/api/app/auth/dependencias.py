"""Lo que cada endpoint del sistema usa para saber quien pregunta y si puede.

Ver contracts/05-sesion.md. Uso tipico, en cualquier modulo:

    from app import bd
    from app.auth.dependencias import SesionCompleta, autorizar

    @router.get("/fincas/{finca_id}")
    def ver_finca(finca_id: int, sesion: SesionCompleta):
        with bd.transaccion() as cur:
            cur.execute("SELECT zona, propietario FROM fincas WHERE id = %s",
                        (finca_id,))
            fila = cur.fetchone()
            ...
            autorizar(sesion, "L", "O1", objeto="O1:%d" % finca_id, atributos={
                "finca.zona": fila["zona"],
                "finca.propietario_id": str(fila["propietario"]),
            })
            ...

`autorizar` llama al motor (contrato 02). Si dice que no, anota el intento en
la bitacora y corta con 403, y la transaccion se revierte sin perder el
evento. Si dice que si, sigue. No hay forma de olvidarse de registrar la
denegacion, porque no la registra quien llama.

Tres niveles de sesion, de menos a mas exigente:

    SesionValida       el token sirve. Solo para /auth/*: salir, ver la
                       sesion y completar el segundo factor
    SesionVerificada   ademas paso el segundo factor si su rol lo exige o si
                       lo tiene activo. Para reautenticar y cambiar la clave
    SesionCompleta     ademas no tiene una clave temporal pendiente de
                       cambiar. Es la que usan todos los demas endpoints
"""

import datetime
from typing import Annotated

from fastapi import Depends, Request

from app import bd
from app.authz.Modelos_opa import Decision, Objeto
from app.authz.Servicio_opa import servicio_consulta_autorizacion
from app.auth import sesiones
from app.auth.sesiones import SesionActiva
from app.bitacora import registrar
from app.errores import ErrorAPI

# El borde lee la cookie y manda el token en esta cabecera. No va en
# Authorization porque esa la usa Cloud Run para el token de identidad de
# Google con el que el borde demuestra que puede invocar al backend (F2).
CABECERA = "X-Verdeazul-Sesion"


def sesion_valida(request: Request) -> SesionActiva:
    """La sesion del token, o 401. Corre en su propia transaccion.

    Propia a proposito: si la sesion vencio por inactividad, buscar() la
    cierra, y ese cierre tiene que quedar aunque la peticion termine en 401.
    """
    token = request.headers.get(CABECERA, "")
    with bd.transaccion() as cur:
        sesion, _motivo = sesiones.buscar(cur, token)
    if sesion is None:
        raise ErrorAPI(401, "sin_sesion")
    return sesion


def sesion_verificada(sesion: Annotated[SesionActiva, Depends(sesion_valida)]
                      ) -> SesionActiva:
    if not sesion.verificada:
        raise ErrorAPI(401, "segundo_factor_pendiente",
                       activo=sesion.totp_activo)
    return sesion


def sesion_completa(sesion: Annotated[SesionActiva, Depends(sesion_verificada)]
                    ) -> SesionActiva:
    if sesion.debe_cambiar:
        raise ErrorAPI(401, "cambio_de_clave_pendiente")
    return sesion


SesionValida = Annotated[SesionActiva, Depends(sesion_valida)]
SesionVerificada = Annotated[SesionActiva, Depends(sesion_verificada)]
SesionCompleta = Annotated[SesionActiva, Depends(sesion_completa)]


def exigir_reautenticacion(sesion: SesionActiva) -> None:
    """Para las acciones graves: aprobar, emitir, cambiar roles, abrir y cerrar.

    P1 (Tabla 7.1) vuelve a pedir el factor antes de esas acciones. El borde
    recibe 401 "reautenticacion_requerida", manda a la persona a
    /auth/reautenticar y vuelve a intentar.
    """
    ahora = datetime.datetime.now(datetime.timezone.utc)
    if not sesion.reautenticada_hace_poco(ahora):
        raise ErrorAPI(401, "reautenticacion_requerida")


def _sesion_reautenticada(sesion: SesionCompleta) -> SesionActiva:
    exigir_reautenticacion(sesion)
    return sesion


SesionReautenticada = Annotated[SesionActiva, Depends(_sesion_reautenticada)]


def consultar(sesion: SesionActiva, operacion: str, tipo: str,
              atributos: dict | None = None) -> Decision:
    """Pregunta al motor sin registrar ni cortar. Para filtrar listados.

    Un listado devuelve solo las filas que el sujeto puede ver. Las que no,
    no son intentos de acceso: el sujeto no las pidio una por una. El listado
    en si se registra con autorizar() o registrar() por quien lo arma.
    """
    return servicio_consulta_autorizacion(
        sesion.sujeto, operacion, Objeto(tipo=tipo, atributos=atributos or {}))


def autorizar(sesion: SesionActiva, operacion: str, tipo: str, *,
              objeto: str | None = None, atributos: dict | None = None
              ) -> Decision:
    """El motor decide. Si niega: bitacora, 403 y reversion.

    Tiene que llamarse dentro de `with bd.transaccion()`, porque el evento de
    denegacion se escribe con el cursor de esa transaccion y bd.transaccion()
    lo rescata cuando revierte.

    Todo `*_id` de `atributos` tiene que ir como texto (contrato 02, "Todo id
    viaja como texto"). Aqui se convierten por si acaso: un entero que se
    cuela hace que C3, C4, C5, C6 y C10 concedan de mas.
    """
    atributos = {
        clave: (str(valor) if clave.endswith("_id") and valor is not None
                else valor)
        for clave, valor in (atributos or {}).items()
    }
    decision = consultar(sesion, operacion, tipo, atributos)
    if not decision.permitido:
        registrar(
            accion="ACCESO_DENEGADO",
            sujeto=sesion.sujeto.id,
            objeto=objeto or tipo,
            resultado="DENEGADO",
            motivo=decision.motivo,
            detalle={
                "operacion": operacion,
                "rol": sesion.rol,
                "condicion": decision.condicion,
                "version_politica": decision.version_politica,
            },
        )
        raise bd.Denegado(decision)
    return decision


def exigir_rol(sesion: SesionActiva, roles: set[str] | frozenset[str],
               accion: str, objeto: str) -> None:
    """Para lo que no es una celda de la matriz, como aprobar una solicitud.

    La matriz no tiene objeto para las solicitudes de cambio de rol ni para
    las ventanas de auditoria (contrato 01). Quien puede tocarlas es una
    decision del grupo, documentada como desviacion, y se impone aqui con la
    misma regla: se niega por omision, se registra y se responde 403.
    """
    if sesion.rol in roles:
        return
    motivo = "denegado: %s solo lo puede hacer %s" % (
        accion, " o ".join(sorted(roles)))
    registrar(accion="ACCESO_DENEGADO", sujeto=sesion.sujeto.id,
              objeto=objeto, resultado="DENEGADO", motivo=motivo,
              detalle={"operacion": accion, "rol": sesion.rol})
    raise bd.Denegado(Decision(permitido=False, motivo=motivo))
