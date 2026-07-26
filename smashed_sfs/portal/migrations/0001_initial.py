# Generated manually (see grades/migrations/0002_attendance_month.py and
# accounts/migrations/0005_teacher_role.py for why: the accounts app's
# migration chain has pre-existing unrelated drift that makemigrations
# chokes on for the whole project, not just this app)

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentAccount',
            fields=[
                ('account_id', models.AutoField(primary_key=True, serialize=False)),
                ('lrn', models.CharField(max_length=12)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('approved', 'Approved'),
                        ('rejected', 'Rejected'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('decided_by', models.IntegerField(blank=True, null=True)),
                ('user', models.OneToOneField(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'student_account',
            },
        ),
    ]
