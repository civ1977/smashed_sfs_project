from django.db import models
from django.contrib.auth.models import User


class StudentAccount(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    account_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    lrn = models.CharField(max_length=12)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    is_active = models.BooleanField(default=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(blank=True, null=True)
    decided_by = models.IntegerField(blank=True, null=True)
    last_seen = models.DateTimeField(blank=True, null=True)
    # See accounts.Teacher.terms_accepted_at - same idea, set at registration
    # (portal/views.py portal_register()).
    terms_accepted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'student_account'

    def __str__(self):
        return f"{self.lrn} ({self.status})"
