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
python test_db.py                   # standalone script: verifies raw pymysql connection to the DB
```

There is no configured test runner beyond Django's default; each app has an empty `tests.py`
(no tests currently exist — `python manage.py test` will pass trivially). There is no
requirements.txt — dependencies (Django, PyMySQL) must be inferred from imports and installed
manually if setting up a fresh environment.

## Database

MySQL via PyMySQL, patched in as MySQLdb (`smashed_sfs/settings.py`: `pymysql.install_as_MySQLdb()`).
Connection settings (host/user/password/db name `smashed_sfs`) are hardcoded in
`smashed_sfs/settings.py` and duplicated in `test_db.py` — there is no `.env`/secrets layer.

`models_auto.py` at the repo root is a stray `inspectdb` dump (all `managed = False`) — it is not
imported anywhere and does not reflect the real app models. Don't edit it; the real models live in
each app's `models.py`.

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

## `reports` app is scaffolded but not implemented

`reports/urls.py` declares routes (`select_student_report`, `view_sf9`, `view_sf10`,
`generate_sf9_excel`, `generate_sf10_excel`) but `reports/views.py` is still the empty Django
stub — none of these view functions exist yet. `reports/urls.py` is also **not included** in
`smashed_sfs/urls.py`'s `urlpatterns`, so the app isn't reachable at all currently. If asked to
build out SF9/SF10 report generation, you'll need to both implement the views in
`reports/views.py` and wire `path('reports/', include('reports.urls'))` into the root urlconf.
`reports/models.py` is empty — report data is expected to be assembled from `students`/`grades`
models at render time, not stored.

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
