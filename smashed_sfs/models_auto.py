# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Attendance(models.Model):
    attendance_id = models.AutoField(primary_key=True)
    lrn = models.ForeignKey('Student', models.DO_NOTHING, db_column='lrn')
    term = models.IntegerField()
    days_present = models.IntegerField(blank=True, null=True)
    days_absent = models.IntegerField(blank=True, null=True)
    uploaded_by = models.ForeignKey('TeacherAdviser', models.DO_NOTHING, db_column='uploaded_by')
    uploaded_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'attendance'
        unique_together = (('lrn', 'term'),)


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.IntegerField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.IntegerField()
    is_active = models.IntegerField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.PositiveSmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class Grades(models.Model):
    grade_id = models.AutoField(primary_key=True)
    lrn = models.ForeignKey('Student', models.DO_NOTHING, db_column='lrn')
    mapping = models.ForeignKey('SubjectMapping', models.DO_NOTHING)
    term = models.IntegerField()
    grade = models.IntegerField()
    comment = models.TextField(blank=True, null=True)
    uploaded_by = models.ForeignKey('TeacherAdviser', models.DO_NOTHING, db_column='uploaded_by')
    uploaded_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'grades'
        unique_together = (('lrn', 'mapping', 'term'),)


class SchoolProfile(models.Model):
    profile_id = models.AutoField(primary_key=True)
    school_year = models.CharField(max_length=20)
    region = models.CharField(max_length=100)
    division = models.CharField(max_length=200)
    district = models.CharField(max_length=100)
    municipality = models.CharField(max_length=100)
    school_name = models.CharField(max_length=200)
    school_id = models.CharField(max_length=20)
    registrar_name = models.CharField(max_length=100)
    registrar_designation = models.CharField(max_length=100)
    guidance_counselor = models.CharField(max_length=100)
    principal_name = models.CharField(max_length=100)
    principal_designation = models.CharField(max_length=100)
    sds_name = models.CharField(max_length=100)
    created_by = models.ForeignKey('TeacherAdviser', models.DO_NOTHING, db_column='created_by', blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    is_active = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'school_profile'


class Section(models.Model):
    section_id = models.AutoField(primary_key=True)
    grade_level = models.CharField(max_length=10)
    track = models.CharField(max_length=50)
    strand = models.CharField(max_length=50)
    section_name = models.CharField(max_length=50)
    modality = models.CharField(max_length=50)
    adviser = models.ForeignKey('TeacherAdviser', models.DO_NOTHING)
    school_profile = models.ForeignKey(SchoolProfile, models.DO_NOTHING)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'section'


class Student(models.Model):
    lrn = models.CharField(primary_key=True, max_length=12)
    surname = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    extension = models.CharField(max_length=10, blank=True, null=True)
    sex = models.CharField(max_length=1)
    birthday = models.DateField()
    school_g10 = models.CharField(max_length=200)
    school_address_g10 = models.CharField(max_length=300)
    average_g10 = models.DecimalField(max_digits=5, decimal_places=2)
    completion_date_g10 = models.DateField()
    shs_admission_date = models.DateField()
    section = models.ForeignKey(Section, models.DO_NOTHING)
    adviser = models.ForeignKey('TeacherAdviser', models.DO_NOTHING)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    is_active = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'student'


class SubjectMapping(models.Model):
    mapping_id = models.AutoField(primary_key=True)
    school_profile = models.ForeignKey(SchoolProfile, models.DO_NOTHING)
    grade_level = models.CharField(max_length=10)
    strand = models.CharField(max_length=50)
    subject_number = models.IntegerField()
    subject_name = models.CharField(max_length=100)
    created_by = models.ForeignKey('TeacherAdviser', models.DO_NOTHING, db_column='created_by')
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    is_active = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'subject_mapping'
        unique_together = (('school_profile', 'grade_level', 'strand', 'subject_number'),)


class TeacherAdviser(models.Model):
    teacher_id = models.AutoField(primary_key=True)
    username = models.CharField(unique=True, max_length=50)
    password = models.CharField(max_length=255)
    full_name = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    email = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    last_login = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'teacher_adviser'
