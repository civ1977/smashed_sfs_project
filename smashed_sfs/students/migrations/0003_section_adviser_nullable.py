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

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0002_alter_schoolprofile_created_by_section_student'),
    ]

    operations = [
        migrations.AlterField(
            model_name='section',
            name='adviser_id',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
