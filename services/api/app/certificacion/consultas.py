"""Lo que comparten los tres objetos de certificacion: consultas y atributos.

Cada condicion de la matriz se decide en el motor (contrato 02), pero el motor
solo ve lo que el endpoint le manda. Este modulo arma esos atributos en un solo
lugar para que O1, O2 y O3 no los calculen cada uno a su manera:

    C1  finca.zona               la zona de la finca
    C2  periodo.estado           ABIERTO o CERRADO
    C3  medicion.autor_id        quien registro la medicion
        contexto.sujeto_midio_en_finca_periodo   lo calcula aqui
    C7  auditoria.inicio / fin   la ventana vigente del auditor
    C8  finca.propietario_id     el dueno de la finca

Todo id viaja como texto. Un entero hace que las comparaciones `!=` del motor
concedan de mas (contrato 02).
"""

import datetime

from app.auth.sesiones import SesionActiva

LIMITE_LISTADO = 200


def atributos_sujeto(cur, sesion: SesionActiva) -> dict:
    """Lo que depende de quien pregunta y no de la fila: la ventana de C7.

    Si el auditor no tiene ninguna ventana vigente hoy no se manda nada. Un
    atributo ausente hace que C7 no se cumpla, y el permiso deja de existir
    (HBAC-03). Con varias ventanas se usa la que encierra hoy.
    """
    if sesion.rol != "AUDITOR_EXTERNO":
        return {}
    hoy = datetime.date.today()
    cur.execute(
        "SELECT inicio, fin FROM ventanas_auditoria "
        "WHERE auditor = %s AND inicio <= %s AND fin >= %s "
        "ORDER BY fin DESC LIMIT 1", (sesion.cuenta, hoy, hoy))
    ventana = cur.fetchone()
    if ventana is None:
        return {}
    return {"auditoria.inicio": ventana["inicio"].isoformat(),
            "auditoria.fin": ventana["fin"].isoformat()}


def atributos_finca(finca: dict) -> dict:
    return {"finca.zona": finca["zona"],
            "finca.propietario_id": str(finca["propietario"])}


def atributos_medicion(medicion: dict) -> dict:
    return {**atributos_finca(medicion),
            "periodo.estado": medicion["periodo_estado"],
            "medicion.estado": medicion["estado"],
            "medicion.autor_id": str(medicion["autor"])}


def sujeto_midio_en_finca_periodo(cur, sesion: SesionActiva, finca: int,
                                  periodo: int, excepto: int) -> bool:
    """Contexto de C3: el sujeto registro otra medicion de esa finca y periodo.

    `excepto` es la medicion que se esta decidiendo. Que el sujeto sea su
    autor ya lo cubre la otra mitad de C3 (autor distinto del sujeto).
    """
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM mediciones WHERE finca = %s "
        "AND periodo = %s AND autor = %s AND id <> %s) AS midio",
        (finca, periodo, sesion.cuenta, excepto))
    return cur.fetchone()["midio"]


def previo_por_rol(sesion: SesionActiva, objeto: str = "O1") -> tuple[str, tuple]:
    """Un filtro SQL que ahorra preguntar al motor por filas que no pueden ser.

    Es solo una optimizacion: el motor sigue decidiendo cada fila. Que un
    filtro de aqui sobrara nunca da acceso, y que faltara solo cuesta tiempo.
    `f` es el alias de la tabla fincas en quien lo use.
    """
    # La matriz da al verificador lectura sin condicion sobre O3 (mediciones)
    # y con condicion de zona sobre O1 (fincas). El tecnico tiene zona en ambos.
    zona_aplica = sesion.rol == "TECNICO_CAMPO" or (
        sesion.rol == "VERIFICADOR" and objeto == "O1"
    )
    if zona_aplica:
        return " AND f.zona = ANY(%s)", (list(sesion.zonas),)
    if sesion.rol == "DUENO_FINCA":
        return " AND f.propietario = %s", (sesion.cuenta,)
    return "", ()


SELECT_FINCA = (
    "SELECT f.id, f.nombre, f.zona, f.propietario, f.registrada_en, "
    "       ST_AsGeoJSON(f.poligono)::jsonb AS poligono "
    "FROM fincas f ")

SELECT_MEDICION = (
    "SELECT m.id, m.finca, m.periodo, m.autor, m.biomasa_toneladas, "
    "       m.estado::text AS estado, m.revisada_por, m.revisada_en, "
    "       m.motivo_devolucion, m.registrada_en, "
    "       f.zona, f.propietario, p.estado::text AS periodo_estado, "
    "       p.etiqueta AS periodo_etiqueta "
    "FROM mediciones m JOIN fincas f ON f.id = m.finca "
    "JOIN periodos_medicion p ON p.id = m.periodo ")


def finca_json(fila: dict) -> dict:
    return {"id": fila["id"], "nombre": fila["nombre"], "zona": fila["zona"],
            "propietario": fila["propietario"],
            "poligono": fila["poligono"],
            "registrada_en": fila["registrada_en"].isoformat()}


def periodo_json(fila: dict) -> dict:
    return {"id": fila["id"], "etiqueta": fila["etiqueta"],
            "estado": str(fila["estado"]),
            "abierto_en": fila["abierto_en"].isoformat(),
            "cerrado_en": (fila["cerrado_en"].isoformat()
                           if fila["cerrado_en"] else None)}


def medicion_json(fila: dict) -> dict:
    # La biomasa va como texto: un numeric no debe pasar por un float.
    return {"id": fila["id"], "finca": fila["finca"],
            "periodo": fila["periodo"], "periodo_etiqueta":
            fila["periodo_etiqueta"], "autor": fila["autor"],
            "biomasa_toneladas": str(fila["biomasa_toneladas"]),
            "estado": fila["estado"], "revisada_por": fila["revisada_por"],
            "revisada_en": (fila["revisada_en"].isoformat()
                            if fila["revisada_en"] else None),
            "motivo_devolucion": fila["motivo_devolucion"],
            "registrada_en": fila["registrada_en"].isoformat()}
