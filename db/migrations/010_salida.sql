-- 010  Bandeja de salida   (persona 5)
--
-- Cada operacion escribe aqui su evento EN LA MISMA TRANSACCION que la
-- operacion. Por eso es imposible que una operacion ocurra sin su evento: si
-- la operacion se confirma, el evento esta.
--
-- Y si la bitacora esta caida, la operacion no falla y el evento no se pierde.
-- El transmisor los copia despues a la otra base y marca enviado_en.

CREATE TABLE eventos_pendientes (
    id         integer          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- La pone esta base, nunca el cliente.
    momento    timestamptz      NOT NULL DEFAULT now(),

    accion     text             NOT NULL,
    sujeto     text             NOT NULL,
    objeto     text             NOT NULL,
    resultado  resultado_evento NOT NULL,
    motivo     text,

    -- Contexto, sin datos personales ni secretos.
    detalle    jsonb,

    enviado_en timestamptz,

    CONSTRAINT denegado_lleva_motivo
        CHECK (resultado = 'PERMITIDO' OR motivo IS NOT NULL)
);

-- Sin llaves foraneas a proposito: un evento describe lo que paso y no
-- depende de que la fila que lo origino siga existiendo. Por eso sujeto y
-- objeto son texto ('O5:7') y no referencias.

-- Lo unico que el transmisor consulta. Parcial, asi que el indice se mantiene
-- pequeno por mas eventos que se acumulen.
CREATE INDEX eventos_pendientes_sin_enviar_idx
    ON eventos_pendientes (momento)
    WHERE enviado_en IS NULL;

-- ---------------------------------------------------------------------------
-- El transmisor, del lado de la base principal
-- ---------------------------------------------------------------------------
-- outbox_rw ve esta tabla y ninguna otra. Y de esta tabla solo puede cambiar
-- enviado_en: si lo comprometen, no puede reescribir lo que un evento dice,
-- solo marcar que ya lo copio.

GRANT SELECT              ON eventos_pendientes TO outbox_rw;
GRANT UPDATE (enviado_en) ON eventos_pendientes TO outbox_rw;
