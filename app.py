import os

import re

import uuid

from datetime import date, datetime, time



from bson import ObjectId

from dotenv import load_dotenv

from flask import Flask, jsonify, render_template, request

from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument

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

counters = db["counters"]



CATEGORIES = ["Sedan", "SUV", "Hatchback", "Convertible", "Truck", "Minivan"]

CONDITIONS = ["Good", "Scratched", "Damaged"]

DAILY_LATE_FEE = 500.0



# -------------------- DATABASE INDEXES --------------------



cars.create_index("vin", unique=True)

cars.create_index("license_plate", unique=True)

cars.create_index([("category", ASCENDING), ("status", ASCENDING)])

customers.create_index("email", unique=True)

customers.create_index("customer_id", unique=True, sparse=True)

customers.create_index("license_number", unique=True)

rentals.create_index("booking_code", unique=True)

rentals.create_index([("car_id", ASCENDING), ("status", ASCENDING)])

rentals.create_index([("customer_id", ASCENDING), ("status", ASCENDING)])



# Assign numeric IDs to existing customers without changing MongoDB's internal _id.

_existing_customers = list(customers.find({"customer_id": {"$exists": True}}).sort("customer_id", DESCENDING).limit(1))

_highest_customer_id = int(_existing_customers[0].get("customer_id", 1000)) if _existing_customers else 1000

for _customer in customers.find({"customer_id": {"$exists": False}}).sort("created_at", ASCENDING):

    _highest_customer_id += 1

    customers.update_one(

        {"_id": _customer["_id"], "customer_id": {"$exists": False}},

        {"$set": {"customer_id": _highest_customer_id}},

    )

counters.update_one({"_id": "customer_id"}, {"$max": {"sequence": _highest_customer_id}}, upsert=True)





def next_customer_id():

    counter = counters.find_one_and_update(

        {"_id": "customer_id"},

        {"$inc": {"sequence": 1}},

        upsert=True,

        return_document=ReturnDocument.AFTER,

    )

    return int(counter["sequence"])



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

    return isinstance(value, str) and ObjectId.is_valid(value)





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





def parse_booking_datetime(value, field_name):

    """Parse a stored ISO datetime string or datetime object."""

    if isinstance(value, datetime):

        return value

    if isinstance(value, str):

        try:

            return datetime.fromisoformat(value)

        except ValueError:

            raise ValueError(f"{field_name} is invalid.")

    raise ValueError(f"{field_name} is missing.")





@app.errorhandler(DuplicateKeyError)

def duplicate_key(_exc):

    return error(

        "A unique value already exists. Check the VIN, license plate, "

        "customer email, driver license, or booking code.",

        409,

    )





@app.errorhandler(PyMongoError)

def database_error(exc):

    app.logger.exception("Database operation failed: %s", exc)

    return error("A database operation failed. Please try again.", 500)





# -------------------- MAIN / HEALTH --------------------



@app.route("/")

def home():

    return render_template("index.html")





@app.route("/api/health")

def health():

    client.admin.command("ping")

    return jsonify({"status": "connected", "database": db.name})





# -------------------- CAR MANAGEMENT --------------------



@app.route("/api/cars", methods=["GET"])

def get_cars():

    documents = cars.find().sort("make", ASCENDING)

    result = []

    for car in documents:

        item = json_doc(car)

        # Legacy records are returned as-is; do not silently treat a daily

        # rate as an hourly rate.

        result.append(item)

    return jsonify(result)





@app.route("/api/cars", methods=["POST"])

