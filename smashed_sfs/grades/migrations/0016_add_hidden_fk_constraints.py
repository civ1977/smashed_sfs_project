from django.db import migrations


class Migration(migrations.Migration):
    """See students/migrations/0006_add_hidden_fk_constraints.py - same
    reconciliation, for this app's tables (attendance, grades,
    subject_mapping)."""

    dependencies = [
        ('grades', '0015_remove_teachersubjectassignment_schedule_and_more'),
        ('students', '0006_add_hidden_fk_constraints'),
        ('accounts', '0011_alter_teachertimerecord_unique_together_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE attendance "
                "ADD CONSTRAINT attendance_ibfk_1 FOREIGN KEY (lrn) "
                "REFERENCES student (lrn) ON DELETE CASCADE;"
            ),
            reverse_sql="ALTER TABLE attendance DROP FOREIGN KEY attendance_ibfk_1;",
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE attendance "
                "ADD CONSTRAINT attendance_ibfk_2 FOREIGN KEY (uploaded_by) "
                "REFERENCES teacher_adviser (teacher_id) ON DELETE CASCADE;"
            ),
            reverse_sql="ALTER TABLE attendance DROP FOREIGN KEY attendance_ibfk_2;",
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE grades "
                "ADD CONSTRAINT grades_ibfk_1 FOREIGN KEY (lrn) "
                "REFERENCES student (lrn) ON DELETE CASCADE;"
            ),
            reverse_sql="ALTER TABLE grades DROP FOREIGN KEY grades_ibfk_1;",
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE grades "
                "ADD CONSTRAINT grades_ibfk_2 FOREIGN KEY (mapping_id) "
                "REFERENCES subject_mapping (mapping_id) ON DELETE CASCADE;"
            ),
            reverse_sql="ALTER TABLE grades DROP FOREIGN KEY grades_ibfk_2;",
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE grades "
                "ADD CONSTRAINT grades_ibfk_3 FOREIGN KEY (uploaded_by) "
                "REFERENCES teacher_adviser (teacher_id) ON DELETE CASCADE;"
            ),
            reverse_sql="ALTER TABLE grades DROP FOREIGN KEY grades_ibfk_3;",
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE subject_mapping "
                "ADD CONSTRAINT subject_mapping_ibfk_1 FOREIGN KEY (school_profile_id) "
                "REFERENCES school_profile (profile_id) ON DELETE CASCADE;"
            ),
            reverse_sql="ALTER TABLE subject_mapping DROP FOREIGN KEY subject_mapping_ibfk_1;",
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE subject_mapping "
                "ADD CONSTRAINT subject_mapping_ibfk_2 FOREIGN KEY (created_by) "
                "REFERENCES teacher_adviser (teacher_id) ON DELETE CASCADE;"
            ),
            reverse_sql="ALTER TABLE subject_mapping DROP FOREIGN KEY subject_mapping_ibfk_2;",
        ),
    ]
