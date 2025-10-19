from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, make_response
import sqlite3
import hashlib
import json
import os
from datetime import datetime, timedelta
from services.meal_api_client import MealPlanningAPI, MealPlanningAPIError
import logging

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this in production

# ====================INITIALIZE WORKOUT GENERATOR ====================
from workout_generator import WorkoutGenerator
workout_generator = WorkoutGenerator(fitplan_db='fitplan.db', exercise_db='exercises.db')

# ==================== METABOLIC CALCULATION FUNCTIONS ====================

def inches_to_cm(inches):
    """Convert inches to centimeters"""
    return round(inches * 2.54, 2)

def lbs_to_kg(lbs):
    """Convert pounds to kilograms"""
    return round(lbs * 0.453592, 2)

def inches_to_feet_inches(total_inches):
    """Convert total inches back to feet and inches for display"""
    feet = int(total_inches // 12)
    inches = int(total_inches % 12)
    return feet, inches

def calculate_bmr(user):
    """Calculate Basal Metabolic Rate using Mifflin-St Jeor equation"""
    age = int(user['age'])
    
    # Convert from stored imperial to metric for calculation
    height_cm = inches_to_cm(float(user['height']))  # height stored as inches
    weight_kg = lbs_to_kg(float(user['weight']))     # weight stored as lbs
    
    gender = user['gender'].lower()
    
    if gender == 'male':
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    else:  # female, non-binary default to female formula
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161
    
    return round(bmr, 2)

def calculate_tdee(bmr, activity_level):
    """Calculate Total Daily Energy Expenditure"""
    activity_multipliers = {
        'sedentary': 1.2,
        'lightly_active': 1.375,
        'moderately_active': 1.55,
        'very_active': 1.725,
        'extra_active': 1.9
    }
    multiplier = activity_multipliers.get(activity_level, 1.2)
    return round(bmr * multiplier, 2)

def calculate_caloric_target(tdee, fitness_goal):
    """Calculate daily caloric target based on fitness goal"""
    adjustments = {
        'weight_loss': -500,
        'muscle_gain': 400,
        'maintenance': 0,
        'general_fitness': -250
    }
    adjustment = adjustments.get(fitness_goal, 0)
    return round(tdee + adjustment, 2)

def calculate_weekly_exercise_calories(workout_plan, weight_kg):
    """Calculate total weekly calories burned from exercise"""
    if not workout_plan:
        return 0
    
    total_calories = 0
    days = workout_plan.get('days', [])
    
    for day in days:
        if 'exercises' in day and day['exercises']:
            # Get MET value for the day's workout
            met_value = day.get('met_value', 5.0)  # Default to moderate intensity
            duration_min = day.get('duration_minutes', 45)  # Default 45 min
            
            # Calories = MET × weight_kg × duration_hours
            calories = met_value * weight_kg * (duration_min / 60)
            total_calories += calories
    
    return round(total_calories, 2)

def calculate_macros(caloric_target, fitness_goal):
    """Calculate macro targets based on fitness goal (percentage method)"""
    macro_ratios = {
        'weight_loss': {'protein': 0.40, 'carbs': 0.30, 'fat': 0.30},
        'muscle_gain': {'protein': 0.30, 'carbs': 0.40, 'fat': 0.30},
        'maintenance': {'protein': 0.25, 'carbs': 0.45, 'fat': 0.30},
        'general_fitness': {'protein': 0.30, 'carbs': 0.40, 'fat': 0.30}
    }
    
    ratios = macro_ratios.get(fitness_goal, macro_ratios['maintenance'])
    
    # Calculate grams (protein: 4 cal/g, carbs: 4 cal/g, fat: 9 cal/g)
    protein_g = round((caloric_target * ratios['protein']) / 4, 1)
    carbs_g = round((caloric_target * ratios['carbs']) / 4, 1)
    fat_g = round((caloric_target * ratios['fat']) / 9, 1)
    
    return {
        'protein_g': protein_g,
        'carbs_g': carbs_g,
        'fat_g': fat_g,
        'protein_pct': int(ratios['protein'] * 100),
        'carbs_pct': int(ratios['carbs'] * 100),
        'fat_pct': int(ratios['fat'] * 100)
    }

def recalculate_nutrition_targets(user_id):
    """Recalculate all nutrition targets for a user"""
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if not user:
        conn.close()
        return
    
    # Convert height to cm if stored as string (e.g., "5'10" or "178 cm")
    height_cm = parse_height_to_cm(user['height'])
    weight_kg = float(user['weight']) * 0.453592  # Convert lbs to kg
    
    # Calculate BMR
    bmr = calculate_bmr(user)
    
    # Calculate TDEE (only if activity level is set)
    tdee = calculate_tdee(bmr, user['activity_level']) if user['activity_level'] else bmr
    
    # Calculate caloric target (only if fitness goal is set)
    caloric_target = calculate_caloric_target(tdee, user['fitness_goals']) if user['fitness_goals'] else tdee
    
    # Calculate macros
    macros = calculate_macros(caloric_target, user['fitness_goals']) if user['fitness_goals'] else {'protein_g': 0, 'carbs_g': 0, 'fat_g': 0}
    
    # Update database
    conn.execute('''
        UPDATE users 
        SET bmr = ?, tdee = ?, caloric_target = ?, 
            protein_target_g = ?, carbs_target_g = ?, fat_target_g = ?
        WHERE id = ?
    ''', (bmr, tdee, caloric_target, 
          macros['protein_g'], macros['carbs_g'], macros['fat_g'], 
          user_id))
    
    conn.commit()
    conn.close()
    
    return {
        'bmr': bmr,
        'tdee': tdee,
        'caloric_target': caloric_target,
        'macros': macros
    }

def parse_height_to_cm(height_str):
    """Parse height string to centimeters"""
    if not height_str:
        return 170  # default
    
    height_str = str(height_str).strip()
    
    # If already in cm format
    if 'cm' in height_str.lower():
        return float(height_str.lower().replace('cm', '').strip())
    
    # If in feet/inches format (e.g., "5'10" or "5'10\"")
    if "'" in height_str:
        parts = height_str.replace('"', '').split("'")
        feet = int(parts[0])
        inches = int(parts[1]) if len(parts) > 1 and parts[1].strip() else 0
        return round((feet * 12 + inches) * 2.54, 2)
    
    # If just a number, assume cm
    try:
        return float(height_str)
    except:
        return 170  # default

# ==================== MEAL PLANS ====================

# Set up logging 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize meal API client 
meal_api = MealPlanningAPI()

# helper functions:

def generate_grocery_list_from_meals(meal_plan):
    """
    Generate grocery list from meal plan API response
    
    Args:
        meal_plan: Raw response from meal planning API
    
    Returns:
        dict: Grocery list organized by sections
    """
    from collections import defaultdict
    
    if not meal_plan or 'daily_plans' not in meal_plan:
        return get_sample_grocery_data()
    
    # Aggregate ingredients
    ingredient_map = defaultdict(lambda: {
        'quantities': [],
        'units': [],
        'meals': []
    })
    
    for day in meal_plan.get('daily_plans', []):
        for meal in day.get('meals', []):
            if meal is None:
                continue
            
            ingredients = meal.get('ingredients', [])
            quantities = meal.get('quantities', [])
            units = meal.get('units', [])
            meal_title = meal.get('title', 'Unknown Meal')
            
            for i, ingredient in enumerate(ingredients):
                qty = quantities[i] if i < len(quantities) else "1"
                unit = units[i] if i < len(units) else "serving"
                
                ingredient_map[ingredient]['quantities'].append(qty)
                ingredient_map[ingredient]['units'].append(unit)
                ingredient_map[ingredient]['meals'].append(meal_title)
    
    # Organize into sections (simple categorization)
    produce_keywords = ['lettuce', 'tomato', 'cucumber', 'onion', 'pepper', 'carrot', 
                       'broccoli', 'spinach', 'kale', 'apple', 'banana', 'berry']
    protein_keywords = ['chicken', 'beef', 'pork', 'fish', 'salmon', 'tuna', 
                       'turkey', 'egg', 'tofu', 'tempeh']
    dairy_keywords = ['milk', 'cheese', 'yogurt', 'butter', 'cream']
    
    produce_items = []
    protein_items = []
    dairy_items = []
    pantry_items = []
    
    for ingredient, data in ingredient_map.items():
        item = {
            'name': ingredient,
            'quantity': ', '.join(data['quantities'][:3])  # Show first 3 quantities
        }
        
        ingredient_lower = ingredient.lower()
        
        if any(kw in ingredient_lower for kw in produce_keywords):
            produce_items.append(item)
        elif any(kw in ingredient_lower for kw in protein_keywords):
            protein_items.append(item)
        elif any(kw in ingredient_lower for kw in dairy_keywords):
            dairy_items.append(item)
        else:
            pantry_items.append(item)
    
    # Build grocery data structure
    grocery_data = {
        'week': datetime.now().strftime("%B %d-%d"),
        'sections': []
    }
    
    if produce_items:
        grocery_data['sections'].append({
            'title': '🥬 Produce',
            'items': sorted(produce_items, key=lambda x: x['name'])
        })
    
    if protein_items:
        grocery_data['sections'].append({
            'title': '🥩 Protein',
            'items': sorted(protein_items, key=lambda x: x['name'])
        })
    
    if dairy_items:
        grocery_data['sections'].append({
            'title': '🥛 Dairy',
            'items': sorted(dairy_items, key=lambda x: x['name'])
        })
    
    if pantry_items:
        grocery_data['sections'].append({
            'title': '🌾 Pantry',
            'items': sorted(pantry_items, key=lambda x: x['name'])
        })
    
    return grocery_data

def transform_meal_plan_for_templates(raw_meal_plan):
    """
    Transform API response to match the format expected by templates
    NOW INCLUDES: instructions, ingredients, quantities, units for recipes
    
    Args:
        raw_meal_plan: Response from meal planning API with structure:
            {
                "daily_plans": [
                    {
                        "day": 0,
                        "target_calories": 2000,
                        "total_calories": 1980,
                        "meals": [...]
                    }
                ]
            }
    
    Returns:
        Dict in format expected by templates:
            {
                "week": "January 20-26",
                "daily_calories": 2000,
                "days": {
                    "Monday": {
                        "date": "January 20",
                        "meals": [...with recipe data]
                    },
                    ...
                }
            }
    """
    from datetime import datetime, timedelta
    
    if not raw_meal_plan or 'daily_plans' not in raw_meal_plan:
        return None
    
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    # Calculate week range
    today = datetime.now()
    week_start = today
    week_end = today + timedelta(days=6)
    
    transformed = {
        "week": f"{week_start.strftime('%B %d')}-{week_end.strftime('%d')}",
        "daily_calories": 0,
        "days": {}
    }
    
    daily_plans = raw_meal_plan['daily_plans']
    
    # Calculate average daily calories
    if daily_plans:
        avg_calories = sum(day.get('target_calories', 0) for day in daily_plans) / len(daily_plans)
        transformed['daily_calories'] = int(avg_calories)
    
    # Transform each day
    for i, day_plan in enumerate(daily_plans):
        if i >= 7:  # Only handle up to 7 days
            break
        
        day_name = day_names[i]
        day_date = (week_start + timedelta(days=i)).strftime('%B %d')
        
        # Transform meals - NOW KEEPING ALL RECIPE DATA
        transformed_meals = []
        for meal in day_plan.get('meals', []):
            if meal is None:
                continue
            
            transformed_meal = {
                'title': meal.get('title', 'Untitled Meal'),
                'calories': meal.get('calories', 0),
                'description': meal.get('description', ''),
                'macros': meal.get('macros', {}),
                # KEEP RECIPE DATA
                'instructions': meal.get('instructions', ''),
                'ingredients': meal.get('ingredients', []),
                'quantities': meal.get('quantities', []),
                'units': meal.get('units', []),
                'meal_type': meal.get('meal_type', '')
            }
            
            # Add meal type emoji
            meal_type = meal.get('meal_type', '').lower()
            if 'breakfast' in meal_type:
                transformed_meal['title'] = f"🌅 {transformed_meal['title']}"
            elif 'lunch' in meal_type:
                transformed_meal['title'] = f"🥗 {transformed_meal['title']}"
            elif 'dinner' in meal_type:
                transformed_meal['title'] = f"🍽️ {transformed_meal['title']}"
            elif 'snack' in meal_type:
                transformed_meal['title'] = f"🥜 {transformed_meal['title']}"
            
            transformed_meals.append(transformed_meal)
        
        transformed['days'][day_name] = {
            'date': day_date,
            'meals': transformed_meals
        }
    
    return transformed


def get_sample_meal_data(user):
    """Fallback sample meal plan when API is unavailable"""
    return {
        "week": datetime.now().strftime("%B %d-%d"),
        "daily_calories": user['caloric_target'] if user['caloric_target'] else 1650,
        "days": {
            "Monday": {
                "date": datetime.now().strftime("%B %d"),
                "meals": [
                    {
                        "title": "🌅 Breakfast",
                        "calories": 420,
                        "description": "Greek Yogurt Parfait with gluten-free granola and blueberries",
                        "macros": {"protein": "25g", "carbs": "45g", "fat": "18g"}
                    },
                    {
                        "title": "🥗 Lunch", 
                        "calories": 480,
                        "description": "Grilled Chicken Quinoa Bowl with roasted vegetables",
                        "macros": {"protein": "32g", "carbs": "42g", "fat": "16g"}
                    },
                    {
                        "title": "🍽️ Dinner",
                        "calories": 520,
                        "description": "Baked Salmon with sweet potato and steamed broccoli", 
                        "macros": {"protein": "35g", "carbs": "38g", "fat": "22g"}
                    },
                    {
                        "title": "🥜 Snacks",
                        "calories": 230,
                        "description": "Apple with almond butter, herbal tea",
                        "macros": {"protein": "8g", "carbs": "22g", "fat": "14g"}
                    }
                ]
            }
        }
    }


def get_sample_grocery_data():
    """Fallback sample grocery list"""
    return {
        "week": datetime.now().strftime("%B %d-%d"),
        "sections": [
            {
                "title": "🥬 Produce",
                "items": [
                    {"name": "Blueberries", "quantity": "2 cups"},
                    {"name": "Broccoli crowns", "quantity": "2 heads"},
                    {"name": "Sweet potatoes", "quantity": "3 medium"},
                    {"name": "Apples", "quantity": "4 large"}
                ]
            },
            {
                "title": "🥩 Protein", 
                "items": [
                    {"name": "Chicken breast", "quantity": "2 lbs"},
                    {"name": "Salmon fillets", "quantity": "4 pieces"},
                    {"name": "Greek yogurt (plain)", "quantity": "32 oz"}
                ]
            },
            {
                "title": "🌾 Pantry",
                "items": [
                    {"name": "Quinoa", "quantity": "1 lb bag"},
                    {"name": "GF granola", "quantity": "1 box"},
                    {"name": "Almond butter", "quantity": "1 jar"}
                ]
            }
        ]
    }


# ==================== DATABASE SETUP ====================

def init_db():
    conn = sqlite3.connect('fitplan.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            weight REAL,
            height REAL,
            activity_level TEXT,
            fitness_goals TEXT,
            workout_schedule INTEGER,
            dietary_restrictions TEXT,
            physical_limitations TEXT,
            available_equipment TEXT,
            bmr REAL,
            tdee REAL,
            caloric_target REAL,
            protein_target_g REAL,
            carbs_target_g REAL,
            fat_target_g REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Meal plans table
    c.execute('''
        CREATE TABLE IF NOT EXISTS meal_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            week_date TEXT,
            plan_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Workout plans table
    c.execute('''
        CREATE TABLE IF NOT EXISTS workout_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            week_date TEXT,
            plan_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Grocery data table
    c.execute('''
        CREATE TABLE IF NOT EXISTS grocery_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            week_date TEXT,
            grocery_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    conn.commit()
    conn.close()


# ==================== TEMPLATE FILTERS ====================

@app.template_filter('fromjson')
def fromjson_filter(value):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    return value

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_db_connection():
    conn = sqlite3.connect('fitplan.db')
    conn.row_factory = sqlite3.Row
    return conn

# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/register', methods=['POST'])
def register():
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    
    if password != confirm_password:
        flash('Passwords do not match')
        return redirect(url_for('signup'))
    
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)',
                    (name, email, hash_password(password)))
        conn.commit()
        
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        
        conn.close()
        return redirect(url_for('questionnaire_intro'))
    except sqlite3.IntegrityError:
        flash('Email already exists')
        conn.close()
        return redirect(url_for('signup'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ? AND password = ?',
                       (email, hash_password(password))).fetchone()
    conn.close()
    
    if user:
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid email or password')
        return redirect(url_for('index'))

@app.route('/questionnaire-intro')
def questionnaire_intro():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('questionnaire_intro.html')

@app.route('/basic-info')
def basic_info():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('basic_info.html')

@app.route('/save-basic-info', methods=['POST'])
def save_basic_info():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    gender = request.form['gender']
    age = request.form['age']
    height_feet = int(request.form['height_feet'])
    height_inches = int(request.form['height_inches'])
    total_height_inches = (height_feet * 12) + height_inches
    weight_lbs = float(request.form['weight_lbs'])
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET gender = ?, age = ?, height = ?, weight = ? WHERE id = ?',
                (gender, age, total_height_inches, weight_lbs, session['user_id']))
    conn.commit()
    conn.close()
    
    # Recalculate after basic info update
    recalculate_nutrition_targets(session['user_id'])
    
    return redirect(url_for('activity_level'))

@app.route('/activity-level')
def activity_level():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('activity_level.html')

@app.route('/save-activity-level', methods=['POST'])
def save_activity_level():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    activity = request.form['activity_level']
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET activity_level = ? WHERE id = ?',
                (activity, session['user_id']))
    conn.commit()
    conn.close()
    
    # Recalculate after activity level update
    recalculate_nutrition_targets(session['user_id'])
    
    return redirect(url_for('fitness_goals'))

@app.route('/fitness-goals')
def fitness_goals():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('fitness_goals.html')

@app.route('/save-fitness-goals', methods=['POST'])
def save_fitness_goals():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    goals = request.form['fitness_goal']
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET fitness_goals = ? WHERE id = ?',
                (goals, session['user_id']))
    conn.commit()
    conn.close()
    
    # Recalculate after fitness goals update
    recalculate_nutrition_targets(session['user_id'])
    
    return redirect(url_for('workout_schedule'))

@app.route('/workout-schedule')
def workout_schedule():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('workout_schedule.html')

@app.route('/save-workout-schedule', methods=['POST'])
def save_workout_schedule():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    schedule = request.form['workout_schedule']
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET workout_schedule = ? WHERE id = ?',
                (schedule, session['user_id']))
    conn.commit()
    conn.close()
    
    return redirect(url_for('dietary_restrictions'))

@app.route('/dietary-restrictions')
def dietary_restrictions():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('dietary_restrictions.html')

@app.route('/save-dietary-restrictions', methods=['POST'])
def save_dietary_restrictions():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    restrictions = request.form.getlist('dietary_restrictions')
    restrictions_json = json.dumps(restrictions)
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET dietary_restrictions = ? WHERE id = ?',
                (restrictions_json, session['user_id']))
    conn.commit()
    conn.close()
    
    return redirect(url_for('physical_limitations'))

@app.route('/physical-limitations')
def physical_limitations():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('physical_limitations.html')

@app.route('/save-physical-limitations', methods=['POST'])
def save_physical_limitations():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    limitations = request.form.getlist('physical_limitations')
    limitations_json = json.dumps(limitations)
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET physical_limitations = ? WHERE id = ?',
                (limitations_json, session['user_id']))
    conn.commit()
    conn.close()
    
    return redirect(url_for('equipment_access'))

@app.route('/equipment-access')
def equipment_access():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('equipment_access.html')

@app.route('/save-equipment-access', methods=['POST'])
def save_equipment_access():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    equipment = request.form.getlist('equipment')
    equipment_json = json.dumps(equipment)
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET available_equipment = ? WHERE id = ?',
                (equipment_json, session['user_id']))
    conn.commit()
    conn.close()
    
    return redirect(url_for('profile_summary'))

@app.route('/profile_summary')
def profile_summary():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', 
                       (session['user_id'],)).fetchone()
    conn.close()
        # Convert for display
    feet, inches = inches_to_feet_inches(user['height'])
    
    user_display = {
        **dict(user),
        'height_feet': feet,
        'height_inches': inches,
        'weight_display': f"{user['weight']} lbs"
    }
    
    return render_template('profile_summary.html', user=user_display)

@app.route('/create-plan', methods=['POST'])
def create_plan():
    """Generate workout and meal plans for the user"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    week_date = datetime.now().strftime('%Y-%m-%d')
    
    try:
        # Get user data
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        
        # ============ GENERATE WORKOUT PLAN ============
        logger.info(f"Generating workout plan for user {user_id}")
        workout_data = workout_generator.generate_weekly_plan(user_id)
        
        # ============ GENERATE MEAL PLAN (NEW - API CALL) ============
        logger.info(f"Generating meal plan for user {user_id}")
        meal_data = None
        grocery_data = None
        
        try:
            # Parse dietary restrictions
            dietary = []
            if user['dietary_restrictions']:
                try:
                    restrictions = json.loads(user['dietary_restrictions'])
                    dietary = [r.strip().lower() for r in restrictions if r.strip()]
                except (json.JSONDecodeError, TypeError):
                    dietary = []
            
            # Call meal planning API
            raw_meal_plan = meal_api.generate_meal_plan(
                target_calories=int(user['caloric_target'] or 2000),
                dietary=dietary,
                preferences=", ".join(dietary) if dietary else "",
                num_days=7,
                limit_per_meal=1
            )
            
            if raw_meal_plan:
                logger.info(f"✓ Successfully generated meal plan for user {user_id}")
                meal_data = transform_meal_plan_for_templates(raw_meal_plan)
                
                # Generate grocery list from meal plan
                grocery_data = generate_grocery_list_from_meals(raw_meal_plan)
            else:
                logger.warning(f"Meal API returned None, using fallback for user {user_id}")
                meal_data = get_sample_meal_data(user)
                grocery_data = get_sample_grocery_data()
        
        except MealPlanningAPIError as e:
            logger.error(f"Meal API validation error: {str(e)}")
            meal_data = get_sample_meal_data(user)
            grocery_data = get_sample_grocery_data()
            flash('Using sample meal plan - meal service unavailable', 'warning')
        
        except Exception as e:
            logger.error(f"Error generating meal plan: {str(e)}")
            import traceback
            traceback.print_exc()
            meal_data = get_sample_meal_data(user)
            grocery_data = get_sample_grocery_data()
            flash('Using sample meal plan - error occurred', 'warning')
        
        # ============ SAVE EVERYTHING TO DATABASE ============
        
        # Save workout plan
        conn.execute('INSERT INTO workout_plans (user_id, week_date, plan_data) VALUES (?, ?, ?)',
                    (user_id, week_date, json.dumps(workout_data)))
        
        # Save meal plan
        conn.execute('INSERT INTO meal_plans (user_id, week_date, plan_data) VALUES (?, ?, ?)',
                    (user_id, week_date, json.dumps(meal_data)))
        
        # Save grocery list
        conn.execute('INSERT INTO grocery_lists (user_id, week_date, grocery_data) VALUES (?, ?, ?)',
                    (user_id, week_date, json.dumps(grocery_data)))
        
        conn.commit()
        conn.close()
        
        flash('Your personalized plans have been created!', 'success')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        logger.error(f"Error in create_plan: {e}")
        import traceback
        traceback.print_exc()
        flash('Error creating plan. Please try again.', 'error')
        return redirect(url_for('profile_summary'))

@app.route('/regenerate-workout', methods=['POST'])
def regenerate_workout():
    """Regenerate workout plan for current user"""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    try:
        user_id = session['user_id']
        workout_plan = workout_generator.generate_weekly_plan(user_id)
        
        # Update database
        week_date = workout_plan['week_of']
        conn = get_db_connection()
        
        conn.execute(
            'DELETE FROM workout_plans WHERE user_id = ? AND week_date = ?',
            (user_id, week_date)
        )
        
        conn.execute(
            'INSERT INTO workout_plans (user_id, week_date, plan_data) VALUES (?, ?, ?)',
            (user_id, week_date, json.dumps(workout_plan))
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "message": "Workout plan regenerated",
            "redirect": url_for('dashboard')
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/regenerate-meal-plan', methods=['POST'])
def regenerate_meal_plan():
    """Regenerate meal plan for current user"""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    try:
        user_id = session['user_id']
        
        # Get user data
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        
        # Parse dietary restrictions
        dietary = []
        if user['dietary_restrictions']:
            try:
                restrictions = json.loads(user['dietary_restrictions'])
                dietary = [r.strip().lower() for r in restrictions if r.strip()]
            except (json.JSONDecodeError, TypeError):
                dietary = []
        
        # Call API
        logger.info(f"Regenerating meal plan for user {user_id}")
        raw_meal_plan = meal_api.generate_meal_plan(
            target_calories=int(user['caloric_target'] or 2000),
            dietary=dietary,
            preferences=", ".join(dietary) if dietary else "",
            num_days=7,
            limit_per_meal=1
        )
        
        if raw_meal_plan:
            # Generate grocery list
            grocery_data = generate_grocery_list_from_meals(raw_meal_plan)
            
            # Update database
            week_date = datetime.now().strftime('%Y-%m-%d')
            
            conn.execute(
                'DELETE FROM meal_plans WHERE user_id = ? AND week_date = ?',
                (user_id, week_date)
            )
            conn.execute(
                'INSERT INTO meal_plans (user_id, week_date, plan_data) VALUES (?, ?, ?)',
                (user_id, week_date, json.dumps(raw_meal_plan))
            )
            
            conn.execute(
                'DELETE FROM grocery_lists WHERE user_id = ? AND week_date = ?',
                (user_id, week_date)
            )
            conn.execute(
                'INSERT INTO grocery_lists (user_id, week_date, grocery_data) VALUES (?, ?, ?)',
                (user_id, week_date, json.dumps(grocery_data))
            )
            
            conn.commit()
            conn.close()
            
            return jsonify({
                "success": True,
                "message": "Meal plan regenerated",
                "redirect": url_for('dashboard')
            }), 200
        else:
            conn.close()
            return jsonify({
                "success": False,
                "error": "Meal service unavailable"
            }), 503
    
    except MealPlanningAPIError as e:
        logger.error(f"Validation error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    
    except Exception as e:
        logger.error(f"Error regenerating meal plan: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get user nutrition data
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    # Get latest plans
    workout_plan = conn.execute('SELECT * FROM workout_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1',
                               (session['user_id'],)).fetchone()
    
    meal_plan = conn.execute('SELECT * FROM meal_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', 
                            (session['user_id'],)).fetchone()
    
    grocery_list = conn.execute('SELECT * FROM grocery_lists WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', 
                            (session['user_id'],)).fetchone()
    conn.close()
    
    workout_data = json.loads(workout_plan['plan_data']) if workout_plan else None
    meal_data = json.loads(meal_plan['plan_data']) if meal_plan else None
    grocery_data = json.loads(grocery_list['grocery_data']) if grocery_list else None
    
    # Extract first day from meal_data for dashboard preview
    first_day = None
    if meal_data:
        if isinstance(meal_data, list) and len(meal_data) > 0:
            first_day = meal_data[0]
        elif isinstance(meal_data, dict):
            if 'days' in meal_data and meal_data['days']:
                first_day_key = next(iter(meal_data['days']))
                first_day = meal_data['days'][first_day_key]
                first_day['day_name'] = first_day_key
            elif 'meal_plan' in meal_data and meal_data['meal_plan']:
                if isinstance(meal_data['meal_plan'], list):
                    first_day = meal_data['meal_plan'][0]
                else:
                    first_day_key = next(iter(meal_data['meal_plan']))
                    first_day = meal_data['meal_plan'][first_day_key]
            elif 'day_1' in meal_data:
                first_day = meal_data['day_1']
            else:
                first_day = meal_data
    
    # Prepare nutrition targets
    nutrition_targets = None
    if user and user['caloric_target']:
        nutrition_targets = {
            'calories': int(user['caloric_target']),
            'protein_g': round(user['protein_target_g'], 1) if user['protein_target_g'] else 0,
            'carbs_g': round(user['carbs_target_g'], 1) if user['carbs_target_g'] else 0,
            'fat_g': round(user['fat_target_g'], 1) if user['fat_target_g'] else 0
        }
        
        # Calculate percentages
        if nutrition_targets['calories'] > 0:
            nutrition_targets['protein_pct'] = int((nutrition_targets['protein_g'] * 4 / nutrition_targets['calories']) * 100)
            nutrition_targets['carbs_pct'] = int((nutrition_targets['carbs_g'] * 4 / nutrition_targets['calories']) * 100)
            nutrition_targets['fat_pct'] = int((nutrition_targets['fat_g'] * 9 / nutrition_targets['calories']) * 100)
    
    return render_template('dashboard.html', 
                         workout_plan=workout_data,
                         meal_plan=meal_data,
                         first_day=first_day,
                         grocery_list=grocery_data,
                         nutrition_targets=nutrition_targets,
                         user_name=session.get('user_name'))

# NEW: Add workout page route
@app.route('/workout')
def workout_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get latest workout plan
    workout_plan = conn.execute('SELECT * FROM workout_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1',
                               (session['user_id'],)).fetchone()
    conn.close()
    
    workout_data = json.loads(workout_plan['plan_data']) if workout_plan else None
    
    return render_template('workout.html', 
                         workout_plan=workout_data,
                         user_name=session.get('user_name'))


# NEW: Add meals page route
@app.route('/meals')
def meals_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get latest meal plan
    meal_plan = conn.execute('SELECT * FROM meal_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', 
                            (session['user_id'],)).fetchone()
    conn.close()
    
    meal_data = json.loads(meal_plan['plan_data']) if meal_plan else None
    
    # Extract first day from meal_data
    first_day = None
    if meal_data:
        if isinstance(meal_data, list) and len(meal_data) > 0:
            first_day = meal_data[0]
        elif isinstance(meal_data, dict):
            if 'days' in meal_data and meal_data['days']:
                first_day_key = next(iter(meal_data['days']))
                first_day = meal_data['days'][first_day_key]
                first_day['day_name'] = first_day_key
            elif 'meal_plan' in meal_data and meal_data['meal_plan']:
                if isinstance(meal_data['meal_plan'], list):
                    first_day = meal_data['meal_plan'][0]
                else:
                    first_day_key = next(iter(meal_data['meal_plan']))
                    first_day = meal_data['meal_plan'][first_day_key]
            elif 'day_1' in meal_data:
                first_day = meal_data['day_1']
            else:
                first_day = meal_data
    
    return render_template('meals.html', 
                         meal_plan=meal_data,
                         first_day=first_day,
                         user_name=session.get('user_name'))

@app.route('/recipe')
def recipe_page():
    """Display recipe page for a specific meal"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    # Recipe data is passed via sessionStorage in JavaScript
    # This route just serves the template
    return render_template('recipe.html', 
                         user_name=session.get('user_name'))

# Add grocery page route
@app.route('/grocery')
def grocery_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get latest grocery list
    grocery_list = conn.execute('SELECT * FROM grocery_lists WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', 
                            (session['user_id'],)).fetchone()
    conn.close()
    
    grocery_data = json.loads(grocery_list['grocery_data']) if grocery_list else None
    
    return render_template('grocery.html', 
                         grocery_list=grocery_data,
                         user_name=session.get('user_name'))

# Placeholder API endpoints for plan generation
@app.route('/api/generate-workout-plan', methods=['POST'])
def generate_workout_plan():
    """Generate personalized workout plan using rule-based algorithm"""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    try:
        user_id = session['user_id']
        
        # Generate workout plan
        workout_plan = workout_generator.generate_weekly_plan(user_id)
        
        # Save to database
        week_date = workout_plan['week_of']
        conn = get_db_connection()
        
        # Check if plan already exists for this week
        existing = conn.execute(
            'SELECT id FROM workout_plans WHERE user_id = ? AND week_date = ?',
            (user_id, week_date)
        ).fetchone()
        
        if existing:
            # Update existing plan
            conn.execute(
                'UPDATE workout_plans SET plan_data = ?, created_at = CURRENT_TIMESTAMP WHERE id = ?',
                (json.dumps(workout_plan), existing['id'])
            )
        else:
            # Insert new plan
            conn.execute(
                'INSERT INTO workout_plans (user_id, week_date, plan_data) VALUES (?, ?, ?)',
                (user_id, week_date, json.dumps(workout_plan))
            )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "message": "Workout plan generated successfully",
            "plan": workout_plan
        }), 200
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Error generating workout plan: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Failed to generate workout plan"}), 500

@app.route('/api/generate-meal-plan', methods=['POST']) 
def generate_meal_plan():
    """
    API endpoint for meal plan generation (called from frontend JavaScript)
    """
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    try:
        user_id = session['user_id']
        
        # Get user data
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        
        # Get custom parameters from request if provided
        data = request.json or {}
        target_calories = data.get('target_calories', user['caloric_target'] or 2000)
        num_days = data.get('num_days', 7)
        
        # Parse dietary restrictions
        dietary = []
        if user['dietary_restrictions']:
            try:
                restrictions = json.loads(user['dietary_restrictions'])
                dietary = [r.strip().lower() for r in restrictions if r.strip()]
            except (json.JSONDecodeError, TypeError):
                dietary = []
        
        # Call API
        meal_plan = meal_api.generate_meal_plan(
            target_calories=int(target_calories),
            dietary=dietary,
            preferences=data.get('preferences', ", ".join(dietary) if dietary else ""),
            num_days=num_days
        )
        
        if meal_plan:
            return jsonify({
                "success": True,
                "message": "Meal plan generated",
                "plan": meal_plan
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Meal service unavailable"
            }), 503
    
    except MealPlanningAPIError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    
    except Exception as e:
        logger.error(f"Error in API endpoint: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500

@app.route('/api/generate-grocery-list', methods=['POST'])
def generate_grocery_list():
    return jsonify({"message": "Grocery list generation - Work in progress"})

@app.route('/logout')
def logout():
    session.clear()
    response = make_response(redirect(url_for('index')))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('RENDER') is None
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
