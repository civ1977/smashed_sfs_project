from datetime import date, timedelta

from django.test import TestCase

from grades.models import Grade, SubjectMapping
from students.models import Student
from .views import (
    _age_from_birthday,
    _build_subject_rows,
    _final_average,
    _gate_finals_pending_term3,
    _remarks_for,
    _split_core_elective,
)


class FinalAverageTests(TestCase):
    def test_all_three_terms_present(self):
        self.assertEqual(_final_average([80, 85, 90]), 85)

    def test_rounds_to_nearest_int(self):
        self.assertEqual(_final_average([80, 81, 81]), round((80 + 81 + 81) / 3))

    def test_missing_terms_are_ignored(self):
        self.assertEqual(_final_average([80, None, None]), 80)

    def test_no_terms_returns_none(self):
        self.assertIsNone(_final_average([None, None, None]))


class RemarksForTests(TestCase):
    def test_none_final_has_no_remark(self):
        self.assertIsNone(_remarks_for(None))

    def test_75_is_passed(self):
        self.assertEqual(_remarks_for(75), 'Passed')

    def test_74_is_failed(self):
        self.assertEqual(_remarks_for(74), 'Failed')


class GateFinalsPendingTerm3Tests(TestCase):
    def test_all_subjects_complete_returns_true(self):
        rows = [
            {'term_3': 90, 'final': 85, 'remarks': 'Passed'},
            {'term_3': 88, 'final': 80, 'remarks': 'Passed'},
        ]
        self.assertTrue(_gate_finals_pending_term3(rows))
        # Untouched when already complete.
        self.assertEqual(rows[0]['final'], 85)

    def test_one_subject_missing_term3_blanks_its_final_and_returns_false(self):
        rows = [
            {'term_3': 90, 'final': 85, 'remarks': 'Passed'},
            {'term_3': None, 'final': 80, 'remarks': 'Passed'},
        ]
        complete = _gate_finals_pending_term3(rows)
        self.assertFalse(complete)
        self.assertIsNone(rows[1]['final'])
        self.assertIsNone(rows[1]['remarks'])
        # A subject that does have Term 3 data is left alone even though
        # the report as a whole isn't complete yet.
        self.assertEqual(rows[0]['final'], 85)


class SplitCoreElectiveTests(TestCase):
    def test_splits_by_is_elective_flag(self):
        rows = [
            {'subject_name': 'Math', 'is_elective': False},
            {'subject_name': 'Research', 'is_elective': True},
        ]
        core, elective = _split_core_elective(rows)
        self.assertEqual([r['subject_name'] for r in core], ['Math'])
        self.assertEqual([r['subject_name'] for r in elective], ['Research'])


class AgeFromBirthdayTests(TestCase):
    def test_none_birthday_returns_none(self):
        self.assertIsNone(_age_from_birthday(None))

    def test_birthday_already_passed_this_year(self):
        today = date.today()
        birthday = today.replace(year=today.year - 20) - timedelta(days=1)
        self.assertEqual(_age_from_birthday(birthday), 20)

    def test_birthday_not_yet_reached_this_year(self):
        today = date.today()
        birthday = today.replace(year=today.year - 20) + timedelta(days=1)
        self.assertEqual(_age_from_birthday(birthday), 19)


class BuildSubjectRowsTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(
            lrn='123456789012', surname='Dela Cruz', name='Juan', sex='MALE',
            school_g10='Test JHS', school_address_g10='Test Address',
            average_g10='90.00', section_id=1, adviser_id=1,
        )
        self.math = SubjectMapping.objects.create(
            school_profile_id=1, grade_level='11', strand='', subject_number=1,
            subject_name='Math', created_by=1, is_elective=False,
        )
        self.research = SubjectMapping.objects.create(
            school_profile_id=1, grade_level='11', strand='', subject_number=2,
            subject_name='Research', created_by=1, is_elective=True,
        )

    def test_groups_by_subject_and_computes_final(self):
        Grade.objects.create(lrn=self.student.lrn, mapping_id=self.math.mapping_id, term=1, grade=80, uploaded_by=1)
        Grade.objects.create(lrn=self.student.lrn, mapping_id=self.math.mapping_id, term=2, grade=84, uploaded_by=1)
        Grade.objects.create(lrn=self.student.lrn, mapping_id=self.math.mapping_id, term=3, grade=88, uploaded_by=1)

        rows = _build_subject_rows(self.student.lrn)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['subject_name'], 'Math')
        self.assertEqual(row['final'], 84)
        self.assertEqual(row['remarks'], 'Passed')

    def test_rows_are_ordered_by_subject_number(self):
        Grade.objects.create(lrn=self.student.lrn, mapping_id=self.research.mapping_id, term=1, grade=80, uploaded_by=1)
        Grade.objects.create(lrn=self.student.lrn, mapping_id=self.math.mapping_id, term=1, grade=90, uploaded_by=1)

        rows = _build_subject_rows(self.student.lrn)

        self.assertEqual([r['subject_name'] for r in rows], ['Math', 'Research'])

    def test_grade_level_filter_excludes_other_levels(self):
        g12_subject = SubjectMapping.objects.create(
            school_profile_id=1, grade_level='12', strand='', subject_number=1,
            subject_name='Practical Research 2', created_by=1,
        )
        Grade.objects.create(lrn=self.student.lrn, mapping_id=self.math.mapping_id, term=1, grade=80, uploaded_by=1)
        Grade.objects.create(lrn=self.student.lrn, mapping_id=g12_subject.mapping_id, term=1, grade=85, uploaded_by=1)

        rows = _build_subject_rows(self.student.lrn, grade_level='11')

        self.assertEqual([r['subject_name'] for r in rows], ['Math'])
