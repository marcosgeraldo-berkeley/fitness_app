"""
Meal Planning API Client
Handles communication with the meal planning microservice
"""
import os
import requests
from typing import Dict, List, Optional
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
        self.timeout = 30  # API developer specified 30 seconds
    
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
                            "day": int,
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
            logger.debug(f"Request payload: {payload}")
            
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
            response = requests.get(
                self.base_url,
                timeout=5
            )
            return response.status_code in [200, 404]  # 404 is ok, means server is up
        except:
            return False
    
    def format_for_display(self, meal_plan: Dict) -> Dict:
        """
        Format API response for frontend display
        
        Args:
            meal_plan (Dict): Raw API response
        
        Returns:
            Dict: Formatted data ready for templates
        """
        if not meal_plan or 'daily_plans' not in meal_plan:
            return {}
        
        formatted = {
            'total_days': len(meal_plan['daily_plans']),
            'days': []
        }
        
        for day_plan in meal_plan['daily_plans']:
            day_data = {
                'day_number': day_plan['day'] + 1,  # Make 1-indexed for display
                'target_calories': day_plan['target_calories'],
                'actual_calories': day_plan['total_calories'],
                'meals': []
            }
            
            # Group meals by type
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
                    'instructions': meal.get('instructions', '')
                }
                
                day_data['meals'].append(meal_data)
            
            formatted['days'].append(day_data)
        
        return formatted


# Convenience function for quick usage
def generate_meal_plan_for_user(user_profile: Dict) -> Optional[Dict]:
    """
    Generate meal plan based on user profile data
    
    Args:
        user_profile (Dict): User data with keys:
            - caloric_target: int
            - dietary_restrictions: str (comma-separated)
            - preferences: str (optional)
    
    Returns:
        Dict: Formatted meal plan or None
    """
    api = MealPlanningAPI()
    
    # Parse dietary restrictions
    dietary = []
    if user_profile.get('dietary_restrictions'):
        restrictions = user_profile['dietary_restrictions'].split(',')
        for r in restrictions:
            r = r.strip().lower()
            if r:  # Only add non-empty strings
                dietary.append(r)
    
    # Generate meal plan
    meal_plan = api.generate_meal_plan(
        target_calories=int(user_profile.get('caloric_target', 2000)),
        dietary=dietary,
        preferences=user_profile.get('preferences', ''),
        num_days=7
    )
    
    if meal_plan:
        return api.format_for_display(meal_plan)
    
    return None
