"""O1 Catalogo de fincas. Contrato 04, persona 4.

    GET   /fincas         lo que el sujeto puede ver
    GET   /fincas/{id}    una finca, con su poligono
    POST  /fincas         registrar una finca (Personal Administrativo)
    PATCH /fincas/{id}    corregir linderos o datos (Personal Administrativo)

La matriz sobre O1:

    Direccion General, Direccion de Certificacion    L
    Personal Administrativo                          L, C, M
    Tecnico de campo, Verificador                    L.C1, solo su zona
    Auditor externo                                  L.C7, solo en su ventana
    Dueno de finca                                   L.C8, solo la suya
    Tercero autorizado                               nada

El poligono se valida dos veces antes de guardarse (frontera F3). Primero la
forma, en Python, para que PostGIS nunca reciba algo que no sea un anillo
cerrado de coordenadas en rango. Despues ST_IsValid, que atrapa lo que solo la
geometria sabe, como un anillo que se cruza a si mismo. Sobre un poligono
invalido ST_Intersects devuelve cualquier cosa y C6 (persona 5) dejaria de
ser confiable, por eso la base ademas tiene un CHECK.
"""

import json
import math

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import bd
from app.auth.dependencias import SesionCompleta, autorizar, consultar
from app.bitacora import registrar
from app.certificacion import consultas as q
from app.errores import ErrorAPI

router = APIRouter(tags=["fincas"])

MAX_VERTICES = 500


class Poligono(BaseModel):
    type: str = Field(pattern="^Polygon$")
    coordinates: list[list[list[float]]]


