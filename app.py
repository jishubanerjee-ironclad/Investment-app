from flask import Flask, render_template, request, redirect, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import yfinance as yf
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "supersecret123"

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT
                )""")
    db.execute("""CREATE TABLE IF NOT EXISTS holdings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    stock TEXT,
                    qty REAL,
                    price REAL,
                    date TEXT
                )""")
    db.commit()

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

        if user and check_password_hash(user["password"], password):
            session["user"] = username
            return redirect("/dashboard")
        return "Wrong username or password"

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])

        db = get_db()
        try:
            db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            db.commit()
            return redirect("/")
        except:
            return "Username already exists. Go back and try a different one."

    return render_template("register.html")

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/")

    db = get_db()

    # Add holding (client)
    if request.method == "POST":
        stock = request.form["stock"].upper().strip() + ".NS"
        qty = float(request.form["qty"])
        price = float(request.form["price"])
        date = request.form["date"]

        db.execute("INSERT INTO holdings (username, stock, qty, price, date) VALUES (?, ?, ?, ?, ?)",
                   (session["user"], stock, qty, price, date))
        db.commit()

    # Fetch all holdings
    rows = db.execute("SELECT * FROM holdings").fetchall()

    # ADMIN VIEW (username = admin)
    if session.get("user") == "admin":
        by_client = defaultdict(list)
        for r in rows:
            by_client[r["username"]].append(dict(r))

        symbols = list({r["stock"] for r in rows})
        prices = {}
        if symbols:
            data = yf.download(symbols, period="1d", interval="1m", group_by="ticker", progress=False)
            for s in symbols:
                try:
                    prices[s] = float(data[s]["Close"].dropna().iloc[-1])
                except:
                    prices[s] = None

        clients_view = []
        for user, items in by_client.items():
            total_value = 0
            invested = 0
            enriched = []

            for it in items:
                live = prices.get(it["stock"])
                value = (live * it["qty"]) if live else 0
                inv = it["price"] * it["qty"]

                total_value += value
                invested += inv

                enriched.append({**it, "live": live, "value": value, "alloc_pct": 0})

            for it in enriched:
                it["alloc_pct"] = (it["value"] / total_value * 100) if total_value else 0

            pnl = total_value - invested

            clients_view.append({
                "user": user,
                "total_value": total_value,
                "invested": invested,
                "pnl": pnl,
                "items": enriched
            })

        return render_template("admin_premium.html", clients=clients_view)

    # CLIENT VIEW
    user_rows = [dict(r) for r in rows if r["username"] == session.get("user")]

    symbols = list({r["stock"] for r in user_rows})
    prices = {}
    if symbols:
        data = yf.download(symbols, period="1d", interval="1m", group_by="ticker", progress=False)
        for s in symbols:
            try:
                prices[s] = float(data[s]["Close"].dropna().iloc[-1])
            except:
                prices[s] = None

    items = []
    total_value = 0
    invested = 0

    for it in user_rows:
        live = prices.get(it["stock"])
        value = (live * it["qty"]) if live else 0
        inv = it["price"] * it["qty"]
        pnl = value - inv

        total_value += value
        invested += inv

        items.append({**it, "live": live, "value": value, "pnl": pnl})

    total_pnl = total_value - invested

    return render_template("client_premium.html", items=items, total_value=total_value, invested=invested, total_pnl=total_pnl)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    init_db()
    app.run()