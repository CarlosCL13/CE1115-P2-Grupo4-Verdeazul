"""O11 Bitacora de auditoria: consultar y exportar. Contrato 04.

    GET /bitacora            los eventos, del mas nuevo al mas viejo
    GET /bitacora/exportar   los mismos eventos, en CSV

La matriz sobre O11:

    Direccion General, Direccion de Certificacion    L, X
    Personal Administrativo                          L
    Auditor externo                                  L.C7, X.C7
    los demas roles                                  nada
    ningun rol                                       C, M, E

Nadie escribe aqui. La API lee la bitacora con log_reader, que solo tiene
SELECT sobre otra base (frontera F6): ni comprometiendo la API se puede
cambiar un evento ya transmitido. Escribir es del transmisor.

Cada consulta deja su propio evento (BITACORA_CONSULTADA, BITACORA_EXPORTADA)
en la bandeja de la base principal. Quien mira la bitacora tambien queda en
la bitacora, y un acceso denegado tambien: lo anota autorizar().

El auditor ve los eventos sin filtro de fechas. C7 decide CUANDO puede mirar
(hoy dentro de su ventana), no QUE: auditar un periodo exige ver lo que paso
en el. Los eventos no llevan datos personales (contrato 03), asi que LG-04 se
cumple sin recortar filas.
"""

import csv
import datetime
import io
import json

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app import bd
from app.auth.dependencias import SesionCompleta, autorizar
from app.bitacora.registrar import registrar
from app.certificacion import consultas as q
from app.errores import ErrorAPI

router = APIRouter(tags=["bitacora"])

# Tamanos de pagina que se aceptan. Cerrados: una pagina de 10 000 seria la
# misma carga masiva que el tope del CSV evita.
POR_PAGINA = (10, 25, 50)
POR_PAGINA_OMISION = 25

# Tope del CSV. La bitacora crece sin parar y un CSV sin tope es justo la
# carga masiva que §3.1 pide evitar. Para mas, se exporta por rango de fechas.
LIMITE_EXPORTACION = 5000

_COLUMNAS = ("secuencia, id, momento, accion, sujeto, objeto, resultado, "
             "motivo, detalle, eslabon")


def _filtro(*, desde, hasta, accion, sujeto, tipo, resultado):
    """Arma el WHERE. Los fragmentos son fijos; los valores van como %s."""
    partes, valores = [], []
    if desde is not None:
        partes.append("momento >= %s")
        valores.append(datetime.datetime.combine(
            desde, datetime.time.min, datetime.timezone.utc))
    if hasta is not None:
        # Hasta el final de ese dia, en UTC.
        partes.append("momento < %s")
        valores.append(datetime.datetime.combine(
            hasta + datetime.timedelta(days=1), datetime.time.min,
            datetime.timezone.utc))
    if accion:
        partes.append("accion = %s")
        valores.append(accion)
    if sujeto:
        partes.append("sujeto = %s")
        valores.append(sujeto)
    if tipo:
        # O3 -> objeto LIKE 'O3:%'. El patron de la consulta ya garantiza que
        # tipo es O1..O11, asi que no trae comodines propios.
        partes.append("objeto LIKE %s")
        valores.append(tipo + ":%")
    if resultado:
        partes.append("resultado = %s")
        valores.append(resultado)
    if desde is not None and hasta is not None and hasta < desde:
        raise ErrorAPI(422, "rango_invalido",
                       "La fecha final es anterior a la inicial.")
    donde = (" WHERE " + " AND ".join(partes)) if partes else ""
    return donde, tuple(valores)


def _leer(donde: str, valores: tuple, limite: int,
          desde_fila: int = 0) -> list[dict]:
    """Del mas nuevo al mas viejo. `desde_fila` es el OFFSET de la pagina."""
    with bd.lectura_bitacora() as cur:
        cur.execute("SELECT %s FROM eventos%s ORDER BY secuencia DESC "
                    "LIMIT %%s OFFSET %%s" % (_COLUMNAS, donde),
                    (*valores, limite, desde_fila))
        return cur.fetchall()


