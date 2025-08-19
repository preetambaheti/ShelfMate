from flask import Flask, render_template, request, redirect, url_for, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from markupsafe import Markup
from dotenv import load_dotenv
from markdown import markdown
import google.generativeai as genai
import os

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("models/gemini-2.0-flash") 

app = Flask(__name__)
app.secret_key = 'supersecretkey'

client = MongoClient(os.getenv("MONGO_URI"))
db = client["foodloop"]
groceries_collection = db["groceries"]
used_collection = db["used_items"]
donations_collection = db["donations"]

# Sample static food bank list
food_banks = [
    {"name": "Bangalore Food Bank", "address": "Subramanya pura Rd,Bangalore,Karnataka 560082", "phone": "(555) 123-4567", "hours": "Mon-Fri: 9am-5pm", "distance": "4.2 km"},
    {"name": "Hoysala Trust", "address": "WGJR+Jh,2nd Phase,Dattatreya Nagar,Hosakekerehalli,Bangalore,karnataka 560085", "phone": "(555) 987-6543", "hours": "Mon-Sat: 10am-7pm", "distance": "2.8 km"},
    {"name": "Aahwahan Foundation", "address": "Building No-40, 3rd Floor, 2nd Phase, J. P. Nagar, Bengaluru, Karnataka 560069", "phone": "(555) 456-7890", "hours": "Tue-Sun: 8am-6pm", "distance": "7.5 km"},
    {"name": "Aahwahan Foundation","address": "Building No-40, 3rd Floor, 2nd Phase, J. P. Nagar, Bengaluru, Karnataka 560069","phone": "(555) 456-7890","hours": "Tue-Sun: 8am-6pm","distance": "8.5 km"},
    {"name": "Feeding India by Zomato - Bangalore Chapter","address": "Koramangala 6th Block, Bengaluru, Karnataka 560095","phone": "(555) 321-6540","hours": "Mon-Sun: 9am-8pm","distance": "15.2 km"},
    {"name": "Robin Hood Army - Bangalore","address": "Indiranagar, Bengaluru, Karnataka 560038","phone": "(555) 789-1234","hours": "Mon-Sun: 10am-9pm","distance": "12.1 km"},
    {"name": "Goonj - Bangalore Center","address": "No. 58, 1st Floor, 5th Cross, 6th Main, RBI Layout, JP Nagar 7th Phase, Bengaluru, Karnataka 560078","phone": "(555) 987-6543","hours": "Mon-Sat: 10am-6pm","distance": "6.3 km"}
]

# --- Routes ---
@app.route('/')
def home():
    return render_template("index.html")

@app.route('/grocery', methods=['GET', 'POST'])
def grocery():
    if request.method == 'POST':
        selected_item = request.form.get('selected_item')
        custom_item = (request.form.get('custom_item') or "").strip()
        quantity = request.form.get('quantity')
        unit = request.form.get('unit')
        mfg_date = request.form.get('mfg_date')
        exp_date = request.form.get('exp_date')

        # Ensure only one is chosen
        if (selected_item and custom_item) or (not selected_item and not custom_item):
            flash("❌ Please choose only one item: from grocery list OR custom item.", "error")
            return redirect(url_for('grocery'))

        if not quantity:
            flash("❌ Quantity is required.", "error")
            return redirect(url_for('grocery'))

        item_to_add = selected_item or custom_item

        groceries_collection.insert_one({
            "item": item_to_add,
            "quantity": quantity,
            "unit": unit,
            "manufacture_date": datetime.strptime(mfg_date, "%Y-%m-%d"),
            "expiry_date": datetime.strptime(exp_date, "%Y-%m-%d"),
            "added_on": datetime.now()
        })

        flash("✅ Item successfully added!", "success")
        return redirect(url_for('grocery'))

    return render_template("grocery.html")

