# Generated manually (see grades/migrations/0002_attendance_month.py and
# accounts/migrations/0005_teacher_role.py for why: the accounts app's
# migration chain has pre-existing unrelated drift that makemigrations
# chokes on for the whole project, not just this app)
#
# Section.adviser_id becomes nullable so a registrar/principal can create
# a section before an adviser is assigned to it (school/views.py
# school_sections). The real FK constraint (section.adviser_id ->
# teacher_adviser.teacher_id) already permits NULL values in MySQL - it
# only enforces referential integrity when the column is non-null.
#
# No-op as of the "Migration history vs. real schema" reconciliation (see
# CLAUDE.md): this originally AlterField'd `section.adviser_id`, but that
# field doesn't actually exist yet at this point in a from-scratch build -
# it's still the ForeignKey `adviser` from 0002 (Section.adviser is only
# replaced with a plain, nullable `adviser_id` in 0004, which was missing
# that AddField and has now been fixed to include it, already nullable).
# This step is kept only so nothing else has to depend on a different
# migration name; deleting it outright would be equally correct but riskier
# to reconcile against the already-applied real database.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0002_alter_schoolprofile_created_by_section_student'),
    ]

    operations = []
