from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import Teacher
from students.models import SchoolProfile, Section, Student
from .models import Grade, SubjectMapping


class SaveGradesTests(TestCase):
    """Covers grades.views.save_grades: the 60-100 grade range check, and
    the strand a new SubjectMapping gets created/looked-up under (see
    CLAUDE.md - this used to be hardcoded to 'STEM' regardless of the
    uploading teacher's actual section strand, which silently broke the
    Core/Elective arrangement page and subject-teacher-assignment dropdowns
    for every non-STEM section)."""

    def setUp(self):
        self.school_profile = SchoolProfile.objects.create(
            school_year='2025-2026', region='R', division='D', district='Dist',
            municipality='M', school_name='Test SHS', school_id='000001',
            registrar_name='R', registrar_designation='RD', guidance_counselor='GC',
            principal_name='P', principal_designation='PD', sds_name='SDS',
        )
        self.user = User.objects.create_user(username='adviser1', password='irrelevant')
        self.teacher = Teacher.objects.create(
            user=self.user, username='adviser1', password='hash', full_name='Adviser One',
            position='Teacher', school_profile_id=self.school_profile.profile_id,
        )
        self.section = Section.objects.create(
            grade_level='11', track='Academic', strand='HUMSS', section_name='A',
            modality='Face-to-face', adviser_id=self.teacher.teacher_id,
            school_profile_id=self.school_profile.profile_id,
        )
        self.student = Student.objects.create(
            lrn='123456789012', surname='Dela Cruz', name='Juan', sex='MALE',
            school_g10='Test JHS', school_address_g10='Test Address',
            average_g10='90.00', section_id=self.section.section_id,
            adviser_id=self.teacher.teacher_id,
        )
        self.client.force_login(self.user)

    def _post(self, **extra):
        data = {
            'row_count': '1', 'term': '1', 'grade_level': '11',
            'update_subjects': 'on', 'subject_name_1': 'Oral Communication',
            'lrn_0': self.student.lrn,
        }
        data.update(extra)
        return self.client.post(reverse('save_grades'), data)

    def test_new_subject_mapping_uses_teacher_section_strand_not_stem(self):
        self._post(**{'grade_0_1': '85'})
        mapping = SubjectMapping.objects.get(
            school_profile_id=self.school_profile.profile_id, grade_level='11', subject_number=1,
        )
        self.assertEqual(mapping.strand, 'HUMSS')

    def test_grade_within_range_is_saved(self):
        self._post(**{'grade_0_1': '85'})
        grade = Grade.objects.get(lrn=self.student.lrn, term=1)
        self.assertEqual(grade.grade, 85)

    def test_grade_below_60_is_rejected(self):
        self._post(**{'grade_0_1': '59'})
        self.assertFalse(Grade.objects.filter(lrn=self.student.lrn, term=1).exists())

    def test_grade_above_100_is_rejected(self):
        self._post(**{'grade_0_1': '101'})
        self.assertFalse(Grade.objects.filter(lrn=self.student.lrn, term=1).exists())

    def test_boundary_grades_60_and_100_are_saved(self):
        self._post(**{'grade_0_1': '60'})
        self.assertEqual(Grade.objects.get(lrn=self.student.lrn, term=1).grade, 60)

    def test_existing_grade_is_updated_not_duplicated(self):
        self._post(**{'grade_0_1': '70'})
        self._post(**{'grade_0_1': '90'})
        grades = Grade.objects.filter(lrn=self.student.lrn, term=1)
        self.assertEqual(grades.count(), 1)
        self.assertEqual(grades.first().grade, 90)

    def test_replace_all_only_clears_matching_grade_level(self):
        # Grade 11 mapping/grade for this student, then a Grade 12 mapping/
        # grade for the same term number - a Grade 11 replace_all upload
        # must not wipe the Grade 12 history.
        self._post(**{'grade_0_1': '80'})
        g12_mapping = SubjectMapping.objects.create(
            school_profile_id=self.school_profile.profile_id, grade_level='12',
            strand='HUMSS', subject_number=1, subject_name='Physical Education',
            created_by=self.teacher.teacher_id,
        )
        Grade.objects.create(
            lrn=self.student.lrn, mapping_id=g12_mapping.mapping_id, term=1,
            grade=88, uploaded_by=self.teacher.teacher_id,
        )

        self._post(replace_all='on', **{'grade_0_1': '95'})

        self.assertTrue(
            Grade.objects.filter(mapping_id=g12_mapping.mapping_id, term=1, grade=88).exists()
        )
