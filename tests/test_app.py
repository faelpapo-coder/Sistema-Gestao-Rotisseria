import app as project


def test_dashboard_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Painel inicial" in response.data


def test_customer_can_be_created(client):
    response = client.post("/clientes", data={"name": "Joao Silva", "phone": "11999990000"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Joao Silva" in response.data


def test_product_can_be_created(client):
    response = client.post("/produtos", data={"name": "Marmita de frango", "price": "20.00", "stock": "5"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Marmita de frango" in response.data


def test_order_reduces_stock(client):
    client.post("/clientes", data={"name": "Joao Silva", "phone": ""})
    client.post("/produtos", data={"name": "Marmita", "price": "20.00", "stock": "5"})
    with project.get_db() as db:
        customer_id = db.execute("SELECT id FROM customers LIMIT 1").fetchone()["id"]
        product_id = db.execute("SELECT id FROM products LIMIT 1").fetchone()["id"]

    response = client.post("/pedidos", data={
        "customer_id": customer_id, "product_id": product_id, "quantity": "2"
    }, follow_redirects=True)
    assert response.status_code == 200
    with project.get_db() as db:
        stock = db.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()["stock"]
    assert stock == 3


# Fixture simples: cada teste usa um banco temporário.
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    database = tmp_path / "test.db"
    monkeypatch.setattr(project, "DATABASE", database)
    project.init_db()
    project.app.config.update(TESTING=True)
    with project.app.test_client() as test_client:
        yield test_client
