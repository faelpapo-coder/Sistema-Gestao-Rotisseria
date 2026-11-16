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
                db.execute(
                    "INSERT INTO customers(name, phone) VALUES (?, ?)",
                    (name, phone)
                )
                db.commit()
                flash("Cliente cadastrado com sucesso.", "success")
                return redirect(url_for("customers"))

        search = request.args.get("q", "").strip()

        rows = db.execute("""
            SELECT * FROM customers
            WHERE name LIKE ? OR phone LIKE ?
            ORDER BY name
        """, (f"%{search}%", f"%{search}%")).fetchall()

    return render_template(
        "customers.html",
        customers=rows,
        search=search
    )


@app.post("/clientes/<int:customer_id>/editar")
def edit_customer(customer_id):
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()

    if not name:
        flash("Informe o nome do cliente.", "error")
        return redirect(url_for("customers"))

    with get_db() as db:
        customer = db.execute(
            "SELECT id FROM customers WHERE id = ?",
            (customer_id,)
        ).fetchone()

        if not customer:
            flash("Cliente não encontrado.", "error")
        else:
            db.execute(
                "UPDATE customers SET name=?, phone=? WHERE id=?",
                (name, phone, customer_id)
            )
            db.commit()
            flash("Cliente atualizado com sucesso.", "success")

    return redirect(url_for("customers"))


@app.post("/clientes/<int:customer_id>/excluir")
def delete_customer(customer_id):
    with get_db() as db:
        customer = db.execute(
            "SELECT id FROM customers WHERE id=?",
            (customer_id,)
        ).fetchone()

        if not customer:
            flash("Cliente não encontrado.", "error")
        else:
            orders = db.execute(
                "SELECT id FROM orders WHERE customer_id=?",
                (customer_id,)
            ).fetchone()

            if orders:
                flash(
                    "Não é possível excluir: este cliente possui pedidos registrados.",
                    "error"
                )
            else:
                db.execute(
                    "DELETE FROM customers WHERE id=?",
                    (customer_id,)
                )
                db.commit()
                flash("Cliente excluído com sucesso.", "success")

    return redirect(url_for("customers"))




@app.route("/produtos", methods=["GET", "POST"])
def products():
    with get_db() as db:
        if request.method == "POST":
            name = request.form.get("name", "").strip()

            try:
                price = float(
                    request.form.get("price", "0").replace(",", ".")
                )
                stock = int(request.form.get("stock", "0"))

                if not name or price < 0 or stock < 0:
                    raise ValueError

            except ValueError:
                flash("Preencha os dados do produto corretamente.", "error")
            else:
                db.execute(
                    "INSERT INTO products(name, price, stock) VALUES (?, ?, ?)",
                    (name, price, stock)
                )
                db.commit()

                flash("Produto cadastrado com sucesso.", "success")
                return redirect(url_for("products"))

        search = request.args.get("q", "").strip()

        rows = db.execute("""
            SELECT * FROM products
            WHERE name LIKE ?
            ORDER BY name
        """, (f"%{search}%",)).fetchall()

    return render_template(
        "products.html",
        products=rows,
        search=search
    )


@app.post("/produtos/<int:product_id>/editar")
def edit_product(product_id):
    name = request.form.get("name", "").strip()

    try:
        price = float(
            request.form.get("price", "0").replace(",", ".")
        )
        stock = int(request.form.get("stock", "0"))

        if not name or price < 0 or stock < 0:
            raise ValueError

    except ValueError:
        flash("Preencha os dados do produto corretamente.", "error")
        return redirect(url_for("products"))

    with get_db() as db:
        product = db.execute(
            "SELECT id FROM products WHERE id=?",
            (product_id,)
        ).fetchone()

        if not product:
            flash("Produto não encontrado.", "error")
        else:
            db.execute("""
                UPDATE products
                SET name=?, price=?, stock=?
                WHERE id=?
            """, (name, price, stock, product_id))

            db.commit()
            flash("Produto atualizado com sucesso.", "success")

    return redirect(url_for("products"))


@app.post("/produtos/<int:product_id>/alternar")
def toggle_product(product_id):
    with get_db() as db:
        product = db.execute(
            "SELECT id, active FROM products WHERE id=?",
            (product_id,)
        ).fetchone()

        if not product:
            flash("Produto não encontrado.", "error")
        else:
            new_status = 0 if product["active"] else 1

            db.execute(
                "UPDATE products SET active=? WHERE id=?",
                (new_status, product_id)
            )

            db.commit()

            if new_status:
                flash("Produto ativado com sucesso.", "success")
            else:
                flash("Produto desativado com sucesso.", "success")

    return redirect(url_for("products"))


@app.route("/pedidos", methods=["GET", "POST"])
def orders():
    with get_db() as db:
        if request.method == "POST":
            customer_id = request.form.get("customer_id", type=int)
            product_id = request.form.get("product_id", type=int)
            quantity = request.form.get("quantity", type=int)

            customer = db.execute(
                "SELECT id FROM customers WHERE id=?",
                (customer_id,)
            ).fetchone()

            product = db.execute(
                "SELECT * FROM products WHERE id=? AND active=1",
                (product_id,)
            ).fetchone()

            if not customer or not product or not quantity or quantity < 1:
                flash(
                    "Selecione um cliente e um produto e informe uma quantidade válida.",
                    "error"
                )

            elif product["stock"] < quantity:
                flash(
                    f"Estoque insuficiente. Disponível: {product['stock']} unidade(s).",
                    "error"
                )

            else:
                total = product["price"] * quantity

                cursor = db.execute(
                    "INSERT INTO orders(customer_id, created_at, total) VALUES (?, ?, ?)",
                    (
                        customer_id,
                        datetime.now().strftime("%d/%m/%Y %H:%M"),
                        total
                    )
                )

                order_id = cursor.lastrowid

                db.execute(
                    "INSERT INTO order_items(order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                    (order_id, product_id, quantity, product["price"])
                )

                db.execute(
                    "UPDATE products SET stock = stock - ? WHERE id=?",
                    (quantity, product_id)
                )

                db.commit()

                flash(
                    f"Pedido #{order_id} cadastrado com sucesso.",
                    "success"
                )

                return redirect(url_for("orders"))

        customer_rows = db.execute(
            "SELECT * FROM customers ORDER BY name"
        ).fetchall()

        product_rows = db.execute(
            "SELECT * FROM products WHERE active=1 AND stock>0 ORDER BY name"
        ).fetchall()

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
        "orders.html",
        customers=customer_rows,
        products=product_rows,
        orders=order_rows,
        statuses=[
            "Aguardando preparo",
            "Em preparo",
            "Pronto",
            "Concluído",
            "Cancelado"
        ]
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
