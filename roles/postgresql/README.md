# Postgres Role
Ansible role for ensuring PostgresDB runs as configured.

## Terminology

- Postgres Service - The "Intended" way of running Postgres instance
    - Disabled brew service
    - Symlink executables to ~/bin (to have easy access irrespective of postgres version)
    - Data coming from $POSTGRES_DB_PATH

## Testing
```zsh
brew remove postgresql@16 && rm -rf $HOME/bin && rm -rf /opt/homebrew/var/postgresql@16
# If you want E2E delete the target data folder too
rm -rf $POSTGRES_DB_PATH
```
