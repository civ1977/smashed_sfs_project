from django.db import migrations, models


class Migration(migrations.Migration):
    """Retroactively inserted between 0001_initial and
    0002_alter_schoolprofile_created_by_section_student. students/0001_initial
    creates SchoolProfile.created_by as a ForeignKey to accounts.Teacher while
    Teacher's PK is still the implicit `id` column; accounts/0003 then removes
    that `id` column to replace it with `teacher_id`, but never touches this
    dependent FK - so building a database from scratch fails right there
    (MySQL refuses to drop a column a live FK constraint still points at).
    This migration converts created_by to a plain IntegerField first so
    accounts/0003 has nothing blocking it; 0002 (which already depends on
    accounts/0003) re-establishes it as a ForeignKey once Teacher's PK is
    teacher_id, and 0004 later converts it to a plain IntegerField for good,
    matching the app's real, final manual-FK convention. See CLAUDE.md's
    "Migration history vs. real schema" note for the full story."""

    dependencies = [
        ('students', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='schoolprofile',
            name='created_by',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
