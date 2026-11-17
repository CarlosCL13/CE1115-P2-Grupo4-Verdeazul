"""O5 Certificados de carbono. Contrato 04.

    GET  /certificados                  los que el sujeto puede ver
    GET  /certificados/exportar         CSV para el auditor (X.C7)
    GET  /certificados/{id}             uno, con su documento firmado
    POST /certificados/{medicion}/emitir el verificador emite y firma (Em.C6)
    POST /certificados/{id}/anular      Direccion de Certificacion (An)
    POST /publico/verificar             SIN SESION: comprueba un archivo (D-09)

La matriz sobre O5:

    Direccion General              L
    Direccion de Certificacion     L, An
    Verificador                    L, Em.C6
    Auditor externo                L.C7, X.C7
    Dueno de finca                 L.C8
    Tercero autorizado             L.C9
    Personal Admin., Tecnico       nada
    ningun rol                     C, M, E

Nadie modifica un certificado: va firmado y circula fuera del sistema. La
base lo impone (migracion 012): app_rw solo puede cambiar estado,
motivo_anulacion y anulado_en, que es lo necesario para anularlo. Corregir un
certificado es anularlo y emitir otro (minuta B2).

En `emitir`, el {id} de la ruta es el de la MEDICION: el certificado todavia
no existe. La ruta la fija el contrato 04, que traduce Em siempre a
POST /recurso/{id}/accion.
"""

import csv
import io
import json

import psycopg
from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import bd
from app.auth.dependencias import (SesionCompleta, SesionReautenticada,
                                   autorizar, consultar)
from app.bitacora import registrar
from app.certificacion import consultas as qc
from app.certificacion.fincas import inexistente
from app.certificados import consultas as q
from app.certificados import firma, verificacion
from app.errores import ErrorAPI

router = APIRouter(tags=["certificados"])


class Anulacion(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


def _uno(cur, certificado_id: int, bloquear: bool = False,
         con_documento: bool = False) -> dict | None:
    select = (q.SELECT_CERTIFICADO_CON_DOCUMENTO if con_documento
              else q.SELECT_CERTIFICADO)
    cur.execute(select + "WHERE c.id = %s" +
                (" FOR UPDATE OF c" if bloquear else ""), (certificado_id,))
    return cur.fetchone()


def _atributos_lectura(cur, sesion, fila: dict,
                       autorizaciones: dict | None = None) -> dict:
    """Todo lo que L puede necesitar: C7 del sujeto, C8 de la fila y C9."""
    if autorizaciones is None:
        autorizaciones = q.autorizaciones_del_tercero(cur, sesion)
    return {**qc.atributos_sujeto(cur, sesion),
            **q.atributos_certificado(fila),
            **autorizaciones.get(fila["finca"], {})}


# ---------------------------------------------------------------------------
# L: listar y ver
# ---------------------------------------------------------------------------

@router.get("/certificados")
def listar_certificados(sesion: SesionCompleta,
                        estado: str | None = Query(
                            default=None, pattern="^(VIGENTE|ANULADO)$"),
                        medicion: int | None = Query(default=None, gt=0)
                        ) -> dict:
    with bd.transaccion() as cur:
        propios = qc.atributos_sujeto(cur, sesion)
        general = consultar(sesion, "L", "O5", propios)
        # Igual que en O1 y O3: si el motor niega sin nombrar condicion, el
        # rol no tiene L (403). El auditor tampoco filtra fila por fila: su
        # condicion (C7) es de el, no de la fila.
        if not general.permitido and (
                general.condicion is None or sesion.rol == "AUDITOR_EXTERNO"):
            autorizar(sesion, "L", "O5", objeto="O5:*", atributos=propios)

        autorizaciones = q.autorizaciones_del_tercero(cur, sesion)
        filtro, parametros = q.previo_por_rol(sesion, autorizaciones)
        for columna, valor in (("c.estado::text", estado),
                               ("c.medicion", medicion)):
            if valor is not None:
                filtro += " AND %s = %%s" % columna
                parametros += (valor,)
        cur.execute(q.SELECT_CERTIFICADO + "WHERE true" + filtro +
                    " ORDER BY c.id DESC LIMIT %s",
                    (*parametros, q.LIMITE_LISTADO))
        visibles = []
        for fila in cur.fetchall():
            if not general.permitido and not consultar(
                    sesion, "L", "O5", _atributos_lectura(
                        cur, sesion, fila, autorizaciones)).permitido:
                continue
            visibles.append(q.certificado_json(fila))
        registrar(accion="CERTIFICADOS_LISTADOS", sujeto=sesion.sujeto.id,
                  objeto="O5:*", resultado="PERMITIDO",
                  detalle={"resultados": len(visibles)})
    return {"certificados": visibles}


# Antes de /certificados/{id}: si no, "exportar" se tomaria por un id.
@router.get("/certificados/exportar")
def exportar_certificados(sesion: SesionCompleta) -> Response:
    """Todos los certificados, en CSV. Solo el auditor, y solo en su ventana.
    Mismo formato que las otras exportaciones: una fila por registro."""
    with bd.transaccion() as cur:
        autorizar(sesion, "X", "O5", objeto="O5:*",
                  atributos=qc.atributos_sujeto(cur, sesion))
        cur.execute(q.SELECT_CERTIFICADO + "ORDER BY c.id")
        filas = cur.fetchall()
        registrar(accion="CERTIFICADOS_EXPORTADOS", sujeto=sesion.sujeto.id,
                  objeto="O5:*", resultado="PERMITIDO",
                  detalle={"filas": len(filas)})

    salida = io.StringIO()
    escritor = csv.writer(salida, lineterminator="\n")
    escritor.writerow(["id", "medicion", "finca", "periodo", "toneladas",
                       "estado", "emitido_por", "emitido_en", "huella_llave",
                       "motivo_anulacion", "anulado_en"])
    for f in filas:
        escritor.writerow([
            f["id"], f["medicion"], f["finca"], f["periodo_etiqueta"],
            f["toneladas"], f["estado"], f["emitido_por"],
            f["emitido_en"].isoformat(), q.huella_de(f),
            f["motivo_anulacion"] or "",
            f["anulado_en"].isoformat() if f["anulado_en"] else ""])
    return Response(
        salida.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 'attachment; filename="certificados.csv"'})


