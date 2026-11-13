"""La tarea volcado sin base ni Cloud Storage: lo que sube, en que orden, y
que la copia se pueda verificar por fuera con la llave de la cadena."""

import datetime
import gzip
import hashlib
import json

import pytest

from app import eslabon
from app.tareas import volcado
from test_cadena import bitacora
from test_transmitir import LLAVE, Cursor, abridor

AHORA = datetime.datetime(2026, 11, 14, 6, 0, 5, tzinfo=datetime.timezone.utc)


def correr(diario, filas, subidas, *, fallar_subida=False):
    def subir(nombre, contenido, tipo):
        if fallar_subida:
            raise RuntimeError("Cloud Storage no responde")
        subidas.append((nombre, contenido, tipo))
        return {"generation": "1731564005000000", "name": nombre}

    bandeja = Cursor("bandeja", diario)
    lotes = [filas[i:i + 4] for i in range(0, len(filas), 4)] + [[]]
    lectura = Cursor("lectura", diario, respuestas=lotes)
    return volcado.ejecutar(llave=LLAVE, abrir_bandeja=abridor(bandeja),
                            abrir_lectura=abridor(lectura), subir=subir,
                            ahora=AHORA)


def _lineas(contenido: bytes) -> list[dict]:
    return [json.loads(l) for l in gzip.decompress(contenido).splitlines()]


def test_sube_los_eventos_y_despues_el_manifiesto():
    diario, subidas = [], []
    r = correr(diario, bitacora(10), subidas)
    nombres = [s[0] for s in subidas]
    assert nombres == [
        "bitacora/2026/11/14/bitacora-20261114T060005Z.jsonl.gz",
        "bitacora/2026/11/14/bitacora-20261114T060005Z.json",
    ]
    assert [s[2] for s in subidas] == ["application/gzip", "application/json"]
    assert r["eventos"] == 10 and r["cadena_intacta"] is True


def test_el_manifiesto_describe_el_archivo():
    diario, subidas = [], []
    filas = bitacora(7, primera_secuencia=8)
    correr(diario, filas, subidas)
    contenido = subidas[0][1]
    m = json.loads(subidas[1][1])
    assert m["sha256"] == hashlib.sha256(contenido).hexdigest()
    assert m["bytes"] == len(contenido)
    assert (m["eventos"], m["secuencia_primera"], m["secuencia_ultima"]) == (7, 8, 14)
    assert m["ultimo_eslabon"] == filas[-1]["eslabon"]
    assert m["archivo"] == subidas[0][0]
    assert m["formato"] == "verdeazul-bitacora-jsonl-v1"


def test_la_copia_se_verifica_por_fuera_con_la_llave():
    """Lo que promete D-03: con el archivo y la llave, sin Neon, se
    recalcula cada eslabon."""
    diario, subidas = [], []
    correr(diario, bitacora(12, saltos=(5,)), subidas)
    anterior = eslabon.INICIO
    for evento in _lineas(subidas[0][1]):
        evento["momento"] = datetime.datetime.fromisoformat(evento["momento"])
        assert eslabon.calcular(LLAVE, anterior, evento) == evento["eslabon"]
        anterior = evento["eslabon"]


def test_una_linea_alterada_en_la_copia_no_cuadra():
    diario, subidas = [], []
    correr(diario, bitacora(5), subidas)
    eventos = _lineas(subidas[0][1])
    eventos[2]["sujeto"] = "99"
    evento = {**eventos[2],
              "momento": datetime.datetime.fromisoformat(eventos[2]["momento"])}
    assert eslabon.calcular(LLAVE, eventos[1]["eslabon"], evento) != eventos[2]["eslabon"]


def test_el_mismo_contenido_da_el_mismo_archivo():
    a, b = [], []
    correr([], bitacora(6), a)
    correr([], bitacora(6), b)
    assert a[0][1] == b[0][1]


def test_una_cadena_rota_se_copia_igual_y_lo_dice():
    diario, subidas = [], []
    filas = bitacora(6)
    filas[3] = {**filas[3], "objeto": "O3:999"}
    r = correr(diario, filas, subidas)
    assert len(subidas) == 2
    assert r["cadena_intacta"] is False and r["eslabones_rotos"] == 1
    assert json.loads(subidas[1][1])["cadena_intacta"] is False


def test_deja_constancia_en_la_bitacora_y_toma_el_candado():
    diario, subidas = [], []
    correr(diario, bitacora(3), subidas)
    assert "pg_advisory_xact_lock" in diario[0][1]
    inserts = [d for d in diario if d[0] == "bandeja" and d[1].startswith("INSERT")]
    (accion, sujeto, objeto, detalle), = inserts[0][2]
    assert (accion, sujeto, objeto) == ("VOLCADO_REALIZADO", "SISTEMA", "O11:*")
    assert detalle.obj["archivo"].endswith(".jsonl.gz")
    assert detalle.obj["sha256"] == hashlib.sha256(subidas[0][1]).hexdigest()
    assert diario[-1] == ("bandeja", "COMMIT", None)


def test_si_la_subida_falla_no_queda_evento():
    diario = []
    with pytest.raises(RuntimeError):
        correr(diario, bitacora(3), [], fallar_subida=True)
    assert not [d for d in diario if d[1].startswith("INSERT")]
    assert diario[-1] == ("bandeja", "ROLLBACK", None)


def test_una_bitacora_vacia_tambien_se_copia():
    diario, subidas = [], []
    r = correr(diario, [], subidas)
    assert r["eventos"] == 0 and gzip.decompress(subidas[0][1]) == b""
