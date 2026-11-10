"""Comun a las pruebas de identidad.

Dos familias:

  unitarias      sin base ni motor. Corren siempre, tambien en el CI.
  integracion    contra un PostgreSQL con el esquema real y un OPA real.
                 Se saltan si falta cualquiera de los dos.

Para correr las de integracion en local:

    bash tests/identidad/preparar_bd.sh          # base desechable
    opa run --server --addr=127.0.0.1:8181 services/policies/rego &
    VERDEAZUL_PRUEBAS_BD="postgresql://app_rw@localhost:5432/neondb" \
        pytest tests/identidad -v

La base de pruebas NUNCA es Neon: es una desechable, con los mismos roles y
migraciones. Por eso la cadena no pide verify-full ni lleva contrasena.
"""

import base64
import os
import secrets
import uuid

import pyotp
import pytest

from app import bd, config
from app.authz import Cliente_opa


# Llaves inventadas, las mismas durante toda la corrida para que lo que cifra
# una prueba lo pueda leer la siguiente. Nunca las de verdad.
_LLAVE_CIFRADO = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
_LLAVE_BUSQUEDA = secrets.token_urlsafe(32)


@pytest.fixture(autouse=True)
def llaves_de_prueba(monkeypatch):
    monkeypatch.setattr(config, "LLAVE_CIFRADO_DATOS",
                        config.Secreto(_LLAVE_CIFRADO))
    monkeypatch.setattr(config, "LLAVE_BUSQUEDA_CEDULA",
                        config.Secreto(_LLAVE_BUSQUEDA))
    monkeypatch.setattr(config, "VERIFICAR_FILTRACIONES", False)


# ---------------------------------------------------------------------------
# Integracion
# ---------------------------------------------------------------------------

URL_PRUEBAS = os.environ.get("VERDEAZUL_PRUEBAS_BD")


@pytest.fixture(scope="session")
def grupo():
    if not URL_PRUEBAS:
        pytest.skip("sin VERDEAZUL_PRUEBAS_BD: pruebas de integracion saltadas")
    if not Cliente_opa.OPA_disponible():
        # Con base configurada, un motor caido es una falla del entorno, no
        # una razon para saltar: si no, el CI se pondria verde sin probar.
        pytest.fail("el motor de politicas no responde en 127.0.0.1:8181")

    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(URL_PRUEBAS, min_size=1, max_size=4,
                          kwargs={"row_factory": dict_row}, open=True)
    yield pool
    pool.close()


@pytest.fixture
def api(grupo, monkeypatch):
    """Un cliente HTTP contra la aplicacion, con la base de pruebas."""
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(bd, "_principal", grupo)
    # Que el ciclo de vida no intente abrir Neon.
    monkeypatch.setattr(bd, "arrancar", lambda: None)
    monkeypatch.setattr(bd, "cerrar", lambda: None)
    with TestClient(app) as cliente:
        yield cliente


class Fabrica:
    """Crea cuentas de prueba directo en la base, con nombres que no chocan."""

    def __init__(self, grupo):
        self.grupo = grupo

    def sql(self, consulta, parametros=()):
        with self.grupo.connection() as con:
            filas = con.execute(consulta, parametros)
            try:
                return filas.fetchall()
            except Exception:
                return None

    def cuenta(self, rol, *, zonas=(), totp=False, debe_cambiar=False,
               clave=None):
        from app.auth import contrasenas, totp as modulo_totp

        usuario = "%s-%s" % (rol.lower()[:6], uuid.uuid4().hex[:8])
        clave = clave or "una frase larga de prueba " + secrets.token_hex(4)
        secreto = modulo_totp.nuevo_secreto() if totp else None
        with self.grupo.connection() as con:
            cuenta = con.execute(
                "INSERT INTO cuentas (usuario, nombre, rol) VALUES (%s, %s, %s) "
                "RETURNING id", (usuario, "Persona " + usuario, rol)
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO credenciales (cuenta, hash_argon2, totp_secreto, "
                "totp_activo, debe_cambiar) VALUES (%s, %s, %s, %s, %s)",
                (cuenta, contrasenas.hashear(clave),
                 modulo_totp.cifrar_secreto(secreto, cuenta) if secreto else None,
                 bool(secreto), debe_cambiar))
            for zona in zonas:
                con.execute("INSERT INTO asignaciones_zona (sujeto, zona, vence) "
                            "VALUES (%s, %s, CURRENT_DATE + 30)", (cuenta, zona))
        return {"id": cuenta, "usuario": usuario, "clave": clave,
                "secreto": secreto}

    def codigo(self, cuenta):
        """Un codigo valido ahora, olvidando el ultimo usado.

        El sistema no acepta dos veces el mismo codigo, y una prueba entra
        varias veces en la misma ventana de 30 segundos. Solo aqui se olvida.
        """
        self.sql("UPDATE credenciales SET totp_ultimo_paso = NULL "
                 "WHERE cuenta = %s", (cuenta["id"],))
        return pyotp.TOTP(cuenta["secreto"]).now()

    def eventos(self, accion=None, sujeto=None):
        consulta = "SELECT * FROM eventos_pendientes WHERE true"
        parametros = []
        if accion:
            consulta += " AND accion = %s"
            parametros.append(accion)
        if sujeto is not None:
            consulta += " AND sujeto = %s"
            parametros.append(str(sujeto))
        return self.sql(consulta + " ORDER BY id", tuple(parametros))


@pytest.fixture
def fabrica(grupo):
    return Fabrica(grupo)


def cabecera(token):
    return {"X-Verdeazul-Sesion": token}


def entrar(api, fabrica, cuenta, reautenticar=False):
    """Entra completo: contrasena, segundo factor si hace falta. Da el token."""
    r = api.post("/auth/entrar", json={"usuario": cuenta["usuario"],
                                       "clave": cuenta["clave"]})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    if r.json()["siguiente"] == "verificar_totp":
        r = api.post("/auth/totp/verificar", headers=cabecera(token),
                     json={"codigo": fabrica.codigo(cuenta)})
        assert r.status_code == 200, r.text
    if reautenticar:
        cuerpo = {"clave": cuenta["clave"]}
        if cuenta["secreto"]:
            cuerpo["codigo"] = fabrica.codigo(cuenta)
        r = api.post("/auth/reautenticar", headers=cabecera(token), json=cuerpo)
        assert r.status_code == 200, r.text
    return token
