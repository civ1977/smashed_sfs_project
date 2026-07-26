# Generated manually (see accounts/models.py Teacher.ROLE_CHOICES)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_alter_teacher_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='teacher',
            name='role',
            field=models.CharField(
                choices=[
                    ('adviser', 'Adviser'),
                    ('registrar', 'Registrar'),
                    ('principal', 'Principal'),
                ],
                default='adviser',
                max_length=20,
            ),
        ),
    ]
