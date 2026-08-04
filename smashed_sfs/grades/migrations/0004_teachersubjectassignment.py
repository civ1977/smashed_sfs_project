# Generated manually (see 0002_attendance_month.py for why: the accounts
# app's migration chain has pre-existing unrelated drift that
# makemigrations chokes on for the whole project, not just this app)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0003_attendance_mark'),
    ]

    operations = [
        migrations.CreateModel(
            name='TeacherSubjectAssignment',
            fields=[
                ('assignment_id', models.AutoField(primary_key=True, serialize=False)),
                ('teacher_id', models.IntegerField()),
                ('section_id', models.IntegerField()),
                ('mapping_id', models.IntegerField()),
            ],
            options={
                'db_table': 'teacher_subject_assignment',
            },
        ),
    ]
