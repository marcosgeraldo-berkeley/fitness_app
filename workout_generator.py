"""
FitPlan Workout Generator v2.1
Research-based exercise recommendation system with contraindication filtering
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import random

class WorkoutGenerator:
    def __init__(self, fitplan_db='fitplan.db', exercise_db='exercises.db'):
        self.fitplan_db = fitplan_db
        self.exercise_db = exercise_db
        
    def get_user_profile(self, user_id: int) -> Dict:
        """Fetch user profile from fitplan.db including workout_schedule preference"""
        conn = sqlite3.connect(self.fitplan_db)
        conn.row_factory = sqlite3.Row
        
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Parse JSON fields
        return {
            'user_id': user['id'],
            'age': user['age'],
            'gender': user['gender'],
            'weight': float(user['weight']),  # in lbs
            'fitness_goal': user['fitness_goals'],
            'activity_level': user['activity_level'],
            'workout_schedule': user['workout_schedule'],
            'physical_limitations': json.loads(user['physical_limitations']) if user['physical_limitations'] else [],
            'available_equipment': json.loads(user['available_equipment']) if user['available_equipment'] else [],
            'tdee': user['tdee'],
            'bmr': user['bmr']
        }
    
    def determine_fitness_level(self, activity_level: str, age: int) -> str:
        """Determine fitness level from activity level and age"""
        level_map = {
            'sedentary': 'beginner',
            'lightly_active': 'beginner',
            'moderately_active': 'intermediate',
            'very_active': 'intermediate',
            'extra_active': 'advanced'
        }
        
        base_level = level_map.get(activity_level, 'beginner')
        
        # Adjust for age (older users start more conservative)
        if age > 55 and base_level == 'advanced':
            return 'intermediate'
        elif age > 65:
            return 'beginner'
        
        return base_level
    
    def determine_workout_days(self, workout_schedule: int, fitness_goal: str, 
                               fitness_level: str, age: int) -> Tuple[int, Optional[str], Optional[str]]:
        """
        Determine optimal workout days with safety overrides
        Returns: (days, warning_flag, warning_message)
        """
        
        # User's preferred range
        preference_ranges = {
            1: [1, 2],
            3: [3, 4],
            5: [5, 6],
            7: [7]
        }
        user_range = preference_ranges.get(workout_schedule, [3, 4])
        
        # Ideal days by fitness goal (research-based)
        goal_ideal_days = {
            'weight-loss': 5,
            'strength': 4,
            'muscle-building': 5,
            'endurance': 6,
            'general_fitness': 3,
            'maintenance': 3
        }
        ideal_days = goal_ideal_days.get(fitness_goal, 3)
        
        # Safety caps by fitness level
        max_days_by_level = {
            'beginner': 5,
            'intermediate': 6,
            'advanced': 7
        }
        max_safe_days = max_days_by_level[fitness_level]
        
        # Additional age-based safety
        if age > 60:
            max_safe_days = min(max_safe_days, 5)
        
        # Select days from user's range
        if ideal_days in user_range:
            selected_days = ideal_days
        else:
            selected_days = min(user_range, key=lambda x: abs(x - ideal_days))
        
        # Apply safety override
        warning_flag = None
        warning_message = None
        
        if selected_days > max_safe_days:
            warning_flag = 'safety_override'
            warning_message = (
                f"⚠️ We've adjusted your plan to {max_safe_days} days per week for optimal recovery "
                f"as a {fitness_level} level athlete. Training 7 days without proper rest can lead to "
                f"overtraining and injury. Your body needs time to repair and grow stronger."
            )
            selected_days = max_safe_days
        
        elif selected_days < ideal_days and selected_days == max(user_range):
            warning_flag = 'suboptimal_frequency'
            goal_name = fitness_goal.replace('-', ' ').replace('_', ' ').title()
            warning_message = (
                f"💡 For optimal {goal_name} results, we recommend {ideal_days} days per week. "
                f"You're currently training {selected_days} days. Consider increasing your workout "
                f"frequency in your profile settings for better results."
            )
        
        elif selected_days == 7:
            warning_flag = 'active_recovery_needed'
            warning_message = (
                "🌱 Your plan includes daily training. We've included active recovery days with light "
                "work (yoga, walking, stretching) to prevent burnout while keeping you active."
            )
        
        return selected_days, warning_flag, warning_message
    
    def calculate_daily_volume(self, workout_days: int, fitness_goal: str, 
                              fitness_level: str) -> Dict:
        """Calculate exercises per day based on total weekly volume goals"""
        
        weekly_volume_targets = {
            'weight-loss': {'beginner': 70, 'intermediate': 85, 'advanced': 100},
            'strength': {'beginner': 40, 'intermediate': 55, 'advanced': 70},
            'muscle-building': {'beginner': 60, 'intermediate': 75, 'advanced': 90},
            'endurance': {'beginner': 75, 'intermediate': 95, 'advanced': 120},
            'general_fitness': {'beginner': 50, 'intermediate': 65, 'advanced': 80},
            'maintenance': {'beginner': 45, 'intermediate': 60, 'advanced': 75}
        }
        
        weekly_sets = weekly_volume_targets.get(fitness_goal, {}).get(fitness_level, 60)
        sets_per_day = weekly_sets / workout_days
        
        goal_programming = {
            'strength': {
                'sets_per_exercise': 4,
                'reps_min': 3,
                'reps_max': 6,
                'rest_seconds': 180,
                'load_pct': '85-90%'
            },
            'muscle-building': {
                'sets_per_exercise': 3,
                'reps_min': 8,
                'reps_max': 12,
                'rest_seconds': 75,
                'load_pct': '70-85%'
            },
            'weight-loss': {
                'sets_per_exercise': 3,
                'reps_min': 10,
                'reps_max': 15,
                'rest_seconds': 45,
                'load_pct': '60-75%'
            },
            'endurance': {
                'sets_per_exercise': 2.5,
                'reps_min': 15,
                'reps_max': 25,
                'rest_seconds': 40,
                'load_pct': '50-65%'
            },
            'general_fitness': {
                'sets_per_exercise': 3,
                'reps_min': 10,
                'reps_max': 12,
                'rest_seconds': 75,
                'load_pct': '65-75%'
            },
            'maintenance': {
                'sets_per_exercise': 3,
                'reps_min': 8,
                'reps_max': 12,
                'rest_seconds': 90,
                'load_pct': '65-75%'
            }
        }
        
        programming = goal_programming.get(fitness_goal, goal_programming['general_fitness'])
        exercises_per_day = int(sets_per_day / programming['sets_per_exercise'])
        
        if workout_days <= 2:
            exercises_per_day = max(exercises_per_day, 8)
        elif workout_days >= 6:
            exercises_per_day = min(exercises_per_day, 5)
        
        exercises_per_day = max(4, min(exercises_per_day, 12))
        
        return {
            'exercises_per_day': exercises_per_day,
            'sets_per_exercise': int(programming['sets_per_exercise']),
            'reps_min': programming['reps_min'],
            'reps_max': programming['reps_max'],
            'rest_seconds': programming['rest_seconds'],
            'load_percentage': programming['load_pct']
        }
    
    def get_workout_split(self, days_per_week: int, fitness_level: str, fitness_goal: str) -> List[Dict]:
        """Enhanced workout split structure with all day options (1-7 days)"""
        
        if days_per_week == 1:
            return [{
                'day': 'Wednesday',
                'focus': 'Total Body Blast',
                'muscle_groups': ['chest', 'back', 'quadriceps', 'shoulders', 'biceps', 'triceps']
            }]
        
        if days_per_week == 2:
            if fitness_level == 'beginner':
                return [
                    {'day': 'Monday', 'focus': 'Full Body A', 'muscle_groups': ['chest', 'back', 'quadriceps', 'shoulders']},
                    {'day': 'Thursday', 'focus': 'Full Body B', 'muscle_groups': ['chest', 'back', 'quadriceps', 'shoulders']}
                ]
            else:
                return [
                    {'day': 'Monday', 'focus': 'Upper Body', 'muscle_groups': ['chest', 'back', 'shoulders', 'biceps', 'triceps']},
                    {'day': 'Thursday', 'focus': 'Lower Body', 'muscle_groups': ['quadriceps', 'hamstrings', 'glutes', 'calves', 'abdominals']}
                ]
        
        if days_per_week == 3:
            if fitness_level == 'beginner':
                return [
                    {'day': 'Monday', 'focus': 'Full Body A', 'muscle_groups': ['chest', 'back', 'quadriceps']},
                    {'day': 'Wednesday', 'focus': 'Full Body B', 'muscle_groups': ['shoulders', 'biceps', 'triceps', 'abdominals']},
                    {'day': 'Friday', 'focus': 'Full Body C', 'muscle_groups': ['chest', 'back', 'quadriceps']}
                ]
            else:
                return [
                    {'day': 'Monday', 'focus': 'Push', 'muscle_groups': ['chest', 'shoulders', 'triceps']},
                    {'day': 'Wednesday', 'focus': 'Pull', 'muscle_groups': ['back', 'lats', 'biceps', 'forearms']},
                    {'day': 'Friday', 'focus': 'Legs & Core', 'muscle_groups': ['quadriceps', 'hamstrings', 'glutes', 'abdominals', 'calves']}
                ]
        
        if days_per_week == 4:
            if fitness_goal in ['strength', 'muscle-building']:
                return [
                    {'day': 'Monday', 'focus': 'Upper Body A', 'muscle_groups': ['chest', 'shoulders', 'triceps']},
                    {'day': 'Tuesday', 'focus': 'Lower Body A', 'muscle_groups': ['quadriceps', 'hamstrings', 'glutes']},
                    {'day': 'Thursday', 'focus': 'Upper Body B', 'muscle_groups': ['back', 'lats', 'biceps', 'forearms']},
                    {'day': 'Saturday', 'focus': 'Lower Body B', 'muscle_groups': ['quadriceps', 'calves', 'abdominals']}
                ]
            else:
                return [
                    {'day': 'Monday', 'focus': 'Full Body Circuit', 'muscle_groups': ['chest', 'back', 'quadriceps']},
                    {'day': 'Tuesday', 'focus': 'Cardio & Core', 'muscle_groups': ['abdominals', 'cardio']},
                    {'day': 'Thursday', 'focus': 'Full Body Strength', 'muscle_groups': ['shoulders', 'quadriceps', 'biceps', 'triceps']},
                    {'day': 'Saturday', 'focus': 'HIIT & Conditioning', 'muscle_groups': ['chest', 'back', 'quadriceps']}
                ]
        
        if days_per_week == 5:
            if fitness_level == 'beginner':
                return [
                    {'day': 'Monday', 'focus': 'Upper Push', 'muscle_groups': ['chest', 'shoulders', 'triceps']},
                    {'day': 'Tuesday', 'focus': 'Lower Body', 'muscle_groups': ['quadriceps', 'hamstrings', 'glutes']},
                    {'day': 'Thursday', 'focus': 'Upper Pull', 'muscle_groups': ['back', 'biceps']},
                    {'day': 'Friday', 'focus': 'Core & Cardio', 'muscle_groups': ['abdominals', 'lower back']},
                    {'day': 'Saturday', 'focus': 'Full Body', 'muscle_groups': ['chest', 'back', 'quadriceps', 'shoulders']}
                ]
            else:
                return [
                    {'day': 'Monday', 'focus': 'Chest & Triceps', 'muscle_groups': ['chest', 'triceps']},
                    {'day': 'Tuesday', 'focus': 'Back & Biceps', 'muscle_groups': ['back', 'lats', 'biceps']},
                    {'day': 'Wednesday', 'focus': 'Legs', 'muscle_groups': ['quadriceps', 'hamstrings', 'glutes', 'calves']},
                    {'day': 'Thursday', 'focus': 'Shoulders & Core', 'muscle_groups': ['shoulders', 'abdominals', 'traps']},
                    {'day': 'Saturday', 'focus': 'Full Body', 'muscle_groups': ['chest', 'back', 'quadriceps', 'shoulders']}
                ]
        
        if days_per_week == 6:
            return [
                {'day': 'Monday', 'focus': 'Push A', 'muscle_groups': ['chest', 'shoulders', 'triceps']},
                {'day': 'Tuesday', 'focus': 'Pull A', 'muscle_groups': ['back', 'lats', 'biceps']},
                {'day': 'Wednesday', 'focus': 'Legs A', 'muscle_groups': ['quadriceps', 'hamstrings', 'glutes']},
                {'day': 'Thursday', 'focus': 'Push B', 'muscle_groups': ['chest', 'shoulders', 'triceps']},
                {'day': 'Friday', 'focus': 'Pull B', 'muscle_groups': ['back', 'lats', 'biceps', 'forearms']},
                {'day': 'Saturday', 'focus': 'Legs B & Core', 'muscle_groups': ['quadriceps', 'calves', 'abdominals']}
            ]
        
        if days_per_week == 7:
            return [
                {'day': 'Monday', 'focus': 'Chest & Triceps', 'muscle_groups': ['chest', 'triceps']},
                {'day': 'Tuesday', 'focus': 'Back & Biceps', 'muscle_groups': ['back', 'lats', 'biceps']},
                {'day': 'Wednesday', 'focus': 'Active Recovery', 'type': 'recovery', 
                 'description': 'Light yoga, stretching, or 20-min walk at easy pace'},
                {'day': 'Thursday', 'focus': 'Shoulders & Core', 'muscle_groups': ['shoulders', 'abdominals', 'traps']},
                {'day': 'Friday', 'focus': 'Legs', 'muscle_groups': ['quadriceps', 'hamstrings', 'glutes', 'calves']},
                {'day': 'Saturday', 'focus': 'Arms & Abs', 'muscle_groups': ['biceps', 'triceps', 'forearms', 'abdominals']},
                {'day': 'Sunday', 'focus': 'Active Recovery', 'type': 'recovery',
                 'description': 'Swimming, easy cycling, or mobility work'}
            ]
        
        return self.get_workout_split(3, fitness_level, fitness_goal)
    
    def get_contraindication_info(self, physical_limitations: List[str]) -> Dict:
        """
        Get comprehensive contraindication information for filtering
        Returns: {
            'excluded_exercises': [exercise_ids without modifications],
            'modified_exercises': {exercise_id: modification_text},
            'categories': [category names]
        }
        """
        if not physical_limitations or 'none' in physical_limitations:
            return {
                'excluded_exercises': [],
                'modified_exercises': {},
                'categories': []
            }
        
        conn = sqlite3.connect(self.exercise_db)
        conn.row_factory = sqlite3.Row
        
        # Get exercises with contraindications in selected categories
        placeholders = ','.join('?' * len(physical_limitations))
        
        # Find exercises with contraindications
        contraindicated_query = f'''
            SELECT DISTINCT ec.exercise_id
            FROM exercise_contraindications ec
            JOIN contraindications c ON ec.contraindication_id = c.contraindication_id
            JOIN modification_categories mc ON c.category_id = mc.category_id
            WHERE mc.category_name IN ({placeholders})
        '''
        contraindicated = conn.execute(contraindicated_query, physical_limitations).fetchall()
        contraindicated_ids = [row['exercise_id'] for row in contraindicated]
        
        # Find which of these have modifications in the same categories
        modified_exercises = {}
        for exercise_id in contraindicated_ids:
            mod_query = f'''
                SELECT em.modification_text, mc.category_name
                FROM exercise_modifications em
                JOIN modification_categories mc ON em.category_id = mc.category_id
                WHERE em.exercise_id = ?
                    AND mc.category_name IN ({placeholders})
                    AND mc.category_type = 'contraindication'
            '''
            mods = conn.execute(mod_query, [exercise_id] + physical_limitations).fetchall()
            
            if mods:
                # Store all modifications for this exercise
                modified_exercises[exercise_id] = [
                    {'category': mod['category_name'], 'text': mod['modification_text']}
                    for mod in mods
                ]
        
        # Exercises to exclude (have contraindications but NO modifications)
        excluded = [ex_id for ex_id in contraindicated_ids if ex_id not in modified_exercises]
        
        conn.close()
        
        return {
            'excluded_exercises': excluded,
            'modified_exercises': modified_exercises,
            'categories': physical_limitations
        }
    
    def filter_exercises_by_equipment(self, available_equipment: List[str]) -> List[str]:
        """Build list of equipment for filtering"""
        if not available_equipment:
            return ['body only']
        
        equipment_mapping = {
            'bodyweight': 'body only',
            'dumbbells': 'dumbbell',
            'resistance_bands': 'bands',
            'kettlebells': 'kettlebells',
            'barbell': 'barbell',
            'pull_up_bar': 'cable',
            'exercise_ball': 'exercise ball',
            'yoga_mat': 'body only'
        }
        
        db_equipment = [equipment_mapping.get(eq, eq) for eq in available_equipment]
        db_equipment.append('body only')
        
        return list(set(db_equipment))
    
    def get_eligible_exercises(self, user_profile: Dict, fitness_level: str, 
                              contraindication_info: Dict) -> List[Dict]:
        """Get all exercises with contraindication priority"""
        conn = sqlite3.connect(self.exercise_db)
        conn.row_factory = sqlite3.Row
        
        excluded_ids = contraindication_info['excluded_exercises']
        equipment_list = self.filter_exercises_by_equipment(user_profile['available_equipment'])
        
        level_map = {
            'beginner': ['beginner'],
            'intermediate': ['beginner', 'intermediate'],
            'advanced': ['beginner', 'intermediate', 'expert']
        }
        allowed_levels = level_map[fitness_level]
        
        excluded_placeholder = ','.join('?' * len(excluded_ids)) if excluded_ids else "''"
        equipment_placeholder = ','.join('?' * len(equipment_list))
        level_placeholder = ','.join('?' * len(allowed_levels))
        
        query = f'''
            SELECT DISTINCT
                e.id,
                e.name,
                e.level,
                e.equipment,
                e.category,
                e.mechanic,
                e.force,
                e.instructions,
                e.images,
                GROUP_CONCAT(DISTINCT pm.muscle_name) as primary_muscles,
                GROUP_CONCAT(DISTINCT sm.muscle_name) as secondary_muscles,
                p.sets_beginner, p.sets_intermediate, p.sets_advanced,
                p.reps_strength, p.reps_hypertrophy, p.reps_endurance,
                p.rest_beginner, p.rest_intermediate, p.rest_advanced,
                p.calories_beginner, p.calories_intermediate, p.calories_advanced,
                p.time_beginner, p.time_intermediate, p.time_advanced
            FROM exercises e
            LEFT JOIN exercise_primary_muscles epm ON e.id = epm.exercise_id
            LEFT JOIN muscles pm ON epm.muscle_id = pm.muscle_id
            LEFT JOIN exercise_secondary_muscles esm ON e.id = esm.exercise_id
            LEFT JOIN muscles sm ON esm.muscle_id = sm.muscle_id
            LEFT JOIN exercise_programming p ON e.id = p.exercise_id
            WHERE e.category IN ('strength', 'cardio', 'plyometrics')
                AND e.level IN ({level_placeholder})
                AND e.equipment IN ({equipment_placeholder})
                {f"AND e.id NOT IN ({excluded_placeholder})" if excluded_ids else ""}
            GROUP BY e.id
        '''
        
        params = allowed_levels + equipment_list
        if excluded_ids:
            params += excluded_ids
        
        exercises = conn.execute(query, params).fetchall()
        conn.close()
        
        result = []
        for ex in exercises:
            ex_dict = dict(ex)
            # Add contraindication priority flag
            if ex_dict['id'] in contraindication_info['modified_exercises']:
                ex_dict['contraindication_status'] = 'modified'
                ex_dict['modifications'] = contraindication_info['modified_exercises'][ex_dict['id']]
            else:
                ex_dict['contraindication_status'] = 'safe'
                ex_dict['modifications'] = []
            result.append(ex_dict)
        
        return result
    
    def score_exercise(self, exercise: Dict, target_muscles: List[str], 
                       fitness_goal: str, already_selected: List[str]) -> float:
        """Score exercise with contraindication priority"""
        score = 100.0
        
        # PRIORITY: Contraindication status
        if exercise['contraindication_status'] == 'safe':
            score += 50  # Highest priority
        elif exercise['contraindication_status'] == 'modified':
            score += 25  # Second priority
        
        primary_muscles = exercise['primary_muscles'].split(',') if exercise['primary_muscles'] else []
        
        # Muscle group match
        muscle_match = len(set(primary_muscles) & set(target_muscles))
        score += muscle_match * 25
        
        # Compound movement bonus
        if exercise['mechanic'] == 'compound':
            score += 30
            if fitness_goal in ['muscle-building', 'strength']:
                score += 20
        
        # Goal alignment
        if fitness_goal == 'weight-loss' and exercise['category'] in ['cardio', 'plyometrics']:
            score += 20
        elif fitness_goal in ['muscle-building', 'strength'] and exercise['category'] == 'strength':
            score += 15
        elif fitness_goal == 'endurance' and exercise['category'] in ['cardio', 'plyometrics']:
            score += 15
        
        # Equipment preference
        if exercise['equipment'] in ['body only', None]:
            score += 8
        
        # Avoid repetition
        if exercise['id'] in already_selected:
            score -= 100
        
        # Slight randomness
        score += random.uniform(-3, 3)
        
        return score
    
    def select_exercises_for_day(self, eligible_exercises: List[Dict], 
                                 day_info: Dict, fitness_level: str, 
                                 fitness_goal: str, target_count: int,
                                 already_selected: List[str]) -> Tuple[List[Dict], List[str]]:
        """
        Select exercises for a day and return warnings for missing muscle groups
        Returns: (selected_exercises, warnings)
        """
        if day_info.get('type') == 'recovery':
            return [], []
        
        target_muscles = day_info['muscle_groups']
        warnings = []
        
        # Check if we have exercises for each target muscle
        available_muscles = set()
        for ex in eligible_exercises:
            primary = ex['primary_muscles'].split(',') if ex['primary_muscles'] else []
            available_muscles.update([m.strip() for m in primary])
        
        missing_muscles = set(target_muscles) - available_muscles
        if missing_muscles:
            for muscle in missing_muscles:
                warnings.append(
                    f"⚕️ {muscle.title()}: To exercise this muscle group, consult your doctor or "
                    f"physical therapist for appropriate exercises that fit your needs."
                )
        
        # Filter exercises for this day
        relevant_exercises = []
        for ex in eligible_exercises:
            primary = ex['primary_muscles'].split(',') if ex['primary_muscles'] else []
            if any(muscle.strip() in target_muscles for muscle in primary):
                relevant_exercises.append(ex)
        
        if not relevant_exercises:
            return [], warnings
        
        # Goal-specific ratios
        exercise_ratios = {
            'strength': {'compound': 0.70, 'isolation': 0.30},
            'muscle-building': {'compound': 0.50, 'isolation': 0.50},
            'weight-loss': {'compound': 0.60, 'isolation': 0.40},
            'endurance': {'compound': 0.50, 'isolation': 0.50},
            'general_fitness': {'compound': 0.55, 'isolation': 0.45},
            'maintenance': {'compound': 0.50, 'isolation': 0.50}
        }
        
        ratio = exercise_ratios.get(fitness_goal, {'compound': 0.55, 'isolation': 0.45})
        num_compound = max(1, int(target_count * ratio['compound']))
        num_isolation = target_count - num_compound
        
        # Separate by type
        compound_exercises = [ex for ex in relevant_exercises if ex['mechanic'] == 'compound']
        isolation_exercises = [ex for ex in relevant_exercises if ex['mechanic'] == 'isolation']
        
        # Score and sort
        compound_exercises.sort(
            key=lambda x: self.score_exercise(x, target_muscles, fitness_goal, already_selected), 
            reverse=True
        )
        isolation_exercises.sort(
            key=lambda x: self.score_exercise(x, target_muscles, fitness_goal, already_selected), 
            reverse=True
        )
        
        # Select exercises
        selected = []
        selected.extend(compound_exercises[:num_compound])
        selected.extend(isolation_exercises[:num_isolation])
        
        # Fill remaining slots
        if len(selected) < target_count:
            remaining = [ex for ex in relevant_exercises 
                        if ex['id'] not in [s['id'] for s in selected]]
            remaining.sort(
                key=lambda x: self.score_exercise(x, target_muscles, fitness_goal, already_selected),
                reverse=True
            )
            selected.extend(remaining[:target_count - len(selected)])
        
        return selected, warnings
    
    def calculate_programming(self, exercise: Dict, fitness_level: str, 
                             fitness_goal: str, goal_programming: Dict) -> Dict:
        """Determine sets, reps, rest for an exercise"""
        sets = goal_programming['sets_per_exercise']
        rest = goal_programming['rest_seconds']
        reps_min = goal_programming['reps_min']
        reps_max = goal_programming['reps_max']
        
        reps = int((reps_min + reps_max) / 2)
        
        return {
            'sets': sets,
            'reps': reps,
            'reps_range': f"{reps_min}-{reps_max}",
            'rest_seconds': rest
        }
    
    def calculate_exercise_calories(self, exercise: Dict, programming: Dict, 
                                   weight_lbs: float, fitness_level: str) -> Tuple[float, float]:
        """Calculate time and calories for an exercise"""
        weight_kg = weight_lbs * 0.453592
        
        cal_per_min = exercise.get(f'calories_{fitness_level}', 5.0)
        if not cal_per_min:
            if exercise['mechanic'] == 'compound':
                cal_per_min = {'beginner': 5.0, 'intermediate': 6.0, 'advanced': 7.0}[fitness_level]
            else:
                cal_per_min = {'beginner': 3.5, 'intermediate': 4.5, 'advanced': 5.5}[fitness_level]
        
        time_per_set = (programming['reps'] * 3 + programming['rest_seconds']) / 60
        total_time = time_per_set * programming['sets']
        calories = cal_per_min * total_time
        
        return total_time, calories
    
    def generate_weekly_plan(self, user_id: int) -> Dict:
        """Main method to generate complete weekly workout plan"""
        user_profile = self.get_user_profile(user_id)
        fitness_level = self.determine_fitness_level(user_profile['activity_level'], user_profile['age'])
        
        workout_days, warning_flag, warning_message = self.determine_workout_days(
            user_profile['workout_schedule'],
            user_profile['fitness_goal'],
            fitness_level,
            user_profile['age']
        )
        
        volume_config = self.calculate_daily_volume(workout_days, user_profile['fitness_goal'], fitness_level)
        split = self.get_workout_split(workout_days, fitness_level, user_profile['fitness_goal'])
        
        # NEW: Get contraindication info
        contraindication_info = self.get_contraindication_info(user_profile['physical_limitations'])
        
        # Get eligible exercises with contraindication filtering
        eligible_exercises = self.get_eligible_exercises(user_profile, fitness_level, contraindication_info)
        
        if not eligible_exercises:
            raise ValueError("No eligible exercises found with current filters")
        
        weekly_plan = {
            'user_id': user_id,
            'week_of': datetime.now().strftime('%Y-%m-%d'),
            'fitness_level': fitness_level,
            'workout_days_per_week': workout_days,
            'user_preference': user_profile['workout_schedule'],
            'physical_limitations': user_profile['physical_limitations'],
            'warning_flag': warning_flag,
            'warning_message': warning_message,
            'programming_notes': {
                'rep_range': f"{volume_config['reps_min']}-{volume_config['reps_max']}",
                'rest_seconds': volume_config['rest_seconds'],
                'load_percentage': volume_config['load_percentage']
            },
            'total_weekly_calories': 0,
            'days': []
        }
        
        already_selected = []
        
        for day_info in split:
            if day_info.get('type') == 'recovery':
                weekly_plan['days'].append({
                    'day': day_info['day'],
                    'focus': day_info['focus'],
                    'type': 'recovery',
                    'duration_minutes': 20,
                    'estimated_calories': 80,
                    'description': day_info['description']
                })
                continue
            
            # Select exercises with warnings
            exercises, day_warnings = self.select_exercises_for_day(
                eligible_exercises, day_info, fitness_level, 
                user_profile['fitness_goal'], 
                volume_config['exercises_per_day'],
                already_selected
            )
            
            day_exercises = []
            day_calories = 0
            day_duration = 0
            
            for i, exercise in enumerate(exercises, 1):
                programming = self.calculate_programming(
                    exercise, fitness_level, user_profile['fitness_goal'], volume_config
                )
                time, calories = self.calculate_exercise_calories(
                    exercise, programming, user_profile['weight'], fitness_level
                )
                
                ex_data = {
                    'order': i,
                    'id': exercise['id'],
                    'name': exercise['name'],
                    'sets': programming['sets'],
                    'reps': programming['reps'],
                    'reps_range': programming['reps_range'],
                    'rest_seconds': programming['rest_seconds'],
                    'estimated_time_min': round(time, 1),
                    'estimated_calories': round(calories, 1),
                    'instructions': json.loads(exercise['instructions']) if exercise['instructions'] else [],
                    'primary_muscles': exercise['primary_muscles'].split(',') if exercise['primary_muscles'] else [],
                    'equipment': exercise['equipment'],
                    'images': json.loads(exercise['images']) if exercise['images'] else []
                }
                
                # NEW: Add modifications if present
                if exercise['modifications']:
                    ex_data['modifications'] = [
                        {'category': mod['category'], 'text': mod['text']}
                        for mod in exercise['modifications']
                    ]
                
                day_exercises.append(ex_data)
                day_calories += calories
                day_duration += time
                already_selected.append(exercise['id'])
            
            day_data = {
                'day': day_info['day'],
                'focus': day_info['focus'],
                'target_muscles': day_info['muscle_groups'],
                'duration_minutes': round(day_duration, 1),
                'estimated_calories': round(day_calories, 1),
                'exercises': day_exercises
            }
            
            # NEW: Add warnings if any
            if day_warnings:
                day_data['warnings'] = day_warnings
            
            weekly_plan['days'].append(day_data)
            weekly_plan['total_weekly_calories'] += day_calories
        
        # Add rest days
        all_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        workout_day_names = [d['day'] for d in weekly_plan['days']]
        
        for day in all_days:
            if day not in workout_day_names:
                weekly_plan['days'].append({
                    'day': day,
                    'focus': 'Rest Day',
                    'type': 'rest',
                    'duration_minutes': 0,
                    'estimated_calories': 0,
                    'description': 'Complete rest. Your muscles grow during recovery, not during workouts.'
                })
        
        # Sort by day order
        day_order = {day: i for i, day in enumerate(all_days)}
        weekly_plan['days'].sort(key=lambda x: day_order[x['day']])
        
        weekly_plan['total_weekly_calories'] = round(weekly_plan['total_weekly_calories'], 1)
        
        return weekly_plan


def main():
    """Example usage"""
    generator = WorkoutGenerator()
    
    try:
        plan = generator.generate_weekly_plan(user_id=1)
        
        print(f"\n{'='*70}")
        print(f"WEEKLY WORKOUT PLAN - Week of {plan['week_of']}")
        print(f"{'='*70}")
        print(f"Fitness Level: {plan['fitness_level'].title()}")
        print(f"Physical Limitations: {', '.join(plan['physical_limitations']) if plan['physical_limitations'] else 'None'}")
        print(f"Workout Days: {plan['workout_days_per_week']} days/week")
        if plan['warning_message']:
            print(f"\n⚠️  {plan['warning_message']}")
        print(f"\nProgramming: {plan['programming_notes']['rep_range']} reps, "
              f"{plan['programming_notes']['rest_seconds']}s rest, "
              f"{plan['programming_notes']['load_percentage']} 1RM")
        print(f"Total Weekly Calories: {plan['total_weekly_calories']} kcal")
        print(f"{'='*70}\n")
        
        for day in plan['days']:
            print(f"\n{day['day'].upper()} - {day['focus']}")
            
            if day.get('type') in ['rest', 'recovery']:
                print(f"  Type: {day.get('type', 'rest').title()}")
                if 'description' in day:
                    print(f"  {day['description']}")
            else:
                print(f"Duration: {day['duration_minutes']} min | Calories: {day['estimated_calories']} kcal")
                
                # Show warnings if any
                if 'warnings' in day:
                    print(f"\n  WARNINGS:")
                    for warning in day['warnings']:
                        print(f"  {warning}")
                
                print(f"\n  Exercises:")
                for ex in day['exercises']:
                    print(f"  {ex['order']}. {ex['name']}")
                    print(f"     {ex['sets']} sets × {ex['reps_range']} reps (Rest: {ex['rest_seconds']}s)")
                    print(f"     Muscles: {', '.join(ex['primary_muscles'])}")
                    
                    # Show modifications if present
                    if 'modifications' in ex:
                        print(f"     ⚕️ MODIFICATIONS:")
                        for mod in ex['modifications']:
                            print(f"        • {mod['category']}: {mod['text']}")
            
            print("-" * 70)
        
        output_file = f"workout_plan_user_{plan['user_id']}.json"
        with open(output_file, 'w') as f:
            json.dump(plan, f, indent=2)
        print(f"\n✅ Full plan saved to {output_file}")
        
    except Exception as e:
        print(f"❌ Error generating workout plan: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
