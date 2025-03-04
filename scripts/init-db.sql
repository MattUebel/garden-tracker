-- Create application user with login privilege
CREATE USER garden_user WITH PASSWORD 'mygarden' LOGIN;

-- Create database if it doesn't exist
CREATE DATABASE garden_db;

-- Connect to the database
\c garden_db;

-- Create extension if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Grant schema privileges
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO garden_user;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO garden_user;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO garden_user;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT USAGE ON TYPES TO garden_user;

GRANT ALL ON SCHEMA public TO garden_user;
GRANT CREATE ON SCHEMA public TO garden_user;
GRANT USAGE ON SCHEMA public TO garden_user;

-- Grant privileges on existing objects
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO garden_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO garden_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO garden_user;

-- Grant database connection privilege
GRANT CONNECT ON DATABASE garden_db TO garden_user;
GRANT TEMP ON DATABASE garden_db TO garden_user;

-- Make sure garden_user owns the public schema and has type creation privileges
ALTER SCHEMA public OWNER TO garden_user;
GRANT CREATE ON SCHEMA public TO postgres;