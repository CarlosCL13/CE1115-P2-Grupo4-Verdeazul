"""Pantallas de identidad: entrar, segundo factor, clave, datos personales y
cuentas. Persona 2.

Estas pantallas no deciden nada. Esconder un boton es comodidad; el control
es que el backend rechaza la operacion (§2.3.2). Por eso varias pantallas
muestran el formulario aunque el rol no pueda usarlo: si alguien lo intenta,
el backend responde 403 y se dibuja la pagina de acceso denegado, que es
justo la evidencia que pide §5.1, punto 7.
"""

import urllib.parse

from fastapi import APIRouter, Form, Query, Request

from app import api
from app.web import (FalloDelBackend, comprobar_csrf, destino_seguro, ir,
                     mensaje_de, pagina, pedir, poner_cookie, quitar_cookie,
                     sesion, token)

router = APIRouter()

ROLES = (
    "DIRECCION_GENERAL", "DIRECCION_CERTIFICACION", "PERSONAL_ADMINISTRATIVO",
    "TECNICO_CAMPO", "VERIFICADOR", "AUDITOR_EXTERNO", "DUENO_FINCA",
    "TERCERO_AUTORIZADO",
)

_DESPUES = {
    "listo": "/panel",
    "verificar_totp": "/segundo-factor",
    "activar_totp": "/segundo-factor/activar",
    "cambiar_clave": "/clave",
}


# ---------------------------------------------------------------------------
# Entrar y salir
# ---------------------------------------------------------------------------

@router.get("/entrar")
def entrar(request: Request):
    return pagina(request, "auth/entrar.html", datos_sesion={})


@router.post("/entrar")
def entrar_enviar(request: Request, usuario: str = Form(max_length=64),
                  clave: str = Form(max_length=1024)):
    respuesta = api.llamar("POST", "/auth/entrar",
                           json={"usuario": usuario, "clave": clave})
    if respuesta.status_code != 200:
        return pagina(request, "auth/entrar.html", estado=401, datos_sesion={},
                      error="Usuario o contraseña incorrectos, o la cuenta "
                            "está temporalmente bloqueada.")
    datos = respuesta.json()
    destino = _DESPUES.get(datos["siguiente"], "/panel")
    if datos["siguiente"] == "listo" and datos.get("intentos_fallidos_previos"):
        destino += "?intentos=%d" % int(datos["intentos_fallidos_previos"])
    salida = ir(destino)
    # Siempre un token nuevo al entrar: nunca se reutiliza la cookie anterior.
    poner_cookie(salida, datos["token"])
    return salida


@router.post("/salir")
def salir(request: Request, csrf: str = Form("")):
    comprobar_csrf(request, csrf)
    if token(request):
        api.llamar("POST", "/auth/salir", sesion=token(request))
    salida = ir("/")
    quitar_cookie(salida)
    return salida


@router.get("/panel")
def panel(request: Request, intentos: int = 0):
    datos = pedir(request, "GET", "/auth/sesion").json()
    if datos["siguiente"] != "listo":
        return ir(_DESPUES[datos["siguiente"]])
    return pagina(request, "auth/panel.html", datos_sesion=datos,
                  intentos=max(0, intentos))


# ---------------------------------------------------------------------------
# Segundo factor
# ---------------------------------------------------------------------------

@router.get("/segundo-factor")
def segundo_factor(request: Request):
    return pagina(request, "auth/segundo_factor.html")


@router.post("/segundo-factor")
def segundo_factor_enviar(request: Request, csrf: str = Form(""),
                          codigo: str = Form("", max_length=16),
                          recuperacion: str = Form("", max_length=32)):
    comprobar_csrf(request, csrf)
    cuerpo = ({"codigo_recuperacion": recuperacion} if recuperacion.strip()
              else {"codigo": codigo})
    try:
        datos = pedir(request, "POST", "/auth/totp/verificar", json=cuerpo).json()
    except FalloDelBackend as error:
        return pagina(request, "auth/segundo_factor.html", estado=error.estado,
                      error=mensaje_de(error))
    return ir(_DESPUES.get(datos.get("siguiente"), "/panel"))


@router.get("/segundo-factor/activar")
def activar(request: Request):
    return pagina(request, "auth/activar_totp.html")


@router.post("/segundo-factor/activar")
def activar_generar(request: Request, csrf: str = Form("")):
    """Genera el secreto. POST y no GET: cambia estado en el backend."""
    comprobar_csrf(request, csrf)
    try:
        alta = pedir(request, "POST", "/auth/totp/activar").json()
    except FalloDelBackend as error:
        return pagina(request, "auth/activar_totp.html", estado=error.estado,
                      error=mensaje_de(error))
    return pagina(request, "auth/activar_totp.html", alta=alta)


