import os
import json
import secrets
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, request, session
from flask_cors import CORS

import mysql.connector
from mysql.connector import Error

from dotenv import load_dotenv

import cloudinary
import cloudinary.uploader

import razorpay


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# ENVIRONMENT SETTINGS
# ============================================================

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "sarika-secret-key-2024"
)

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

app.secret_key = SECRET_KEY


# ============================================================
# SESSION CONFIGURATION
# ============================================================

app.config.update(
    SESSION_COOKIE_NAME="sarika_admin_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_PATH="/",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
    SESSION_COOKIE_DOMAIN=None,
)


# ============================================================
# CORS
# ============================================================

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://10.101.222.75:5173",
    "http://10.101.222.75:5174",
    "https://sarika-fashions-frontend.vercel.app",
]

FRONTEND_URL = os.getenv("FRONTEND_URL", "").strip().rstrip("/")

if FRONTEND_URL and FRONTEND_URL not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(FRONTEND_URL)

CORS(
    app,
    supports_credentials=True,
    origins=ALLOWED_ORIGINS,
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Customer-Order-Token",
    ],
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
)


# ============================================================
# CLOUDINARY
# ============================================================

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)


# ============================================================
# RAZORPAY
# ============================================================

razorpay_client = None

if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    razorpay_client = razorpay.Client(
        auth=(
            RAZORPAY_KEY_ID,
            RAZORPAY_KEY_SECRET,
        )
    )

    print(f"✅ Razorpay Loaded: {RAZORPAY_KEY_ID}")
else:
    print("❌ Razorpay keys missing")


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "sarika_db")


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )


# ============================================================
# ADMIN AUTH MIDDLEWARE
# ============================================================

def admin_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

        logged_in = session.get("admin_logged_in", False)
        admin_email = session.get("admin_email")

        if not logged_in:
            print("❌ ADMIN AUTH FAILED")

            return jsonify({
                "success": False,
                "message": "Admin login required",
                "logged_in": False,
            }), 401

        print("✅ ADMIN AUTH PASSED:", admin_email)

        return f(*args, **kwargs)

    return decorated_function


# ============================================================
# CUSTOMER ORDER TOKEN
# ============================================================

def get_customer_order_token():

    token = session.get("customer_order_token")

    if token:
        return str(token).strip()

    authorization = request.headers.get(
        "Authorization",
        ""
    ).strip()

    if authorization.lower().startswith("bearer "):

        bearer_token = authorization[7:].strip()

        if bearer_token:
            session["customer_order_token"] = bearer_token
            session.permanent = True
            return bearer_token

    header_token = request.headers.get(
        "X-Customer-Order-Token",
        ""
    ).strip()

    if header_token:

        session["customer_order_token"] = header_token
        session.permanent = True

        return header_token

    query_token = request.args.get(
        "customer_order_token",
        ""
    ).strip()

    if query_token:

        session["customer_order_token"] = query_token
        session.permanent = True

        return query_token

    try:

        if request.method in ("POST", "PUT", "PATCH"):

            data = request.get_json(silent=True) or {}

            body_token = str(
                data.get(
                    "customer_order_token",
                    ""
                )
            ).strip()

            if body_token:

                session["customer_order_token"] = body_token
                session.permanent = True

                return body_token

            form_token = str(
                request.form.get(
                    "customer_order_token",
                    ""
                )
            ).strip()

            if form_token:

                session["customer_order_token"] = form_token
                session.permanent = True

                return form_token

    except Exception:
        pass

    return None


def create_customer_order_token():

    token = secrets.token_urlsafe(48)

    session["customer_order_token"] = token
    session.permanent = True

    return token


# ============================================================
# HELPER - SAFE JSON
# ============================================================

def parse_order_items(items):

    if isinstance(items, str):

        try:
            items = json.loads(items)

        except Exception:
            return []

    if not isinstance(items, list):
        return []

    return items


# ============================================================
# HELPER - PRODUCT ID NORMALIZATION
# ============================================================

def normalize_product_id(value):

    if value is None:
        return None

    try:
        return int(value)

    except (ValueError, TypeError):
        return str(value).strip()


# ============================================================
# HELPER - GET PRODUCT ID FROM ORDER ITEM
# ============================================================

def get_item_product_id(item):

    if not isinstance(item, dict):
        return None

    possible_ids = [
        item.get("product_id"),
        item.get("productId"),
        item.get("id"),
    ]

    product = item.get("product")

    if isinstance(product, dict):

        possible_ids.extend([
            product.get("id"),
            product.get("product_id"),
            product.get("productId"),
        ])

    for value in possible_ids:

        if value is not None and str(value).strip() != "":
            return value

    return None


# ============================================================
# HELPER - GET PRODUCT NAME FROM ORDER ITEM
# ============================================================

def get_item_product_name(item):

    if not isinstance(item, dict):
        return ""

    possible_names = [
        item.get("product_name"),
        item.get("productName"),
        item.get("name"),
        item.get("title"),
    ]

    product = item.get("product")

    if isinstance(product, dict):

        possible_names.extend([
            product.get("name"),
            product.get("title"),
            product.get("product_name"),
        ])

    for value in possible_names:

        if value is not None and str(value).strip():
            return str(value).strip()

    return ""


# ============================================================
# HELPER - GET ITEM QUANTITY
# ============================================================

def get_item_quantity(item):

    if not isinstance(item, dict):
        return 1

    value = (
        item.get("quantity")
        if item.get("quantity") is not None
        else item.get("qty", 1)
    )

    try:

        quantity = int(value)

        if quantity < 1:
            return 1

        return quantity

    except (ValueError, TypeError):

        return 1


# ============================================================
# CREATE / MIGRATE TABLES
# ============================================================

def create_tables():

    conn = None
    cur = None

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        # ====================================================
        # ADMINS
        # ====================================================

        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) UNIQUE,
                password VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ====================================================
        # ORDERS
        # ====================================================

        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                order_number VARCHAR(50) UNIQUE,
                customer_name VARCHAR(150) NOT NULL,
                customer_email VARCHAR(150),
                customer_phone VARCHAR(30) NOT NULL,
                address TEXT,
                address_line VARCHAR(255) NULL,
                city VARCHAR(100) NOT NULL,
                state VARCHAR(100) NOT NULL,
                pincode VARCHAR(20) NOT NULL,
                items JSON NOT NULL,
                subtotal DECIMAL(10,2) NULL,
                shipping DECIMAL(10,2) NULL,
                total_amount DECIMAL(10,2) NOT NULL,
                razorpay_order_id VARCHAR(100),
                razorpay_payment_id VARCHAR(100),
                payment_status VARCHAR(30) DEFAULT 'Pending',
                order_status VARCHAR(30) DEFAULT 'Placed',
                customer_access_token VARCHAR(255),
                customer_received TINYINT(1) NOT NULL DEFAULT 0,
                received_at DATETIME NULL,
                confirmed_at DATETIME NULL,
                shipped_at DATETIME NULL,
                out_for_delivery_at DATETIME NULL,
                delivered_at DATETIME NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ====================================================
        # ORDER MIGRATIONS
        # ====================================================

        migrations = [

            ("subtotal", "DECIMAL(10,2) NULL"),

            ("shipping", "DECIMAL(10,2) NULL"),

            ("address_line", "VARCHAR(255) NULL"),

            ("customer_access_token", "VARCHAR(255) NULL"),

            (
                "customer_received",
                "TINYINT(1) NOT NULL DEFAULT 0"
            ),

            ("received_at", "DATETIME NULL"),

            ("confirmed_at", "DATETIME NULL"),

            ("shipped_at", "DATETIME NULL"),

            ("out_for_delivery_at", "DATETIME NULL"),

            ("delivered_at", "DATETIME NULL"),
        ]

        for col_name, col_def in migrations:

            cur.execute(
                f"SHOW COLUMNS FROM orders LIKE '{col_name}'"
            )

            if not cur.fetchone():

                try:

                    cur.execute(
                        f"""
                        ALTER TABLE orders
                        ADD COLUMN {col_name} {col_def}
                        """
                    )

                    print(
                        f"✅ Column {col_name} added to orders"
                    )

                except Exception as alter_err:

                    print(
                        f"Note on {col_name}:",
                        alter_err
                    )

        # ====================================================
        # REVIEWS
        # ====================================================

        cur.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INT AUTO_INCREMENT PRIMARY KEY,
                product_id INT NOT NULL,
                customer_name VARCHAR(100) NOT NULL,
                rating INT NOT NULL,
                review_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ====================================================
        # RETURN REQUESTS
        # ====================================================

        cur.execute("""
            CREATE TABLE IF NOT EXISTS return_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,

                order_id INT NOT NULL,

                order_number VARCHAR(50) NOT NULL,

                product_id INT,

                product_name VARCHAR(255) NOT NULL,

                quantity INT DEFAULT 1,

                customer_access_token VARCHAR(191) NOT NULL,

                reason VARCHAR(150) NOT NULL,

                description TEXT,

                return_status VARCHAR(50)
                    DEFAULT 'Return Requested',

                refund_status VARCHAR(50)
                    DEFAULT 'Not Initiated',

                refund_id VARCHAR(100) NULL,

                refund_amount DECIMAL(10,2) NULL,

                admin_note TEXT,

                requested_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                updated_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,

                INDEX idx_return_order_id (order_id),

                INDEX idx_return_product_id (product_id)
            )
        """)

        # ====================================================
        # RETURN TABLE MIGRATIONS
        # ====================================================

        return_migrations = [

            (
                "refund_id",
                "VARCHAR(100) NULL"
            ),

            (
                "refund_amount",
                "DECIMAL(10,2) NULL"
            ),

            (
                "admin_note",
                "TEXT"
            ),
        ]

        for col_name, col_def in return_migrations:

            cur.execute(
                f"""
                SHOW COLUMNS FROM return_requests
                LIKE '{col_name}'
                """
            )

            if not cur.fetchone():

                try:

                    cur.execute(
                        f"""
                        ALTER TABLE return_requests
                        ADD COLUMN {col_name} {col_def}
                        """
                    )

                    print(
                        f"✅ Column {col_name} added to return_requests"
                    )

                except Exception as alter_err:

                    print(
                        f"Note on return column {col_name}:",
                        alter_err
                    )

        conn.commit()

        print(
            "✅ Database tables and columns verified"
        )

    except Exception as e:

        print("❌ Table error:", e)

        if conn:
            conn.rollback()

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# RUN MIGRATIONS ON STARTUP
# ============================================================

