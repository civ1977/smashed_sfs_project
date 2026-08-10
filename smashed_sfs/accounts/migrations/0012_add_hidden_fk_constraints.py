from django.db import migrations


class Migration(migrations.Migration):
    """See students/migrations/0006_add_hidden_fk_constraints.py - same
    reconciliation, for the one hidden constraint on this app's table."""

    dependencies = [
        ('accounts', '0011_alter_teachertimerecord_unique_together_and_more'),
        ('students', '0006_add_hidden_fk_constraints'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE teacher_adviser "
                "ADD CONSTRAINT fk_teacher_school FOREIGN KEY (school_profile_id) "
                "REFERENCES school_profile (profile_id);"
            ),
            reverse_sql="ALTER TABLE teacher_adviser DROP FOREIGN KEY fk_teacher_school;",
        ),
    ]
