# recipes_client.py
import os
import requests
import logging

logging.basicConfig(level=logging.INFO)

RECIPE_API_BASE = os.getenv("RECIPE_API_BASE", "http://api:8000")
RECIPE_API_KEY = os.getenv("RECIPE_API_KEY")  # optional

def _request(path: str, params: dict):
    url = f"{RECIPE_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    logging.info(f"Requesting URL: {url} with params: {params}")
    headers = {}
    headers["accept"] = "application/json"
    headers["Content-Type"] = "application/json"
    if RECIPE_API_KEY:
        headers["Authorization"] = f"Bearer {RECIPE_API_KEY}"

    if params:
        r = requests.post(url, json=params, headers=headers, timeout=10)
    else:
        r = requests.get(url, headers=headers, timeout=10)
    # r = requests.get(url, params=params, headers=headers, timeout=10)
    # POST request
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

def get_one_day_meal_plan(caloric_target: float, dietary: list = []):
    """
    Fetch a one-day meal plan from the API based on optional dietary and macro parameters
    """
    # get api status to make sure it is up and running
    data = _request("/status", {})
    logging.info(f"API status: {data}")

    # call API to get basic meals for one day, one meal at a time
    params = {
        "caloric_target": caloric_target,
        "dietary": dietary
    }
    logging.info(f"Requesting meal plan with params: {params}")
    data = _request("/meal-plan", params)
    return data
