
import os
import re
import uuid
from datetime import date, datetime, time

from bson import ObjectId
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

load_dotenv()

app = Flask(__name__)

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing from your .env file")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
db = client["vehicle_rental_db"]

cars = db["cars"]
customers = db["customers"]
rentals = db["rentals"]

CATEGORIES = [
    "Sedan", "SUV", "Hatchback", "Convertible", "Truck", "Minivan"
]
CONDITIONS = ["Good", "Scratched", "Damaged"]
DAILY_LATE_FEE = 500.0


# -------------------- DATABASE INDEXES --------------------

cars.create_index("vin", unique=True)
cars.create_index("license_plate", unique=True)
cars.create_index([("category", ASCENDING), ("status", ASCENDING)])
customers.create_index("email", unique=True)
customers.create_index("license_number", unique=True)
rentals.create_index("booking_code", unique=True)
rentals.create_index([("car_id", ASCENDING), ("status", ASCENDING)])
rentals.create_index([("customer_id", ASCENDING), ("status", ASCENDING)])


# -------------------- HELPERS --------------------

def json_doc(doc):
    """Convert MongoDB documents to JSON-safe dictionaries."""
    if doc is None:
        return None

    result = {}

    for key, value in doc.items():
        if key == "_id" or isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        else:
            result[key] = value

    return result


def error(message, status=400):
    return jsonify({"error": message}), status


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def valid_object_id(value):
    return ObjectId.is_valid(value)


def parse_date(value):
    return date.fromisoformat(value)


def get_positive_amount(value, field_name, allow_zero=True):
    try:
        amount = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} must be a valid number.")

    if amount < 0 or (not allow_zero and amount == 0):
        raise ValueError(f"{field_name} cannot be negative or zero.")

    return round(amount, 2)


@app.errorhandler(DuplicateKeyError)
def duplicate_key(_):
    return error(
        "A unique value already exists. Check the VIN, license plate, "
        "customer email, driver license, or booking code.",
        409
    )


@app.errorhandler(PyMongoError)
def database_error(exc):
    app.logger.exception("Database operation failed: %s", exc)
    return error("A database operation failed. Please try again.", 500)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/health")
def health():
    client.admin.command("ping")
    return jsonify({
        "status": "connected",
        "database": db.name
    })


# -------------------- CAR MANAGEMENT --------------------

@app.route("/api/cars", methods=["GET"])
def get_cars():
    documents = cars.find().sort("make", ASCENDING)
    return jsonify([json_doc(car) for car in documents])


@app.route("/api/cars", methods=["POST"])
def add_car():
    data = body()

    required = [
        "make", "model", "year", "category", "daily_rate",
        "license_plate", "vin", "fuel_type", "transmission"
    ]

    if any(
        data.get(field) is None or str(data.get(field)).strip() == ""
        for field in required
    ):
        return error("Please complete every car field.")

    if data["category"] not in CATEGORIES:
        return error("Choose a valid vehicle category.")

    try:
        year = int(data["year"])
        daily_rate = get_positive_amount(
            data["daily_rate"], "Daily rate", allow_zero=False
        )
    except (ValueError, TypeError) as exc:
        return error(str(exc) or "Enter a valid year and daily rate.")

    if year < 2015 or year > date.today().year + 1:
        return error("Vehicle year must be 2015 or later.")

    if daily_rate < 15:
        return error("Daily rate must be at least ₹15.")

    plate = str(data["license_plate"]).strip().upper()
    vin = str(data["vin"]).strip().upper()

    if not re.fullmatch(r"[A-Z0-9 -]{3,20}", plate):
        return error("License plate must be 3–20 valid characters.")

    if not re.fullmatch(r"[A-Z0-9]{5,30}", vin):
        return error("VIN must be 5–30 alphanumeric characters.")

    document = {
        "make": str(data["make"]).strip(),
        "model": str(data["model"]).strip(),
        "year": year,
        "category": data["category"],
        "daily_rate": daily_rate,
        "license_plate": plate,
        "vin": vin,
        "fuel_type": str(data["fuel_type"]).strip(),
        "transmission": str(data["transmission"]).strip(),
        "status": "Available",
        "created_at": datetime.utcnow()
    }

    result = cars.insert_one(document)

    return jsonify({
        "message": "Car added successfully.",
        "id": str(result.inserted_id)
    }), 201


@app.route("/api/cars/<car_id>", methods=["DELETE"])
def delete_car(car_id):
    if not valid_object_id(car_id):
        return error("Invalid car ID.")

    car = cars.find_one({"_id": ObjectId(car_id)})

    if not car:
        return error("Car not found.", 404)

    if car.get("status") == "Rented":
        return error("Return the car before deleting it.", 409)

    if rentals.count_documents({"car_id": car_id}) > 0:
        return error(
            "This car has rental history. Keep it to preserve records.",
            409
        )

    cars.delete_one({"_id": ObjectId(car_id)})

    return jsonify({"message": "Car deleted successfully."})


