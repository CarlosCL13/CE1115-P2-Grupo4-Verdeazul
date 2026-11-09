
from app.authz.Modelos_opa import Sujeto

# Las zonas que usan las pruebas. No es el catalogo real de Verdeazul: es el
# minimo para que C1 tenga un dentro y un fuera.
NORTE = "norte"
ATLANTICA = "atlantica"
PACIFICO = "pacifico"

USUARIOS: dict[str, Sujeto] = {
    "direccion": Sujeto(id="u-dg-1", rol="DIRECCION_GENERAL"),
    "certificacion": Sujeto(id="u-dc-1", rol="DIRECCION_CERTIFICACION"),
    "administrativo": Sujeto(id="u-pa-1", rol="PERSONAL_ADMINISTRATIVO"),
    "tecnico": Sujeto(id="u-tc-1", rol="TECNICO_CAMPO", zonas=(NORTE,)),
    "tecnico2": Sujeto(id="u-tc-2", rol="TECNICO_CAMPO", zonas=(NORTE, ATLANTICA)),
    "verificador": Sujeto(id="u-vf-1", rol="VERIFICADOR", zonas=(NORTE, ATLANTICA)),
    "auditor": Sujeto(id="u-ae-1", rol="AUDITOR_EXTERNO"),
    "dueno": Sujeto(id="u-df-1", rol="DUENO_FINCA"),
    "tercero": Sujeto(id="u-ta-1", rol="TERCERO_AUTORIZADO")
}

def sujeto_de(nombre: str) -> Sujeto:
    if nombre not in USUARIOS:
        raise KeyError(
            f"no hay usuario de prueba '{nombre}'. "
            f"Los que hay: {', '.join(sorted(USUARIOS))}"
        )
    return USUARIOS[nombre]
