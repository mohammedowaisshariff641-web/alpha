
from flask import Blueprint, jsonify, render_template, request, session
from datetime import date, datetime
from .sheets import get_store
import uuid
import secrets
import time

from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps


bp = Blueprint("main", __name__)


# =========================================================
# AUTHENTICATION AND ROLE PERMISSIONS
# =========================================================

def normalize(value):
    return str(value or "").strip().lower()


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Please log in first."}), 401
        return func(*args, **kwargs)
    return wrapper


def role_required(*allowed_roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return jsonify({"error": "Please log in first."}), 401

            role = normalize(session.get("role"))
            permitted_roles = [normalize(r) for r in allowed_roles]

            if role not in permitted_roles:
                return jsonify({
                    "error": "You do not have permission to perform this action."
                }), 403

            return func(*args, **kwargs)
        return wrapper
    return decorator


admin_required = role_required("admin")
staff_required = role_required("admin", "staff")
logged_in_required = role_required("admin", "staff", "student")


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def clean(row):
    return {
        key: ("" if value is None else value)
        for key, value in row.items()
    }


def as_int(value, default=0):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return default


def active_user(store, user_code):
    wanted = normalize(user_code)

    for user in store.rows("Users"):
        if normalize(user.get("USN_or_Staff_ID")) == wanted:
            return user

    return None


def find_inventory_item(store, item_id):
    wanted = normalize(item_id)

    for item in store.rows("Inventory"):
        if normalize(item.get("Item_ID")) == wanted:
            return item

    return None


def current_user_code():
    return normalize(session.get("user_id"))


def belongs_to_current_user(record):
    return normalize(record.get("User_ID")) == current_user_code()


# =========================================================
# LOGIN
# =========================================================

@bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}

    username = str(data.get("username", "")).strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Enter username and password."}), 400

    store = get_store()
    sheet_start = time.perf_counter()
    credentials = store.rows("Login_Credentials")

    print(
        "Google Sheets time:",
        round(time.perf_counter() - sheet_start, 3),
        "seconds"
    )

    for account in credentials:
        account_username = normalize(account.get("Username"))
        account_email = normalize(account.get("Email"))

        if (
            account_username == normalize(username)
            or account_email == normalize(username)
        ):
            if normalize(account.get("Account_Status")) != "active":
                return jsonify({"error": "Account is inactive."}), 403

            password_hash = account.get("Password_Hash", "")

            if not password_hash:
                return jsonify({
                    "error": "Password is not configured for this account."
                }), 401

            hash_start = time.perf_counter()

            try:
                password_valid = check_password_hash(password_hash, password)
            except Exception:
                password_valid = False

            print(
                "Password verification time:",
                round(time.perf_counter() - hash_start, 3),
                "seconds"
            )

            if password_valid:
                session.clear()

                session["user_id"] = account.get("User_ID")
                session["role"] = account.get("Role")
                session["username"] = account.get("Username")

                return jsonify({
                    "message": "Login successful",
                    "user_id": session["user_id"],
                    "role": session["role"],
                    "username": session["username"]
                })

            break

    return jsonify({"error": "Invalid username or password."}), 401


# =========================================================
# LOGOUT
# =========================================================

@bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully."})


# =========================================================
# SESSION
# =========================================================

@bp.route("/api/session")
def check_session():
    if "user_id" not in session:
        return jsonify({"logged_in": False})

    return jsonify({
        "logged_in": True,
        "user_id": session.get("user_id"),
        "username": session.get("username"),
        "role": session.get("role")
    })


# =========================================================
# HOME
# =========================================================

@bp.get("/")
def home():
    return render_template("index.html")


# =========================================================
# HEALTH CHECK
# =========================================================

@bp.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "app": "Borrow Board"
    })


# =========================================================
# BOOTSTRAP DATA
# =========================================================

