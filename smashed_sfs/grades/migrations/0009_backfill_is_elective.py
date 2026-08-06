from django.db import migrations


def backfill_is_elective(apps, schema_editor):
    """One-time backfill matching the name-based heuristic reports/views.py
    used before SubjectMapping.is_elective existed, so existing SF9/SF10
    output doesn't change until a teacher explicitly re-arranges subjects
    on the new Core/Elective drag-and-drop page."""
    SubjectMapping = apps.get_model('grades', 'SubjectMapping')
    SubjectMapping.objects.filter(subject_name__icontains='elective').update(is_elective=True)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0008_subjectmapping_is_elective'),
    ]

    operations = [
        migrations.RunPython(backfill_is_elective, reverse_noop),
    ]
