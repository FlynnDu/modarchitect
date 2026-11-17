\set ON_ERROR_STOP on
\getenv migrator_password MODARCHITECT_MIGRATOR_PASSWORD
\getenv app_password MODARCHITECT_APP_PASSWORD

SELECT format('CREATE ROLE modarchitect_migrator LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L',
              :'migrator_password') \gexec
SELECT format('CREATE ROLE modarchitect_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L',
              :'app_password') \gexec

ALTER DATABASE modarchitect OWNER TO modarchitect_migrator;
REVOKE CONNECT ON DATABASE modarchitect FROM PUBLIC;
GRANT CONNECT ON DATABASE modarchitect TO modarchitect_app;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO modarchitect_app;
