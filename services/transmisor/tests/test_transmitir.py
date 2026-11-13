"""La tarea transmitir contra dos bases de mentira.

La bandeja y la bitacora son cursores falsos que anotan lo que se les pide en
un diario, en orden. Asi se comprueban las reglas del README: el candado va
primero, la bitacora se confirma antes de tocar la bandeja, un fallo a la
mitad no deja nada marcado y reintentar no duplica.
"""

import contextlib
from datetime import datetime, timedelta, timezone

import pytest

from app import eslabon
from app.tareas import transmitir

LLAVE = bytes(range(32))
T0 = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)


def fila(i, **cambios):
    base = {
        "id": i,
        "momento": T0 + timedelta(seconds=i),
        "accion": "MEDICION_REGISTRADA",
        "sujeto": "4",
        "objeto": f"O3:{i}",
        "resultado": "PERMITIDO",
        "motivo": None,
        "detalle": {"periodo": "2"},
    }
    base.update(cambios)
    return base


class Cursor:
    def __init__(self, nombre, diario, respuestas=(), fallar_en=None,
                 almacen=None):
        self.nombre = nombre
        self.diario = diario
        self.respuestas = list(respuestas)
        self.fallar_en = fallar_en
        self.almacen = almacen

    def _quizas_fallar(self, sql):
        if self.fallar_en and self.fallar_en in sql:
            raise RuntimeError("fallo simulado en " + self.nombre)

    def execute(self, sql, params=None):
        self.diario.append((self.nombre, sql, params))
        self._quizas_fallar(sql)

    def executemany(self, sql, filas):
        filas = list(filas)
        self.diario.append((self.nombre, sql, filas))
        self._quizas_fallar(sql)
        if self.almacen is not None and sql.startswith("INSERT"):
            for f in filas:
                # ON CONFLICT DO NOTHING sobre el uuid.
                self.almacen.setdefault(f[0], f)

    def fetchone(self):
        return self.respuestas.pop(0)

    def fetchall(self):
        return self.respuestas.pop(0)


def abridor(cursor):
    @contextlib.contextmanager
    def abrir():
        try:
            yield cursor
        except BaseException:
            cursor.diario.append((cursor.nombre, "ROLLBACK", None))
            raise
        else:
            cursor.diario.append((cursor.nombre, "COMMIT", None))
    return abrir


def correr(diario, *, ultimo=None, lote=(), tope=500, margen=120,
           fallar_bandeja=None, fallar_bitacora=None, almacen=None):
    bandeja = Cursor("bandeja", diario,
                     respuestas=[ultimo, list(lote)], fallar_en=fallar_bandeja)
    bitacora = Cursor("bitacora", diario, fallar_en=fallar_bitacora,
                      almacen=almacen)
    return transmitir.ejecutar(llave=LLAVE, tope=tope, margen=margen,
                               abrir_bandeja=abridor(bandeja),
                               abrir_bitacora=abridor(bitacora))


def pasos(diario):
    """El diario resumido: quien, y la primera palabra de lo que hizo."""
    return [(quien, sql.split()[0]) for quien, sql, _ in diario]


def encadenar_a_mano(anterior, filas):
    sellos = []
    for f in filas:
        ev = {**f, "id": eslabon.id_en_bitacora(f["id"])}
        anterior = eslabon.calcular(LLAVE, anterior, ev)
        sellos.append(anterior)
    return sellos


# ---------------------------------------------------------------------------

def test_sin_pendientes_no_abre_la_bitacora():
    diario = []
    r = correr(diario, lote=[])
    assert r == {"tarea": "transmitir", "transmitidos": 0, "quedan_mas": False}
    assert all(quien == "bandeja" for quien, _, _ in diario)
    assert diario[-1][1] == "COMMIT"


def test_el_orden_de_los_pasos():
    diario = []
    correr(diario, lote=[fila(1), fila(2)])
    assert pasos(diario) == [
        ("bandeja", "SELECT"),    # candado
        ("bandeja", "SELECT"),    # ultimo eslabon
        ("bandeja", "SELECT"),    # lote
        ("bitacora", "INSERT"),
        ("bitacora", "COMMIT"),   # la bitacora se confirma primero
        ("bandeja", "UPDATE"),
        ("bandeja", "COMMIT"),
    ]
    assert "pg_advisory_xact_lock" in diario[0][1]
    assert diario[0][2] == (transmitir.CANDADO,)


