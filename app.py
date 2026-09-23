from flask import Flask, jsonify, request, session
from flask_cors import CORS
from dotenv import load_dotenv
import os
import razorpay
import time

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "sarika-secret-key-2024")

CORS(app, supports_credentials=True, origins=[
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000"
])

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    print(f"Razorpay Loaded: {RAZORPAY_KEY_ID}")
else:
    razorpay_client = None
    print("WARNING: Razorpay keys not found in .env - Check your .env file")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
print(f"Admin loaded: {ADMIN_EMAIL}")

@app.route("/")
def home():
    return jsonify({"message": "Sarika Fashions Backend is running!", "admin_set": bool(ADMIN_EMAIL), "razorpay_set": bool(razorpay_client)})

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}
    email = data.get("email") or data.get("username")
    password = data.get("password")
    if not email or not password:
        return jsonify({"status": "error", "message": "Email and password are required"}), 400
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return jsonify({"status": "error", "message": ".env not loaded - ADMIN_EMAIL missing"}), 500
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        session['admin'] = {"email": email, "role": "admin"}
        return jsonify({"status": "success", "authenticated": True, "admin": {"email": email}}), 200
    else:
        return jsonify({"status": "error", "message": "Invalid email or password."}), 401

@app.route("/api/admin/me", methods=["GET"])
def admin_me():
    admin = session.get('admin')
    if admin:
        return jsonify({"status": "success", "authenticated": True, "admin": admin}), 200
    return jsonify({"status": "error", "authenticated": False}), 401

@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop('admin', None)
    return jsonify({"status": "success"}), 200

@app.route("/api/payment/create-order", methods=["POST"])
def create_order():
    try:
        if not razorpay_client:
            return jsonify({"error": "Razorpay keys missing in .env"}), 500

        data = request.get_json() or {}
        amount = data.get("amount")
        
        print(f"Creating order for amount: {amount}")
        
        if not amount:
            return jsonify({"error": "Amount is required"}), 400

        # Convert to paise - must be integer
        amount_in_paise = int(float(amount) * 100)
        
        if amount_in_paise < 100:  # Minimum 1 rupee
            amount_in_paise = 100

        # Receipt is REQUIRED now
        order_data = {
            "amount": amount_in_paise,
            "currency": "INR",
            "receipt": f"receipt_{int(time.time())}"
        }
        
        order = razorpay_client.order.create(data=order_data)
        
        print(f"Order created: {order['id']}")

        return jsonify({
            "order_id": order["id"], 
            "amount": order["amount"], 
            "currency": order["currency"], 
            "key_id": RAZORPAY_KEY_ID
        })
        
    except Exception as e:
        print("RAZORPAY CREATE ORDER ERROR:", str(e))
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)