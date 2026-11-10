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
.\.venv\Scripts\python.exe run.py
```

Set `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` in the backend `.env`
before starting the API. These are the only administrator login credentials;
the login endpoint does not read or create administrator database accounts.
Public accounts register through `/api/auth/register` and remain separate from
administrator access.

## Deploy on Render

Configure the existing Render service to use the `backend/render.yaml` settings.
Set both `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` in the backend
service's protected environment settings. Do not put credentials in the
frontend's Netlify environment or in source control. The login endpoint
authenticates directly against these environment values; no admin account is
created during deployment.

Set `FRONTEND_ORIGIN` to `https://portfolio-mabrixel.netlify.app`. The separate
frontend repository contains the Netlify build configuration and proxies
`/api/*` to this Render API. The browser therefore uses same-origin HTTP-only
JWT cookies through the proxy; the backend also allows the configured frontend
origin for credentialed CORS requests.

For persistent production media, set `CLOUDINARY_CLOUD_NAME`,
`CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET` in the Render backend
service's protected environment settings. Alternatively, configure a
`CLOUDINARY_URL` instead of the three individual values. Without Cloudinary,
uploads fall back to the backend's local disk; on Render, local files are
temporary and may disappear when the service restarts or redeploys.

Set `GEMINI_API_KEY` in the same protected environment settings to enable
Mabrook's backend chat endpoint (`POST /api/assistant/chat`). The key is never
sent to the browser. `GEMINI_MODEL` may be set to another model enabled for the
Google AI project; otherwise the current default is used.

Review the Render plan and database retention settings before relying on them.
Production media is stored on Cloudinary rather than Render's temporary disk.

## Configuration

Configure `FRONTEND_ORIGIN`, `DATABASE_URL`, `SECRET_KEY`, `JWT_SECRET_KEY`,
`COOKIE_SECURE`, and optionally `CLOUDINARY_REQUIRED` through the environment.
Set `CLOUDINARY_REQUIRED=1` to reject uploads when Cloudinary is unavailable.
Configure Cloudinary using either `CLOUDINARY_URL` or the three
`CLOUDINARY_*` variables.
Configure `GEMINI_API_KEY` to enable the rate-limited Mabrook assistant and
optionally set `GEMINI_MODEL`.
Use unique random signing keys and the existing durable production database.
Never commit `.env` files, local databases, or credential values.

The admin image library stores Cloudinary secure URLs and public asset IDs for
Cloudinary uploads. Image upload contexts are separated into
`mabrixel/projects`, `services`, `about`, `contact`, `homepage`, and `journey`; deleting a
Cloudinary image is an explicit admin action. When Cloudinary is not configured
and not required, uploads use local disk storage, including profile images.

The additive `76d4b8c2f901` migration adds profile technologies, organization
and multiple image URLs per Journey milestone, and project display ordering.
Existing profile, milestone, project, and inquiry records are retained.

Project records include separate short and detailed descriptions, thumbnail and
live/repository URLs, technology lists, featured and publication flags. The
additive `3c0e8a1594b2` migration also adds editable professional profile fields
without dropping or rewriting existing records. Apply it with the existing
`flask --app run:app db upgrade` deployment command. Digital Marketing package
names and prices are seeded only when package data is absent; the seed command
does not replace existing customized package descriptions or inclusions.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```