def add_car():

    data = body()



    required = [

        "make", "model", "year", "category", "hourly_rate",

        "license_plate", "vin", "fuel_type", "transmission",

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

        hourly_rate = get_positive_amount(

            data["hourly_rate"], "Hourly rate", allow_zero=False

        )

    except (ValueError, TypeError) as exc:

        return error(str(exc) or "Enter a valid year and hourly rate.")



    if year < 2015 or year > date.today().year + 1:

        return error("Vehicle year must be 2015 or later.")



    if hourly_rate < 15:

        return error("Hourly rate must be at least ₹15.")



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

        "hourly_rate": hourly_rate,

        "license_plate": plate,

        "vin": vin,

        "fuel_type": str(data["fuel_type"]).strip(),

        "transmission": str(data["transmission"]).strip(),

        "status": "Available",

        "created_at": datetime.utcnow(),

    }



    result = cars.insert_one(document)

    return jsonify({

        "message": "Car added successfully.",

        "id": str(result.inserted_id),

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

            409,

        )



    cars.delete_one({"_id": ObjectId(car_id)})

    return jsonify({"message": "Car deleted successfully."})





@app.route("/api/cars/<car_id>/maintenance-complete", methods=["POST"])

def maintenance_complete(car_id):

    """Mark a vehicle as available after its maintenance is complete."""

    if not valid_object_id(car_id):

        return error("Invalid car ID.")



    result = cars.update_one(

        {"_id": ObjectId(car_id), "status": "Maintenance"},

        {"$set": {"status": "Available"}},

    )



    if result.modified_count != 1:

        car = cars.find_one({"_id": ObjectId(car_id)}, {"status": 1})

        if not car:

            return error("Car not found.", 404)

        if car.get("status") == "Available":

            return jsonify({"message": "Vehicle is already available."})

        return error("Vehicle is not marked for maintenance.", 409)



    return jsonify({"message": "Maintenance completed. Vehicle is available."})





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

        "customer_id": next_customer_id(),

        "name": str(data["name"]).strip(),

        "email": email,

        "phone": str(data["phone"]).strip(),

        "license_number": str(data["license_number"]).strip().upper(),

        "city": str(data["city"]).strip(),

        "total_spending": 0.0,

        "created_at": datetime.utcnow(),

    }



    result = customers.insert_one(document)

    return jsonify({

        "message": "Customer registered successfully.",

        "id": str(result.inserted_id),

        "customer_id": document["customer_id"],

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

        "status": "Rented",

    }):

        return error("Customer has an active rental.", 409)



    if rentals.count_documents({"customer_id": customer_id}):

        return error(

            "This customer has rental history. Keep the record.",

            409,

        )



    customers.delete_one({"_id": ObjectId(customer_id)})

    return jsonify({"message": "Customer deleted successfully."})





# -------------------- RENTAL HISTORY --------------------



@app.route("/api/rentals", methods=["GET"])

def get_rentals():

    documents = rentals.find().sort("created_at", DESCENDING)

    return jsonify([json_doc(rental) for rental in documents])





# -------------------- CREATE HOURLY RENTAL --------------------



@app.route("/api/rentals", methods=["POST"])

