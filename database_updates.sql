-- Script to change tables 
ALTER TABLE users ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC';
ALTER TABLE workout_plans RENAME COLUMN week_date TO start_date;
ALTER TABLE meal_plans RENAME COLUMN week_date TO start_date;
ALTER TABLE grocery_lists RENAME COLUMN week_date TO start_date;

-- Remove week_date 
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'workout_plans' AND column_name = 'week_date'
    ) THEN
        ALTER TABLE workout_plans DROP COLUMN week_date;
        RAISE NOTICE 'Dropped week_date column from workout_plans';
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'meal_plans' AND column_name = 'week_date'
    ) THEN
        ALTER TABLE meal_plans DROP COLUMN week_date;
        RAISE NOTICE 'Dropped week_date column from meal_plans';
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'grocery_lists' AND column_name = 'week_date'
    ) THEN
        ALTER TABLE grocery_lists DROP COLUMN week_date;
        RAISE NOTICE 'Dropped week_date column from grocery_lists';
    END IF;
END $$;

-- Remove potential duplicates
DELETE FROM workout_plans
WHERE id IN (
    SELECT wp.id
    FROM workout_plans wp
    INNER JOIN users u ON wp.user_id = u.id
    WHERE u.timezone = 'UTC'
    AND wp.id NOT IN (
        -- Keep only the most recent record for each user+date combination
        SELECT DISTINCT ON (wp2.user_id, 
            (COALESCE(wp2.updated_at, wp2.created_at) AT TIME ZONE 'UTC' AT TIME ZONE 'America/Los_Angeles')::date)
        wp2.id
        FROM workout_plans wp2
        INNER JOIN users u2 ON wp2.user_id = u2.id
        WHERE u2.timezone = 'UTC'
        ORDER BY wp2.user_id, 
                 (COALESCE(wp2.updated_at, wp2.created_at) AT TIME ZONE 'UTC' AT TIME ZONE 'America/Los_Angeles')::date,
                 COALESCE(wp2.updated_at, wp2.created_at) DESC
    )
);

-- For meal_plans: Delete older duplicates
DELETE FROM meal_plans
WHERE id IN (
    SELECT mp.id
    FROM meal_plans mp
    INNER JOIN users u ON mp.user_id = u.id
    WHERE u.timezone = 'UTC'
    AND mp.id NOT IN (
        SELECT DISTINCT ON (mp2.user_id, 
            (COALESCE(mp2.updated_at, mp2.created_at) AT TIME ZONE 'UTC' AT TIME ZONE 'America/Los_Angeles')::date)
        mp2.id
        FROM meal_plans mp2
        INNER JOIN users u2 ON mp2.user_id = u2.id
        WHERE u2.timezone = 'UTC'
        ORDER BY mp2.user_id, 
                 (COALESCE(mp2.updated_at, mp2.created_at) AT TIME ZONE 'UTC' AT TIME ZONE 'America/Los_Angeles')::date,
                 COALESCE(mp2.updated_at, mp2.created_at) DESC
    )
);

-- For grocery_lists: Delete older duplicates
DELETE FROM grocery_lists
WHERE id IN (
    SELECT gl.id
    FROM grocery_lists gl
    INNER JOIN users u ON gl.user_id = u.id
    WHERE u.timezone = 'UTC'
    AND gl.id NOT IN (
        SELECT DISTINCT ON (gl2.user_id, 
            (COALESCE(gl2.updated_at, gl2.created_at) AT TIME ZONE 'UTC' AT TIME ZONE 'America/Los_Angeles')::date)
        gl2.id
        FROM grocery_lists gl2
        INNER JOIN users u2 ON gl2.user_id = u2.id
        WHERE u2.timezone = 'UTC'
        ORDER BY gl2.user_id, 
                 (COALESCE(gl2.updated_at, gl2.created_at) AT TIME ZONE 'UTC' AT TIME ZONE 'America/Los_Angeles')::date,
                 COALESCE(gl2.updated_at, gl2.created_at) DESC
    )
);

-- move the start_date values a year back to avoid conflicts
update workout_plans 
set start_date = (start_date - interval '1 year')::date 

UPDATE workout_plans wp
SET start_date = (
    COALESCE(wp.updated_at, wp.created_at) 
    AT TIME ZONE 'UTC' 
    AT TIME ZONE 'America/Los_Angeles'
)::date
FROM users u
WHERE wp.user_id = u.id 
    AND u.timezone = 'UTC'


update meal_plans 
set start_date = (start_date - interval '1 year')::date 

UPDATE meal_plans mp
SET start_date = (
    COALESCE(mp.updated_at, mp.created_at) 
    AT TIME ZONE 'UTC' 
    AT TIME ZONE 'America/Los_Angeles'
)::date
FROM users u
WHERE mp.user_id = u.id 
    AND u.timezone = 'UTC';

update grocery_lists 
set start_date = (start_date - interval '1 year')::date 

UPDATE grocery_lists gl
SET start_date = (
    COALESCE(gl.updated_at, gl.created_at) 
    AT TIME ZONE 'UTC' 
    AT TIME ZONE 'America/Los_Angeles'
)::date
FROM users u
WHERE gl.user_id = u.id 
    AND u.timezone = 'UTC';

-- correct existing users timezones to the right one. 
-- 'America/Los_Angeles'  -- Pacific (NOT 'US/Pacific')
-- 'America/Denver'       -- Mountain
-- 'America/Chicago'      -- Central
-- 'America/New_York'     -- Eastern

UPDATE users 
SET timezone = 'America/Los_Angeles' 
WHERE timezone = 'UTC';