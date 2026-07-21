# External MySQL Compose Design

## Goal

Keep database lifecycle outside this repository's Docker Compose project. The
application must connect to the externally managed MySQL instance through the
existing profile configuration and must not start MySQL or Redis containers.

## Scope

- Remove the `mysql` service from `docker-compose.yml`.
- Remove the `mysql_data` volume reference and database health dependency.
- Keep only the backend and frontend application services.
- Set the backend profile to `prod`; do not duplicate database credentials in
  Compose YAML.
- Inject an untracked deployment file through
  `BACK_ENV_FILE` (default `back/.env.deploy`) before Python starts.
- Keep tracked `back/.env.prod` as a placeholder-only profile template.
- Exclude dotenv files from the backend image.
- Preserve the existing rule that deployment environment variables override
  profile dotenv values.

## Runtime flow

1. Compose reads the host-side deployment file selected by `BACK_ENV_FILE`.
2. Compose injects its variables into the backend process and sets
   `FLASK_ENV=prod`.
3. The existing config classes read the already-injected values; deployment
   environment values remain higher priority than tracked templates.
4. The backend runs Alembic migrations against the configured external MySQL
   instance, then starts Gunicorn.
5. Frontend startup still depends on the backend service, but the backend has
   no Compose-managed database dependency.

## Failure handling

- If external MySQL is unreachable or the credentials are invalid, the
  migration entrypoint fails and the backend container exits instead of
  starting against an unknown database.
- Database readiness remains covered by the backend's database health check.
- No Redis health check or Redis configuration is introduced.
- If the deployment env file is absent, Compose validation/startup fails rather
  than silently falling back to a container-local database hostname.

## Verification

- `docker compose config --quiet` succeeds.
- The rendered Compose configuration contains no `mysql` or `redis` service.
- The backend image context excludes `.env*` files.
- The tracked production profile contains placeholders only.
- The deployment env file is ignored by Git.
- Backend Ruff, formatting, mypy, and pytest gates pass.
- Existing profile-loading tests continue to pass.

## Non-goals

- Provisioning, backing up, or monitoring the external MySQL instance.
- Adding secret-management infrastructure.
- Changing application database models or migrations.

## Separate scaffolding correction

The existing `ENV_FILE` profile-loading path initializes configuration class
attributes before `bootstrap_env()` is called by some entrypoints. Correcting
that behavior requires changing `config.py`, which project policy classifies as
a scaffolding change. It must therefore be delivered in a separate
`scaffolding` PR with fresh-process regression tests; the Compose deployment
does not depend on that correction because variables are injected before the
Python process starts.