def create_rental():

    data = body()



    email = str(data.get("customer_email", "")).strip().lower()

    raw_customer_id = str(data.get("customer_id", "")).strip()

    plate = str(data.get("license_plate", "")).strip().upper()



    required = [

        "license_plate",

        "start_date", "start_time", "end_date", "end_time",

    ]

    if any(not str(data.get(field, "")).strip() for field in required):

        return error("Please complete all rental fields.")



    try:

        start_date = parse_date(data["start_date"])

        end_date = parse_date(data["end_date"])

        start_time = datetime.strptime(data["start_time"], "%H:%M").time()

        end_time = datetime.strptime(data["end_time"], "%H:%M").time()

    except (ValueError, TypeError):

        return error("Select valid rental dates and times.")



    start_at = datetime.combine(start_date, start_time)

    end_at = datetime.combine(end_date, end_time)



    if start_date < date.today():

        return error("Rental start date cannot be in the past.")



    if end_at <= start_at:

        return error("Rental end date and time must be after the start.")



    # Charge every started hour as one billable hour.

    duration_seconds = (end_at - start_at).total_seconds()

    duration_hours = int((duration_seconds + 3599) // 3600)

    if duration_hours < 1:

        return error("Rental duration must be at least one hour.")



    customer = None

    if raw_customer_id.isdigit():

        customer = customers.find_one({"customer_id": int(raw_customer_id)})

    if customer is None and email:

        customer = customers.find_one({"email": email})

    if not customer:

        return error("Select a registered customer first.", 404)

    email = customer.get("email", email)



    car = cars.find_one({"license_plate": plate})

    if not car:

        return error("Car not found.", 404)



    if car.get("status") != "Available":

        return error("Car is not available.", 409)



    if car.get("hourly_rate") is None:

        return error(

            "This vehicle has no hourly rate. Update its rate first.",

            409,

        )



    try:

        hourly_rate = get_positive_amount(

            car["hourly_rate"], "Hourly rate", allow_zero=False

        )

    except (ValueError, TypeError) as exc:

        return error(str(exc))



    car_id = str(car["_id"])



    # Check time overlap against active rentals. Older date-only bookings

    # conservatively block the entire date range they cover.

    active_rentals = rentals.find({

        "car_id": car_id,

        "status": "Rented",

    })



    for existing in active_rentals:

        try:

            if existing.get("start_at") and existing.get("end_at"):

                existing_start = parse_booking_datetime(

                    existing["start_at"], "Existing booking start"

                )

                existing_end = parse_booking_datetime(

                    existing["end_at"], "Existing booking end"

                )

            else:

                old_start = parse_date(existing["start_date"])

                old_end = parse_date(existing["end_date"])

                existing_start = datetime.combine(old_start, time.min)

                existing_end = datetime.combine(old_end, time.max)

        except (ValueError, TypeError, KeyError):

            return error(

                "An existing booking has invalid date/time data.",

                409,

            )



        if start_at < existing_end and end_at > existing_start:

            return error(

                "This car has an overlapping active booking.",

                409,

            )



    rental_amount = round(duration_hours * hourly_rate, 2)

    booking_code = "BK-" + uuid.uuid4().hex[:8].upper()



    # Claim the car before saving, preventing simultaneous bookings.

    claimed = cars.update_one(

        {"_id": car["_id"], "status": "Available"},

        {"$set": {"status": "Rented"}},

    )

    if claimed.modified_count != 1:

        return error(

            "The car was just booked. Refresh and select another vehicle.",

            409,

        )



    rental = {

        "booking_code": booking_code,

        "car_id": car_id,

        "car_name": f'{car["make"]} {car["model"]}',

        "license_plate": plate,

        "customer_id": str(customer["_id"]),

        "customer_numeric_id": customer.get("customer_id"),

        "customer_name": customer["name"],

        "customer_email": email,

        "start_date": start_date.isoformat(),

        "start_time": start_time.strftime("%H:%M"),

        "end_date": end_date.isoformat(),

        "end_time": end_time.strftime("%H:%M"),

        "start_at": start_at.isoformat(),

        "end_at": end_at.isoformat(),

        "duration_hours": duration_hours,

        "hourly_rate": hourly_rate,

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

        "maintenance_required": False,

    }



    try:

        result = rentals.insert_one(rental)

        rental["_id"] = result.inserted_id

    except Exception:

        cars.update_one(

            {"_id": car["_id"], "status": "Rented"},

            {"$set": {"status": "Available"}},

        )

        raise



    return jsonify({

        "message": "Booking created successfully.",

        "booking_code": booking_code,

        "duration_hours": duration_hours,

        "hourly_rate": hourly_rate,

        "total_amount": rental_amount,

        "rental": json_doc(rental),

    }), 201





# -------------------- RETURN VEHICLE --------------------



@app.route("/api/rentals/<rental_id>/return", methods=["POST"])

def return_car(rental_id):

    if not valid_object_id(rental_id):

        return error("Invalid rental ID.")



    data = body()

    rental = rentals.find_one({

        "_id": ObjectId(rental_id),

        "status": "Rented",

    })



    if not rental:

        return error("Active rental not found or already returned.", 404)



    try:

        returned_date = parse_date(

            data.get("returned_date", date.today().isoformat())

        )

        late_fee = get_positive_amount(data.get("late_fee", 0), "Late fee")

        damage_charge = get_positive_amount(

            data.get("damage_charge", 0), "Damage charge"

        )

        discount_amount = get_positive_amount(

            data.get("discount_amount", 0), "Discount"

        )

    except (ValueError, TypeError) as exc:

        return error(str(exc) or "Enter a valid return date and fees.")



    condition = data.get("condition", "Good")

    if condition not in CONDITIONS:

        return error(

            "Choose Good, Scratched, or Damaged for vehicle condition."

        )



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



    base_amount = float(rental.get("total_amount", 0))

    subtotal = round(base_amount + late_fee + damage_charge, 2)

    if discount_amount > subtotal:

        return error("Discount cannot exceed the rental total and charges.")

    final_amount = round(subtotal - discount_amount, 2)



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

            "discount_amount": discount_amount,

            "return_notes": notes,

            "maintenance_required": maintenance,

            "final_amount": final_amount,

        }},

    )



    if completed.modified_count != 1:

        return error("Rental has already been returned.", 409)



    new_status = "Maintenance" if maintenance else "Available"

    cars.update_one(

        {"_id": ObjectId(rental["car_id"])},

        {"$set": {"status": new_status}},

    )



    customers.update_one(

        {"_id": ObjectId(rental["customer_id"])},

        {"$inc": {"total_spending": final_amount}},

    )



    return jsonify({

        "message": "Vehicle returned. Rental history preserved.",

        "booking_code": rental["booking_code"],

        "vehicle_status": new_status,

        "overdue_days": overdue_days,

        "suggested_late_fee": suggested_late_fee,

        "discount_amount": discount_amount,

        "final_amount": final_amount,

    })





