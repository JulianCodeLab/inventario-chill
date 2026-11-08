"""Inventario Chill: CRUD de productos con Flask y PostgreSQL."""

import os
import secrets
from decimal import Decimal, InvalidOperation

import psycopg
from psycopg.rows import dict_row
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

app = Flask(__name__)
# Clave temporal para los formularios de esta instancia local; no contiene credenciales.
app.secret_key = secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=64 * 1024, SESSION_COOKIE_SAMESITE="Lax")


def conectar():
    """Lee la configuración de PostgreSQL exclusivamente del entorno."""
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
        row_factory=dict_row,
    )


@app.before_request
def proteger_formularios():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    if request.method == "POST":
        recibido = request.form.get("csrf_token", "")
        if not secrets.compare_digest(recibido, session["csrf_token"]):
            abort(400, description="El formulario venció. Recarga la página e inténtalo otra vez.")


def validar_producto(datos):
    nombre = datos.get("nombre", "").strip()
    descripcion = datos.get("descripcion", "").strip()
    if not nombre or len(nombre) > 120:
        raise ValueError("El nombre es obligatorio y admite hasta 120 caracteres.")
    if len(descripcion) > 500:
        raise ValueError("La descripción admite hasta 500 caracteres.")
    try:
        cantidad = int(datos.get("cantidad", ""))
        precio = Decimal(datos.get("precio", ""))
    except (ValueError, InvalidOperation):
        raise ValueError("Ingresa una cantidad entera y un precio válido.") from None
    if not 0 <= cantidad <= 2147483647:
        raise ValueError("La cantidad debe ser un entero entre 0 y 2147483647.")
    if not precio.is_finite() or not Decimal("0") <= precio <= Decimal("9999999999.99"):
        raise ValueError("El precio debe estar entre 0 y 9999999999.99.")
    if precio != precio.quantize(Decimal("0.01")):
        raise ValueError("El precio admite como máximo dos decimales.")
    return nombre, descripcion, cantidad, precio


@app.get("/")
def index():
    consulta = request.args.get("q", "").strip()[:120]
    with conectar() as conexion:
        productos = conexion.execute(
            "SELECT id, nombre, descripcion, cantidad, precio FROM productos "
            "WHERE nombre ILIKE %s OR descripcion ILIKE %s ORDER BY id DESC",
            (f"%{consulta}%", f"%{consulta}%"),
        ).fetchall()
    return render_template("index.html", productos=productos, consulta=consulta, editar=None)


@app.post("/productos")
def registrar():
    try:
        producto = validar_producto(request.form)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("index"))
    # El contexto confirma la transacción al salir sin errores y cierra la conexión.
    with conectar() as conexion:
        conexion.execute(
            "INSERT INTO productos (nombre, descripcion, cantidad, precio) VALUES (%s, %s, %s, %s)",
            producto,
        )
    flash("Producto registrado correctamente.", "exito")
    return redirect(url_for("index"))


@app.get("/productos/<int:producto_id>/editar")
def editar(producto_id):
    with conectar() as conexion:
        producto = conexion.execute(
            "SELECT id, nombre, descripcion, cantidad, precio FROM productos WHERE id = %s",
            (producto_id,),
        ).fetchone()
    if producto is None:
        abort(404)
    return render_template("index.html", productos=[], consulta="", editar=producto)


@app.post("/productos/<int:producto_id>/actualizar")
def actualizar(producto_id):
    try:
        producto = validar_producto(request.form)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("editar", producto_id=producto_id))
    with conectar() as conexion:
        resultado = conexion.execute(
            "UPDATE productos SET nombre = %s, descripcion = %s, cantidad = %s, precio = %s "
            "WHERE id = %s RETURNING id",
            (*producto, producto_id),
        ).fetchone()
    if resultado is None:
        abort(404)
    flash("Producto actualizado correctamente.", "exito")
    return redirect(url_for("index"))


@app.post("/productos/<int:producto_id>/eliminar")
def eliminar(producto_id):
    with conectar() as conexion:
        resultado = conexion.execute(
            "DELETE FROM productos WHERE id = %s RETURNING id", (producto_id,)
        ).fetchone()
    if resultado is None:
        abort(404)
    flash("Producto eliminado correctamente.", "exito")
    return redirect(url_for("index"))


@app.get("/health")
def health():
    with conectar() as conexion:
        conexion.execute("SELECT 1 FROM productos LIMIT 1")
    return {"estado": "ok"}


@app.errorhandler(psycopg.Error)
def error_base_datos(error):
    # No se muestran credenciales ni detalles internos en el navegador.
    app.logger.error("Error de PostgreSQL: %s", type(error).__name__)
    return "No fue posible consultar la base de datos. Revisa el servicio de PostgreSQL.", 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
