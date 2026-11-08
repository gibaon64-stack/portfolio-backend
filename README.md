# Portfolio Backend

Flask API for the portfolio frontend. It provides public portfolio, inquiry,
registration, separate admin authentication, protected content management, and
Cloudinary-backed image uploads.

## Local Setup

From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m flask --app run:app db upgrade
.\.venv\Scripts\python.exe -m flask --app run:app seed-content
.\.venv\Scripts\python.exe -m flask --app run:app create-admin
.\.venv\Scripts\python.exe run.py
```

The API listens on port `5000` by default. The `create-admin` command prompts
for an email and a password of at least 12 characters. Public accounts register
through `/api/auth/register` and remain separate from administrators.

## Deploy on Render

Configure the existing Render service to use the `backend/render.yaml` settings.
Set `INITIAL_ADMIN_PASSWORD` as a protected environment secret; never pass it in
a deploy command or commit it. The initial hook provisions `ian@gmail.com`
idempotently and does not replace an existing password. For an already deployed
service, apply database migrations and run `flask --app run:app provision-admin`
from Render Shell once after setting the secret.

Set `FRONTEND_ORIGIN` to `https://portfolio-mabrixel.netlify.app`. Netlify builds
from the repository root using `netlify.toml` and proxies `/api/*` to the Render
API. This keeps JWT and CSRF cookies same-origin in the browser.

Review the Render plan and database retention settings before relying on them.
Production media is stored on Cloudinary rather than Render's temporary disk.

## Configuration

Configure `FRONTEND_ORIGIN`, `DATABASE_URL`, `SECRET_KEY`, `JWT_SECRET_KEY`,
`COOKIE_SECURE`, and `CLOUDINARY_REQUIRED` through the environment. Configure
Cloudinary using either `CLOUDINARY_URL` or the three `CLOUDINARY_*` variables.
Use unique random signing keys and the existing durable production database.
Never commit `.env` files, local databases, or credential values.

The admin image library stores Cloudinary secure URLs and public asset IDs.
Image upload contexts are separated into `mabrixel/projects`, `services`,
`about`, `contact`, and `homepage`; deleting an image is an explicit admin action.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```