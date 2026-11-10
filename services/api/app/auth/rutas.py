"""Autenticacion y credenciales propias (O10). Contrato 04, persona 2.

    POST  /auth/entrar           contrasena -> sesion nueva
    POST  /auth/salir            cierra la sesion
    GET   /auth/sesion           quien soy, para que el borde dibuje
    POST  /auth/totp/activar     alta del segundo factor, con QR
    POST  /auth/totp/verificar   codigo de seis digitos, o de recuperacion
    POST  /auth/reautenticar     contrasena otra vez antes de algo grave
    PATCH /credenciales          cambiar la propia contrasena (O10, M)

No existe GET /credenciales, y no es un olvido: en la matriz los ocho roles
tienen M sobre O10 y ninguno tiene L. Las credenciales se cambian, no se
consultan, ni siquiera Direccion General.

Un detalle que se repite en todo el archivo: cuando algo falla por una clave o
un codigo equivocado, la respuesta de error se lanza DESPUES de cerrar la
transaccion. Si se lanzara adentro, bd.transaccion() revertiria tambien el
contador de intentos fallidos, y el bloqueo de RC-01 no avanzaria nunca.
"""

import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import bd, config
from app.auth import contrasenas, sesiones, totp
from app.auth.dependencias import (SesionValida, SesionVerificada, autorizar)
from app.bitacora import registrar
from app.errores import ErrorAPI

router = APIRouter(tags=["autenticacion"])


# ---------------------------------------------------------------------------
# Cuerpos de las peticiones
# ---------------------------------------------------------------------------
# Topes de largo en todos los campos: validar entradas (§2.3.5) empieza por no
# aceptar un megabyte donde se espera un nombre de usuario.

class Entrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=64)
    clave: str = Field(min_length=1, max_length=1024)


class Codigo(BaseModel):
    codigo: str | None = Field(default=None, max_length=16)
    codigo_recuperacion: str | None = Field(default=None, max_length=32)


class Reautenticacion(BaseModel):
    clave: str = Field(min_length=1, max_length=1024)
    codigo: str | None = Field(default=None, max_length=16)


class CambioDeClave(BaseModel):
    clave_actual: str = Field(min_length=1, max_length=1024)
    clave_nueva: str = Field(min_length=1, max_length=1024)


# ---------------------------------------------------------------------------
# RC-01: intentos fallidos
# ---------------------------------------------------------------------------

def _segundos_de_espera(intentos: int) -> int | None:
    """Cuanto queda bloqueada la cuenta despues de este intento fallido.

    RC-01: "tras 5 intentos fallidos la espera aumenta; tras 10, bloqueo de 30
    minutos". Del quinto al noveno la espera se duplica: 15 s, 30 s, 1 min,
    2 min, 4 min. Con eso, probar contrasenas a mano deja de servir mucho
    antes del bloqueo largo, y una persona que se equivoca cinco veces espera
    quince segundos, no media hora.
    """
    if intentos >= config.INTENTOS_BLOQUEO:
        return config.BLOQUEO_MINUTOS * 60
    if intentos >= config.INTENTOS_ESPERA:
        return 15 * 2 ** (intentos - config.INTENTOS_ESPERA)
    return None


def _contar_fallo(cur, cuenta: int, intentos_previos: int, motivo: str) -> bool:
    """Suma un intento fallido, bloquea si toca y lo registra. Dice si bloqueo."""
    intentos = intentos_previos + 1
    espera = _segundos_de_espera(intentos)
    cur.execute(
        "UPDATE cuentas SET intentos_fallidos = %s, "
        "bloqueada_hasta = CASE WHEN %s::int IS NULL THEN NULL "
        "                       ELSE now() + make_interval(secs => %s::int) END "
        "WHERE id = %s",
        (intentos, espera, espera, cuenta),
    )
    registrar(accion="AUTENTICACION_FALLIDA", sujeto=str(cuenta),
              objeto="O10:%d" % cuenta, resultado="DENEGADO",
              motivo="%s (intento %d)" % (motivo, intentos))

    bloqueo_largo = intentos >= config.INTENTOS_BLOQUEO
    if bloqueo_largo:
        # "Aviso al titular": no hay correo en este sistema, asi que el aviso
        # es este evento y el contador que ve la persona al volver a entrar.
        registrar(accion="CUENTA_BLOQUEADA", sujeto=str(cuenta),
                  objeto="O10:%d" % cuenta, resultado="DENEGADO",
                  motivo="RC-01: %d intentos fallidos, bloqueo de %d minutos"
                  % (intentos, config.BLOQUEO_MINUTOS))
    return bloqueo_largo


