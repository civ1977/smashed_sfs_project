# Generated manually (see accounts/models.py Teacher.ROLE_CHOICES)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_teacher_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='teacher',
            name='role',
            field=models.CharField(
                choices=[
                    ('adviser', 'Adviser'),
                    ('registrar', 'Registrar'),
                    ('principal', 'Principal'),
                    ('non_teaching', 'Non-Teaching'),
                ],
                default='adviser',
                max_length=20,
            ),
        ),
    ]
