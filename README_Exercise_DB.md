# Exercise Database Documentation

**Database File:** `exercises.db` (SQLite 3.x)

A relational database storing comprehensive exercise information including instructions, muscle targeting, contraindications, modifications, and programming recommendations.

---

## Quick Overview

**Core Data:**
- ~600-900 exercises with detailed instructions
- 17 muscle groups (primary & secondary targeting)
- Contraindications & safety information
- Exercise modifications (easier/harder/injury-specific)
- Programming recommendations (sets, reps, rest periods)

**Key Features:**
- Filter exercises by level, equipment, muscle group
- Identify exercises safe for specific injuries/conditions
- Get modifications for user limitations
- Access form cues, safety notes, and common mistakes

---

## Core Tables

### 1. `exercises` - Main Exercise Data

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Primary key (e.g., "3_4_Sit-Up") |
| `name` | TEXT | Exercise name |
| `level` | TEXT | "beginner", "intermediate", "expert" |
| `equipment` | TEXT | Required equipment (see options below) |
| `category` | TEXT | "strength", "stretching", "cardio", etc. |
| `force` | TEXT | "push", "pull", "static", or NULL |
| `mechanic` | TEXT | "compound", "isolation", or NULL |
| `instructions` | TEXT | JSON array of step-by-step instructions |
| `images` | TEXT | JSON array of image paths |

**Equipment Options:** `body only`, `dumbbell`, `barbell`, `kettlebells`, `cable`, `machine`, `bands`, `medicine ball`, `exercise ball`, `foam roll`, `e-z curl bar`, `other`

**Categories:** `strength`, `stretching`, `cardio`, `powerlifting`, `olympic weightlifting`, `strongman`, `plyometrics`

---

### 2. `muscles` - Muscle Groups

| Column | Type | Description |
|--------|------|-------------|
| `muscle_id` | INTEGER | Primary key |
| `muscle_name` | TEXT | Muscle name (unique) |

**Valid Muscles:** abdominals, abductors, adductors, biceps, calves, chest, forearms, glutes, hamstrings, lats, lower back, middle back, neck, quadriceps, shoulders, traps, triceps

---

### 3. `exercise_primary_muscles` & `exercise_secondary_muscles`

Junction tables linking exercises to muscles (many-to-many).

| Column | Type | Description |
|--------|------|-------------|
| `exercise_id` | TEXT | Foreign key to exercises.id |
| `muscle_id` | INTEGER | Foreign key to muscles.muscle_id |

---

### 4. `contraindications` - Health Conditions

| Column | Type | Description |
|--------|------|-------------|
| `contraindication_id` | INTEGER | Primary key |
| `contraindication_name` | TEXT | Condition name (unique) |
| `category_id` | INTEGER | Links to modification_categories |
| `severity` | TEXT | "low", "moderate", "high" |

---

### 5. `exercise_contraindications`

Links exercises to health conditions they may aggravate.

| Column | Type | Description |
|--------|------|-------------|
| `exercise_id` | TEXT | Foreign key to exercises.id |
| `contraindication_id` | INTEGER | Foreign key to contraindications |
| `specific_reason` | TEXT | Why this exercise is contraindicated |
| `severity` | TEXT | "low", "moderate", "high" |

---

### 6. `modification_categories`

Categories for contraindications and difficulty modifications.

| Column | Type | Description |
|--------|------|-------------|
| `category_id` | INTEGER | Primary key |
| `category_name` | TEXT | Category name (unique) |
| `category_type` | TEXT | "contraindication" or "difficulty" |

**Contraindication Categories:**
- back and spinal issues
- knee and foot issues  
- chest and shoulder issues
- hip or lumbar issues
- arm and hand issues
- Pregnancy
- chronical or neurological issues

**Difficulty Categories:** easier, harder

---

### 7. `exercise_modifications`

Exercise variations for different needs.

| Column | Type | Description |
|--------|------|-------------|
| `exercise_id` | TEXT | Foreign key to exercises.id |
| `category_id` | INTEGER | Foreign key to modification_categories |
| `modification_text` | TEXT | How to modify the exercise |

---

### 8. `exercise_programming`

Programming recommendations for sets, reps, and rest.

| Column | Type | Description |
|--------|------|-------------|
| `exercise_id` | TEXT | Primary key, foreign key to exercises.id |
| `sets_beginner/intermediate/advanced` | INTEGER | Recommended sets |
| `reps_strength/hypertrophy/endurance` | INTEGER | Recommended reps |
| `rest_beginner/intermediate/advanced` | INTEGER | Rest period (seconds) |
| `time_beginner/intermediate/advanced` | INTEGER | Estimated duration (minutes) |
| `calories_beginner/intermediate/advanced` | REAL | Calories per minute |

---

### 9. `exercise_safety_notes`, `exercise_form_cues`, `exercise_common_mistakes`

Additional guidance for proper exercise execution.

| Table | Columns | Purpose |
|-------|---------|---------|
| safety_notes | exercise_id, note_text, display_order | Safety warnings |
| form_cues | exercise_id, cue_text, display_order | Technique tips |
| common_mistakes | exercise_id, mistake_text, display_order | What to avoid |

---

## Essential Queries

### Find Exercises by Criteria

```sql
-- Beginner exercises with specific equipment
SELECT id, name, category
FROM exercises
WHERE level = 'beginner' 
  AND equipment = 'dumbbell'
ORDER BY name;
```

### Get Exercise with Muscles

