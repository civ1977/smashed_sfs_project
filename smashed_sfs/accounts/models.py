from django.db import models
from django.contrib.auth.models import User

class Teacher(models.Model):
    ROLE_ADVISER = 'adviser'
    ROLE_REGISTRAR = 'registrar'
    ROLE_PRINCIPAL = 'principal'
    ROLE_NON_TEACHING = 'non_teaching'
    ROLE_SUBJECT_TEACHER = 'subject_teacher'
    ROLE_CHOICES = [
        (ROLE_ADVISER, 'Class Adviser'),
        (ROLE_REGISTRAR, 'Registrar'),
        (ROLE_PRINCIPAL, 'Principal'),
        (ROLE_NON_TEACHING, 'Non-Teaching'),
        (ROLE_SUBJECT_TEACHER, 'Subject Teacher'),
    ]

    teacher_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255)
    full_name = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    email = models.CharField(max_length=100, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ADVISER)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(blank=True, null=True)
    last_seen = models.DateTimeField(blank=True, null=True)
    school_profile_id = models.IntegerField(blank=True, null=True)
    # Set once, at registration, when the required "I agree to the User's
    # Agreement and Privacy Policy" checkbox is submitted (accounts/views.py
    # register()). Null for accounts created before this field existed -
    # there's no forced re-consent flow for those.
    terms_accepted_at = models.DateTimeField(blank=True, null=True)
    # An on-screen-drawn signature (data: URL, PNG) captured once from the
    # DTR page (accounts/views.py's save_dtr_signature) and reused on every
    # month's card from then on - one signature per teacher, not per DTR
    # record, since a real signature doesn't change month to month either.
    signature_image = models.TextField(blank=True, null=True)
    # Only meaningful when role == ROLE_NON_TEACHING: an Officer gets the
    # same full school-admin access as Registrar/Principal (see
    # school/views.py's _get_school_admin_teacher); a Non-Officer only gets
    # Tools (their own DTR). Ignored for every other role.
    is_officer = models.BooleanField(default=False)
    # Null until the registrant clicks their confirmation email link
    # (accounts/views.py verify_email) - deliberately separate from
    # is_active above, which is this app's own admin-controlled "standing"
    # toggle (see school/views.py toggle_teacher_status): an unverified
    # account should still show as Active to a registrar, it just can't
    # log in yet (blocked via the linked auth.User's own is_active, set
    # False at registration and flipped True on verification) - it isn't
    # something a registrar deactivated.
    email_verified_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'teacher_adviser'

    def __str__(self):
        return self.full_name


class SiteVisit(models.Model):
    """One row per (IP address, calendar date) - get_or_create'd by
    smashed_sfs.middleware.TrackSiteVisitMiddleware on every request that
    isn't served directly by whitenoise, so a visitor's repeat requests
    within the same day never create more than one row. Powers the
    day/week/month/lifetime unique-visitor counters on the Online Users
    admin page (smashed_sfs/admin_monitoring.py)."""
    visit_id = models.AutoField(primary_key=True)
    ip_address = models.GenericIPAddressField()
    visited_date = models.DateField()

    class Meta:
        db_table = 'site_visit'
        unique_together = ('ip_address', 'visited_date')

    def __str__(self):
        return f'{self.ip_address} ({self.visited_date})'


