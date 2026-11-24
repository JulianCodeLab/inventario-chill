"""Pruebas de validación y rutas Flask, sin depender de una base de datos externa.

Las conexiones se sustituyen por dobles de prueba. El despliegue comprueba
por separado la comunicación real con PostgreSQL mediante /health y HTTP.
"""

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import psycopg
import pytest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
SPEC = importlib.util.spec_from_file_location("inventario_app_tests", APP_PATH)
inventario = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventario
SPEC.loader.exec_module(inventario)


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setitem(inventario.app.config, "TESTING", True)
    with inventario.app.test_client() as cliente:
        with cliente.session_transaction() as sesion:
            sesion["csrf_token"] = "token-pruebas"
        yield cliente


@pytest.fixture
def base_simulada(monkeypatch):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.execute.return_value.fetchall.return_value = []
    conexion.execute.return_value.fetchone.return_value = {"id": 1}
    fabrica = MagicMock(return_value=conexion)
    monkeypatch.setattr(inventario, "conectar", fabrica)
    return conexion, fabrica


@pytest.fixture
def datos():
    return {
        "nombre": "Cuaderno",
        "descripcion": "Universitario",
        "cantidad": "10",
        "precio": "5000.00",
        "csrf_token": "token-pruebas",
    }


def test_validacion_limpia_espacios_y_conserva_decimal(datos):
    datos["nombre"] = "  Cuaderno  "
    assert inventario.validar_producto(datos) == (
        "Cuaderno", "Universitario", 10, Decimal("5000.00")
    )


@pytest.mark.parametrize("campo,valor", [
    ("nombre", ""), ("nombre", "   "), ("nombre", "x" * 121),
    ("descripcion", "x" * 501),
    ("cantidad", "-1"), ("cantidad", "1.5"), ("cantidad", "texto"),
    ("cantidad", "2147483648"),
    ("precio", "-1"), ("precio", "texto"), ("precio", "NaN"),
    ("precio", "Infinity"), ("precio", "10000000000"), ("precio", "1.001"),
])
def test_rechaza_datos_invalidos(datos, campo, valor):
    datos[campo] = valor
    with pytest.raises(ValueError):
        inventario.validar_producto(datos)


def test_acepta_cantidad_y_precio_cero(datos):
    datos.update(cantidad="0", precio="0")
    assert inventario.validar_producto(datos)[2:] == (0, Decimal("0"))


def test_consulta_inventario_vacio(cliente, base_simulada):
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "Aún no hay productos" in respuesta.get_data(as_text=True)


def test_busqueda_trata_el_texto_como_parametro(cliente, base_simulada):
    conexion, _ = base_simulada
    consulta = "O'Reilly"
    assert cliente.get("/", query_string={"q": consulta}).status_code == 200
    sql, parametros = conexion.execute.call_args.args
    assert consulta not in sql
    assert parametros == ("%O'Reilly%", "%O'Reilly%")


def test_escapa_html_de_productos(cliente, base_simulada):
    conexion, _ = base_simulada
    conexion.execute.return_value.fetchall.return_value = [{
        "id": 1, "nombre": "<script>alert(1)</script>", "descripcion": "",
        "cantidad": 1, "precio": Decimal("2.50"),
    }]
    html = cliente.get("/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_registra_producto_y_confirma_al_usuario(cliente, base_simulada, datos):
    conexion, _ = base_simulada
    respuesta = cliente.post("/productos", data=datos, follow_redirects=True)
    assert respuesta.status_code == 200
    assert "Producto registrado correctamente" in respuesta.get_data(as_text=True)
    assert conexion.execute.call_args_list[0].args[1] == (
        "Cuaderno", "Universitario", 10, Decimal("5000.00")
    )


@pytest.mark.parametrize("ruta", ["/productos", "/productos/1/actualizar", "/productos/1/eliminar"])
def test_cambios_sin_token_no_acceden_a_la_base(cliente, base_simulada, datos, ruta):
    _, fabrica = base_simulada
    datos.pop("csrf_token")
    assert cliente.post(ruta, data=datos).status_code == 400
    fabrica.assert_not_called()


def test_registro_invalido_no_escribe(cliente, base_simulada, datos):
    _, fabrica = base_simulada
    datos["cantidad"] = "-1"
    assert cliente.post("/productos", data=datos).status_code == 302
    fabrica.assert_not_called()


def test_formulario_editar_muestra_producto(cliente, base_simulada):
    conexion, _ = base_simulada
    conexion.execute.return_value.fetchone.return_value = {
        "id": 7, "nombre": "Cuaderno", "descripcion": "Universitario",
        "cantidad": 10, "precio": Decimal("5000"),
    }
    respuesta = cliente.get("/productos/7/editar")
    assert respuesta.status_code == 200
    assert 'value="Cuaderno"' in respuesta.get_data(as_text=True)
    assert "/productos/7/actualizar" in respuesta.get_data(as_text=True)


def test_actualiza_producto(cliente, base_simulada, datos):
    conexion, _ = base_simulada
    datos["cantidad"] = "15"
    respuesta = cliente.post("/productos/7/actualizar", data=datos)
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/"
    assert conexion.execute.call_args.args[1] == (
        "Cuaderno", "Universitario", 15, Decimal("5000.00"), 7
    )


def test_actualizacion_invalida_no_escribe(cliente, base_simulada, datos):
    _, fabrica = base_simulada
    datos["precio"] = "-10"
    respuesta = cliente.post("/productos/7/actualizar", data=datos)
    assert respuesta.headers["Location"] == "/productos/7/editar"
    fabrica.assert_not_called()


def test_elimina_producto(cliente, base_simulada):
    conexion, _ = base_simulada
    respuesta = cliente.post("/productos/7/eliminar", data={"csrf_token": "token-pruebas"})
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/"
    assert conexion.execute.call_args.args[1] == (7,)


@pytest.mark.parametrize("ruta,metodo", [
    ("/productos/999/editar", "get"),
    ("/productos/999/actualizar", "post"),
    ("/productos/999/eliminar", "post"),
])
def test_producto_inexistente_devuelve_404(cliente, base_simulada, datos, ruta, metodo):
    conexion, _ = base_simulada
    conexion.execute.return_value.fetchone.return_value = None
    respuesta = cliente.get(ruta) if metodo == "get" else cliente.post(ruta, data=datos)
    assert respuesta.status_code == 404


def test_health_consulta_base(cliente, base_simulada):
    conexion, _ = base_simulada
    respuesta = cliente.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json == {"estado": "ok"}
    conexion.execute.assert_called_once()


def test_error_postgresql_no_expone_detalles(cliente, monkeypatch):
    def fallo():
        raise psycopg.OperationalError("detalle-interno-de-prueba")
    monkeypatch.setattr(inventario, "conectar", fallo)
    respuesta = cliente.get("/")
    assert respuesta.status_code == 503
    assert "detalle-interno-de-prueba" not in respuesta.get_data(as_text=True)
