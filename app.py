import sqlite3
from datetime import datetime, date
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

BASE=Path(__file__).resolve().parent
DB=BASE/"food_waste.db"
app=Flask(__name__)
app.secret_key="freshtrack-training-secret"

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    c=db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS food_items(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,name TEXT NOT NULL,category TEXT NOT NULL,quantity REAL NOT NULL,unit TEXT NOT NULL,expiry_date TEXT NOT NULL,price REAL DEFAULT 0,status TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'Available',created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,item_id INTEGER,action TEXT NOT NULL,quantity REAL DEFAULT 0,price REAL DEFAULT 0,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS shopping(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,item TEXT NOT NULL,quantity TEXT,checked INTEGER DEFAULT 0,created_at TEXT NOT NULL);
    """); c.commit(); c.close()

def status_for(d):
    days=(datetime.strptime(d,"%Y-%m-%d").date()-date.today()).days
    return ("Expired",days) if days<0 else ("Use Soon",days) if days<=2 else ("Expiring Soon",days) if days<=7 else ("Fresh",days)

def login_required(f):
    @wraps(f)
    def w(*a,**k):
        if "user_id" not in session: return redirect(url_for("login"))
        return f(*a,**k)
    return w

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=request.form["name"].strip(); email=request.form["email"].strip().lower(); pw=request.form["password"]
        if len(pw)<6: flash("Password must be at least 6 characters.","error"); return redirect(url_for("register"))
        c=db()
        try:
            c.execute("INSERT INTO users(name,email,password,created_at) VALUES(?,?,?,?)",(name,email,generate_password_hash(pw),datetime.now().isoformat(timespec="seconds"))); c.commit()
            flash("Account created. Please log in.","success"); return redirect(url_for("login"))
        except sqlite3.IntegrityError: flash("An account with this email already exists.","error")
        finally: c.close()
    return render_template("auth.html",mode="register")

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form["email"].strip().lower(); pw=request.form["password"]; c=db()
        u=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone(); c.close()
        if u and check_password_hash(u["password"],pw):
            session["user_id"]=u["id"]; session["name"]=u["name"]; return redirect(url_for("dashboard"))
        flash("Invalid email or password.","error")
    return render_template("auth.html",mode="login")

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    uid=session["user_id"]; c=db()
    items=c.execute("SELECT * FROM food_items WHERE user_id=? AND state='Available' ORDER BY expiry_date",(uid,)).fetchall()
    q=lambda sql: c.execute(sql,(uid,)).fetchone()["n"]
    counts={"total":q("SELECT COUNT(*) n FROM food_items WHERE user_id=?"),
            "available":q("SELECT COUNT(*) n FROM food_items WHERE user_id=? AND state='Available'"),
            "priority":q("SELECT COUNT(*) n FROM food_items WHERE user_id=? AND state='Available' AND status IN ('Use Soon','Expiring Soon')"),
            "expired":q("SELECT COUNT(*) n FROM food_items WHERE user_id=? AND status='Expired' AND state='Available'"),
            "wasted":c.execute("SELECT COALESCE(SUM(price),0) n FROM activity WHERE user_id=? AND action='Wasted'",(uid,)).fetchone()["n"],
            "donated":c.execute("SELECT COALESCE(SUM(price),0) n FROM activity WHERE user_id=? AND action='Donated'",(uid,)).fetchone()["n"],
            "consumed":c.execute("SELECT COALESCE(SUM(price),0) n FROM activity WHERE user_id=? AND action='Consumed'",(uid,)).fetchone()["n"]}
    recent=c.execute("SELECT * FROM activity WHERE user_id=? ORDER BY created_at DESC LIMIT 6",(uid,)).fetchall(); c.close()
    return render_template("dashboard.html",items=items,counts=counts,recent=recent,name=session["name"])

@app.route("/add",methods=["POST"])
@login_required
def add():
    f=request.form
    try:
        qty=float(f["quantity"]); price=float(f.get("price") or 0); status,_=status_for(f["expiry_date"])
        if qty<=0 or price<0: raise ValueError
    except: flash("Please enter valid quantity, price and expiry date.","error"); return redirect(url_for("dashboard"))
    c=db(); c.execute("""INSERT INTO food_items(user_id,name,category,quantity,unit,expiry_date,price,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
      (session["user_id"],f["name"].strip(),f["category"],qty,f["unit"],f["expiry_date"],price,status,datetime.now().isoformat(timespec="seconds"))); c.commit(); c.close()
    flash("Food added to your pantry.","success"); return redirect(url_for("dashboard"))

@app.route("/action/<int:item_id>/<action>",methods=["POST"])
@login_required
def action(item_id,action):
    if action not in ("Consumed","Donated","Wasted"): return redirect(url_for("dashboard"))
    c=db(); item=c.execute("SELECT * FROM food_items WHERE id=? AND user_id=? AND state='Available'",(item_id,session["user_id"])).fetchone()
    if item:
        c.execute("UPDATE food_items SET state=? WHERE id=?",(action,item_id))
        c.execute("INSERT INTO activity(user_id,item_id,action,quantity,price,created_at) VALUES(?,?,?,?,?,?)",(session["user_id"],item_id,action,item["quantity"],item["price"],datetime.now().isoformat(timespec="seconds"))); c.commit()
    c.close(); return redirect(url_for("inventory"))

@app.route("/inventory")
@login_required
def inventory():
    c=db(); items=c.execute("SELECT * FROM food_items WHERE user_id=? ORDER BY expiry_date",(session["user_id"],)).fetchall(); c.close()
    return render_template("inventory.html",items=items)

@app.route("/refresh")
@login_required
def refresh():
    c=db(); rows=c.execute("SELECT id,expiry_date FROM food_items WHERE user_id=? AND state='Available'",(session["user_id"],)).fetchall()
    for r in rows: c.execute("UPDATE food_items SET status=? WHERE id=?",(status_for(r["expiry_date"])[0],r["id"]))
    c.commit(); c.close(); return redirect(request.referrer or url_for("dashboard"))

@app.route("/analytics")
@login_required
def analytics():
    c=db(); activity=c.execute("SELECT action,COUNT(*) n,COALESCE(SUM(price),0) value FROM activity WHERE user_id=? GROUP BY action",(session["user_id"],)).fetchall()
    categories=c.execute("SELECT category,COUNT(*) n,COALESCE(SUM(price),0) value FROM food_items WHERE user_id=? GROUP BY category ORDER BY value DESC",(session["user_id"],)).fetchall(); c.close()
    return render_template("analytics.html",activity=activity,categories=categories)

@app.route("/recipes")
@login_required
def recipes():
    c=db(); names=[r["name"].lower() for r in c.execute("SELECT name FROM food_items WHERE user_id=? AND state='Available'",(session["user_id"],)).fetchall()]; c.close()
    recipes=[("Quick Tomato Pasta",["tomato","pasta","onion"],"Use tomatoes, onion and pasta with basic seasoning.","🍝"),("Veggie Fried Rice",["rice","carrot","peas","onion"],"Combine cooked rice with vegetables and a quick stir-fry.","🍚"),("Potato Sandwich",["potato","bread","onion"],"Mash cooked potato with onion and spices; toast with bread.","🥪"),("Fruit Bowl",["apple","banana","orange"],"Combine available fruits for a simple snack.","🍎")]
    scored=sorted([(sum(any(k in n for n in names) for k in keys),title,desc,icon) for title,keys,desc,icon in recipes],reverse=True)
    return render_template("recipes.html",recipes=[x for x in scored if x[0]>0])

@app.route("/shopping",methods=["GET","POST"])
@login_required
def shopping():
    c=db()
    if request.method=="POST":
        c.execute("INSERT INTO shopping(user_id,item,quantity,created_at) VALUES(?,?,?,?)",(session["user_id"],request.form["item"],request.form.get("quantity",""),datetime.now().isoformat(timespec="seconds"))); c.commit()
    items=c.execute("SELECT * FROM shopping WHERE user_id=? ORDER BY checked,id DESC",(session["user_id"],)).fetchall(); c.close()
    return render_template("shopping.html",items=items)

@app.route("/shopping/<int:item_id>/toggle",methods=["POST"])
@login_required
def toggle_shopping(item_id):
    c=db(); c.execute("UPDATE shopping SET checked=1-checked WHERE id=? AND user_id=?",(item_id,session["user_id"])); c.commit(); c.close(); return redirect(url_for("shopping"))

@app.route("/shopping/<int:item_id>/delete",methods=["POST"])
@login_required
def delete_shopping(item_id):
    c=db(); c.execute("DELETE FROM shopping WHERE id=? AND user_id=?",(item_id,session["user_id"])); c.commit(); c.close(); return redirect(url_for("shopping"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