def _reiniciar_intentos(cur, cuenta: int) -> None:
    cur.execute("UPDATE cuentas SET intentos_fallidos = 0, "
                "bloqueada_hasta = NULL WHERE id = %s", (cuenta,))


def _cuenta_para_verificar(cur, cuenta: int) -> dict:
    """La cuenta y su credencial, bloqueadas para el resto de la transaccion.

    FOR UPDATE: dos intentos simultaneos no pueden leer el mismo contador y
    escribir los dos "intento 3". Sin esto, un atacante en paralelo esquiva
    el bloqueo.
    """
    cur.execute(
        "SELECT c.id, c.usuario, c.nombre, c.rol::text AS rol, c.activa, "
        "       c.intentos_fallidos, c.bloqueada_hasta, now() AS ahora, "
        "       cr.hash_argon2, cr.totp_secreto, cr.totp_activo, "
        "       cr.totp_ultimo_paso, cr.codigos_recuperacion, cr.debe_cambiar "
        "FROM cuentas c LEFT JOIN credenciales cr ON cr.cuenta = c.id "
        "WHERE c.id = %s FOR UPDATE OF c",
        (cuenta,),
    )
    return cur.fetchone()


def _bloqueada(fila: dict) -> bool:
    return fila["bloqueada_hasta"] is not None and fila["bloqueada_hasta"] > fila["ahora"]


def _siguiente_paso(totp_activo: bool, requerido: bool, verificada: bool,
                    debe_cambiar: bool) -> str:
    """Que tiene que hacer el borde despues: una sola palabra."""
    if not verificada:
        return "verificar_totp" if totp_activo else "activar_totp"
    if debe_cambiar:
        return "cambiar_clave"
    return "listo"


# ---------------------------------------------------------------------------
# Entrar y salir
# ---------------------------------------------------------------------------

@router.post("/auth/entrar")
def entrar(datos: Entrada) -> dict:
    """Verifica la contrasena contra el hash Argon2id y abre una sesion.

    El error es siempre el mismo, "credenciales_invalidas", exista o no el
    usuario, este bloqueado o desactivado. Decir "ese usuario no existe" o "su
    cuenta esta bloqueada" le confirma a quien prueba que la cuenta existe.
    Lo que paso de verdad queda en la bitacora.
    """
    resultado = None

    with bd.transaccion() as cur:
        cur.execute("SELECT id FROM cuentas WHERE usuario = %s", (datos.usuario,))
        encontrada = cur.fetchone()

        if encontrada is None:
            # Mismo trabajo que con un usuario real, para que el tiempo de
            # respuesta no delate cuales existen.
            contrasenas.verificar(contrasenas.hash_senuelo(), datos.clave)
            # El usuario escrito no va al evento: a veces es la contrasena
            # tecleada en el campo equivocado.
            registrar(accion="AUTENTICACION_FALLIDA", sujeto="ANONIMO",
                      objeto="O10:-", resultado="DENEGADO",
                      motivo="usuario inexistente")
        else:
            fila = _cuenta_para_verificar(cur, encontrada["id"])
            cuenta = fila["id"]
            hash_guardado = fila["hash_argon2"] or contrasenas.hash_senuelo()

            if _bloqueada(fila):
                contrasenas.verificar(contrasenas.hash_senuelo(), datos.clave)
                registrar(accion="AUTENTICACION_FALLIDA", sujeto=str(cuenta),
                          objeto="O10:%d" % cuenta, resultado="DENEGADO",
                          motivo="cuenta en espera o bloqueada (RC-01)")

            elif not contrasenas.verificar(hash_guardado, datos.clave) \
                    or fila["hash_argon2"] is None:
                _contar_fallo(cur, cuenta, fila["intentos_fallidos"],
                              "contrasena incorrecta")

            elif not fila["activa"]:
                registrar(accion="AUTENTICACION_FALLIDA", sujeto=str(cuenta),
                          objeto="O10:%d" % cuenta, resultado="DENEGADO",
                          motivo="cuenta desactivada (CU-11)")

            else:
                previos = fila["intentos_fallidos"]
                _reiniciar_intentos(cur, cuenta)

                # Si los parametros de Argon2 subieron desde que se guardo
                # este hash, se rehace ahora que se tiene la clave en mano.
                if contrasenas.necesita_rehash(fila["hash_argon2"]):
                    cur.execute("UPDATE credenciales SET hash_argon2 = %s "
                                "WHERE cuenta = %s",
                                (contrasenas.hashear(datos.clave), cuenta))

                requerido = sesiones.segundo_factor_requerido(
                    fila["rol"], fila["totp_activo"])
                token, expira = sesiones.crear(cur, cuenta,
                                               segundo_factor_ok=not requerido)
                registrar(accion="SESION_INICIADA", sujeto=str(cuenta),
                          objeto="O10:%d" % cuenta, resultado="PERMITIDO",
                          detalle={"rol": fila["rol"],
                                   "segundo_factor": ("pendiente" if requerido
                                                      else "no requerido"),
                                   "intentos_fallidos_previos": previos})
                resultado = {
                    "token": token,
                    "expira_en": expira.isoformat(),
                    "siguiente": _siguiente_paso(
                        fila["totp_activo"], requerido, not requerido,
                        fila["debe_cambiar"]),
                    # Lo mas parecido a "avisar al titular" (RC-01) que hay
                    # sin correo: al entrar ve que alguien estuvo probando.
                    "intentos_fallidos_previos": previos,
                }

    if resultado is None:
        raise ErrorAPI(401, "credenciales_invalidas",
                       "Usuario o contraseña incorrectos, o la cuenta está "
                       "temporalmente bloqueada.")
    return resultado


