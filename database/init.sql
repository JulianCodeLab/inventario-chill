-- Inventario Chill: estructura inicial de PostgreSQL.
-- Las credenciales y el nombre de la base se configuran desde el entorno.

BEGIN;

CREATE TABLE IF NOT EXISTS productos (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    descripcion VARCHAR(500) NOT NULL DEFAULT '',
    cantidad INTEGER NOT NULL DEFAULT 0,
    precio NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT productos_nombre_valido CHECK (length(trim(nombre)) > 0),
    CONSTRAINT productos_cantidad_valida CHECK (cantidad >= 0),
    CONSTRAINT productos_precio_valido
        CHECK (precio >= 0 AND precio <= 9999999999.99)
);

COMMIT;
