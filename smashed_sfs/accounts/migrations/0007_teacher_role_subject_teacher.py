# Generated manually (see accounts/models.py Teacher.ROLE_CHOICES)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_teacher_role_non_teaching'),
    ]

    operations = [
        migrations.AlterField(
            model_name='teacher',
            name='role',
            field=models.CharField(
                choices=[
                    ('adviser', 'Class Adviser'),
                    ('registrar', 'Registrar'),
                    ('principal', 'Principal'),
                    ('non_teaching', 'Non-Teaching'),
                    ('subject_teacher', 'Subject Teacher'),
                ],
                default='adviser',
                max_length=20,
            ),
        ),
    ]