```sql
SELECT 
    e.name,
    GROUP_CONCAT(DISTINCT pm.muscle_name) as primary_muscles,
    GROUP_CONCAT(DISTINCT sm.muscle_name) as secondary_muscles
FROM exercises e
LEFT JOIN exercise_primary_muscles epm ON e.id = epm.exercise_id
LEFT JOIN muscles pm ON epm.muscle_id = pm.muscle_id
LEFT JOIN exercise_secondary_muscles esm ON e.id = esm.exercise_id
LEFT JOIN muscles sm ON esm.muscle_id = sm.muscle_id
WHERE e.id = 'Barbell_Squat'
GROUP BY e.id;
```

### Find Safe Exercises for Condition

```sql
-- Exercises WITHOUT back pain contraindication
SELECT DISTINCT e.id, e.name, e.level
FROM exercises e
WHERE e.id NOT IN (
    SELECT ec.exercise_id
    FROM exercise_contraindications ec
    JOIN contraindications c ON ec.contraindication_id = c.contraindication_id
    WHERE c.contraindication_name LIKE '%back%'
)
AND e.level = 'beginner'
ORDER BY e.name;
```

### Get Contraindications for Exercise

```sql
SELECT 
    e.name,
    c.contraindication_name,
    c.severity,
    ec.specific_reason
FROM exercises e
JOIN exercise_contraindications ec ON e.id = ec.exercise_id
JOIN contraindications c ON ec.contraindication_id = c.contraindication_id
WHERE e.id = 'Barbell_Squat'
ORDER BY c.severity DESC;
```

### Get Exercise Modifications

```sql
SELECT 
    e.name,
    mc.category_name,
    em.modification_text
FROM exercises e
JOIN exercise_modifications em ON e.id = em.exercise_id
JOIN modification_categories mc ON em.category_id = mc.category_id
WHERE e.id = 'Push-Ups'
ORDER BY mc.category_type, mc.category_name;
```

### Get Complete Exercise Profile

```sql
SELECT 
    e.id,
    e.name,
    e.level,
    e.equipment,
    e.category,
    e.instructions,
    GROUP_CONCAT(DISTINCT pm.muscle_name) as primary_muscles,
    p.sets_intermediate,
    p.reps_hypertrophy,
    p.rest_intermediate
FROM exercises e
LEFT JOIN exercise_primary_muscles epm ON e.id = epm.exercise_id
LEFT JOIN muscles pm ON epm.muscle_id = pm.muscle_id
LEFT JOIN exercise_programming p ON e.id = p.exercise_id
WHERE e.name LIKE '%Press%'
GROUP BY e.id
LIMIT 5;
```

### Build Safe Workout for User

```sql
-- Chest exercises safe for shoulder issues, with modifications
SELECT DISTINCT
    e.name,
    e.equipment,
    GROUP_CONCAT(DISTINCT pm.muscle_name) as muscles,
    em.modification_text as shoulder_safe_modification
FROM exercises e
JOIN exercise_primary_muscles epm ON e.id = epm.exercise_id
JOIN muscles pm ON epm.muscle_id = pm.muscle_id
LEFT JOIN exercise_modifications em ON e.id = em.exercise_id
LEFT JOIN modification_categories mc ON em.category_id = mc.category_id
WHERE pm.muscle_name = 'chest'
    AND e.level = 'beginner'
    AND e.id NOT IN (
        SELECT ec.exercise_id
        FROM exercise_contraindications ec
        JOIN contraindications c ON ec.contraindication_id = c.contraindication_id
        WHERE c.contraindication_name LIKE '%shoulder%'
          AND c.severity = 'high'
    )
    AND (mc.category_name = 'chest and shoulder issues' OR mc.category_name IS NULL)
GROUP BY e.id
ORDER BY e.name;
```

---

## Entity Relationships

```
exercises (1) ──→ (many) exercise_primary_muscles (many) ──→ (1) muscles
exercises (1) ──→ (many) exercise_secondary_muscles (many) ──→ (1) muscles
exercises (1) ──→ (many) exercise_contraindications (many) ──→ (1) contraindications
exercises (1) ──→ (many) exercise_modifications (many) ──→ (1) modification_categories
exercises (1) ──→ (0..1) exercise_programming
exercises (1) ──→ (many) exercise_safety_notes
exercises (1) ──→ (many) exercise_form_cues
exercises (1) ──→ (many) exercise_common_mistakes
contraindications (many) ──→ (1) modification_categories
```

---

## JSON Format Examples

**Instructions Array:**
```json
["Step 1: Position yourself correctly", "Step 2: Execute the movement", "Step 3: Return to start"]
```

**Images Array:**
```json
["Exercise_Name/0.jpg", "Exercise_Name/1.jpg"]
```

---

## Database Statistics

- **~600-900** exercises
- **17** muscle groups
- **~850** primary muscle relationships
- **~400-500** secondary muscle relationships  
- **10** modification categories
- **~200-300** contraindications
- **~2,400+** exercise modifications
- Multiple safety notes, form cues, and mistakes per exercise

---

## Notes

- All muscle names are lowercase
- Exercise IDs use underscores (e.g., "3_4_Sit-Up")
- Image paths are relative to image directory
- NULL equipment means bodyweight only
- Severity levels: low (minor concern) → moderate (modification recommended) → high (avoid/consult professional)
- Programming fields are nullable (not all exercises have recommendations)

---

## Version

**Database Version:** 2.0  
**Last Updated:** 2025-01-06  
**Compatible with:** SQLite 3.x
