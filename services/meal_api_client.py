"""
Meal Planning API Client
Handles communication with the meal planning microservice
"""
import os
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class MealPlanningAPIError(Exception):
    """Custom exception for meal planning API errors"""
    pass


class MealPlanningAPI:
    """Client for meal planning API"""
    
    def __init__(self):
        self.base_url = os.environ.get(
            'RECIPE_API_BASE', 
            'https://cqztaifwfa.us-east-1.awsapprunner.com/' # production API as backup
        )
        self.timeout = 90  # API developer specified 30 seconds
    
    def generate_meal_plan(
        self,
        target_calories: int,
        dietary: List[str] = None,
        exclusions: str = "",
        preferences: str = "",
        num_days: int = 7,
        limit_per_meal: int = 1
    ) -> Optional[Dict]:
        """
        Generate a meal plan from the API
        
        Args:
            target_calories (int): Daily calorie target
            dietary (List[str]): Dietary restrictions (e.g., ["vegetarian", "gluten-free"])
            exclusions (str): Comma-separated foods to exclude
            preferences (str): Natural language meal preferences
            num_days (int): Number of days to plan (default 7)
            limit_per_meal (int): Recipes per meal (default 1)
        
        Returns:
            Dict: Meal plan data with structure:
                {
                    "daily_plans": [
                        {
                            "day": int (1-7),
                            "target_calories": int,
                            "total_calories": int,
                            "meals": [...]
                        }
                    ]
                }
            None: If API call fails
        
        Raises:
            MealPlanningAPIError: If API returns validation errors
        """
        url = f"{self.base_url}/meal-planning/n-day"
        
        # Prepare request payload
        payload = {
            "target_calories": target_calories,
            "dietary": dietary or [],
            "exclusions": exclusions,
            "preferences": preferences,
            "num_days": num_days,
            "limit_per_meal": limit_per_meal
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            logger.info(f"Calling meal planning API: {url}")
            logger.info(f"Request payload: {payload}")
            
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            
            # Handle successful response
            if response.status_code == 200:
                meal_plan = response.json()
                days_count = len(meal_plan.get('daily_plans', []))
                logger.info(f"✓ Successfully generated {days_count}-day meal plan")
                return meal_plan
            
            # Handle validation errors (422)
            elif response.status_code == 422:
                error_data = response.json()
                error_messages = []
                
                for error in error_data.get('detail', []):
                    location = " -> ".join(str(loc) for loc in error.get('loc', []))
                    message = error.get('msg', 'Unknown error')
                    error_messages.append(f"{location}: {message}")
                
                error_str = "; ".join(error_messages)
                logger.error(f"API validation error: {error_str}")
                raise MealPlanningAPIError(f"Invalid request: {error_str}")
            
            # Handle other errors
            else:
                logger.error(f"API error {response.status_code}: {response.text}")
                response.raise_for_status()
        
        except requests.exceptions.Timeout:
            logger.error(f"API timeout after {self.timeout} seconds")
            return None
        
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to API at {url}: {str(e)}")
            return None
        
        except MealPlanningAPIError:
            # Re-raise our custom errors
            raise
        
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error: {str(e)}")
            return None
        
        except Exception as e:
            logger.error(f"Unexpected error calling meal API: {str(e)}")
            return None
    
    def health_check(self) -> bool:
        """
        Check if the meal planning API is available
        
        Returns:
            bool: True if API is responding, False otherwise
        """
        try:
            # Try a simple GET to the base URL or health endpoint
            status_url = f"{self.base_url.rstrip('/')}/status"
            response = requests.get(status_url, timeout=5)
            return response.status_code in [200, 404]  # 404 is ok, means server is up
        except:
            return False
    
    def _transform_meal_plan_to_grocery_format(self, meal_plan: Dict) -> List[List[str]]:
        """
        Transform meal plan into grocery list API format.
        Each meal becomes one array of ingredient descriptions.
        
        Args:
            meal_plan: Raw meal plan with daily_plans structure
            
        Returns:
            list: List of meal descriptions (each meal = array of ingredient strings)
        """
        meal_descriptions = []
        
        if not meal_plan or 'daily_plans' not in meal_plan:
            logger.warning("Invalid meal plan structure for grocery list generation")
            return meal_descriptions
        
        for day in meal_plan.get('daily_plans', []):
            for meal in day.get('meals', []):
                if meal is None:
                    continue
                
                ingredients = meal.get('ingredients', [])
                quantities = meal.get('quantities', [])
                units = meal.get('units', [])
                
                # Build ingredient descriptions for this meal
                meal_ingredients = []
                for i, ingredient in enumerate(ingredients):
                    qty = quantities[i] if i < len(quantities) else "1"
                    unit = units[i] if i < len(units) else "serving"
                    
                    # Format: "quantity unit ingredient"
                    ingredient_desc = f"{qty} {unit} {ingredient}"
                    meal_ingredients.append(ingredient_desc)
                
                if meal_ingredients:
                    meal_descriptions.append(meal_ingredients)
        
        return meal_descriptions
    
    def generate_grocery_list(
        self,
        meal_plan: Dict,
        model: str = "command-a-03-2025"
    ) -> Optional[Dict]:
        """
        Generate a grocery list from a meal plan
        
        Args:
            meal_plan (Dict): Meal plan data with daily_plans structure
            model (str): Model to use for generation (default: command-a-03-2025)
        
        Returns:
            Dict: Grocery list data with structure:
                {
                    "shopping_list": [
                        {
                            "category": str,
                            "name": str,
                            "unit": str,
                            "quantity": float
                        }
                    ],
                    "notes": str or None
                }
            None: If API call fails
        
        Raises:
            MealPlanningAPIError: If API returns validation errors
        """
        url = f"{self.base_url.rstrip('/')}/generate-shopping-list"
        
        # Transform meal plan to API format
        meal_descriptions = self._transform_meal_plan_to_grocery_format(meal_plan)
        
        if not meal_descriptions:
            logger.warning("No meal descriptions extracted from meal plan")
            return None
        
        # Prepare request payload
        payload = {
            "meal_descriptions": meal_descriptions,
            "model": model
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            logger.info(f"Calling grocery list API: {url}")
            logger.info(f"Request payload with {len(meal_descriptions)} meals")
            
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            
            # Handle successful response
            if response.status_code == 200:
                grocery_data = response.json()
                items_count = len(grocery_data.get('shopping_list', []))
                logger.info(f"✓ Successfully generated grocery list with {items_count} items")
                return grocery_data
            
            # Handle validation errors (422)
            elif response.status_code == 422:
                error_data = response.json()
                error_messages = []
                
                for error in error_data.get('detail', []):
                    location = " -> ".join(str(loc) for loc in error.get('loc', []))
                    message = error.get('msg', 'Unknown error')
                    error_messages.append(f"{location}: {message}")
                
                error_str = "; ".join(error_messages)
                logger.error(f"Grocery API validation error: {error_str}")
                raise MealPlanningAPIError(f"Invalid grocery list request: {error_str}")
            
            # Handle other errors
            else:
                logger.error(f"Grocery API error {response.status_code}: {response.text}")
                response.raise_for_status()
        
        except requests.exceptions.Timeout:
            logger.error(f"Grocery API timeout after {self.timeout} seconds")
            return None
        
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to grocery API at {url}: {str(e)}")
            return None
        
        except MealPlanningAPIError:
            # Re-raise our custom errors
            raise
        
        except requests.exceptions.HTTPError as e:
            logger.error(f"Grocery API HTTP error: {str(e)}")
            return None
        
        except Exception as e:
            logger.error(f"Unexpected error calling grocery API: {str(e)}")
            return None
    
    def format_grocery_list_for_display(self, grocery_api_response: Dict, week_monday: datetime) -> Dict:
        """
        Format grocery API response for frontend display
        
        Args:
            grocery_api_response (Dict): Raw API response with shopping_list
            week_monday (datetime): The Monday of the week for this list
        
        Returns:
            Dict: Formatted data ready for templates with categories and checked status
        """
        if not grocery_api_response or 'shopping_list' not in grocery_api_response:
            logger.warning("Invalid grocery API response")
            return {}
        
        shopping_list = grocery_api_response.get('shopping_list', [])
        
        if not shopping_list:
            logger.warning("Empty shopping list from API")
            return {}
        
        # Add checked status to each item
        for item in shopping_list:
            item['checked'] = False
        
        # Organize by category
        categories = {}
        for item in shopping_list:
            category = item.get('category', 'Other')
            if category not in categories:
                categories[category] = []
            categories[category].append(item)
        
        # Calculate week range
        sunday = week_monday + timedelta(days=6)
        if week_monday.month == sunday.month:
            week_str = f"{week_monday.strftime('%b %d')} to {sunday.strftime('%d')}"
        else:
            week_str = f"{week_monday.strftime('%b %d')} to {sunday.strftime('%b %d')}"
        
        # Map categories to emoji icons
        category_icons = {
            'Pasta, Rice, and Cereals': '🌾',
            'Vegetables': '🥬',
            'Fruits': '🍎',
            'Dairy': '🥛',
            'Meat and Poultry': '🥩',
            'Fish and Seafood': '🐟',
            'Herbs and Spices': '🌿',
            'Bakery': '🍞',
            'Condiments and Sauces': '🧂',
            'Oils and Fats': '🫒',
            'Beverages': '🥤',
            'Other': '📦'
        }
        
        # Build final structure
        grocery_data = {
            'week': week_str,
            'sections': []
        }
        
        # Sort categories and build sections
        for category in sorted(categories.keys()):
            icon = category_icons.get(category, '📦')
            grocery_data['sections'].append({
                'title': f"{icon} {category}",
                'items': categories[category]
            })
        
        logger.info(f"Formatted grocery list with {len(shopping_list)} items in {len(categories)} categories")
        return grocery_data
    
    def format_for_display(self, meal_plan: Dict, week_monday: datetime) -> Dict:
        """
        Format API response for frontend display with actual dates
        
        Args:
            meal_plan (Dict): Raw API response with days numbered 1-7
            week_monday (datetime): The Monday of the week for this plan
        
        Returns:
            Dict: Formatted data ready for templates with actual dates
        """
        if not meal_plan or 'daily_plans' not in meal_plan:
            return {}
        
        # Day names (Monday = 1, Sunday = 7)
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        formatted = {
            'total_days': len(meal_plan['daily_plans']),
            'days': {}
        }
        
        for day_plan in meal_plan['daily_plans']:
            day_number = day_plan['day']  # 1-7 from API
            
            # Calculate the actual date for this day
            day_date = week_monday + timedelta(days=day_number - 1)
            day_name = day_names[day_number - 1]
            
            # Format date as "Mon, Oct 28"
            date_str = day_date.strftime('%b %d')
            
            # Store by day number for easy access
            formatted['days'][day_number] = {
                'day_number': day_number,
                'day_name': day_name,
                'date': date_str,
                'full_date': day_date.strftime('%Y-%m-%d'),
                'target_calories': day_plan.get('target_calories', 0),
                'actual_calories': day_plan.get('total_calories', 0),
                'target_protein': day_plan.get('target_protein', 0),
                'actual_protein': day_plan.get('total_protein', 0),
                'target_carbs': day_plan.get('target_carbs', 0),
                'actual_carbs': day_plan.get('total_carbs', 0),
                'target_fat': day_plan.get('target_fat', 0),
                'actual_fat': day_plan.get('total_fat', 0),
                'meals': []
            }
            
            # Process meals
            for meal in day_plan.get('meals', []):
                if meal is None:  # Handle null meals
                    continue
                
                meal_data = {
                    'type': meal.get('meal_type', 'Unknown'),
                    'title': meal.get('title', 'Untitled Meal'),
                    'calories': meal.get('calories', 0),
                    'description': meal.get('description', ''),
                    'macros': meal.get('macros', {}),
                    'ingredients': meal.get('ingredients', []),
                    'quantities': meal.get('quantities', []),
                    'units': meal.get('units', []),
                    'instructions': meal.get('instructions', ''),
                    'query': meal.get('query', '')
                }
                
                formatted['days'][day_number]['meals'].append(meal_data)
        
        return formatted
    
    def create_default_meal_plan(self, week_monday: datetime, calories: int = 2000) -> Dict:
        """
        Create a default meal plan when API fails
        
        Args:
            week_monday (datetime): The Monday of the week
            calories (int): Daily calorie target
        
        Returns:
            Dict: Default meal plan structure
        """
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        default_plan = {
            'total_days': 7,
            'days': {}
        }
        
        # Default meals for each day
        default_meals = [
            {
                'type': 'breakfast',
                'title': 'Balanced Breakfast',
                'calories': calories // 4,
                'description': 'A nutritious breakfast to start your day',
                'macros': {'protein': '25g', 'carbs': '45g', 'fat': '15g'},
                'ingredients': [],
                'quantities': [],
                'units': [],
                'instructions': 'Please regenerate your meal plan for detailed recipes.'
            },
            {
                'type': 'lunch',
                'title': 'Healthy Lunch',
                'calories': calories // 3,
                'description': 'A satisfying midday meal',
                'macros': {'protein': '30g', 'carbs': '50g', 'fat': '18g'},
                'ingredients': [],
                'quantities': [],
                'units': [],
                'instructions': 'Please regenerate your meal plan for detailed recipes.'
            },
            {
                'type': 'dinner',
                'title': 'Nutritious Dinner',
                'calories': calories // 3,
                'description': 'A complete evening meal',
                'macros': {'protein': '35g', 'carbs': '45g', 'fat': '20g'},
                'ingredients': [],
                'quantities': [],
                'units': [],
                'instructions': 'Please regenerate your meal plan for detailed recipes.'
            }
        ]
        
        for day_num in range(1, 8):
            day_date = week_monday + timedelta(days=day_num - 1)
            day_name = day_names[day_num - 1]
            date_str = day_date.strftime('%b %d')
            
            default_plan['days'][day_num] = {
                'day_number': day_num,
                'day_name': day_name,
                'date': date_str,
                'full_date': day_date.strftime('%Y-%m-%d'),
                'target_calories': calories,
                'actual_calories': calories,
                'target_protein': 100,
                'actual_protein': 90,
                'target_carbs': 200,
                'actual_carbs': 190,
                'target_fat': 60,
                'actual_fat': 55,
                'meals': default_meals.copy()
            }
        
        return default_plan


# Convenience function for quick usage
def generate_meal_plan_for_user(user_profile: Dict, week_monday: datetime) -> Optional[Dict]:
    """
    Generate meal plan based on user profile data
    
    Args:
        user_profile (Dict): User data with keys:
            - caloric_target: int
            - dietary_restrictions: str (comma-separated)
            - preferences: str (optional)
        week_monday (datetime): The Monday of the week for this plan
    
    Returns:
        Dict: Formatted meal plan or default plan
    """
    api = MealPlanningAPI()
    
    # Parse dietary restrictions
    dietary = []
    if user_profile.get('dietary_restrictions'):
        restrictions = user_profile['dietary_restrictions'].split(',')
        for r in restrictions:
            r = r.strip().lower()
            if r and r != 'none':  # Only add non-empty and not 'none'
                dietary.append(r)
    
    # Generate meal plan
    meal_plan = api.generate_meal_plan(
        target_calories=int(user_profile.get('caloric_target', 2000)),
        dietary=dietary,
        preferences=user_profile.get('preferences', ''),
        num_days=7
    )
    
    # If API call succeeded, format the response
    if meal_plan:
        return api.format_for_display(meal_plan, week_monday)
    
    # If API failed, return default plan
    logger.warning("Meal API unavailable, returning default plan")
    return api.create_default_meal_plan(week_monday, user_profile.get('caloric_target', 2000))