@router.post("/auth/salir")
def salir(sesion: SesionValida) -> dict:
    with bd.transaccion() as cur:
        sesiones.cerrar(cur, sesion.id)
        registrar(accion="SESION_CERRADA", sujeto=sesion.sujeto.id,
                  objeto="O10:%d" % sesion.cuenta, resultado="PERMITIDO")
    return {"cerrada": True}


@router.get("/auth/sesion")
def ver_sesion(sesion: SesionValida) -> dict:
    """Lo que el borde necesita para dibujar: quien es y que le falta.

    Sin el token ni nada de la credencial. El borde ya tiene el token.
    """
    ahora = datetime.datetime.now(datetime.timezone.utc)
    return {
        "cuenta": sesion.cuenta,
        "usuario": sesion.usuario,
        "nombre": sesion.nombre,
        "rol": sesion.rol,
        "zonas": list(sesion.zonas),
        "expira_en": sesion.expira_en.isoformat(),
        "segundo_factor": {
            "requerido": sesion.segundo_factor_requerido,
            "activo": sesion.totp_activo,
            "verificado": sesion.verificada,
        },
        "debe_cambiar": sesion.debe_cambiar,
        "reautenticada": sesion.reautenticada_hace_poco(ahora),
        "siguiente": _siguiente_paso(sesion.totp_activo,
                                     sesion.segundo_factor_requerido,
                                     sesion.verificada, sesion.debe_cambiar),
    }


# ---------------------------------------------------------------------------
# Segundo factor
# ---------------------------------------------------------------------------

@router.post("/auth/totp/activar")
def activar_totp(sesion: SesionValida) -> dict:
    """Genera el secreto y devuelve el QR. Queda inactivo hasta el primer codigo.

    Si ya esta activo se niega: cambiar el segundo factor de alguien con solo
    su contrasena seria saltarse el segundo factor.
    """
    if sesion.totp_activo:
        raise ErrorAPI(409, "totp_ya_activo")

    secreto = totp.nuevo_secreto()
    with bd.transaccion() as cur:
        cur.execute(
            "UPDATE credenciales SET totp_secreto = %s, totp_activo = false, "
            "totp_ultimo_paso = NULL WHERE cuenta = %s",
            (totp.cifrar_secreto(secreto, sesion.cuenta), sesion.cuenta))
        registrar(accion="TOTP_ALTA_INICIADA", sujeto=sesion.sujeto.id,
                  objeto="O10:%d" % sesion.cuenta, resultado="PERMITIDO")

    direccion = totp.uri(secreto, sesion.usuario)
    return {
        "otpauth": direccion,
        "qr": totp.qr_svg(direccion),
        # Para escribirlo a mano si la camara no lee el QR.
        "secreto": secreto,
    }


