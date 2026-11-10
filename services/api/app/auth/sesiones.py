"""Sesiones: viven en la base, como prometio P1, para poder cerrarlas al instante.

Un token firmado (JWT) no se puede revocar antes de que venza: si a alguien lo
dan de baja a las 10:00 y su token vence a las 18:00, entra hasta las 18:00.
SE-01 y CU-11 piden lo contrario, "se cierran al instante al cerrar sesion,
cambiar de rol o dar de baja la cuenta". Con la sesion en la base, cerrarla es
un UPDATE y la siguiente peticion ya no pasa.

El token es opaco: 256 bits aleatorios que no dicen nada. La base guarda su
SHA-256, nunca el token, asi que quien lea la tabla sesiones no puede
hacerse pasar por nadie. SHA-256 y no Argon2 porque el token no es una clave
que alguien eligio: no hay diccionario contra el que probar.

Todo token se crea nuevo al iniciar sesion. Nunca se reutiliza uno anterior,
y eso es lo que impide la fijacion de sesion.

Funciones que reciben `cur` corren dentro de la transaccion de quien llama.
"""

import dataclasses
import datetime
import hashlib
import secrets

from app import config
from app.authz.Modelos_opa import Sujeto

# Cierre por inactividad, Tabla 7.1 del Informe de politicas de P1. Cuanto
# puede quedarse quieta una sesion antes de pedir la contrasena otra vez.
INACTIVIDAD_MINUTOS = {
    "DIRECCION_GENERAL": 15,
    "DIRECCION_CERTIFICACION": 15,
    "PERSONAL_ADMINISTRATIVO": 15,
    "VERIFICADOR": 15,
    "AUDITOR_EXTERNO": 15,
    "TECNICO_CAMPO": 60,
    "DUENO_FINCA": 30,
    "TERCERO_AUTORIZADO": 30,
}


@dataclasses.dataclass(frozen=True)
class SesionActiva:
    """Quien esta del otro lado de una peticion, ya comprobado."""

    id: int
    cuenta: int
    usuario: str
    nombre: str
    rol: str
    zonas: tuple[str, ...]
    expira_en: datetime.datetime
    segundo_factor_ok: bool
    segundo_factor_requerido: bool
    totp_activo: bool
    debe_cambiar: bool
    reautenticada_en: datetime.datetime | None

    @property
    def sujeto(self) -> Sujeto:
        """El Sujeto del contrato 02. El id va como texto, siempre."""
        return Sujeto(id=str(self.cuenta), rol=self.rol, zonas=self.zonas)

    @property
    def verificada(self) -> bool:
        """Si ya paso el segundo factor, o no lo necesita."""
        return self.segundo_factor_ok or not self.segundo_factor_requerido

    def reautenticada_hace_poco(self, ahora: datetime.datetime) -> bool:
        if self.reautenticada_en is None:
            return False
        limite = datetime.timedelta(minutes=config.REAUTENTICACION_MINUTOS)
        return ahora - self.reautenticada_en <= limite


def nuevo_token() -> str:
    """256 bits aleatorios en base64 url. Lo unico que viaja al navegador."""
    return secrets.token_urlsafe(32)


