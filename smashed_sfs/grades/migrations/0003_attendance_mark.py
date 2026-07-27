# Generated manually (see 0002_attendance_month.py for why: the accounts
# app's migration chain has pre-existing unrelated drift that
# makemigrations chokes on for the whole project, not just this app)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0002_attendance_month'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceMark',
            fields=[
                ('mark_id', models.AutoField(primary_key=True, serialize=False)),
                ('lrn', models.CharField(max_length=12)),
                ('date', models.DateField()),
                ('status', models.CharField(
                    choices=[
                        ('absent', 'Absent'),
                        ('late_comer', 'Late Comer'),
                        ('cutting_classes', 'Cutting Classes'),
                    ],
                    max_length=20,
                )),
                ('remarks', models.TextField(blank=True, null=True)),
                ('recorded_by', models.IntegerField()),
            ],
            options={
                'db_table': 'attendance_mark',
                'unique_together': {('lrn', 'date')},
            },
        ),
        migrations.CreateModel(
            name='SchoolCalendarException',
            fields=[
                ('exception_id', models.AutoField(primary_key=True, serialize=False)),
                ('school_profile_id', models.IntegerField()),
                ('date', models.DateField()),
                ('is_school_day', models.BooleanField()),
            ],
            options={
                'db_table': 'school_calendar_exception',
                'unique_together': {('school_profile_id', 'date')},
            },
        ),
    ]
