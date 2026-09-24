
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

# Optional: add another frontend origin through Render environment variables.
# Example: FRONTEND_URL=https://your-other-vercel-deployment.vercel.app
FRONTEND_URL = os.getenv("FRONTEND_URL", "").strip().rstrip("/")

if FRONTEND_URL and FRONTEND_URL not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(FRONTEND_URL)

CORS(
    app,
    supports_credentials=True,
    origins=ALLOWED_ORIGINS,
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

    print(
        f"✅ Razorpay Loaded: {RAZORPAY_KEY_ID}"
    )

else:

    print("❌ Razorpay keys missing")


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DB_HOST = os.getenv(
    "DB_HOST",
    "localhost"
)

DB_PORT = int(
    os.getenv(
        "DB_PORT",
        "3306"
    )
)

DB_USER = os.getenv(
    "DB_USER",
    "root"
)

DB_PASSWORD = os.getenv(
    "DB_PASSWORD",
    ""
)

DB_NAME = os.getenv(
    "DB_NAME",
    "sarika_db"
)


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

        logged_in = session.get(
            "admin_logged_in",
            False
        )

        admin_email = session.get(
            "admin_email"
        )

        print("\n------------------------------------------")
        print("🔐 ADMIN AUTH CHECK")
        print("Path:", request.path)
        print("Method:", request.method)
        print("Logged in:", logged_in)
        print("Admin email:", admin_email)
        print("Session:", dict(session))
        print("------------------------------------------")

        if not logged_in:

            print(
                "❌ ADMIN AUTH FAILED"
            )

            return jsonify({
                "success": False,
                "message": "Admin login required",
                "logged_in": False,
            }), 401

        print(
            "✅ ADMIN AUTH PASSED:",
            admin_email
        )

        return f(*args, **kwargs)

    return decorated_function


# ============================================================
# CUSTOMER ORDER TOKEN
# ============================================================

def get_customer_order_token():

    return session.get(
        "customer_order_token"
    )


def create_customer_order_token():

    token = secrets.token_urlsafe(48)

    session["customer_order_token"] = token

    session.permanent = True

    return token


# ============================================================
# CREATE TABLES
# ============================================================

def create_tables():

    conn = None
    cur = None

    try:

        conn = get_db_connection()

        cur = conn.cursor()

        # ----------------------------------------------------
        # ADMINS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) UNIQUE,
                password VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # ORDERS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (

                id INT AUTO_INCREMENT PRIMARY KEY,

                order_number VARCHAR(50) UNIQUE,

                customer_name VARCHAR(150) NOT NULL,

                customer_email VARCHAR(150),

                customer_phone VARCHAR(30) NOT NULL,

                address TEXT,

                address_line VARCHAR(255) NOT NULL,

                city VARCHAR(100) NOT NULL,

                state VARCHAR(100) NOT NULL,

                pincode VARCHAR(20) NOT NULL,

                items JSON NOT NULL,

                total_amount DECIMAL(10,2) NOT NULL,

                razorpay_order_id VARCHAR(100),

                razorpay_payment_id VARCHAR(100),

                payment_status VARCHAR(30)
                    DEFAULT 'Pending',

                order_status VARCHAR(30)
                    DEFAULT 'Placed',

                customer_access_token VARCHAR(255),

                customer_received TINYINT(1)
                    NOT NULL DEFAULT 0,

                received_at DATETIME NULL,

                confirmed_at DATETIME NULL,

                shipped_at DATETIME NULL,

                out_for_delivery_at DATETIME NULL,

                delivered_at DATETIME NULL,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP

            )
        """)

        # ----------------------------------------------------
        # ADD CUSTOMER TOKEN TO OLD ORDERS
        # ----------------------------------------------------

        cur.execute("""
            SHOW COLUMNS FROM orders
            LIKE 'customer_access_token'
        """)

        token_column = cur.fetchone()

        if not token_column:

            print(
                "➕ Adding customer_access_token column..."
            )

            cur.execute("""
                ALTER TABLE orders
                ADD COLUMN customer_access_token
                VARCHAR(255)
            """)

            print(
                "✅ customer_access_token added"
            )

        # ----------------------------------------------------
        # ADD CUSTOMER RECEIVED TO OLD ORDERS
        # ----------------------------------------------------

        cur.execute("""
            SHOW COLUMNS FROM orders
            LIKE 'customer_received'
        """)

        received_column = cur.fetchone()

        if not received_column:

            print(
                "➕ Adding customer_received column..."
            )

            cur.execute("""
                ALTER TABLE orders
                ADD COLUMN customer_received
                TINYINT(1) NOT NULL DEFAULT 0
            """)

            print(
                "✅ customer_received added"
            )

        # ----------------------------------------------------
        # ADD RECEIVED AT TO OLD ORDERS
        # ----------------------------------------------------

        cur.execute("""
            SHOW COLUMNS FROM orders
            LIKE 'received_at'
        """)

        received_at_column = cur.fetchone()

        if not received_at_column:

            print(
                "➕ Adding received_at column..."
            )

            cur.execute("""
                ALTER TABLE orders
                ADD COLUMN received_at DATETIME NULL
            """)

            print(
                "✅ received_at added"
            )

        # ----------------------------------------------------
        # ADD CONFIRMED AT
        # ----------------------------------------------------

        cur.execute("""
            SHOW COLUMNS FROM orders
            LIKE 'confirmed_at'
        """)

        confirmed_at_column = cur.fetchone()

        if not confirmed_at_column:

            print(
                "➕ Adding confirmed_at column..."
            )

            cur.execute("""
                ALTER TABLE orders
                ADD COLUMN confirmed_at DATETIME NULL
            """)

            print(
                "✅ confirmed_at added"
            )

        # ----------------------------------------------------
        # ADD SHIPPED AT
        # ----------------------------------------------------

        cur.execute("""
            SHOW COLUMNS FROM orders
            LIKE 'shipped_at'
        """)

        shipped_at_column = cur.fetchone()

        if not shipped_at_column:

            print(
                "➕ Adding shipped_at column..."
            )

            cur.execute("""
                ALTER TABLE orders
                ADD COLUMN shipped_at DATETIME NULL
            """)

            print(
                "✅ shipped_at added"
            )

        # ----------------------------------------------------
        # ADD OUT FOR DELIVERY AT
        # ----------------------------------------------------

        cur.execute("""
            SHOW COLUMNS FROM orders
            LIKE 'out_for_delivery_at'
        """)

        out_for_delivery_column = cur.fetchone()

        if not out_for_delivery_column:

            print(
                "➕ Adding out_for_delivery_at column..."
            )

            cur.execute("""
                ALTER TABLE orders
                ADD COLUMN out_for_delivery_at DATETIME NULL
            """)

            print(
                "✅ out_for_delivery_at added"
            )

        # ----------------------------------------------------
        # ADD DELIVERED AT
        # ----------------------------------------------------

        cur.execute("""
            SHOW COLUMNS FROM orders
            LIKE 'delivered_at'
        """)

        delivered_at_column = cur.fetchone()

        if not delivered_at_column:

            print(
                "➕ Adding delivered_at column..."
            )

            cur.execute("""
                ALTER TABLE orders
                ADD COLUMN delivered_at DATETIME NULL
            """)

            print(
                "✅ delivered_at added"
            )

        # ----------------------------------------------------
        # REVIEWS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS reviews (

                id INT AUTO_INCREMENT PRIMARY KEY,

                product_id INT NOT NULL,

                customer_name VARCHAR(100) NOT NULL,

                rating INT NOT NULL,

                review_text TEXT NOT NULL,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP

            )
        """)

        # ----------------------------------------------------
        # RETURN REQUESTS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS return_requests (

                id INT AUTO_INCREMENT PRIMARY KEY,

                order_id INT NOT NULL,

                order_number VARCHAR(50) NOT NULL,

                product_id INT,

                product_name VARCHAR(255) NOT NULL,

                quantity INT DEFAULT 1,

                customer_access_token VARCHAR(255) NOT NULL,

                reason VARCHAR(150) NOT NULL,

                description TEXT,

                return_status VARCHAR(50)
                    DEFAULT 'Return Requested',

                refund_status VARCHAR(50)
                    DEFAULT 'Not Initiated',

                admin_note TEXT,

                requested_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                updated_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,

                INDEX idx_return_order_id (order_id),

                INDEX idx_return_customer_token (
                    customer_access_token
                )

            )
        """)

        conn.commit()

        print("✅ Tables ready")
        print("✅ Return requests table ready")

    except Exception as e:

        print(
            "❌ Table error:",
            e
        )

        if conn:
            conn.rollback()

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({
        "success": True,
        "message": "Sarika Fashions backend running!",
        "razorpay": bool(razorpay_client),
    })


# ============================================================
# ADMIN LOGIN
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
        data.get(
            "email",
            ""
        )
    ).strip()

    password = str(
        data.get(
            "password",
            ""
        )
    )

    print("\n==========================================")
    print("🔐 ADMIN LOGIN REQUEST")
    print("Email received:", email)
    print("Configured admin:", ADMIN_EMAIL)
    print("==========================================")


    if not ADMIN_EMAIL:

        return jsonify({
            "success": False,
            "message":
                "Admin email is not configured in backend .env",
        }), 500


    if not ADMIN_PASSWORD:

        return jsonify({
            "success": False,
            "message":
                "Admin password is not configured in backend .env",
        }), 500


    if (
        email.lower() != ADMIN_EMAIL.lower()
        or password != ADMIN_PASSWORD
    ):

        print(
            "❌ INVALID ADMIN LOGIN"
        )

        return jsonify({
            "success": False,
            "message":
                "Invalid email or password",
        }), 401


    session.clear()

    session["admin_logged_in"] = True
    session["admin_email"] = ADMIN_EMAIL

    session.permanent = True


    print(
        "✅ ADMIN LOGIN SUCCESS:",
        ADMIN_EMAIL
    )

    print(
        "✅ SESSION CREATED:",
        dict(session)
    )

    return jsonify({

        "success": True,

        "message":
            "Admin login successful",

        "admin": {
            "email": ADMIN_EMAIL
        },

    })


# ============================================================
# ADMIN ME
# ============================================================

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


    print("\n==========================================")
    print("🔎 ADMIN SESSION CHECK")
    print("Logged in:", logged_in)
    print("Admin email:", admin_email)
    print("Session:", dict(session))
    print("==========================================")


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

            "email":
                admin_email

        },

    })


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route(
    "/api/admin/logout",
    methods=["POST"]
)
def admin_logout():

    print(
        "\n🚪 ADMIN LOGOUT:",
        session.get(
            "admin_email"
        )
    )

    session.clear()

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
                    ROUND(
                        AVG(r.rating),
                        1
                    ),
                    0
                ) AS rating,

                COUNT(r.id) AS reviews

            FROM products p

            LEFT JOIN reviews r
                ON p.id = r.product_id

            GROUP BY
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
                p.image4

            ORDER BY
                p.created_at DESC
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

            "products": products

        })


    except Error as e:

        print(
            "❌ PRODUCTS ERROR:",
            e
        )

        return jsonify({

            "success": False,

            "error": str(e)

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# ADD PRODUCT - ADMIN ONLY
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


        if not name:

            return jsonify({
                "success": False,
                "message":
                    "Product name is required"
            }), 400


        if not category:

            return jsonify({
                "success": False,
                "message":
                    "Category is required"
            }), 400


        try:
            price = float(price)
        except (ValueError, TypeError):

            return jsonify({
                "success": False,
                "message":
                    "Invalid price"
            }), 400


        try:
            stock = int(stock)
        except (ValueError, TypeError):

            return jsonify({
                "success": False,
                "message":
                    "Invalid stock quantity"
            }), 400


        if old_price:

            try:
                old_price = float(old_price)
            except (ValueError, TypeError):
                old_price = None

        else:
            old_price = None


        image_urls = {}


        for field_name in [
            "image",
            "image2",
            "image3",
            "image4"
        ]:

            file = request.files.get(
                field_name
            )

            if file and file.filename:

                upload_result = (
                    cloudinary.uploader.upload(
                        file,
                        folder="sarika-fashions/products"
                    )
                )

                image_url = (
                    upload_result.get(
                        "secure_url"
                    )
                )

                if image_url:

                    image_urls[
                        field_name
                    ] = image_url


        if not image_urls.get("image"):

            return jsonify({
                "success": False,
                "message":
                    "Main product image is required"
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
            image_urls.get("image4")

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

        print(
            "❌ ADD PRODUCT ERROR:",
            e
        )

        return jsonify({

            "success": False,

            "message":
                "Failed to add product",

            "error":
                str(e)

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# UPDATE PRODUCT - ADMIN ONLY
# ============================================================

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


        existing_product = cur.fetchone()


        if not existing_product:

            return jsonify({
                "success": False,
                "message":
                    "Product not found"
            }), 404


        name = request.form.get(
            "name",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        price_value = request.form.get(
            "price",
            ""
        ).strip()

        old_price_value = request.form.get(
            "old_price",
            ""
        ).strip()

        stock_value = request.form.get(
            "stock",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        fabric = request.form.get(
            "fabric",
            ""
        ).strip()

        color = request.form.get(
            "color",
            ""
        ).strip()

        is_featured = (
            request.form.get(
                "isFeatured",
                "false"
            ).lower() == "true"
        )

        is_active = (
            request.form.get(
                "isActive",
                "true"
            ).lower() == "true"
        )


        if not name:

            return jsonify({
                "success": False,
                "message":
                    "Product name is required"
            }), 400


        if not category:

            return jsonify({
                "success": False,
                "message":
                    "Category is required"
            }), 400


        try:
            price = float(price_value)
        except (ValueError, TypeError):

            return jsonify({
                "success": False,
                "message":
                    "Invalid price"
            }), 400


        if price <= 0:

            return jsonify({
                "success": False,
                "message":
                    "Price must be greater than 0"
            }), 400


        try:
            stock = int(stock_value)
        except (ValueError, TypeError):

            return jsonify({
                "success": False,
                "message":
                    "Invalid stock quantity"
            }), 400


        if stock < 0:

            return jsonify({
                "success": False,
                "message":
                    "Stock cannot be negative"
            }), 400


        old_price = None

        if old_price_value:

            try:
                old_price = float(
                    old_price_value
                )
            except (ValueError, TypeError):

                return jsonify({
                    "success": False,
                    "message":
                        "Invalid old price"
                }), 400


        image_urls = {
            "image":
                existing_product.get("image"),
            "image2":
                existing_product.get("image2"),
            "image3":
                existing_product.get("image3"),
            "image4":
                existing_product.get("image4"),
        }


        for field_name in [
            "image",
            "image2",
            "image3",
            "image4"
        ]:

            file = request.files.get(
                field_name
            )

            if file and file.filename:

                upload_result = (
                    cloudinary.uploader.upload(
                        file,
                        folder="sarika-fashions/products"
                    )
                )

                new_url = (
                    upload_result.get(
                        "secure_url"
                    )
                )

                if not new_url:

                    return jsonify({
                        "success": False,
                        "message":
                            f"Cloudinary upload failed for {field_name}"
                    }), 500

                image_urls[
                    field_name
                ] = new_url


        cur.execute(
            "SHOW COLUMNS FROM products"
        )

        column_rows = cur.fetchall()

        product_columns = {
            row["Field"]
            for row in column_rows
        }


        update_fields = [

            "name=%s",
            "category=%s",
            "price=%s",
            "old_price=%s",
            "description=%s",
            "stock=%s",
            "image=%s",
            "image2=%s",
            "image3=%s",
            "image4=%s",

        ]


        values = [

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

        ]


        if "fabric" in product_columns:

            update_fields.append(
                "fabric=%s"
            )

            values.append(
                fabric
            )


        if "color" in product_columns:

            update_fields.append(
                "color=%s"
            )

            values.append(
                color
            )


        if "is_featured" in product_columns:

            update_fields.append(
                "is_featured=%s"
            )

            values.append(
                1 if is_featured else 0
            )


        if "is_active" in product_columns:

            update_fields.append(
                "is_active=%s"
            )

            values.append(
                1 if is_active else 0
            )


        values.append(
            product_id
        )


        query = f"""
            UPDATE products
            SET {", ".join(update_fields)}
            WHERE id=%s
        """


        cur.execute(
            query,
            tuple(values)
        )


        conn.commit()


        return jsonify({

            "success": True,

            "message":
                "Product updated successfully",

        })


    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "❌ UPDATE PRODUCT ERROR:",
            e
        )

        return jsonify({

            "success": False,

            "message":
                "Failed to update product",

            "error":
                str(e),

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# DELETE PRODUCT - ADMIN ONLY
# ============================================================

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

            conn.rollback()

            return jsonify({
                "success": False,
                "message":
                    "Product not found"
            }), 404


        conn.commit()


        return jsonify({

            "success": True,

            "message":
                "Product deleted successfully"

        })


    except Error as e:

        if conn:
            conn.rollback()

        return jsonify({

            "success": False,

            "message":
                "Failed to delete product",

            "error":
                str(e)

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# SINGLE PRODUCT
# ============================================================

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
                    "Product not found"
            }), 404


        if product.get("created_at"):

            product["created_at"] = (
                product["created_at"].isoformat()
            )


        return jsonify({

            "success": True,

            "product":
                product

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

        "key":
            RAZORPAY_KEY_ID,

        "key_id":
            RAZORPAY_KEY_ID,

    })


# ============================================================
# CREATE RAZORPAY ORDER
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


        data = (
            request.get_json(
                silent=True
            )
            or {}
        )


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


        order = (
            razorpay_client.order.create({

                "amount":
                    amount_paise,

                "currency":
                    "INR",

                "receipt":
                    f"receipt_{int(datetime.now().timestamp())}",

                "payment_capture":
                    1,

            })
        )


        return jsonify({

            "success":
                True,

            "order":
                order,

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
            "❌ RAZORPAY ERROR:",
            e
        )

        return jsonify({

            "success":
                False,

            "error":
                str(e),

        }), 500


# ============================================================
# VERIFY PAYMENT
# ============================================================

@app.route(
    "/api/payment/verify",
    methods=["POST"]
)
def verify_payment():

    try:

        if not razorpay_client:

            return jsonify({
                "success":
                    False,
                "error":
                    "Razorpay is not configured",
            }), 500


        data = (
            request.get_json(
                silent=True
            )
            or {}
        )


        razorpay_client.utility.verify_payment_signature({

            "razorpay_order_id":
                data[
                    "razorpay_order_id"
                ],

            "razorpay_payment_id":
                data[
                    "razorpay_payment_id"
                ],

            "razorpay_signature":
                data[
                    "razorpay_signature"
                ],

        })


        return jsonify({

            "success":
                True,

            "message":
                "Payment verified successfully",

        })


    except Exception as e:

        return jsonify({

            "success":
                False,

            "error":
                str(e),

        }), 400


# ============================================================
# CREATE CUSTOMER ORDER
# ============================================================

@app.route(
    "/api/orders",
    methods=["POST"]
)
def create_order():

    conn = None
    cur = None

    try:

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )


        print("\n==========================================")
        print("🛍️ CREATE CUSTOMER ORDER")
        print("Customer:", data.get("customer_name"))
        print("Phone:", data.get("customer_phone"))
        print("Total:", data.get("total_amount"))
        print("==========================================")


        customer_token = (
            get_customer_order_token()
        )

        if not customer_token:

            customer_token = (
                create_customer_order_token()
            )


        conn = get_db_connection()

        cur = conn.cursor()


        cur.execute("""
            SELECT order_number
            FROM orders
            ORDER BY id DESC
            LIMIT 1
        """)


        last = cur.fetchone()

        next_num = 1


        if last and last[0]:

            try:

                next_num = (
                    int(
                        str(
                            last[0]
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
                ""
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

        # ----------------------------------------------------
        # NORMALIZE NEW ORDERS
        # ----------------------------------------------------

        if not order_status:
            order_status = "Placed"

        if str(order_status).lower() == "pending":
            order_status = "Placed"


        if not customer_name:

            return jsonify({
                "success": False,
                "message":
                    "Customer name is required"
            }), 400


        if not customer_phone:

            return jsonify({
                "success": False,
                "message":
                    "Customer phone is required"
            }), 400


        if not city:

            return jsonify({
                "success": False,
                "message":
                    "City is required"
            }), 400


        if not state:

            return jsonify({
                "success": False,
                "message":
                    "State is required"
            }), 400


        if not pincode:

            return jsonify({
                "success": False,
                "message":
                    "Pincode is required"
            }), 400


        if not items:

            return jsonify({
                "success": False,
                "message":
                    "Order must contain at least one item"
            }), 400


        if total_amount <= 0:

            return jsonify({
                "success": False,
                "message":
                    "Invalid order amount"
            }), 400


        cur.execute("""
            INSERT INTO orders (

                order_number,
                customer_name,
                customer_email,
                customer_phone,
                address,
                address_line,
                city,
                state,
                pincode,
                items,
                total_amount,
                razorpay_order_id,
                razorpay_payment_id,
                payment_status,
                order_status,
                customer_access_token

            )

            VALUES (

                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s

            )
        """, (

            order_number,
            customer_name,
            customer_email,
            customer_phone,
            address,
            address_line,
            city,
            state,
            pincode,
            json.dumps(items),
            total_amount,
            razorpay_order_id,
            razorpay_payment_id,
            payment_status,
            order_status,
            customer_token,

        ))


        order_id = cur.lastrowid

        conn.commit()


        session["customer_order_token"] = (
            customer_token
        )

        session.permanent = True


        print(
            "✅ ORDER CREATED:",
            order_number
        )


        return jsonify({

            "success":
                True,

            "message":
                "Order created successfully",

            "order_id":
                order_id,

            "order_number":
                order_number,

        }), 201


    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "❌ ORDER CREATE ERROR:",
            e
        )

        import traceback

        traceback.print_exc()


        return jsonify({

            "success":
                False,

            "error":
                str(e),

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# MY ORDERS - CUSTOMER ONLY
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


        if not customer_token:

            return jsonify({

                "success":
                    True,

                "authenticated":
                    False,

                "orders":
                    [],

                "message":
                    "No customer order session found",

            })


        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )


        cur.execute(
            """
            SELECT *
            FROM orders
            WHERE customer_access_token=%s
            ORDER BY created_at DESC
            """,
            (customer_token,)
        )


        orders = cur.fetchall()


        # ----------------------------------------------------
        # LOAD RETURN REQUESTS
        # ----------------------------------------------------

        order_ids = [
            order["id"]
            for order in orders
        ]


        return_requests_by_order = {}


        if order_ids:

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
                    admin_note,
                    requested_at,
                    updated_at
                FROM return_requests
                WHERE order_id IN ({placeholders})
                ORDER BY requested_at DESC
                """,
                tuple(order_ids)
            )


            return_rows = cur.fetchall()


            for return_item in return_rows:

                if return_item.get(
                    "requested_at"
                ):

                    return_item[
                        "requested_at"
                    ] = (
                        return_item[
                            "requested_at"
                        ].isoformat()
                    )


                if return_item.get(
                    "updated_at"
                ):

                    return_item[
                        "updated_at"
                    ] = (
                        return_item[
                            "updated_at"
                        ].isoformat()
                    )


                order_id = (
                    return_item["order_id"]
                )


                return_requests_by_order.setdefault(
                    order_id,
                    []
                ).append(
                    return_item
                )


        # ----------------------------------------------------
        # FORMAT ORDERS
        # ----------------------------------------------------

        for order in orders:

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


            if isinstance(
                order.get("items"),
                str
            ):

                try:

                    order[
                        "items"
                    ] = json.loads(
                        order[
                            "items"
                        ]
                    )

                except Exception:

                    order[
                        "items"
                    ] = []


            order[
                "total_amount"
            ] = float(
                order.get(
                    "total_amount"
                ) or 0
            )


            order[
                "total"
            ] = order[
                "total_amount"
            ]


            order[
                "return_requests"
            ] = return_requests_by_order.get(
                order["id"],
                []
            )


            order.pop(
                "customer_access_token",
                None
            )


        print(
            f"✅ MY ORDERS: {len(orders)} orders found"
        )


        return jsonify({

            "success":
                True,

            "authenticated":
                True,

            "orders":
                orders,

        })


    except Exception as e:

        print(
            "❌ MY ORDERS ERROR:",
            e
        )

        import traceback

        traceback.print_exc()


        return jsonify({

            "success":
                False,

            "message":
                "Failed to fetch your orders",

            "error":
                str(e),

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# CUSTOMER - CONFIRM ORDER RECEIVED
#
# PRIMARY ENDPOINT
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

        # ----------------------------------------------------
        # GET CUSTOMER'S ORDER
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                id,
                order_number,
                order_status,
                customer_received,
                received_at
            FROM orders
            WHERE id=%s
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
            )
            or ""
        )

        # ----------------------------------------------------
        # ALREADY RECEIVED
        # ----------------------------------------------------

        if int(
            order.get(
                "customer_received"
            ) or 0
        ) == 1:

            received_at = None

            if order.get(
                "received_at"
            ):

                received_at = (
                    order["received_at"]
                    .isoformat()
                )

            return jsonify({

                "success": True,

                "message":
                    "Order was already confirmed as received.",

                "order": {

                    "id":
                        order["id"],

                    "order_number":
                        order["order_number"],

                    "order_status":
                        order["order_status"],

                    "customer_received":
                        True,

                    "received_at":
                        received_at,

                },

            })

        # ----------------------------------------------------
        # ONLY DELIVERED ORDERS CAN BE CONFIRMED
        # ----------------------------------------------------

        if current_status != "Delivered":

            return jsonify({

                "success": False,

                "message":
                    "You can confirm receipt only after the order is marked Delivered.",

            }), 400

        # ----------------------------------------------------
        # MARK RECEIVED + CLOSE ORDER
        # ----------------------------------------------------

        cur.execute(
            """
            UPDATE orders
            SET
                customer_received=1,
                received_at=NOW(),
                order_status='Closed'
            WHERE id=%s
            AND customer_access_token=%s
            """,
            (
                order_id,
                customer_token,
            )
        )

        conn.commit()

        # ----------------------------------------------------
        # FETCH UPDATED ORDER
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                id,
                order_number,
                order_status,
                customer_received,
                received_at
            FROM orders
            WHERE id=%s
            AND customer_access_token=%s
            """,
            (
                order_id,
                customer_token,
            )
        )

        updated_order = cur.fetchone()

        if updated_order:

            if updated_order.get(
                "received_at"
            ):

                updated_order[
                    "received_at"
                ] = (
                    updated_order[
                        "received_at"
                    ].isoformat()
                )

            updated_order[
                "customer_received"
            ] = bool(
                updated_order.get(
                    "customer_received",
                    0
                )
            )

        print(
            "✅ CUSTOMER CONFIRMED RECEIPT:",
            order_id
        )

        print(
            "🔒 ORDER CLOSED:",
            order_id
        )

        return jsonify({

            "success": True,

            "message":
                "Order received successfully. Order is now closed.",

            "order":
                updated_order,

        })

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "❌ CUSTOMER RECEIVE ERROR:",
            e
        )

        import traceback

        traceback.print_exc()

        return jsonify({

            "success": False,

            "message":
                "Failed to confirm order receipt.",

            "error":
                str(e),

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# CUSTOMER - OLD RECEIVED ENDPOINT
#
# KEPT FOR FRONTEND COMPATIBILITY
# ============================================================

@app.route(
    "/api/orders/<int:order_id>/received",
    methods=["PUT", "POST"]
)
def confirm_order_received_legacy(order_id):

    return customer_confirm_received(
        order_id
    )


# ============================================================
# CREATE RETURN REQUEST - CUSTOMER
# ============================================================

@app.route(
    "/api/returns",
    methods=["POST"]
)
def create_return_request():

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
                    "Customer order session not found. Please place an order first."

            }), 401


        data = (
            request.get_json(
                silent=True
            )
            or {}
        )


        order_id = data.get(
            "order_id"
        )

        order_number = str(
            data.get(
                "order_number",
                ""
            )
        ).strip().upper()

        product_id = data.get(
            "product_id"
        )

        product_name = str(
            data.get(
                "product_name",
                ""
            )
        ).strip()

        quantity = int(
            data.get(
                "quantity",
                1
            ) or 1
        )

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


        if not order_id:

            return jsonify({
                "success": False,
                "message":
                    "Order ID is required"
            }), 400


        if not product_name:

            return jsonify({
                "success": False,
                "message":
                    "Product name is required"
            }), 400


        if not reason:

            return jsonify({
                "success": False,
                "message":
                    "Return reason is required"
            }), 400


        if quantity < 1:

            quantity = 1


        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )


        # ----------------------------------------------------
        # VERIFY ORDER BELONGS TO CUSTOMER
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT *
            FROM orders
            WHERE id=%s
            AND customer_access_token=%s
            """,
            (
                order_id,
                customer_token
            )
        )


        order = cur.fetchone()


        if not order:

            return jsonify({

                "success": False,

                "message":
                    "Order not found or you do not have access to this order"

            }), 404


        # ----------------------------------------------------
        # RETURN ONLY AFTER DELIVERED
        # ----------------------------------------------------

        order_status = str(
            order.get(
                "order_status",
                ""
            )
        ).strip().lower()


        if (
            "deliver" not in order_status
            or "out" in order_status
        ):

            return jsonify({

                "success": False,

                "message":
                    "Returns can only be requested after the order is delivered"

            }), 400


        # ----------------------------------------------------
        # PARSE ORDER ITEMS
        # ----------------------------------------------------

        order_items = order.get(
            "items"
        )


        if isinstance(
            order_items,
            str
        ):

            try:

                order_items = json.loads(
                    order_items
                )

            except Exception:

                order_items = []


        if not isinstance(
            order_items,
            list
        ):

            order_items = []


        # ----------------------------------------------------
        # VERIFY PRODUCT EXISTS IN ORDER
        # ----------------------------------------------------

        matched_item = None


        for item in order_items:

            item_product_id = (
                item.get("product_id")
                if isinstance(item, dict)
                else None
            )

            if item_product_id is None and isinstance(item, dict):

                item_product_id = item.get(
                    "id"
                )


            if (
                product_id is not None
                and str(item_product_id)
                == str(product_id)
            ):

                matched_item = item
                break


            item_name = (
                item.get("name", "")
                if isinstance(item, dict)
                else ""
            )


            if (
                not matched_item
                and product_id is None
                and str(item_name).strip().lower()
                == product_name.lower()
            ):

                matched_item = item
                break


        if not matched_item:

            return jsonify({

                "success": False,

                "message":
                    "Selected product was not found in this order"

            }), 400


        trusted_product_id = (
            matched_item.get("product_id")
            if isinstance(matched_item, dict)
            else None
        )


        if trusted_product_id is None and isinstance(
            matched_item,
            dict
        ):

            trusted_product_id = (
                matched_item.get("id")
            )


        trusted_product_name = (
            matched_item.get("name")
            if isinstance(matched_item, dict)
            else product_name
        )


        # ----------------------------------------------------
        # CHECK EXISTING RETURN
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT *
            FROM return_requests
            WHERE order_id=%s
            AND customer_access_token=%s
            AND product_id=%s
            AND return_status NOT IN (
                'Rejected',
                'Cancelled'
            )
            LIMIT 1
            """,
            (
                order["id"],
                customer_token,
                trusted_product_id
            )
        )


        existing_return = cur.fetchone()


        if existing_return:

            return jsonify({

                "success": False,

                "message":
                    "A return request already exists for this product"

            }), 409


        # ----------------------------------------------------
        # INSERT RETURN REQUEST
        # ----------------------------------------------------

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

                %s,%s,%s,%s,%s,
                %s,%s,%s,
                'Return Requested',
                'Not Initiated'

            )
            """,
            (
                order["id"],
                order.get(
                    "order_number"
                ) or order_number,
                trusted_product_id,
                trusted_product_name,
                quantity,
                customer_token,
                reason,
                description,
            )
        )


        return_id = cur.lastrowid

        conn.commit()


        print(
            "✅ RETURN REQUEST CREATED:",
            return_id
        )


        return jsonify({

            "success": True,

            "message":
                "Return request submitted successfully",

            "return_id":
                return_id,

        }), 201


    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "❌ CREATE RETURN ERROR:",
            e
        )

        import traceback

        traceback.print_exc()


        return jsonify({

            "success": False,

            "message":
                "Failed to create return request",

            "error":
                str(e),

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# MY RETURNS - CUSTOMER
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


        if not customer_token:

            return jsonify({

                "success": True,

                "authenticated": False,

                "returns": [],

            })


        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )


        cur.execute(
            """
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
                admin_note,
                requested_at,
                updated_at
            FROM return_requests
            WHERE customer_access_token=%s
            ORDER BY requested_at DESC
            """,
            (
                customer_token,
            )
        )


        returns = cur.fetchall()


        for item in returns:

            if item.get(
                "requested_at"
            ):

                item[
                    "requested_at"
                ] = (
                    item[
                        "requested_at"
                    ].isoformat()
                )


            if item.get(
                "updated_at"
            ):

                item[
                    "updated_at"
                ] = (
                    item[
                        "updated_at"
                    ].isoformat()
                )


        return jsonify({

            "success":
                True,

            "authenticated":
                True,

            "returns":
                returns,

        })


    except Exception as e:

        print(
            "❌ MY RETURNS ERROR:",
            e
        )


        return jsonify({

            "success": False,

            "message":
                "Failed to fetch return requests",

            "error":
                str(e),

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# SINGLE CUSTOMER RETURN
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


        if not customer_token:

            return jsonify({

                "success": False,

                "message":
                    "Customer order session not found"

            }), 401


        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )


        cur.execute(
            """
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
                admin_note,
                requested_at,
                updated_at
            FROM return_requests
            WHERE id=%s
            AND customer_access_token=%s
            """,
            (
                return_id,
                customer_token
            )
        )


        return_item = cur.fetchone()


        if not return_item:

            return jsonify({

                "success": False,

                "message":
                    "Return request not found"

            }), 404


        if return_item.get(
            "requested_at"
        ):

            return_item[
                "requested_at"
            ] = (
                return_item[
                    "requested_at"
                ].isoformat()
            )


        if return_item.get(
            "updated_at"
        ):

            return_item[
                "updated_at"
            ] = (
                return_item[
                    "updated_at"
                ].isoformat()
            )


        return jsonify({

            "success":
                True,

            "return":
                return_item,

        })


    except Exception as e:

        print(
            "❌ GET RETURN ERROR:",
            e
        )


        return jsonify({

            "success": False,

            "message":
                "Failed to fetch return request",

            "error":
                str(e),

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# GET ALL ORDERS - ADMIN ONLY
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

        print(
            "✅ ADMIN FETCHING ORDERS:",
            session.get(
                "admin_email"
            )
        )


        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )


        cur.execute("""
            SELECT *
            FROM orders
            ORDER BY created_at DESC
        """)


        orders = cur.fetchall()


        for order in orders:

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


            if isinstance(
                order.get("items"),
                str
            ):

                try:

                    order[
                        "items"
                    ] = json.loads(
                        order[
                            "items"
                        ]
                    )

                except Exception:

                    order[
                        "items"
                    ] = []


            order[
                "total_amount"
            ] = float(
                order.get(
                    "total_amount"
                ) or 0
            )


            order[
                "total"
            ] = order[
                "total_amount"
            ]


            order.pop(
                "customer_access_token",
                None
            )


        print(
            f"✅ {len(orders)} orders found"
        )


        return jsonify({

            "success":
                True,

            "orders":
                orders,

        })


    except Exception as e:

        print(
            "❌ GET ORDERS ERROR:",
            e
        )


        return jsonify({

            "success":
                False,

            "message":
                "Failed to fetch orders",

            "error":
                str(e),

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# ADMIN - UPDATE ORDER STATUS
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

        # ----------------------------------------------------
        # SUPPORT BOTH:
        #
        # { "order_status": "Shipped" }
        #
        # AND:
        #
        # { "status": "Shipped" }
        # ----------------------------------------------------

        requested_status = str(
            data.get(
                "order_status",
                data.get(
                    "status",
                    ""
                )
            )
        ).strip()

        # ----------------------------------------------------
        # ALLOWED STATUSES
        # ----------------------------------------------------

        allowed_statuses = [
            "Placed",
            "Confirmed",
            "Shipped",
            "Out for Delivery",
            "Delivered",
            "Cancelled",
        ]

        status_map = {
            status.lower(): status
            for status in allowed_statuses
        }

        new_status = status_map.get(
            requested_status.lower()
        )

        if not new_status:

            return jsonify({

                "success": False,

                "message":
                    "Invalid order status.",

                "allowed_statuses":
                    allowed_statuses,

            }), 400

        # ----------------------------------------------------
        # DATABASE
        # ----------------------------------------------------

        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )

        # ----------------------------------------------------
        # GET CURRENT ORDER
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                id,
                order_number,
                order_status,
                customer_received,
                received_at
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

        current_status = (
            order.get(
                "order_status"
            )
            or "Placed"
        )

        # ----------------------------------------------------
        # CLOSED ORDER CANNOT BE CHANGED
        # ----------------------------------------------------

        if (
            current_status == "Closed"
            or int(
                order.get(
                    "customer_received"
                ) or 0
            ) == 1
        ):

            return jsonify({

                "success": False,

                "message":
                    "This order is already closed because the customer confirmed receipt.",

            }), 400

        # ----------------------------------------------------
        # VALID STATUS FLOW
        # ----------------------------------------------------

        status_order = [
            "Placed",
            "Confirmed",
            "Shipped",
            "Out for Delivery",
            "Delivered",
        ]

        # ----------------------------------------------------
        # PREVENT BACKWARD MOVEMENT
        # ----------------------------------------------------

        if (
            new_status != "Cancelled"
            and current_status in status_order
            and new_status in status_order
        ):

            current_index = (
                status_order.index(
                    current_status
                )
            )

            new_index = (
                status_order.index(
                    new_status
                )
            )

            # Same status is allowed.
            if new_index < current_index:

                return jsonify({

                    "success": False,

                    "message":
                        f"Order is already at '{current_status}'. "
                        f"It cannot be moved backward to '{new_status}'.",

                }), 400

        # ----------------------------------------------------
        # UPDATE STATUS
        # ----------------------------------------------------

        if new_status == "Confirmed":

            cur.execute(
                """
                UPDATE orders
                SET
                    order_status=%s,
                    confirmed_at=NOW()
                WHERE id=%s
                """,
                (
                    new_status,
                    order_id,
                )
            )

        elif new_status == "Shipped":

            cur.execute(
                """
                UPDATE orders
                SET
                    order_status=%s,
                    shipped_at=NOW()
                WHERE id=%s
                """,
                (
                    new_status,
                    order_id,
                )
            )

        elif new_status == "Out for Delivery":

            cur.execute(
                """
                UPDATE orders
                SET
                    order_status=%s,
                    out_for_delivery_at=NOW()
                WHERE id=%s
                """,
                (
                    new_status,
                    order_id,
                )
            )

        elif new_status == "Delivered":

            cur.execute(
                """
                UPDATE orders
                SET
                    order_status=%s,
                    delivered_at=NOW()
                WHERE id=%s
                """,
                (
                    new_status,
                    order_id,
                )
            )

        elif new_status == "Cancelled":

            cur.execute(
                """
                UPDATE orders
                SET
                    order_status=%s
                WHERE id=%s
                """,
                (
                    new_status,
                    order_id,
                )
            )

        else:

            # Placed
            cur.execute(
                """
                UPDATE orders
                SET
                    order_status=%s
                WHERE id=%s
                """,
                (
                    new_status,
                    order_id,
                )
            )

        conn.commit()

        # ----------------------------------------------------
        # FETCH UPDATED ORDER
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT *
            FROM orders
            WHERE id=%s
            """,
            (order_id,)
        )

        updated_order = cur.fetchone()

        if updated_order:

            datetime_fields = [
                "created_at",
                "confirmed_at",
                "shipped_at",
                "out_for_delivery_at",
                "delivered_at",
                "received_at",
            ]

            for field in datetime_fields:

                if updated_order.get(field):

                    updated_order[field] = (
                        updated_order[field]
                        .isoformat()
                    )

            # ------------------------------------------------
            # FORMAT ITEMS
            # ------------------------------------------------

            if isinstance(
                updated_order.get("items"),
                str
            ):

                try:

                    updated_order["items"] = (
                        json.loads(
                            updated_order["items"]
                        )
                    )

                except Exception:

                    updated_order["items"] = []

            # ------------------------------------------------
            # FORMAT TOTAL
            # ------------------------------------------------

            updated_order["total_amount"] = float(
                updated_order.get(
                    "total_amount"
                ) or 0
            )

            updated_order["total"] = (
                updated_order["total_amount"]
            )

            # ------------------------------------------------
            # FORMAT RECEIVED
            # ------------------------------------------------

            updated_order[
                "customer_received"
            ] = bool(
                updated_order.get(
                    "customer_received",
                    0
                )
            )

            # ------------------------------------------------
            # REMOVE PRIVATE TOKEN
            # ------------------------------------------------

            updated_order.pop(
                "customer_access_token",
                None
            )

        print(
            "✅ ORDER STATUS UPDATED:",
            order_id,
            current_status,
            "→",
            new_status
        )

        return jsonify({

            "success": True,

            "message":
                f"Order status changed to {new_status}.",

            "order":
                updated_order,

        })

    except Exception as e:

        if conn:
            conn.rollback()

        print(
            "❌ UPDATE ORDER STATUS ERROR:",
            e
        )

        import traceback

        traceback.print_exc()

        return jsonify({

            "success": False,

            "message":
                "Failed to update order status.",

            "error":
                str(e),

        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# ADMIN - GET ALL RETURN REQUESTS
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


        cur.execute("""
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
                admin_note,
                requested_at,
                updated_at
            FROM return_requests
            ORDER BY requested_at DESC
        """)


        returns = cur.fetchall()


        for item in returns:

            if item.get(
                "requested_at"
            ):

                item[
                    "requested_at"
                ] = (
                    item[
                        "requested_at"
                    ].isoformat()
                )


            if item.get(
                "updated_at"
            ):

                item[
                    "updated_at"
                ] = (
                    item[
                        "updated_at"
                    ].isoformat()
                )


        print(
            f"✅ ADMIN RETURNS: {len(returns)} found"
        )


        return jsonify({

            "success":
                True,

            "returns":
                returns,

        })


    except Exception as e:

        print(
            "❌ ADMIN RETURNS ERROR:",
            e
        )


        return jsonify({

            "success": False,

            "message":
                "Failed to fetch return requests",

            "error":
                str(e),

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# ADMIN - UPDATE RETURN REQUEST
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

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )


        return_status = data.get(
            "return_status"
        )

        refund_status = data.get(
            "refund_status"
        )

        admin_note = data.get(
            "admin_note"
        )


        allowed_return_statuses = {

            "Return Requested",

            "Under Review",

            "Approved",

            "Rejected",

            "Item Received",

            "Refund Processed",

        }


        allowed_refund_statuses = {

            "Not Initiated",

            "Pending",

            "Processing",

            "Refunded",

            "Failed",

        }


        if (
            return_status is not None
            and return_status
            not in allowed_return_statuses
        ):

            return jsonify({

                "success": False,

                "message":
                    "Invalid return status",

            }), 400


        if (
            refund_status is not None
            and refund_status
            not in allowed_refund_statuses
        ):

            return jsonify({

                "success": False,

                "message":
                    "Invalid refund status",

            }), 400


        conn = get_db_connection()

        cur = conn.cursor(
            dictionary=True
        )


        cur.execute(
            """
            SELECT *
            FROM return_requests
            WHERE id=%s
            """,
            (return_id,)
        )


        existing = cur.fetchone()


        if not existing:

            return jsonify({

                "success": False,

                "message":
                    "Return request not found",

            }), 404


        update_fields = []
        values = []


        if return_status is not None:

            update_fields.append(
                "return_status=%s"
            )

            values.append(
                return_status
            )


        if refund_status is not None:

            update_fields.append(
                "refund_status=%s"
            )

            values.append(
                refund_status
            )


        if admin_note is not None:

            update_fields.append(
                "admin_note=%s"
            )

            values.append(
                str(admin_note).strip()
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


        query = f"""
            UPDATE return_requests
            SET {", ".join(update_fields)}
            WHERE id=%s
        """


        cur.execute(
            query,
            tuple(values)
        )


        conn.commit()


        cur.execute(
            """
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
                admin_note,
                requested_at,
                updated_at
            FROM return_requests
            WHERE id=%s
            """,
            (return_id,)
        )


        updated = cur.fetchone()


        if updated.get(
            "requested_at"
        ):

            updated[
                "requested_at"
            ] = (
                updated[
                    "requested_at"
                ].isoformat()
            )


        if updated.get(
            "updated_at"
        ):

            updated[
                "updated_at"
            ] = (
                updated[
                    "updated_at"
                ].isoformat()
            )


        print(
            "✅ RETURN UPDATED:",
            return_id
        )


        return jsonify({

            "success":
                True,

            "message":
                "Return request updated successfully",

            "return":
                updated,

        })


    except Exception as e:

        if conn:
            conn.rollback()


        print(
            "❌ UPDATE RETURN ERROR:",
            e
        )


        return jsonify({

            "success": False,

            "message":
                "Failed to update return request",

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
                order_number
                .strip()
                .upper(),
            )
        )


        order = cur.fetchone()


        if not order:

            return jsonify({

                "success":
                    False,

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


        if isinstance(
            order.get("items"),
            str
        ):

            try:

                order[
                    "items"
                ] = json.loads(
                    order[
                        "items"
                    ]
                )

            except Exception:

                order[
                    "items"
                ] = []


        order[
            "total_amount"
        ] = float(
            order.get(
                "total_amount"
            ) or 0
        )


        order[
            "total"
        ] = order[
            "total_amount"
        ]


        order.pop(
            "customer_access_token",
            None
        )


        return jsonify({

            "success":
                True,

            "order":
                order,

        })


    except Exception as e:

        print(
            "❌ TRACK ORDER ERROR:",
            e
        )

        return jsonify({

            "success":
                False,

            "message":
                "Unable to track order",

            "error":
                str(e),

        }), 500


    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    create_tables()

    print(
        "\n=========================================="
    )

    print(
        "🛍️  SARIKA FASHIONS BACKEND"
    )

    print(
        "=========================================="
    )

    print(
        "Local:"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print(
        "http://localhost:5000"
    )

    print(
        "=========================================="
    )

    print(
        "Admin email configured:",
        bool(ADMIN_EMAIL)
    )

    print(
        "Admin password configured:",
        bool(ADMIN_PASSWORD)
    )

    print(
        "Razorpay configured:",
        bool(razorpay_client)
    )

    print(
        "Customer My Orders:",
        "http://localhost:5000/api/my-orders"
    )

    print(
        "Customer Returns:",
        "http://localhost:5000/api/my-returns"
    )

    print(
        "Admin Returns:",
        "http://localhost:5000/api/admin/returns"
    )

    print(
        "Admin Order Status:",
        "PUT/PATCH /api/orders/<order_id>/status"
    )

    print(
        "Customer Confirm Received:",
        "POST /api/my-orders/<order_id>/received"
    )

    print(
        "==========================================\n"
    )

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )

