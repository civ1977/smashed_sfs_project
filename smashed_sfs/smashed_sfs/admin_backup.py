"""Per-group JSON backup downloads, added onto the admin site at
/admin/backup/<group-slug>/. Reads the exact same group -> model mapping
admin_grouping.py uses for the index page (resolve_group_keys), so each
group's "Download Backup" button always exports precisely the tables
that group displays - nothing more, nothing less.

The output is Django's own dumpdata format (a JSON array of
{"model": ..., "pk": ..., "fields": {...}} objects), so it's a genuine,
restorable backup: `python manage.py loaddata <file>` can load it back
in, not just a human-readable export.
"""
import json
from datetime import date

from django.contrib import admin
from django.core import serializers
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, HttpResponseNotFound
from django.urls import path

from . import admin_grouping


def _model_lookup():
    return {(model._meta.app_label, model.__name__): model for model in admin.site._registry}


def backup_group_view(request, slug):
    keys = admin_grouping.resolve_group_keys(slug)
    if keys is None:
        return HttpResponseNotFound('Unknown backup group.')

    lookup = _model_lookup()
    records = []
    for app_label, object_name in keys:
        model = lookup.get((app_label, object_name))
        if model is None:
            continue
        records.extend(serializers.serialize('python', model.objects.all().order_by('pk')))

    payload = json.dumps(records, indent=2, cls=DjangoJSONEncoder)
    filename = f'{slug}_backup_{date.today().isoformat()}.json'
    response = HttpResponse(payload, content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def apply():
    original_get_urls = admin.site.get_urls

    def get_urls():
        custom = [
            path('backup/<slug:slug>/', admin.site.admin_view(backup_group_view), name='group_backup'),
        ]
        return custom + original_get_urls()

    admin.site.get_urls = get_urls