@bp.get("/api/bootstrap")
@login_required
def bootstrap():
    try:
        store = get_store()
        role = normalize(session.get("role"))

        inventory = [
            clean(item)
            for item in store.rows("Inventory")
        ]

        all_transactions = [
            clean(transaction)
            for transaction in store.rows("Borrow_Transactions")
        ]

        all_reservations = [
            clean(reservation)
            for reservation in store.rows("Reservations")
        ]

        all_users = store.rows("Users")

        # Students can only see their own records.
        if role == "student":
            transactions = [
                record for record in all_transactions
                if belongs_to_current_user(record)
            ]

            reservations = [
                record for record in all_reservations
                if belongs_to_current_user(record)
            ]
        else:
            transactions = all_transactions
            reservations = all_reservations

        today = date.today().isoformat()

        active_transactions = [
            transaction for transaction in transactions
            if normalize(transaction.get("Transaction_Status"))
            in ("borrowed", "overdue")
        ]

        overdue_transactions = [
            transaction for transaction in active_transactions
            if str(transaction.get("Due_Date", "")).strip()
            and str(transaction.get("Due_Date")) < today
        ]

        visible_users = []

        # Admin and Staff can see borrower details.
        # Only Admin can access user-management actions.
        if role in ("admin", "staff"):
            visible_users = [
                {
                    "Full_Name": user.get("Full_Name"),
                    "USN_or_Staff_ID": user.get("USN_or_Staff_ID"),
                    "Email": user.get("Email", ""),
                    "Role": user.get("Role"),
                    "Account_Status": user.get("Account_Status", "Active")
                }
                for user in all_users
            ]

        return jsonify({
            "inventory": inventory,
            "transactions": transactions,
            "reservations": reservations,
            "users": visible_users,

            "current_user": {
                "user_id": session.get("user_id"),
                "username": session.get("username"),
                "role": session.get("role")
            },

            "stats": {
                "items": len(inventory),
                "available": sum(
                    as_int(item.get("Available_Quantity"))
                    for item in inventory
                ),
                "active_loans": len(active_transactions),
                "overdue": len(overdue_transactions)
            }
        })

    except Exception as error:
        print("BOOTSTRAP ERROR:", repr(error))
        return jsonify({"error": str(error)}), 503


# =========================================================
# CREATE USER - ADMIN ONLY
# =========================================================

