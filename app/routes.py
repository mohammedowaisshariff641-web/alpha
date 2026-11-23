from flask import Blueprint, jsonify, render_template, request, current_app, session
from datetime import date, datetime, timedelta
from .sheets import get_store, SHEET_HEADERS
import os, uuid
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import secrets
import time

bp = Blueprint("main", __name__)

def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Please log in first"}), 401
        return func(*args, **kwargs)
    return wrapper

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Please log in first"}), 401

        if session.get("role") != "Admin":
            return jsonify({"error": "Admin access required"}), 403

        return func(*args, **kwargs)

    return wrapper

@bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Enter username and password"}), 400

    store = get_store()

    sheet_start = time.perf_counter()
    credentials = store.rows("Login_Credentials")
    print("Google Sheets time:", round(time.perf_counter() - sheet_start, 3), "seconds")

    for account in credentials:
        if (
           str(account.get("Username") or "").lower() == username.lower()
           or str(account.get("Email") or "").lower() == username.lower()
        ):
            if account.get("Account_Status") != "Active":
                return jsonify({"error": "Account is inactive"}), 403

            password_hash = account.get("Password_Hash", "")

            hash_start = time.perf_counter()
            password_valid = password_hash and check_password_hash(password_hash, password)
            print("Password verification time:", round(time.perf_counter() - hash_start, 3), "seconds")

            if password_valid:
                session["user_id"] = account.get("User_ID")
                session["role"] = account.get("Role")
                session["username"] = account.get("Username")

                return jsonify({
                    "message": "Login successful",
                    "role": session["role"],
                    "username": session["username"]
                })

            break

    return jsonify({"error": "Invalid username or password"}), 401

