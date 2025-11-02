"""Centralized database schema definition for FitPlan."""

DATABASE_SCHEMA = {
    "users": {
        "create": """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            gender TEXT,
            age INTEGER,
            height NUMERIC(5, 2),
            weight NUMERIC(6, 2),
            activity_level TEXT,
            fitness_goals TEXT,
            available_equipment TEXT,
            workout_schedule TEXT,
            physical_limitations TEXT,
            dietary_restrictions TEXT,
            food_preferences TEXT,
            food_exclusions TEXT,
            bmr NUMERIC(10, 2),
            tdee NUMERIC(10, 2),
            caloric_target NUMERIC(10, 2),
            protein_target_g NUMERIC(10, 2),
            carbs_target_g NUMERIC(10, 2),
            fat_target_g NUMERIC(10, 2),
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            privacy_accepted BOOLEAN DEFAULT FALSE,
            privacy_accepted_at TIMESTAMPTZ
        );
        """,
        "columns": {
            "name": "ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;",
            "email": "ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;",
            "password": "ALTER TABLE users ADD COLUMN IF NOT EXISTS password TEXT;",
            "gender": "ALTER TABLE users ADD COLUMN IF NOT EXISTS gender TEXT;",
            "age": "ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER;",
            "height": "ALTER TABLE users ADD COLUMN IF NOT EXISTS height NUMERIC(5, 2);",
            "weight": "ALTER TABLE users ADD COLUMN IF NOT EXISTS weight NUMERIC(6, 2);",
            "activity_level": "ALTER TABLE users ADD COLUMN IF NOT EXISTS activity_level TEXT;",
            "fitness_goals": "ALTER TABLE users ADD COLUMN IF NOT EXISTS fitness_goals TEXT;",
            "available_equipment": "ALTER TABLE users ADD COLUMN IF NOT EXISTS available_equipment TEXT;",
            "workout_schedule": "ALTER TABLE users ADD COLUMN IF NOT EXISTS workout_schedule TEXT;",
            "physical_limitations": "ALTER TABLE users ADD COLUMN IF NOT EXISTS physical_limitations TEXT;",
            "dietary_restrictions": "ALTER TABLE users ADD COLUMN IF NOT EXISTS dietary_restrictions TEXT;",
            "food_preferences": "ALTER TABLE users ADD COLUMN IF NOT EXISTS food_preferences TEXT;",
            "food_exclusions": "ALTER TABLE users ADD COLUMN IF NOT EXISTS food_exclusions TEXT;",
            "bmr": "ALTER TABLE users ADD COLUMN IF NOT EXISTS bmr NUMERIC(10, 2);",
            "tdee": "ALTER TABLE users ADD COLUMN IF NOT EXISTS tdee NUMERIC(10, 2);",
            "caloric_target": "ALTER TABLE users ADD COLUMN IF NOT EXISTS caloric_target NUMERIC(10, 2);",
            "protein_target_g": "ALTER TABLE users ADD COLUMN IF NOT EXISTS protein_target_g NUMERIC(10, 2);",
            "carbs_target_g": "ALTER TABLE users ADD COLUMN IF NOT EXISTS carbs_target_g NUMERIC(10, 2);",
            "fat_target_g": "ALTER TABLE users ADD COLUMN IF NOT EXISTS fat_target_g NUMERIC(10, 2);",
            "created_at": "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
            "updated_at": "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
            "privacy_accepted": "ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy_accepted BOOLEAN DEFAULT FALSE;",
            "privacy_accepted_at": "ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy_accepted_at TIMESTAMPTZ;",
        },
        "indexes": [
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email);",
        ],
    },
    "workout_plans": {
        "create": """
        CREATE TABLE IF NOT EXISTS workout_plans (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            week_date DATE NOT NULL,
            plan_data TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, week_date)
        );
        """,
        "columns": {
            "user_id": "ALTER TABLE workout_plans ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;",
            "week_date": "ALTER TABLE workout_plans ADD COLUMN IF NOT EXISTS week_date DATE;",
            "plan_data": "ALTER TABLE workout_plans ADD COLUMN IF NOT EXISTS plan_data TEXT;",
            "created_at": "ALTER TABLE workout_plans ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
            "updated_at": "ALTER TABLE workout_plans ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
        },
        "indexes": [
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_workout_plans_user_week ON workout_plans (user_id, week_date);",
        ],
    },
    "meal_plans": {
        "create": """
        CREATE TABLE IF NOT EXISTS meal_plans (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            week_date DATE NOT NULL,
            plan_data TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, week_date)
        );
        """,
        "columns": {
            "user_id": "ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;",
            "week_date": "ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS week_date DATE;",
            "plan_data": "ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS plan_data TEXT;",
            "created_at": "ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
            "updated_at": "ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
        },
        "indexes": [
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_meal_plans_user_week ON meal_plans (user_id, week_date);",
        ],
    },
    "grocery_lists": {
        "create": """
        CREATE TABLE IF NOT EXISTS grocery_lists (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            week_date DATE NOT NULL,
            grocery_data TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, week_date)
        );
        """,
        "columns": {
            "user_id": "ALTER TABLE grocery_lists ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;",
            "week_date": "ALTER TABLE grocery_lists ADD COLUMN IF NOT EXISTS week_date DATE;",
            "grocery_data": "ALTER TABLE grocery_lists ADD COLUMN IF NOT EXISTS grocery_data TEXT;",
            "created_at": "ALTER TABLE grocery_lists ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
            "updated_at": "ALTER TABLE grocery_lists ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
        },
        "indexes": [
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_grocery_lists_user_week ON grocery_lists (user_id, week_date);",
        ],
    },
}
