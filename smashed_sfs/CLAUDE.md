# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Django app ("smashed_sfs") for DepEd (Philippine Dept. of Education) SHS teachers/advisers to
upload student records, enter grades, and (eventually) generate SF9/SF10 report forms. Single
Django project (`smashed_sfs/`) with four apps: `accounts`, `students`, `grades`, `reports`.

## Commands

Run everything from the repo root (where `manage.py` lives).

```powershell
python manage.py runserver          # dev server
python manage.py makemigrations     # after changing any app's models.py
python manage.py migrate            # apply migrations
python manage.py createsuperuser    # for /admin/
python db_check.py                  # standalone script: verifies raw pymysql connection to the DB
```

There is no configured test runner beyond Django's default. `db_check.py` is deliberately *not*
named `test_db.py` — Django's test discovery matches any `test*.py` file, and a `test_db.py` at
the repo root used to get imported as a test module (crashing on Windows' console encoding
because of its ✅/❌ print output) every time `python manage.py test` ran.

`accounts/tests.py`, `grades/tests.py`, and `reports/tests.py` have real coverage (grade-range validation, the
subject-strand scoping in `save_grades`, and the pure report-shaping helpers in
`reports/views.py` like `_final_average`/`_build_subject_rows`/`_gate_finals_pending_term3`);
`accounts`, `students`, `portal`, and `school` still have empty stubs. `manage.py test` runs
against an isolated in-memory SQLite database with migrations disabled (see the `if 'test' in
sys.argv` block in `settings.py`) rather than replaying the real migration history against MySQL
— faster and fully isolated, not a workaround for a broken replay (that's fixed now — see
"Migration history vs. real schema" below).