@router.post("/auth/totp/verificar")
def verificar_totp(datos: Codigo, sesion: SesionValida) -> dict:
    """Comprueba el codigo y marca la sesion como verificada.

    La primera vez que funciona tambien activa el factor y entrega los ocho
    codigos de recuperacion (RC-02), que no se vuelven a mostrar.
    """
    if not datos.codigo and not datos.codigo_recuperacion:
        raise ErrorAPI(422, "falta_codigo")

    respuesta = None
    cerro_sesion = False

    with bd.transaccion() as cur:
        fila = _cuenta_para_verificar(cur, sesion.cuenta)
        cuenta = sesion.cuenta

        if _bloqueada(fila):
            registrar(accion="AUTENTICACION_FALLIDA", sujeto=str(cuenta),
                      objeto="O10:%d" % cuenta, resultado="DENEGADO",
                      motivo="segundo factor con la cuenta bloqueada (RC-01)")

        elif datos.codigo_recuperacion:
            huella = totp.huella_recuperacion(datos.codigo_recuperacion)
            restantes = list(fila["codigos_recuperacion"] or [])
            if fila["totp_activo"] and huella in restantes:
                restantes.remove(huella)
                cur.execute("UPDATE credenciales SET codigos_recuperacion = %s "
                            "WHERE cuenta = %s", (restantes, cuenta))
                _reiniciar_intentos(cur, cuenta)
                sesiones.marcar_segundo_factor(cur, sesion.id)
                # RC-04: toda recuperacion cierra las sesiones anteriores.
                cerradas = sesiones.cerrar_todas(cur, cuenta, salvo=sesion.id)
                registrar(accion="CODIGO_RECUPERACION_USADO", sujeto=str(cuenta),
                          objeto="O10:%d" % cuenta, resultado="PERMITIDO",
                          detalle={"restantes": len(restantes),
                                   "sesiones_cerradas": cerradas})
                respuesta = {"verificado": True, "restantes": len(restantes)}
            else:
                cerro_sesion = _contar_fallo(cur, cuenta, fila["intentos_fallidos"],
                                             "codigo de recuperacion invalido")

        elif fila["totp_secreto"] is None:
            raise ErrorAPI(409, "totp_sin_activar")

        else:
            secreto = totp.descifrar_secreto(fila["totp_secreto"], cuenta)
            paso = totp.verificar(secreto, datos.codigo, fila["totp_ultimo_paso"])
            if paso is None:
                cerro_sesion = _contar_fallo(cur, cuenta, fila["intentos_fallidos"],
                                             "codigo TOTP incorrecto o repetido")
            else:
                cur.execute("UPDATE credenciales SET totp_ultimo_paso = %s "
                            "WHERE cuenta = %s", (paso, cuenta))
                _reiniciar_intentos(cur, cuenta)
                sesiones.marcar_segundo_factor(cur, sesion.id)
                respuesta = {"verificado": True}

                if not fila["totp_activo"]:
                    codigos = totp.codigos_recuperacion()
                    cur.execute(
                        "UPDATE credenciales SET totp_activo = true, "
                        "codigos_recuperacion = %s WHERE cuenta = %s",
                        ([totp.huella_recuperacion(c) for c in codigos], cuenta))
                    registrar(accion="TOTP_ACTIVADO", sujeto=str(cuenta),
                              objeto="O10:%d" % cuenta, resultado="PERMITIDO")
                    respuesta["codigos_recuperacion"] = codigos
                else:
                    registrar(accion="SEGUNDO_FACTOR_VERIFICADO",
                              sujeto=str(cuenta), objeto="O10:%d" % cuenta,
                              resultado="PERMITIDO")

        if respuesta is None and cerro_sesion:
            # Al llegar al bloqueo largo, la sesion a medio verificar tampoco
            # sirve: quien probaba codigos tiene que volver a la contrasena.
            sesiones.cerrar(cur, sesion.id)

    if respuesta is None:
        raise ErrorAPI(401, "codigo_invalido",
                       "El código no es válido o ya se usó.")
    respuesta["siguiente"] = "cambiar_clave" if fila["debe_cambiar"] else "listo"
    return respuesta


# ---------------------------------------------------------------------------
# Reautenticacion
# ---------------------------------------------------------------------------

