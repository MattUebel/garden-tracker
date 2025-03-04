-- Create application user
CREATE USER garden_user WITH PASSWORD 'mygarden';

-- Create database if it doesn't exist
SELECT 'CREATE DATABASE garden_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'garden_db')\gexec

-- Connect to the database
\c garden_db

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE garden_db TO garden_user;
GRANT ALL PRIVILEGES ON SCHEMA public TO garden_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO garden_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO garden_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO garden_user;

-- Create extension if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";