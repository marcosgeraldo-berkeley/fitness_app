import sqlite3
import json
from datetime import datetime
from database import get_db
from sqlalchemy import text

def get_db_connection():
    conn = sqlite3.connect('fitplan.db')
    conn.row_factory = sqlite3.Row  # This is the critical line
    return conn

def read_users():
    db = get_db()
    # Read all users from the postgres database
    users = db.execute(text("SELECT * FROM users")).fetchall()
    print("=" * 50)
    print(f"USERS TABLE - {len(users)} records found")
    print("=" * 50)
    if not users:
        print("No users found in database.")
        return
    for user in users:
        print(f"\nUser ID: {user['id']}")
        print(f"Name: {user['name']}")
        print(f"Email  : {user['email']}")
        print(f"Height : {user['height']}")
        print(f"Weight : {user['weight']}")
        print(f"Created: {user['created_at']}")
        print(f"Fitness Goals: {user['fitness_goals']}")
        
        # Handle JSON fields if they exist
        if 'dietary_restrictions' in user.keys() and user['dietary_restrictions']:
            try:
                restrictions = json.loads(user['dietary_restrictions'])
                print(f"Dietary Restrictions: {restrictions}")
            except json.JSONDecodeError:
                print(f"Dietary Restrictions: {user['dietary_restrictions']} (raw)")

        if 'available_equipment' in user.keys() and user['available_equipment']:
            try:
                equipment = json.loads(user['available_equipment'])
                print(f"Equipment: {equipment}")
            except json.JSONDecodeError:
                print(f"Equipment: {user['available_equipment']} (raw)")
        print(f"BMR     : {user['bmr']}")
        print(f"TDEE    : {user['tdee']}")
        print(f"Cals    : {user['caloric_target']}")
        print(f"Proteins: {user['protein_target_g']}")
        print(f"Carbs   : {user['carbs_target_g']}")
        print(f"Fat     : {user['fat_target_g']}")
        print("-" * 30)

if __name__ == "__main__":
    read_users()