@router.post("/auth/reautenticar")
def reautenticar(datos: Reautenticacion, sesion: SesionVerificada) -> dict:
    """Contrasena, y codigo si tiene TOTP, antes de una accion grave.

    Vale config.REAUTENTICACION_MINUTOS minutos y solo para esta sesion. Los
    fallos cuentan para el bloqueo igual que al entrar: si no, este endpoint
    seria una forma de probar contrasenas sin limite desde una sesion robada.
    """
    exito = False
    with bd.transaccion() as cur:
        fila = _cuenta_para_verificar(cur, sesion.cuenta)
        cuenta = sesion.cuenta
        bloqueo = False

        if _bloqueada(fila):
            registrar(accion="AUTENTICACION_FALLIDA", sujeto=str(cuenta),
                      objeto="O10:%d" % cuenta, resultado="DENEGADO",
                      motivo="reautenticacion con la cuenta bloqueada (RC-01)")
        elif not contrasenas.verificar(fila["hash_argon2"] or
                                       contrasenas.hash_senuelo(), datos.clave):
            bloqueo = _contar_fallo(cur, cuenta, fila["intentos_fallidos"],
                                    "reautenticacion: contrasena incorrecta")
        else:
            paso = None
            if fila["totp_activo"]:
                secreto = totp.descifrar_secreto(fila["totp_secreto"], cuenta)
                paso = totp.verificar(secreto, datos.codigo or "",
                                      fila["totp_ultimo_paso"])
            if fila["totp_activo"] and paso is None:
                bloqueo = _contar_fallo(cur, cuenta, fila["intentos_fallidos"],
                                        "reautenticacion: codigo TOTP incorrecto")
            else:
                if paso is not None:
                    cur.execute("UPDATE credenciales SET totp_ultimo_paso = %s "
                                "WHERE cuenta = %s", (paso, cuenta))
                _reiniciar_intentos(cur, cuenta)
                sesiones.marcar_reautenticada(cur, sesion.id)
                registrar(accion="REAUTENTICACION", sujeto=str(cuenta),
                          objeto="O10:%d" % cuenta, resultado="PERMITIDO")
                exito = True

        if bloqueo:
            sesiones.cerrar(cur, sesion.id)

    if not exito:
        raise ErrorAPI(401, "reautenticacion_fallida",
                       "La contraseña o el código no son correctos.")
    return {"reautenticada": True,
            "vigente_minutos": config.REAUTENTICACION_MINUTOS}


# ---------------------------------------------------------------------------
# O10: credenciales propias
# ---------------------------------------------------------------------------

@router.patch("/credenciales")
def cambiar_clave(datos: CambioDeClave, sesion: SesionVerificada) -> dict:
    """M sobre O10: cada quien cambia su contrasena, y solo la suya.

    No recibe ningun id: la cuenta sale de la sesion. Asi no hay forma de
    pedir el cambio de la clave de otro cambiando un numero en la peticion.

    Pide la contrasena actual (la reautenticacion que exige el contrato 04),
    valida la nueva contra CO-01 y CO-02, y cierra las demas sesiones abiertas
    de la cuenta: si la clave se cambio porque se filtro, quien la uso pierde
    el acceso en ese momento.
    """
    # Antes de abrir la transaccion: puede consultar un servicio externo
    # (CO-02) y no tiene sentido tener la fila bloqueada mientras tanto.
    fallas = contrasenas.problemas(datos.clave_nueva, sesion.usuario,
                                   sesion.nombre)
    if fallas:
        raise ErrorAPI(422, "clave_invalida", fallas[0], problemas=fallas)

    exito = False
    misma = False
    with bd.transaccion() as cur:
        autorizar(sesion, "M", "O10", objeto="O10:%d" % sesion.cuenta)
        fila = _cuenta_para_verificar(cur, sesion.cuenta)
        bloqueo = False

        if _bloqueada(fila):
            registrar(accion="AUTENTICACION_FALLIDA", sujeto=sesion.sujeto.id,
                      objeto="O10:%d" % sesion.cuenta, resultado="DENEGADO",
                      motivo="cambio de clave con la cuenta bloqueada (RC-01)")
        elif not contrasenas.verificar(fila["hash_argon2"] or
                                       contrasenas.hash_senuelo(),
                                       datos.clave_actual):
            bloqueo = _contar_fallo(cur, sesion.cuenta, fila["intentos_fallidos"],
                                    "cambio de clave: contrasena actual incorrecta")
        elif contrasenas.verificar(fila["hash_argon2"], datos.clave_nueva):
            misma = True
        else:
            cur.execute(
                "UPDATE credenciales SET hash_argon2 = %s, cambiada_en = now(), "
                "debe_cambiar = false WHERE cuenta = %s",
                (contrasenas.hashear(datos.clave_nueva), sesion.cuenta))
            _reiniciar_intentos(cur, sesion.cuenta)
            cerradas = sesiones.cerrar_todas(cur, sesion.cuenta, salvo=sesion.id)
            registrar(accion="CREDENCIAL_CAMBIADA", sujeto=sesion.sujeto.id,
                      objeto="O10:%d" % sesion.cuenta, resultado="PERMITIDO",
                      detalle={"sesiones_cerradas": cerradas,
                               "era_temporal": fila["debe_cambiar"]})
            exito = True

        if bloqueo:
            sesiones.cerrar(cur, sesion.id)

    if misma:
        raise ErrorAPI(422, "clave_invalida",
                       "La nueva tiene que ser distinta de la actual.",
                       problemas=["La nueva tiene que ser distinta de la actual."])
    if not exito:
        raise ErrorAPI(401, "clave_actual_incorrecta",
                       "La contraseña actual no es correcta.")
    return {"cambiada": True}
