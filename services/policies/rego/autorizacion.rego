package verdeazul.autorizacion

import data.verdeazul.condiciones # se trae las condiciones de condiciones.rego
import rego.v1

# Identifica el conjunto de reglas que decidió. Va al evento de bitacora, para
# que despues se pueda saber que politica estaba corriendo cuando se concedio o
# se nego algo. Se sube a mano cuando la matriz cambia.
version_politica := "matriz-p1-v1"

# ---------------------------------------------------------------------------
# La matriz. 8 roles x 11 objetos = 88 celdas, todas presentes.
#
# Una celda es un objeto {operacion: [condiciones]}:
#
#   "L": []                 el permiso depende solo del rol
#   "L": ["C8"]             el permiso exige que C8 se cumpla
#   "C": ["C1", "C2"]       exige las dos (el C1 ^ C2 de la matriz)
#   {}                      el rol no tiene ningun permiso sobre el objeto
#
# Las celdas vacias se escriben igual que las demas, a proposito: una celda que
# falta no es una celda vacia, es una celda sobre la que nadie decidio.
# ---------------------------------------------------------------------------

# Matriz de control de acceso
matriz := {
	# Direccion General: lectura transversal, y modifica su propia credencial.
	"DIRECCION_GENERAL": {
		"O1": {"L": []},
		"O2": {"L": []},
		"O3": {"L": []},
		"O4": {"L": []},
		"O5": {"L": []},
		"O6": {"L": []},
		"O7": {"L": []},
		"O8": {"L": []},
		"O9": {"L": []},
		"O10": {"M": []},
		"O11": {"L": [], "X": []},
	},
	# Direccion de Certificacion: abre y cierra periodos, anula certificados,
	# cierra enmiendas como tercera persona (C5).
	"DIRECCION_CERTIFICACION": {
		"O1": {"L": []},
		"O2": {"L": [], "Ab": [], "Cr": []},
		"O3": {"L": []},
		"O4": {"L": [], "Cr": ["C5"]},
		"O5": {"L": [], "An": []},
		"O6": {},
		"O7": {},
		"O8": {"L": [], "C": [], "M": []},
		"O9": {},
		"O10": {"M": []},
		"O11": {"L": [], "X": []},
	},
	# Personal Administrativo: el unico que toca datos personales, y toca
	# cuentas solo con aprobacion previa de la Direccion General (C10).
	"PERSONAL_ADMINISTRATIVO": {
		"O1": {"L": [], "C": [], "M": []},
		"O2": {},
		"O3": {},
		"O4": {},
		"O5": {},
		"O6": {"L": [], "C": [], "M": []},
		"O7": {"L": [], "C": []},
		"O8": {},
		"O9": {"L": ["C10"], "C": ["C10"], "M": ["C10"]},
		"O10": {"M": []},
		"O11": {"L": []},
	},
	# Tecnico de campo: solo su zona (C1), solo periodos abiertos (C2), y
	# enmienda lo suyo cuando el periodo ya cerro (C11).
	"TECNICO_CAMPO": {
		"O1": {"L": ["C1"]},
		"O2": {"L": []},
		"O3": {"L": ["C1"], "C": ["C2"]},
		"O4": {"L": ["C1"], "C": ["C11"]},
		"O5": {},
		"O6": {},
		"O7": {},
		"O8": {"L": ["C1"]},
		"O9": {},
		"O10": {"M": []},
		"O11": {},
	},
	# Verificador: aprueba y devuelve lo que no registro el mismo (C3, C4) y
	# emite certificados sin traslape de poligonos (C6). Notese que no tiene M
	# sobre O3: una medicion no se modifica, se enmienda.
	"VERIFICADOR": {
		"O1": {"L": ["C1"]},
		"O2": {"L": []},
		"O3": {"L": [], "C": ["C1", "C2"], "A": ["C3"], "D": ["C3"]},
		"O4": {"L": [], "A": ["C4"], "D": ["C4"]},
		"O5": {"L": [], "Em": ["C6"]},
		"O6": {},
		"O7": {},
		"O8": {"L": ["C1"]},
		"O9": {},
		"O10": {"M": []},
		"O11": {},
	},
	# Auditor externo: todo lo suyo depende de la ventana de auditoria (C7).
	# Fuera de la ventana el permiso no se suspende, deja de existir.
	"AUDITOR_EXTERNO": {
		"O1": {"L": ["C7"]},
		"O2": {"L": ["C7"]},
		"O3": {"L": ["C7"], "X": ["C7"]},
		"O4": {"L": ["C7"], "X": ["C7"]},
		"O5": {"L": ["C7"], "X": ["C7"]},
		"O6": {},
		"O7": {},
		"O8": {},
		"O9": {},
		"O10": {"M": []},
		"O11": {"L": ["C7"], "X": ["C7"]},
	},
	# Dueno de finca: solo lo suyo (C8). O2 es la excepcion, los periodos son
	# informacion general.
	"DUENO_FINCA": {
		"O1": {"L": ["C8"]},
		"O2": {"L": []},
		"O3": {"L": ["C8"]},
		"O4": {"L": ["C8"]},
		"O5": {"L": ["C8"]},
		"O6": {"L": ["C8"]},
		"O7": {"L": ["C8"], "C": ["C8"], "M": ["C8"]},
		"O8": {},
		"O9": {},
		"O10": {"M": []},
		"O11": {},
	},
	# Tercero autorizado: el certificado que le autorizaron, mientras la
	# autorizacion siga vigente (C9). Nada mas.
	"TERCERO_AUTORIZADO": {
		"O1": {},
		"O2": {},
		"O3": {},
		"O4": {},
		"O5": {"L": ["C9"]},
		"O6": {},
		"O7": {},
		"O8": {},
		"O9": {},
		"O10": {"M": []},
		"O11": {},
	},
}

