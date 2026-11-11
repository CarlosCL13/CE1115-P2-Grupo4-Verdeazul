"""Pruebas sin base de datos ni motor. Corren siempre, tambien en el CI."""

import time

import pyotp
import pytest

from app import config
from app.auth import cifrado, contrasenas, sesiones, totp
from app.personas import cedula as ced


# ---------------------------------------------------------------------------
# §2.3.1: Argon2id con sal
# ---------------------------------------------------------------------------

def test_el_hash_es_argon2id_con_los_parametros_de_p1():
    h = contrasenas.hashear("caballo bateria grapa correcta")
    # Los parametros viajan dentro del hash: m=19 MiB, t=2, p=1 (OWASP, P1).
    assert h.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert "caballo" not in h


def test_la_sal_cambia_en_cada_hash():
    clave = "caballo bateria grapa correcta"
    assert contrasenas.hashear(clave) != contrasenas.hashear(clave)


def test_verificar():
    h = contrasenas.hashear("caballo bateria grapa correcta")
    assert contrasenas.verificar(h, "caballo bateria grapa correcta")
    assert not contrasenas.verificar(h, "caballo bateria grapa correctA")
    assert not contrasenas.verificar("no es un hash", "lo que sea")


def test_la_normalizacion_unicode_no_cambia_la_clave():
    # "n" con tilde precompuesta y descompuesta: misma clave para la persona.
    h = contrasenas.hashear("contraseña de la montaña")
    assert contrasenas.verificar(h, "contraseña de la montaña")


def test_un_hash_con_parametros_viejos_se_rehace():
    from argon2 import PasswordHasher, Type
    viejo = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1,
                           type=Type.ID).hash("x")
    assert contrasenas.necesita_rehash(viejo)
    assert not contrasenas.necesita_rehash(contrasenas.hashear("x"))


# ---------------------------------------------------------------------------
# CO-01 y CO-02
# ---------------------------------------------------------------------------

def test_co01_minimo_15_sin_reglas_de_composicion():
    assert contrasenas.problemas("corta1!A") != []
    # Sin mayusculas, sin numeros, sin simbolos: sirve igual (NIST).
    assert contrasenas.problemas("tres perros en el rio grande") == []


def test_co01_acepta_64_y_rechaza_lo_desmedido():
    assert contrasenas.problemas("ab cd ef gh " * 5 + "ijkl") == []
    assert contrasenas.problemas("x" * 129) != []


@pytest.mark.parametrize("clave", [
    "qwertyuiop12345",          # de la lista de SecLists
    "1q2w3e4r5t6y7u8i",
    "contrasena123456",          # de las agregadas a mano
    "QWERTYUIOP12345",          # mayusculas no la salvan
])
def test_co02_rechaza_las_comunes(clave):
    assert any("común" in p for p in contrasenas.problemas(clave))


def test_co02_rechaza_usuario_nombre_y_empresa():
    assert contrasenas.problemas("soy tcampos y esta es mi clave", "tcampos")
    assert contrasenas.problemas("tomas tiene una clave larga", "x",
                                 "Tomas Campos")
    assert contrasenas.problemas("la clave de VerdeAzul 2026")


def test_rechaza_pocos_caracteres_distintos():
    assert contrasenas.problemas("aaaaaaaaaaaaaaaaaaaa")
    assert contrasenas.problemas("abababababababababab")


def test_la_clave_temporal_es_larga_y_aleatoria():
    a, b = contrasenas.generar_temporal(), contrasenas.generar_temporal()
    assert a != b and len(a) >= 20


# ---------------------------------------------------------------------------
# Cifrado de datos (LG-05)
# ---------------------------------------------------------------------------

def test_cifrar_y_descifrar():
    blob = cifrado.cifrar("112340567", "datos_personales.cedula:9")
    assert b"112340567" not in blob
    assert cifrado.descifrar(blob, "datos_personales.cedula:9") == "112340567"


def test_mismo_texto_blobs_distintos():
    assert cifrado.cifrar("x", "c") != cifrado.cifrar("x", "c")


def test_el_contexto_ata_el_dato_a_su_fila():
    blob = cifrado.cifrar("112340567", "datos_personales.cedula:9")
    with pytest.raises(cifrado.DatoAlterado):
        cifrado.descifrar(blob, "datos_personales.cedula:10")