@router.post("/segundo-factor/confirmar")
def activar_confirmar(request: Request, csrf: str = Form(""),
                      codigo: str = Form("", max_length=16)):
    comprobar_csrf(request, csrf)
    try:
        datos = pedir(request, "POST", "/auth/totp/verificar",
                      json={"codigo": codigo}).json()
    except FalloDelBackend as error:
        return pagina(request, "auth/activar_totp.html", estado=error.estado,
                      error=mensaje_de(error) + " Generá el código QR de nuevo.")
    # RC-02: los codigos de recuperacion se muestran esta unica vez.
    return pagina(request, "auth/codigos.html",
                  codigos=datos.get("codigos_recuperacion", []),
                  siguiente=_DESPUES.get(datos.get("siguiente"), "/panel"))


# ---------------------------------------------------------------------------
# Clave y reautenticacion
# ---------------------------------------------------------------------------

@router.get("/clave")
def clave(request: Request):
    return pagina(request, "auth/clave.html")


@router.post("/clave")
def clave_enviar(request: Request, csrf: str = Form(""),
                 actual: str = Form(max_length=1024),
                 nueva: str = Form(max_length=1024),
                 repetida: str = Form(max_length=1024)):
    comprobar_csrf(request, csrf)
    if nueva != repetida:
        return pagina(request, "auth/clave.html", estado=422,
                      problemas=["Las dos contraseñas nuevas no coinciden."])
    try:
        pedir(request, "PATCH", "/credenciales",
              json={"clave_actual": actual, "clave_nueva": nueva})
    except FalloDelBackend as error:
        return pagina(request, "auth/clave.html", estado=error.estado,
                      problemas=error.cuerpo.get("problemas")
                      or [mensaje_de(error)])
    return pagina(request, "auth/clave.html", listo=True)


@router.get("/reautenticar")
def reautenticar(request: Request, siguiente: str = "/panel"):
    return pagina(request, "auth/reautenticar.html",
                  siguiente=destino_seguro(siguiente))


@router.post("/reautenticar")
def reautenticar_enviar(request: Request, csrf: str = Form(""),
                        clave: str = Form(max_length=1024),
                        codigo: str = Form("", max_length=16),
                        siguiente: str = Form("/panel")):
    comprobar_csrf(request, csrf)
    siguiente = destino_seguro(siguiente)
    cuerpo = {"clave": clave}
    if codigo.strip():
        cuerpo["codigo"] = codigo
    try:
        pedir(request, "POST", "/auth/reautenticar", json=cuerpo)
    except FalloDelBackend as error:
        return pagina(request, "auth/reautenticar.html", estado=error.estado,
                      siguiente=siguiente, error=mensaje_de(error))
    return ir(siguiente)


# ---------------------------------------------------------------------------
# O6 Datos personales
# ---------------------------------------------------------------------------

@router.get("/personas")
def personas(request: Request, cedula: str = ""):
    params = {"cedula": cedula} if cedula.strip() else None
    try:
        datos = pedir(request, "GET", "/personas", params=params).json()
    except FalloDelBackend as error:
        return pagina(request, "personas/lista.html", estado=error.estado,
                      personas=[], cedula=cedula, error=mensaje_de(error))
    return pagina(request, "personas/lista.html", personas=datos["personas"],
                  cedula=cedula)


@router.get("/personas/nueva")
def persona_nueva(request: Request):
    return pagina(request, "personas/formulario.html", persona=None)


@router.post("/personas/nueva")
def persona_nueva_enviar(request: Request, csrf: str = Form(""),
                         usuario: str = Form(max_length=64),
                         nombre_completo: str = Form(max_length=200),
                         cedula: str = Form(max_length=20),
                         telefono: str = Form("", max_length=20)):
    comprobar_csrf(request, csrf)
    cuerpo = {"usuario": usuario, "nombre_completo": nombre_completo,
              "cedula": cedula, "telefono": telefono or None}
    try:
        creada = pedir(request, "POST", "/personas", json=cuerpo).json()
    except FalloDelBackend as error:
        return pagina(request, "personas/formulario.html", estado=error.estado,
                      persona=None, valores=cuerpo, error=mensaje_de(error))
    return ir("/personas/%d" % creada["cuenta"])


@router.get("/personas/{cuenta}")
def persona(request: Request, cuenta: int):
    datos = pedir(request, "GET", "/personas/%d" % cuenta).json()
    return pagina(request, "personas/detalle.html", persona=datos)


@router.get("/personas/{cuenta}/editar")
def persona_editar(request: Request, cuenta: int):
    datos = pedir(request, "GET", "/personas/%d" % cuenta).json()
    return pagina(request, "personas/formulario.html", persona=datos,
                  valores=datos)


