"""SQL y atributos de O5. El motor decide; este modulo le arma lo que necesita.

    C6  medicion.estado, medicion.autor_id,
        contexto.poligono_traslapa_certificado_vigente   lo calcula aqui
"""

from app.certificados import firma

# Dos enteros y no uno: pg_advisory_xact_lock(int, int) y
# pg_advisory_xact_lock(bigint) son espacios de llaves separados, asi que este
# candado no puede chocar con el 42 del transmisor. 5 por O5, 6 por C6.
CANDADO_EMISION = "SELECT pg_advisory_xact_lock(5, 6)"

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


def atributos_emision(fila: dict, traslapa: bool) -> dict:
    """Lo que C6 necesita (contrato 02)."""
    return {"medicion.estado": fila["estado"],
            "medicion.autor_id": str(fila["autor"]),
            "contexto.poligono_traslapa_certificado_vigente": bool(traslapa)}


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