class NuevaFinca(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    zona: str = Field(min_length=1, max_length=8)
    propietario: int = Field(gt=0)
    poligono: Poligono


class CambioFinca(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    zona: str | None = Field(default=None, min_length=1, max_length=8)
    propietario: int | None = Field(default=None, gt=0)
    poligono: Poligono | None = None


def _forma_del_poligono(poligono: Poligono) -> None:
    """Un solo anillo exterior, cerrado, con coordenadas de este planeta."""
    anillos = poligono.coordinates
    if len(anillos) != 1:
        raise ErrorAPI(422, "poligono_invalido",
                       "El polígono lleva un solo anillo, sin huecos.")
    anillo = anillos[0]
    if not 4 <= len(anillo) <= MAX_VERTICES:
        raise ErrorAPI(422, "poligono_invalido",
                       "El polígono necesita entre 4 y %d puntos." % MAX_VERTICES)
    for punto in anillo:
        if len(punto) != 2 or not all(math.isfinite(v) for v in punto):
            raise ErrorAPI(422, "poligono_invalido",
                           "Cada punto es [longitud, latitud].")
        longitud, latitud = punto
        if not (-180 <= longitud <= 180 and -90 <= latitud <= 90):
            raise ErrorAPI(422, "poligono_invalido",
                           "Una coordenada está fuera de rango.")
    if anillo[0] != anillo[-1]:
        raise ErrorAPI(422, "poligono_invalido",
                       "El anillo tiene que cerrar: el último punto es el primero.")


def _geometria_valida(cur, poligono: Poligono) -> str:
    """El poligono como texto GeoJSON, ya revisado por PostGIS."""
    texto = json.dumps({"type": "Polygon",
                        "coordinates": poligono.coordinates})
    cur.execute(
        "SELECT ST_IsValid(g) AS valido, ST_IsValidReason(g) AS razon "
        "FROM (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS g) t",
        (texto,))
    fila = cur.fetchone()
    if not fila["valido"]:
        raise ErrorAPI(422, "poligono_invalido",
                       "El polígono no es válido: %s." % fila["razon"])
    return texto


def _revisar_zona_y_dueno(cur, zona: str | None, propietario: int | None):
    if zona is not None:
        cur.execute("SELECT 1 FROM zonas WHERE id = %s", (zona,))
        if cur.fetchone() is None:
            raise ErrorAPI(422, "zona_inexistente", "Esa zona no existe.")
    if propietario is not None:
        cur.execute("SELECT 1 FROM cuentas WHERE id = %s AND activa "
                    "AND rol = 'DUENO_FINCA'", (propietario,))
        if cur.fetchone() is None:
            raise ErrorAPI(422, "propietario_invalido",
                           "El propietario tiene que ser una cuenta activa de "
                           "dueño de finca.")


def inexistente(cur, sesion, operacion: str, tipo: str, objeto: str):
    """404 para quien podria verlo todo, 403 para quien no.

    Si el sujeto no tiene permiso sobre ninguna fila concreta, decirle "no
    existe" le dejaria averiguar que ids existen comparando con el 403 de los
    que si. Se pregunta al motor con lo unico que se sabe del sujeto, y si
    niega responde igual que ante una finca ajena.
    """
    autorizar(sesion, operacion, tipo, objeto=objeto,
              atributos=q.atributos_sujeto(cur, sesion))
    raise ErrorAPI(404, "no_existe")


@router.get("/fincas")
def listar_fincas(sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        propios = q.atributos_sujeto(cur, sesion)
        general = consultar(sesion, "L", "O1", propios)
        # El auditor no filtra fila por fila: su unica condicion (C7) es de
        # el y no de la fila. Sin ventana vigente no hay permiso que filtrar.
        if not general.permitido and (
                general.condicion is None or sesion.rol == "AUDITOR_EXTERNO"):
            autorizar(sesion, "L", "O1", objeto="O1:*", atributos=propios)

        filtro, parametros = q.previo_por_rol(sesion)
        cur.execute(q.SELECT_FINCA + "WHERE true" + filtro +
                    " ORDER BY f.id LIMIT %s",
                    (*parametros, q.LIMITE_LISTADO))
        visibles = []
        for fila in cur.fetchall():
            if not general.permitido and not consultar(
                    sesion, "L", "O1",
                    {**propios, **q.atributos_finca(fila)}).permitido:
                continue
            visibles.append(q.finca_json(fila))
        registrar(accion="FINCAS_LISTADAS", sujeto=sesion.sujeto.id,
                  objeto="O1:*", resultado="PERMITIDO",
                  detalle={"resultados": len(visibles)})
    return {"fincas": visibles}


@router.get("/fincas/{finca_id}")
def ver_finca(finca_id: int, sesion: SesionCompleta) -> dict:
    with bd.transaccion() as cur:
        cur.execute(q.SELECT_FINCA + "WHERE f.id = %s", (finca_id,))
        fila = cur.fetchone()
        objeto = "O1:%d" % finca_id
        if fila is None:
            inexistente(cur, sesion, "L", "O1", objeto)
        autorizar(sesion, "L", "O1", objeto=objeto, atributos={
            **q.atributos_sujeto(cur, sesion), **q.atributos_finca(fila)})
    return q.finca_json(fila)


@router.post("/fincas", status_code=201)
def crear_finca(datos: NuevaFinca, sesion: SesionCompleta) -> dict:
    _forma_del_poligono(datos.poligono)
    with bd.transaccion() as cur:
        autorizar(sesion, "C", "O1", objeto="O1:nueva")
        _revisar_zona_y_dueno(cur, datos.zona, datos.propietario)
        texto = _geometria_valida(cur, datos.poligono)
        cur.execute(
            "INSERT INTO fincas (nombre, zona, propietario, poligono) "
            "VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) "
            "RETURNING id", (datos.nombre, datos.zona, datos.propietario, texto))
        nueva = cur.fetchone()["id"]
        registrar(accion="FINCA_REGISTRADA", sujeto=sesion.sujeto.id,
                  objeto="O1:%d" % nueva, resultado="PERMITIDO",
                  detalle={"zona": datos.zona})
    return {"id": nueva}


@router.patch("/fincas/{finca_id}")
def corregir_finca(finca_id: int, datos: CambioFinca,
                   sesion: SesionCompleta) -> dict:
    if datos.model_dump(exclude_none=True) == {}:
        raise ErrorAPI(422, "sin_cambios")
    if datos.poligono is not None:
        _forma_del_poligono(datos.poligono)

    with bd.transaccion() as cur:
        cur.execute(q.SELECT_FINCA + "WHERE f.id = %s FOR UPDATE OF f",
                    (finca_id,))
        fila = cur.fetchone()
        objeto = "O1:%d" % finca_id
        if fila is None:
            inexistente(cur, sesion, "M", "O1", objeto)
        autorizar(sesion, "M", "O1", objeto=objeto,
                  atributos=q.atributos_finca(fila))
        _revisar_zona_y_dueno(cur, datos.zona, datos.propietario)

        cambios: dict[str, object] = {}
        for campo in ("nombre", "zona", "propietario"):
            if getattr(datos, campo) is not None:
                cambios[campo] = getattr(datos, campo)
        if datos.poligono is not None:
            texto = _geometria_valida(cur, datos.poligono)
        # Los nombres de columna salen de las tuplas de arriba, nunca de lo
        # que manda el usuario. Los valores van como parametros.
        asignaciones = [("%s = %%s" % c, v) for c, v in cambios.items()]
        if datos.poligono is not None:
            asignaciones.append(
                ("poligono = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)", texto))
        cur.execute("UPDATE fincas SET %s WHERE id = %%s" %
                    ", ".join(a for a, _ in asignaciones),
                    (*(v for _, v in asignaciones), finca_id))
        registrar(accion="FINCA_CORREGIDA", sujeto=sesion.sujeto.id,
                  objeto=objeto, resultado="PERMITIDO",
                  detalle={"campos": sorted(
                      [*cambios, *(["poligono"] if datos.poligono else [])])})
    return {"id": finca_id, "corregida": True}
