"""Cobertura de la matriz: las 88 celdas, en las dos direcciones.

Dos familias de pruebas, y la primera importa mas que la segunda:

  1. Lo que la matriz NO concede tiene que negarse. 884 combinaciones. Estas
     pruebas pasan desde hoy y tienen que seguir pasando para siempre: son las
     que detectan que alguien concedio de mas al implementar una celda.

  2. Lo que la matriz SI concede tiene que permitirse. 84 permisos. Hoy fallan
     todas porque el motor es un relleno que deniega todo, asi que estan
     marcadas xfail. F3 las va destapando: cada vez que una pasa de xfail a
     xpass, esa celda quedo implementada.

De aqui sale la tabla de cobertura del informe. `pytest -v` imprime una linea
por celda con su identificador.
"""

import pytest
from conftest import celdas_concedidas, celdas_denegadas

from app.authz import Decision, Objeto, Sujeto, puede


def _sujeto(rol: str) -> Sujeto:
    return Sujeto(id="u-prueba", rol=rol, zonas=("norte",))


@pytest.mark.parametrize(
    ("rol", "objeto", "operacion"),
    list(celdas_denegadas()),
    ids=lambda v: str(v),
)
def test_lo_no_concedido_se_niega(rol: str, objeto: str, operacion: str) -> None:
    """Denegacion por omision: lo que no esta en la matriz, no existe."""
    decision = puede(_sujeto(rol), operacion, Objeto(tipo=objeto))

    assert isinstance(decision, Decision)
    assert not decision.permitido, (
        f"{rol} NO deberia poder {operacion} sobre {objeto}, "
        f"y el motor lo permitio"
    )


@pytest.mark.parametrize(
    ("rol", "objeto", "operacion", "condicion"),
    list(celdas_concedidas()),
    ids=lambda v: str(v),
)
@pytest.mark.xfail(
    reason="el motor de politicas es todavia un relleno que deniega todo",
    strict=False,
)
def test_lo_concedido_se_permite(
    rol: str, objeto: str, operacion: str, condicion: str | None
) -> None:
    """Las celdas concedidas.

    Las que tienen condicion necesitan los atributos que la condicion mira, y
    eso depende del esquema. Por eso, mientras no haya esquema, esta prueba
    solo cubre de verdad las celdas sin condicion.
    """
    if condicion is not None:
        pytest.skip(f"{condicion}: necesita atributos del esquema (contrato 1)")

    decision = puede(_sujeto(rol), operacion, Objeto(tipo=objeto))

    assert decision.permitido, (
        f"{rol} deberia poder {operacion} sobre {objeto} y el motor lo nego: "
        f"{decision.motivo}"
    )


def test_ninguna_celda_concede_eliminar() -> None:
    """E esta en el vocabulario pero ningun rol la recibe.

    No es un detalle: significa que nada se borra, todo se anula o se enmienda.
    Si esta prueba falla, alguien concedio borrado al transcribir la matriz.
    """
    concede_e = [c for c in celdas_concedidas() if c[2] == "E"]
    assert concede_e == [], f"la matriz no concede E, y aparecio en {concede_e}"


def test_la_matriz_esta_completa() -> None:
    """8 roles x 11 objetos = 88 celdas, ninguna sin definir.

    Una celda que falta no es una celda vacia: es una celda sobre la que nadie
    decidio. El documento de P1 insiste en que ninguna quede implicita.
    """
    celdas = {(rol, objeto) for rol, objeto, _, _ in celdas_concedidas()}
    celdas |= {(rol, objeto) for rol, objeto, _ in celdas_denegadas()}
    assert len(celdas) == 88, f"se esperaban 88 celdas definidas, hay {len(celdas)}"
