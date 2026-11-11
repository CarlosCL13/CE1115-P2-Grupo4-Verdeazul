"""Pruebas de integracion: la aplicacion entera contra PostgreSQL y OPA reales.

Cada prueba es algo que el enunciado o P1 piden demostrar, y varias son
justo lo que hay que mostrar el 19 de noviembre (§6): un rol haciendo lo que
le corresponde, otro intentando lo que no y el servidor rechazandolo, y el
registro de auditoria con esas acciones.
"""

import pyotp

from conftest import cabecera, entrar

# ---------------------------------------------------------------------------
# Entrar
# ---------------------------------------------------------------------------


def test_entrar_y_ver_la_sesion(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO", zonas=("PN", "CS"))
    token = entrar(api, fabrica, tc)

    r = api.get("/auth/sesion", headers=cabecera(token))
    assert r.status_code == 200
    sesion = r.json()
    assert sesion["rol"] == "TECNICO_CAMPO"
    assert sesion["zonas"] == ["CS", "PN"]
    assert sesion["siguiente"] == "listo"
    assert fabrica.eventos("SESION_INICIADA", tc["id"])


def test_la_base_guarda_argon2id_y_nunca_la_clave(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO")
    fila = fabrica.sql("SELECT hash_argon2 FROM credenciales WHERE cuenta = %s",
                       (tc["id"],))[0]
    assert fila["hash_argon2"].startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert tc["clave"] not in fila["hash_argon2"]


def test_el_error_no_dice_si_el_usuario_existe(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO")
    mala = api.post("/auth/entrar", json={"usuario": tc["usuario"],
                                          "clave": "no es la clave correcta"})
    inexistente = api.post("/auth/entrar", json={"usuario": "nadie-asi-se-llama",
                                                 "clave": "lo que sea aqui"})
    assert mala.status_code == inexistente.status_code == 401
    assert mala.json() == inexistente.json()
    # Pero la bitacora si sabe que paso.
    assert fabrica.eventos("AUTENTICACION_FALLIDA", tc["id"])
    assert fabrica.eventos("AUTENTICACION_FALLIDA", "ANONIMO")


def test_sin_sesion_no_hay_nada(api, fabrica):
    assert api.get("/auth/sesion").status_code == 401
    assert api.get("/personas", headers=cabecera("inventado")).status_code == 401
    assert api.get("/cuentas").json() == {"detail": "sin_sesion"}


def test_salir_invalida_el_token(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO")
    token = entrar(api, fabrica, tc)
    assert api.post("/auth/salir", headers=cabecera(token)).status_code == 200
    assert api.get("/auth/sesion", headers=cabecera(token)).status_code == 401


def test_cada_entrada_da_un_token_nuevo(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO")
    assert entrar(api, fabrica, tc) != entrar(api, fabrica, tc)
    # Y la base no guarda el token, solo su SHA-256.
    filas = fabrica.sql("SELECT token_hash FROM sesiones WHERE cuenta = %s",
                        (tc["id"],))
    assert all(len(f["token_hash"]) == 64 for f in filas)


# ---------------------------------------------------------------------------
# RC-01: bloqueo
# ---------------------------------------------------------------------------

def test_rc01_tras_cinco_fallos_hay_que_esperar(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO")
    for _ in range(5):
        api.post("/auth/entrar", json={"usuario": tc["usuario"],
                                       "clave": "equivocada pero larga"})
    # La clave correcta tampoco sirve mientras dura la espera.
    r = api.post("/auth/entrar", json={"usuario": tc["usuario"],
                                       "clave": tc["clave"]})
    assert r.status_code == 401
    fila = fabrica.sql("SELECT intentos_fallidos, bloqueada_hasta > now() AS b "
                       "FROM cuentas WHERE id = %s", (tc["id"],))[0]
    assert fila["intentos_fallidos"] == 5 and fila["b"]


def test_rc01_al_decimo_bloqueo_de_30_minutos(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO")
    fabrica.sql("UPDATE cuentas SET intentos_fallidos = 9 WHERE id = %s",
                (tc["id"],))
    api.post("/auth/entrar", json={"usuario": tc["usuario"],
                                   "clave": "equivocada pero larga"})
    fila = fabrica.sql(
        "SELECT bloqueada_hasta - now() > interval '29 minutes' AS largo "
        "FROM cuentas WHERE id = %s", (tc["id"],))[0]
    assert fila["largo"]
    assert fabrica.eventos("CUENTA_BLOQUEADA", tc["id"])


def test_al_entrar_se_ven_los_intentos_fallidos_previos(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO")
    for _ in range(2):
        api.post("/auth/entrar", json={"usuario": tc["usuario"],
                                       "clave": "equivocada pero larga"})
    r = api.post("/auth/entrar", json={"usuario": tc["usuario"],
                                       "clave": tc["clave"]})
    assert r.json()["intentos_fallidos_previos"] == 2
    assert fabrica.sql("SELECT intentos_fallidos FROM cuentas WHERE id = %s",
                       (tc["id"],))[0]["intentos_fallidos"] == 0


# ---------------------------------------------------------------------------
# Segundo factor
# ---------------------------------------------------------------------------

def test_direccion_general_no_entra_sin_activar_el_segundo_factor(api, fabrica):
    dg = fabrica.cuenta("DIRECCION_GENERAL")
    r = api.post("/auth/entrar", json={"usuario": dg["usuario"],
                                       "clave": dg["clave"]})
    assert r.json()["siguiente"] == "activar_totp"
    token = r.json()["token"]

    # Con solo la contrasena no ve nada.
    r = api.get("/personas", headers=cabecera(token))
    assert r.status_code == 401
    assert r.json()["detail"] == "segundo_factor_pendiente"

    alta = api.post("/auth/totp/activar", headers=cabecera(token)).json()
    assert alta["otpauth"].startswith("otpauth://totp/")
    assert alta["qr"].startswith("data:image/svg+xml")

    codigo = pyotp.TOTP(alta["secreto"]).now()
    r = api.post("/auth/totp/verificar", headers=cabecera(token),
                 json={"codigo": codigo})
    assert r.status_code == 200, r.text
    assert len(r.json()["codigos_recuperacion"]) == 8

    assert api.get("/personas", headers=cabecera(token)).status_code == 200
    assert fabrica.eventos("TOTP_ACTIVADO", dg["id"])

    # El secreto quedo cifrado: no aparece en la base.
    blob = fabrica.sql("SELECT totp_secreto FROM credenciales WHERE cuenta = %s",
                       (dg["id"],))[0]["totp_secreto"]
    assert alta["secreto"].encode() not in bytes(blob)


def test_el_mismo_codigo_no_sirve_dos_veces(api, fabrica):
    vf = fabrica.cuenta("VERIFICADOR", totp=True)
    codigo = fabrica.codigo(vf)
    for intento, esperado in ((1, 200), (2, 401)):
        r = api.post("/auth/entrar", json={"usuario": vf["usuario"],
                                           "clave": vf["clave"]})
        r = api.post("/auth/totp/verificar", headers=cabecera(r.json()["token"]),
                     json={"codigo": codigo})
        assert r.status_code == esperado, intento


def test_activar_otra_vez_se_niega(api, fabrica):
    # Con solo la contrasena no se puede reemplazar el segundo factor ajeno.
    vf = fabrica.cuenta("VERIFICADOR", totp=True)
    r = api.post("/auth/entrar", json={"usuario": vf["usuario"],
                                       "clave": vf["clave"]})
    r = api.post("/auth/totp/activar", headers=cabecera(r.json()["token"]))
    assert r.status_code == 409


def test_codigo_de_recuperacion_sirve_una_vez_y_cierra_lo_demas(api, fabrica):
    dg = fabrica.cuenta("DIRECCION_GENERAL")
    r = api.post("/auth/entrar", json={"usuario": dg["usuario"],
                                       "clave": dg["clave"]})
    token = r.json()["token"]
    secreto = api.post("/auth/totp/activar", headers=cabecera(token)).json()["secreto"]
    codigos = api.post("/auth/totp/verificar", headers=cabecera(token),
                       json={"codigo": pyotp.TOTP(secreto).now()}
                       ).json()["codigos_recuperacion"]

    nuevo = api.post("/auth/entrar", json={"usuario": dg["usuario"],
                                           "clave": dg["clave"]}).json()["token"]
    r = api.post("/auth/totp/verificar", headers=cabecera(nuevo),
                 json={"codigo_recuperacion": codigos[0]})
    assert r.status_code == 200 and r.json()["restantes"] == 7
    # RC-04: la sesion anterior se cerro.
    assert api.get("/auth/sesion", headers=cabecera(token)).status_code == 401

    otro = api.post("/auth/entrar", json={"usuario": dg["usuario"],
                                          "clave": dg["clave"]}).json()["token"]
    r = api.post("/auth/totp/verificar", headers=cabecera(otro),
                 json={"codigo_recuperacion": codigos[0]})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Sesion: inactividad, reautenticacion
# ---------------------------------------------------------------------------

def test_inactividad_cierra_la_sesion(api, fabrica):
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO", totp=True)
    token = entrar(api, fabrica, pa)
    fabrica.sql("UPDATE sesiones SET ultimo_uso = now() - interval '16 minutes' "
                "WHERE cuenta = %s", (pa["id"],))
    assert api.get("/auth/sesion", headers=cabecera(token)).status_code == 401


def test_el_tecnico_tiene_una_hora(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO")
    token = entrar(api, fabrica, tc)
    fabrica.sql("UPDATE sesiones SET ultimo_uso = now() - interval '45 minutes' "
                "WHERE cuenta = %s", (tc["id"],))
    assert api.get("/auth/sesion", headers=cabecera(token)).status_code == 200


def test_reautenticar_pide_contrasena_y_codigo(api, fabrica):
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO", totp=True)
    token = entrar(api, fabrica, pa)
    r = api.post("/auth/reautenticar", headers=cabecera(token),
                 json={"clave": pa["clave"]})
    assert r.status_code == 401
    r = api.post("/auth/reautenticar", headers=cabecera(token),
                 json={"clave": pa["clave"], "codigo": fabrica.codigo(pa)})
    assert r.status_code == 200
    assert api.get("/auth/sesion", headers=cabecera(token)).json()["reautenticada"]


# ---------------------------------------------------------------------------
# O10: credenciales propias
# ---------------------------------------------------------------------------

def test_cambiar_la_clave(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO")
    otra_sesion = entrar(api, fabrica, tc)
    token = entrar(api, fabrica, tc)

    debil = api.patch("/credenciales", headers=cabecera(token),
                      json={"clave_actual": tc["clave"],
                            "clave_nueva": "qwertyuiop12345"})
    assert debil.status_code == 422 and debil.json()["problemas"]

    nueva = "el rio suena cuando piedras trae"
    r = api.patch("/credenciales", headers=cabecera(token),
                  json={"clave_actual": tc["clave"], "clave_nueva": nueva})
    assert r.status_code == 200, r.text

    # Las demas sesiones se cerraron; la vieja clave ya no sirve.
    assert api.get("/auth/sesion", headers=cabecera(otra_sesion)).status_code == 401
    assert api.get("/auth/sesion", headers=cabecera(token)).status_code == 200
    assert api.post("/auth/entrar", json={"usuario": tc["usuario"],
                                          "clave": tc["clave"]}).status_code == 401
    assert api.post("/auth/entrar", json={"usuario": tc["usuario"],
                                          "clave": nueva}).status_code == 200


def test_cambiar_la_clave_exige_la_actual(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO")
    token = entrar(api, fabrica, tc)
    r = api.patch("/credenciales", headers=cabecera(token),
                  json={"clave_actual": "no es la actual para nada",
                        "clave_nueva": "el rio suena cuando piedras trae"})
    assert r.status_code == 401
    assert fabrica.sql("SELECT intentos_fallidos FROM cuentas WHERE id = %s",
                       (tc["id"],))[0]["intentos_fallidos"] == 1


def test_no_existe_leer_credenciales(api, fabrica):
    # Ningun rol tiene L sobre O10: no hay ruta GET. La ruta existe, pero
    # solo para PATCH, asi que el servidor responde 405 y no 404.
    tc = fabrica.cuenta("TECNICO_CAMPO")
    token = entrar(api, fabrica, tc)
    assert api.get("/credenciales", headers=cabecera(token)).status_code == 405


def test_un_dato_alterado_en_la_base_se_detecta(api, fabrica):
    # Alguien con acceso a la base copia la cedula cifrada de un dueno sobre
    # la de otro. GCM lo detecta porque el contexto ata el dato a su fila.
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO", totp=True)
    t_pa = entrar(api, fabrica, pa)
    a = _registrar_dueno(api, fabrica, t_pa, "3-0%03d-0001" % (pa["id"] % 1000))
    b = _registrar_dueno(api, fabrica, t_pa, "3-0%03d-0002" % (pa["id"] % 1000))
    fabrica.sql("UPDATE datos_personales SET cedula_cifrada = "
                "(SELECT cedula_cifrada FROM datos_personales WHERE cuenta = %s) "
                "WHERE cuenta = %s", (a["id"], b["id"]))
    r = api.get("/personas/%d" % b["id"], headers=cabecera(t_pa))
    assert r.status_code == 409 and r.json()["detail"] == "dato_ilegible"
    assert fabrica.eventos("DATO_PERSONAL_ILEGIBLE", pa["id"])
    # Y el listado sigue funcionando.
    assert api.get("/personas", headers=cabecera(t_pa)).status_code == 200


# ---------------------------------------------------------------------------
# O9 y C10: nadie se da permisos a si mismo
# ---------------------------------------------------------------------------

def _solicitar(api, token, **cuerpo):
    cuerpo.setdefault("justificacion", "pedido de la jefatura por correo")
    r = api.post("/solicitudes-rol", headers=cabecera(token), json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()["solicitud"]


def test_c10_alta_completa(api, fabrica):
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO", totp=True)
    dg = fabrica.cuenta("DIRECCION_GENERAL", totp=True)
    t_pa = entrar(api, fabrica, pa, reautenticar=True)
    t_dg = entrar(api, fabrica, dg, reautenticar=True)

    usuario = "nuevo" + pa["usuario"][-6:]
    solicitud = _solicitar(api, t_pa, tipo="ALTA", usuario_nuevo=usuario,
                           nombre_nuevo="Persona Nueva", rol="TECNICO_CAMPO")

    # Sin aprobacion de DG el motor niega por C10, y queda en la bitacora.
    r = api.post("/cuentas", headers=cabecera(t_pa), json={"solicitud": solicitud})
    assert r.status_code == 403 and r.json() == {"detail": "denegado"}
    negado = fabrica.eventos("ACCESO_DENEGADO", pa["id"])[-1]
    assert negado["detalle"]["condicion"] == "C10"
    assert negado["resultado"] == "DENEGADO"

    # El administrativo no puede aprobar su propia solicitud.
    r = api.post("/solicitudes-rol/%d/aprobar" % solicitud, headers=cabecera(t_pa))
    assert r.status_code == 403

    r = api.post("/solicitudes-rol/%d/aprobar" % solicitud, headers=cabecera(t_dg))
    assert r.status_code == 200, r.text

    # Direccion General no puede ejecutar: solo tiene L sobre O9.
    r = api.post("/cuentas", headers=cabecera(t_dg), json={"solicitud": solicitud})
    assert r.status_code == 403

    r = api.post("/cuentas", headers=cabecera(t_pa), json={"solicitud": solicitud})
    assert r.status_code == 201, r.text
    creada = r.json()
    assert creada["rol"] == "TECNICO_CAMPO" and len(creada["clave_temporal"]) >= 20

    # La solicitud no sirve dos veces.
    r = api.post("/cuentas", headers=cabecera(t_pa), json={"solicitud": solicitud})
    assert r.status_code == 403

    # La cuenta nueva entra, pero solo puede cambiar la clave temporal.
    r = api.post("/auth/entrar", json={"usuario": usuario,
                                       "clave": creada["clave_temporal"]})
    assert r.json()["siguiente"] == "cambiar_clave"
    t_nuevo = r.json()["token"]
    r = api.get("/personas", headers=cabecera(t_nuevo))
    assert r.json()["detail"] == "cambio_de_clave_pendiente"
    r = api.patch("/credenciales", headers=cabecera(t_nuevo),
                  json={"clave_actual": creada["clave_temporal"],
                        "clave_nueva": "mi propia frase secreta de campo"})
    assert r.status_code == 200
    assert api.get("/auth/sesion", headers=cabecera(t_nuevo)).json()["siguiente"] == "listo"


def test_c10_las_acciones_graves_piden_reautenticacion(api, fabrica):
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO", totp=True)
    token = entrar(api, fabrica, pa)
    r = api.post("/cuentas", headers=cabecera(token), json={"solicitud": 1})
    assert r.status_code == 401
    assert r.json()["detail"] == "reautenticacion_requerida"


def test_cambio_de_rol_cierra_sesiones_y_revoca_zonas(api, fabrica):
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO", totp=True)
    dg = fabrica.cuenta("DIRECCION_GENERAL", totp=True)
    tc = fabrica.cuenta("TECNICO_CAMPO", zonas=("PN",))
    t_pa = entrar(api, fabrica, pa, reautenticar=True)
    t_dg = entrar(api, fabrica, dg, reautenticar=True)
    t_tc = entrar(api, fabrica, tc)

    solicitud = _solicitar(api, t_pa, tipo="CAMBIO_ROL", usuario=tc["usuario"],
                           rol="DUENO_FINCA")
    api.post("/solicitudes-rol/%d/aprobar" % solicitud, headers=cabecera(t_dg))

    # Mientras tanto, el administrativo ve esa cuenta (L.C10) y solo esa.
    cuentas = api.get("/cuentas", headers=cabecera(t_pa)).json()["cuentas"]
    assert tc["id"] in [c["id"] for c in cuentas]
    assert pa["id"] not in [c["id"] for c in cuentas]

    # Una aprobacion para otra cuenta no sirve para esta.
    r = api.patch("/cuentas/%d" % pa["id"], headers=cabecera(t_pa),
                  json={"solicitud": solicitud})
    assert r.status_code == 403

    r = api.patch("/cuentas/%d" % tc["id"], headers=cabecera(t_pa),
                  json={"solicitud": solicitud})
    assert r.status_code == 200, r.text
    assert r.json()["sesiones_cerradas"] == 1

    # SE-01: la sesion del tecnico murio en ese instante.
    assert api.get("/auth/sesion", headers=cabecera(t_tc)).status_code == 401
    vigentes = fabrica.sql("SELECT count(*) AS n FROM asignaciones_zona "
                           "WHERE sujeto = %s AND revocada_en IS NULL", (tc["id"],))
    assert vigentes[0]["n"] == 0
    # Y al volver a entrar ya es dueno de finca.
    token = entrar(api, fabrica, tc)
    assert api.get("/auth/sesion", headers=cabecera(token)).json()["rol"] == "DUENO_FINCA"


def test_baja_el_mismo_dia(api, fabrica):
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO", totp=True)
    dg = fabrica.cuenta("DIRECCION_GENERAL", totp=True)
    vf = fabrica.cuenta("VERIFICADOR", totp=True)
    t_pa = entrar(api, fabrica, pa, reautenticar=True)
    t_dg = entrar(api, fabrica, dg, reautenticar=True)
    t_vf = entrar(api, fabrica, vf)

    solicitud = _solicitar(api, t_pa, tipo="BAJA", usuario=vf["usuario"])
    api.post("/solicitudes-rol/%d/aprobar" % solicitud, headers=cabecera(t_dg))
    r = api.patch("/cuentas/%d" % vf["id"], headers=cabecera(t_pa),
                  json={"solicitud": solicitud})
    assert r.status_code == 200, r.text

    assert api.get("/auth/sesion", headers=cabecera(t_vf)).status_code == 401
    r = api.post("/auth/entrar", json={"usuario": vf["usuario"], "clave": vf["clave"]})
    assert r.status_code == 401
    # CU-13: no se borro, se desactivo.
    fila = fabrica.sql("SELECT activa, desactivada_en FROM cuentas WHERE id = %s",
                       (vf["id"],))[0]
    assert fila["activa"] is False and fila["desactivada_en"] is not None


def test_nadie_pide_cambios_para_si_mismo(api, fabrica):
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO", totp=True)
    token = entrar(api, fabrica, pa)
    r = api.post("/solicitudes-rol", headers=cabecera(token),
                 json={"tipo": "CAMBIO_ROL", "usuario": pa["usuario"],
                       "rol": "DIRECCION_GENERAL",
                       "justificacion": "quiero mas permisos"})
    assert r.status_code == 422


def test_solo_el_administrativo_pide_y_solo_dg_ve_todas_las_cuentas(api, fabrica):
    tc = fabrica.cuenta("TECNICO_CAMPO")
    dg = fabrica.cuenta("DIRECCION_GENERAL", totp=True)
    t_tc = entrar(api, fabrica, tc)
    t_dg = entrar(api, fabrica, dg)

    r = api.post("/solicitudes-rol", headers=cabecera(t_tc),
                 json={"tipo": "CAMBIO_ROL", "usuario": "dg",
                       "rol": "TECNICO_CAMPO", "justificacion": "por probar"})
    assert r.status_code == 403
    assert api.get("/cuentas", headers=cabecera(t_tc)).status_code == 403

    todas = api.get("/cuentas", headers=cabecera(t_dg)).json()["cuentas"]
    assert {tc["id"], dg["id"]} <= {c["id"] for c in todas}


# ---------------------------------------------------------------------------
# O6: datos personales
# ---------------------------------------------------------------------------

def _registrar_dueno(api, fabrica, t_pa, cedula):
    df = fabrica.cuenta("DUENO_FINCA")
    r = api.post("/personas", headers=cabecera(t_pa),
                 json={"usuario": df["usuario"], "nombre_completo": "Delia Fallas",
                       "cedula": cedula, "telefono": "+506 8888-1234"})
    assert r.status_code == 201, r.text
    return df


def test_o6_el_administrativo_registra_y_busca_por_cedula(api, fabrica, grupo):
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO", totp=True)
    t_pa = entrar(api, fabrica, pa)
    cedula = "1-%04d-%04d" % (abs(hash(pa["usuario"])) % 10000, pa["id"] % 10000)
    df = _registrar_dueno(api, fabrica, t_pa, cedula)

    r = api.get("/personas", headers=cabecera(t_pa), params={"cedula": cedula})
    personas = r.json()["personas"]
    assert [p["cuenta"] for p in personas] == [df["id"]]
    assert personas[0]["cedula"].startswith("*****")

    # LG-05: en la base no hay ni una cedula ni un telefono legibles.
    fila = fabrica.sql("SELECT cedula_cifrada, telefono_cifrado, cedula_busqueda "
                       "FROM datos_personales WHERE cuenta = %s", (df["id"],))[0]
    digitos = cedula.replace("-", "").encode()
    for columna in fila.values():
        assert digitos not in bytes(columna)
        assert b"88881234" not in bytes(columna)

    # Repetir la cedula en otra cuenta se rechaza.
    otro = fabrica.cuenta("DUENO_FINCA")
    r = api.post("/personas", headers=cabecera(t_pa),
                 json={"usuario": otro["usuario"], "nombre_completo": "Otra",
                       "cedula": cedula})
    assert r.status_code == 409


def test_o6_el_dueno_ve_lo_suyo_y_nada_mas(api, fabrica):
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO", totp=True)
    t_pa = entrar(api, fabrica, pa)
    df1 = _registrar_dueno(api, fabrica, t_pa, "2-0%03d-0001" % (pa["id"] % 1000))
    df2 = _registrar_dueno(api, fabrica, t_pa, "2-0%03d-0002" % (pa["id"] % 1000))
    t_df1 = entrar(api, fabrica, df1)

    r = api.get("/personas/%d" % df1["id"], headers=cabecera(t_df1))
    assert r.status_code == 200
    assert r.json()["telefono"] == "+50688881234"

    # Cambiar el numero en la direccion no sirve (IDOR), y queda registrado.
    r = api.get("/personas/%d" % df2["id"], headers=cabecera(t_df1))
    assert r.status_code == 403
    negado = fabrica.eventos("ACCESO_DENEGADO", df1["id"])[-1]
    assert negado["objeto"] == "O6:%d" % df2["id"]
    assert negado["detalle"]["condicion"] == "C8"

    # El listado del dueno trae solo lo suyo.
    lista = api.get("/personas", headers=cabecera(t_df1)).json()["personas"]
    assert [p["cuenta"] for p in lista] == [df1["id"]]

    # Y no puede corregir: el dueno no tiene M sobre O6.
    r = api.patch("/personas/%d" % df1["id"], headers=cabecera(t_df1),
                  json={"telefono": "88880000"})
    assert r.status_code == 403
    r = api.patch("/personas/%d" % df1["id"], headers=cabecera(t_pa),
                  json={"telefono": "88880000"})
    assert r.status_code == 200


def test_o6_direccion_de_certificacion_no_ve_datos_personales(api, fabrica):
    dc = fabrica.cuenta("DIRECCION_CERTIFICACION", totp=True)
    token = entrar(api, fabrica, dc)
    assert api.get("/personas", headers=cabecera(token)).status_code == 403
    assert api.get("/personas/9", headers=cabecera(token)).status_code == 403
    for rol in ("TECNICO_CAMPO", "AUDITOR_EXTERNO", "TERCERO_AUTORIZADO"):
        cuenta = fabrica.cuenta(rol)
        t = entrar(api, fabrica, cuenta)
        assert api.get("/personas", headers=cabecera(t)).status_code == 403, rol


# ---------------------------------------------------------------------------
# La bitacora no pierde las denegaciones aunque la operacion se revierta
# ---------------------------------------------------------------------------

def test_la_denegacion_sobrevive_la_reversion(api, fabrica):
    ta = fabrica.cuenta("TERCERO_AUTORIZADO")
    token = entrar(api, fabrica, ta)
    antes = len(fabrica.eventos("ACCESO_DENEGADO", ta["id"]))
    api.post("/personas", headers=cabecera(token),
             json={"usuario": "x", "nombre_completo": "xxx", "cedula": "112340567"})
    despues = fabrica.eventos("ACCESO_DENEGADO", ta["id"])
    assert len(despues) == antes + 1
    assert despues[-1]["motivo"].startswith("denegado")
