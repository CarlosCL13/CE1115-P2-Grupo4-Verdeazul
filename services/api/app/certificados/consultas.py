"""SQL y atributos de O5. El motor decide; este modulo le arma lo que necesita.

    C6  medicion.estado, medicion.autor_id,
        contexto.poligono_traslapa_certificado_vigente   lo calcula aqui
    C7  auditoria.inicio / fin       (app.certificacion.consultas)
    C8  finca.propietario_id         el dueno de la finca del certificado
    C9  autorizacion.tercero_id,     de la tabla consentimientos (O7)
        autorizacion.vence

C9 en el motor solo mira que la autorizacion sea del sujeto y no haya
vencido. No sabe de que finca es ni si el dueno la revoco. Eso lo resuelve
este modulo: solo le manda una autorizacion si es **de la finca del
certificado** y **no esta revocada**. Si no hay ninguna, no manda nada y C9
no se cumple. Es el hueco que notamos en la revision de P1 (con la regla tal
como estaba escrita, cualquier autorizacion vigente abria todos los
certificados). Ver D-20.
"""

from app.auth.sesiones import SesionActiva
from app.certificados import firma

LIMITE_LISTADO = 200

# Dos enteros y no uno: pg_advisory_xact_lock(int, int) y
# pg_advisory_xact_lock(bigint) son espacios de llaves separados, asi que este
# candado no puede chocar con el 42 del transmisor. 5 por O5, 6 por C6.
CANDADO_EMISION = "SELECT pg_advisory_xact_lock(5, 6)"

_COLUMNAS = (
    "c.id, c.medicion, c.toneladas, c.estado::text AS estado, "
    "c.emitido_por, c.emitido_en, c.motivo_anulacion, c.anulado_en, "
    "c.llave_publica, m.finca, m.autor, f.nombre AS finca_nombre, "
    "f.zona, f.propietario, p.etiqueta AS periodo_etiqueta")
_DESDE = (
    " FROM certificados c "
    "JOIN mediciones m ON m.id = c.medicion "
    "JOIN fincas f ON f.id = m.finca "
    "JOIN periodos_medicion p ON p.id = m.periodo ")

# Para listados: sin el documento, que pesa un par de KB por fila.
SELECT_CERTIFICADO = "SELECT " + _COLUMNAS + _DESDE
# Para ver uno: con el documento firmado, tal como se entrego.
SELECT_CERTIFICADO_CON_DOCUMENTO = "SELECT " + _COLUMNAS + ", c.documento" + _DESDE

# Lo que hace falta para emitir. Bloquea la medicion (nadie la cambia de
# estado mientras se emite) y la finca (nadie le cambia el poligono entre la
# revision del traslape y la copia al certificado).
SELECT_PARA_EMITIR = (
    "SELECT m.id, m.finca, m.autor, m.revisada_por, m.biomasa_toneladas, "
    "       m.estado::text AS estado, f.nombre AS finca_nombre, f.zona, "
    "       f.propietario, ST_AsText(f.poligono) AS poligono_wkt, "
    "       p.etiqueta AS periodo_etiqueta "
    "FROM mediciones m "
    "JOIN fincas f ON f.id = m.finca "
    "JOIN periodos_medicion p ON p.id = m.periodo "
    "WHERE m.id = %s "
    "FOR UPDATE OF m FOR SHARE OF f")

# C6, la parte geografica. Dos fincas vecinas comparten un lindero: sus
# poligonos se tocan en el borde, y ST_Intersects solo diria que si. Eso
# impediria certificar al vecino de cualquier finca certificada. Lo que la
# minuta B4 prohibe es certificar dos veces el mismo terreno, asi que se pide
# que se crucen por dentro: se intersecan y no solo se tocan.
#
# El indice GiST parcial de la 009 hace que esto no recorra la tabla: solo
# mira los vigentes cuyo rectangulo envolvente toca el de la finca.
SELECT_TRASLAPE = (
    "SELECT EXISTS ("
    "  SELECT 1 FROM certificados c, fincas f "
    "  WHERE f.id = %s AND c.estado = 'VIGENTE' "
    "    AND ST_Intersects(c.poligono, f.poligono) "
    "    AND NOT ST_Touches(c.poligono, f.poligono)"
    ") AS traslapa")

INSERTAR = (
    "INSERT INTO certificados (id, medicion, poligono, toneladas, emitido_por, "
    "                          emitido_en, firma, llave_publica, documento) "
    "OVERRIDING SYSTEM VALUE "
    "SELECT %s, m.id, f.poligono, m.biomasa_toneladas, %s, %s, %s, %s, %s "
    "FROM mediciones m JOIN fincas f ON f.id = m.finca WHERE m.id = %s")