# -------------------- CUSTOMER MANAGEMENT --------------------

@app.route("/api/customers", methods=["GET"])
def get_customers():
    documents = customers.find().sort("name", ASCENDING)
    return jsonify([json_doc(customer) for customer in documents])


@app.route("/api/customers", methods=["POST"])
def add_customer():
    data = body()

    required = ["name", "email", "phone", "license_number", "city"]

    if any(not str(data.get(key, "")).strip() for key in required):
        return error("Please complete every customer field.")

    email = str(data["email"]).strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return error("Enter a valid email address.")

    document = {
        "name": str(data["name"]).strip(),
        "email": email,
        "phone": str(data["phone"]).strip(),
        "license_number": str(data["license_number"]).strip().upper(),
        "city": str(data["city"]).strip(),
        "total_spending": 0.0,
        "created_at": datetime.utcnow()
    }

    result = customers.insert_one(document)

    return jsonify({
        "message": "Customer registered successfully.",
        "id": str(result.inserted_id)
    }), 201


@app.route("/api/customers/<customer_id>", methods=["DELETE"])
def delete_customer(customer_id):
    if not valid_object_id(customer_id):
        return error("Invalid customer ID.")

    customer = customers.find_one({"_id": ObjectId(customer_id)})

    if not customer:
        return error("Customer not found.", 404)

    if rentals.count_documents({
        "customer_id": customer_id,
        "status": "Rented"
    }):
        return error("Customer has an active rental.", 409)

    if rentals.count_documents({"customer_id": customer_id}):
        return error(
            "This customer has rental history. Keep the record.",
            409
        )

    customers.delete_one({"_id": ObjectId(customer_id)})

    return jsonify({"message": "Customer deleted successfully."})


# -------------------- RENTAL HISTORY --------------------

@app.route("/api/rentals", methods=["GET"])
def get_rentals():
    documents = rentals.find().sort("created_at", DESCENDING)
    return jsonify([json_doc(rental) for rental in documents])


# -------------------- CREATE RENTAL --------------------

@app.route("/api/rentals", methods=["POST"])
def create_rental():
    data = body()

    email = str(data.get("customer_email", "")).strip().lower()
    plate = str(data.get("license_plate", "")).strip().upper()

    try:
        start = parse_date(data.get("start_date", ""))
        end = parse_date(data.get("end_date", ""))
    except (ValueError, TypeError):
        return error("Select valid rental start and end dates.")

    if start < date.today():
        return error("Rental start date cannot be in the past.")

    if end < start:
        return error("End date must be on or after the start date.")

    customer = customers.find_one({"email": email})

    if not customer:
        return error("Customer not found. Register the customer first.", 404)

    car = cars.find_one({"license_plate": plate})

    if not car:
        return error("Car not found.", 404)

    if car.get("status") != "Available":
        return error("Car is not available.", 409)

    start_text = start.isoformat()
    end_text = end.isoformat()
    car_id = str(car["_id"])
    customer_id = str(customer["_id"])

    # Reject overlapping active rentals.
    overlap = rentals.find_one({
        "car_id": car_id,
        "status": "Rented",
        "start_date": {"$lte": end_text},
        "end_date": {"$gte": start_text}
    })

    if overlap:
        return error("This car has an overlapping active booking.", 409)

    days = (end - start).days + 1
    rental_amount = round(days * float(car["daily_rate"]), 2)
    booking_code = "BK-" + uuid.uuid4().hex[:8].upper()

    # Claim the car before inserting the rental.
    claimed = cars.update_one(
        {"_id": car["_id"], "status": "Available"},
        {"$set": {"status": "Rented"}}
    )

    if claimed.modified_count != 1:
        return error(
            "The car was just booked. Refresh and select another vehicle.",
            409
        )

    rental = {
        "booking_code": booking_code,
        "car_id": car_id,
        "car_name": f'{car["make"]} {car["model"]}',
        "license_plate": plate,
        "customer_id": customer_id,
        "customer_name": customer["name"],
        "customer_email": email,
        "start_date": start_text,
        "end_date": end_text,
        "duration_days": days,
        "daily_rate": float(car["daily_rate"]),
        "total_amount": rental_amount,
        "late_fee": 0.0,
        "damage_charge": 0.0,
        "final_amount": rental_amount,
        "status": "Rented",
        "created_at": datetime.utcnow(),
        "returned_at": None,
        "returned_date": None,
        "vehicle_condition": None,
        "return_notes": "",
        "overdue_days": 0,
        "maintenance_required": False
    }

    try:
        result = rentals.insert_one(rental)
        rental["_id"] = result.inserted_id
    except Exception:
        # Compensating update if booking insertion fails.
        cars.update_one(
            {"_id": car["_id"], "status": "Rented"},
            {"$set": {"status": "Available"}}
        )
        raise

    return jsonify({
        "message": "Booking created successfully.",
        "booking_code": booking_code,
        "total_amount": rental_amount,
        "rental": json_doc(rental)
    }), 201


