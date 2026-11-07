# Portfolio Backend

Flask API for the portfolio frontend. It provides public portfolio and inquiry
endpoints, JWT-cookie admin authentication, protected content management, and
image uploads.

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
for an email and a password of at least 12 characters; there is no public
registration route.

## Deploy on Render

Create a Blueprint from this repository and select `render.yaml`. The Blueprint
creates a free Flask service and a free PostgreSQL database. During setup, enter
the frontend origin and the initial admin email and password when prompted.
After the first successful deploy creates the admin account, remove
`INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` from the service environment.

Set `FRONTEND_ORIGIN` to the exact frontend `onrender.com` origin. The frontend
Blueprint separately prompts for `VITE_API_BASE_URL`; set it to the API URL with
`/api` appended. Both values must match the deployed service URLs.

This free configuration is for a demo, not production: the web service spins
down when idle and its local uploads are lost on restart or deploy. The free
PostgreSQL database expires after 30 days. Upgrade to paid persistent services
before relying on saved content or uploaded media.

## Configuration

Configure `FRONTEND_ORIGIN`, `DATABASE_URL`, `SECRET_KEY`, `JWT_SECRET_KEY`,
`COOKIE_SECURE`, `COOKIE_SAMESITE`, and `UPLOAD_FOLDER` through the environment.
Use unique random signing keys and a durable database and upload location in
production. Never commit `.env` files, local databases, or uploaded media.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```