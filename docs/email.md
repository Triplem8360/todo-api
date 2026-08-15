# Email and smtp4dev

The application uses FastAPI-Mail 1.x for asynchronous SMTP delivery. The development Compose
stack includes smtp4dev, a fake SMTP server that captures messages instead of relaying them to
real recipients.

Start the development stack with:

```bash
docker compose -f compose.dev.yaml up --build
```

The API container connects to `smtp4dev:25`. A host-run API connects through
`localhost:${SMTP4DEV_SMTP_PORT:-2525}`, and the captured-message UI is available only on the
local machine at `http://localhost:${SMTP4DEV_WEB_PORT:-5000}`. smtp4dev stores its inbox in the
`smtp4dev_data` volume.

## Test endpoints

Both endpoints require a valid access token. The test-delivery endpoint always uses the
authenticated user's registered address, so it cannot be used as an unauthenticated or
arbitrary-address SMTP relay.

Check that the configured SMTP server accepts a connection:

```http
GET /api/v1/emails/smtp
Authorization: Bearer <access-token>
```

This opens the connection, negotiates the configured TLS mode, optionally logs in, and sends
`QUIT`; it does not create a message.

Send a message that can be inspected in the smtp4dev inbox:

```http
POST /api/v1/emails/test
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "subject": "Todo API SMTP test",
  "body": "Email delivery works.",
  "subtype": "plain"
}
```

`subtype` accepts `plain` or `html`. A successful SMTP handoff returns `status: "sent"`; when
`SUPPRESS_SEND=true`, both endpoints return `status: "suppressed"` and do not use the network.
After a `sent` response, open the smtp4dev UI and inspect the recipient, subject, rendered body,
raw MIME source, and SMTP session.

## Registration verification

`POST /api/v1/auth/register` now creates an unverified account and synchronously attempts to send
a multipart HTML/plain-text verification message. Delivery failure does not roll back a valid
account; the response exposes `verification_email_sent: false` so the client can present a resend
action. Open the message in smtp4dev and follow its single-use link:

```http
GET /api/v1/auth/email-verification/confirm?token=<opaque-token>
```

If the message was not delivered, request another without revealing whether an account exists:

```http
POST /api/v1/auth/email-verification/resend
Content-Type: application/json

{"email": "user@example.com"}
```

The verification URL, token lifetime, and resend cooldown are configured with:

```env
EMAIL_VERIFICATION_URL=http://localhost:8000/api/v1/auth/email-verification/confirm
EMAIL_VERIFICATION_TOKEN_TTL=PT24H
EMAIL_VERIFICATION_RESEND_COOLDOWN=PT60S
```

The two duration values use ISO 8601 syntax: `PT24H` means 24 hours and `PT60S` means
60 seconds.

Staging and production require an HTTPS verification URL. Existing accounts are marked verified
by the migration, while trusted CLI and seed workflows continue creating verified accounts.

## FastAPI-Mail `ConnectionConfig`

The application exposes every field in FastAPI-Mail 1.6.5's `ConnectionConfig`. Values come from
environment variables and are validated by `Settings` before being translated in
`todo_api.utils.email.create_mail_config`.

| Environment variable | Local default | Meaning |
| --- | --- | --- |
| `MAIL_SERVER` | `localhost` | SMTP hostname. Compose overrides this to the `smtp4dev` service name for containers. |
| `MAIL_PORT` | `2525` | SMTP TCP port, from 1 through 65535. Compose overrides this to smtp4dev's container port `25`. |
| `MAIL_USERNAME` | empty | SMTP login name. Some providers use the sender address; others issue a separate username. |
| `MAIL_PASSWORD` | empty | SMTP login secret. It is stored as Pydantic `SecretStr` and is not returned by the status endpoint. |
| `USE_CREDENTIALS` | `false` | When true, log in after connecting. The application then requires non-empty username and password. smtp4dev needs no login. |
| `MAIL_STARTTLS` | `false` | Connect in plaintext and upgrade with STARTTLS, commonly on port 587. |
| `MAIL_SSL_TLS` | `false` | Use implicit TLS from the first byte, commonly on port 465. It cannot be enabled with `MAIL_STARTTLS`. |
| `VALIDATE_CERTS` | `true` | Verify the SMTP server certificate for a TLS connection. Keep this enabled outside isolated local testing. |
| `CERT_BUNDLE` | empty | Optional path to a custom CA certificate bundle, forwarded to the SMTP client. Empty means the platform trust store. |
| `MAIL_FROM` | `noreply@example.com` | Default RFC 5322 sender address placed in outgoing messages. Replace it with a domain accepted by the real provider. |
| `MAIL_FROM_NAME` | `Todo API` | Optional human-readable display name paired with `MAIL_FROM`. |
| `MAIL_DEBUG` | `0` | FastAPI-Mail's integer debug compatibility field (`0` or `1`). Version 1.6.5 validates it but does not currently pass it to its SMTP connection, so application logging should be used for diagnostics. |
| `SUPPRESS_SEND` | `false` | Build and dispatch FastAPI-Mail's test signal without connecting or delivering. This supports deterministic unit tests. |
| `TIMEOUT` | `10` | SMTP operation timeout in seconds. The application accepts 1 through 300 seconds. |
| `LOCAL_HOSTNAME` | empty | Optional hostname sent by the client during the SMTP EHLO/HELO exchange. Empty lets the SMTP library choose. |
| `TEMPLATE_FOLDER` | empty | Optional existing directory containing Jinja templates used by `send_message`. The current test endpoint sends its body directly. |

The valid transport combinations are:

| Connection type | `MAIL_STARTTLS` | `MAIL_SSL_TLS` |
| --- | --- | --- |
| Plain local SMTP (smtp4dev) | `false` | `false` |
| STARTTLS | `true` | `false` |
| Implicit TLS | `false` | `true` |

For a real SMTP provider, change the server, port, sender, credential, and TLS values in the
deployment environment. Do not add real secrets to `.env.example` or Compose files.
