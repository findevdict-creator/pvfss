# Run PVFSS ERP in Docker

The fastest way to run the whole system on a laptop (Windows, macOS or Linux).
It is meant for local review and testing, not for production.

## Requirements

- Docker Desktop (Windows / macOS) or Docker Engine with the compose plugin (Linux).
- About 6 GB of free disk and 4 GB of memory for Docker.

## Start

From the repository root:

```bash
docker compose up --build
```

The first run builds the image (10 to 20 minutes, it downloads Frappe and ERPNext)
and then creates the site (a few more minutes). Wait for the line
`PVFSS ERP is starting at http://localhost:8000`, then open http://localhost:8000.

- User: `Administrator`
- Password: `admin` (change it with `ADMIN_PASSWORD`, see below)

On first login ERPNext shows its setup wizard: pick the company, country (United Arab
Emirates), currency (AED) and fiscal year. The PVFSS workspaces then show in the sidebar.

## Everyday use

| Task | Command |
|---|---|
| Start in the background | `docker compose up -d` |
| Watch the logs | `docker compose logs -f pvfss` |
| Stop | `docker compose down` |
| Rebuild after pulling new code | `docker compose up -d --build` (the site migrates on start) |
| Open a shell in the bench | `docker compose exec pvfss bash` |
| Run the pvfss tests | see below |
| Delete everything, data included | `docker compose down -v` |

Data lives in the `db-data` and `sites` volumes, so it survives `down` and rebuilds.

## Settings

Put any of these in a `.env` file next to `docker-compose.yml`, or set them in the shell:

| Variable | Default | Meaning |
|---|---|---|
| `ADMIN_PASSWORD` | `admin` | Administrator password, used only when the site is first created |
| `DB_ROOT_PASSWORD` | `admin` | MariaDB root password |
| `HTTP_PORT` | `8000` | Port on your machine |

The site runs with developer mode on and two-factor login off (`pvfss_skip_2fa`), which
is right for local review only. Staging and production keep 2FA (GEN-63).

## Run the tests

```bash
docker compose exec pvfss bash -c "
  bench new-site test_site --mariadb-root-password admin --admin-password admin \
    --mariadb-user-host-login-scope='%' --install-app erpnext --install-app pvfss &&
  bench --site test_site set-config allow_tests true &&
  bench --site test_site run-tests --app pvfss"
```

## Look at one build step

The image is built from whatever branch you have checked out. To review a single module,
`git checkout NN-modulename` and run `docker compose up -d --build`. Moving backwards to an
earlier branch on the same data can fail; use `docker compose down -v` first for a clean site.
