# Smashed SFS

A Django app for DepEd (Philippine Dept. of Education) Senior High School teachers/advisers to
upload student records, enter grades, and generate SF9/SF10 report forms.

## Requirements

- Python 3.11+
- MySQL Server, running locally, with a database named `smashed_sfs`

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Create the MySQL database (once):

   ```sql
   CREATE DATABASE smashed_sfs CHARACTER SET utf8mb4;
   ```

3. Set `DB_USER` and `DB_PASSWORD` (e.g. in a `.env` file — copy `.env.example` to `.env`
   and fill them in). There is no default/root fallback: `settings.py` raises an error on
   startup if these aren't set, so create a least-privilege MySQL user for this database
   first (see `CLAUDE.md` for the `CREATE USER` / `GRANT` statement).

4. Apply migrations:

   ```bash
   python manage.py migrate
   ```

5. Create an admin account for `/admin/`:

   ```bash
   python manage.py createsuperuser
   ```

6. Run the dev server:

   ```bash
   python manage.py runserver
   ```

   The app is now at http://127.0.0.1:8000/. Teacher/student accounts are created through the
   app's own `/register/` page, not `createsuperuser` (that's only for `/admin/`).

## Running tests

```bash
python manage.py test
```

Tests run against an isolated in-memory SQLite database and never touch the real MySQL database
(see `CLAUDE.md`'s Commands section for why).

## Checking the database connection

```bash
python db_check.py
```

A standalone script (not part of the Django test suite) that just verifies a raw MySQL connection
using the same credentials as `settings.py`.

## Password reset emails

By default, password-reset emails print to the console instead of actually being sent — fine for
local development. To send real emails, set these environment variables to a real SMTP account
(e.g. a Gmail address with an [App Password](https://myaccount.google.com/apppasswords)):

```bash
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-address@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
EMAIL_USE_TLS=True
```

## Deploying beyond your own machine

Local dev needs none of this — it's only relevant if you're exposing the app beyond localhost
(a tunnel, a real server, etc.). Set these environment variables first:

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | A real secret key (generate one, don't reuse the dev default) |
| `DJANGO_DEBUG` | Set to `False` — with `DEBUG=True`, unhandled errors show a full stack trace/settings dump to whoever triggers them |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames the app will answer to |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated origins (with scheme) allowed to POST, e.g. a tunnel's URL |
| `DB_PASSWORD` | Your real MySQL password — don't leave the default in place |

Then, before starting the server:

```bash
python manage.py collectstatic --noinput
```

This populates `staticfiles/`, which `whitenoise` (already wired into `MIDDLEWARE`) serves
directly — no separate web server needed for static files. Application errors (ERROR level and
up) are written to `logs/django.log` in addition to the console.

There's no `Procfile`/Dockerfile/CI setup yet — how you actually run the process (gunicorn,
systemd, etc.) is up to you.

## More detail for AI coding assistants

See `CLAUDE.md` — it documents the app's architecture (notably: no Django `ForeignKey` fields,
relationships are manual integer-id lookups) in more depth than this file does.