class TeacherTimeRecord(models.Model):
    """One day's worth of Daily Time Record (Civil Service Form No. 48)
    entries for a named employee - either typed in by hand or imported
    from a biometric/DTR app's CSV or Excel export via
    accounts.views.upload_dtr.

    teacher_id is the logged-in account preparing/editing this DTR (for
    access scoping), NOT necessarily who it's for - a registrar routinely
    prepares DTRs for other staff, so employee_name is the actual subject
    of the record and is searchable/editable independently of the account
    that owns the edit. Defaults to that account's own Teacher.full_name
    the first time a DTR is opened, but can be changed to anyone."""

    # The official CSC Form No. 6 (Application for Leave) categories - the
    # stored value IS the short code shown on the printed card (accounts/
    # views.py's build_dtr_days reuses the same label/am_label/pm_label
    # mechanism already built for Holiday/Class Suspension rows, just
    # sourced from this field instead of a school-wide calendar exception),
    # so no separate code-lookup table is needed.
    LEAVE_CHOICES = [
        ('VL', 'Vacation Leave'),
        ('FL', 'Mandatory/Forced Leave'),
        ('SL', 'Sick Leave'),
        ('ML', 'Maternity Leave'),
        ('PL', 'Paternity Leave'),
        ('SPL', 'Special Privilege Leave'),
        ('SOLO', 'Solo Parent Leave'),
        ('STL', 'Study Leave'),
        ('VAWC', '10-Day VAWC Leave'),
        ('REHAB', 'Rehabilitation Privilege'),
        ('SLBW', 'Special Leave Benefits for Women'),
        ('CL', 'Special Emergency (Calamity) Leave'),
        ('AL', 'Adoption Leave'),
        ('OTHER', 'Other'),
    ]
    LEAVE_SESSION_WHOLE_DAY = 'whole_day'
    LEAVE_SESSION_AM = 'am'
    LEAVE_SESSION_PM = 'pm'
    LEAVE_SESSION_CHOICES = [
        (LEAVE_SESSION_WHOLE_DAY, 'Whole Day'),
        (LEAVE_SESSION_AM, 'Morning Only'),
        (LEAVE_SESSION_PM, 'Afternoon Only'),
    ]

    record_id = models.AutoField(primary_key=True)
    teacher_id = models.IntegerField()
    employee_name = models.CharField(max_length=100, default='')
    date = models.DateField()
    am_arrival = models.CharField(max_length=16, blank=True, null=True)
    am_departure = models.CharField(max_length=16, blank=True, null=True)
    pm_arrival = models.CharField(max_length=16, blank=True, null=True)
    pm_departure = models.CharField(max_length=16, blank=True, null=True)
    undertime_hours = models.CharField(max_length=16, blank=True, null=True)
    undertime_minutes = models.CharField(max_length=16, blank=True, null=True)
    leave_type = models.CharField(max_length=10, choices=LEAVE_CHOICES, blank=True, null=True)
    leave_session = models.CharField(
        max_length=10, choices=LEAVE_SESSION_CHOICES, default=LEAVE_SESSION_WHOLE_DAY, blank=True,
    )

    class Meta:
        db_table = 'teacher_time_record'
        unique_together = ('teacher_id', 'employee_name', 'date')


class DTRCalendarException(models.Model):
    """A date marked Holiday or Class Suspension on the Daily Time Record
    calendar only - deliberately separate from grades.SchoolCalendarException
    (which SF2/attendance and the report cards also read), so a registrar
    marking a day here never changes attendance-taking or SF2 elsewhere.
    Every weekday defaults to a school day unless a row here says otherwise;
    weekends already default to non-school days regardless."""

    REASON_HOLIDAY = 'holiday'
    REASON_SUSPENSION = 'suspension'
    REASON_CHOICES = [
        (REASON_HOLIDAY, 'Holiday'),
        (REASON_SUSPENSION, 'Class Suspension'),
    ]

    # Only meaningful for REASON_SUSPENSION - a Holiday is always a whole
    # day. A suspension is often announced for just one session (e.g.
    # "morning classes suspended, afternoon classes push through"), so the
    # DTR needs to keep the other session's time fields real/editable
    # rather than blanking the whole row.
    SESSION_WHOLE_DAY = 'whole_day'
    SESSION_AM = 'am'
    SESSION_PM = 'pm'
    SESSION_CHOICES = [
        (SESSION_WHOLE_DAY, 'Whole Day'),
        (SESSION_AM, 'Morning Only'),
        (SESSION_PM, 'Afternoon Only'),
    ]

    exception_id = models.AutoField(primary_key=True)
    school_profile_id = models.IntegerField()
    date = models.DateField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default=REASON_HOLIDAY)
    session = models.CharField(max_length=20, choices=SESSION_CHOICES, default=SESSION_WHOLE_DAY)
    created_by = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dtr_calendar_exception'
        unique_together = ('school_profile_id', 'date')

    def __str__(self):
        return f'{self.school_profile_id} {self.date} {self.get_reason_display()}'


class SchoolMasterlistEntry(models.Model):
    """Reference data only - DepEd's SY 2020-2021 Masterlist of Schools,
    imported once via manage.py load_school_masterlist. Powers the cascading
    Region -> Division -> City/Municipality -> District -> School picker on
    the Complete Your Profile page (accounts/views.py complete_profile) when
    adding a brand-new school - not a live/editable part of the app's own
    school data (that's students.models.SchoolProfile), so nothing here is
    ever created/edited through the app's UI."""

    entry_id = models.AutoField(primary_key=True)
    region = models.CharField(max_length=100)
    division = models.CharField(max_length=100)
    municipality = models.CharField(max_length=100)
    district = models.CharField(max_length=150)
    school_id = models.CharField(max_length=20)
    school_name = models.CharField(max_length=200)

    class Meta:
        db_table = 'school_masterlist_entry'
        indexes = [
            models.Index(fields=['region']),
            models.Index(fields=['region', 'division']),
            models.Index(fields=['region', 'division', 'municipality']),
            models.Index(fields=['region', 'division', 'municipality', 'district']),
        ]

    def __str__(self):
        return f'{self.school_name} ({self.school_id})'