# -------------------- RETURN VEHICLE --------------------

@app.route("/api/rentals/<rental_id>/return", methods=["POST"])
def return_car(rental_id):
    if not valid_object_id(rental_id):
        return error("Invalid rental ID.")

    data = body()

    rental = rentals.find_one({
        "_id": ObjectId(rental_id),
        "status": "Rented"
    })

    if not rental:
        return error("Active rental not found or already returned.", 404)

    try:
        returned_date = parse_date(
            data.get("returned_date", date.today().isoformat())
        )
        late_fee = get_positive_amount(
            data.get("late_fee", 0), "Late fee"
        )
        damage_charge = get_positive_amount(
            data.get("damage_charge", 0), "Damage charge"
        )
    except (ValueError, TypeError) as exc:
        return error(str(exc) or "Enter a valid return date and fees.")

    condition = data.get("condition", "Good")

    if condition not in CONDITIONS:
        return error("Choose Good, Scratched, or Damaged for vehicle condition.")

    if returned_date < parse_date(rental["start_date"]):
        return error("Return date cannot be before the rental start date.")

    notes = str(data.get("return_notes", "")).strip()
    maintenance = data.get("maintenance", False)

    if isinstance(maintenance, str):
        maintenance = maintenance.lower() in ("true", "1", "yes")

    if not isinstance(maintenance, bool):
        return error("Invalid maintenance selection.")

    planned_end = parse_date(rental["end_date"])
    overdue_days = max(0, (returned_date - planned_end).days)
    suggested_late_fee = round(overdue_days * DAILY_LATE_FEE, 2)

    # The final amount includes rental cost and return charges.
    base_amount = float(rental.get("total_amount", 0))
    final_amount = round(base_amount + late_fee + damage_charge, 2)

    # Mark the rental complete only if it is still active.
    completed = rentals.update_one(
        {"_id": rental["_id"], "status": "Rented"},
        {"$set": {
            "status": "Completed",
            "returned_at": datetime.combine(returned_date, time.min),
            "returned_date": returned_date.isoformat(),
            "vehicle_condition": condition,
            "late_fee": late_fee,
            "suggested_late_fee": suggested_late_fee,
            "overdue_days": overdue_days,
            "damage_charge": damage_charge,
            "return_notes": notes,
            "maintenance_required": maintenance,
            "final_amount": final_amount
        }}
    )

    if completed.modified_count != 1:
        return error("Rental has already been returned.", 409)

    # Return to the available fleet unless maintenance is required.
    new_status = "Maintenance" if maintenance else "Available"

    cars.update_one(
        {"_id": ObjectId(rental["car_id"])},
        {"$set": {"status": new_status}}
    )

    # Update cumulative customer spending.
    customers.update_one(
        {"_id": ObjectId(rental["customer_id"])},
        {"$inc": {"total_spending": final_amount}}
    )

    return jsonify({
        "message": "Vehicle returned. Rental history preserved.",
        "booking_code": rental["booking_code"],
        "vehicle_status": new_status,
        "overdue_days": overdue_days,
        "suggested_late_fee": suggested_late_fee,
        "final_amount": final_amount
    })


# -------------------- ANALYTICS DASHBOARD --------------------

@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    total_cars = cars.count_documents({})
    available_cars = cars.count_documents({"status": "Available"})
    rented_cars = cars.count_documents({"status": "Rented"})
    customer_count = customers.count_documents({})

    # Include completed rentals only in recognized revenue.
    completed_rentals = list(rentals.find(
        {"status": "Completed"},
        {"total_amount": 1, "final_amount": 1}
    ))

    revenue = round(sum(
        float(rental.get("final_amount", rental.get("total_amount", 0)))
        for rental in completed_rentals
    ), 2)

    monthly_pipeline = [
        {
            "$match": {
                "status": "Completed",
                "returned_at": {"$type": "date"}
            }
        },
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m",
                        "date": "$returned_at"
                    }
                },
                "total": {
                    "$sum": {
                        "$ifNull": ["$final_amount", "$total_amount"]
                    }
                }
            }
        },
        {"$sort": {"_id": 1}}
    ]

    monthly = list(rentals.aggregate(monthly_pipeline))

    categories = list(cars.aggregate([
        {
            "$group": {
                "_id": "$category",
                "count": {"$sum": 1}
            }
        },
        {"$sort": {"_id": 1}}
    ]))

    return jsonify({
        "total_cars": total_cars,
        "available_cars": available_cars,
        "rented_cars": rented_cars,
        "customers": customer_count,
        "total_revenue": revenue,
        "months": [item["_id"] for item in monthly],
        "monthly_revenue": [item["total"] for item in monthly],
        "categories": categories
    })


# -------------------- START SERVER --------------------

if __name__ == "__main__":
    client.admin.command("ping")
    print("MongoDB connected successfully.")
    print("Vehicle Rental application starting...")
    app.run(host="127.0.0.1", port=5000, debug=True)