# ---------------------------------------------------------------------------
# Decisiones
# ---------------------------------------------------------------------------

# Denegacion por omision. Lo que no esta concedido explicitamente, se niega.
default permitir := false

# Lista de condiciones que esa celda de la matriz exige, ejm: matriz["TECNICO_CAMPO"]["O1"]["L"] -> ["C1"]
# Si la celda buscada (condición), rol u objeto no existe en la matriz, exigidas = indefinido (se deniega por omision)
exigidas := matriz[input.sujeto.rol][input.objeto.tipo][input.operacion]

# Devuelve True, si exigidas == [] o si exigidas == ["C1", "C2"] y estan en condiciones.cumplidas -> True, de lo conrario False
# Devuelve nada (indefinido) si exigidas == indefinido -> cuerpo falla y permitir cae en dafualt false
permitir if {
	# Para cada condición que la celda exige, esa condición está en el conjunto que el sujeto cumple
	every condicion_celda in exigidas { condicion_celda in condiciones.cumplidas } # condiciones.cumplidas viene de condiciones.rego
}

# El conjunto fallidas contiene cada condicion que la celda exigia y el sujeto no cumplió
# Es una recopilacion de condiciones que no se cumplieron
fallidas contains condicion if {
	# si exigidas es indefinido, entonces no se puede recorrer y no se agregan condiciones a fallidas
	some condicion in exigidas # alguna condicion en exigidas (recorre la lista)

	# Si condición no está en condiciones.cumplidas, entonces se agrega a fallidas
	not condicion in condiciones.cumplidas
}

# ejm: si exigidas = ["C1", "C2"] y solo C1 está en condiciones.cumplidas, entonces fallidas = ["C2"]

# Fallidas siempre está definidas, puede quedar vacía []
condicion := condicion_aux if {
	count(fallidas) > 0 # si está vació se retorna condicion = null (es decir tiene autorización)

	# sort convierte el conjunto en arreglo ordenado, y luego se toma la primera para que el mensaje de denegacion sea consistente
	condicion_aux := sort(fallidas)[0]
} else := null

# El motivo va a la bitacora, solo puede salir un valor
motivo := "concedido: la matriz autoriza esta operacion a este rol" if {
	permitir # si permitir es true
	count(exigidas) == 0 # y si la celda no exige ninguna condicion en esa operacion
} else := sprintf("concedido: se cumplen las condiciones %v", [sort(exigidas)]) if {
	permitir # si permitir es true, quiere decir que habían condiciones pero se cumplieron todas
} else := "denegado: la operacion E (eliminar) no se concede a ningun rol de la matriz" if {
	input.operacion == "E" # En caso de que alguien intenten eliminar algo (nadie lo puede hacer)
} else := sprintf("denegado: la celda exige %v y no se cumple %v", [sort(exigidas), sort(fallidas)]) if {
	count(fallidas) > 0 # se deniega porque hay condiciones que no se cumplen y registran las fallidas
} else := "denegado por omision: la matriz no concede esta operacion a este rol sobre este objeto"

# El backend hace una consulta por HTTP de la forma:
#   POST /v1/data/verdeazul/autorizacion/decision
#   {"input": {"sujeto": {...}, "operacion": "L", "objeto": {...}}}
#
# ver contracts/02-autorizacion.md
# Esta es la respuesta que se le envia al backend
decision := {
	"permitido": permitir,
	"motivo": motivo,
	"condicion": condicion,
	"version_politica": version_politica,
}

# Ejemplo de los tres casos de celda que se pueden dar en la matriz:
# matriz["TECNICO_CAMPO"]["O1"]["L"] -> ["C1"] exige C1
# matriz["DIRECCION_GENERAL"]["O1"]["L"] -> [] no exige nada, el rol tiene permiso sin condición
# matriz["TERCERO_AUTORIZADO"]["O11"]["L"] -> indefinida, esa celda no existe
