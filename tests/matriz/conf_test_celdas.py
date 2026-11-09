import pytest

# (rol, objeto) -> {operacion: condicion o None}
# None significa que el permiso depende solo del rol.
MATRIZ: dict[tuple[str, str], dict[str, str | None]] = {
    # --- Direccion General: lectura transversal, modifica su credencial ------
    ("DIRECCION_GENERAL", "O1"): {"L": None},
    ("DIRECCION_GENERAL", "O2"): {"L": None},
    ("DIRECCION_GENERAL", "O3"): {"L": None},
    ("DIRECCION_GENERAL", "O4"): {"L": None},
    ("DIRECCION_GENERAL", "O5"): {"L": None},
    ("DIRECCION_GENERAL", "O6"): {"L": None},
    ("DIRECCION_GENERAL", "O7"): {"L": None},
    ("DIRECCION_GENERAL", "O8"): {"L": None},
    ("DIRECCION_GENERAL", "O9"): {"L": None},
    ("DIRECCION_GENERAL", "O10"): {"M": None},
    ("DIRECCION_GENERAL", "O11"): {"L": None, "X": None},

    # --- Direccion de Certificacion -----------------------------------------
    ("DIRECCION_CERTIFICACION", "O1"): {"L": None},
    ("DIRECCION_CERTIFICACION", "O2"): {"L": None, "Ab": None, "Cr": None},
    ("DIRECCION_CERTIFICACION", "O3"): {"L": None},
    ("DIRECCION_CERTIFICACION", "O4"): {"L": None, "Cr": "C5"},
    ("DIRECCION_CERTIFICACION", "O5"): {"L": None, "An": None},
    ("DIRECCION_CERTIFICACION", "O6"): {},
    ("DIRECCION_CERTIFICACION", "O7"): {},
    ("DIRECCION_CERTIFICACION", "O8"): {"L": None, "C": None, "M": None},
    ("DIRECCION_CERTIFICACION", "O9"): {},
    ("DIRECCION_CERTIFICACION", "O10"): {"M": None},
    ("DIRECCION_CERTIFICACION", "O11"): {"L": None, "X": None},

    # --- Personal Administrativo --------------------------------------------
    ("PERSONAL_ADMINISTRATIVO", "O1"): {"L": None, "C": None, "M": None},
    ("PERSONAL_ADMINISTRATIVO", "O2"): {},
    ("PERSONAL_ADMINISTRATIVO", "O3"): {},
    ("PERSONAL_ADMINISTRATIVO", "O4"): {},
    ("PERSONAL_ADMINISTRATIVO", "O5"): {},
    ("PERSONAL_ADMINISTRATIVO", "O6"): {"L": None, "C": None, "M": None},
    ("PERSONAL_ADMINISTRATIVO", "O7"): {"L": None, "C": None},
    ("PERSONAL_ADMINISTRATIVO", "O8"): {},
    ("PERSONAL_ADMINISTRATIVO", "O9"): {"L": "C10", "C": "C10", "M": "C10"},
    ("PERSONAL_ADMINISTRATIVO", "O10"): {"M": None},
    ("PERSONAL_ADMINISTRATIVO", "O11"): {"L": None},

    # --- Tecnico de campo ---------------------------------------------------
    ("TECNICO_CAMPO", "O1"): {"L": "C1"},
    ("TECNICO_CAMPO", "O2"): {"L": None},
    ("TECNICO_CAMPO", "O3"): {"L": "C1", "C": "C2"},
    ("TECNICO_CAMPO", "O4"): {"L": "C1", "C": "C11"},
    ("TECNICO_CAMPO", "O5"): {},
    ("TECNICO_CAMPO", "O6"): {},
    ("TECNICO_CAMPO", "O7"): {},
    ("TECNICO_CAMPO", "O8"): {"L": "C1"},
    ("TECNICO_CAMPO", "O9"): {},
    ("TECNICO_CAMPO", "O10"): {"M": None},
    ("TECNICO_CAMPO", "O11"): {},

    # --- Verificador --------------------------------------------------------
    ("VERIFICADOR", "O1"): {"L": "C1"},
    ("VERIFICADOR", "O2"): {"L": None},
    ("VERIFICADOR", "O3"): {"L": None, "C": "C1yC2", "A": "C3", "D": "C3"},
    ("VERIFICADOR", "O4"): {"L": None, "A": "C4", "D": "C4"},
    ("VERIFICADOR", "O5"): {"L": None, "Em": "C6"},
    ("VERIFICADOR", "O6"): {},
    ("VERIFICADOR", "O7"): {},
    ("VERIFICADOR", "O8"): {"L": "C1"},
    ("VERIFICADOR", "O9"): {},
    ("VERIFICADOR", "O10"): {"M": None},
    ("VERIFICADOR", "O11"): {},

    # --- Auditor externo: todo dentro de la ventana de auditoria -------------
    ("AUDITOR_EXTERNO", "O1"): {"L": "C7"},
    ("AUDITOR_EXTERNO", "O2"): {"L": "C7"},
    ("AUDITOR_EXTERNO", "O3"): {"L": "C7", "X": "C7"},
    ("AUDITOR_EXTERNO", "O4"): {"L": "C7", "X": "C7"},
    ("AUDITOR_EXTERNO", "O5"): {"L": "C7", "X": "C7"},
    ("AUDITOR_EXTERNO", "O6"): {},
    ("AUDITOR_EXTERNO", "O7"): {},
    ("AUDITOR_EXTERNO", "O8"): {},
    ("AUDITOR_EXTERNO", "O9"): {},
    ("AUDITOR_EXTERNO", "O10"): {"M": None},
    ("AUDITOR_EXTERNO", "O11"): {"L": "C7", "X": "C7"},

    # --- Dueno de finca: solo lo suyo ---------------------------------------
    ("DUENO_FINCA", "O1"): {"L": "C8"},
    ("DUENO_FINCA", "O2"): {"L": None},
    ("DUENO_FINCA", "O3"): {"L": "C8"},
    ("DUENO_FINCA", "O4"): {"L": "C8"},
    ("DUENO_FINCA", "O5"): {"L": "C8"},
    ("DUENO_FINCA", "O6"): {"L": "C8"},
    ("DUENO_FINCA", "O7"): {"L": "C8", "C": "C8", "M": "C8"},
    ("DUENO_FINCA", "O8"): {},
    ("DUENO_FINCA", "O9"): {},
    ("DUENO_FINCA", "O10"): {"M": None},
    ("DUENO_FINCA", "O11"): {},

    # --- Tercero autorizado: solo el certificado que le autorizaron ---------
    ("TERCERO_AUTORIZADO", "O1"): {},
    ("TERCERO_AUTORIZADO", "O2"): {},
    ("TERCERO_AUTORIZADO", "O3"): {},
    ("TERCERO_AUTORIZADO", "O4"): {},
    ("TERCERO_AUTORIZADO", "O5"): {"L": "C9"},
    ("TERCERO_AUTORIZADO", "O6"): {},
    ("TERCERO_AUTORIZADO", "O7"): {},
    ("TERCERO_AUTORIZADO", "O8"): {},
    ("TERCERO_AUTORIZADO", "O9"): {},
    ("TERCERO_AUTORIZADO", "O10"): {"M": None},
    ("TERCERO_AUTORIZADO", "O11"): {},
}

OPERACIONES = ("L", "C", "M", "E", "A", "D", "Ab", "Cr", "Em", "An", "X")

def celdas_concedidas():
    # Cada (rol, objeto, operacion, condicion), aquellas celdas que tienen al menos una operación
    for (rol, objeto), permisos in MATRIZ.items():
        for operacion, condicion in permisos.items():
            yield rol, objeto, operacion, condicion

def celdas_denegadas():
    # Aquellas celdas que no tienen ninguna operación
    for (rol, objeto), permisos in MATRIZ.items():
        for operacion in OPERACIONES:
            if operacion not in permisos:
                yield rol, objeto, operacion

# se exporta la matriz para que los tests puedan usarla
@pytest.fixture(scope="session")
def matriz():
    return MATRIZ