# -------------------- ANALYTICS DASHBOARD --------------------



@app.route("/api/dashboard", methods=["GET"])

def dashboard():

    total_cars = cars.count_documents({})

    available_cars = cars.count_documents({"status": "Available"})

    rented_cars = cars.count_documents({"status": "Rented"})

    customer_count = customers.count_documents({})



    completed_rentals = list(rentals.find(

        {"status": "Completed"},

        {"total_amount": 1, "final_amount": 1},

    ))



    revenue = round(sum(

        float(rental.get("final_amount", rental.get("total_amount", 0)))

        for rental in completed_rentals

    ), 2)



    monthly_pipeline = [

        {

            "$match": {

                "status": "Completed",

                "returned_at": {"$type": "date"},

            }

        },

        {

            "$group": {

                "_id": {

                    "$dateToString": {

                        "format": "%Y-%m",

                        "date": "$returned_at",

                    }

                },

                "total": {

                    "$sum": {

                        "$ifNull": ["$final_amount", "$total_amount"]

                    }

                },

            }

        },

        {"$sort": {"_id": 1}},

    ]



    monthly = list(rentals.aggregate(monthly_pipeline))



    categories = list(cars.aggregate([

        {

            "$group": {

                "_id": "$category",

                "count": {"$sum": 1},

            }

        },

        {"$sort": {"_id": 1}},

    ]))



    return jsonify({

        "total_cars": total_cars,

        "available_cars": available_cars,

        "rented_cars": rented_cars,

        "customers": customer_count,

        "total_revenue": revenue,

        "months": [item["_id"] for item in monthly],

        "monthly_revenue": [item["total"] for item in monthly],

        "categories": categories,

    })





# -------------------- START SERVER --------------------



if __name__ == "__main__":

    client.admin.command("ping")

    print("MongoDB connected successfully.")

    print("Vehicle Rental application starting...")

    app.run(host="127.0.0.1", port=5000, debug=True)