@app.route('/dashboard')
def dashboard():
    filter_status = request.args.get('filter', 'All')
    today = datetime.now().date()

    items = groceries_collection.find()
    groceries = []
    for item in items:
        expiry = item.get('expiry_date').date()
        mfg = item.get('manufacture_date').date()
        days_left = (expiry - today).days

        if days_left < 2:
            status = 'Expiring Soon'
        elif days_left < 7:
            status = 'Use Soon'
        else:
            status = 'Fresh'

        groceries.append({
            'id': str(item['_id']),
            'name': item.get('item'),
            'quantity': item.get('quantity'),
            'unit': item.get('unit'),
            'category': item.get('category', 'General'),
            'expiry': expiry.strftime("%b %d, %Y"),
            'mfg': mfg.strftime("%b %d, %Y"),
            'days_left': days_left,
            'status': status
        })

    if filter_status == 'Expiring':
        groceries = [g for g in groceries if g['status'] == 'Expiring Soon']
    elif filter_status == 'Soon':
        groceries = [g for g in groceries if g['status'] == 'Use Soon']
    elif filter_status == 'Fresh':
        groceries = [g for g in groceries if g['status'] == 'Fresh']

    return render_template("dashboard.html", groceries=groceries, active=filter_status)

@app.route('/mark_used/<id>')
def mark_used(id):
    item = groceries_collection.find_one({"_id": ObjectId(id)})
    if item:
        used_collection.insert_one(item)
        groceries_collection.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('dashboard'))

@app.route('/remove/<id>')
def remove_item(id):
    groceries_collection.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('dashboard'))

@app.route('/donate', methods=['GET', 'POST'])
def donate():
    if request.method == 'POST':
        selected_items_ids = request.form.getlist('items')
        selected_foodbank = request.form.get('foodbank')

        if selected_items_ids and selected_foodbank:
            selected_items = []
            for item_id in selected_items_ids:
                item = groceries_collection.find_one({"_id": ObjectId(item_id)})
                if item:
                    selected_items.append({
                        "item": item["item"],
                        "quantity": item["quantity"],
                        "unit": item["unit"],
                        "status": item.get("status", "Unknown"),
                        "expiry_date": item["expiry_date"]
                    })
                    groceries_collection.delete_one({"_id": ObjectId(item_id)})

            donations_collection.insert_one({
                "foodbank": selected_foodbank,
                "items": selected_items,
                "donated_at": datetime.now()
            })

        return redirect(url_for('donate', success='1'))

    groceries = list(groceries_collection.find())
    success = request.args.get('success')
    return render_template("donation.html", groceries=groceries, food_banks=food_banks, success=success)


@app.route('/impact')
def impact():
    used_count = db["used_items"].count_documents({})

    donated_agg = db["donations"].aggregate([
        {"$unwind": "$items"},
        {"$count": "total"}
    ])
    donated_count = next(donated_agg, {}).get("total", 0)

    total_saved = used_count + donated_count
    current_items = db["groceries"].count_documents({})
    total_added = total_saved + current_items

    usage_rate = round((total_saved / total_added) * 100, 2) if total_added > 0 else 0

    return render_template("impact.html",
        items_saved=total_saved,
        items_donated=donated_count,
        usage_rate=usage_rate
    )


@app.route("/recipes", methods=["GET", "POST"])
def recipes():
    generated_recipe = ""
    if request.method == "POST":
        ingredients = request.form.get("ingredients")

        prompt = f"""
        I have these ingredients: {ingredients}.
        Suggest a simple recipe with:
        - Recipe Name
        - Ingredients
        - Steps
        - Prep Time
        - Difficulty Level
        """

        try:
            response = model.generate_content(prompt)
            generated_recipe = markdown(response.text)
        except Exception as e:
            generated_recipe = f"❌ Error: {str(e)}"

    return render_template("recipes.html", recipe=generated_recipe)

# --- Main ---
if __name__ == '__main__':
    app.run(debug=True)
