"""O6 Datos personales de duenos. Contrato 04, persona 2.

    GET   /personas            buscar por cedula, o listar lo que se puede ver
    GET   /personas/{cuenta}   ver los datos completos de un dueno
    POST  /personas            registrar los datos de un dueno
    PATCH /personas/{cuenta}   corregir datos

La matriz sobre O6:

    Direccion General          L
    Personal Administrativo    L, C, M
    Dueno de finca             L.C8, solo los suyos
    los otros cinco            nada

Direccion de Certificacion NO ve datos personales, y es a proposito: no los
necesita para certificar (minimizacion, LG-04). Es la celda que mas gente
implementa mal porque suena raro, y la que conviene saber defender.

Los datos personales cuelgan de una cuenta: el {cuenta} de las rutas es el id
de la cuenta del dueno. Para C8 eso significa que "el propietario" de los
datos de la cuenta 9 es la cuenta 9.
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app import bd
from app.auth import cifrado
from app.auth.dependencias import SesionCompleta, autorizar, consultar
from app.bitacora import registrar
from app.errores import ErrorAPI
from app.personas import cedula as ced

router = APIRouter(tags=["datos personales"])

LIMITE_LISTADO = 200


class NuevaPersona(BaseModel):
    usuario: str = Field(min_length=1, max_length=64)
    nombre_completo: str = Field(min_length=3, max_length=200)
    cedula: str = Field(min_length=9, max_length=20)
    telefono: str | None = Field(default=None, max_length=20)


class CambioPersona(BaseModel):
    nombre_completo: str | None = Field(default=None, min_length=3, max_length=200)
    cedula: str | None = Field(default=None, min_length=9, max_length=20)
    telefono: str | None = Field(default=None, max_length=20)


def _atributos(cuenta: int) -> dict:
    # C8 compara finca.propietario_id con el sujeto. En O6 el dueno de los
    # datos es la cuenta misma. Texto, como todo id que va al motor.
    return {"finca.propietario_id": str(cuenta)}


def _anotar_ilegible(sesion, cuenta: int) -> None:
    """GCM detecto que el dato no es el que se guardo. Eso es un incidente."""
    registrar(accion="DATO_PERSONAL_ILEGIBLE", sujeto=sesion.sujeto.id,
              objeto="O6:%d" % cuenta, resultado="DENEGADO",
              motivo="la etiqueta GCM no cuadra: dato alterado en la base o "
                     "cifrado con otra llave")


def _validar(funcion, valor):
    try:
        return funcion(valor)
    except ced.CedulaInvalida as error:
        raise ErrorAPI(422, "dato_invalido", str(error)) from None


@router.get("/personas")
def buscar_personas(sesion: SesionCompleta,
                    cedula: str | None = Query(default=None, max_length=20)
                    ) -> dict:
    """Busca por cedula sin descifrar nada: compara el HMAC.

    Sin cedula, lista lo que el sujeto puede ver: todo para DG y PA, solo lo
    suyo para un dueno. Las cedulas salen enmascaradas en el listado; completas
    solo en GET /personas/{cuenta}, que registra la consulta.
    """
    buscada = _validar(ced.normalizar, cedula) if cedula else None

    with bd.transaccion() as cur:
        # Primero, si el rol tiene algun L sobre O6. Si el motor niega sin
        # nombrar una condicion, el rol no tiene el permiso: eso es un intento
        # denegado y se registra. Si niega por una condicion (C8 del dueno),
        # el rol si tiene el permiso y lo que falta es filtrar fila por fila.
        general = consultar(sesion, "L", "O6")
        if not general.permitido and general.condicion is None:
            autorizar(sesion, "L", "O6", objeto="O6:*")

        if buscada is not None:
            cur.execute(
                "SELECT d.cuenta, d.nombre_completo, d.cedula_cifrada, "
                "       c.usuario "
                "FROM datos_personales d JOIN cuentas c ON c.id = d.cuenta "
                "WHERE d.cedula_busqueda = %s",
                (ced.huella_busqueda(buscada),))
        else:
            cur.execute(
                "SELECT d.cuenta, d.nombre_completo, d.cedula_cifrada, "
                "       c.usuario "
                "FROM datos_personales d JOIN cuentas c ON c.id = d.cuenta "
                "ORDER BY d.nombre_completo LIMIT %s",
                (LIMITE_LISTADO,))
        filas = cur.fetchall()

        visibles = []
        for fila in filas:
            if not general.permitido and not consultar(
                    sesion, "L", "O6", _atributos(fila["cuenta"])).permitido:
                continue
            try:
                visible = ced.enmascarar(
                    ced.descifrar_cedula(fila["cedula_cifrada"], fila["cuenta"]))
            except cifrado.DatoAlterado:
                # Una fila que no descifra fue alterada en la base, o se cifro
                # con otra llave. No tumba el listado, pero queda anotada.
                _anotar_ilegible(sesion, fila["cuenta"])
                visible = "(ilegible)"
            visibles.append({
                "cuenta": fila["cuenta"],
                "usuario": fila["usuario"],
                "nombre_completo": fila["nombre_completo"],
                "cedula": visible,
            })

        registrar(accion="DATOS_PERSONALES_BUSCADOS", sujeto=sesion.sujeto.id,
                  objeto="O6:*", resultado="PERMITIDO",
                  detalle={"por_cedula": buscada is not None,
                           "resultados": len(visibles)})

    return {"personas": visibles}


@router.get("/personas/{cuenta}")
def ver_persona(cuenta: int, sesion: SesionCompleta) -> dict:
    """Los datos completos, descifrados. Cada consulta queda en la bitacora.

    Se autoriza antes de buscar la fila. Un dueno que pide /personas/10 recibe
    403 exista o no esa persona, asi que cambiar el numero de la direccion no
    sirve ni para averiguar que cuentas tienen datos (el IDOR que P1 cita).
    """
    with bd.transaccion() as cur:
        autorizar(sesion, "L", "O6", objeto="O6:%d" % cuenta,
                  atributos=_atributos(cuenta))
        cur.execute(
            "SELECT d.cuenta, d.nombre_completo, d.cedula_cifrada, "
            "       d.telefono_cifrado, d.actualizado_en, c.usuario "
            "FROM datos_personales d JOIN cuentas c ON c.id = d.cuenta "
            "WHERE d.cuenta = %s", (cuenta,))
        fila = cur.fetchone()
        if fila is None:
            raise ErrorAPI(404, "no_existe")
        try:
            cedula = ced.descifrar_cedula(fila["cedula_cifrada"], cuenta)
            telefono = ced.descifrar_telefono(fila["telefono_cifrado"], cuenta)
        except cifrado.DatoAlterado:
            _anotar_ilegible(sesion, cuenta)
            ilegible = True
        else:
            ilegible = False
            registrar(accion="DATOS_PERSONALES_CONSULTADOS",
                      sujeto=sesion.sujeto.id, objeto="O6:%d" % cuenta,
                      resultado="PERMITIDO")

    # Fuera de la transaccion, para que el evento de arriba se confirme.
    if ilegible:
        raise ErrorAPI(409, "dato_ilegible",
                       "Los datos de esta persona no se pueden leer. Quedó "
                       "registrado para revisión.")
    return {
        "cuenta": fila["cuenta"],
        "usuario": fila["usuario"],
        "nombre_completo": fila["nombre_completo"],
        "cedula": cedula,
        "telefono": telefono,
        "actualizado_en": fila["actualizado_en"].isoformat(),
    }


@router.post("/personas", status_code=201)
def registrar_persona(datos: NuevaPersona, sesion: SesionCompleta) -> dict:
    """C sobre O6. Solo para cuentas de Dueno de finca: es su objeto."""
    cedula = _validar(ced.normalizar, datos.cedula)
    telefono = (_validar(ced.normalizar_telefono, datos.telefono)
                if datos.telefono else None)

    with bd.transaccion() as cur:
        autorizar(sesion, "C", "O6", objeto="O6:nuevo")

        cur.execute("SELECT id, rol::text AS rol FROM cuentas WHERE usuario = %s",
                    (datos.usuario,))
        cuenta = cur.fetchone()
        if cuenta is None:
            raise ErrorAPI(404, "cuenta_inexistente",
                           "No existe una cuenta con ese usuario.")
        if cuenta["rol"] != "DUENO_FINCA":
            raise ErrorAPI(422, "no_es_dueno",
                           "Los datos personales son de cuentas de dueño de finca.")

        huella = ced.huella_busqueda(cedula)
        cur.execute("SELECT cuenta FROM datos_personales "
                    "WHERE cuenta = %s OR cedula_busqueda = %s",
                    (cuenta["id"], huella))
        if cur.fetchone() is not None:
            raise ErrorAPI(409, "ya_registrada",
                           "Esa cuenta ya tiene datos, o esa cédula ya está "
                           "registrada.")

        cur.execute(
            "INSERT INTO datos_personales "
            "(cuenta, nombre_completo, cedula_cifrada, cedula_busqueda, "
            " telefono_cifrado) VALUES (%s, %s, %s, %s, %s)",
            (cuenta["id"], datos.nombre_completo,
             ced.cifrar_cedula(cedula, cuenta["id"]), huella,
             ced.cifrar_telefono(telefono, cuenta["id"]) if telefono else None))
        registrar(accion="DATOS_PERSONALES_REGISTRADOS",
                  sujeto=sesion.sujeto.id, objeto="O6:%d" % cuenta["id"],
                  resultado="PERMITIDO")

    return {"cuenta": cuenta["id"]}


@router.patch("/personas/{cuenta}")
def corregir_persona(cuenta: int, datos: CambioPersona,
                     sesion: SesionCompleta) -> dict:
    """M sobre O6. El dueno no tiene M: pide la correccion (LG-02) y la hace PA.

    El evento dice que campos cambiaron, no los valores: el contrato 03 no
    deja datos personales en la bitacora.
    """
    cambios: dict[str, object] = {}
    if datos.nombre_completo is not None:
        cambios["nombre_completo"] = datos.nombre_completo
    if datos.cedula is not None:
        nueva = _validar(ced.normalizar, datos.cedula)
        cambios["cedula_cifrada"] = ced.cifrar_cedula(nueva, cuenta)
        cambios["cedula_busqueda"] = ced.huella_busqueda(nueva)
    if datos.telefono is not None:
        cambios["telefono_cifrado"] = (
            ced.cifrar_telefono(_validar(ced.normalizar_telefono, datos.telefono),
                                cuenta) if datos.telefono else None)
    if not cambios:
        raise ErrorAPI(422, "sin_cambios")

    with bd.transaccion() as cur:
        autorizar(sesion, "M", "O6", objeto="O6:%d" % cuenta,
                  atributos=_atributos(cuenta))

        cur.execute("SELECT 1 FROM datos_personales WHERE cuenta = %s FOR UPDATE",
                    (cuenta,))
        if cur.fetchone() is None:
            raise ErrorAPI(404, "no_existe")
        if "cedula_busqueda" in cambios:
            cur.execute("SELECT 1 FROM datos_personales "
                        "WHERE cedula_busqueda = %s AND cuenta <> %s",
                        (cambios["cedula_busqueda"], cuenta))
            if cur.fetchone() is not None:
                raise ErrorAPI(409, "ya_registrada",
                               "Esa cédula ya está registrada en otra cuenta.")

        # Los nombres de columna salen de este diccionario, que arma este
        # mismo codigo, nunca de lo que manda el usuario. Los valores van como
        # parametros (§2.3.5).
        asignaciones = ", ".join("%s = %%s" % columna for columna in cambios)
        cur.execute(
            "UPDATE datos_personales SET %s, actualizado_en = now() "
            "WHERE cuenta = %%s" % asignaciones,
            (*cambios.values(), cuenta))
        registrar(accion="DATOS_PERSONALES_CORREGIDOS",
                  sujeto=sesion.sujeto.id, objeto="O6:%d" % cuenta,
                  resultado="PERMITIDO",
                  detalle={"campos": sorted({"cedula" if c.startswith("cedula")
                                             else c.replace("_cifrado", "")
                                             for c in cambios})})

    return {"cuenta": cuenta, "corregida": True}
