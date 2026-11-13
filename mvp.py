from pathlib import Path
import textwrap, zipfile, os

base = Path("/mnt/data/Sistema-Gestao-Rotisseria")
(base / "templates").mkdir(parents=True, exist_ok=True)
(base / "static").mkdir(parents=True, exist_ok=True)
(base / "tests").mkdir(parents=True, exist_ok=True)

files = {
"app.py": r'''
from datetime import datetime
from pathlib import Path
import sqlite3

from flask import Flask, flash, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "rotisseria.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = "troque-esta-chave-em-producao"


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL CHECK(price >= 0),
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Aguardando preparo',
            total REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price REAL NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        """)


@app.template_filter("currency")
def currency(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@app.route("/")
def dashboard():
    with get_db() as db:
        totals = {
            "orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "customers": db.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
            "products": db.execute("SELECT COUNT(*) FROM products WHERE active=1").fetchone()[0],
            "sales": db.execute("SELECT COALESCE(SUM(total), 0) FROM orders WHERE status='Concluído'").fetchone()[0],
        }
        recent_orders = db.execute("""
            SELECT o.*, c.name AS customer_name
            FROM orders o JOIN customers c ON c.id=o.customer_id
            ORDER BY o.id DESC LIMIT 5
        """).fetchall()
    return render_template("dashboard.html", totals=totals, recent_orders=recent_orders)


@app.route("/clientes", methods=["GET", "POST"])
def customers():
    with get_db() as db:
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            if not name:
                flash("Informe o nome do cliente.", "error")
            else:
                db.execute("INSERT INTO customers(name, phone) VALUES (?, ?)", (name, phone))
                db.commit()
                flash("Cliente cadastrado com sucesso.", "success")
                return redirect(url_for("customers"))
        rows = db.execute("SELECT * FROM customers ORDER BY name").fetchall()
    return render_template("customers.html", customers=rows)


@app.route("/produtos", methods=["GET", "POST"])
def products():
    with get_db() as db:
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            try:
                price = float(request.form.get("price", "0").replace(",", "."))
                stock = int(request.form.get("stock", "0"))
                if not name or price < 0 or stock < 0:
                    raise ValueError
            except ValueError:
                flash("Preencha os dados do produto corretamente.", "error")
            else:
                db.execute(
                    "INSERT INTO products(name, price, stock) VALUES (?, ?, ?)",
                    (name, price, stock),
                )
                db.commit()
                flash("Produto cadastrado com sucesso.", "success")
                return redirect(url_for("products"))
        rows = db.execute("SELECT * FROM products WHERE active=1 ORDER BY name").fetchall()
    return render_template("products.html", products=rows)


@app.route("/pedidos", methods=["GET", "POST"])
def orders():
    with get_db() as db:
        if request.method == "POST":
            customer_id = request.form.get("customer_id", type=int)
            product_id = request.form.get("product_id", type=int)
            quantity = request.form.get("quantity", type=int)

            customer = db.execute("SELECT id FROM customers WHERE id=?", (customer_id,)).fetchone()
            product = db.execute("SELECT * FROM products WHERE id=? AND active=1", (product_id,)).fetchone()

            if not customer or not product or not quantity or quantity < 1:
                flash("Selecione um cliente e um produto e informe uma quantidade válida.", "error")
            elif product["stock"] < quantity:
                flash(f"Estoque insuficiente. Disponível: {product['stock']} unidade(s).", "error")
            else:
                total = product["price"] * quantity
                cursor = db.execute(
                    "INSERT INTO orders(customer_id, created_at, total) VALUES (?, ?, ?)",
                    (customer_id, datetime.now().strftime("%d/%m/%Y %H:%M"), total),
                )
                order_id = cursor.lastrowid
                db.execute(
                    "INSERT INTO order_items(order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                    (order_id, product_id, quantity, product["price"]),
                )
                db.execute("UPDATE products SET stock = stock - ? WHERE id=?", (quantity, product_id))
                db.commit()
                flash(f"Pedido #{order_id} cadastrado com sucesso.", "success")
                return redirect(url_for("orders"))

        customer_rows = db.execute("SELECT * FROM customers ORDER BY name").fetchall()
        product_rows = db.execute("SELECT * FROM products WHERE active=1 AND stock>0 ORDER BY name").fetchall()
        order_rows = db.execute("""
            SELECT o.*, c.name AS customer_name,
                   GROUP_CONCAT(p.name || ' (' || oi.quantity || ' un.)', ', ') AS items
            FROM orders o
            JOIN customers c ON c.id=o.customer_id
            LEFT JOIN order_items oi ON oi.order_id=o.id
            LEFT JOIN products p ON p.id=oi.product_id
            GROUP BY o.id
            ORDER BY o.id DESC
        """).fetchall()
    return render_template(
        "orders.html", customers=customer_rows, products=product_rows, orders=order_rows,
        statuses=["Aguardando preparo", "Em preparo", "Pronto", "Concluído", "Cancelado"]
    )


@app.post("/pedidos/<int:order_id>/status")
def update_order_status(order_id):
    allowed = {"Aguardando preparo", "Em preparo", "Pronto", "Concluído", "Cancelado"}
    status = request.form.get("status")
    if status not in allowed:
        flash("Status inválido.", "error")
    else:
        with get_db() as db:
            exists = db.execute("SELECT id FROM orders WHERE id=?", (order_id,)).fetchone()
            if exists:
                db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
                db.commit()
                flash(f"Status do pedido #{order_id} atualizado.", "success")
            else:
                flash("Pedido não encontrado.", "error")
    return redirect(url_for("orders"))


@app.route("/historico")
def history():
    with get_db() as db:
        rows = db.execute("""
            SELECT o.*, c.name AS customer_name,
                   GROUP_CONCAT(p.name || ' (' || oi.quantity || ' un.)', ', ') AS items
            FROM orders o
            JOIN customers c ON c.id=o.customer_id
            LEFT JOIN order_items oi ON oi.order_id=o.id
            LEFT JOIN products p ON p.id=oi.product_id
            GROUP BY o.id
            ORDER BY o.id DESC
        """).fetchall()
    return render_template("history.html", orders=rows)


@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("Banco de dados inicializado.")


init_db()

if __name__ == "__main__":
    app.run(debug=True)
''',
"templates/base.html": r'''
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Rotisseria Fácil{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
<header class="topbar">
  <a class="brand" href="{{ url_for('dashboard') }}">🍽️ Rotisseria Fácil</a>
  <nav aria-label="Navegação principal">
    <a href="{{ url_for('dashboard') }}">Início</a>
    <a href="{{ url_for('customers') }}">Clientes</a>
    <a href="{{ url_for('products') }}">Produtos</a>
    <a href="{{ url_for('orders') }}">Pedidos</a>
    <a href="{{ url_for('history') }}">Histórico</a>
  </nav>
</header>
<main class="container">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      <section aria-label="Mensagens do sistema">
      {% for category, message in messages %}
        <p class="flash {{ category }}" role="status">{{ message }}</p>
      {% endfor %}
      </section>
    {% endif %}
  {% endwith %}
  {% block content %}{% endblock %}
</main>
<footer>Rotisseria Fácil · MVP acadêmico</footer>
</body>
</html>
''',
"templates/dashboard.html": r'''
{% extends "base.html" %}
{% block title %}Início | Rotisseria Fácil{% endblock %}
{% block content %}
<h1>Painel inicial</h1>
<p class="intro">Acompanhe as principais informações da rotisseria.</p>
<section class="stats">
  <article class="stat"><span>Pedidos registrados</span><strong>{{ totals.orders }}</strong></article>
  <article class="stat"><span>Clientes</span><strong>{{ totals.customers }}</strong></article>
  <article class="stat"><span>Produtos ativos</span><strong>{{ totals.products }}</strong></article>
  <article class="stat"><span>Vendas concluídas</span><strong>{{ totals.sales|currency }}</strong></article>
</section>
<section class="panel">
  <div class="section-heading"><h2>Pedidos recentes</h2><a class="button" href="{{ url_for('orders') }}">Gerenciar pedidos</a></div>
  {% if recent_orders %}
  <div class="table-wrap"><table>
    <thead><tr><th>Nº</th><th>Cliente</th><th>Data</th><th>Status</th><th>Total</th></tr></thead>
    <tbody>{% for order in recent_orders %}
    <tr><td>#{{ order.id }}</td><td>{{ order.customer_name }}</td><td>{{ order.created_at }}</td><td><span class="status">{{ order.status }}</span></td><td>{{ order.total|currency }}</td></tr>
    {% endfor %}</tbody>
  </table></div>
  {% else %}<p class="empty">Nenhum pedido cadastrado ainda.</p>{% endif %}
</section>
{% endblock %}
''',
"templates/customers.html": r'''
{% extends "base.html" %}
{% block title %}Clientes | Rotisseria Fácil{% endblock %}
{% block content %}
<h1>Clientes</h1>
<section class="panel">
  <h2>Cadastrar cliente</h2>
  <form method="post" class="form-grid">
    <label>Nome do cliente<input name="name" required maxlength="100" placeholder="Ex.: João Silva"></label>
    <label>Telefone<input name="phone" maxlength="30" placeholder="Ex.: (11) 99999-9999"></label>
    <button class="button" type="submit">Salvar cliente</button>
  </form>
</section>
<section class="panel">
  <h2>Clientes cadastrados</h2>
  {% if customers %}<div class="table-wrap"><table>
    <thead><tr><th>Nome</th><th>Telefone</th></tr></thead>
    <tbody>{% for customer in customers %}<tr><td>{{ customer.name }}</td><td>{{ customer.phone or "Não informado" }}</td></tr>{% endfor %}</tbody>
  </table></div>{% else %}<p class="empty">Nenhum cliente cadastrado.</p>{% endif %}
</section>
{% endblock %}
''',
"templates/products.html": r'''
{% extends "base.html" %}
{% block title %}Produtos | Rotisseria Fácil{% endblock %}
{% block content %}
<h1>Produtos e estoque</h1>
<section class="panel">
  <h2>Cadastrar produto</h2>
  <form method="post" class="form-grid">
    <label>Nome do produto<input name="name" required maxlength="100" placeholder="Ex.: Marmita de frango"></label>
    <label>Preço (R$)<input name="price" type="number" min="0" step="0.01" required placeholder="20.00"></label>
    <label>Quantidade em estoque<input name="stock" type="number" min="0" step="1" required value="0"></label>
    <button class="button" type="submit">Salvar produto</button>
  </form>
</section>
<section class="panel">
  <h2>Produtos cadastrados</h2>
  {% if products %}<div class="table-wrap"><table>
    <thead><tr><th>Produto</th><th>Preço</th><th>Estoque</th></tr></thead>
    <tbody>{% for product in products %}<tr><td>{{ product.name }}</td><td>{{ product.price|currency }}</td><td>{{ product.stock }}</td></tr>{% endfor %}</tbody>
  </table></div>{% else %}<p class="empty">Nenhum produto cadastrado.</p>{% endif %}
</section>
{% endblock %}
''',
"templates/orders.html": r'''
{% extends "base.html" %}
{% block title %}Pedidos | Rotisseria Fácil{% endblock %}
{% block content %}
<h1>Gerenciamento de pedidos</h1>
<section class="panel">
  <h2>Novo pedido</h2>
  {% if not customers or not products %}
    <p class="notice">Para cadastrar um pedido, primeiro registre pelo menos um cliente e um produto com estoque disponível.</p>
  {% endif %}
  <form method="post" class="form-grid">
    <label>Cliente
      <select name="customer_id" required>
        <option value="">Selecione um cliente</option>
        {% for customer in customers %}<option value="{{ customer.id }}">{{ customer.name }}</option>{% endfor %}
      </select>
    </label>
    <label>Produto
      <select name="product_id" required>
        <option value="">Selecione um produto</option>
        {% for product in products %}<option value="{{ product.id }}">{{ product.name }} — {{ product.price|currency }} ({{ product.stock }} disponíveis)</option>{% endfor %}
      </select>
    </label>
    <label>Quantidade<input name="quantity" type="number" min="1" step="1" required value="1"></label>
    <button class="button" type="submit" {% if not customers or not products %}disabled{% endif %}>Cadastrar pedido</button>
  </form>
</section>
<section class="panel">
  <h2>Pedidos registrados</h2>
  {% if orders %}<div class="table-wrap"><table>
    <thead><tr><th>Pedido</th><th>Cliente</th><th>Itens</th><th>Data</th><th>Total</th><th>Status</th><th>Atualizar</th></tr></thead>
    <tbody>{% for order in orders %}
    <tr>
      <td>#{{ order.id }}</td><td>{{ order.customer_name }}</td><td>{{ order.items or "—" }}</td>
      <td>{{ order.created_at }}</td><td>{{ order.total|currency }}</td>
      <td><span class="status">{{ order.status }}</span></td>
      <td><form method="post" action="{{ url_for('update_order_status', order_id=order.id) }}" class="inline-form">
        <label class="sr-only" for="status-{{ order.id }}">Status do pedido {{ order.id }}</label>
        <select id="status-{{ order.id }}" name="status">
          {% for status in statuses %}<option value="{{ status }}" {% if status == order.status %}selected{% endif %}>{{ status }}</option>{% endfor %}
        </select>
        <button class="button small" type="submit">Salvar</button>
      </form></td>
    </tr>{% endfor %}</tbody>
  </table></div>{% else %}<p class="empty">Nenhum pedido cadastrado.</p>{% endif %}
</section>
{% endblock %}
''',
"templates/history.html": r'''
{% extends "base.html" %}
{% block title %}Histórico | Rotisseria Fácil{% endblock %}
{% block content %}
<h1>Histórico de pedidos</h1>
<section class="panel">
  {% if orders %}<div class="table-wrap"><table>
    <thead><tr><th>Pedido</th><th>Cliente</th><th>Itens</th><th>Data</th><th>Total</th><th>Status</th></tr></thead>
    <tbody>{% for order in orders %}<tr>
      <td>#{{ order.id }}</td><td>{{ order.customer_name }}</td><td>{{ order.items or "—" }}</td>
      <td>{{ order.created_at }}</td><td>{{ order.total|currency }}</td><td><span class="status">{{ order.status }}</span></td>
    </tr>{% endfor %}</tbody>
  </table></div>{% else %}<p class="empty">O histórico aparecerá quando houver pedidos cadastrados.</p>{% endif %}
</section>
{% endblock %}
''',
"static/style.css": r'''
:root { font-family: Arial, Helvetica, sans-serif; color: #2c2926; background: #f7f5f1; }
* { box-sizing: border-box; }
body { margin: 0; }
.topbar { background: #713b2b; color: white; padding: 16px max(5%, calc((100% - 1100px)/2)); display: flex; align-items: center; justify-content: space-between; gap: 20px; flex-wrap: wrap; }
.brand { color: white; font-size: 1.2rem; font-weight: 700; text-decoration: none; }
nav { display: flex; gap: 16px; flex-wrap: wrap; }
nav a { color: white; text-decoration: none; font-weight: 600; }
nav a:hover, nav a:focus { text-decoration: underline; }
.container { max-width: 1100px; margin: 32px auto; padding: 0 18px; min-height: 70vh; }
h1 { margin-bottom: 8px; color: #4d2c22; }
h2 { margin-top: 0; font-size: 1.15rem; }
.intro { color: #68615c; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 24px 0; }
.stat, .panel { background: white; border: 1px solid #e8e0d9; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px #3420160b; }
.stat span { display: block; color: #6e6660; font-size: .92rem; }
.stat strong { display: block; color: #713b2b; font-size: 1.7rem; margin-top: 8px; }
.panel { margin: 20px 0; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); align-items: end; gap: 14px; }
label { display: grid; gap: 7px; font-size: .92rem; font-weight: 600; }
input, select { width: 100%; min-height: 42px; border: 1px solid #cfc5bd; border-radius: 7px; padding: 9px 10px; background: white; color: #292522; font: inherit; }
input:focus, select:focus, button:focus, a:focus { outline: 3px solid #e5a45b; outline-offset: 2px; }
.button { display: inline-block; border: 0; border-radius: 7px; background: #713b2b; color: white; padding: 11px 16px; font-weight: 700; cursor: pointer; text-decoration: none; min-height: 42px; }
.button:hover { background: #542a20; }
.button:disabled { opacity: .5; cursor: not-allowed; }
.button.small { padding: 8px 10px; min-height: 36px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; text-align: left; }
th, td { padding: 12px 10px; border-bottom: 1px solid #eee8e2; vertical-align: middle; }
th { color: #5b3428; background: #fbf8f5; }
.status { display: inline-block; background: #f2e8df; border-radius: 20px; padding: 5px 9px; font-size: .85rem; font-weight: 700; }
.inline-form { display: flex; align-items: center; gap: 6px; min-width: 190px; }
.inline-form select { min-width: 130px; }
.flash, .notice { padding: 12px 14px; border-radius: 8px; }
.flash.success { background: #e6f4e8; color: #205b2b; }
.flash.error { background: #fde9e7; color: #8a2118; }
.notice { background: #fff3d9; color: #684914; }
.empty { color: #6e6660; padding: 12px 0; }
footer { text-align: center; padding: 22px; color: #746b64; font-size: .9rem; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@media (max-width: 620px) { .topbar { align-items: flex-start; } nav { gap: 10px 14px; } .container { margin-top: 22px; } }
''',
"requirements.txt": "Flask==3.1.0\npytest==8.3.4\n",
"README.md": r'''
# Sistema de Gestão da Rotisseria

MVP acadêmico desenvolvido em Python 3.12, Flask e SQLite para apoiar a rotina de uma rotisseria.

## Funcionalidades

- Painel inicial com resumo de pedidos, clientes, produtos e vendas concluídas.
- Cadastro e consulta de clientes.
- Cadastro de produtos com preço e quantidade em estoque.
- Cadastro de pedidos com cliente, produto e quantidade.
- Baixa automática do estoque ao registrar um pedido.
- Atualização do status: Aguardando preparo, Em preparo, Pronto, Concluído ou Cancelado.
- Histórico de pedidos.

## Requisitos

- Python 3.12 ou superior
- pip

## Como executar

1. Baixe ou clone este repositório.
2. Abra o terminal na pasta do projeto.
3. Crie um ambiente virtual:

   ```bash
   python -m venv .venv
   ```

4. Ative o ambiente virtual:

   **Windows**
   ```bash
   .venv\Scripts\activate
   ```

   **Linux/macOS**
   ```bash
   source .venv/bin/activate
   ```

5. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

6. Inicie o sistema:

   ```bash
   python app.py
   ```

7. Acesse no navegador: http://127.0.0.1:5000

O banco `rotisseria.db` é criado automaticamente na primeira execução.

## Fluxo recomendado para testar

1. Cadastre um cliente (ex.: João Silva).
2. Cadastre um produto (ex.: Marmita de frango), com preço e estoque.
3. Acesse Pedidos e registre o pedido do cliente.
4. Atualize o status do pedido e consulte o Histórico.

## Estrutura

```text
Sistema-Gestao-Rotisseria/
├── app.py
├── requirements.txt
├── README.md
├── rotisseria.db       # criado automaticamente ao executar
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── customers.html
│   ├── products.html
│   ├── orders.html
│   └── history.html
├── static/
│   └── style.css
└── tests/
```

## Observações

Este projeto é um MVP educacional. Antes de uso real, é necessário configurar uma chave secreta segura, autenticação e autorização de usuários, proteção contra CSRF, validações adicionais, política de backups e testes mais abrangentes. Não utilize dados pessoais reais durante a demonstração acadêmica.
''',
".gitignore": r'''
.venv/
__pycache__/
.pytest_cache/
*.py[cod]
rotisseria.db
.env
''',
"tests/test_app.py": r'''
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
'''.lstrip()
}

for name, content in files.items():
    path = base / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")

zip_path = Path("/mnt/data/Sistema-Gestao-Rotisseria-MVP.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in base.rglob("*"):
        if path.is_file():
            zf.write(path, path.relative_to(base.parent))

print(f"Projeto criado: {zip_path}")
print("Arquivos:", len(files))