def atributos_certificado(fila: dict) -> dict:
    """C8 y, por si algun dia hiciera falta, la zona."""
    return {"finca.zona": fila["zona"],
            "finca.propietario_id": str(fila["propietario"])}


def atributos_emision(fila: dict, traslapa: bool) -> dict:
    """Lo que C6 necesita (contrato 02)."""
    return {"medicion.estado": fila["estado"],
            "medicion.autor_id": str(fila["autor"]),
            "contexto.poligono_traslapa_certificado_vigente": bool(traslapa)}


def autorizaciones_del_tercero(cur, sesion: SesionActiva) -> dict[int, dict]:
    """Para C9: finca -> atributos de la autorizacion que la cubre.

    Solo para el tercero autorizado; a los demas roles no les aplica C9 y se
    devuelve vacio. Solo autorizaciones sin revocar. Si hay varias de la misma
    finca se manda la que vence mas tarde.

    No se filtra por fecha aqui a proposito: la fecha la decide el motor
    (C9 compara hoy < vence). Asi una autorizacion vencida llega al motor y
    el motor la niega, que es lo que se quiere mostrar.
    """
    if sesion.rol != "TERCERO_AUTORIZADO":
        return {}
    cur.execute(
        "SELECT DISTINCT ON (finca) finca, tercero, vence "
        "FROM consentimientos "
        "WHERE tercero = %s AND revocado_en IS NULL "
        "ORDER BY finca, vence DESC", (sesion.cuenta,))
    return {f["finca"]: {"autorizacion.tercero_id": str(f["tercero"]),
                         "autorizacion.vence": f["vence"].isoformat()}
            for f in cur.fetchall()}


def previo_por_rol(sesion: SesionActiva,
                   autorizaciones: dict[int, dict]) -> tuple[str, tuple]:
    """Filtro SQL que ahorra preguntarle al motor por filas imposibles.

    Optimizacion, no control: el motor sigue decidiendo fila por fila. Que
    sobre un filtro nunca da acceso; que falte solo cuesta tiempo.
    """
    if sesion.rol == "DUENO_FINCA":
        return " AND f.propietario = %s", (sesion.cuenta,)
    if sesion.rol == "TERCERO_AUTORIZADO":
        return " AND m.finca = ANY(%s)", (list(autorizaciones),)
    return "", ()


def huella_de(fila: dict) -> str:
    return firma.huella(firma.desb64(fila["llave_publica"]))


def certificado_json(fila: dict) -> dict:
    # Las toneladas como texto: un numeric no debe pasar por un float.
    return {
        "id": fila["id"],
        "medicion": fila["medicion"],
        "finca": fila["finca"],
        "finca_nombre": fila["finca_nombre"],
        "zona": fila["zona"],
        "periodo_etiqueta": fila["periodo_etiqueta"],
        "toneladas": str(fila["toneladas"]),
        "estado": fila["estado"],
        "emitido_por": fila["emitido_por"],
        "emitido_en": fila["emitido_en"].isoformat(),
        "motivo_anulacion": fila["motivo_anulacion"],
        "anulado_en": (fila["anulado_en"].isoformat()
                       if fila["anulado_en"] else None),
        "huella_llave": huella_de(fila),
    }


def contenido_a_firmar(fila: dict, certificado: int, emisor: int,
                       momento) -> dict:
    """Lo que dice el certificado. Es lo unico que cubre la firma.

    Sin datos personales del dueno (LG-05): el certificado circula fuera de
    Verdeazul. Las personas van por su numero de cuenta, que permite a un
    auditor reconstruir la cadena (quien midio, quien aprobo, quien emitio)
    sin poner nombres en un documento publico.

    Sin numeros con decimales: todo valor es texto o entero.
    """
    return {
        "emisor": firma.EMISOR,
        "certificado": certificado,
        "medicion": fila["id"],
        "finca": fila["finca"],
        "finca_nombre": fila["finca_nombre"],
        "zona": fila["zona"],
        "periodo": fila["periodo_etiqueta"],
        "toneladas": str(fila["biomasa_toneladas"]),
        "poligono_wkt": fila["poligono_wkt"],
        "registrada_por": fila["autor"],
        "aprobada_por": fila["revisada_por"],
        "emitido_por": emisor,
        "emitido_en": firma.fecha_texto(momento),
    }