try:

    create_tables()

except Exception as e:

    print("Startup check notice:", e)


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({

        "success": True,

        "message":
            "Sarika Fashions backend running!",

        "razorpay":
            bool(razorpay_client),

    })


# ============================================================
# ADMIN AUTH ROUTES
# ============================================================

@app.route(
    "/api/admin/login",
    methods=["POST"]
)
def admin_login():

    data = request.get_json(
        silent=True
    ) or {}

    email = str(
        data.get("email", "")
    ).strip()

    password = str(
        data.get("password", "")
    )

    if not ADMIN_EMAIL or not ADMIN_PASSWORD:

        return jsonify({

            "success": False,

            "message":
                "Admin credentials not configured in backend .env",

        }), 500

    if (
        email.lower()
        != ADMIN_EMAIL.lower()
        or password != ADMIN_PASSWORD
    ):

        return jsonify({

            "success": False,

            "message":
                "Invalid email or password",

        }), 401

    session["admin_logged_in"] = True

    session["admin_email"] = ADMIN_EMAIL

    session.permanent = True

    return jsonify({

        "success": True,

        "message":
            "Admin login successful",

        "admin": {
            "email": ADMIN_EMAIL
        },

    })


@app.route(
    "/api/admin/me",
    methods=["GET"]
)
def admin_me():

    logged_in = bool(
        session.get(
            "admin_logged_in",
            False
        )
    )

    admin_email = session.get(
        "admin_email"
    )

    if not logged_in:

        return jsonify({

            "success": False,

            "logged_in": False,

            "message":
                "Admin session not found",

        }), 401

    return jsonify({

        "success": True,

        "logged_in": True,

        "admin": {
            "email": admin_email
        },

    })


@app.route(
    "/api/admin/logout",
    methods=["POST"]
)
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    session.pop(
        "admin_email",
        None
    )

    return jsonify({

        "success": True,

        "message":
            "Logged out successfully",

    })


# ============================================================
# PRODUCTS - PUBLIC GET
# ============================================================