@bp.post("/api/admin/users")
@admin_required
def create_user():
    data = request.get_json() or {}

    full_name = str(data.get("full_name") or "").strip()
    user_code = str(data.get("user_code") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    role = str(data.get("role") or "").strip()
    department = str(data.get("department") or "").strip()

    if not all([full_name, user_code, email, role, department]):
        return jsonify({"error": "All fields are required."}), 400

    if role not in ("Student", "Staff"):
        return jsonify({"error": "Invalid role."}), 400

    store = get_store()
    users = store.rows("Users")
    credentials = store.rows("Login_Credentials")

    username = "".join(full_name.split()).lower()

    for user in users:
        if (
            normalize(user.get("USN_or_Staff_ID")) == normalize(user_code)
            or normalize(user.get("Email")) == email
        ):
            return jsonify({
                "error": "USN/Staff ID or email already exists."
            }), 409

    for account in credentials:
        if (
            normalize(account.get("Email")) == email
            or normalize(account.get("Username")) == username
        ):
            return jsonify({
                "error": "Username or email already exists."
            }), 409

    new_user_id = user_code
    new_credential_id = uid("CRED")
    temporary_password = secrets.token_urlsafe(12)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

    store.append("Login_Credentials", {
        "Credential_ID": new_credential_id,
        "User_ID": new_user_id,
        "Username": username,
        "Email": email,
        "Password_Hash": generate_password_hash(temporary_password),
        "Role": role,
        "Account_Status": "Active",
        "Failed_Login_Attempts": 0,
        "Last_Login": "",
        "Created_At": created_at,
        "Remarks": "Temporary password issued",
        "Must_Change_Password": "TRUE"
    })

    return jsonify({
        "message": "User account created successfully.",
        "username": username,
        "temporary_password": temporary_password
    }), 201


# =========================================================
# BORROW EQUIPMENT - ADMIN AND STAFF ONLY
# =========================================================

@bp.post("/api/borrow")
@staff_required
def borrow():
    try:
        data = request.get_json(silent=True) or {}

        user_code = str(data.get("user_code") or "").strip()
        item_id = str(data.get("item_id") or "").strip()
        purpose = str(data.get("purpose") or "").strip()
        due_date = str(data.get("due_date") or "").strip()
        quantity = as_int(data.get("quantity"), 1)

        if not user_code:
            return jsonify({"error": "Please select a borrower."}), 400

        if not item_id:
            return jsonify({"error": "Please select equipment."}), 400

        if not purpose:
            return jsonify({"error": "Please enter the purpose."}), 400

        if not due_date:
            return jsonify({"error": "Please select the return date."}), 400

        if quantity < 1:
            return jsonify({"error": "Quantity must be at least 1."}), 400

        store = get_store()
        user = active_user(store, user_code)

        if not user:
            return jsonify({
                "error": "Borrower not found. Please select a valid borrower."
            }), 404

        if normalize(user.get("Account_Status")) != "active":
            return jsonify({
                "error": "This account is not active. Contact the lab administrator."
            }), 403

        if as_int(user.get("Outstanding_Fine")) > 0:
            return jsonify({
                "error": "Outstanding fine exists. Please contact the lab administrator."
            }), 403

        item = find_inventory_item(store, item_id)

        if not item:
            return jsonify({
                "error": "Equipment not found. Please select a valid equipment item."
            }), 404

        available_quantity = as_int(item.get("Available_Quantity"))

        if available_quantity < quantity:
            return jsonify({
                "error": f"Only {available_quantity} unit(s) of this equipment are currently available."
            }), 409

        try:
            due = date.fromisoformat(due_date)
        except ValueError:
            return jsonify({"error": "Invalid return date."}), 400

        if due < date.today():
            return jsonify({
                "error": "Return date cannot be before today."
            }), 400

        transaction_id = uid("TXN")

        transaction = {
            "Transaction_ID": transaction_id,
            "User_ID": user.get("User_ID") or user.get("USN_or_Staff_ID"),
            "Item_ID": item.get("Item_ID"),
            "Quantity": quantity,
            "Issue_Date": date.today().isoformat(),
            "Due_Date": due.isoformat(),
            "Return_Date": "",
            "Return_Condition": "",
            "Inspection_Notes": "",
            "Issued_By": session.get("username", "Lab Staff"),
            "Received_By": "",
            "Transaction_Status": "Borrowed",
            "Overdue_Flag": "No",
            "Fine_Status": "Not assessed",
            "Fine_Amount": 0,
            "Purpose": purpose,
            "Request_Reason": str(data.get("reason", "")).strip(),
            "Remarks": ""
        }

        store.append("Borrow_Transactions", transaction)

        new_available_quantity = available_quantity - quantity
        new_borrowed_quantity = (
            as_int(item.get("Borrowed_Quantity")) + quantity
        )

        store.update(
            "Inventory",
            "Item_ID",
            item.get("Item_ID"),
            {
                "Available_Quantity": new_available_quantity,
                "Borrowed_Quantity": new_borrowed_quantity,
                "Item_Status": (
                    "Available" if new_available_quantity > 0 else "Borrowed"
                )
            }
        )

        return jsonify({
            "message": "Equipment issued successfully.",
            "transaction_id": transaction_id,
            "user": user.get("Full_Name", user_code),
            "item": item.get("Item_Name", item_id),
            "quantity": quantity,
            "due_date": due.isoformat()
        }), 201

    except Exception as error:
        print("BORROW ERROR:", repr(error))
        return jsonify({
            "error": "Borrowing failed: " + str(error)
        }), 500


# =========================================================
# RETURN EQUIPMENT - ADMIN AND STAFF ONLY
# =========================================================

@bp.post("/api/return")
@staff_required
def return_item():
    try:
        data = request.get_json(silent=True) or {}

        transaction_id = str(data.get("transaction_id") or "").strip()
        condition = str(data.get("condition") or "").strip()

        if not transaction_id:
            return jsonify({
                "error": "Please select a borrowing transaction."
            }), 400

        if not condition:
            return jsonify({
                "error": "Please select the return condition."
            }), 400

        store = get_store()
        transaction = None
        wanted_transaction = normalize(transaction_id)

        for record in store.rows("Borrow_Transactions"):
            if normalize(record.get("Transaction_ID")) == wanted_transaction:
                transaction = record
                break

        if not transaction:
            return jsonify({
                "error": "Borrowing transaction not found."
            }), 404

        transaction_status = normalize(
            transaction.get("Transaction_Status")
        )

        if transaction_status not in ("borrowed", "overdue"):
            return jsonify({
                "error": "This equipment has already been returned."
            }), 409

        item = find_inventory_item(store, transaction.get("Item_ID"))

        return_status = (
            "Returned - Inspection Required"
            if condition in ("Damaged", "Not working", "Incomplete")
            else "Returned"
        )

        due_date = str(transaction.get("Due_Date", ""))
        overdue_flag = (
            "Yes"
            if due_date and due_date < date.today().isoformat()
            else "No"
        )

        store.update(
            "Borrow_Transactions",
            "Transaction_ID",
            transaction.get("Transaction_ID"),
            {
                "Return_Date": date.today().isoformat(),
                "Return_Condition": condition,
                "Inspection_Notes": str(data.get("notes", "")).strip(),
                "Received_By": str(
                    data.get("received_by")
                    or session.get("username", "Lab Staff")
                ).strip(),
                "Transaction_Status": return_status,
                "Overdue_Flag": overdue_flag
            }
        )

        if item:
            quantity = max(1, as_int(transaction.get("Quantity")))
            current_borrowed = as_int(item.get("Borrowed_Quantity"))

            updates = {
                "Borrowed_Quantity": max(0, current_borrowed - quantity)
            }

            if condition == "Good":
                new_available = (
                    as_int(item.get("Available_Quantity")) + quantity
                )

                updates["Available_Quantity"] = new_available
                updates["Condition"] = "Functional"
                updates["Item_Status"] = "Available"
            else:
                updates["Condition"] = "Needs inspection"
                updates["Item_Status"] = "Under inspection"

            store.update(
                "Inventory",
                "Item_ID",
                item.get("Item_ID"),
                updates
            )

        return jsonify({
            "message": (
                "Return recorded successfully."
                if condition == "Good"
                else "Return recorded. Administrator inspection is required."
            )
        })

    except Exception as error:
        print("RETURN ERROR:", repr(error))
        return jsonify({
            "error": "Return failed: " + str(error)
        }), 500


# =========================================================
# RESERVATIONS - ALL ROLES
# =========================================================

@bp.post("/api/reservations")
@logged_in_required
def reserve():
    try:
        data = request.get_json(silent=True) or {}

        user_code = str(data.get("user_code") or "").strip()
        item_id = str(data.get("item_id") or "").strip()
        purpose = str(data.get("purpose") or "").strip()
        quantity = as_int(data.get("quantity"), 1)

        if not item_id:
            return jsonify({"error": "Please select equipment."}), 400

        if not purpose:
            return jsonify({"error": "Please enter the purpose."}), 400

        if quantity < 1:
            return jsonify({
                "error": "Quantity must be at least 1."
            }), 400

        store = get_store()
        role = normalize(session.get("role"))

        # Students can reserve only for themselves.
        if role == "student":
            user_code = current_user_code()

        if not user_code:
            return jsonify({
                "error": "Please select a borrower."
            }), 400

        user = None
        wanted_user = normalize(user_code)

        for record in store.rows("Users"):
            usn = normalize(record.get("USN_or_Staff_ID"))
            user_id = normalize(record.get("User_ID"))

            if wanted_user == usn or wanted_user == user_id:
                user = record
                break

        if not user:
            return jsonify({
                "error": "Borrower not found. Please select a valid borrower."
            }), 404

        if normalize(user.get("Account_Status", "Active")) != "active":
            return jsonify({
                "error": "This account is not active. Contact the lab administrator."
            }), 403

        item = find_inventory_item(store, item_id)

        if not item:
            return jsonify({
                "error": "Equipment not found. Please select a valid equipment item."
            }), 404

        existing_reservations = store.rows("Reservations")

        reservation = {
            "Reservation_ID": uid("RSV"),
            "User_ID": user.get("User_ID") or user.get("USN_or_Staff_ID"),
            "Item_ID": item.get("Item_ID"),
            "Quantity": quantity,
            "Request_Date": date.today().isoformat(),
            "Expected_Availability_Date": "",
            "Approved_By": "",
            "Reservation_Status": "Pending",
            "Priority_Number": len(existing_reservations) + 1,
            "Notification_Status": "Not sent",
            "Purpose": purpose,
            "Booking_Notes": str(data.get("notes", "")).strip(),
            "Remarks": ""
        }

        store.append("Reservations", reservation)

        return jsonify({
            "message": "Reservation request added to the queue.",
            "reservation_id": reservation["Reservation_ID"]
        }), 201

    except Exception as error:
        print("RESERVATION ERROR:", repr(error))
        return jsonify({
            "error": "Reservation failed: " + str(error)
        }), 500


# =========================================================
# ADMIN - INSPECT RETURN
# =========================================================

@bp.post("/api/admin/inspect")
@admin_required
def inspect_return():
    try:
        data = request.get_json(silent=True) or {}
        store = get_store()

        item = find_inventory_item(store, data.get("item_id"))

        if not item:
            return jsonify({"error": "Item not found."}), 404

        quantity = max(1, as_int(data.get("quantity"), 1))
        decision = str(data.get("decision") or "").strip()

        if decision not in ("Functional", "Repair", "Retire"):
            return jsonify({
                "error": "Choose Functional, Repair or Retire."
            }), 400

        updates = {
            "Condition": decision,
            "Item_Status": (
                "Available" if decision == "Functional"
                else "Under repair" if decision == "Repair"
                else "Retired"
            )
        }

        if decision == "Functional":
            updates["Available_Quantity"] = (
                as_int(item.get("Available_Quantity")) + quantity
            )

        store.update(
            "Inventory",
            "Item_ID",
            item.get("Item_ID"),
            updates
        )

        return jsonify({
            "message": f"Inspection saved: {decision}."
        })

    except Exception as error:
        print("INSPECTION ERROR:", repr(error))
        return jsonify({
            "error": "Inspection failed: " + str(error)
        }), 500


# =========================================================
# ADMIN - ADD ITEM
# =========================================================

@bp.post("/api/admin/items")
@admin_required
def add_item():
    try:
        data = request.get_json(silent=True) or {}

        item_name = str(data.get("item_name") or "").strip()
        quantity = as_int(data.get("quantity"))

        if not item_name:
            return jsonify({
                "error": "Item name is required."
            }), 400

        if quantity < 1:
            return jsonify({
                "error": "Quantity must be at least 1."
            }), 400

        store = get_store()
        item_id = uid("ITM")

        record = {
            "Item_ID": item_id,
            "Item_Name": item_name,
            "Category": str(data.get("category", "General")).strip(),
            "Tracking_Method": str(
                data.get("tracking_method", "Quantity-based")
            ).strip(),
            "Total_Quantity": quantity,
            "Available_Quantity": quantity,
            "Borrowed_Quantity": 0,
            "Condition": "Functional",
            "Location": str(data.get("location", "ALPHA Lab")).strip(),
            "Specifications": str(
                data.get("specifications", "")
            ).strip(),
            "Compatibility_Notes": str(
                data.get("compatibility", "")
            ).strip(),
            "Item_Status": "Available",
            "Last_Verified": date.today().isoformat(),
            "Remarks": str(data.get("remarks", "")).strip()
        }

        store.append("Inventory", record)

        return jsonify({
            "message": "Equipment added.",
            "item_id": item_id
        }), 201

    except Exception as error:
        print("ADD ITEM ERROR:", repr(error))
        return jsonify({
            "error": "Could not add equipment: " + str(error)
        }), 500
