-- Create database if it doesn't exist
CREATE DATABASE garden_db;

-- Create application user
CREATE USER garden_user WITH PASSWORD 'mygarden';

-- Connect to the database
\c garden_db;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE garden_db TO garden_user;
GRANT ALL PRIVILEGES ON SCHEMA public TO garden_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO garden_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO garden_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO garden_user;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO garden_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO garden_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO garden_user;

-- Create extension if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";