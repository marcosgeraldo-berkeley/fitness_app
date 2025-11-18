"""
app.py: Flask application to control the flow of the front end.
UPDATED FOR POSTGRESQL
"""
import os
import logging
import hashlib
import json
import threading
import time
from datetime import datetime, timedelta
from services.meal_api_client import MealPlanningAPI, MealPlanningAPIError
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, make_response
from functools import wraps

# PostgreSQL imports
from database import get_db, close_db, init_db, get_engine
from sqlalchemy import text
from dotenv import load_dotenv
from decimal import Decimal
import requests

# Load environment variables FIRST
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')  # Use env var in production
API_STATUS_CHECK_SECONDS = max(1, int(os.environ.get('MEAL_API_STATUS_INTERVAL', 5)))
app.config.setdefault('MEAL_API_AVAILABLE', True)

# ====================Security fix to clean cache between sessions ====

def no_cache(view):
    """Decorator to add no-cache headers to prevent browser caching of sensitive pages"""
    @wraps(view)
    def no_cache_view(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response
    return no_cache_view

# ====================HELPER TO HANDLE SERIAL DECIMALS IN POSTGRES ====

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# ====================INITIALIZE WORKOUT GENERATOR ====================
from workout_generator import WorkoutGenerator
# NOTE: exercises.db stays as SQLite (read-only reference database)
# Only fitplan user data moves to PostgreSQL
workout_generator = WorkoutGenerator(exercise_db='exercises.db')

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

def get_monday_of_week(date=None):
    """Get the Monday of the week for a given date (or today)"""
    if date is None:
        date = datetime.now()
    elif isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d')
    
    # Monday = 0, Sunday = 6
    days_since_monday = date.weekday()
    monday = date - timedelta(days=days_since_monday)
    return monday

def get_day_number(date=None):
    """Get the day number (1-7) where Monday=1, Sunday=7"""
    if date is None:
        date = datetime.now()
    elif isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d')
    
    # weekday() returns 0-6 (Monday-Sunday), we want 1-7
    return date.weekday() + 1

def get_week_date_range(monday_date):
    """Get formatted week range string like 'Oct 27 to Nov 2'"""
    sunday = monday_date + timedelta(days=6)
    
    # If same month
    if monday_date.month == sunday.month:
        return f"{monday_date.strftime('%b %d')} to {sunday.strftime('%d')}"
    else:
        return f"{monday_date.strftime('%b %d')} to {sunday.strftime('%b %d')}"

def recalculate_nutrition_targets(user_id):
    """Recalculate all nutrition targets for a user"""
    db = get_db()
    try:
        # Get user data
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': user_id})
        user = result.fetchone()
        
        if not user:
            return
        
        # Convert to dict for easier access
        user_dict = dict(user._mapping)
        
        # Calculate BMR
        bmr = calculate_bmr(user_dict)
        
        # Calculate TDEE (only if activity level is set)
        tdee = calculate_tdee(bmr, user_dict['activity_level']) if user_dict['activity_level'] else bmr
        
        # Calculate caloric target (only if fitness goal is set)
        caloric_target = calculate_caloric_target(tdee, user_dict['fitness_goals']) if user_dict['fitness_goals'] else tdee
        
        # Calculate macros
        macros = calculate_macros(caloric_target, user_dict['fitness_goals']) if user_dict['fitness_goals'] else {'protein_g': 0, 'carbs_g': 0, 'fat_g': 0}
        
        # Update database
        db.execute(text('''
            UPDATE users 
            SET bmr = :bmr, tdee = :tdee, caloric_target = :caloric_target, 
                protein_target_g = :protein_g, carbs_target_g = :carbs_g, fat_target_g = :fat_g
            WHERE id = :id
        '''), {
            'bmr': bmr, 
            'tdee': tdee, 
            'caloric_target': caloric_target,
            'protein_g': macros['protein_g'], 
            'carbs_g': macros['carbs_g'], 
            'fat_g': macros['fat_g'],
            'id': user_id
        })
        
        db.commit()
        
        return {
            'bmr': bmr,
            'tdee': tdee,
            'caloric_target': caloric_target,
            'macros': macros
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error recalculating nutrition targets: {e}")
        raise
    finally:
        close_db()

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

# Suppress Flask/Werkzeug access log entries for the health check endpoint
class WerkzeugHealthcheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        request_line = None
        if record.args and isinstance(record.args, tuple) and len(record.args) >= 3:
            request_line = record.args[2]
        message = record.getMessage()
        combined = f"{request_line or ''} {message}"
        return "/api/service-status" not in combined

logging.getLogger("werkzeug").addFilter(WerkzeugHealthcheckFilter())

def ensure_database_schema():
    """Make sure required tables and columns exist before serving traffic."""
    try:
        logger.info("Verifying database schema...")
        init_db()
        logger.info("Database schema verified.")
        # Log the database connection string (without password)
        # Get the database engine
        engine = get_engine()
        logger.info(f"Connected to database: {engine.url}")

    except Exception:
        logger.exception("Failed to initialize database schema.")
        raise

# Ensure schema as soon as the app module loads (covers CLI runners & WSGI servers)
ensure_database_schema()

# Initialize meal API client 
meal_api = MealPlanningAPI()

_api_monitor_started = False


def start_meal_api_status_monitor():
    """Launch a background thread that keeps track of the meal API availability."""
    global _api_monitor_started
    if _api_monitor_started:
        return

    def _monitor():
        last_status = None
        while True:
            try:
                available = bool(meal_api.health_check())
            except Exception as exc:
                logger.error(f"Error checking meal API health: {exc}")
                available = False

            app.config['MEAL_API_AVAILABLE'] = available

            if last_status is None or available != last_status:
                status_label = "available" if available else "unavailable"
                logger.info(f"Meal planning API status changed: {status_label}")
                last_status = available

            time.sleep(API_STATUS_CHECK_SECONDS)

    monitor_thread = threading.Thread(
        target=_monitor,
        daemon=True,
        name="MealAPIStatusMonitor"
    )
    monitor_thread.start()
    _api_monitor_started = True


start_meal_api_status_monitor()


@app.context_processor
def inject_service_status():
    """Expose service availability flags to all templates."""
    available = app.config.get('MEAL_API_AVAILABLE', True)
    return {
        'generation_services_down': not available,
        'meal_api_available': available,
    }

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


# Function to check if dictionary is actual a string, convert to dictionary
def ensure_dict(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value

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

# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/signup')
@no_cache
def signup():
    return render_template('signup.html')

@app.route('/register', methods=['POST'])
@no_cache
def register():
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    
    if password != confirm_password:
        flash('Passwords do not match')
        return redirect(url_for('signup'))
    
    db = get_db()
    try:
        db.execute(text('INSERT INTO users (name, email, password) VALUES (:name, :email, :password)'),
                    {'name': name, 'email': email, 'password': hash_password(password)})
        db.commit()
        
        result = db.execute(text('SELECT * FROM users WHERE email = :email'), {'email': email})
        user = result.fetchone()
        session['user_id'] = user.id
        session['user_name'] = user.name
        
        return redirect(url_for('questionnaire_intro'))
    except Exception as e:
        db.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            flash('Email already exists')
        else:
            flash('Registration error')
        return redirect(url_for('signup'))
    finally:
        close_db()

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    
    db = get_db()
    try:
        result = db.execute(text('SELECT * FROM users WHERE email = :email AND password = :password'),
                            {'email': email, 'password': hash_password(password)})
        user = result.fetchone()
        
        if user:
            session['user_id'] = user.id
            session['user_name'] = user.name
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password')
            return redirect(url_for('index'))
    finally:
        close_db()

@app.route('/questionnaire-intro')
@no_cache
def questionnaire_intro():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('questionnaire_intro.html')

@app.route('/basic-info')
@no_cache
def basic_info():
     # DEBUG: Print session info
    logger.info(f"Session user_id: {session.get('user_id')}")
    logger.info(f"Session user_name: {session.get('user_name')}")
    logger.info(f"Full session: {dict(session)}")
    # END debug
    if 'user_id' not in session:
        return redirect(url_for('index'))
    db = get_db()
    try:
        # Get existing user data if any
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': session['user_id']})
        user = result.fetchone()
        # DEBUG: Print session info
        logger.info(f"Fetched user_id: {session.get('user_id')}")
        logger.info(f"Fetched user_name: {session.get('user_name')}")
        logger.info(f"Fetched Full session: {dict(session)}")
        logger.info(f"User: {user}")
        
        # END debug
        
        # Convert to dict for template
        user_data = dict(user._mapping) if user else {}
        
        # Convert height back to feet and inches for display
        if user_data.get('height'):
            feet, inches = inches_to_feet_inches(user_data['height'])
            user_data['height_feet'] = feet
            user_data['height_inches'] = inches
        
        return render_template('basic_info.html', user=user_data)
    finally:
        close_db()

@app.route('/save-basic-info', methods=['POST'])
@no_cache
def save_basic_info():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    gender = request.form['gender']
    age = request.form['age']
    height_feet = int(request.form['height_feet'])
    height_inches = int(request.form['height_inches'])
    total_height_inches = (height_feet * 12) + height_inches
    weight_lbs = float(request.form['weight_lbs'])
    
    db = get_db()
    try:
        db.execute(text('UPDATE users SET gender = :gender, age = :age, height = :height, weight = :weight WHERE id = :id'),
                    {'gender': gender, 'age': age, 'height': total_height_inches, 'weight': weight_lbs, 'id': session['user_id']})
        db.commit()
        
        # Recalculate after basic info update
        recalculate_nutrition_targets(session['user_id'])
        
        return redirect(url_for('activity_level'))
    except Exception as e:
        db.rollback()
        flash('Error saving basic info')
        logger.error(f"Error saving basic info: {e}")
        return redirect(url_for('basic_info'))
    finally:
        close_db()

@app.route('/activity-level')
@no_cache
def activity_level():
    if 'user_id' not in session:
        return redirect(url_for('index'))   
    db = get_db()
    try:
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': session['user_id']})
        user = result.fetchone()
        user_data = dict(user._mapping) if user else {}

        return render_template('activity_level.html', user=user_data)
    finally:
        close_db()

@app.route('/save-activity-level', methods=['POST'])
@no_cache
def save_activity_level():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    activity = request.form['activity_level']
    
    db = get_db()
    try:
        db.execute(text('UPDATE users SET activity_level = :activity WHERE id = :id'),
                    {'activity': activity, 'id': session['user_id']})
        db.commit()
        
        # Recalculate after activity level update
        recalculate_nutrition_targets(session['user_id'])
        
        return redirect(url_for('fitness_goals'))
    except Exception as e:
        db.rollback()
        flash('Error saving activity level')
        logger.error(f"Error saving activity level: {e}")
        return redirect(url_for('activity_level'))
    finally:
        close_db()

@app.route('/fitness-goals')
@no_cache
def fitness_goals():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    db = get_db()
    try:
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': session['user_id']})
        user = result.fetchone()
        user_data = dict(user._mapping) if user else {}

        return render_template('fitness_goals.html', user=user_data)
    finally:
        close_db()

@app.route('/save-fitness-goals', methods=['POST'])
@no_cache
def save_fitness_goals():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    goals = request.form['fitness_goal']
    
    db = get_db()
    try:
        db.execute(text('UPDATE users SET fitness_goals = :goals WHERE id = :id'),
                    {'goals': goals, 'id': session['user_id']})
        db.commit()
        
        # Recalculate after fitness goals update
        recalculate_nutrition_targets(session['user_id'])
        
        return redirect(url_for('equipment_access'))
    except Exception as e:
        db.rollback()
        flash('Error saving fitness goals')
        logger.error(f"Error saving fitness goals: {e}")
        return redirect(url_for('fitness_goals'))
    finally:
        close_db()

@app.route('/equipment-access')
@no_cache
def equipment_access():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    db = get_db()
    try:
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': session['user_id']})
        user = result.fetchone()
        user_data = dict(user._mapping) if user else {}
        return render_template('equipment_access.html', user=user_data)
    finally:
        close_db()

@app.route('/save-equipment-access', methods=['POST'])
@no_cache
def save_equipment_access():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    equipment = request.form.getlist('equipment')
    equipment_json = json.dumps(equipment)
    
    db = get_db()
    try:
        db.execute(text('UPDATE users SET available_equipment = :equipment WHERE id = :id'),
                    {'equipment': equipment_json, 'id': session['user_id']})
        db.commit()
        
        return redirect(url_for('workout_schedule'))
    except Exception as e:
        db.rollback()
        flash('Error saving equipment access')
        logger.error(f"Error saving equipment access: {e}")
        return redirect(url_for('equipment_access'))
    finally:
        close_db()

@app.route('/workout-schedule')
@no_cache
def workout_schedule():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    db = get_db()
    try:
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': session['user_id']})
        user = result.fetchone()
        user_data = dict(user._mapping) if user else {}
        return render_template('workout_schedule.html', user=user_data)
    finally:
        close_db()

@app.route('/save-workout-schedule', methods=['POST'])
@no_cache
def save_workout_schedule():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    schedule = request.form['workout_schedule']
    
    db = get_db()
    try:
        db.execute(text('UPDATE users SET workout_schedule = :schedule WHERE id = :id'),
                    {'schedule': schedule, 'id': session['user_id']})
        db.commit()
        
        return redirect(url_for('physical_limitations'))
    except Exception as e:
        db.rollback()
        flash('Error saving workout schedule')
        logger.error(f"Error saving workout schedule: {e}")
        return redirect(url_for('workout_schedule'))
    finally:
        close_db()

@app.route('/physical-limitations')
@no_cache
def physical_limitations():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    db = get_db()
    try:
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': session['user_id']})
        user = result.fetchone()
        user_data = dict(user._mapping) if user else {}
        return render_template('physical_limitations.html',user=user_data)
    finally:
        close_db()

@app.route('/save-physical-limitations', methods=['POST'])
@no_cache
def save_physical_limitations():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    limitations = request.form.getlist('physical_limitations')
    limitations_json = json.dumps(limitations)
    
    db = get_db()
    try:
        db.execute(text('UPDATE users SET physical_limitations = :limitations WHERE id = :id'),
                    {'limitations': limitations_json, 'id': session['user_id']})
        db.commit()
        
        return redirect(url_for('dietary_restrictions'))
    except Exception as e:
        db.rollback()
        flash('Error saving physical limitations')
        logger.error(f"Error saving physical limitations: {e}")
        return redirect(url_for('physical_limitations'))
    finally:
        close_db()

@app.route('/dietary-restrictions')
@no_cache
def dietary_restrictions():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    db = get_db()
    try:
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': session['user_id']})
        user = result.fetchone()
        user_data = dict(user._mapping) if user else {}
        return render_template('dietary_restrictions.html', user=user_data)
    finally:
        close_db()

@app.route('/save-dietary-restrictions', methods=['POST'])
@no_cache
def save_dietary_restrictions():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    restrictions = request.form.getlist('dietary_restrictions')
    restrictions_json = json.dumps(restrictions)
    
    db = get_db()
    try:
        db.execute(text('UPDATE users SET dietary_restrictions = :restrictions WHERE id = :id'),
                    {'restrictions': restrictions_json, 'id': session['user_id']})
        db.commit()
        
        return redirect(url_for('food_preferences'))
    except Exception as e:
        db.rollback()
        flash('Error saving dietary restrictions')
        logger.error(f"Error saving dietary restrictions: {e}")
        return redirect(url_for('dietary_restrictions'))
    finally:
        close_db()

@app.route('/food-preferences')
@no_cache
def food_preferences():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    db = get_db()
    try:
        result = db.execute(
            text('SELECT * FROM users WHERE id = :user_id'),
            {'user_id': session['user_id']}
        )
        user = result.fetchone()
        return render_template('food_preferences.html', user=user)
    finally:
        close_db()

@app.route('/save-food-preferences', methods=['POST'])
@no_cache
def save_food_preferences():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    food_preferences = request.form.get('food_preferences', '').strip()
    food_exclusions = request.form.get('food_exclusions', '').strip()
    
    db = get_db()
    try:
        db.execute(text('''
            UPDATE users 
            SET food_preferences = :preferences, food_exclusions = :exclusions
            WHERE id = :user_id
        '''), {
            'preferences': food_preferences,
            'exclusions': food_exclusions,
            'user_id': session['user_id']
        })
        db.commit()
        return redirect(url_for('profile_summary'))
    except Exception as e:
        db.rollback()
        flash(f'Error saving food preferences: {str(e)}')
        return redirect(url_for('food_preferences'))
    finally:
        close_db()

@app.route('/profile_summary')
@no_cache
def profile_summary():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    db = get_db()
    try:
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), 
                            {'id': session['user_id']})
        user = result.fetchone()
        
        # Convert for display
        feet, inches = inches_to_feet_inches(user.height)
        
        user_display = {
            **dict(user._mapping),
            'height_feet': feet,
            'height_inches': inches,
            'weight_display': f"{user.weight} lbs"
        }
        
        return render_template('profile_summary.html', user=user_display)
    finally:
        close_db()

@app.route('/create-plan', methods=['POST'])
def create_plan():
    """Generate workout and meal plans for the user"""
    if 'user_id' not in session:
        return redirect(url_for('index'))

    if not app.config.get('MEAL_API_AVAILABLE', True):
        flash('Plan generation is currently unavailable. Please try again soon.', 'error')
        return redirect(url_for('profile_summary'))
    
    user_id = session['user_id']
    
    # Calculate Monday of current week for week_date
    monday = get_monday_of_week()
    week_date = monday.strftime('%Y-%m-%d')
    
    # Get privacy acceptance
    privacy_accepted = request.form.get('privacy_accepted')
    if not privacy_accepted:
        flash('You must accept the privacy policy to create a plan')
        return redirect(url_for('profile_summary'))
    
    # Save privacy acceptance with timestamp
    timestamp = datetime.now()

    db = get_db()
    try:
        # Update privacy acceptance
        db.execute(text('''
            UPDATE users 
            SET privacy_accepted = TRUE, privacy_accepted_at = :timestamp
            WHERE id = :user_id
        '''), {
            'timestamp': timestamp,
            'user_id': session['user_id']
        })
        db.commit()
        
        # Get user data
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': user_id})
        user = result.fetchone()
        user_dict = dict(user._mapping)
        
        # ============ GENERATE WORKOUT PLAN ============
        logger.info(f"Generating workout plan for user {user_id}")
        workout_data = workout_generator.generate_weekly_plan(user_id)
        
        # ============ GENERATE MEAL PLAN (API CALL) ============
        logger.info(f"Generating meal plan for user {user_id}")
        meal_data = None
        grocery_data = None
        
        try:
            # Parse dietary restrictions
            dietary = []
            if user_dict['dietary_restrictions']:
                try:
                    restrictions = json.loads(user_dict['dietary_restrictions'])
                    dietary = [r.strip().lower() for r in restrictions if r.strip() and r.strip().lower() != 'none']
                except (json.JSONDecodeError, TypeError):
                    dietary = []
            
            # Call meal planning API
            raw_meal_plan = meal_api.generate_meal_plan(
                target_calories=int(user_dict['caloric_target'] or 2000),
                dietary=dietary,
                preferences=user.food_preferences,
                exclusions=user.food_exclusions,
                num_days=7,
                limit_per_meal=1
            )
            
            if raw_meal_plan:
                logger.info(f"✓ Successfully generated meal plan for user {user_id}")
                # Store the RAW API output (with days 1-7)
                meal_data = raw_meal_plan
                
                # Generate grocery list from meal plan
                grocery_data = generate_grocery_list_from_meals(raw_meal_plan)
            else:
                logger.warning(f"Meal API returned None, using fallback for user {user_id}")
                # Create default plan
                meal_data = meal_api.create_default_meal_plan(monday, int(user_dict['caloric_target'] or 2000))
                grocery_data = get_sample_grocery_data()
        
        except MealPlanningAPIError as e:
            logger.error(f"Meal API validation error: {str(e)}")
            meal_data = meal_api.create_default_meal_plan(monday, int(user_dict['caloric_target'] or 2000))
            grocery_data = get_sample_grocery_data()
            flash('Using default meal plan - meal service validation error', 'warning')
        
        except Exception as e:
            logger.error(f"Error generating meal plan: {str(e)}")
            import traceback
            traceback.print_exc()
            meal_data = meal_api.create_default_meal_plan(monday, int(user_dict['caloric_target'] or 2000))
            grocery_data = get_sample_grocery_data()
            flash('Using default meal plan - error occurred', 'warning')
        
        # ============ SAVE EVERYTHING TO DATABASE ============
        
        # Save workout plan (upsert to overwrite existing weeks)
        db.execute(text('''
            INSERT INTO workout_plans (user_id, week_date, plan_data)
            VALUES (:user_id, :week_date, :plan_data)
            ON CONFLICT (user_id, week_date)
            DO UPDATE SET
                plan_data = EXCLUDED.plan_data,
                updated_at = CURRENT_TIMESTAMP
        '''), {
            'user_id': user_id,
            'week_date': week_date,
            'plan_data': json.dumps(workout_data, cls=DecimalEncoder)
        })
        
        # Save meal plan (storing the RAW API output)
        db.execute(text('''
            INSERT INTO meal_plans (user_id, week_date, plan_data)
            VALUES (:user_id, :week_date, :plan_data)
            ON CONFLICT (user_id, week_date)
            DO UPDATE SET
                plan_data = EXCLUDED.plan_data,
                updated_at = CURRENT_TIMESTAMP
        '''), {
            'user_id': user_id,
            'week_date': week_date,
            'plan_data': json.dumps(meal_data, cls=DecimalEncoder)
        })
        
        # Save grocery list
        db.execute(text('''
            INSERT INTO grocery_lists (user_id, week_date, grocery_data)
            VALUES (:user_id, :week_date, :grocery_data)
            ON CONFLICT (user_id, week_date)
            DO UPDATE SET
                grocery_data = EXCLUDED.grocery_data,
                updated_at = CURRENT_TIMESTAMP
        '''), {
            'user_id': user_id,
            'week_date': week_date,
            'grocery_data': json.dumps(grocery_data, cls=DecimalEncoder)
        })
        
        db.commit()
        
        flash('Your personalized plans have been created!', 'success')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error in create_plan: {e}")
        import traceback
        traceback.print_exc()
        flash('Error creating plan. Please try again.', 'error')
        return redirect(url_for('profile_summary'))
    finally:
        close_db()

@app.route('/privacy-policy')
def privacy_policy():
    current_date = datetime.now().strftime('%B %d, %Y')
    return render_template('privacy_policy.html', current_date=current_date)

@app.route('/regenerate-workout', methods=['POST'])
def regenerate_workout():
    """Regenerate workout plan for current user"""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401

    if not app.config.get('MEAL_API_AVAILABLE', True):
        return jsonify({
            "error": "Plan generation services are currently unavailable. Please try again later."
        }), 503
    
    db = get_db()
    try:
        user_id = session['user_id']
        workout_plan = workout_generator.generate_weekly_plan(user_id)
        
        # Update database
        week_date = workout_plan['week_of']
        
        db.execute(text('DELETE FROM workout_plans WHERE user_id = :user_id AND week_date = :week_date'),
                    {'user_id': user_id, 'week_date': week_date})
        
        db.execute(text('INSERT INTO workout_plans (user_id, week_date, plan_data) VALUES (:user_id, :week_date, :plan_data)'),
                    {'user_id': user_id, 'week_date': week_date, 'plan_data': json.dumps(workout_plan,cls=DecimalEncoder)})
        
        db.commit()
        
        return jsonify({
            "success": True,
            "message": "Workout plan regenerated",
            "redirect": url_for('dashboard')
        }), 200
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error regenerating workout: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        close_db()


@app.route('/regenerate-meal-plan', methods=['POST'])
def regenerate_meal_plan():
    """Regenerate meal plan for current user"""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401

    if not app.config.get('MEAL_API_AVAILABLE', True):
        return jsonify({
            "error": "Plan generation services are currently unavailable. Please try again later."
        }), 503
    
    db = get_db()
    try:
        user_id = session['user_id']
        
        # Get user data
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': user_id})
        user = result.fetchone()
        user_dict = dict(user._mapping)
        
        # Parse dietary restrictions
        dietary = []
        if user_dict['dietary_restrictions']:
            try:
                restrictions = json.loads(user_dict['dietary_restrictions'])
                dietary = [r.strip().lower() for r in restrictions if r.strip()]
            except (json.JSONDecodeError, TypeError):
                dietary = []
        
        # Call API
        logger.info(f"Regenerating meal plan for user {user_id}")
        raw_meal_plan = meal_api.generate_meal_plan(
            target_calories=int(user_dict['caloric_target'] or 2000),
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
            
            db.execute(text('DELETE FROM meal_plans WHERE user_id = :user_id AND week_date = :week_date'),
                        {'user_id': user_id, 'week_date': week_date})
            db.execute(text('INSERT INTO meal_plans (user_id, week_date, plan_data) VALUES (:user_id, :week_date, :plan_data)'),
                        {'user_id': user_id, 'week_date': week_date, 'plan_data': json.dumps(raw_meal_plan,cls=DecimalEncoder)})
            
            db.execute(text('DELETE FROM grocery_lists WHERE user_id = :user_id AND week_date = :week_date'),
                        {'user_id': user_id, 'week_date': week_date})
            db.execute(text('INSERT INTO grocery_lists (user_id, week_date, grocery_data) VALUES (:user_id, :week_date, :grocery_data)'),
                        {'user_id': user_id, 'week_date': week_date, 'grocery_data': json.dumps(grocery_data,cls=DecimalEncoder)})
            
            db.commit()
            
            return jsonify({
                "success": True,
                "message": "Meal plan regenerated",
                "redirect": url_for('dashboard')
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Meal service unavailable"
            }), 503
    
    except MealPlanningAPIError as e:
        db.rollback()
        logger.error(f"Validation error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error regenerating meal plan: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500
    finally:
        close_db()


@app.route('/api/service-status')
def service_status_api():
    """Expose the current availability of generation services."""
    available = bool(app.config.get('MEAL_API_AVAILABLE', True))
    return jsonify({"generation_available": available})


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    db = get_db()
    try:
        # Get user nutrition data
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': session['user_id']})
        user = result.fetchone()
        user_dict = dict(user._mapping)

        # logging.info(f"User dict: {user_dict}")
        
        # Get latest plans
        result = db.execute(text('SELECT * FROM workout_plans WHERE user_id = :id ORDER BY created_at DESC LIMIT 1'),
                            {'id': session['user_id']})
        workout_plan = result.fetchone()
        # logging.info(f"Workout plan: {workout_plan}")
        
        result = db.execute(text('SELECT * FROM meal_plans WHERE user_id = :id ORDER BY created_at DESC LIMIT 1'),
                            {'id': session['user_id']})
        meal_plan = result.fetchone()
        # logging.info(f"Meal plan: {meal_plan}")
        
        result = db.execute(text('SELECT * FROM grocery_lists WHERE user_id = :id ORDER BY created_at DESC LIMIT 1'), 
                                {'id': session['user_id']})
        grocery_list = result.fetchone()
        # logging.info(f"Grocery list: {grocery_list}")

        workout_data = ensure_dict(workout_plan.plan_data) if workout_plan else None
        meal_data = ensure_dict(meal_plan.plan_data) if meal_plan else None
        grocery_data = ensure_dict(grocery_list.grocery_data) if grocery_list else None

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
        if user and user_dict['caloric_target']:
            nutrition_targets = {
                'calories': int(user_dict['caloric_target']),
                'protein_g': round(user_dict['protein_target_g'], 1) if user_dict['protein_target_g'] else 0,
                'carbs_g': round(user_dict['carbs_target_g'], 1) if user_dict['carbs_target_g'] else 0,
                'fat_g': round(user_dict['fat_target_g'], 1) if user_dict['fat_target_g'] else 0
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
    finally:
        close_db()

@app.route('/workout')
def workout_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    db = get_db()
    try:
        # Calculate Monday of current week
        monday = get_monday_of_week()
        week_date = monday.strftime('%Y-%m-%d')
        
        # Get latest workout plan for current week
        result = db.execute(text('''
            SELECT * FROM workout_plans 
            WHERE user_id = :id AND week_date = :week_date
            ORDER BY created_at DESC 
            LIMIT 1
        '''), {'id': session['user_id'], 'week_date': week_date})
        workout_plan = result.fetchone()

        workout_data = ensure_dict(workout_plan.plan_data) if workout_plan else None

        # Add formatted week range to workout data
        if workout_data:
            workout_data['week_range'] = get_week_date_range(monday)
        
        return render_template('workout.html', 
                                workout_plan=workout_data,
                                user_name=session.get('user_name'))
    finally:
        close_db()

@app.route('/meals')
def meals_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    db = get_db()
    try:
        # Calculate Monday of current week
        monday = get_monday_of_week()
        week_date = monday.strftime('%Y-%m-%d')
        
        # Get the MOST RECENT meal plan for the current week
        result = db.execute(text('''
            SELECT * FROM meal_plans 
            WHERE user_id = :id AND week_date = :week_date
            ORDER BY created_at DESC 
            LIMIT 1
        '''), {'id': session['user_id'], 'week_date': week_date})
        meal_plan = result.fetchone()
        
        # If no plan for current week, redirect to profile summary
        if not meal_plan:
            flash('No meal plan found for this week. Please create a new plan.', 'info')
            return redirect(url_for('profile_summary'))
        
        # Get the raw API data
        raw_meal_data = meal_plan.plan_data
        raw_meal_data = ensure_dict(raw_meal_data)

        # logger.info(f"Raw meal data for user {session['user_id']}: {raw_meal_data}")
        
        # Format for display with actual dates
        formatted_meal_data = meal_api.format_for_display(raw_meal_data, monday)
        
        # Get current day number (1-7, where Monday=1)
        current_day_number = get_day_number()
        
        return render_template('meals.html',
                                meal_plan=formatted_meal_data,
                                current_day=current_day_number,
                                user_name=session.get('user_name'))
    finally:
        close_db()

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
    
    db = get_db()
    try:
        # Get latest grocery list
        result = db.execute(text('SELECT * FROM grocery_lists WHERE user_id = :id ORDER BY created_at DESC LIMIT 1'), 
                                {'id': session['user_id']})
        grocery_list = result.fetchone()
        
        grocery_data = grocery_list.grocery_data if grocery_list else None
        
        return render_template('grocery.html', 
                                grocery_list=grocery_data,
                                user_name=session.get('user_name'))
    finally:
        close_db()

# API endpoints for plan generation
@app.route('/api/generate-workout-plan', methods=['POST'])
def generate_workout_plan():
    """Generate personalized workout plan using rule-based algorithm"""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    db = get_db()
    try:
        user_id = session['user_id']
        
        # Generate workout plan
        workout_plan = workout_generator.generate_weekly_plan(user_id)
        
        # Save to database
        week_date = workout_plan['week_of']
        
        # Check if plan already exists for this week
        result = db.execute(text('SELECT id FROM workout_plans WHERE user_id = :user_id AND week_date = :week_date'),
                {'user_id': user_id, 'week_date': week_date})
        existing = result.fetchone()
        
        if existing:
            # Update existing plan
            db.execute(text('UPDATE workout_plans SET plan_data = :plan_data, created_at = CURRENT_TIMESTAMP WHERE id = :id'),
                        {'plan_data': json.dumps(workout_plan,cls=DecimalEncoder), 'id': existing.id})
        else:
            # Insert new plan
            db.execute(text('INSERT INTO workout_plans (user_id, week_date, plan_data) VALUES (:user_id, :week_date, :plan_data)'),
                        {'user_id': user_id, 'week_date': week_date, 'plan_data': json.dumps(workout_plan,cls=DecimalEncoder)})
        
        db.commit()
        
        return jsonify({
            "success": True,
            "message": "Workout plan generated successfully",
            "plan": workout_plan
        }), 200
        
    except ValueError as e:
        db.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        db.rollback()
        logger.error(f"Error generating workout plan: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Failed to generate workout plan"}), 500
    finally:
        close_db()

@app.route('/api/generate-meal-plan', methods=['POST']) 
def generate_meal_plan():
    """
    API endpoint for meal plan generation (called from frontend JavaScript)
    """
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    db = get_db()
    try:
        user_id = session['user_id']
        
        # Get user data
        result = db.execute(text('SELECT * FROM users WHERE id = :id'), {'id': user_id})
        user = result.fetchone()
        user_dict = dict(user._mapping)
        
        # Get custom parameters from request if provided
        data = request.json or {}
        target_calories = data.get('target_calories', user_dict['caloric_target'] or 2000)
        num_days = data.get('num_days', 7)
        
        # Parse dietary restrictions
        dietary = []
        if user_dict['dietary_restrictions']:
            try:
                restrictions = json.loads(user_dict['dietary_restrictions'])
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
    finally:
        close_db()

@app.route('/api/generate-grocery-list', methods=['POST'])
def generate_grocery_list():
    return jsonify({"message": "Grocery list generation - Work in progress"})

@app.route('/logout')
def logout():
    session.clear()
    response = make_response(redirect(url_for('index')))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response

if __name__ == '__main__':
    # Initialize database tables (creates tables if they don't exist)
    init_db()
    
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', '1') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)

@app.route("/_probe/out")
def probe_out():
    base = os.getenv("RECIPE_API_BASE", "")
    out = {}
    try:
        r = requests.get("https://ifconfig.me", timeout=5)
        out["internet_ok"] = True
        out["public_ip"] = r.text.strip()[:80]
    except Exception as e:
        out["internet_ok"] = False
        out["internet_err"] = str(e)

    try:
        if base:
            r2 = requests.get(f"{base.rstrip('/')}/status", timeout=5)
            out["api_base"] = base
            out["api_status_code"] = r2.status_code
            out["api_body"] = r2.text[:200]
        else:
            out["api_base_missing"] = True
    except Exception as e:
        out["api_base"] = base
        out["api_err"] = str(e)
    return jsonify(out)
