package verdeazul.autorizacion_test

import data.verdeazul.autorizacion # se trae la politica de autorizacion.rego
import rego.v1

# Se hace una función con el formato de la petición del backend (se regresa un tipo objeto o diccionario cuando se llama)
peticion(rol, objeto, operacion, atributos) := {
	"sujeto": {"id": "u-1", "rol": rol, "zonas": ["norte"]},
	"operacion": operacion,
	"objeto": {"tipo": objeto, "atributos": atributos},
}

# Nota: todavía hay que definir el formato de acuerdo a los nombres de la base de datos

# ---------------------------------------------------------------------------
# Las cuatro reglas que no se negocian, en este caso para la matriz aplica solo 1 y 3 (contracts/02-autorizacion.md)
# ---------------------------------------------------------------------------

# Regla 1: lo que no esta concedido en la matriz, se niega.
test_denegacion_por_omision if {
	# El tercero autorizador no tiene permiso de leer O11
	not autorizacion.permitir with input as peticion("TERCERO_AUTORIZADO", "O11", "L", {})
}

# Se reporta que fue denegado por omisión, no fue por condición que no se cumplió
test_la_omision_no_se_reporta_como_condicion if {
	d := autorizacion.decision with input as peticion("TERCERO_AUTORIZADO", "O11", "L", {})
	d.permitido == false
	d.condicion == null
}

# Regla 3: ABAC quita, nunca agrega. El dueño de la finca no tiene M sobre O1, y ser el propietario no se lo da
test_abac_no_agrega_lo_que_el_rol_no_tiene if {
	not autorizacion.permitir with input as peticion("DUENO_FINCA", "O1", "M", {"finca.propietario_id": "u-1"})
}

# Un rol que no existe no cae en ninguna celda. El rol viene de la sesion y un rol corrupto no debe conceder nada
test_rol_desconocido_se_niega if {
	not autorizacion.permitir with input as peticion("ADMINISTRADOR", "O1", "L", {})
}

# Una peticion sin rol tampoco, el motor no asume nada (no se indica el rol)
test_peticion_incompleta_se_niega if {
	not autorizacion.permitir with input as {"operacion": "L", "objeto": {"tipo": "O1"}}
}

# ---------------------------------------------------------------------------
# Decisiones de diseño (políticas) de la matriz que se deben respetar
# ---------------------------------------------------------------------------

# La operación E está descrita pero ningun rol la recibe
test_eliminar_nunca_se_concede if {
	not autorizacion.permitir with input as peticion("DIRECCION_GENERAL", "O1", "E", {})
}

# Las operaciones en la matriz son 10, excepto E, que no se concede a nadie
test_la_tabla_solo_usa_diez_operaciones if {
	# Se agrega la operación op si se encuentra en la matriz dicha op en algún rol y objeto
	operaciones := {op |
		some rol, obj, op
		is_array(autorizacion.matriz[rol][obj][op]) # puede ser que sea una lista vacía
	}
	operaciones == {"L", "C", "M", "A", "D", "Ab", "Cr", "Em", "An", "X"}
}

# Ningun rol tiene M sobre O3. Toda corrección de una medición pasa por una enmienda, que involucra tres personas
test_ningun_rol_modifica_mediciones if {
	every rol, _ in autorizacion.matriz {
		# Todas las celdas se les niega M sobre 03 (permitir = false)
		not autorizacion.permitir with input as peticion(rol, "O3", "M", {})
	}
}

# ---------------------------------------------------------------------------
# Permisos sin condicion que dependen solo del rol
# ---------------------------------------------------------------------------

# Dirección general puede leer el catálogo de fincas
test_direccion_general_lee_fincas if {
	autorizacion.permitir with input as peticion("DIRECCION_GENERAL", "O1", "L", {})
}

# Dirección general no puede modificar el catálogo de fincas, solo verlas
test_direccion_general_no_modifica_fincas if {
	not autorizacion.permitir with input as peticion("DIRECCION_GENERAL", "O1", "M", {})
}

# Dirección de certificación puede abrir periodos de medición
test_certificacion_abre_periodos if {
	autorizacion.permitir with input as peticion("DIRECCION_CERTIFICACION", "O2", "Ab", {})
}

# Un técnico de campo no puede abrir periodos de medición
test_tecnico_no_abre_periodos if {
	not autorizacion.permitir with input as peticion("TECNICO_CAMPO", "O2", "Ab", {})
}

