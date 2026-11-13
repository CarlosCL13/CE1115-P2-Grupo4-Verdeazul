"""La tarea cadena: detectar un evento alterado, uno borrado y una cola
recortada, sin base. La bitacora es una lista de filas selladas con la misma
funcion que usa transmitir."""

import pytest

from app import eslabon
from app.tareas import cadena, transmitir
from test_transmitir import LLAVE, Cursor, abridor, fila


def bitacora(n, primera_secuencia=1, saltos=()):
    """n eventos sellados como los dejaria transmitir, con su secuencia."""
    sellados = transmitir.sellar(LLAVE, eslabon.INICIO,
                                 [fila(i) for i in range(1, n + 1)])
    filas, secuencia = [], primera_secuencia
    for i, (_, evento, sello) in enumerate(sellados, start=1):
        if i in saltos:
            secuencia += 3  # un INSERT que fallo gasto numeros
        filas.append({**evento, "secuencia": secuencia, "eslabon": sello})
        secuencia += 1
    return filas


# ---------------------------------------------------------------------------
# El recorrido
# ---------------------------------------------------------------------------

def test_una_cadena_sana_cuadra_entera():
    filas = bitacora(20)
    r = cadena.recorrer(LLAVE, [filas[:7], filas[7:]])
    assert (r["eventos"], r["rotos"], r["primer_roto"]) == (20, 0, None)
    assert r["ultimo_eslabon"] == filas[-1]["eslabon"]


def test_los_huecos_de_secuencia_no_son_borrados():
    r = cadena.recorrer(LLAVE, [bitacora(10, saltos=(3, 8))])
    assert r["rotos"] == 0


def test_un_evento_modificado_se_marca_solo_el():
    filas = bitacora(10)
    filas[4] = {**filas[4], "detalle": {"periodo": "9"}}
    r = cadena.recorrer(LLAVE, [filas])
    assert (r["rotos"], r["primer_roto"]) == (1, filas[4]["secuencia"])


@pytest.mark.parametrize("campo, valor", [
    ("accion", "MEDICION_APROBADA"),
    ("sujeto", "99"),
    ("resultado", "DENEGADO"),
])
def test_cualquier_campo_alterado_se_detecta(campo, valor):
    filas = bitacora(5)
    filas[2] = {**filas[2], campo: valor}
    assert cadena.recorrer(LLAVE, [filas])["primer_roto"] == filas[2]["secuencia"]


def test_un_evento_borrado_del_medio_rompe_el_siguiente():
    filas = bitacora(10)
    borrado = filas.pop(5)
    r = cadena.recorrer(LLAVE, [filas])
    assert r["rotos"] == 1
    assert r["primer_roto"] == borrado["secuencia"] + 1


def test_un_eslabon_inventado_sin_la_llave_no_cuadra():
    filas = bitacora(5)
    falso = eslabon.calcular(bytes(32), filas[1]["eslabon"], filas[2])
    filas[2] = {**filas[2], "eslabon": falso}
    # Se marca ese y el siguiente, que se encadeno con el eslabon verdadero.
    assert cadena.recorrer(LLAVE, [filas])["rotos"] == 2


def test_una_bitacora_vacia():
    r = cadena.recorrer(LLAVE, [])
    assert (r["eventos"], r["rotos"], r["ultimo_eslabon"]) == (0, 0, eslabon.INICIO)


# ---------------------------------------------------------------------------
# La corrida completa, con la cola de la bandeja
# ---------------------------------------------------------------------------

def correr(diario, filas, *, enviados=None, ultimo=None, tamano=4):
    enviados = len(filas) if enviados is None else enviados
    if ultimo is None:
        ultimo = filas[-1]["eslabon"] if filas else None
    bandeja = Cursor("bandeja", diario, respuestas=[
        {"n": enviados}, {"eslabon": ultimo} if ultimo else None])
    lotes = [filas[i:i + tamano] for i in range(0, len(filas), tamano)] + [[]]
    lectura = Cursor("lectura", diario, respuestas=lotes)
    return cadena.ejecutar(llave=LLAVE, tamano=tamano,
                           abrir_bandeja=abridor(bandeja),
                           abrir_lectura=abridor(lectura))


def _evento_anotado(diario):
    inserts = [d for d in diario if d[0] == "bandeja" and d[1].startswith("INSERT")]
    assert len(inserts) == 1
    (accion, sujeto, objeto, detalle), = inserts[0][2]
    return accion, sujeto, objeto, detalle.obj


def test_intacta_deja_constancia_en_la_bitacora():
    diario = []
    r = correr(diario, bitacora(10))
    assert r["intacta"] and r["cola_completa"] and r["eventos"] == 10
    accion, sujeto, objeto, detalle = _evento_anotado(diario)
    assert (accion, sujeto, objeto) == ("CADENA_VERIFICADA", "SISTEMA", "O11:*")
    assert detalle["eventos"] == 10
    # El candado va primero, igual que en transmitir.
    assert "pg_advisory_xact_lock" in diario[0][1]
    assert diario[-1] == ("bandeja", "COMMIT", None)


def test_lee_por_lotes_avanzando_por_secuencia():
    diario = []
    correr(diario, bitacora(10), tamano=4)
    lecturas = [d[2] for d in diario if d[0] == "lectura" and "FROM eventos" in d[1]]
    assert [desde for desde, _ in lecturas] == [0, 4, 8, 10]


def test_borrar_los_ultimos_eventos_se_ve_en_la_cola():
    diario = []
    filas = bitacora(10)
    # La bandeja dice que se enviaron 10; a la bitacora le quitaron 2.
    r = correr(diario, filas[:8], enviados=10, ultimo=filas[-1]["eslabon"])
    assert r["rotos"] == 0           # lo que queda cuadra solo
    assert r["cola_completa"] is False
    assert r["intacta"] is False
    assert _evento_anotado(diario)[0] == "CADENA_ROTA"


def test_un_evento_alterado_marca_la_cadena_rota():
    diario = []
    filas = bitacora(6)
    filas[3] = {**filas[3], "objeto": "O3:999"}
    r = correr(diario, filas)
    assert r["intacta"] is False and r["primer_roto"] == filas[3]["secuencia"]


def test_sin_eventos_todavia():
    diario = []
    r = correr(diario, [], enviados=0)
    assert r["intacta"] and r["eventos"] == 0