@bp.route("/api/admin/users", methods=["POST"])
@admin_required
def create_user():
    data = request.get_json() or {}

    full_name = str(data.get("full_name") or "").strip()
    user_code = str(data.get("user_code") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    role = str(data.get("role") or "").strip()
    department = str(data.get("department") or "").strip()

    if not all([full_name, user_code, email, role, department]):
        return jsonify({"error": "All fields are required"}), 400

    if role not in ("Student", "Staff"):
        return jsonify({"error": "Invalid role"}), 400

    store = get_store()

    users = store.rows("Users")
    credentials = store.rows("Login_Credentials")

    # Check duplicate USN/Staff ID and email
    for user in users:
        if (
            str(user.get("USN_or_Staff_ID") or "").strip().lower()
            == user_code.lower()
            or str(user.get("Email") or "").strip().lower() == email
        ):
            return jsonify({
                "error": "USN/Staff ID or email already exists"
            }), 409

    # Check duplicate login credentials
    for account in credentials:
        if (
            str(account.get("Email") or "").strip().lower() == email
            or str(account.get("Username") or "").strip().lower()
            == full_name.replace(" ", "").lower()
        ):
            return jsonify({
                "error": "Username or email already has login credentials"
            }), 409

    # Generate sequential User ID
    existing_ids = [
        str(user.get("User_ID") or "")
        for user in users
    ]

    test_numbers = []

    for existing_id in existing_ids:
        if existing_id.startswith("USR-TEST-"):
            try:
                number = int(existing_id.split("-")[-1])
                test_numbers.append(number)
            except ValueError:
                continue

    next_number = max(test_numbers, default=0) + 1

    new_user_id = f"USR-TEST-{next_number}"

    # Generate unique Credential ID
    new_credential_id = uid("CRED")

    temporary_password = secrets.token_urlsafe(12)

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Add user to Users sheet
    store.append("Users", {
        "User_ID": new_user_id,
        "Full_Name": full_name,
        "USN_or_Staff_ID": user_code,
        "Email": email,
        "Role": role,
        "Department": department,
        "Account_Status": "Active",
        "Block_Reason": "",
        "Outstanding_Fine": 0
    })

    # Add login credentials
    store.append("Login_Credentials", {
        "Credential_ID": new_credential_id,
        "User_ID": new_user_id,
        "Username": full_name.replace(" ", "").lower(),
        "Email": email,
        "Password_Hash": generate_password_hash(temporary_password),
        "Role": role,
        "Account_Status": "Active",
        "Failed_Login_Attempts": 0,
        "Last_Login": "",
        "Created_At": created_at,
        "Remarks": "Temporary password issued"
    })

    return jsonify({
        "message": "User account created successfully",
        "username": full_name.replace(" ", "").lower(),
        "temporary_password": temporary_password
    }), 201


@bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"})

@bp.route("/api/session")
def check_session():
    if "user_id" not in session:
        return jsonify({"logged_in": False})

    return jsonify({
        "logged_in": True,
        "user_id": session["user_id"],
        "username": session["username"],
        "role": session["role"]
    })

def uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

def clean(row):
    return {k: ("" if v is None else v) for k,v in row.items()}

def as_int(v, default=0):
    try: return int(float(v or 0))
    except (TypeError, ValueError): return default

def active_user(store, user_code):
    return next((u for u in store.rows("Users") if str(u.get("USN_or_Staff_ID","")).lower() == str(user_code).lower()), None)

@bp.get("/")
def home():
    return render_template("index.html")

@bp.get("/api/health")
def health():
    return jsonify({"status":"ok","app":"Borrow Board"})

@bp.get("/api/bootstrap")
@login_required
def bootstrap():
    try:
        store = get_store()

        inventory = [
            clean(item)
            for item in store.rows("Inventory")
        ]

        users = store.rows("Users")

        transactions = [
            clean(transaction)
            for transaction in store.rows("Borrow_Transactions")
        ]

        reservations = [
            clean(reservation)
            for reservation in store.rows("Reservations")
        ]

        today = date.today().isoformat()

        active_transactions = [
            transaction
            for transaction in transactions
            if transaction.get("Transaction_Status") in ("Borrowed", "Overdue")
        ]

        overdue_transactions = [
            transaction
            for transaction in active_transactions
            if str(transaction.get("Due_Date") or "").strip()
            and str(transaction.get("Due_Date")).strip() < today
        ]

        user_list = [
            {
                "Full_Name": user.get("Full_Name", ""),
                "USN_or_Staff_ID": user.get("USN_or_Staff_ID", ""),
                "Role": user.get("Role", "")
            }
            for user in users
        ]

        return jsonify({
            "inventory": inventory,
            "transactions": transactions,
            "reservations": reservations,
            "users": user_list,
            "stats": {
                "items": len(inventory),
                "available": sum(
                    as_int(item.get("Available_Quantity"))
                    for item in inventory
                ),
                "active_loans": len(active_transactions),
                "overdue": len(overdue_transactions)
            }
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()

        return jsonify({
            "error": str(e)
        }), 503


@bp.post("/api/borrow")
def borrow():
    data = request.get_json(force=True)
    required = ["user_code","item_id","purpose","due_date"]
    if any(not str(data.get(k,"")).strip() for k in required):
        return jsonify({"error":"Please complete borrower ID, item, purpose and due date."}), 400
    s = get_store()
    user = active_user(s, data["user_code"])
    if not user: return jsonify({"error":"Borrower ID not found in the Users sheet."}), 404
    if user.get("Account_Status") != "Active": return jsonify({"error":"This account is not active. Contact the lab administrator."}), 403
    if as_int(user.get("Outstanding_Fine")) > 0: return jsonify({"error":"Outstanding fine exists. Please contact the lab administrator."}), 403
    item = next((i for i in s.rows("Inventory") if i.get("Item_ID")==data["item_id"]), None)
    qty = max(1, as_int(data.get("quantity"),1))
    if not item: return jsonify({"error":"Equipment not found."}), 404
    if as_int(item.get("Available_Quantity")) < qty: return jsonify({"error":"Not enough available quantity. You can place a reservation instead."}), 409
    try:
        due = date.fromisoformat(data["due_date"])
        if due < date.today(): raise ValueError()
    except ValueError: return jsonify({"error":"Return date must be today or a future date."}), 400
    txn_id = uid("TXN")
    record = {"Transaction_ID":txn_id,"User_ID":user["User_ID"],"Item_ID":item["Item_ID"],"Quantity":qty,
      "Issue_Date":date.today().isoformat(),"Due_Date":due.isoformat(),"Return_Date":"","Return_Condition":"",
      "Inspection_Notes":"","Issued_By":data.get("issued_by","Lab Admin"),"Received_By":"",
      "Transaction_Status":"Borrowed","Overdue_Flag":"No","Fine_Status":"Not assessed","Fine_Amount":0,
      "Purpose":data["purpose"].strip(),"Request_Reason":data.get("reason","").strip(),"Remarks":""}
    s.append("Borrow_Transactions",record)
    s.update("Inventory","Item_ID",item["Item_ID"],{"Available_Quantity":as_int(item.get("Available_Quantity"))-qty,
      "Borrowed_Quantity":as_int(item.get("Borrowed_Quantity"))+qty})
    return jsonify({"message":"Equipment issued successfully.","transaction_id":txn_id}), 201

@bp.post("/api/return")
def return_item():
    data = request.get_json(force=True)
    if not data.get("transaction_id") or not data.get("condition"):
        return jsonify({"error":"Transaction ID and return condition are required."}), 400
    s = get_store()
    txn = next((t for t in s.rows("Borrow_Transactions") if t.get("Transaction_ID")==data["transaction_id"]),None)
    if not txn or txn.get("Transaction_Status") not in ("Borrowed","Overdue"):
        return jsonify({"error":"Active borrowing record not found."}), 404
    item = next((i for i in s.rows("Inventory") if i.get("Item_ID")==txn.get("Item_ID")),None)
    condition = data["condition"]
    status = "Returned - Inspection Required" if condition in ("Damaged","Not working","Incomplete") else "Returned"
    s.update("Borrow_Transactions","Transaction_ID",txn["Transaction_ID"],{
      "Return_Date":date.today().isoformat(),"Return_Condition":condition,
      "Inspection_Notes":data.get("notes",""),"Received_By":data.get("received_by","Lab Admin"),
      "Transaction_Status":status,"Overdue_Flag":"Yes" if str(txn.get("Due_Date","")) < date.today().isoformat() else "No"})
    if item:
        qty=as_int(txn.get("Quantity"),1)
        updates={"Borrowed_Quantity":max(0,as_int(item.get("Borrowed_Quantity"))-qty)}
        if condition == "Good":
            updates["Available_Quantity"]=as_int(item.get("Available_Quantity"))+qty
        else:
            updates["Condition"]="Needs inspection"
            updates["Item_Status"]="Under inspection"
        s.update("Inventory","Item_ID",item["Item_ID"],updates)
    return jsonify({"message":"Return recorded. " + ("Administrator inspection is required before the item becomes available." if condition!="Good" else "Item quantity restored to available stock.")})

@bp.post("/api/reservations")
def reserve():
    data=request.get_json(force=True)
    if not all(data.get(k) for k in ("user_code","item_id","purpose")):
        return jsonify({"error":"Borrower ID, item and purpose are required."}),400
    s=get_store(); user=active_user(s,data["user_code"])
    if not user: return jsonify({"error":"Borrower ID not found."}),404
    item=next((i for i in s.rows("Inventory") if i.get("Item_ID")==data["item_id"]),None)
    if not item: return jsonify({"error":"Equipment not found."}),404
    rec={"Reservation_ID":uid("RSV"),"User_ID":user["User_ID"],"Item_ID":item["Item_ID"],"Quantity":max(1,as_int(data.get("quantity"),1)),
      "Request_Date":date.today().isoformat(),"Expected_Availability_Date":"","Approved_By":"","Reservation_Status":"Pending",
      "Priority_Number":len(s.rows("Reservations"))+1,"Notification_Status":"Not sent","Purpose":data["purpose"],"Booking_Notes":data.get("notes",""),"Remarks":""}
    s.append("Reservations",rec)
    return jsonify({"message":"Reservation request added to the queue.","reservation_id":rec["Reservation_ID"]}),201

@bp.post("/api/admin/inspect")
def inspect_return():
    if request.headers.get("X-Admin-Key") != os.getenv("ADMIN_API_KEY","change-this-admin-key"):
        return jsonify({"error":"Admin key is incorrect."}),401
    data=request.get_json(force=True); s=get_store()
    item=next((i for i in s.rows("Inventory") if i.get("Item_ID")==data.get("item_id")),None)
    if not item: return jsonify({"error":"Item not found."}),404
    qty=max(1,as_int(data.get("quantity"),1))
    decision=data.get("decision")
    if decision not in ("Functional","Repair","Retire"): return jsonify({"error":"Choose Functional, Repair or Retire."}),400
    updates={"Condition":decision,"Item_Status":"Available" if decision=="Functional" else ("Under repair" if decision=="Repair" else "Retired")}
    if decision=="Functional": updates["Available_Quantity"]=as_int(item.get("Available_Quantity"))+qty
    s.update("Inventory","Item_ID",item["Item_ID"],updates)
    return jsonify({"message":f"Inspection saved: {decision}."})

@bp.post("/api/admin/items")
def add_item():
    if request.headers.get("X-Admin-Key") != os.getenv("ADMIN_API_KEY","change-this-admin-key"):
        return jsonify({"error":"Admin key is incorrect."}),401
    d=request.get_json(force=True)
    if not d.get("item_name") or not d.get("quantity"): return jsonify({"error":"Item name and quantity are required."}),400
    s=get_store(); qty=max(0,as_int(d["quantity"]))
    rec={"Item_ID":uid("ITM"),"Item_Name":d["item_name"],"Category":d.get("category","General"),"Tracking_Method":d.get("tracking_method","Quantity-based"),
      "Total_Quantity":qty,"Available_Quantity":qty,"Borrowed_Quantity":0,"Condition":"Functional","Location":d.get("location","ALPHA Lab"),
      "Specifications":d.get("specifications",""),"Compatibility_Notes":d.get("compatibility",""),"Item_Status":"Available","Last_Verified":date.today().isoformat(),"Remarks":d.get("remarks","")}
    s.append("Inventory",rec)
    return jsonify({"message":"Equipment added.","item_id":rec["Item_ID"]}),201