# Los ocho roles pueden modifican su propia credencial
test_los_ocho_roles_cambian_su_credencial if {
	every rol, _ in autorizacion.matriz {
		autorizacion.permitir with input as peticion(rol, "O10", "M", {})
	}
}

# Ningún rol puede leer las credenciales de otros (SE TIENE QUE REVISAR)
test_nadie_lee_credenciales_ajenas if {
	every rol, _ in autorizacion.matriz {
		not autorizacion.permitir with input as peticion(rol, "O10", "L", {})
	}
}

# ---------------------------------------------------------------------------
# Permisos con condicion, la celda existe, pero hace falta cumplirla
# ---------------------------------------------------------------------------

# Sin los atributos que la condicion mira, se niega. Un atributo ausente no es un atributo que valga cualquier cosa
test_celda_con_condicion_sin_atributos_se_niega if {
	# Se pasa atributo vacío, sin finca.zona
	d := autorizacion.decision with input as peticion("TECNICO_CAMPO", "O1", "L", {})
	d.permitido == false
	d.condicion == "C1"
}

# Un técnico de campo solo puede leer fincas asignadas a su zona
test_tecnico_lee_finca_de_su_zona if {
	autorizacion.permitir with input as peticion("TECNICO_CAMPO", "O1", "L", {"finca.zona": "norte"})
}

# Un técnico de campo no puede leer fincas de otra zona
test_tecnico_no_lee_finca_de_otra_zona if {
	not autorizacion.permitir with input as peticion(
		"TECNICO_CAMPO", "O1", "L",
		{"finca.zona": "sur"},
	)
}

# La celda VF -> O3 exige en C que se cumpla C1 Y C2
test_verificador_mide_necesita_zona_y_periodo_abierto if {
	# No se pasa el periodo.estado en atributos
	con_una := peticion("VERIFICADOR", "O3", "C", {"finca.zona": "norte"})
	not autorizacion.permitir with input as con_una

	# Ahora se pasa el periodo.estado
	con_las_dos := peticion(
		"VERIFICADOR", "O3", "C",
		{"finca.zona": "norte", "periodo.estado": "ABIERTO"},
	)
	autorizacion.permitir with input as con_las_dos
}

# Separacion de deberes, un verificador no puede aprobar lo que midió el mismo
test_verificador_no_aprueba_su_propia_medicion if {
	not autorizacion.permitir with input as peticion(
		"VERIFICADOR", "O3", "A",
		{
			"medicion.autor_id": "u-1",
			"contexto.sujeto_midio_en_finca_periodo": false,
		},
	)
}

# Separacion de deberes, un verificador puede aprobar lo que midió otra persona
test_verificador_aprueba_medicion_ajena if {
	autorizacion.permitir with input as peticion(
		"VERIFICADOR", "O3", "A",
		{
			"medicion.autor_id": "u-otro",
			"contexto.sujeto_midio_en_finca_periodo": false,
		},
	)
}

# Un auditor dentro de la ventana de auditoria puede exportar la bitácora
test_auditor_dentro_de_la_ventana if {
	autorizacion.permitir with input as peticion(
		"AUDITOR_EXTERNO", "O11", "X",
		{
			"contexto.hoy": "2026-11-04",
			"auditoria.inicio": "2026-11-01",
			"auditoria.fin": "2026-11-30",
		},
	)
}

# Un auditor fuera de la ventana de auditoria no puede exportar la bitácora
test_auditor_fuera_de_la_ventana if {
	d := autorizacion.decision with input as peticion(
		"AUDITOR_EXTERNO", "O11", "X",
		{
			"contexto.hoy": "2026-12-01",
			"auditoria.inicio": "2026-11-01",
			"auditoria.fin": "2026-11-30",
		},
	)
	d.permitido == false
	d.condicion == "C7"
}

# ---------------------------------------------------------------------------
# Formato de respuesta
# ---------------------------------------------------------------------------

# En Python se obtendría el formato dado
test_la_decision_siempre_trae_las_cuatro_claves if {
	d := autorizacion.decision with input as peticion("DIRECCION_GENERAL", "O1", "L", {})
	object.keys(d) == {"permitido", "motivo", "condicion", "version_politica"} # esto es lo que se tomaría en Python
}

# En caso de que el cuerpo de la petición sea incorrecto, se regresa una respuesta (con negación)
test_la_decision_existe_aunque_la_peticion_sea_basura if {
	d := autorizacion.decision with input as {"hola": "mundo"}
	d.permitido == false
	d.condicion == null
	count(d.motivo) > 0
}
