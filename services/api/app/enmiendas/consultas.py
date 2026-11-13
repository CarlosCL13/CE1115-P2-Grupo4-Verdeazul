"""Consultas y atributos de O4. Lo que el motor necesita de cada enmienda.

    C1   finca.zona                la zona de la finca de la medicion
    C4   enmienda.solicitante_id   quien la pidio
    C5   enmienda.estado, enmienda.solicitante_id, enmienda.revisor_id
    C7   auditoria.inicio / fin    (de quien pregunta: certificacion.consultas)
    C8   finca.propietario_id      el dueno de la finca
    C11  medicion.autor_id, periodo.estado

Todo id viaja como texto (contrato 02). autorizar() lo convierte igual, pero
aqui ya sale asi.
"""

SELECT_ENMIENDA = (
    "SELECT e.id, e.medicion, e.solicitante, e.justificacion, "
    "       e.estado::text AS estado, e.revisor, e.revisada_en, "
    "       e.cerrada_por, e.cerrada_en, e.solicitada_en, "
    "       m.autor AS medicion_autor, m.biomasa_toneladas, "
    "       m.estado::text AS medicion_estado, m.finca, m.periodo, "
    "       f.zona, f.propietario, "
    "       p.estado::text AS periodo_estado, p.etiqueta AS periodo_etiqueta, "
    "       cs.usuario AS solicitante_usuario, cr.usuario AS revisor_usuario, "
    "       cc.usuario AS cerrada_por_usuario "
    "FROM enmiendas e "
    "JOIN mediciones m ON m.id = e.medicion "
    "JOIN fincas f ON f.id = m.finca "
    "JOIN periodos_medicion p ON p.id = m.periodo "
    "JOIN cuentas cs ON cs.id = e.solicitante "
    "LEFT JOIN cuentas cr ON cr.id = e.revisor "
    "LEFT JOIN cuentas cc ON cc.id = e.cerrada_por ")


def _texto(valor) -> str | None:
    return None if valor is None else str(valor)


def atributos_enmienda(fila: dict) -> dict:
    return {
        "finca.zona": fila["zona"],
        "finca.propietario_id": _texto(fila["propietario"]),
        "enmienda.estado": fila["estado"],
        "enmienda.solicitante_id": _texto(fila["solicitante"]),
        "enmienda.revisor_id": _texto(fila["revisor"]),
        "medicion.autor_id": _texto(fila["medicion_autor"]),
        "periodo.estado": fila["periodo_estado"],
    }


def _fecha(valor) -> str | None:
    return valor.isoformat() if valor else None


def enmienda_json(fila: dict) -> dict:
    return {
        "id": fila["id"],
        "medicion": fila["medicion"],
        "finca": fila["finca"],
        "periodo": fila["periodo"],
        "periodo_etiqueta": fila["periodo_etiqueta"],
        # Texto, no float: un numeric no pasa por coma flotante.
        "biomasa_toneladas": str(fila["biomasa_toneladas"]),
        "justificacion": fila["justificacion"],
        "estado": fila["estado"],
        "solicitante": fila["solicitante"],
        "solicitante_usuario": fila["solicitante_usuario"],
        "revisor": fila["revisor"],
        "revisor_usuario": fila["revisor_usuario"],
        "revisada_en": _fecha(fila["revisada_en"]),
        "cerrada_por": fila["cerrada_por"],
        "cerrada_por_usuario": fila["cerrada_por_usuario"],
        "cerrada_en": _fecha(fila["cerrada_en"]),
        "solicitada_en": _fecha(fila["solicitada_en"]),
    }