@router.post("/personas/{cuenta}/editar")
def persona_editar_enviar(request: Request, cuenta: int, csrf: str = Form(""),
                          nombre_completo: str = Form("", max_length=200),
                          cedula: str = Form("", max_length=20),
                          telefono: str = Form("", max_length=20)):
    comprobar_csrf(request, csrf)
    cuerpo = {"nombre_completo": nombre_completo or None,
              "cedula": cedula or None, "telefono": telefono}
    try:
        pedir(request, "PATCH", "/personas/%d" % cuenta,
              json={k: v for k, v in cuerpo.items() if v is not None})
    except FalloDelBackend as error:
        return pagina(request, "personas/formulario.html", estado=error.estado,
                      persona={"cuenta": cuenta}, valores=cuerpo,
                      error=mensaje_de(error))
    return ir("/personas/%d" % cuenta)


# ---------------------------------------------------------------------------
# O9 Cuentas y solicitudes de cambio
# ---------------------------------------------------------------------------

def _volver_con_error(error: FalloDelBackend):
    """De vuelta a la lista con el mensaje del backend, codificado y acotado."""
    return ir("/solicitudes?error=" + urllib.parse.quote(mensaje_de(error)[:200]))


@router.get("/cuentas")
def cuentas(request: Request):
    datos = pedir(request, "GET", "/cuentas").json()
    return pagina(request, "cuentas/lista.html", cuentas=datos["cuentas"])


@router.get("/solicitudes")
def solicitudes(request: Request, error: str = Query("", max_length=200)):
    datos = pedir(request, "GET", "/solicitudes-rol").json()
    return pagina(request, "cuentas/solicitudes.html",
                  solicitudes=datos["solicitudes"], roles=ROLES,
                  error=error or None)


@router.post("/solicitudes")
def solicitud_nueva(request: Request, csrf: str = Form(""),
                    tipo: str = Form(max_length=12),
                    usuario: str = Form("", max_length=64),
                    usuario_nuevo: str = Form("", max_length=32),
                    nombre_nuevo: str = Form("", max_length=200),
                    rol: str = Form("", max_length=40),
                    justificacion: str = Form("", max_length=500)):
    comprobar_csrf(request, csrf)
    cuerpo = {"tipo": tipo, "justificacion": justificacion,
              "usuario": usuario or None, "usuario_nuevo": usuario_nuevo or None,
              "nombre_nuevo": nombre_nuevo or None,
              "rol": rol if tipo != "BAJA" and rol else None}
    try:
        pedir(request, "POST", "/solicitudes-rol", json=cuerpo)
    except FalloDelBackend as error:
        datos = pedir(request, "GET", "/solicitudes-rol").json()
        return pagina(request, "cuentas/solicitudes.html", estado=error.estado,
                      solicitudes=datos["solicitudes"], roles=ROLES,
                      error=mensaje_de(error))
    return ir("/solicitudes")


@router.post("/solicitudes/{solicitud}/aprobar")
def solicitud_aprobar(request: Request, solicitud: int, csrf: str = Form("")):
    comprobar_csrf(request, csrf)
    try:
        pedir(request, "POST", "/solicitudes-rol/%d/aprobar" % solicitud,
              volver_a="/solicitudes")
    except FalloDelBackend as error:
        return _volver_con_error(error)
    return ir("/solicitudes")


@router.post("/solicitudes/{solicitud}/rechazar")
def solicitud_rechazar(request: Request, solicitud: int, csrf: str = Form(""),
                       motivo: str = Form("", max_length=500)):
    comprobar_csrf(request, csrf)
    try:
        pedir(request, "POST", "/solicitudes-rol/%d/rechazar" % solicitud,
              json={"motivo": motivo})
    except FalloDelBackend as error:
        return _volver_con_error(error)
    return ir("/solicitudes")


@router.post("/solicitudes/{solicitud}/aplicar")
def solicitud_aplicar(request: Request, solicitud: int, csrf: str = Form(""),
                      tipo: str = Form(max_length=12),
                      cuenta: int | None = Form(None)):
    """El administrativo ejecuta lo aprobado: POST /cuentas o PATCH /cuentas/{id}."""
    comprobar_csrf(request, csrf)
    try:
        if tipo == "ALTA":
            creada = pedir(request, "POST", "/cuentas",
                           json={"solicitud": solicitud},
                           volver_a="/solicitudes").json()
            # La clave temporal se muestra esta unica vez.
            return pagina(request, "cuentas/creada.html", creada=creada)
        pedir(request, "PATCH", "/cuentas/%d" % (cuenta or 0),
              json={"solicitud": solicitud}, volver_a="/solicitudes")
    except FalloDelBackend as error:
        return _volver_con_error(error)
    return ir("/cuentas")


# Para que otras paginas sepan si hay sesion sin pedirla de nuevo.
__all__ = ["router", "sesion"]
