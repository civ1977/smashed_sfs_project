from django.db import migrations


class Migration(migrations.Migration):
    """Declares FK constraints that already exist on the real MySQL database
    but were never created by any migration (they were added directly via
    raw SQL at some point outside Django's history - see CLAUDE.md's
    "## Migration history vs. real schema" note). Fields stay plain
    IntegerFields at the Django/model level (unchanged, per the app's
    documented manual-FK convention) - this only makes the migration
    history able to reproduce the real database's constraints, including
    their ON DELETE behavior, when building a fresh database from scratch.
    """

    dependencies = [
        ('students', '0005_schoolprofile_show_core_heading_and_more'),
        ('accounts', '0011_alter_teachertimerecord_unique_together_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE school_profile "
                "ADD CONSTRAINT school_profile_ibfk_1 FOREIGN KEY (created_by) "
                "REFERENCES teacher_adviser (teacher_id) ON DELETE SET NULL;"
            ),
            reverse_sql="ALTER TABLE school_profile DROP FOREIGN KEY school_profile_ibfk_1;",
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE section "
                "ADD CONSTRAINT section_ibfk_1 FOREIGN KEY (adviser_id) "
                "REFERENCES teacher_adviser (teacher_id) ON DELETE CASCADE;"
            ),
            reverse_sql="ALTER TABLE section DROP FOREIGN KEY section_ibfk_1;",
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE section "
                "ADD CONSTRAINT section_ibfk_2 FOREIGN KEY (school_profile_id) "
                "REFERENCES school_profile (profile_id) ON DELETE CASCADE;"
            ),
            reverse_sql="ALTER TABLE section DROP FOREIGN KEY section_ibfk_2;",
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE student "
                "ADD CONSTRAINT student_ibfk_1 FOREIGN KEY (section_id) "
                "REFERENCES section (section_id) ON DELETE CASCADE;"
            ),
            reverse_sql="ALTER TABLE student DROP FOREIGN KEY student_ibfk_1;",
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE student "
                "ADD CONSTRAINT student_ibfk_2 FOREIGN KEY (adviser_id) "
                "REFERENCES teacher_adviser (teacher_id) ON DELETE CASCADE;"
            ),
            reverse_sql="ALTER TABLE student DROP FOREIGN KEY student_ibfk_2;",
        ),
    ]
