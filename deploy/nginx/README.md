# Nginx security-header rollout

`mobile-order.conf.example` is a template. Do not install it unchanged.

## Values to replace

Replace every existing `CHANGE_ME` value for the public host and certificate paths. Also replace these CSP tokens with complete HTTPS origins (scheme and host, with no path or trailing slash):

- `CSP_CHANGE_ME_COGNITO_ORIGIN`: the Cognito user-pool or custom-domain origin used by `/oauth2/token`, for example the actual origin shown in the deployed Cognito configuration.
- `CSP_CHANGE_ME_S3_IMAGE_ORIGIN`: the exact origin present in generated product-image presigned URLs.

These are literal template tokens, not environment-variable references. Nginx does not automatically expand shell or application `.env` values in its configuration. Replace them during deployment/configuration management and inspect the rendered file before installing it.

Before copying the rendered file into `/etc/nginx`, run the common preflight
against that exact file. A nonzero result stops the deployment; do not bypass
it. The command reports only the file, line, and marker category.

```bash
python3 deploy/preflight/validate_deployment_config.py REPLACE_WITH_RENDERED_NGINX_FILE
```

Run `nginx -t` only after this preflight succeeds. The repository `.example`
file is expected to fail this check and must never be installed directly.

The WebSocket source uses `wss://$host`, which Nginx expands from the request host. This matches the planned same-origin HTTPS/WSS deployment. If WebSocket traffic is moved to a separate origin, replace it with that exact `wss://` origin.

Before rollout, inventory existing product image URLs. Legacy database rows can contain an HTTP(S) URL from a host other than the configured S3 origin. Report-Only will report those loads; enforcement would block them unless the exact trusted origin is added. Do not add broad wildcards and do not change database values as part of the Nginx rollout.

## Report-Only validation

The template initially sends `Content-Security-Policy-Report-Only`. It reports violations but does not block resources or connections. No reporting endpoint is configured.

1. Render all required values and run `nginx -t`.
2. Open browser DevTools, select the Console, and keep the Network panel open with **Preserve log** enabled.
3. Exercise demo login/logout, Cognito login/callback/logout, customer and staff/admin APIs, orders, history, checkout, WebSocket reconnect, S3 image display, and image preview/upload.
4. Review Console messages beginning with `Content Security Policy` and inspect response headers for the document, API errors, and static resources.
5. Add only verified required origins. Do not add `unsafe-inline`, `unsafe-eval`, or broad wildcards to silence violations.
6. After the complete production-equivalent test passes, change only the header name from `Content-Security-Policy-Report-Only` to `Content-Security-Policy` and repeat the tests.

The production CSP should be configured on the HTTPS server only. The header directives use `always`, so Nginx-generated and proxied error responses receive them too. Do not add location-level `add_header` directives without repeating or deliberately preserving the server-level policy, because Nginx header inheritance changes when a child level defines its own headers.

## HSTS rollout

HSTS is intentionally absent from the template. Do not send it from the port 80 redirect server. After the public domain, TLS certificate, HTTPS API, Cognito callback, S3 images, and WSS have all been verified, add the following to the HTTPS server only:

```nginx
add_header Strict-Transport-Security "max-age=300" always;
```

Verify all flows, then increase it in stages:

1. Initial check: `max-age=300`
2. After successful validation: `max-age=86400`
3. After stable operation: `max-age=31536000`

Do not initially add `includeSubDomains` or `preload`. They require a separate review of every subdomain and a deliberate, difficult-to-reverse preload decision.

## Verification commands

Run the repository static test before deployment:

```text
python -m unittest deploy.nginx.test_mobile_order_config
```

On the target host, after rendering the template:

```text
sudo nginx -t
```

After reloading Nginx, inspect both successful and error responses over HTTPS. Verify that the five configured headers are present and that HSTS is absent until its staged rollout is approved.
