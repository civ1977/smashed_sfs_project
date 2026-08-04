# Generated manually (see portal/migrations/0001_initial.py for why this
# app's migrations are hand-written)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentaccount',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
