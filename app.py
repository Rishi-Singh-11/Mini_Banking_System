from flask import Flask, render_template, request, redirect, session
import database

app = Flask(__name__)
app.secret_key = "supersecret"  # required for sessions

# Initialize DB tables if not exist
with app.app_context():
    db = database.get_db()
    with open("schema.sql", "r") as f:
        db.executescript(f.read())

# ---------------------------
# ROUTES
# ---------------------------

# Home page
@app.route("/")
def home():
    return redirect("/login")

# Register
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        try:
            user_id = database.execute_db(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password),
            )
            database.execute_db(
                "INSERT INTO accounts (user_id, balance) VALUES (?, ?)",
                (user_id, 0),
            )
            return redirect("/login")
        except Exception as e:
            return f"Error: {e}"
    return render_template("register.html")

# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = database.query_db(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password),
            one=True,
        )
        if user:
            session["user_id"] = user["id"]
            return redirect("/dashboard")
        else:
            return "Invalid login"
    return render_template("login.html")

# Dashboard
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    account = database.query_db(
        "SELECT * FROM accounts WHERE user_id=?", (session["user_id"],), one=True
    )
    transactions = database.query_db(
        "SELECT * FROM transactions WHERE from_account=? OR to_account=? ORDER BY timestamp DESC",
        (account["id"], account["id"]),
    )
    return render_template("dashboard.html", balance=account["balance"], transactions=transactions)

# Deposit money
@app.route("/deposit", methods=["POST"])
def deposit():
    if "user_id" not in session:
        return redirect("/login")

    amount = float(request.form["amount"])
    if amount <= 0:
        return "Invalid amount"

    db = database.get_db()
    account = database.query_db(
        "SELECT * FROM accounts WHERE user_id=?", (session["user_id"],), one=True
    )
    try:
        db.execute("BEGIN")  # start transaction
        # Credit user's account
        db.execute(
            "UPDATE accounts SET balance = balance + ? WHERE id=?", 
            (amount, account["id"])
        )
        # Log deposit as a transaction (from_account=None)
        db.execute(
            "INSERT INTO transactions (from_account, to_account, amount) VALUES (?, ?, ?)",
            (None, account["id"], amount),
        )
        db.commit()  # commit changes
        return redirect("/dashboard")
    except Exception as e:
        db.rollback()  # undo changes if something fails
        return f"Deposit failed: {e}"


# Transfer money
@app.route("/transfer", methods=["POST"])
def transfer():
    if "user_id" not in session:
        return redirect("/login")
    from_account = database.query_db(
        "SELECT * FROM accounts WHERE user_id=?", (session["user_id"],), one=True
    )["id"]
    to_username = request.form["to_username"]
    amount = float(request.form["amount"])

    # Get receiver account
    to_user = database.query_db(
        "SELECT * FROM users WHERE username=?", (to_username,), one=True
    )
    if not to_user:
        return "Receiver not found"
    to_account = database.query_db(
        "SELECT * FROM accounts WHERE user_id=?", (to_user["id"],), one=True
    )["id"]

    # Perform transfer with rollback
    db = database.get_db()
    try:
        db.execute("BEGIN")  # start transaction
        # Check balance
        from_balance = database.query_db(
            "SELECT balance FROM accounts WHERE id=?", (from_account,), one=True
        )["balance"]
        if from_balance < amount:
            raise Exception("Insufficient funds")

        # Debit sender
        db.execute("UPDATE accounts SET balance = balance - ? WHERE id=?", (amount, from_account))
        # Credit receiver
        db.execute("UPDATE accounts SET balance = balance + ? WHERE id=?", (amount, to_account))
        # Log transaction
        db.execute(
            "INSERT INTO transactions (from_account, to_account, amount) VALUES (?, ?, ?)",
            (from_account, to_account, amount),
        )
        db.commit()  # commit changes
        return redirect("/dashboard")
    except Exception as e:
        db.rollback()  # undo changes if anything fails
        return f"Transaction failed: {e}"

# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# Run app
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
