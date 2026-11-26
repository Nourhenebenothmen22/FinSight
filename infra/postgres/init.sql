-- FinSight PostgreSQL Initialization Script
-- Runs on first container startup to set up extensions and baseline configuration

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gin";  -- For composite indexes
CREATE EXTENSION IF NOT EXISTS "citext";     -- Case-insensitive text

-- Create application role (optional, for stricter permissions)
-- CREATE ROLE finsight_app WITH LOGIN PASSWORD '...';
-- GRANT CONNECT ON DATABASE finsight TO finsight_app;
-- GRANT USAGE ON SCHEMA public TO finsight_app;

-- Set default timezone
SET timezone = 'UTC';

-- Log initialization
DO $$
BEGIN
  RAISE NOTICE 'FinSight PostgreSQL initialized with extensions: uuid-ossp, pgcrypto, btree_gin, citext';
END $$;