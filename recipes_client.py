# recipes_client.py
import os
import requests
import logging

logging.basicConfig(level=logging.INFO)

RECIPE_API_BASE = os.getenv("RECIPE_API_BASE", "http://apig:8000")
RECIPE_API_KEY = os.getenv("RECIPE_API_KEY")  # optional

def _request(path: str, params: dict):
    url = f"{RECIPE_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    headers = {}
    if RECIPE_API_KEY:
        headers["Authorization"] = f"Bearer {RECIPE_API_KEY}"
    # r = requests.get(url, params=params, headers=headers, timeout=10)
    # POST request
    r = requests.post(url, json=params, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()

def get_one_recipe(dense_query: str, meal_type: str, dietary: list = [], cal_min: int = None, cal_max: int = None,
                   protein_min: int = None, protein_max: int = None,
                   carbs_min: int = None, carbs_max: int = None,
                   fat_min: int = None, fat_max: int = None):
    """
    Fetch a single meal from the API based on optional dietary and macro parameters
    """
    params = {
        "meal_tag": meal_type, 
        "limit": 1,
        "query": dense_query
    }
    for diet in dietary:
        params[diet] = True
    if cal_min is not None: params["cal_min"] = cal_min
    if cal_max is not None: params["cal_max"] = cal_max
    if protein_min is not None: params["protein_min"] = protein_min
    if protein_max is not None: params["protein_max"] = protein_max
    if carbs_min is not None: params["carbs_min"] = carbs_min
    if carbs_max is not None: params["carbs_max"] = carbs_max
    if fat_min is not None: params["fat_min"] = fat_min
    if fat_max is not None: params["fat_max"] = fat_max
    print(params)
    data = _request("/recipes/top", params)
    results = data.get("results")
    return results[0] if results else None

def get_one_day_meal_plan(caloric_target: int, dietary: list = []):
    """
    Fetch a one-day meal plan from the API based on optional dietary and macro parameters
    """
    # call API to get basic meals for one day, one meal at a time
    # TODO: Maybe we can let the API handle all of this logic instead?
    #       But for now, we'll do it here to keep control
    #       Also, we can improve the prompts later
    original_caloric_target = caloric_target

    # meal calorie percentages
    daily_meal_config = {
        "breakfast": {"calorie_pct": 0.25, "query": "healthy breakfast","meal_tag":"breakfast"},
        "lunch": {"calorie_pct": 0.30, "query": "easy lunch salad","meal_tag":"salad"},
        "dinner": {"calorie_pct": 0.30, "query": "healthy dinner","meal_tag":"main"},
        "snack": {"calorie_pct": 0.15, "query": "healthy snack","meal_tag":"snack"},
    }

    meals = []

    calorie_tolerance = 0.025  # 2.5% tolerance

    for k, v in daily_meal_config.items():

        meal = get_one_recipe(
            dense_query=v["query"],
            meal_type=v["meal_tag"],
            dietary=dietary,
            cal_min=int(caloric_target * (v["calorie_pct"] - calorie_tolerance)),
            cal_max=int(caloric_target * (v["calorie_pct"] + calorie_tolerance))
        )
        calorie_offset = caloric_target*v["calorie_pct"] - (meal['macros_per_serving']['cal'] if meal else 0)
        caloric_target += calorie_offset  # Adjust target for remaining meals
        meal_display = results_to_display(meal)
        print(meal_display)
        meals.append(meal_display)

    print(f"Caloric target: {original_caloric_target}. Actual total: {sum(m['calories'] for m in meals if m)}")

    return meals

def results_to_display(recipe: dict):
    if not recipe:
        return None
    return {
        "title": recipe['title'],
        "calories": int(recipe['macros_per_serving']['cal']),
        "description": recipe['summary'],
        "macros": {
            "protein": f"{int(recipe['macros_per_serving']['protein_g']+0.5)}g", # Round to nearest gram
            "carbs": f"{int(recipe['macros_per_serving']['carbs_g']+0.5)}g",
            "fat": f"{int(recipe['macros_per_serving']['fat_g']+0.5)}g"
        }
    }