def test_la_primera_corrida_empieza_desde_el_inicio():
    diario = []
    lote = [fila(1), fila(2), fila(3)]
    correr(diario, ultimo=None, lote=lote)

    insertadas = diario[3][2]
    marcadas = diario[5][2]
    esperados = encadenar_a_mano(eslabon.INICIO, lote)

    assert [f[-1] for f in insertadas] == esperados
    assert [m[0] for m in marcadas] == esperados
    assert [m[1] for m in marcadas] == [1, 2, 3]
    # Mismo eslabon en las dos bases, para cada evento.
    assert [f[-1] for f in insertadas] == [m[0] for m in marcadas]


def test_sigue_desde_el_ultimo_eslabon_enviado():
    diario = []
    anterior = "a" * 64
    lote = [fila(7), fila(8)]
    correr(diario, ultimo={"eslabon": anterior}, lote=lote)
    assert [f[-1] for f in diario[3][2]] == encadenar_a_mano(anterior, lote)


def test_el_punto_de_partida_es_el_orden_de_envio_no_el_id():
    # Un evento con id menor que se confirmo tarde sale en un lote posterior.
    # El ultimo encadenado es el del ultimo lote, no el de id mas alto.
    assert "ORDER BY enviado_en DESC, id DESC" in transmitir._ULTIMO_ESLABON


def test_copia_el_momento_de_la_operacion():
    diario = []
    f = fila(1)
    correr(diario, lote=[f])
    assert diario[3][2][0][1] == f["momento"]


def test_el_id_de_la_bitacora_sale_del_de_la_bandeja():
    diario = []
    correr(diario, lote=[fila(15)])
    assert diario[3][2][0][0] == eslabon.id_en_bitacora(15)


def test_detalle_vacio_va_como_null():
    diario = []
    correr(diario, lote=[fila(1, detalle=None), fila(2)])
    insertadas = diario[3][2]
    assert insertadas[0][7] is None
    assert insertadas[1][7].obj == {"periodo": "2"}


def test_resultado_del_enum_se_copia_como_texto():
    class Enum(str):
        pass
    diario = []
    correr(diario, lote=[fila(1, resultado=Enum("DENEGADO"), motivo="C3")])
    assert type(diario[3][2][0][5]) is str


def test_tope_y_margen_van_a_la_consulta():
    diario = []
    correr(diario, lote=[fila(1), fila(2)], tope=2, margen=30)
    assert diario[2][2] == (30, 2)


def test_un_lote_lleno_avisa_que_quedan_mas_y_no_repite():
    diario = []
    r = correr(diario, lote=[fila(1), fila(2)], tope=2)
    assert r["quedan_mas"] is True
    assert r["transmitidos"] == 2
    # Una sola consulta de lote: nada de bucles hasta vaciar (§3.1).
    lotes = [d for d in diario if "LIMIT %s" in d[1]]
    assert len(lotes) == 1


def test_si_falla_la_bitacora_no_se_marca_nada():
    diario = []
    with pytest.raises(RuntimeError):
        correr(diario, lote=[fila(1)], fallar_bitacora="INSERT")
    assert ("bandeja", "UPDATE") not in pasos(diario)
    assert diario[-1] == ("bandeja", "ROLLBACK", None)


def test_si_falla_al_marcar_el_reintento_no_duplica_ni_cambia_la_cadena():
    almacen = {}
    lote = [fila(1), fila(2), fila(3)]

    # Primera corrida: la bitacora confirma y la bandeja falla al marcar.
    primero = []
    with pytest.raises(RuntimeError):
        correr(primero, lote=lote, fallar_bandeja="UPDATE", almacen=almacen)
    assert ("bitacora", "COMMIT", None) in primero
    assert primero[-1] == ("bandeja", "ROLLBACK", None)
    sellos_primero = {k: v[-1] for k, v in almacen.items()}

    # Segunda corrida: la bandeja sigue sin marcar, asi que sale el mismo lote
    # desde el mismo punto de partida.
    segundo = []
    correr(segundo, lote=lote, almacen=almacen)

    assert len(almacen) == 3
    assert {k: v[-1] for k, v in almacen.items()} == sellos_primero
    assert [m[0] for m in segundo[5][2]] == list(sellos_primero.values())


def test_sin_llave_no_arranca(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "LLAVE_CADENA", None)
    with pytest.raises(eslabon.LlaveInvalida):
        transmitir.ejecutar(abrir_bandeja=lambda: pytest.fail("abrio la base"))
