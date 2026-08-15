-- 04_readonly_role.sql
-- Hardening for a PUBLIC deployment (e.g. Streamlit Community Cloud).
-- Creates a read-only role + a dedicated app user, and caps warehouse spend so a
-- public, unauthenticated app cannot do anything but read the dog data and cannot
-- drain your account. Run as ACCOUNTADMIN after the data is loaded.
--
-- Put DOG_APP_USER / its password (NOT your ACCOUNTADMIN login) into the app's
-- Streamlit secrets. See the [snowflake] block in the deploy notes.

USE ROLE ACCOUNTADMIN;

-- Read-only role: SELECT on the results only, USAGE on the warehouse. Nothing else.
CREATE ROLE IF NOT EXISTS DOG_APP_RO;
GRANT USAGE ON DATABASE DOG_COSTS                     TO ROLE DOG_APP_RO;
GRANT USAGE ON SCHEMA   DOG_COSTS.PUBLIC              TO ROLE DOG_APP_RO;
GRANT SELECT ON ALL TABLES    IN SCHEMA DOG_COSTS.PUBLIC TO ROLE DOG_APP_RO;
GRANT SELECT ON ALL VIEWS     IN SCHEMA DOG_COSTS.PUBLIC TO ROLE DOG_APP_RO;
GRANT SELECT ON FUTURE TABLES IN SCHEMA DOG_COSTS.PUBLIC TO ROLE DOG_APP_RO;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA DOG_COSTS.PUBLIC TO ROLE DOG_APP_RO;
GRANT USAGE  ON WAREHOUSE DOG_WH                      TO ROLE DOG_APP_RO;

-- Dedicated user for the public app. CHANGE THE PASSWORD BELOW to a strong value.
CREATE USER IF NOT EXISTS DOG_APP_USER
    PASSWORD = 'CHANGE_ME_to_a_long_random_password'
    DEFAULT_ROLE = DOG_APP_RO
    DEFAULT_WAREHOUSE = DOG_WH
    MUST_CHANGE_PASSWORD = FALSE
    COMMENT = 'Read-only user for the public Streamlit app';
GRANT ROLE DOG_APP_RO TO USER DOG_APP_USER;

-- Cap spend: a resource monitor that suspends the warehouse at the quota so a
-- public app (or abuse of it) cannot run up your bill. Adjust CREDIT_QUOTA.
CREATE RESOURCE MONITOR IF NOT EXISTS DOG_WH_MONITOR
    WITH CREDIT_QUOTA = 5
    FREQUENCY = MONTHLY
    START_TIMESTAMP = IMMEDIATELY
    TRIGGERS ON 100 PERCENT DO SUSPEND
             ON  90 PERCENT DO NOTIFY;
ALTER WAREHOUSE DOG_WH SET RESOURCE_MONITOR = DOG_WH_MONITOR;

-- Sanity: what the read-only user can see.
SHOW GRANTS TO ROLE DOG_APP_RO;
