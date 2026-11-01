"""Cliente del punto de decision (PDP).

CONTRATO CONGELADO. Ver contracts/02-autorizacion.md. Cambiar estas firmas
rompe el trabajo de los frentes de identidad, dominio y certificados.

La implementacion de hoy deniega todo. Es a proposito: los demas frentes pueden
llamar puede(...) desde el primer dia, y cuando el motor de politicas este
listo nadie tiene que cambiar una linea. Ademas arranca en el estado seguro,
que es lo que la matriz exige por omision.
"""

from dataclasses import dataclass, field
from typing import Literal

# Las once operaciones de la matriz. E se define en el vocabulario pero ningun
# rol la recibe, asi que una peticion con E siempre se deniega.
Operacion = Literal["L", "C", "M", "E", "A", "D", "Ab", "Cr", "Em", "An", "X"]

# Los ocho roles. El nombre es la clave con la que la politica los identifica.
ROLES = (
    "DIRECCION_GENERAL",
    "DIRECCION_CERTIFICACION",
    "PERSONAL_ADMINISTRATIVO",
    "TECNICO_CAMPO",
    "VERIFICADOR",
    "AUDITOR_EXTERNO",
    "DUENO_FINCA",
    "TERCERO_AUTORIZADO",
)

# Los once objetos protegidos.
OBJETOS = tuple(f"O{n}" for n in range(1, 12))


@dataclass(frozen=True)
class Sujeto:
    """Quien hace la peticion. Sale de la sesion, nunca del cliente."""

    id: str
    rol: str
    # Zonas con asignacion vigente (O8). Lo consulta C1.
    zonas: tuple[str, ...] = ()


@dataclass(frozen=True)
class Objeto:
    """Sobre que se pide actuar.

    Los nombres de los atributos son los del contrato 1 y tienen que ser
    exactos: finca.zona, periodo.estado, medicion.autor, etc. Un nombre mal
    escrito no es un error de ejecucion, es una condicion que nunca se cumple.
    """

    tipo: str
    atributos: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    """Respuesta del motor.

    El motivo va a la bitacora, no al cliente: un mensaje detallado revela
    estructura interna. Al cliente se le responde 403 y nada mas.
    """

    permitido: bool
    motivo: str
    condicion: str | None = None


def puede(sujeto: Sujeto, operacion: Operacion, objeto: Objeto) -> Decision:
    """Pregunta al punto de decision si se concede la operacion.

    RELLENO: deniega todo. F3 reemplaza el cuerpo por la consulta a OPA en el
    contenedor adjunto, sin tocar la firma.
    """
    return Decision(
        permitido=False,
        motivo=(
            "relleno de autorizacion: el motor de politicas no esta "
            "implementado, se deniega por omision"
        ),
        condicion=None,
    )