def test_un_byte_alterado_se_detecta():
    blob = bytearray(cifrado.cifrar("112340567", "c"))
    blob[-1] ^= 1
    with pytest.raises(cifrado.DatoAlterado):
        cifrado.descifrar(bytes(blob), "c")


def test_sin_llave_no_cifra(monkeypatch):
    monkeypatch.setattr(config, "LLAVE_CIFRADO_DATOS", None)
    with pytest.raises(cifrado.SinLlave):
        cifrado.cifrar("x", "c")


def test_llave_de_largo_equivocado(monkeypatch):
    monkeypatch.setattr(config, "LLAVE_CIFRADO_DATOS", config.Secreto("corta"))
    with pytest.raises(cifrado.SinLlave):
        cifrado.cifrar("x", "c")


# ---------------------------------------------------------------------------
# Cedula: buscar sin descifrar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entrada", ["1-1234-0567", "112340567", "1 1234 0567"])
def test_cedula_se_normaliza(entrada):
    assert ced.normalizar(entrada) == "112340567"


@pytest.mark.parametrize("mala", ["12345678", "1-1234-056a", "1234567890123", ""])
def test_cedula_invalida(mala):
    with pytest.raises(ced.CedulaInvalida):
        ced.normalizar(mala)


def test_el_hmac_es_determinista_y_depende_de_la_llave(monkeypatch):
    uno = ced.huella_busqueda("112340567")
    assert uno == ced.huella_busqueda("112340567")
    assert uno != ced.huella_busqueda("112340568")
    monkeypatch.setattr(config, "LLAVE_BUSQUEDA_CEDULA", config.Secreto("otra"))
    # Sin la llave, el valor guardado no se puede reproducir: un volcado de la
    # base no basta para recorrer las cedulas posibles.
    assert ced.huella_busqueda("112340567") != uno


def test_enmascarar():
    assert ced.enmascarar("112340567") == "*****0567"


def test_telefono():
    assert ced.normalizar_telefono("+506 8888-1234") == "+50688881234"
    with pytest.raises(ced.CedulaInvalida):
        ced.normalizar_telefono("123")


# ---------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------

def test_totp_acepta_el_codigo_actual_y_la_ventana_vecina():
    secreto = totp.nuevo_secreto()
    ahora = time.time()
    generador = pyotp.TOTP(secreto)
    assert totp.verificar(secreto, generador.at(ahora), None, ahora) is not None
    assert totp.verificar(secreto, generador.at(ahora - 30), None, ahora) is not None
    assert totp.verificar(secreto, generador.at(ahora - 90), None, ahora) is None


def test_totp_no_acepta_el_mismo_codigo_dos_veces():
    secreto = totp.nuevo_secreto()
    ahora = time.time()
    codigo = pyotp.TOTP(secreto).at(ahora)
    paso = totp.verificar(secreto, codigo, None, ahora)
    assert paso is not None
    assert totp.verificar(secreto, codigo, paso, ahora) is None


def test_totp_rechaza_basura():
    secreto = totp.nuevo_secreto()
    for codigo in ("", "12345", "1234567", "abcdef"):
        assert totp.verificar(secreto, codigo, None) is None


def test_secreto_totp_cifrado_y_atado_a_la_cuenta():
    secreto = totp.nuevo_secreto()
    blob = totp.cifrar_secreto(secreto, 4)
    assert secreto.encode() not in blob
    assert totp.descifrar_secreto(blob, 4) == secreto
    with pytest.raises(cifrado.DatoAlterado):
        totp.descifrar_secreto(blob, 5)


def test_codigos_de_recuperacion():
    codigos = totp.codigos_recuperacion()
    assert len(set(codigos)) == 8
    c = codigos[0]
    assert totp.huella_recuperacion(c) == totp.huella_recuperacion(
        c.lower().replace("-", " "))


def test_qr_es_un_svg_en_linea():
    assert totp.qr_svg(totp.uri(totp.nuevo_secreto(), "dg")).startswith(
        "data:image/svg+xml")


# ---------------------------------------------------------------------------
# Sesiones
# ---------------------------------------------------------------------------

def test_el_token_es_opaco_y_se_guarda_su_huella():
    token = sesiones.nuevo_token()
    assert len(token) >= 43
    assert sesiones.huella(token) != token and len(sesiones.huella(token)) == 64