def _contar(donde: str, valores: tuple) -> int:
    with bd.lectura_bitacora() as cur:
        cur.execute("SELECT count(*) AS n FROM eventos%s" % donde, valores)
        return cur.fetchone()["n"]


def _usuarios(cur, filas: list[dict]) -> dict[str, str]:
    """El nombre de usuario de cada sujeto, para leer la tabla sin adivinar.

    El evento guarda el id de la cuenta y no el nombre, a proposito: un id no
    es un dato personal y no cambia. El nombre se busca aqui, al mostrar.
    """
    ids = sorted({f["sujeto"] for f in filas if f["sujeto"].isdigit()})
    if not ids:
        return {}
    cur.execute("SELECT id::text AS id, usuario FROM cuentas "
                "WHERE id::text = ANY(%s)", (ids,))
    return {f["id"]: f["usuario"] for f in cur.fetchall()}


def _json(fila: dict, usuarios: dict[str, str]) -> dict:
    return {
        "secuencia": fila["secuencia"],
        "id": str(fila["id"]),
        "momento": fila["momento"].astimezone(datetime.timezone.utc).isoformat(),
        "accion": fila["accion"],
        "sujeto": fila["sujeto"],
        "usuario": usuarios.get(fila["sujeto"]),
        "objeto": fila["objeto"],
        "resultado": fila["resultado"],
        "motivo": fila["motivo"],
        "detalle": fila["detalle"],
        "eslabon": fila["eslabon"],
    }


# Los parametros comunes de las dos rutas. Todos con forma cerrada: lo que no
# calza, FastAPI lo rechaza con 422 antes de entrar.
_DESDE = Query(default=None, description="AAAA-MM-DD, en UTC")
_HASTA = Query(default=None, description="AAAA-MM-DD, en UTC, incluido")
# Mayusculas, digitos y guion bajo, como los nombres de accion. Sin comillas,
# espacios ni % o _ sueltos de LIKE: igual va por igualdad y parametrizada.
_ACCION = Query(default=None, max_length=60, pattern="^[A-Z0-9_]+$")
# SISTEMA es quien actua en lo que hace el transmisor solo: revocar lo
# vencido (vencer) y comprobar la cadena (cadena).
_SUJETO = Query(default=None, max_length=40,
                pattern="^[0-9]+$|^ANONIMO$|^SISTEMA$")
_TIPO = Query(default=None, pattern="^O([1-9]|1[01])$")
_RESULTADO = Query(default=None, pattern="^(PERMITIDO|DENEGADO)$")


