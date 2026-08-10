# Generated manually (see grades/models.py ATTENDANCE_MONTHS)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0001_initial'),
    ]

    operations = [
        # Added during the "Migration history vs. real schema" reconciliation
        # (see CLAUDE.md): 0001_initial's Attendance.unique_together was
        # {('student', 'term')} - removing `term` below without first
        # clearing that made a from-scratch build crash much later, in
        # 0005_alter_attendance_unique_together_and_more, when Django tried
        # to compute the old unique_together's columns and 'term' no longer
        # existed. Must come before the RemoveField immediately below.
        migrations.AlterUniqueTogether(
            name='attendance',
            unique_together=set(),
        ),
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
