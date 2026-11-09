from dataclasses import dataclass, field
from typing import Literal

# Las once operaciones de la matriz
Operacion = Literal["L", "C", "M", "E", "A", "D", "Ab", "Cr", "Em", "An", "X"]

# Roles en la matriz de control de acceso
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

# Modelo del sujeto para la petición que solicita la autorización
@dataclass(frozen=True) # permite crear el constructor de la clase usando los argumentos = a los atributos
class Sujeto:
    id: str
    rol: str
    zonas: tuple[str, ...] = () # lista de zonas a las que tiene acceso el sujeto, puede estar vacía

# Modelo del objeto para el que se solicita autorización (por parte del sujeto)
@dataclass(frozen=True)
class Objeto:
    tipo: str # se indica cual objeto de los 11, por ejemplo "O1", "O2"

    # Atributos del objeto, columnas de la entidad en la base de datos
    atributos: dict[str, object] = field(default_factory=dict) # puede estar vacío

# Modelo de la decisión que retorna el motor de políticas
@dataclass(frozen=True)
class Decision:
    permitido: bool
    motivo: str
    condicion: str | None = None
    version_politica: str | None = None
