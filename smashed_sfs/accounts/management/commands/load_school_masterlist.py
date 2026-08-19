import json

from django.core.management.base import BaseCommand
from django.conf import settings

from accounts.models import SchoolMasterlistEntry

DEFAULT_PATH = settings.BASE_DIR / 'accounts' / 'data' / 'school_masterlist.json'


class Command(BaseCommand):
    help = (
        "Loads DepEd's SY 2020-2021 Masterlist of Schools (accounts/data/school_masterlist.json) "
        "into SchoolMasterlistEntry - reference data for the Complete Your Profile page's cascading "
        "Region/Division/Municipality/District/School picker. Safe to re-run: clears and reloads."
    )

    def add_arguments(self, parser):
        parser.add_argument('--path', default=str(DEFAULT_PATH))

    def handle(self, *args, **options):
        path = options['path']
        with open(path, encoding='utf-8') as f:
            rows = json.load(f)

        self.stdout.write(f'Read {len(rows)} rows from {path}')

        SchoolMasterlistEntry.objects.all().delete()

        # A handful of rows (~1.5%, concentrated in one Ilocos Sur district
        # group where the source PDF's table columns visually overlapped)
        # came out of extraction with a garbled school_id - not a real BEIS
        # ID, and too long for the column anyway. Skip rather than load junk;
        # a school that lands here can still be added via the "or enter a
        # new..." fields on the form.
        skipped = 0
        batch = []
        for row in rows:
            school_id = row['school_id']
            if not school_id.isdigit() or len(school_id) > 20:
                skipped += 1
                continue
            batch.append(SchoolMasterlistEntry(
                region=row['region'],
                division=row['division'],
                municipality=row['municipality'],
                district=row['district'][:150],
                school_id=school_id,
                school_name=row['school_name'][:200],
            ))
            if len(batch) >= 2000:
                SchoolMasterlistEntry.objects.bulk_create(batch)
                batch = []
        if batch:
            SchoolMasterlistEntry.objects.bulk_create(batch)

        self.stdout.write(self.style.SUCCESS(
            f'Loaded {SchoolMasterlistEntry.objects.count()} SchoolMasterlistEntry rows '
            f'({skipped} skipped for a garbled school_id).'
        ))