@router.get("/certificados/{certificado_id}")
def ver_certificado(certificado_id: int, sesion: SesionCompleta) -> dict:
    """Un certificado y su documento firmado, que es el archivo que el dueno
    descarga y que despues se sube a la verificacion publica."""
    with bd.transaccion() as cur:
        fila = _uno(cur, certificado_id, con_documento=True)
        objeto = "O5:%d" % certificado_id
        if fila is None:
            inexistente(cur, sesion, "L", "O5", objeto)
        autorizar(sesion, "L", "O5", objeto=objeto,
                  atributos=_atributos_lectura(cur, sesion, fila))
        # Quien vio que certificado. Es lo que la carta pide saber ("si
        # alguien anduvo viendo informacion que no le correspondia") y lo
        # que prueba que un tercero solo vio lo que el dueno le autorizo.
        registrar(accion="CERTIFICADO_CONSULTADO", sujeto=sesion.sujeto.id,
                  objeto=objeto, resultado="PERMITIDO",
                  detalle={"rol": sesion.rol})
    return {**q.certificado_json(fila), "documento": fila["documento"]}


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
# An: anular
# ---------------------------------------------------------------------------

@router.post("/certificados/{certificado_id}/anular")
def anular_certificado(certificado_id: int, datos: Anulacion,
                       sesion: SesionReautenticada) -> dict:
    """Direccion de Certificacion deja sin efecto un certificado vigente.

    Nada se borra (minuta B2, LG-06): cambia el estado, y el documento
    firmado sigue guardado. Anular libera el terreno para una emision nueva,
    porque C6 solo compara contra los vigentes; por eso pide
    reautenticacion, igual que emitir (D-21).
    """
    with bd.transaccion() as cur:
        fila = _uno(cur, certificado_id, bloquear=True)
        objeto = "O5:%d" % certificado_id
        if fila is None:
            inexistente(cur, sesion, "An", "O5", objeto)
        autorizar(sesion, "An", "O5", objeto=objeto,
                  atributos=q.atributos_certificado(fila))
        if fila["estado"] != "VIGENTE":
            raise ErrorAPI(409, "ya_anulado", "El certificado ya está anulado.")

        cur.execute("UPDATE certificados SET estado = 'ANULADO', "
                    "motivo_anulacion = %s, anulado_en = now() WHERE id = %s",
                    (datos.motivo.strip(), certificado_id))
        registrar(accion="CERTIFICADO_ANULADO", sujeto=sesion.sujeto.id,
                  objeto=objeto, resultado="PERMITIDO",
                  detalle={"medicion": str(fila["medicion"]),
                           "finca": str(fila["finca"]),
                           "motivo": datos.motivo.strip()})
        fila = _uno(cur, certificado_id)
    return q.certificado_json(fila)


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