@router.get("/bitacora")
def consultar_bitacora(
        sesion: SesionCompleta,
        desde: datetime.date | None = _DESDE,
        hasta: datetime.date | None = _HASTA,
        accion: str | None = _ACCION,
        sujeto: str | None = _SUJETO,
        tipo: str | None = _TIPO,
        resultado: str | None = _RESULTADO,
        pagina: int = Query(default=1, gt=0, le=100_000),
        por_pagina: int = Query(default=POR_PAGINA_OMISION),
) -> dict:
    if por_pagina not in POR_PAGINA:
        raise ErrorAPI(422, "por_pagina_invalido",
                       "Se muestran 10, 25 o 50 eventos por página.")
    with bd.transaccion() as cur:
        # C7 depende de quien pregunta, no de la fila: un solo autorizar
        # decide todo el listado. Si niega, queda registrado y es 403.
        autorizar(sesion, "L", "O11", objeto="O11:*",
                  atributos=q.atributos_sujeto(cur, sesion))

        donde, valores = _filtro(desde=desde, hasta=hasta, accion=accion,
                                 sujeto=sujeto, tipo=tipo,
                                 resultado=resultado)
        total = _contar(donde, valores)
        paginas = max(1, -(-total // por_pagina))
        # Una pagina que ya no existe (por ejemplo, tras filtrar) muestra la
        # ultima en vez de una tabla vacia.
        pagina = min(pagina, paginas)
        filas = _leer(donde, valores, por_pagina, (pagina - 1) * por_pagina)
        usuarios = _usuarios(cur, filas)

        # Lo que todavia esta en la bandeja, sin transmitir. Ayuda a entender
        # por que una accion de hace un minuto no aparece aun (D-19).
        cur.execute("SELECT count(*) AS n FROM eventos_pendientes "
                    "WHERE enviado_en IS NULL")
        pendientes = cur.fetchone()["n"]

        registrar(accion="BITACORA_CONSULTADA", sujeto=sesion.sujeto.id,
                  objeto="O11:*", resultado="PERMITIDO",
                  detalle={"resultados": len(filas),
                           "filtros": {k: str(v) for k, v in (
                               ("desde", desde), ("hasta", hasta),
                               ("accion", accion), ("sujeto", sujeto),
                               ("tipo", tipo), ("resultado", resultado))
                               if v is not None}})

    return {
        "eventos": [_json(f, usuarios) for f in filas],
        "total": total,
        "pagina": pagina,
        "paginas": paginas,
        "por_pagina": por_pagina,
        # Posicion de la primera fila de la pagina, contando desde 1, para
        # que el borde numere "1-25 de 91" sin depender de la secuencia.
        "primera_fila": (pagina - 1) * por_pagina + 1 if filas else 0,
        "pendientes_de_transmitir": pendientes,
    }


@router.get("/bitacora/exportar")
def exportar_bitacora(
        sesion: SesionCompleta,
        desde: datetime.date | None = _DESDE,
        hasta: datetime.date | None = _HASTA,
        accion: str | None = _ACCION,
        sujeto: str | None = _SUJETO,
        tipo: str | None = _TIPO,
        resultado: str | None = _RESULTADO,
) -> Response:
    """CSV, igual que GET /mediciones/exportar. DG, DC y el auditor en su
    ventana. El personal administrativo puede leer, pero no exportar.

    Lleva el eslabon de cada evento y la secuencia, para que quien lo reciba
    pueda pedir despues que se compruebe la cadena sobre esas mismas filas
    (tarea `cadena` del transmisor, que tiene la llave).
    """
    with bd.transaccion() as cur:
        autorizar(sesion, "X", "O11", objeto="O11:*",
                  atributos=q.atributos_sujeto(cur, sesion))
        donde, valores = _filtro(desde=desde, hasta=hasta, accion=accion,
                                 sujeto=sujeto, tipo=tipo,
                                 resultado=resultado)
        filas = _leer(donde, valores, LIMITE_EXPORTACION)
        registrar(accion="BITACORA_EXPORTADA", sujeto=sesion.sujeto.id,
                  objeto="O11:*", resultado="PERMITIDO",
                  detalle={"filas": len(filas),
                           "truncado": len(filas) == LIMITE_EXPORTACION})

    salida = io.StringIO()
    escritor = csv.writer(salida, lineterminator="\n")
    escritor.writerow(["secuencia", "id", "momento", "accion", "sujeto",
                       "objeto", "resultado", "motivo", "detalle", "eslabon"])
    # En el CSV van en el orden de la cadena, del mas viejo al mas nuevo.
    for f in reversed(filas):
        escritor.writerow([
            f["secuencia"], f["id"],
            f["momento"].astimezone(datetime.timezone.utc).isoformat(),
            f["accion"], f["sujeto"], f["objeto"], f["resultado"],
            f["motivo"] or "",
            json.dumps(f["detalle"], sort_keys=True, ensure_ascii=False)
            if f["detalle"] is not None else "",
            f["eslabon"]])
    return Response(
        salida.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bitacora.csv"'})