def huella(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()


def segundo_factor_requerido(rol: str, totp_activo: bool) -> bool:
    from app.auth.totp import ROLES_OBLIGADOS
    return rol in ROLES_OBLIGADOS or totp_activo


def crear(cur, cuenta: int, segundo_factor_ok: bool) -> tuple[str, datetime.datetime]:
    """Abre una sesion nueva y devuelve el token, que no se vuelve a ver."""
    token = nuevo_token()
    cur.execute(
        "INSERT INTO sesiones (token_hash, cuenta, segundo_factor_ok, expira_en) "
        "VALUES (%s, %s, %s, now() + make_interval(hours => %s)) "
        "RETURNING expira_en",
        (huella(token), cuenta, segundo_factor_ok, config.SESION_HORAS),
    )
    return token, cur.fetchone()["expira_en"]


def _zonas(cur, cuenta: int) -> tuple[str, ...]:
    """Las zonas con asignacion vigente hoy. Es lo que C1 compara.

    Vigente es sin revocar y sin vencer. Una asignacion vencida no cuenta
    aunque la tarea que las revoca (HBAC-03, del transmisor) no haya pasado
    todavia: el permiso deja de existir el dia que vence, no cuando alguien
    se acuerda de quitarlo.
    """
    cur.execute(
        "SELECT zona FROM asignaciones_zona "
        "WHERE sujeto = %s AND revocada_en IS NULL AND vence >= CURRENT_DATE "
        "ORDER BY zona",
        (cuenta,),
    )
    return tuple(fila["zona"] for fila in cur.fetchall())


def buscar(cur, token: str) -> tuple[SesionActiva | None, str | None]:
    """La sesion del token, o (None, motivo) si no sirve.

    Si la sesion se paso del limite de inactividad de su perfil, se cierra
    aqui mismo. Si sirve, se anota el uso para medir la inactividad desde
    ahora.
    """
    if not token or len(token) > 200:
        return None, "sin token"

    cur.execute(
        "SELECT s.id, s.cuenta, s.expira_en, s.segundo_factor_ok, "
        "       s.reautenticada_en, s.ultimo_uso, now() AS ahora, "
        "       c.usuario, c.nombre, c.rol::text AS rol, c.activa, "
        "       coalesce(cr.totp_activo, false) AS totp_activo, "
        "       coalesce(cr.debe_cambiar, false) AS debe_cambiar "
        "FROM sesiones s "
        "JOIN cuentas c ON c.id = s.cuenta "
        "LEFT JOIN credenciales cr ON cr.cuenta = s.cuenta "
        "WHERE s.token_hash = %s AND s.cerrada_en IS NULL "
        "FOR UPDATE OF s",
        (huella(token),),
    )
    fila = cur.fetchone()
    if fila is None:
        return None, "sesion inexistente o cerrada"

    if fila["expira_en"] <= fila["ahora"]:
        cerrar(cur, fila["id"])
        return None, "sesion vencida"

    if not fila["activa"]:
        # No deberia pasar: dar de baja cierra todas las sesiones. Pero si
        # alguien desactiva a mano en la base, esto la cierra igual.
        cerrar(cur, fila["id"])
        return None, "cuenta desactivada"

    limite = datetime.timedelta(minutes=INACTIVIDAD_MINUTOS.get(fila["rol"], 15))
    if fila["ahora"] - fila["ultimo_uso"] > limite:
        cerrar(cur, fila["id"])
        return None, "sesion cerrada por inactividad"

    cur.execute("UPDATE sesiones SET ultimo_uso = now() WHERE id = %s",
                (fila["id"],))

    sesion = SesionActiva(
        id=fila["id"],
        cuenta=fila["cuenta"],
        usuario=fila["usuario"],
        nombre=fila["nombre"],
        rol=fila["rol"],
        zonas=_zonas(cur, fila["cuenta"]),
        expira_en=fila["expira_en"],
        segundo_factor_ok=fila["segundo_factor_ok"],
        segundo_factor_requerido=segundo_factor_requerido(
            fila["rol"], fila["totp_activo"]),
        totp_activo=fila["totp_activo"],
        debe_cambiar=fila["debe_cambiar"],
        reautenticada_en=fila["reautenticada_en"],
    )
    return sesion, None


def cerrar(cur, sesion_id: int) -> None:
    cur.execute(
        "UPDATE sesiones SET cerrada_en = now() "
        "WHERE id = %s AND cerrada_en IS NULL",
        (sesion_id,),
    )


def cerrar_todas(cur, cuenta: int, salvo: int | None = None) -> int:
    """Cierra todas las sesiones abiertas de una cuenta. Devuelve cuantas.

    SE-01 y CU-11: al cambiar de rol, al dar de baja y al cambiar la
    contrasena. `salvo` deja abierta la sesion desde la que se hizo el cambio.
    """
    cur.execute(
        "UPDATE sesiones SET cerrada_en = now() "
        "WHERE cuenta = %s AND cerrada_en IS NULL AND id IS DISTINCT FROM %s",
        (cuenta, salvo),
    )
    return cur.rowcount


def marcar_segundo_factor(cur, sesion_id: int) -> None:
    cur.execute("UPDATE sesiones SET segundo_factor_ok = true WHERE id = %s",
                (sesion_id,))


def marcar_reautenticada(cur, sesion_id: int) -> None:
    cur.execute("UPDATE sesiones SET reautenticada_en = now() WHERE id = %s",
                (sesion_id,))