`requirements.txt` pins the three third-party dependencies (Django, PyMySQL, openpyxl) plus
`whitenoise` (production static file serving — see `## Deployment` below). See `README.md` for
human-facing setup instructions (this file is written for an AI assistant's use, not onboarding).

## Database

MySQL via PyMySQL, patched in as MySQLdb (`smashed_sfs/settings.py`: `pymysql.install_as_MySQLdb()`).
Connection settings (host/user/password) come from `DB_USER`/`DB_PASSWORD` env vars via `.env`
(`python-dotenv`) — both `settings.py` and the standalone `db_check.py` raise/exit loudly if they're
unset rather than falling back to a default credential.

`models_auto.py` at the repo root is a stray `inspectdb` dump (all `managed = False`) — it is not
imported anywhere and does not reflect the real app models. Don't edit it; the real models live in
each app's `models.py`.

## Migration history vs. real schema

The real MySQL database has **24 real, enforced foreign-key constraints** at the DB level — on
`student`, `section`, `grades`, `subject_mapping`, `attendance`, and `school_profile` — even though
none of those relationships are declared as Django `ForeignKey` fields (see "Architecture: manual
foreign keys" above; that's still accurate at the *model* level, just not at the *database* level).
Several of these `ON DELETE CASCADE`, which is real, silent, DB-enforced cascading behavior that
the Python code has no visibility into — e.g. deleting a `Teacher` row would cascade-delete all
their sections, students, grades, attendance, and subject mappings, with no warning beyond whatever
the deleting code happens to check itself (see `school/views.py`'s `delete_section`, which guards
against orphaning precisely because of this). `admin_backup.py`'s generic delete tools have no such
guard and would surface this as an unhandled `IntegrityError` (from the constraints *without*
cascade, like `fk_teacher_school`) or an unexpectedly wide cascade (from the ones that do) if ever
used on a row with dependents.

These constraints exist because someone added them directly via raw SQL, outside any migration —
confirmed by their MySQL-auto-generated names (`section_ibfk_1`, `school_profile_ibfk_1`, etc.)
differing from Django's own naming convention, and by the fact no migration file created most of
them. As a result, replaying the full migration history from an empty database used to fail
outright, in three independent ways (all now fixed):

1. `students/migrations/0001_initial.py` creates `SchoolProfile.created_by` as a `ForeignKey` to
   `Teacher` while `Teacher`'s PK was still the implicit `id` column; `accounts/migrations/0003`
   later drops that `id` column (replacing it with `teacher_id`) without touching the dependent FK.
   Fixed by inserting `students/migrations/0001b_drop_created_by_fk_before_teacher_pk_rename.py`
   (converts `created_by` to a plain field first) ahead of `accounts/0003` in the dependency graph.
2. `students/migrations/0004_...` removes `Section.adviser` (a `ForeignKey`, physical column
   `adviser_id`) but never added back a plain `adviser_id` field — unlike the equivalent `Student`
   fields in the same migration, which do. Fixed by adding the missing `AddField`, and turning the
   now-redundant `AlterField` in `0003_section_adviser_nullable.py` (which ran before the field
   existed) into a no-op.
3. `grades/migrations/0002_attendance_month.py` removes `Attendance.term` without first clearing
   the `unique_together = {('student', 'term')}` that referenced it, and
   `grades/migrations/0005_...` added `SubjectMapping.school_profile_id` before removing
   `SubjectMapping.school_profile` (same physical column, wrong order). Fixed in place.

The 24 real constraints themselves are now also formally declared via `migrations.RunSQL` in
`students/migrations/0006_add_hidden_fk_constraints.py`, `accounts/migrations/0012_...`, and
`grades/migrations/0016_...` — model field types are unchanged (still plain `IntegerField`s, per
the app's manual-FK convention), this only makes a from-scratch `migrate` reproduce the real
schema's constraints and `ON DELETE` behavior. These were fake-applied on the real dev database
(`migrate <app> <migration> --fake`) since the constraints already existed there; verified with a
byte-for-byte column/constraint diff against a real from-scratch rebuild in a throwaway database
that the two now match exactly (aside from one cosmetic FK constraint name).

If you add a new cross-model relationship, decide deliberately whether it needs a real DB-level FK
(add it the same way, formally, via a migration) or should stay purely a Python-level convention —
don't let it happen by accident via undocumented raw SQL again.

## Architecture: manual foreign keys, no `ForeignKey` fields

This is the most important thing to know before touching models or views. Relationships between
apps are **not** expressed as Django `ForeignKey`s — they're plain `IntegerField`/`CharField`
columns holding another table's PK, resolved manually in view code via separate queries:

- `students.Section.adviser_id` / `students.Student.adviser_id` → `accounts.Teacher.teacher_id`
- `students.Student.section_id` → `students.Section.section_id`
- `students.SchoolProfile` ↔ `accounts.Teacher.school_profile_id` (loose link, not a real FK)
- `grades.SubjectMapping.school_profile_id` → `students.SchoolProfile.profile_id`
- `grades.Grade.lrn` → `students.Student.lrn` (PK is the LRN string itself, not an autoincrement id)
- `grades.Grade.mapping_id` → `grades.SubjectMapping.mapping_id`

This is intentional (likely to mirror an existing external MySQL schema — see `models_auto.py` for
what the "real" FK-annotated schema would look like), but it means:
- There are no cascading deletes, no `select_related`/`prefetch_related` joins, and no
  `.<relation>` reverse accessors — every cross-model lookup is a manual `.objects.get(...)` or
  `.objects.filter(...)` by the raw id field.
- When adding a new relationship, follow the existing convention (`whatever_id = IntegerField()`)
  unless you're deliberately migrating the schema to real FKs — don't mix styles within a model.

`accounts.Teacher` is a **separate model from Django's `auth.User`**, linked by an optional
`OneToOneField` (`user`) but views mostly resolve the current teacher via
`Teacher.objects.get(username=request.user.username)`, not `request.user.teacher`. Every
teacher-scoped view in `students` and `grades` follows this pattern:
```python
teacher = Teacher.objects.get(username=request.user.username)
# then filter students/grades by teacher.teacher_id (as adviser_id)
```
If `Teacher.DoesNotExist`, the view redirects with an error message rather than raising — replicate
this pattern rather than letting it 500.

## Password reset

Wired at `smashed_sfs/urls.py` using Django's built-in `auth.views.PasswordReset*` class-based
views (not custom ones) against `templates/accounts/password_reset*.html`, since both
`accounts.register()` and `portal.portal_register()` set `User.email`, so one flow covers
teachers and students alike - there's no separate reset path per account type. Email delivery
goes through `EMAIL_BACKEND` in `settings.py`: defaults to the console backend when `DEBUG=True`
(reset links print to the runserver console, no setup needed) and would need real
`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` env vars for actual delivery outside local dev.

## CSV upload → preview → save flow

Both `students` and `grades` uploads follow a two-step pattern instead of saving directly:
1. `upload_students` / `upload_grades` (GET or POST with `csv_file`): parses the CSV with the
   stdlib `csv` module, stashes parsed rows into `request.session` (`student_preview_data` /
   `grade_preview_data`, plus `grade_term`/`grade_headers`/`grade_replace_all` for grades), and
   re-renders the same upload template with an editable preview table.
2. `save_students` / `save_grades` (POST only): reads back `row_count` and per-row fields named
   like `lrn_{i}`, `surname_{i}`, `grade_{i}_{subject_num}`, etc. from POST data (not from the
   session) and persists them, then clears the session preview keys.

Date parsing across both apps goes through a local `convert_date()` helper (duplicated in
`students/views.py` and `grades/views.py`) that tries a fixed list of `strptime` formats.

Grades are stored per (student, subject mapping, term); `grades.views.save_grades` validates each
grade is in the 60–100 range and dynamically creates/updates `SubjectMapping` rows for subjects
1–30 when `update_subjects` is checked on the form.

## `reports` app is implemented (SF9/SF10 view + print-to-PDF)

`reports/urls.py` is wired into `smashed_sfs/urls.py` at `path('reports/', include('reports.urls'))`.
`reports/views.py` implements `select_student_for_report`, `view_sf9`, and `view_sf10` (see commits
3b0027b, 0e75964, 463f79a), rendering `reports/select_student.html`, `reports/sf9.html`, and
`reports/sf10.html`. There are no `generate_sf9_excel`/`generate_sf10_excel` views — an earlier Excel
export was deliberately replaced by print-to-PDF (commit 0e75964): the SF9/SF10 templates are styled
to match the DepEd form and are meant to be printed/saved as PDF straight from the browser, not
exported server-side. Don't reintroduce Excel export unless explicitly asked.

As with `students`/`grades`, both view functions resolve the current teacher via
`Teacher.objects.get(username=request.user.username)` and redirect with an error message on
`Teacher.DoesNotExist` rather than raising. `reports/models.py` is empty — report data is assembled
from `students`/`grades` models at render time (helper functions in `reports/views.py` like
`_build_subject_rows`, `_attendance_rows`, `_gate_finals_pending_term3`), not stored.

## Deployment

Local dev needs zero configuration — every setting below has a working default. For anything
beyond `runserver` on localhost, `smashed_sfs/settings.py` reads these environment variables
(none are required to be set locally):

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` — see
  the comments directly above each in `settings.py`.
- `DB_PASSWORD` — overrides the hardcoded local MySQL password.
- `EMAIL_BACKEND`/`EMAIL_HOST`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`/`EMAIL_USE_TLS`/
  `DEFAULT_FROM_EMAIL` — for the password-reset flow's emails; defaults to the console backend.

Static files: `whitenoise` (in `MIDDLEWARE`) serves them directly from the app process once
`DEBUG=False`, after running `python manage.py collectstatic` to populate `STATIC_ROOT`
(`staticfiles/`, gitignored, not built by default). Under `DEBUG=True` this is skipped entirely —
`STORAGES['staticfiles']` is set conditionally in `settings.py` because whitenoise's
`CompressedManifestStaticFilesStorage` requires that `collectstatic` manifest to exist before any
`{% static %}` tag resolves, which would otherwise break local `runserver` and `manage.py test`.

Logging: `LOGGING` in `settings.py` always writes ERROR+ to a rotating file under `logs/`
(gitignored) in addition to the console, so errors aren't silently lost once `DEBUG=False` stops
showing Django's debug page.

There's still no `Procfile`/Dockerfile/CI config — deployment is otherwise unopinionated.

## Templates

Two template roots are both active: the project-level `templates/` dir (`templates/accounts/`,
`templates/students/`, `templates/grades/`, plus shared `templates/base.html`) is on
`TEMPLATES[0]['DIRS']`, and each app also has `APP_DIRS = True`. Note `accounts/register.html` and
`accounts/dashboard.html` exist directly under the `accounts/` app dir (not `accounts/templates/accounts/`)
— check which template actually resolves before assuming `templates/accounts/*.html` is the only copy in play.

All pages extend `templates/base.html`, which defines the header/nav, flash-message rendering
(`{% if messages %}`), and the shared `.btn`/`.card`/`.alert`/`.form-group` CSS classes — reuse
these rather than adding new inline styles.

`grades/templatetags/grade_filters.py` provides `{{ dict|get:key }}` (and `map` as an alias) since
Django templates can't index a dict by a variable key directly; used in `grades/list.html` /
`grades/view.html` to look up per-subject grades keyed by `mapping_id`.