@app.route(
    "/api/products",
    methods=["GET"]
)
def get_products():

    conn = None
    cur = None

    try:

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        cur.execute("""
            SELECT
                p.id,
                p.name,
                p.category,
                p.price,
                p.old_price,
                p.image,
                p.description,
                p.stock,
                p.created_at,
                p.image2,
                p.image3,
                p.image4,

                COALESCE(
                    ROUND(AVG(r.rating), 1),
                    0
                ) AS rating,

                COUNT(r.id) AS reviews

            FROM products p

            LEFT JOIN reviews r
                ON p.id = r.product_id

            GROUP BY p.id

            ORDER BY p.created_at DESC
        """)

        products = cur.fetchall()

        for product in products:

            if product.get("created_at"):

                product["created_at"] = (
                    product["created_at"]
                    .isoformat()
                )

            product["price"] = float(
                product["price"] or 0
            )

            product["old_price"] = float(
                product["old_price"] or 0
            )

            product["rating"] = float(
                product["rating"] or 0
            )

            product["reviews"] = int(
                product["reviews"] or 0
            )

            product["stock"] = int(
                product["stock"] or 0
            )

        return jsonify({

            "success": True,

            "products": products,

        })

    except Error as e:

        return jsonify({

            "success": False,

            "error": str(e),

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


@app.route(
    "/api/products/<int:product_id>",
    methods=["GET"]
)
def get_product(product_id):

    conn = None
    cur = None

    try:

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        cur.execute(
            """
            SELECT *
            FROM products
            WHERE id=%s
            """,
            (product_id,)
        )

        product = cur.fetchone()

        if not product:

            return jsonify({

                "success": False,

                "message":
                    "Product not found",

            }), 404

        if product.get("created_at"):

            product["created_at"] = (
                product["created_at"]
                .isoformat()
            )

        return jsonify({

            "success": True,

            "product": product,

        })

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# PRODUCTS - ADMIN CRUD
# ============================================================

@app.route(
    "/api/products",
    methods=["POST"]
)
@admin_required
def add_product():

    conn = None
    cur = None

    try:

        name = request.form.get(
            "name",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        price = request.form.get(
            "price",
            ""
        ).strip()

        old_price = request.form.get(
            "old_price",
            ""
        ).strip()

        stock = request.form.get(
            "stock",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        if not name or not category:

            return jsonify({

                "success": False,

                "message":
                    "Name and Category are required",

            }), 400

        try:

            price = float(price)

            stock = int(stock)

            old_price = (
                float(old_price)
                if old_price
                else None
            )

        except (
            ValueError,
            TypeError
        ):

            return jsonify({

                "success": False,

                "message":
                    "Invalid numeric fields",

            }), 400

        image_urls = {}

        for field_name in [
            "image",
            "image2",
            "image3",
            "image4",
        ]:

            file = request.files.get(
                field_name
            )

            if file and file.filename:

                res = cloudinary.uploader.upload(
                    file,
                    folder="sarika-fashions/products"
                )

                image_urls[field_name] = (
                    res.get("secure_url")
                )

        if not image_urls.get("image"):

            return jsonify({

                "success": False,

                "message":
                    "Main product image is required",

            }), 400

        conn = get_db_connection()

        cur = conn.cursor()

        cur.execute("""
            INSERT INTO products (
                name,
                category,
                price,
                old_price,
                image,
                description,
                stock,
                image2,
                image3,
                image4
            )
            VALUES (
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s
            )
        """, (

            name,

            category,

            price,

            old_price,

            image_urls.get("image"),

            description,

            stock,

            image_urls.get("image2"),

            image_urls.get("image3"),

            image_urls.get("image4"),

        ))

        product_id = cur.lastrowid

        conn.commit()

        return jsonify({

            "success": True,

            "message":
                "Product added successfully",

            "product_id":
                product_id,

        }), 201

    except Exception as e:

        if conn:
            conn.rollback()

        return jsonify({

            "success": False,

            "error": str(e),

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


@app.route(
    "/api/products/<int:product_id>",
    methods=["PUT"]
)
@admin_required
def update_product(product_id):

    conn = None
    cur = None

    try:

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        cur.execute(
            """
            SELECT *
            FROM products
            WHERE id=%s
            """,
            (product_id,)
        )

        existing = cur.fetchone()

        if not existing:

            return jsonify({

                "success": False,

                "message":
                    "Product not found",

            }), 404

        name = request.form.get(
            "name",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        price_val = request.form.get(
            "price",
            ""
        ).strip()

        old_price_val = request.form.get(
            "old_price",
            ""
        ).strip()

        stock_val = request.form.get(
            "stock",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        try:

            price = float(price_val)

            stock = int(stock_val)

            old_price = (
                float(old_price_val)
                if old_price_val
                else None
            )

        except (
            ValueError,
            TypeError
        ):

            return jsonify({

                "success": False,

                "message":
                    "Invalid numeric fields",

            }), 400

        image_urls = {
            k: existing.get(k)
            for k in [
                "image",
                "image2",
                "image3",
                "image4",
            ]
        }

        for field_name in [
            "image",
            "image2",
            "image3",
            "image4",
        ]:

            file = request.files.get(
                field_name
            )

            if file and file.filename:

                res = cloudinary.uploader.upload(
                    file,
                    folder="sarika-fashions/products"
                )

                if res.get("secure_url"):

                    image_urls[field_name] = (
                        res["secure_url"]
                    )

        cur.execute("""
            UPDATE products

            SET
                name=%s,
                category=%s,
                price=%s,
                old_price=%s,
                description=%s,
                stock=%s,
                image=%s,
                image2=%s,
                image3=%s,
                image4=%s

            WHERE id=%s
        """, (

            name,

            category,

            price,

            old_price,

            description,

            stock,

            image_urls["image"],

            image_urls["image2"],

            image_urls["image3"],

            image_urls["image4"],

            product_id,

        ))

        conn.commit()

        return jsonify({

            "success": True,

            "message":
                "Product updated successfully",

        })

    except Exception as e:

        if conn:
            conn.rollback()

        return jsonify({

            "success": False,

            "error": str(e),

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


@app.route(
    "/api/products/<int:product_id>",
    methods=["DELETE"]
)
@admin_required
def delete_product(product_id):

    conn = None
    cur = None

    try:

        conn = get_db_connection()

        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM products
            WHERE id=%s
            """,
            (product_id,)
        )

        if cur.rowcount == 0:

            return jsonify({

                "success": False,

                "message":
                    "Product not found",

            }), 404

        conn.commit()

        return jsonify({

            "success": True,

            "message":
                "Product deleted successfully",

        })

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# RAZORPAY KEY
# ============================================================

@app.route(
    "/api/razorpay/key",
    methods=["GET"]
)
def get_razorpay_key():

    return jsonify({

        "key": RAZORPAY_KEY_ID,

        "key_id": RAZORPAY_KEY_ID,

    })


# ============================================================
# RAZORPAY CREATE ORDER
# ============================================================

@app.route(
    "/api/payment/create-order",
    methods=["POST"]
)
def create_payment_order():

    try:

        if not razorpay_client:

            return jsonify({

                "success": False,

                "error":
                    "Razorpay keys missing",

            }), 500

        data = request.get_json(
            silent=True
        ) or {}

        amount = float(
            data.get(
                "amount",
                0
            )
        )

        amount_paise = int(
            round(
                amount * 100
            )
        )

        if amount_paise < 100:
            amount_paise = 100

        order = razorpay_client.order.create({

            "amount":
                amount_paise,

            "currency":
                "INR",

            "receipt":
                f"receipt_{int(datetime.now().timestamp())}",

            "payment_capture":
                1,

        })

        return jsonify({

            "success": True,

            "order": order,

            "order_id":
                order["id"],

            "amount":
                order["amount"],

            "currency":
                order["currency"],

            "key_id":
                RAZORPAY_KEY_ID,

            "key":
                RAZORPAY_KEY_ID,

        })

    except Exception as e:

        print(
            "❌ RAZORPAY CREATE ORDER ERROR:",
            e
        )

        return jsonify({

            "success": False,

            "error": str(e),

        }), 500


# ============================================================
# RAZORPAY VERIFY
# ============================================================

@app.route(
    "/api/payment/verify",
    methods=["POST"]
)
def verify_payment():

    try:

        if not razorpay_client:

            return jsonify({

                "success": False,

                "error":
                    "Razorpay is not configured",

            }), 500

        data = request.get_json(
            silent=True
        ) or {}

        razorpay_client.utility.verify_payment_signature({

            "razorpay_order_id":
                data["razorpay_order_id"],

            "razorpay_payment_id":
                data["razorpay_payment_id"],

            "razorpay_signature":
                data["razorpay_signature"],

        })

        return jsonify({

            "success": True,

            "message":
                "Payment verified successfully",

        })

    except Exception as e:

        return jsonify({

            "success": False,

            "error": str(e),

        }), 400


# ============================================================
# COMPLETE PAYMENT + CREATE ORDER
# ============================================================

@app.route(
    "/api/payment/complete",
    methods=["POST"]
)
def complete_payment_and_create_order():

    conn = None
    cur = None

    try:

        if not razorpay_client:

            return jsonify({

                "success": False,

                "message":
                    "Razorpay is not configured",

            }), 500

        data = request.get_json(
            silent=True
        ) or {}

        razorpay_order_id = str(
            data.get(
                "razorpay_order_id",
                ""
            )
        ).strip()

        razorpay_payment_id = str(
            data.get(
                "razorpay_payment_id",
                ""
            )
        ).strip()

        razorpay_signature = str(
            data.get(
                "razorpay_signature",
                ""
            )
        ).strip()

        if (
            not razorpay_order_id
            or not razorpay_payment_id
            or not razorpay_signature
        ):

            return jsonify({

                "success": False,

                "message":
                    "Razorpay payment details missing",

            }), 400

        # ====================================================
        # VERIFY SIGNATURE
        # ====================================================

        try:

            razorpay_client.utility.verify_payment_signature({

                "razorpay_order_id":
                    razorpay_order_id,

                "razorpay_payment_id":
                    razorpay_payment_id,

                "razorpay_signature":
                    razorpay_signature,

            })

        except Exception as sig_err:

            print(
                "❌ SIGNATURE VERIFICATION FAILED:",
                sig_err
            )

            return jsonify({

                "success": False,

                "message":
                    f"Signature verification failed: {str(sig_err)}",

            }), 400

        # ====================================================
        # FETCH PAYMENT
        # ====================================================

        payment = razorpay_client.payment.fetch(
            razorpay_payment_id
        )

        payment_status = str(
            payment.get(
                "status",
                ""
            )
        ).lower()

        if payment_status not in [
            "captured",
            "authorized",
        ]:

            return jsonify({

                "success": False,

                "message":
                    f"Payment is in '{payment_status}' status, not captured.",

            }), 400

        if payment_status == "authorized":

            try:

                razorpay_client.payment.capture(
                    razorpay_payment_id,
                    int(
                        payment.get(
                            "amount",
                            0
                        )
                    )
                )

                payment_status = "captured"

            except Exception as cap_err:

                print(
                    "Capture notice:",
                    cap_err
                )

        # ====================================================
        # VERIFY AMOUNT
        # ====================================================

        razorpay_amount = int(
            payment.get(
                "amount",
                0
            )
        )

        try:

            requested_total = float(
                data.get(
                    "total_amount",
                    data.get(
                        "total",
                        data.get(
                            "amount",
                            0
                        )
                    )
                )
            )

        except Exception:

            requested_total = 0

        requested_amount_paise = int(
            round(
                requested_total * 100
            )
        )

        if (
            requested_amount_paise > 0
            and razorpay_amount > 0
            and razorpay_amount
            != requested_amount_paise
        ):

            print(
                "❌ AMOUNT MISMATCH:",
                "Razorpay:",
                razorpay_amount,
                "Requested:",
                requested_amount_paise
            )

            return jsonify({

                "success": False,

                "message":
                    f"Payment amount mismatch: expected {razorpay_amount} paise, got {requested_amount_paise} paise",

            }), 400

        # ====================================================
        # DATABASE
        # ====================================================

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        # ====================================================
        # PREVENT DUPLICATES
        # ====================================================

        cur.execute(
            """
            SELECT
                id,
                order_number,
                customer_access_token,
                payment_status,
                order_status

            FROM orders

            WHERE razorpay_payment_id=%s

            LIMIT 1
            """,
            (razorpay_payment_id,)
        )

        existing_order = cur.fetchone()

        if existing_order:

            existing_token = (
                existing_order.get(
                    "customer_access_token"
                )
            )

            if existing_token:

                session[
                    "customer_order_token"
                ] = existing_token

                session.permanent = True

            return jsonify({

                "success": True,

                "message":
                    "Order already exists",

                "order_id":
                    existing_order["id"],

                "order_number":
                    existing_order["order_number"],

                "customer_order_token":
                    existing_token,

            }), 200

        # ====================================================
        # CUSTOMER TOKEN
        # ====================================================

        customer_token = (
            get_customer_order_token()
        )

        if not customer_token:

            customer_token = (
                create_customer_order_token()
            )

        # ====================================================
        # CUSTOMER DETAILS
        # ====================================================

        customer_name = str(
            data.get(
                "customer_name",
                ""
            )
        ).strip()

        customer_email = str(
            data.get(
                "customer_email",
                ""
            )
        ).strip()

        customer_phone = str(
            data.get(
                "customer_phone",
                ""
            )
        ).strip()

        address = str(
            data.get(
                "address",
                data.get(
                    "address_line",
                    ""
                )
            )
        ).strip()

        address_line = str(
            data.get(
                "address_line",
                address
            )
        ).strip()

        city = str(
            data.get(
                "city",
                ""
            )
        ).strip()

        state = str(
            data.get(
                "state",
                ""
            )
        ).strip()

        pincode = str(
            data.get(
                "pincode",
                ""
            )
        ).strip()

        items = data.get(
            "items",
            []
        )

        try:

            subtotal = float(
                data.get(
                    "subtotal",
                    0
                )
            )

        except Exception:

            subtotal = 0

        try:

            shipping = float(
                data.get(
                    "shipping",
                    0
                )
            )

        except Exception:

            shipping = 0

        total_amount = (
            requested_total
            if requested_total > 0
            else razorpay_amount / 100.0
        )

        # ====================================================
        # ORDER NUMBER
        # ====================================================

        cur.execute(
            """
            SELECT order_number
            FROM orders
            ORDER BY id DESC
            LIMIT 1
            """
        )

        last = cur.fetchone()

        next_num = 1

        if last and last.get(
            "order_number"
        ):

            try:

                next_num = (
                    int(
                        str(
                            last[
                                "order_number"
                            ]
                        ).replace(
                            "SF-",
                            ""
                        )
                    )
                    + 1
                )

            except Exception:

                next_num = 1

        order_number = (
            f"SF-{next_num:05d}"
        )

        # ====================================================
        # DYNAMIC COLUMNS
        # ====================================================

        cur.execute(
            "SHOW COLUMNS FROM orders"
        )

        existing_cols = {
            col["Field"]
            for col in cur.fetchall()
        }

        order_data_map = {

            "order_number":
                order_number,

            "customer_name":
                customer_name,

            "customer_email":
                customer_email,

            "customer_phone":
                customer_phone,

            "address":
                address,

            "city":
                city,

            "state":
                state,

            "pincode":
                pincode,

            "items":
                json.dumps(items),

            "total_amount":
                total_amount,

            "razorpay_order_id":
                razorpay_order_id,

            "razorpay_payment_id":
                razorpay_payment_id,

            "payment_status":
                "Captured",

            "order_status":
                "Placed",

            "customer_access_token":
                customer_token,

        }

        if "address_line" in existing_cols:

            order_data_map[
                "address_line"
            ] = address_line

        if "subtotal" in existing_cols:

            order_data_map[
                "subtotal"
            ] = subtotal

        if "shipping" in existing_cols:

            order_data_map[
                "shipping"
            ] = shipping

        columns = list(
            order_data_map.keys()
        )

        placeholders = ", ".join(
            ["%s"] * len(columns)
        )

        values = tuple(
            order_data_map[col]
            for col in columns
        )

        cur.execute(
            f"""
            INSERT INTO orders
            ({', '.join(columns)})
            VALUES
            ({placeholders})
            """,
            values
        )

        order_id = cur.lastrowid

        conn.commit()

        session[
            "customer_order_token"
        ] = customer_token

        session.permanent = True

        print(
            "======================================"
        )

        print(
            "✅ ORDER CREATED SUCCESSFULLY:",
            order_number
        )

        print(
            "Order ID:",
            order_id
        )

        print(
            "======================================"
        )

        return jsonify({

            "success": True,

            "message":
                "Order created successfully",

            "order_id":
                order_id,

            "order_number":
                order_number,

            "customer_order_token":
                customer_token,

            "total_amount":
                total_amount,

        }), 201

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "❌ PAYMENT COMPLETE ERROR:",
            repr(e)
        )

        import traceback

        traceback.print_exc()

        return jsonify({

            "success": False,

            "message":
                f"Failed to save order: {str(e)}",

            "error":
                str(e),

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# MANUAL / FALLBACK ORDER
# ============================================================

@app.route(
    "/api/orders",
    methods=["POST"]
)
def create_order():

    conn = None
    cur = None

    try:

        data = request.get_json(
            silent=True
        ) or {}

        customer_token = (
            get_customer_order_token()
        )

        if not customer_token:

            customer_token = (
                create_customer_order_token()
            )

        customer_name = str(
            data.get(
                "customer_name",
                ""
            )
        ).strip()

        customer_email = str(
            data.get(
                "customer_email",
                ""
            )
        ).strip()

        customer_phone = str(
            data.get(
                "customer_phone",
                ""
            )
        ).strip()

        address = str(
            data.get(
                "address",
                data.get(
                    "address_line",
                    ""
                )
            )
        ).strip()

        address_line = str(
            data.get(
                "address_line",
                address
            )
        ).strip()

        city = str(
            data.get(
                "city",
                ""
            )
        ).strip()

        state = str(
            data.get(
                "state",
                ""
            )
        ).strip()

        pincode = str(
            data.get(
                "pincode",
                ""
            )
        ).strip()

        items = data.get(
            "items",
            []
        )

        total_amount = float(
            data.get(
                "total_amount",
                data.get(
                    "total",
                    0
                )
            )
        )

        subtotal = float(
            data.get(
                "subtotal",
                total_amount
            )
        )

        shipping = float(
            data.get(
                "shipping",
                0
            )
        )

        razorpay_order_id = data.get(
            "razorpay_order_id"
        )

        razorpay_payment_id = data.get(
            "razorpay_payment_id"
        )

        payment_status = data.get(
            "payment_status",
            "Paid"
        )

        order_status = data.get(
            "order_status",
            "Placed"
        )

        if (
            not customer_name
            or not customer_phone
            or not address
            or not city
            or not state
            or not pincode
            or not items
        ):

            return jsonify({

                "success": False,

                "message":
                    "All customer fields and items are required",

            }), 400

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        cur.execute(
            """
            SELECT order_number
            FROM orders
            ORDER BY id DESC
            LIMIT 1
            """
        )

        last = cur.fetchone()

        next_num = 1

        if last and last.get(
            "order_number"
        ):

            try:

                next_num = (
                    int(
                        str(
                            last[
                                "order_number"
                            ]
                        ).replace(
                            "SF-",
                            ""
                        )
                    )
                    + 1
                )

            except Exception:

                next_num = 1

        order_number = (
            f"SF-{next_num:05d}"
        )

        cur.execute(
            "SHOW COLUMNS FROM orders"
        )

        existing_cols = {
            col["Field"]
            for col in cur.fetchall()
        }

        order_data_map = {

            "order_number":
                order_number,

            "customer_name":
                customer_name,

            "customer_email":
                customer_email,

            "customer_phone":
                customer_phone,

            "address":
                address,

            "city":
                city,

            "state":
                state,

            "pincode":
                pincode,

            "items":
                json.dumps(items),

            "total_amount":
                total_amount,

            "razorpay_order_id":
                razorpay_order_id,

            "razorpay_payment_id":
                razorpay_payment_id,

            "payment_status":
                payment_status,

            "order_status":
                order_status,

            "customer_access_token":
                customer_token,

        }

        if "address_line" in existing_cols:

            order_data_map[
                "address_line"
            ] = address_line

        if "subtotal" in existing_cols:

            order_data_map[
                "subtotal"
            ] = subtotal

        if "shipping" in existing_cols:

            order_data_map[
                "shipping"
            ] = shipping

        columns = list(
            order_data_map.keys()
        )

        placeholders = ", ".join(
            ["%s"] * len(columns)
        )

        values = tuple(
            order_data_map[col]
            for col in columns
        )

        cur.execute(
            f"""
            INSERT INTO orders
            ({', '.join(columns)})
            VALUES
            ({placeholders})
            """,
            values
        )

        order_id = cur.lastrowid

        conn.commit()

        session[
            "customer_order_token"
        ] = customer_token

        session.permanent = True

        return jsonify({

            "success": True,

            "message":
                "Order created successfully",

            "order_id":
                order_id,

            "order_number":
                order_number,

            "customer_order_token":
                customer_token,

        }), 201

    except Exception as e:

        if conn:
            conn.rollback()

        return jsonify({

            "success": False,

            "error":
                str(e),

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# MY ORDERS
# ============================================================

@app.route(
    "/api/my-orders",
    methods=["GET"]
)
def get_my_orders():

    conn = None
    cur = None

    try:

        customer_token = (
            get_customer_order_token()
        )

        phone = request.args.get(
            "phone",
            ""
        ).strip()

        print(
            "\n======================================"
        )

        print(
            "🛍️ MY ORDERS REQUEST"
        )

        print(
            "Customer token:",
            customer_token
        )

        print(
            "Phone fallback:",
            phone
        )

        print(
            "======================================"
        )

        if not customer_token and not phone:

            return jsonify({

                "success": True,

                "authenticated": False,

                "orders": [],

                "message":
                    "Please enter your phone number to find orders.",

            }), 200

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        if customer_token and phone:

            cur.execute(
                """
                SELECT *
                FROM orders

                WHERE
                    customer_access_token=%s
                    OR customer_phone=%s

                ORDER BY created_at DESC
                """,
                (
                    customer_token,
                    phone,
                )
            )

        elif customer_token:

            cur.execute(
                """
                SELECT *
                FROM orders

                WHERE customer_access_token=%s

                ORDER BY created_at DESC
                """,
                (customer_token,)
            )

        else:

            cur.execute(
                """
                SELECT *
                FROM orders

                WHERE customer_phone=%s

                ORDER BY created_at DESC
                """,
                (phone,)
            )

        orders = cur.fetchall()

        # ====================================================
        # GET RETURNS FOR THESE ORDERS
        # ====================================================

        order_ids = [
            order["id"]
            for order in orders
            if order.get("id") is not None
        ]

        return_requests_by_order = {}

        if order_ids:

            try:

                placeholders = ",".join(
                    ["%s"] * len(order_ids)
                )

                cur.execute(
                    f"""
                    SELECT
                        id,
                        order_id,
                        order_number,
                        product_id,
                        product_name,
                        quantity,
                        reason,
                        description,
                        return_status,
                        refund_status,
                        refund_id,
                        refund_amount,
                        admin_note,
                        requested_at,
                        updated_at

                    FROM return_requests

                    WHERE order_id IN
                    ({placeholders})

                    ORDER BY requested_at DESC
                    """,
                    tuple(order_ids)
                )

                for return_item in cur.fetchall():

                    if (
                        return_item.get(
                            "requested_at"
                        )
                        and hasattr(
                            return_item[
                                "requested_at"
                            ],
                            "isoformat"
                        )
                    ):

                        return_item[
                            "requested_at"
                        ] = (
                            return_item[
                                "requested_at"
                            ].isoformat()
                        )

                    if (
                        return_item.get(
                            "updated_at"
                        )
                        and hasattr(
                            return_item[
                                "updated_at"
                            ],
                            "isoformat"
                        )
                    ):

                        return_item[
                            "updated_at"
                        ] = (
                            return_item[
                                "updated_at"
                            ].isoformat()
                        )

                    if return_item.get(
                        "refund_amount"
                    ) is not None:

                        return_item[
                            "refund_amount"
                        ] = float(
                            return_item[
                                "refund_amount"
                            ]
                        )

                    return_requests_by_order.setdefault(
                        return_item["order_id"],
                        []
                    ).append(
                        return_item
                    )

            except Exception as ret_err:

                print(
                    "Notice: return_requests check skipped:",
                    ret_err
                )

        datetime_fields = [

            "created_at",

            "confirmed_at",

            "shipped_at",

            "out_for_delivery_at",

            "delivered_at",

            "received_at",

        ]

        for order in orders:

            for field in datetime_fields:

                val = order.get(field)

                if val:

                    if hasattr(
                        val,
                        "isoformat"
                    ):

                        order[field] = (
                            val.isoformat()
                        )

                    else:

                        order[field] = str(
                            val
                        )

            order[
                "customer_received"
            ] = bool(
                order.get(
                    "customer_received",
                    0
                )
            )

            order["items"] = parse_order_items(
                order.get("items")
            )

            order["subtotal"] = float(
                order.get(
                    "subtotal"
                ) or 0
            )

            order["shipping"] = float(
                order.get(
                    "shipping"
                ) or 0
            )

            order["total_amount"] = float(
                order.get(
                    "total_amount"
                ) or 0
            )

            order["total"] = (
                order["total_amount"]
            )

            order[
                "return_requests"
            ] = return_requests_by_order.get(
                order["id"],
                []
            )

            # NEVER expose customer token
            order.pop(
                "customer_access_token",
                None
            )

        print(
            f"✅ MY ORDERS FOUND: {len(orders)}"
        )

        return jsonify({

            "success": True,

            "authenticated": True,

            "orders": orders,

        }), 200

    except Exception as e:

        print(
            "❌ MY ORDERS ERROR:",
            repr(e)
        )

        import traceback

        traceback.print_exc()

        return jsonify({

            "success": False,

            "authenticated": False,

            "orders": [],

            "message":
                f"Failed to fetch your orders: {str(e)}",

            "error":
                str(e),

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


@app.route(
    "/api/my-orders/session",
    methods=["GET"]
)
def my_orders_session_status():

    token = get_customer_order_token()

    return jsonify({

        "success": True,

        "authenticated":
            bool(token),

        "has_customer_order_session":
            bool(token),

    }), 200


# ============================================================
# CUSTOMER CONFIRM RECEIVED
# ============================================================

@app.route(
    "/api/my-orders/<int:order_id>/received",
    methods=["POST"]
)
def customer_confirm_received(order_id):

    conn = None
    cur = None

    try:

        customer_token = (
            get_customer_order_token()
        )

        if not customer_token:

            return jsonify({

                "success": False,

                "message":
                    "Customer order session not found.",

            }), 401

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        cur.execute(
            """
            SELECT
                id,
                order_number,
                order_status,
                customer_received,
                received_at

            FROM orders

            WHERE
                id=%s
                AND customer_access_token=%s
            """,
            (
                order_id,
                customer_token,
            )
        )

        order = cur.fetchone()

        if not order:

            return jsonify({

                "success": False,

                "message":
                    "Order not found.",

            }), 404

        current_status = (
            order.get(
                "order_status"
            ) or ""
        )

        if int(
            order.get(
                "customer_received"
            ) or 0
        ) == 1:

            return jsonify({

                "success": True,

                "message":
                    "Order was already confirmed as received.",

            })

        if current_status != "Delivered":

            return jsonify({

                "success": False,

                "message":
                    "Receipt can only be confirmed once Delivered.",

            }), 400

        cur.execute(
            """
            UPDATE orders

            SET
                customer_received=1,
                received_at=NOW(),
                order_status='Closed'

            WHERE
                id=%s
                AND customer_access_token=%s
            """,
            (
                order_id,
                customer_token,
            )
        )

        conn.commit()

        return jsonify({

            "success": True,

            "message":
                "Order received successfully. Order is now closed.",

        })

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


@app.route(
    "/api/orders/<int:order_id>/received",
    methods=["PUT", "POST"]
)
def confirm_order_received_legacy(order_id):

    return customer_confirm_received(
        order_id
    )


# ============================================================
# CREATE RETURN REQUEST - FIXED
# ============================================================

@app.route(
    "/api/returns",
    methods=["POST"]
)
def create_return_request():

    conn = None
    cur = None

    try:

        # ====================================================
        # GET TOKEN
        # ====================================================

        authorization = request.headers.get(
            "Authorization",
            ""
        ).strip()

        header_token = request.headers.get(
            "X-Customer-Order-Token",
            ""
        ).strip()

        customer_token = None

        if authorization.lower().startswith(
            "bearer "
        ):

            customer_token = (
                authorization[7:].strip()
            )

        if (
            not customer_token
            and header_token
        ):

            customer_token = header_token

        if not customer_token:

            customer_token = (
                get_customer_order_token()
            )

        # ====================================================
        # READ DATA
        # ====================================================

        data = request.get_json(
            silent=True
        ) or {}

        print(
            "\n======================================"
        )

        print(
            "↩️ RETURN REQUEST"
        )

        print(
            "Customer token exists:",
            bool(customer_token)
        )

        print(
            "Return data:",
            data
        )

        print(
            "======================================"
        )

        # ====================================================
        # PHONE FALLBACK
        # ====================================================

        customer_phone = str(
            data.get(
                "customer_phone",
                data.get(
                    "phone",
                    ""
                )
            )
        ).strip()

        if not customer_token and not customer_phone:

            return jsonify({

                "success": False,

                "message":
                    "Customer order session not found.",

            }), 401

        # ====================================================
        # READ RETURN DATA
        # ====================================================

        order_id = data.get(
            "order_id"
        )

        order_number = str(
            data.get(
                "order_number",
                ""
            )
        ).strip().upper()

        requested_product_id = data.get(
            "product_id"
        )

        requested_product_name = str(
            data.get(
                "product_name",
                ""
            )
        ).strip()

        try:

            requested_quantity = int(
                data.get(
                    "quantity",
                    1
                ) or 1
            )

        except (
            ValueError,
            TypeError
        ):

            requested_quantity = 1

        reason = str(
            data.get(
                "reason",
                ""
            )
        ).strip()

        description = str(
            data.get(
                "description",
                ""
            )
        ).strip()

        # ====================================================
        # VALIDATION
        # ====================================================

        if not order_id:

            return jsonify({

                "success": False,

                "message":
                    "Order ID is required.",

            }), 400

        if not reason:

            return jsonify({

                "success": False,

                "message":
                    "Return reason is required.",

            }), 400

        if requested_quantity < 1:

            return jsonify({

                "success": False,

                "message":
                    "Return quantity must be at least 1.",

            }), 400

        # ====================================================
        # DATABASE
        # ====================================================

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        # ====================================================
        # FIND ORDER
        #
        # Token is preferred.
        # Phone is fallback for your existing My Orders flow.
        # ====================================================

        order = None

        if customer_token:

            cur.execute(
                """
                SELECT *

                FROM orders

                WHERE
                    id=%s
                    AND customer_access_token=%s

                LIMIT 1
                """,
                (
                    order_id,
                    customer_token,
                )
            )

            order = cur.fetchone()

        if not order and customer_phone:

            cur.execute(
                """
                SELECT *

                FROM orders

                WHERE
                    id=%s
                    AND customer_phone=%s

                LIMIT 1
                """,
                (
                    order_id,
                    customer_phone,
                )
            )

            order = cur.fetchone()

        # ====================================================
        # LAST FALLBACK:
        # ORDER NUMBER + PHONE
        # ====================================================

        if (
            not order
            and order_number
            and customer_phone
        ):

            cur.execute(
                """
                SELECT *

                FROM orders

                WHERE
                    order_number=%s
                    AND customer_phone=%s

                LIMIT 1
                """,
                (
                    order_number,
                    customer_phone,
                )
            )

            order = cur.fetchone()

        if not order:

            print(
                "❌ RETURN FAILED: order not found"
            )

            return jsonify({

                "success": False,

                "message":
                    "Order not found or customer details do not match.",

            }), 404

        # ====================================================
        # GET REAL CUSTOMER TOKEN
        # ====================================================

        real_customer_token = (
            order.get(
                "customer_access_token"
            )
        )

        if not real_customer_token:

            return jsonify({

                "success": False,

                "message":
                    "This order does not have a customer access token.",

            }), 400

        # ====================================================
        # PARSE ORDER ITEMS
        # ====================================================

        order_items = parse_order_items(
            order.get("items")
        )

        if not order_items:

            return jsonify({

                "success": False,

                "message":
                    "No products were found in this order.",

            }), 400

        print(
            "Order items:",
            order_items
        )

        # ====================================================
        # FIND EXACT PRODUCT
        # ====================================================

        selected_item = None

        normalized_requested_id = (
            normalize_product_id(
                requested_product_id
            )
        )

        # ----------------------------------------------------
        # FIRST: MATCH BY PRODUCT ID
        # ----------------------------------------------------

        if normalized_requested_id is not None:

            for item in order_items:

                item_product_id = (
                    get_item_product_id(
                        item
                    )
                )

                normalized_item_id = (
                    normalize_product_id(
                        item_product_id
                    )
                )

                if (
                    normalized_item_id
                    is not None
                    and normalized_item_id
                    == normalized_requested_id
                ):

                    selected_item = item
                    break

        # ----------------------------------------------------
        # SECOND: MATCH BY PRODUCT NAME
        # ----------------------------------------------------

        if (
            selected_item is None
            and requested_product_name
        ):

            requested_name_lower = (
                requested_product_name
                .strip()
                .lower()
            )

            for item in order_items:

                item_name = (
                    get_item_product_name(
                        item
                    )
                )

                if (
                    item_name
                    and item_name.strip().lower()
                    == requested_name_lower
                ):

                    selected_item = item
                    break

        # ====================================================
        # PRODUCT NOT FOUND
        # ====================================================

        if selected_item is None:

            print(
                "❌ PRODUCT NOT FOUND IN ORDER"
            )

            print(
                "Requested product ID:",
                requested_product_id
            )

            print(
                "Requested product name:",
                requested_product_name
            )

            return jsonify({

                "success": False,

                "message":
                    "The selected product was not found in this order.",

            }), 400

        # ====================================================
        # GET ACTUAL PRODUCT DATA
        # ====================================================

        actual_product_id = (
            get_item_product_id(
                selected_item
            )
        )

        actual_product_name = (
            get_item_product_name(
                selected_item
            )
        )

        if not actual_product_name:

            actual_product_name = (
                requested_product_name
                or "Product"
            )

        ordered_quantity = (
            get_item_quantity(
                selected_item
            )
        )

        # ====================================================
        # CLAMP RETURN QUANTITY
        # ====================================================

        return_quantity = min(
            requested_quantity,
            ordered_quantity
        )

        if return_quantity < 1:

            return jsonify({

                "success": False,

                "message":
                    "Invalid return quantity.",

            }), 400

        # ====================================================
        # CHECK DUPLICATE RETURN
        #
        # If same product already has a return request,
        # do not create another one.
        # ====================================================

        duplicate_return = None

        if actual_product_id is not None:

            cur.execute(
                """
                SELECT
                    id,
                    return_status,
                    refund_status

                FROM return_requests

                WHERE
                    order_id=%s
                    AND product_id=%s

                LIMIT 1
                """,
                (
                    order["id"],
                    normalize_product_id(
                        actual_product_id
                    ),
                )
            )

            duplicate_return = (
                cur.fetchone()
            )

        if (
            duplicate_return is None
            and actual_product_name
        ):

            cur.execute(
                """
                SELECT
                    id,
                    return_status,
                    refund_status

                FROM return_requests

                WHERE
                    order_id=%s
                    AND LOWER(TRIM(product_name))
                        = LOWER(TRIM(%s))

                LIMIT 1
                """,
                (
                    order["id"],
                    actual_product_name,
                )
            )

            duplicate_return = (
                cur.fetchone()
            )

        if duplicate_return:

            return jsonify({

                "success": False,

                "already_exists": True,

                "return_id":
                    duplicate_return["id"],

                "message":
                    "A return request already exists for this product.",

                "return_status":
                    duplicate_return.get(
                        "return_status"
                    ),

                "refund_status":
                    duplicate_return.get(
                        "refund_status"
                    ),

            }), 409

        # ====================================================
        # INSERT RETURN
        # ====================================================

        cur.execute(
            """
            INSERT INTO return_requests (

                order_id,

                order_number,

                product_id,

                product_name,

                quantity,

                customer_access_token,

                reason,

                description,

                return_status,

                refund_status

            )

            VALUES (

                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'Return Requested',
                'Not Initiated'

            )
            """,
            (
                order["id"],

                order.get(
                    "order_number"
                ) or order_number,

                (
                    normalize_product_id(
                        actual_product_id
                    )
                    if actual_product_id
                    is not None
                    else None
                ),

                actual_product_name,

                return_quantity,

                real_customer_token,

                reason,

                description,

            )
        )

        return_id = cur.lastrowid

        conn.commit()

        # ====================================================
        # RESTORE SESSION TOKEN
        # ====================================================

        session[
            "customer_order_token"
        ] = real_customer_token

        session.permanent = True

        print(
            "======================================"
        )

        print(
            "✅ RETURN REQUEST SAVED"
        )

        print(
            "Return ID:",
            return_id
        )

        print(
            "Order ID:",
            order["id"]
        )

        print(
            "Order Number:",
            order.get("order_number")
        )

        print(
            "Product ID:",
            actual_product_id
        )

        print(
            "Product Name:",
            actual_product_name
        )

        print(
            "Quantity:",
            return_quantity
        )

        print(
            "======================================"
        )

        return jsonify({

            "success": True,

            "message":
                "Return request submitted successfully",

            "return_id":
                return_id,

            "order_id":
                order["id"],

            "order_number":
                order.get(
                    "order_number"
                ),

            "product_id":
                actual_product_id,

            "product_name":
                actual_product_name,

            "quantity":
                return_quantity,

            "return_status":
                "Return Requested",

            "refund_status":
                "Not Initiated",

        }), 201

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "❌ RETURN REQUEST ERROR:",
            repr(e)
        )

        import traceback

        traceback.print_exc()

        return jsonify({

            "success": False,

            "message":
                f"Failed to submit return request: {str(e)}",

            "error":
                str(e),

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# MY RETURNS - FIXED
# ============================================================

@app.route(
    "/api/my-returns",
    methods=["GET"]
)
def get_my_returns():

    conn = None
    cur = None

    try:

        customer_token = (
            get_customer_order_token()
        )

        phone = request.args.get(
            "phone",
            ""
        ).strip()

        if (
            not customer_token
            and not phone
        ):

            return jsonify({

                "success": True,

                "authenticated": False,

                "returns": [],

            })

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        # ====================================================
        # TOKEN FIRST
        # ====================================================

        if customer_token:

            cur.execute(
                """
                SELECT
                    r.*,
                    o.customer_name,
                    o.customer_email,
                    o.customer_phone

                FROM return_requests r

                LEFT JOIN orders o
                    ON o.id = r.order_id

                WHERE
                    r.customer_access_token=%s

                ORDER BY
                    r.requested_at DESC
                """,
                (
                    customer_token,
                )
            )

        else:

            # =================================================
            # PHONE FALLBACK
            # =================================================

            cur.execute(
                """
                SELECT
                    r.*,
                    o.customer_name,
                    o.customer_email,
                    o.customer_phone

                FROM return_requests r

                LEFT JOIN orders o
                    ON o.id = r.order_id

                WHERE
                    o.customer_phone=%s

                ORDER BY
                    r.requested_at DESC
                """,
                (
                    phone,
                )
            )

        returns = cur.fetchall()

        for item in returns:

            if item.get(
                "requested_at"
            ):

                item[
                    "requested_at"
                ] = item[
                    "requested_at"
                ].isoformat()

            if item.get(
                "updated_at"
            ):

                item[
                    "updated_at"
                ] = item[
                    "updated_at"
                ].isoformat()

            if item.get(
                "refund_amount"
            ) is not None:

                item[
                    "refund_amount"
                ] = float(
                    item[
                        "refund_amount"
                    ]
                )

            # Never send customer token
            item.pop(
                "customer_access_token",
                None
            )

        return jsonify({

            "success": True,

            "authenticated": True,

            "returns": returns,

        })

    except Exception as e:

        print(
            "❌ MY RETURNS ERROR:",
            repr(e)
        )

        return jsonify({

            "success": False,

            "message":
                f"Failed to load returns: {str(e)}",

            "returns": [],

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# GET ONE CUSTOMER RETURN
# ============================================================

@app.route(
    "/api/my-returns/<int:return_id>",
    methods=["GET"]
)
def get_my_return(return_id):

    conn = None
    cur = None

    try:

        customer_token = (
            get_customer_order_token()
        )

        phone = request.args.get(
            "phone",
            ""
        ).strip()

        if (
            not customer_token
            and not phone
        ):

            return jsonify({

                "success": False,

                "message":
                    "Customer order session not found",

            }), 401

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        return_item = None

        if customer_token:

            cur.execute(
                """
                SELECT
                    r.*,
                    o.customer_name,
                    o.customer_email,
                    o.customer_phone

                FROM return_requests r

                LEFT JOIN orders o
                    ON o.id = r.order_id

                WHERE
                    r.id=%s
                    AND r.customer_access_token=%s

                LIMIT 1
                """,
                (
                    return_id,
                    customer_token,
                )
            )

            return_item = (
                cur.fetchone()
            )

        if (
            not return_item
            and phone
        ):

            cur.execute(
                """
                SELECT
                    r.*,
                    o.customer_name,
                    o.customer_email,
                    o.customer_phone

                FROM return_requests r

                LEFT JOIN orders o
                    ON o.id = r.order_id

                WHERE
                    r.id=%s
                    AND o.customer_phone=%s

                LIMIT 1
                """,
                (
                    return_id,
                    phone,
                )
            )

            return_item = (
                cur.fetchone()
            )

        if not return_item:

            return jsonify({

                "success": False,

                "message":
                    "Return request not found",

            }), 404

        if return_item.get(
            "requested_at"
        ):

            return_item[
                "requested_at"
            ] = return_item[
                "requested_at"
            ].isoformat()

        if return_item.get(
            "updated_at"
        ):

            return_item[
                "updated_at"
            ] = return_item[
                "updated_at"
            ].isoformat()

        if return_item.get(
            "refund_amount"
        ) is not None:

            return_item[
                "refund_amount"
            ] = float(
                return_item[
                    "refund_amount"
                ]
            )

        return_item.pop(
            "customer_access_token",
            None
        )

        return jsonify({

            "success": True,

            "return":
                return_item,

        })

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# ADMIN - ORDERS
# ============================================================

@app.route(
    "/api/orders",
    methods=["GET"]
)
@admin_required
def get_orders():

    conn = None
    cur = None

    try:

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        cur.execute(
            """
            SELECT *
            FROM orders
            ORDER BY created_at DESC
            """
        )

        orders = cur.fetchall()

        datetime_fields = [

            "created_at",

            "confirmed_at",

            "shipped_at",

            "out_for_delivery_at",

            "delivered_at",

            "received_at",

        ]

        for order in orders:

            for field in datetime_fields:

                if order.get(field):

                    order[field] = (
                        order[field]
                        .isoformat()
                    )

            order[
                "customer_received"
            ] = bool(
                order.get(
                    "customer_received",
                    0
                )
            )

            order["items"] = parse_order_items(
                order.get("items")
            )

            order[
                "total_amount"
            ] = float(
                order.get(
                    "total_amount"
                ) or 0
            )

            order["total"] = (
                order[
                    "total_amount"
                ]
            )

            order.pop(
                "customer_access_token",
                None
            )

        return jsonify({

            "success": True,

            "orders": orders,

        })

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# ADMIN UPDATE ORDER STATUS
# ============================================================

@app.route(
    "/api/orders/<int:order_id>/status",
    methods=["PUT", "PATCH"]
)
@admin_required
def update_order_status(order_id):

    conn = None
    cur = None

    try:

        data = request.get_json(
            silent=True
        ) or {}

        requested_status = str(
            data.get(
                "order_status",
                data.get(
                    "status",
                    ""
                )
            )
        ).strip()

        allowed_statuses = [

            "Placed",

            "Confirmed",

            "Shipped",

            "Out for Delivery",

            "Delivered",

            "Cancelled",

        ]

        status_map = {

            s.lower(): s

            for s in allowed_statuses

        }

        new_status = status_map.get(
            requested_status.lower()
        )

        if not new_status:

            return jsonify({

                "success": False,

                "message":
                    "Invalid order status.",

            }), 400

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        cur.execute(
            """
            SELECT
                id,
                order_status

            FROM orders

            WHERE id=%s
            """,
            (order_id,)
        )

        order = cur.fetchone()

        if not order:

            return jsonify({

                "success": False,

                "message":
                    "Order not found.",

            }), 404

        time_field_map = {

            "Confirmed":
                "confirmed_at=NOW()",

            "Shipped":
                "shipped_at=NOW()",

            "Out for Delivery":
                "out_for_delivery_at=NOW()",

            "Delivered":
                "delivered_at=NOW()",

        }

        extra_sql = ""

        if new_status in time_field_map:

            extra_sql = (
                ", "
                + time_field_map[
                    new_status
                ]
            )

        cur.execute(
            f"""
            UPDATE orders

            SET
                order_status=%s
                {extra_sql}

            WHERE id=%s
            """,
            (
                new_status,
                order_id,
            )
        )

        conn.commit()

        return jsonify({

            "success": True,

            "message":
                f"Order status changed to {new_status}.",

        })

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# ADMIN GET RETURNS - FIXED
# ============================================================

@app.route(
    "/api/admin/returns",
    methods=["GET"]
)
@admin_required
def admin_get_returns():

    conn = None
    cur = None

    try:

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        cur.execute(
            """
            SELECT

                r.id,

                r.order_id,

                r.order_number,

                r.product_id,

                r.product_name,

                r.quantity,

                r.reason,

                r.description,

                r.return_status,

                r.refund_status,

                r.refund_id,

                r.refund_amount,

                r.admin_note,

                r.requested_at,

                r.updated_at,

                o.customer_name,

                o.customer_email,

                o.customer_phone,

                o.address,

                o.address_line,

                o.city,

                o.state,

                o.pincode,

                o.total_amount,

                o.payment_status,

                o.razorpay_order_id,

                o.razorpay_payment_id,

                o.order_status

            FROM return_requests r

            LEFT JOIN orders o
                ON o.id = r.order_id

            ORDER BY
                r.requested_at DESC
            """
        )

        returns = cur.fetchall()

        for item in returns:

            for field in [
                "requested_at",
                "updated_at",
            ]:

                if (
                    item.get(field)
                    and hasattr(
                        item[field],
                        "isoformat"
                    )
                ):

                    item[field] = (
                        item[field]
                        .isoformat()
                    )

            if item.get(
                "refund_amount"
            ) is not None:

                item[
                    "refund_amount"
                ] = float(
                    item[
                        "refund_amount"
                    ]
                )

            if item.get(
                "total_amount"
            ) is not None:

                item[
                    "total_amount"
                ] = float(
                    item[
                        "total_amount"
                    ]
                )

        print(
            "======================================"
        )

        print(
            "ADMIN RETURNS FOUND:",
            len(returns)
        )

        for item in returns:

            print(
                "Return:",
                item.get("id"),
                "| Order:",
                item.get("order_number"),
                "| Product:",
                item.get("product_name"),
                "| Status:",
                item.get("return_status")
            )

        print(
            "======================================"
        )

        return jsonify({

            "success": True,

            "returns": returns,

            "count": len(returns),

        })

    except Exception as e:

        import traceback

        traceback.print_exc()

        return jsonify({

            "success": False,

            "message":
                f"Failed to load returns: {str(e)}",

            "returns": [],

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# ADMIN UPDATE RETURN
# ============================================================

@app.route(
    "/api/admin/returns/<int:return_id>",
    methods=["PUT"]
)
@admin_required
def admin_update_return(return_id):

    conn = None
    cur = None

    try:

        data = request.get_json(
            silent=True
        ) or {}

        return_status = data.get(
            "return_status"
        )

        refund_status = data.get(
            "refund_status"
        )

        admin_note = data.get(
            "admin_note"
        )

        update_fields = []

        values = []

        if return_status:

            update_fields.append(
                "return_status=%s"
            )

            values.append(
                str(
                    return_status
                ).strip()
            )

        if refund_status:

            update_fields.append(
                "refund_status=%s"
            )

            values.append(
                str(
                    refund_status
                ).strip()
            )

        if admin_note is not None:

            update_fields.append(
                "admin_note=%s"
            )

            values.append(
                str(
                    admin_note
                ).strip()
            )

        if not update_fields:

            return jsonify({

                "success": False,

                "message":
                    "Nothing to update",

            }), 400

        values.append(
            return_id
        )

        conn = get_db_connection()

        cur = conn.cursor()

        cur.execute(
            f"""
            UPDATE return_requests

            SET
                {', '.join(update_fields)}

            WHERE id=%s
            """,
            tuple(values)
        )

        if cur.rowcount == 0:

            return jsonify({

                "success": False,

                "message":
                    "Return request not found",

            }), 404

        conn.commit()

        return jsonify({

            "success": True,

            "message":
                "Return request updated successfully",

        })

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# ADMIN PROCESS RAZORPAY REFUND
# ============================================================

@app.route(
    "/api/admin/returns/<int:return_id>/refund",
    methods=["POST", "PUT"]
)
@admin_required
def admin_process_refund(return_id):

    conn = None
    cur = None

    try:

        if not razorpay_client:

            return jsonify({

                "success": False,

                "message":
                    "Razorpay is not configured.",

            }), 500

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        # ====================================================
        # GET RETURN + ORDER
        # ====================================================

        cur.execute(
            """
            SELECT

                r.*,

                o.razorpay_payment_id,

                o.payment_status,

                o.order_number AS db_order_number,

                o.total_amount AS order_total

            FROM return_requests r

            LEFT JOIN orders o
                ON o.id = r.order_id

            WHERE r.id=%s

            LIMIT 1
            """,
            (return_id,)
        )

        return_item = cur.fetchone()

        if not return_item:

            return jsonify({

                "success": False,

                "message":
                    "Return request not found.",

            }), 404

        # ====================================================
        # PREVENT DUPLICATE REFUND
        # ====================================================

        if (
            return_item.get(
                "refund_status"
            ) == "Refunded"
        ):

            return jsonify({

                "success": False,

                "message":
                    "This return has already been refunded.",

                "refund_id":
                    return_item.get(
                        "refund_id"
                    ),

            }), 400

        payment_id = str(
            return_item.get(
                "razorpay_payment_id"
            ) or ""
        ).strip()

        if not payment_id:

            return jsonify({

                "success": False,

                "message":
                    "No Razorpay payment ID is linked to this order.",

            }), 400

        # ====================================================
        # CHECK DATABASE PAYMENT STATUS
        # ====================================================

        db_payment_status = str(
            return_item.get(
                "payment_status"
            ) or ""
        ).lower()

        if db_payment_status not in [
            "captured",
            "paid",
            "success",
            "successful",
        ]:

            return jsonify({

                "success": False,

                "message":
                    f"Database payment status is '{db_payment_status or 'Unknown'}'. Refund cannot be processed.",

            }), 400

        # ====================================================
        # FETCH RAZORPAY PAYMENT
        # ====================================================

        try:

            razorpay_payment = (
                razorpay_client.payment.fetch(
                    payment_id
                )
            )

        except Exception as razorpay_fetch_error:

            print(
                "❌ RAZORPAY PAYMENT FETCH ERROR:",
                razorpay_fetch_error
            )

            return jsonify({

                "success": False,

                "message":
                    f"Unable to fetch Razorpay payment: {str(razorpay_fetch_error)}",

            }), 400

        razorpay_payment_status = str(
            razorpay_payment.get(
                "status",
                ""
            )
        ).lower()

        if razorpay_payment_status != "captured":

            return jsonify({

                "success": False,

                "message":
                    f"Razorpay payment status is '{razorpay_payment_status or 'Unknown'}'. Only captured payments can be refunded.",

            }), 400

        # ====================================================
        # DETERMINE REFUND AMOUNT
        #
        # If frontend sends amount, use it.
        # Otherwise use full captured payment.
        # ====================================================

        data = request.get_json(
            silent=True
        ) or {}

        requested_refund_amount = data.get(
            "refund_amount"
        )

        payment_amount_paise = int(
            razorpay_payment.get(
                "amount",
                0
            )
        )

        if requested_refund_amount is not None:

            try:

                refund_amount_rupees = float(
                    requested_refund_amount
                )

            except (
                ValueError,
                TypeError
            ):

                return jsonify({

                    "success": False,

                    "message":
                        "Invalid refund amount.",

                }), 400

            refund_amount_paise = int(
                round(
                    refund_amount_rupees
                    * 100
                )
            )

        else:

            refund_amount_paise = (
                payment_amount_paise
            )

            refund_amount_rupees = (
                refund_amount_paise
                / 100
            )

        if refund_amount_paise <= 0:

            return jsonify({

                "success": False,

                "message":
                    "Refund amount must be greater than zero.",

            }), 400

        if (
            refund_amount_paise
            > payment_amount_paise
        ):

            return jsonify({

                "success": False,

                "message":
                    "Refund amount cannot exceed the captured payment amount.",

            }), 400

        # ====================================================
        # CREATE RAZORPAY REFUND
        # ====================================================

        try:

            refund = (
                razorpay_client.payment.refund(
                    payment_id,
                    {
                        "amount":
                            refund_amount_paise,
                    }
                )
            )

        except Exception as refund_error:

            print(
                "❌ RAZORPAY REFUND ERROR:",
                refund_error
            )

            return jsonify({

                "success": False,

                "message":
                    f"Razorpay refund failed: {str(refund_error)}",

            }), 400

        refund_id = refund.get(
            "id"
        )

        # ====================================================
        # SAVE REFUND
        # ====================================================

        cur.execute(
            """
            UPDATE return_requests

            SET

                refund_status='Refunded',

                return_status='Refunded',

                refund_id=%s,

                refund_amount=%s

            WHERE id=%s
            """,
            (
                refund_id,

                refund_amount_rupees,

                return_id,
            )
        )

        conn.commit()

        print(
            "======================================"
        )

        print(
            "✅ REFUND SUCCESSFUL"
        )

        print(
            "Return ID:",
            return_id
        )

        print(
            "Refund ID:",
            refund_id
        )

        print(
            "Refund Amount:",
            refund_amount_rupees
        )

        print(
            "======================================"
        )

        return jsonify({

            "success": True,

            "message":
                "Refund processed successfully.",

            "return_id":
                return_id,

            "refund_id":
                refund_id,

            "refund_amount":
                refund_amount_rupees,

            "refund_status":
                "Refunded",

            "return_status":
                "Refunded",

        })

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "❌ ADMIN REFUND ERROR:",
            repr(e)
        )

        import traceback

        traceback.print_exc()

        return jsonify({

            "success": False,

            "message":
                f"Failed to process refund: {str(e)}",

            "error":
                str(e),

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# TRACK ORDER
# ============================================================

@app.route(
    "/api/orders/track/<string:order_number>",
    methods=["GET"]
)
def track_order(order_number):

    conn = None
    cur = None

    try:

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        cur.execute(
            """
            SELECT *
            FROM orders

            WHERE order_number=%s
            """,
            (
                order_number.strip().upper(),
            )
        )

        order = cur.fetchone()

        if not order:

            return jsonify({

                "success": False,

                "message":
                    "Order not found",

            }), 404

        datetime_fields = [

            "created_at",

            "confirmed_at",

            "shipped_at",

            "out_for_delivery_at",

            "delivered_at",

            "received_at",

        ]

        for field in datetime_fields:

            if order.get(field):

                order[field] = (
                    order[field]
                    .isoformat()
                )

        order[
            "customer_received"
        ] = bool(
            order.get(
                "customer_received",
                0
            )
        )

        order["items"] = parse_order_items(
            order.get("items")
        )

        order[
            "total_amount"
        ] = float(
            order.get(
                "total_amount"
            ) or 0
        )

        order["total"] = (
            order["total_amount"]
        )

        order.pop(
            "customer_access_token",
            None
        )

        return jsonify({

            "success": True,

            "order": order,

        })

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    print(
        "\n=========================================="
    )

    print(
        "🛍️  SARIKA FASHIONS BACKEND RUNNING"
    )

    print(
        "=========================================="
    )

    print(
        "Admin email configured:",
        bool(ADMIN_EMAIL)
    )

    print(
        "Razorpay configured:",
        bool(razorpay_client)
    )

    print(
        "Database:",
        DB_NAME
    )

    print(
        "==========================================\n"
    )

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )