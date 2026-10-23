# FastAPI production service on Ubuntu 24.04

This runbook prepares the existing single-EC2 deployment. PostgreSQL, IAM, S3, Cognito, Nginx, DNS, and TLS must already be configured or handled by their respective runbooks. Replace every placeholder before installation. Never print secrets in terminal output, tickets, or logs.

## Paths and process model

- OS user/group: `mobile-order`
- Application: `/opt/mobile-order`
- Backend working directory: `/opt/mobile-order/backend`
- Virtual environment: `/opt/mobile-order/backend/.venv`
- Production environment: `/etc/mobile-order/backend.env`
- Installed unit: `/etc/systemd/system/mobile-order-api.service`
- Listener: `127.0.0.1:8000`
- Process count: one Uvicorn worker
- Logs: systemd journal under `mobile-order-api`

One worker is intentional. API rate limits and WebSocket connection state are process-local. Do not add automatic worker calculation or multiple workers without redesigning that state.

## 1. Create the dedicated OS account

Run these commands as an administrator. The service account has no interactive password and cannot log in with a shell.

```bash
sudo adduser --system --group --home /opt/mobile-order --shell /usr/sbin/nologin mobile-order
sudo install -d -o mobile-order -g mobile-order -m 0750 /opt/mobile-order
```

Do not run Uvicorn as root and do not add this user to `sudo`.

## 2. Place the application

Deploy a reviewed release into `/opt/mobile-order`. Preserve the previous release outside the new release directory until validation finishes. Do not copy development `.env` files, Git metadata, test caches, frontend `node_modules`, or AWS credential files.

The installed service makes `/opt/mobile-order` read-only inside the service process. Stop the service before replacing a release. The deployment administrator can still update files outside the service namespace.

Give the service account temporary ownership while creating the virtual
environment. Ownership is locked down after dependency installation in the
next step:

```bash
sudo chown -R mobile-order:mobile-order /opt/mobile-order
```

Do not build the React application on a t3.micro if it can be built and tested before deployment. Deploy the reviewed `dist` artifacts to the Nginx document root separately.

## 3. Create the Python virtual environment

```bash
sudo -u mobile-order python3 -m venv /opt/mobile-order/backend/.venv
sudo -u mobile-order /opt/mobile-order/backend/.venv/bin/python -m pip install --upgrade pip
sudo -u mobile-order /opt/mobile-order/backend/.venv/bin/python -m pip install -r /opt/mobile-order/backend/requirements.txt
sudo chown -R root:mobile-order /opt/mobile-order
sudo chmod -R u=rwX,g=rX,o= /opt/mobile-order
```

The final symbolic mode preserves executable bits on virtual-environment
programs while removing access for other users. The service user then has
read/execute access but cannot modify application or dependency files. Use
pinned and reviewed dependencies. The application command deliberately uses
the virtual environment's Python executable.

## 4. Install the production environment file

Create the directory and install a rendered copy of `backend.env.example` without displaying its contents:

Before `install`, validate the exact rendered environment file and rendered
unit. A nonzero result stops deployment. The validator never prints resolved
values. The repository `.example` files are expected to fail until rendered.

```bash
python3 deploy/preflight/validate_deployment_config.py REPLACE_WITH_RENDERED_ENV_FILE REPLACE_WITH_RENDERED_SYSTEMD_UNIT
```

```bash
sudo install -d -o root -g root -m 0750 /etc/mobile-order
sudo install -o root -g root -m 0600 REPLACE_WITH_RENDERED_ENV_FILE /etc/mobile-order/backend.env
```

The file is root-owned and mode `0600`. This is compatible with the unit: the systemd system manager reads `EnvironmentFile` before starting the process as `User=mobile-order`; the service account does not need direct read permission. Confirm this through service startup, not by weakening the file to world-readable.

Required production rules:

- `APP_ENV=production`
- `DEMO_AUTH_COOKIE_SECURE=true`
- CORS, customer WebSocket, and demo-auth origins contain only the exact public HTTPS origin
- customer JWT, demo-auth signing, and demo password values are independent secrets
- no secret is placed in a frontend `VITE_` variable
- no AWS access key, session token, profile, or shared-credentials override is present
- S3 and Cognito use the attached EC2 IAM role

The application does not call `load_dotenv()` in production mode. Therefore `/etc/mobile-order/backend.env` is authoritative and a checkout-local `.env` cannot silently fill missing production settings. Missing required settings, insecure demo cookies, and AWS credential overrides fail startup with variable names only; values are not logged.

Do not use `systemctl show ... --property=Environment` or `cat` the environment file in shared terminals because those can reveal values. Confirm metadata without contents:

```bash
sudo stat -c '%U:%G %a %n' /etc/mobile-order/backend.env
```

Expected metadata is `root:root 600`.

## 5. Install and verify the systemd unit

```bash
sudo install -o root -g root -m 0644 deploy/systemd/mobile-order-api.service.example /etc/systemd/system/mobile-order-api.service
sudo systemd-analyze verify /etc/systemd/system/mobile-order-api.service
sudo systemctl daemon-reload
sudo systemctl enable mobile-order-api.service
```

Review the installed file before starting. The command must contain `--host 127.0.0.1`, `--port 8000`, `--workers 1`, no `--reload`, and `--forwarded-allow-ips 127.0.0.1`. Nginx is the only trusted proxy and already forwards to `127.0.0.1:8000`.

## 6. Start, stop, restart, and inspect

```bash
sudo systemctl start mobile-order-api.service
sudo systemctl status mobile-order-api.service --no-pager
sudo systemctl restart mobile-order-api.service
sudo systemctl stop mobile-order-api.service
sudo systemctl start mobile-order-api.service
```

Check recent logs without increasing application verbosity:

```bash
sudo journalctl -u mobile-order-api.service -n 100 --no-pager
sudo journalctl -u mobile-order-api.service --since today
```

Never add request headers, cookies, JWTs, passwords, the environment file, or the database URL to diagnostic output. Journal retention and disk limits must be reviewed separately on the EC2 host.

## 7. Validate the listener and health endpoint

On EC2, verify that Uvicorn listens only on loopback:

```bash
sudo ss -lntp | grep ':8000'
curl --fail --silent http://127.0.0.1:8000/api/health
```

The expected health body contains only `{"status":"ok"}`. It intentionally does not expose environment, database, IAM, dependency, version, or build information.

Then validate through Nginx over HTTPS:

```bash
curl --fail --silent https://REPLACE_WITH_PUBLIC_DOMAIN/api/health
```

Ports 8000 and 5432 must have no EC2 security-group or UFW ingress rule. Confirm from a separate host that direct access fails. The existing Nginx `/api/` and `/ws/` proxy configuration remains unchanged.

## 8. Confirm production documentation behavior

Through the public HTTPS origin, `/docs`, `/redoc`, and `/openapi.json` must not expose FastAPI documentation. In development and test environments these endpoints remain enabled.

## 9. Confirm restart and boot behavior

After functional tests, record a maintenance window and reboot the instance:

```bash
sudo reboot
```

After reconnecting, confirm PostgreSQL, FastAPI, and Nginx status, then repeat the loopback and HTTPS health checks. `Restart=on-failure`, `RestartSec=5s`, and the start limit prevent an uncontrolled rapid restart loop.

## 10. Troubleshooting

Use the status and journal commands first. Common safe checks are:

- exit status and the name of a missing variable, without printing values
- owner/mode of `/etc/mobile-order/backend.env`
- existence of the virtual-environment Python and installed packages
- `WorkingDirectory` and release ownership
- PostgreSQL service state and loopback listener
- IAM role attachment and credential source, without printing credentials
- Nginx upstream port matching `127.0.0.1:8000`
- `sudo systemd-analyze security mobile-order-api.service` for hardening review

If `ProtectSystem`, `ProtectHome`, `PrivateDevices`, or `ReadOnlyPaths` blocks a newly introduced legitimate requirement, identify the exact required path or device and add the narrowest exception. Do not broadly disable all hardening as the first response.

## 11. Roll back

Before each deployment, retain the previous unit file, environment-file metadata and protected backup, backend release, and virtual environment. Do not include secret contents in deployment logs.

If startup or smoke tests fail:

1. Stop `mobile-order-api.service`.
2. Restore the previous release and virtual environment.
3. Restore the previous unit file and, only if required, the protected previous environment file.
4. Run `systemd-analyze verify`.
5. Run `systemctl daemon-reload`.
6. Start the service and repeat health, authentication, order, accounting, S3, Cognito, and WebSocket checks.

This rollback does not reverse a database migration. Database migration and backup/restore procedures belong to a later stage and must be completed before applying schema-changing deployments.