def test_roles_que_exigen_segundo_factor():
    # D-05: los que aprueban, emiten o cambian permisos.
    for rol in ("DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
                "PERSONAL_ADMINISTRATIVO", "VERIFICADOR"):
        assert sesiones.segundo_factor_requerido(rol, totp_activo=False)
    for rol in ("TECNICO_CAMPO", "AUDITOR_EXTERNO", "DUENO_FINCA",
                "TERCERO_AUTORIZADO"):
        assert not sesiones.segundo_factor_requerido(rol, totp_activo=False)
        # Si lo activo por su cuenta, se le pide siempre.
        assert sesiones.segundo_factor_requerido(rol, totp_activo=True)


def test_inactividad_por_perfil_segun_p1():
    m = sesiones.INACTIVIDAD_MINUTOS
    assert set(m) == {"DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
                      "PERSONAL_ADMINISTRATIVO", "TECNICO_CAMPO", "VERIFICADOR",
                      "AUDITOR_EXTERNO", "DUENO_FINCA", "TERCERO_AUTORIZADO"}
    assert m["TECNICO_CAMPO"] == 60 and m["DUENO_FINCA"] == 30
    assert m["DIRECCION_GENERAL"] == 15


def test_el_sujeto_lleva_el_id_como_texto():
    # Contrato 02: un id entero hace que C3, C4, C5, C6 y C10 concedan de mas.
    import datetime
    s = sesiones.SesionActiva(
        id=1, cuenta=6, usuario="vf1", nombre="V", rol="VERIFICADOR",
        zonas=("PN",), expira_en=datetime.datetime.now(datetime.timezone.utc),
        segundo_factor_ok=True, segundo_factor_requerido=True, totp_activo=True,
        debe_cambiar=False, reautenticada_en=None)
    assert s.sujeto.id == "6" and s.sujeto.zonas == ("PN",)


# ---------------------------------------------------------------------------
# RC-01
# ---------------------------------------------------------------------------

def test_rc01_la_espera_crece_y_a_los_diez_bloquea():
    from app.auth.rutas import _segundos_de_espera
    assert [_segundos_de_espera(n) for n in range(1, 5)] == [None] * 4
    assert [_segundos_de_espera(n) for n in range(5, 10)] == [15, 30, 60, 120, 240]
    assert _segundos_de_espera(10) == 30 * 60
    assert _segundos_de_espera(11) == 30 * 60


# ---------------------------------------------------------------------------
# Bitacora
# ---------------------------------------------------------------------------

class _CursorFalso:
    def __init__(self):
        self.ejecutado = []

    def execute(self, sql, parametros):
        self.ejecutado.append((sql, parametros))


def test_registrar_escribe_en_la_bandeja_y_preserva_las_denegaciones():
    from app import bd
    from app.bitacora import registrar

    cursor = _CursorFalso()
    salvados = []
    t1 = bd._cursor_actual.set(cursor)
    t2 = bd._eventos_a_salvo.set(salvados)
    try:
        registrar(accion="X", sujeto="1", objeto="O9:1", resultado="PERMITIDO")
        registrar(accion="Y", sujeto="1", objeto="O9:1", resultado="DENEGADO",
                  motivo="porque si")
    finally:
        bd._cursor_actual.reset(t1)
        bd._eventos_a_salvo.reset(t2)
    assert len(cursor.ejecutado) == 2
    assert "eventos_pendientes" in cursor.ejecutado[0][0]
    assert len(salvados) == 1 and salvados[0]["accion"] == "Y"


def test_registrar_rechaza_lo_que_el_contrato_prohibe():
    from app.bitacora import registrar
    from app.bitacora.registrar import EventoInvalido
    with pytest.raises(EventoInvalido):
        registrar(accion="X", sujeto="1", objeto="O", resultado="DENEGADO")
    with pytest.raises(EventoInvalido):
        registrar(accion="X", sujeto="1", objeto="O", resultado="TAL VEZ")
    with pytest.raises(EventoInvalido):
        registrar(accion="X", sujeto="1", objeto="O", resultado="PERMITIDO",
                  detalle={"clave": "nunca"})


def test_registrar_fuera_de_transaccion_falla():
    from app import bd
    from app.bitacora import registrar
    with pytest.raises(bd.SinTransaccion):
        registrar(accion="X", sujeto="1", objeto="O", resultado="PERMITIDO")
