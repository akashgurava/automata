#!/bin/bash

set -e

# Function to log messages with a timestamp
log_message() {
    local message=$1
    echo "$(date +%Y-%m-%d\ %H:%M:%S) - ${message}"
}

# Function to check if an environment variable is set and not empty
check_env_var() {
    local var_name=$1
    if [ -z "${!var_name}" ]; then
        log_message "Error: Environment variable ${var_name} is not set or is empty."
        exit 1
    fi
}

# List of required environment variables
required_env_vars=(
    "POSTGRES_DB_PATH"
    "POSTGRES_DB_INIT_PATH"
    "POSTGRES_LOGS_PATH"
    "POSTGRES_SUPERUSER_PASSWORD"
    "POSTGRES_SUPERUSER_USERNAME"
    "POSTGRES_BLOCKY_USERNAME"
    "POSTGRES_BLOCKY_PASSWORD"
    "POSTGRES_BLOCKY_DB"
)

# Check each required environment variable
for var in "${required_env_vars[@]}"; do
    check_env_var "$var"
done


# Ignore status for only this block
set +e
log_message "Stop database if running."
${USER_BIN_PATH}/pg_ctl -D ${POSTGRES_DB_INIT_PATH} stop || true
${USER_BIN_PATH}/pg_ctl -D ${POSTGRES_DB_PATH} stop || true
log_message "Database stopped."

# Check the status of the PostgreSQL database
${USER_BIN_PATH}/pg_ctl -D ${POSTGRES_DB_PATH}/postgres@${POSTGRES_VERSION} status
set -e

# Capture the return code of the previous command
rc=$?

# Log messages based on the return code
if [ $rc -eq 0 ]; then
    log_message "PostgreSQL is installed."
elif [ $rc -eq 2 ]; then
    log_message "PostgreSQL is not installed or not symlinked."
elif [ $rc -eq 3 ]; then
    log_message "DBMS folder is correct but the server is not running."
elif [ $rc -eq 4 ]; then
    log_message "Database data does not exist at ${POSTGRES_DB_PATH} or is corrupted."
else
    log_message "Unexpected return code: $rc"
fi

# Exit with code 0 if the return code is not 4
if [ $rc -ne 4 ]; then
    exit 0
fi


rm -rf /tmp/postgres_pwd
rm -rf ${POSTGRES_DB_INIT_PATH}

# Remove temporary files and initialize the database
log_message "Starting database initialization."
echo ${POSTGRES_SUPERUSER_PASSWORD} > /tmp/postgres_pwd
${USER_BIN_PATH}/initdb -D ${POSTGRES_DB_INIT_PATH} \
    -U ${POSTGRES_SUPERUSER_USERNAME} \
    --pwfile=/tmp/postgres_pwd \
    -A scram-sha-256 \
    --encoding=UTF8 --locale=en_US \
    --data-checksums
rm /tmp/postgres_pwd
log_message "Database initialization completed."

# Start the PostgreSQL server and log the output
log_message "Starting PostgreSQL server."
mkdir -p ${POSTGRES_LOGS_PATH}
${USER_BIN_PATH}/pg_ctl -D ${POSTGRES_DB_INIT_PATH} -l ${POSTGRES_LOGS_PATH}/initdb-$(date +%Y%m%d%H%M%S).log start

# Wait for PostgreSQL to start
sleep 5
log_message "PostgreSQL server started."

# Connect to PostgreSQL and create a new user and database
log_message "Creating blocky user and database."
export PGPASSWORD=${POSTGRES_SUPERUSER_PASSWORD}
${USER_BIN_PATH}/psql -U ${POSTGRES_SUPERUSER_USERNAME} -c "CREATE USER ${POSTGRES_BLOCKY_USERNAME} WITH PASSWORD '${POSTGRES_BLOCKY_PASSWORD}' NOINHERIT NOSUPERUSER CREATEDB;"
${USER_BIN_PATH}/psql -U ${POSTGRES_SUPERUSER_USERNAME} -c "CREATE DATABASE ${POSTGRES_BLOCKY_DB} OWNER ${POSTGRES_BLOCKY_USERNAME};"
unset PGPASSWORD
log_message "Blocky user and database created."

# Stop the PostgreSQL server
log_message "Stopping PostgreSQL server."
${USER_BIN_PATH}/pg_ctl -D ${POSTGRES_DB_INIT_PATH} stop
log_message "PostgreSQL server stopped."

# Move the initialized database to the desired path
log_message "Moving initialized database to the desired path."
mkdir -p ${POSTGRES_DB_PATH}
mv ${POSTGRES_DB_INIT_PATH} ${POSTGRES_DB_PATH}
log_message "Database moved to ${POSTGRES_DB_PATH}."
