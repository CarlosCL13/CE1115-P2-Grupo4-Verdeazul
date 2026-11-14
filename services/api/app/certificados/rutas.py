"""O5 Certificados de carbono: emitir y verificar. Contrato 04.

    POST /certificados/{medicion}/emitir el verificador emite y firma (Em.C6)
    POST /publico/verificar             SIN SESION: comprueba un archivo (D-09)

Listar, ver, anular y exportar en la rama feature/certificados-resto.

La matriz sobre O5, para Em:

    Verificador                    Em.C6
    los demas roles                nada

Nadie modifica un certificado: va firmado y circula fuera del sistema. La
base lo impone (migracion 012): app_rw solo puede cambiar estado,
motivo_anulacion y anulado_en, que es lo necesario para anularlo.

En `emitir`, el {id} de la ruta es el de la MEDICION: el certificado todavia
no existe. La ruta la fija el contrato 04, que traduce Em siempre a
POST /recurso/{id}/accion.
"""

import json

import psycopg
from fastapi import APIRouter, Request

from app import bd
from app.auth.dependencias import SesionReautenticada, autorizar
from app.bitacora import registrar
from app.certificacion.fincas import inexistente
from app.certificados import consultas as q
from app.certificados import firma, verificacion
from app.errores import ErrorAPI

router = APIRouter(tags=["certificados"])


# ---------------------------------------------------------------------------
# Em: emitir y firmar
# ---------------------------------------------------------------------------

@router.post("/certificados/{medicion_id}/emitir", status_code=201)
def emitir_certificado(medicion_id: int, sesion: SesionReautenticada) -> dict:
    """El verificador emite el certificado de una medicion aprobada.

    Todo ocurre en una sola transaccion, en este orden:

    1. Candado de emision. Dos verificadores que emiten a la vez sobre
       fincas que se cruzan verian los dos "no hay traslape" antes de que el
       otro confirme, y saldrian dos certificados sobre el mismo terreno: el
       segundo susto de la carta. Con el candado, el segundo espera a que el
       primero termine y entonces si ve su certificado.
    2. La medicion y su finca, bloqueadas.
    3. Si el poligono se cruza con algun certificado vigente.
    4. El motor decide con C6. Si niega: 403 y queda en la bitacora.
    5. Se firma y se guarda, con el evento de emision en la misma
       transaccion. Si algo falla, no queda ni el certificado ni el evento.
    """
    objeto = "O5:medicion-%d" % medicion_id
    with bd.transaccion() as cur:
        cur.execute(q.CANDADO_EMISION)
        cur.execute(q.SELECT_PARA_EMITIR, (medicion_id,))
        fila = cur.fetchone()
        if fila is None:
            inexistente(cur, sesion, "Em", "O5", objeto)

        cur.execute(q.SELECT_TRASLAPE, (fila["finca"],))
        traslapa = cur.fetchone()["traslapa"]
        autorizar(sesion, "Em", "O5", objeto=objeto,
                  atributos=q.atributos_emision(fila, traslapa))

        cur.execute("SELECT nextval(pg_get_serial_sequence('certificados', "
                    "'id')) AS id")
        nuevo = cur.fetchone()["id"]
        momento = firma.ahora()
        contenido = q.contenido_a_firmar(fila, nuevo, sesion.cuenta, momento)
        try:
            documento = firma.firmar(contenido)
        except firma.SinLlaveFirma:
            raise ErrorAPI(503, "sin_llave_de_firma",
                           "El sistema no puede firmar en este momento.")
        texto = firma.documento_texto(documento)
        huella = documento["firma"]["huella_llave"]

        try:
            cur.execute(q.INSERTAR, (
                nuevo, sesion.cuenta, momento,
                firma.desb64(documento["firma"]["valor"]),
                documento["firma"]["llave_publica"], texto, medicion_id))
        except psycopg.errors.UniqueViolation:
            # El indice de la 009: una medicion no tiene dos certificados
            # vigentes. Con el traslape ya revisado no deberia pasar, salvo
            # que el poligono de la finca haya cambiado despues del primero.
            raise ErrorAPI(409, "ya_certificada",
                           "Esa medición ya tiene un certificado vigente.")

        registrar(accion="CERTIFICADO_EMITIDO", sujeto=sesion.sujeto.id,
                  objeto="O5:%d" % nuevo, resultado="PERMITIDO",
                  detalle={"medicion": str(medicion_id),
                           "finca": str(fila["finca"]),
                           "toneladas": contenido["toneladas"],
                           # D-10: la huella de la llave que firmo.
                           "huella_llave": huella})
    return {"id": nuevo, "estado": "VIGENTE", "huella_llave": huella,
            "documento": texto}


# ---------------------------------------------------------------------------
# Verificacion publica (D-09)
# ---------------------------------------------------------------------------

# El JSON que manda el borde envuelve el archivo: {"archivo": "<texto>"}. Con
# el texto escapado puede crecer, de ahi el margen.
_MAXIMO_CUERPO = 2 * verificacion.MAXIMO_BYTES + 1024


@router.post("/publico/verificar")
async def verificar_publico(request: Request) -> dict:
    """Sin sesion. Recibe el archivo y dice si el certificado es valido.

    No consulta la base ni registra en la bitacora: no hay objeto protegido
    en juego, solo el archivo que trae quien verifica. Desde internet no se
    llega directo aqui: el backend solo acepta llamadas del borde (F2), y el
    borde es quien limita cuantas veces por minuto se puede verificar.

    El tamano se revisa antes de leer el cuerpo, para que un archivo enorme
    no llegue a ocupar memoria.
    """
    largo = request.headers.get("content-length", "")
    if largo.isdigit() and int(largo) > _MAXIMO_CUERPO:
        raise ErrorAPI(413, "archivo_muy_grande",
                       "El archivo es demasiado grande para un certificado.")
    cuerpo = await request.body()
    if len(cuerpo) > _MAXIMO_CUERPO:
        raise ErrorAPI(413, "archivo_muy_grande",
                       "El archivo es demasiado grande para un certificado.")
    try:
        envoltura = json.loads(cuerpo)
    except ValueError:
        raise ErrorAPI(422, "peticion_invalida") from None
    texto = envoltura.get("archivo") if isinstance(envoltura, dict) else None
    if not isinstance(texto, str):
        raise ErrorAPI(422, "peticion_invalida")

    try:
        confiables = {firma.huella_verdeazul()}
    except firma.SinLlaveFirma:
        raise ErrorAPI(503, "sin_llave_de_firma")
    resultado = verificacion.verificar_texto(texto, confiables)
    return {
        "valido": resultado.valido,
        "motivo": resultado.motivo,
        "firma_valida": resultado.firma_valida,
        "llave_de_verdeazul": resultado.llave_de_verdeazul,
        "huella_llave": resultado.huella_llave,
        "huella_verdeazul": next(iter(confiables)),
        "contenido": resultado.contenido,
    }
