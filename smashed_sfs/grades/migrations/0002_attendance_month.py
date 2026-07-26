# Generated manually (see grades/models.py ATTENDANCE_MONTHS)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='attendance',
            name='term',
        ),
        migrations.AddField(
            model_name='attendance',
            name='month',
            field=models.CharField(
                choices=[
                    ('Jun', 'Jun'), ('Jul', 'Jul'), ('Aug', 'Aug'), ('Sep', 'Sep'),
                    ('Oct', 'Oct'), ('Nov', 'Nov'), ('Dec', 'Dec'), ('Jan', 'Jan'),
                    ('Feb', 'Feb'), ('Mar', 'Mar'), ('Apr', 'Apr'),
                ],
                default='Jun',
                max_length=3,
            ),
            preserve_default=False,
        ),
    ]
