from django.db import models


class TeacherAccountAuditLog(models.Model):
    """One row per activate/deactivate action taken on a Teacher account from
    the school-admin Accounts page - who did it, to whom, and when."""

    ACTION_ACTIVATED = 'activated'
    ACTION_DEACTIVATED = 'deactivated'
    ACTION_CHOICES = [
        (ACTION_ACTIVATED, 'Activated'),
        (ACTION_DEACTIVATED, 'Deactivated'),
    ]

    log_id = models.AutoField(primary_key=True)
    target_teacher_id = models.IntegerField()
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.IntegerField()
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'teacher_account_audit_log'
        ordering = ['-performed_at']

    def __str__(self):
        return f"teacher {self.target_teacher_id} {self.action} by {self.performed_by}"


class SectionAuditLog(models.Model):
    """One row per edit/delete action taken on a Section from the
    school-admin Sections page. section_label is a snapshot (e.g.
    "Grade 11-STEM-A") rather than a live section_id lookup, so the log
    stays readable after a section is deleted."""

    ACTION_EDITED = 'edited'
    ACTION_DELETED = 'deleted'
    ACTION_CHOICES = [
        (ACTION_EDITED, 'Edited'),
        (ACTION_DELETED, 'Deleted'),
    ]

    log_id = models.AutoField(primary_key=True)
    school_profile_id = models.IntegerField()
    section_label = models.CharField(max_length=100)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    detail = models.CharField(max_length=255, blank=True, default='')
    performed_by = models.IntegerField()
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'section_audit_log'
        ordering = ['-performed_at']

    def __str__(self):
        return f"{self.section_label} {self.action} by {self.performed_by}"
