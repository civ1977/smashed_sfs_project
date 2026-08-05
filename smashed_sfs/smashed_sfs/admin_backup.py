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

from django.contrib import admin, messages
from django.core import serializers
from django.core.serializers.base import DeserializationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import redirect, render
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


def _model_key(deserialized_obj):
    obj = deserialized_obj.object
    return f'{obj._meta.app_label}.{type(obj).__name__}'.lower()


def restore_group_view(request, slug):
    keys = admin_grouping.resolve_group_keys(slug)
    group_name = admin_grouping.group_name_for_slug(slug)
    if keys is None:
        return HttpResponseNotFound('Unknown backup group.')

    allowed = {f'{app_label}.{object_name}'.lower() for app_label, object_name in keys}
    session_key = f'restore_payload_{slug}'

    context = {
        **admin.site.each_context(request),
        'title': f'Restore Backup - {group_name}',
        'group_name': group_name,
        'slug': slug,
    }

    if request.method == 'POST' and request.POST.get('action') == 'confirm':
        payload = request.session.get(session_key)
        if not payload:
            messages.error(request, 'Nothing staged to restore - upload a backup file first.')
            return redirect('admin:group_restore', slug=slug)

        try:
            deserialized = list(serializers.deserialize('json', payload))
        except (DeserializationError, ValueError):
            request.session.pop(session_key, None)
            messages.error(request, 'That backup data could not be read - it may be corrupted.')
            return redirect('admin:group_restore', slug=slug)

        saved, skipped = 0, 0
        with transaction.atomic():
            for obj in deserialized:
                if _model_key(obj) not in allowed:
                    skipped += 1
                    continue
                obj.save()
                saved += 1

        request.session.pop(session_key, None)
        message = f'Restored {saved} record(s) into {group_name}.'
        if skipped:
            message += f' Skipped {skipped} record(s) that did not belong to this group.'
        messages.success(request, message)
        return redirect('admin:index')

    if request.method == 'POST' and 'backup_file' in request.FILES:
        uploaded = request.FILES['backup_file']
        try:
            payload = uploaded.read().decode('utf-8-sig')
            deserialized = list(serializers.deserialize('json', payload))
        except (DeserializationError, ValueError, UnicodeDecodeError):
            messages.error(request, 'That file could not be read as a backup - make sure it is an unmodified .json backup downloaded from this admin.')
            return render(request, 'admin/restore_backup.html', context)

        counts = {}
        skipped = 0
        for obj in deserialized:
            key = _model_key(obj)
            if key not in allowed:
                skipped += 1
                continue
            counts[key] = counts.get(key, 0) + 1

        if not counts:
            if skipped:
                messages.error(
                    request,
                    f"This file doesn't contain any records for {group_name} - it looks like a "
                    f"backup from a different group ({skipped} record(s) skipped)."
                )
            else:
                messages.info(request, 'That file has no records in it.')
            return render(request, 'admin/restore_backup.html', context)

        request.session[session_key] = payload
        context.update({
            'summary': sorted(counts.items()),
            'skipped': skipped,
            'total': sum(counts.values()),
        })
        return render(request, 'admin/restore_backup.html', context)

    return render(request, 'admin/restore_backup.html', context)


def apply():
    original_get_urls = admin.site.get_urls

    def get_urls():
        custom = [
            path('backup/<slug:slug>/', admin.site.admin_view(backup_group_view), name='group_backup'),
            path('backup/<slug:slug>/restore/', admin.site.admin_view(restore_group_view), name='group_restore'),
        ]
        return custom + original_get_urls()

    admin.site.get_urls = get_urls
