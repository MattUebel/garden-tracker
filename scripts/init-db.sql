-- Create application user with login privilege
CREATE USER garden_user WITH PASSWORD 'mygarden' LOGIN;

-- Create database if it doesn't exist
CREATE DATABASE garden_db;

-- Grant connection privilege
GRANT CONNECT ON DATABASE garden_db TO garden_user;

-- Connect to the database
\c garden_db;

-- Create extension if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Grant schema privileges
GRANT USAGE ON SCHEMA public TO garden_user;
GRANT CREATE ON SCHEMA public TO garden_user;

-- Grant table privileges
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO garden_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO garden_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO garden_user;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO garden_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO garden_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO garden_user;