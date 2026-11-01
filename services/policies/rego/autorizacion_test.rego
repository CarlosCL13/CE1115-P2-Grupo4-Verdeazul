# Pruebas de las politicas. Se corren con `opa test services/policies/rego/`
# y no necesitan levantar nada.

package verdeazul.autorizacion_test

import data.verdeazul.autorizacion
import rego.v1

# Mientras el relleno este en pie, esta prueba pasa. Cuando F3 empiece a
# conceder celdas, hay que cambiarla por una celda que de verdad no exista en
# la matriz: por ejemplo un tercero autorizado leyendo la bitacora.
test_denegacion_por_omision if {
	not autorizacion.permitir with input as {
		"sujeto": {"id": "u-1", "rol": "DIRECCION_GENERAL", "zonas": []},
		"operacion": "L",
		"objeto": {"tipo": "O1", "atributos": {}},
	}
}

# Esta prueba tiene que seguir pasando para siempre: ninguna celda de la matriz
# concede E. Si algun dia falla, alguien concedio borrado por error.
test_eliminar_nunca_se_concede if {
	not autorizacion.permitir with input as {
		"sujeto": {"id": "u-1", "rol": "DIRECCION_GENERAL", "zonas": []},
		"operacion": "E",
		"objeto": {"tipo": "O1", "atributos": {}},
	}
}

# Un tercero autorizado no tiene ningun permiso sobre la bitacora.
test_tercero_no_lee_bitacora if {
	not autorizacion.permitir with input as {
		"sujeto": {"id": "u-9", "rol": "TERCERO_AUTORIZADO", "zonas": []},
		"operacion": "L",
		"objeto": {"tipo": "O11", "atributos": {}},
	}
}
