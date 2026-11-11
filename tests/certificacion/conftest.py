"""Comun a las pruebas de certificacion (O1 fincas, O2 periodos, O3 mediciones).

Igual que las de identidad, son de integracion: necesitan un PostgreSQL con el
esquema real y un OPA real, y se saltan si no hay base configurada.

    bash tests/identidad/preparar_bd.sh          # base desechable, la misma
    opa run --server --addr=127.0.0.1:8181 services/policies/rego &
    VERDEAZUL_PRUEBAS_BD="postgresql://app_rw@localhost:5432/neondb" \
        pytest tests/certificacion -v

La base es compartida por toda la corrida, asi que cada prueba crea sus propias
cuentas, fincas y periodos con nombres unicos y nunca depende de lo que dejo
otra. La base de pruebas NUNCA es Neon.
"""

import base64
import datetime
import os
import secrets
import uuid

import pyotp
import pytest

from app import bd, config
from app.authz import Cliente_opa

_LLAVE_CIFRADO = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
_LLAVE_BUSQUEDA = secrets.token_urlsafe(32)

# Un cuadrado de 0.01 grados. Cada finca de prueba lleva uno distinto.
_CUADRADO = ("POLYGON((%(x)s %(y)s, %(x2)s %(y)s, %(x2)s %(y2)s, "
             "%(x)s %(y2)s, %(x)s %(y)s))")


@pytest.fixture(autouse=True)
def llaves_de_prueba(monkeypatch):
    monkeypatch.setattr(config, "LLAVE_CIFRADO_DATOS",
                        config.Secreto(_LLAVE_CIFRADO))
    monkeypatch.setattr(config, "LLAVE_BUSQUEDA_CEDULA",
                        config.Secreto(_LLAVE_BUSQUEDA))
    monkeypatch.setattr(config, "VERIFICAR_FILTRACIONES", False)


URL_PRUEBAS = os.environ.get("VERDEAZUL_PRUEBAS_BD")


@pytest.fixture(scope="session")
def grupo():
    if not URL_PRUEBAS:
        pytest.skip("sin VERDEAZUL_PRUEBAS_BD: pruebas de integracion saltadas")
    if not Cliente_opa.OPA_disponible():
        pytest.fail("el motor de politicas no responde en 127.0.0.1:8181")

    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(URL_PRUEBAS, min_size=1, max_size=4,
                          kwargs={"row_factory": dict_row}, open=True)
    yield pool
    pool.close()


@pytest.fixture
def api(grupo, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(bd, "_principal", grupo)
    monkeypatch.setattr(bd, "arrancar", lambda: None)
    monkeypatch.setattr(bd, "cerrar", lambda: None)
    with TestClient(app) as cliente:
        yield cliente


class Fabrica:
    """Cuentas, fincas, periodos y mediciones de prueba, directo en la base."""

    def __init__(self, grupo):
        self.grupo = grupo

    def sql(self, consulta, parametros=()):
        with self.grupo.connection() as con:
            filas = con.execute(consulta, parametros)
            try:
                return filas.fetchall()
            except Exception:
                return None

    # -- cuentas ------------------------------------------------------------

    def cuenta(self, rol, *, zonas=()):
        from app.auth import contrasenas, totp as modulo_totp

        usuario = "%s-%s" % (rol.lower()[:6], uuid.uuid4().hex[:8])
        clave = "una frase larga de prueba " + secrets.token_hex(4)
        # El segundo factor es obligatorio para cuatro roles (D-13). Se activa
        # siempre: cuesta lo mismo y cada cuenta entra por el camino completo.
        secreto = modulo_totp.nuevo_secreto()
        with self.grupo.connection() as con:
            cuenta = con.execute(
                "INSERT INTO cuentas (usuario, nombre, rol) VALUES (%s, %s, %s) "
                "RETURNING id", (usuario, "Persona " + usuario, rol)
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO credenciales (cuenta, hash_argon2, totp_secreto, "
                "totp_activo) VALUES (%s, %s, %s, true)",
                (cuenta, contrasenas.hashear(clave),
                 modulo_totp.cifrar_secreto(secreto, cuenta)))
            for zona in zonas:
                con.execute("INSERT INTO asignaciones_zona (sujeto, zona, vence) "
                            "VALUES (%s, %s, CURRENT_DATE + 30)", (cuenta, zona))
        return {"id": cuenta, "usuario": usuario, "clave": clave,
                "secreto": secreto}

    def codigo(self, cuenta):
        self.sql("UPDATE credenciales SET totp_ultimo_paso = NULL "
                 "WHERE cuenta = %s", (cuenta["id"],))
        return pyotp.TOTP(cuenta["secreto"]).now()

    def ventana(self, auditor, dias_desde=-1, dias_hasta=1):
        hoy = datetime.date.today()
        self.sql("INSERT INTO ventanas_auditoria (auditor, inicio, fin) "
                 "VALUES (%s, %s, %s)",
                 (auditor["id"], hoy + datetime.timedelta(days=dias_desde),
                  hoy + datetime.timedelta(days=dias_hasta)))

    # -- datos --------------------------------------------------------------

    def finca(self, propietario, zona="PN"):
        # Un lugar distinto para cada finca, para que ningun traslape de una
        # prueba afecte a otra.
        x = -(80 + secrets.randbelow(5000) / 100)
        y = 5 + secrets.randbelow(500) / 100
        poligono = _CUADRADO % {"x": x, "x2": x + 0.01, "y": y, "y2": y + 0.01}
        return self.sql(
            "INSERT INTO fincas (nombre, zona, propietario, poligono) "
            "VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326)) RETURNING id",
            ("Finca " + uuid.uuid4().hex[:6], zona, propietario["id"],
             poligono))[0]["id"]

    def periodo(self, estado="ABIERTO"):
        return self.sql(
            "INSERT INTO periodos_medicion (etiqueta, estado, cerrado_en) "
            "VALUES (%s, %s, CASE WHEN %s = 'CERRADO' THEN now() END) "
            "RETURNING id", ("P-" + uuid.uuid4().hex[:8], estado, estado)
        )[0]["id"]

    def medicion(self, finca, periodo, autor, estado="REGISTRADA", revisor=None):
        return self.sql(
            "INSERT INTO mediciones (finca, periodo, autor, biomasa_toneladas, "
            "estado, revisada_por, revisada_en, motivo_devolucion) "
            "VALUES (%s, %s, %s, 10.5, %s, %s, "
            "CASE WHEN %s::text IS NULL THEN NULL ELSE now() END, "
            "CASE WHEN %s = 'DEVUELTA' THEN 'prueba' END) RETURNING id",
            (finca, periodo, autor["id"], estado,
             revisor["id"] if revisor else None,
             revisor["id"] if revisor else None, estado))[0]["id"]

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
    """Entra completo. Da la cabecera lista para usar."""
    r = api.post("/auth/entrar", json={"usuario": cuenta["usuario"],
                                       "clave": cuenta["clave"]})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    if r.json()["siguiente"] == "verificar_totp":
        r = api.post("/auth/totp/verificar", headers=cabecera(token),
                     json={"codigo": fabrica.codigo(cuenta)})
        assert r.status_code == 200, r.text
    if reautenticar:
        r = api.post("/auth/reautenticar", headers=cabecera(token),
                     json={"clave": cuenta["clave"],
                           "codigo": fabrica.codigo(cuenta)})
        assert r.status_code == 200, r.text
    return cabecera(token)
