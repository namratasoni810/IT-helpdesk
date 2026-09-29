# ---------------------------------------------------------------------------
# Starts the local Postgres server without Docker.
#
# Docker Desktop is installed on this machine but cannot run because hardware
# virtualization is disabled in the firmware (WSL2 needs it). This script uses
# the portable EDB Postgres binaries instead so the prototype is fully testable
# with no container runtime and no administrator rights.
#
# The docker-compose.yml is still here and is the intended path on a machine
# where Docker works (and later, Lakebase) -- the app only ever sees
# DATABASE_URL, so both setups are interchangeable.
# ---------------------------------------------------------------------------

[Cmdlet.Binding()]
param(
    [string]$PgDir = "pgsql_bin",
    [string]$DataDir = "pgdata",
    [int]$Port = 5432
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$pgCtl = Join-Path $PgDir "bin\pg_ctl.exe"
$initDb = Join-Path $PgDir "bin\initdb.exe"
$psql = Join-Path $PgDir "bin\psql.exe"

if (-not (Test-Path $pgCtl)) {
    Write-Error "Postgres binaries not found at '$pgCtl'. Download the Windows x64 archive from https://www.enterprisedb.com/download-postgresql-binaries and extract it to '$PgDir'."
    exit 1
}

# 1. Initialise the cluster on first run.
if (-not (Test-Path $DataDir)) {
    Write-Host "Initialising Postgres cluster in $DataDir ..."
    "postgres" | Set-Content -Path "pgpass_init.txt" -NoNewline
    & $initDb -U postgres -A password --pwfile="pgpass_init.txt" -D $DataDir -E UTF8
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

# 2. Start the server (idempotent -- skips if already running).
$status = & $pgCtl -D $DataDir status
if ($status -match "server is running") {
    Write-Host "Postgres is already running."
} else {
    & $pgCtl -D $DataDir -l (Join-Path $DataDir "postgresql.log") -o "-p $Port" start
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

# 3. Create the role + database that docker-compose.yml also defines, so the
#    DATABASE_URL in .env works identically either way.
$env:PGPASSWORD = "postgres"
$queries = @(
    "SELECT 1 FROM pg_roles WHERE rolname = 'helpdesk'",
    "SELECT 1 FROM pg_database WHERE datname = 'helpdesk'"
)
$roleExists = & $psql -U postgres -h localhost -p $Port -d postgres -tAc $queries[0]
$dbExists = & $psql -U postgres -h localhost -p $Port -d postgres -tAc $queries[1]

if ($roleExists -ne "1") {
    & $psql -U postgres -h localhost -p $Port -d postgres -c "CREATE ROLE helpdesk WITH LOGIN PASSWORD 'helpdesk';"
}
if ($dbExists -ne "1") {
    & $psql -U postgres -h localhost -p $Port -d postgres -c "CREATE DATABASE helpdesk OWNER helpdesk;"
    & $psql -U postgres -h localhost -p $Port -d postgres -c "GRANT ALL PRIVILEGES ON DATABASE helpdesk TO helpdesk;"
}

Write-Host ""
Write-Host "Postgres is ready: postgresql://helpdesk:helpdesk@localhost:$Port/helpdesk"
Write-Host "Stop it with:  .\pgsql_bin\bin\pg_ctl.exe -D pgdata stop"
