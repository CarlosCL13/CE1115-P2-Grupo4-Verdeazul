package verdeazul.condiciones

import rego.v1

# Si la peticion no trae atributos, el objeto vacio hace que toda condicion falle, que es el comportamiento correcto
default atributos := {}

atributos := input.objeto.atributos # es un diccionario de atributos que tiene el objeto en cuestión

# ---------------------------------------------------------------------------
# C1 - ABAC de zona
# Aplica a TC (Tecnico de campo)-> O1, O3, O4, O8 y a VF -> O1, O3, O8
#
# Caso pendiente: O8 (asignaciones tecnico-zona) tiene zona propia y no
# necesariamente una finca detras. Hoy se pasa bajo la misma clave. Ver
# docs/Preguntas_abiertas.md.
# ---------------------------------------------------------------------------
cumplidas contains "C1" if {
	atributos["finca.zona"] in input.sujeto.zonas
}

# ---------------------------------------------------------------------------
# C2 - periodo abierto
# Aplica a TC (Tecnico de campo)-> O1, O3, O4, O8 y a VF -> O1, O3, O8
#
# No se registra una medicion en un periodo cerrado. Para eso son las enmiendas (C11)
# ---------------------------------------------------------------------------
cumplidas contains "C2" if {
	atributos["periodo.estado"] == "ABIERTO"
}

# ---------------------------------------------------------------------------
# C3 - separacion de deberes al aprobar una medicion (HBAC-01)
# Aplica a VF (Verificador) -> O3 y O4
#
# Quien aprueba no puede ser quien midió, y tampoco puede haber medido otra vez esa misma finca en ese mismo periodo
# Si se olvida enviar un atributo el valor de este queda indefinido, la condicion no se cumple y se niega
# ---------------------------------------------------------------------------
cumplidas contains "C3" if {
	atributos["medicion.autor_id"] != input.sujeto.id
	atributos["contexto.sujeto_midio_en_finca_periodo"] == false # Llega como contexto, ya backend verificó eso y pasa true/false
}

# ---------------------------------------------------------------------------
# C4 - separacion de deberes al revisar una enmienda (SR-03)
# Aplica a VF (Verificador) -> O10
#
# Quien revisa no puede ser quien la solicitó
# ---------------------------------------------------------------------------
cumplidas contains "C4" if {
	atributos["enmienda.solicitante_id"] != input.sujeto.id
}

# ---------------------------------------------------------------------------
# C5 - tres personas distintas para cerrar una enmienda (SR-03)
# Aplica a DC (Dirección de certificación) -> O11
#
# Solicitante, revisor y quien cierra (DC) tienen que ser tres. La enmienda ya tiene que estar revisada,
# 	pues no se cierra lo que nadie revisó
# ---------------------------------------------------------------------------
cumplidas contains "C5" if {
	atributos["enmienda.estado"] == "REVISADA"
	atributos["enmienda.solicitante_id"] != input.sujeto.id
	atributos["enmienda.revisor_id"] != input.sujeto.id # el sujeto aquí es quien cierra la enmienda
}

# ---------------------------------------------------------------------------
# C6 - emision de certificado (SR-05)
# Aplica a VF (Verificador) -> O5
#
# Aquí la medición esta aprobada, quien emite no es quien midió, y ningun certificado vigente tiene
#	un poligono que se traslape con el de esta medición
#
# El traslape llega como contexto.poligono_traslapa_certificado_vigente
# Esta condicion es la primera barrera, no la unica, ver contracts/01-esquema.md
# ---------------------------------------------------------------------------
cumplidas contains "C6" if {
	atributos["medicion.estado"] == "APROBADA"
	atributos["medicion.autor_id"] != input.sujeto.id # el sujeto aquí es quien emite el certificado
	atributos["contexto.poligono_traslapa_certificado_vigente"] == false
}

# ---------------------------------------------------------------------------
# C7 - ventana de auditoria (HBAC-03)
# Aplica a AE (Auditor externo) -> O1, O2, O3, O4, O5, O11
#
# Fuera de la ventana el permiso no se suspende, sino que deja de existir, y por eso se evalua aqui y no
# 	como un estado de la cuenta del auditor
#
# `hoy` se manda como contexto.hoy en lugar de leerlo del reloj de OPA
# ---------------------------------------------------------------------------
cumplidas contains "C7" if {
	hoy := atributos["contexto.hoy"] # fechas son de formato (AAAA-MM-DD)
	hoy >= atributos["auditoria.inicio"]
	hoy <= atributos["auditoria.fin"]
}

# ---------------------------------------------------------------------------
# C8 - ABAC de propietario
# Aplica a DF (Dueño de la finca) -> O1, O3, O4, O5, O6, O7
#
# El dueño de la finca solo el puede ver y modificar lo que es suyo
# ---------------------------------------------------------------------------
cumplidas contains "C8" if {
	atributos["finca.propietario_id"] == input.sujeto.id # el sujeto aquí es el dueño de la finca
}

# ---------------------------------------------------------------------------
# C9 — autorizacion vigente del tercero (HBAC-03)
# Aplica a TA (Tercero autorizado) -> O5
#
# El tercero es el autorizado y la autorizacion no ha vencido. Es Estricto <, osea, el dia que vence, ya no sirve
# ---------------------------------------------------------------------------
cumplidas contains "C9" if {
	atributos["autorizacion.tercero_id"] == input.sujeto.id
	atributos["contexto.hoy"] < atributos["autorizacion.vence"] # se comparan fechas
}

# ---------------------------------------------------------------------------
# C10 - aprobacion previa para tocar cuentas y permisos (SR-04, CU-03)
# Aplica a PA (Personal Administrativo) -> 09
#
# Existe una aprobacion previa de la Direccion General, y quien aprobo no puede ser quien ejecuta.
# ---------------------------------------------------------------------------
cumplidas contains "C10" if {
	aprobador_id := atributos["cambio.aprobador_id"] # Solicitud de cambio (la hace PA y la aprueba DG)
	aprobador_id != input.sujeto.id # en este caso el sujeto es quien solicitó el cambio (en DC)
	atributos["cambio.aprobador_rol"] == "DIRECCION_GENERAL"
}

# ---------------------------------------------------------------------------
# C11 - enmienda de lo propio con el periodo cerrado.
# Aplica a TC (Tecnico de campo) -> O4
#
# El tecnico enmienda su propia medición, y solo puede solicitar enmiendas después de que el periodo cerró
# ---------------------------------------------------------------------------
cumplidas contains "C11" if {
	atributos["medicion.autor_id"] == input.sujeto.id # el sujeto aquí es quien solicita la enmienda, o sea el que medió
	atributos["periodo.estado"] == "CERRADO"
}
