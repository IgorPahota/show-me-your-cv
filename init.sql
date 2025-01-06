-- Create the postgres superuser if it doesn't exist
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles
      WHERE  rolname = 'postgres') THEN

      CREATE ROLE postgres WITH SUPERUSER LOGIN PASSWORD 'postgres';
   END IF;
END
$do$;

-- Create database
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'jobs_db') THEN
      PERFORM dblink_exec('dbname=' || current_database(), 'CREATE DATABASE jobs_db');
   END IF;
END
$do$;

\c jobs_db;

-- Create extension if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; 