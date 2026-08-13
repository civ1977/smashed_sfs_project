"""Auto-scheduling algorithm: fills empty (section, day, timeslot) cells
with TeacherSubjectAssignment sessions, without ever double-booking a
teacher or a section.

This is a from-scratch Python port of the *idea* behind the user's
GNHS scheduling workbook (priority-sort teachers by remaining load, then
greedily place sessions) - not a copy of its VBA. The two ScheduleEntry
unique_together constraints are the actual conflict guarantee here, so
the algorithm only needs to avoid pairs it already knows are taken; it
never has to "discover" a conflict after the fact the way the VBA's
randomized retry phase did.
"""
import random
from collections import defaultdict

from grades.models import TeacherSubjectAssignment, SubjectMapping
from students.models import Section
from accounts.models import Teacher
from .models import TimeSlot, ScheduleRequirement, ScheduleEntry

DEFAULT_SESSIONS_PER_WEEK = 4
DAYS = [d for d, _ in ScheduleEntry.DAY_CHOICES]


def generate_schedule(school_profile_id):
    """Fill every under-scheduled TeacherSubjectAssignment for this school
    as far as it can without touching existing ScheduleEntry rows.
    Returns {'created': int, 'unresolved': [{'teacher', 'section',
    'subject', 'still_needed'}]}."""

    sections = {s.section_id: s for s in Section.objects.filter(school_profile_id=school_profile_id)}
    if not sections:
        return {'created': 0, 'unresolved': []}

    teachers = {t.teacher_id: t for t in Teacher.objects.filter(school_profile_id=school_profile_id)}
    mappings = {m.mapping_id: m for m in SubjectMapping.objects.filter(school_profile_id=school_profile_id)}

    assignments = list(TeacherSubjectAssignment.objects.filter(section_id__in=sections.keys()))
    if not assignments:
        return {'created': 0, 'unresolved': []}

    slots = list(
        TimeSlot.objects.filter(school_profile_id=school_profile_id, is_break=False)
        .order_by('slot_order')
    )
    if not slots:
        return {'created': 0, 'unresolved': []}
    slot_ids = [s.timeslot_id for s in slots]

    requirements = {
        r.assignment_id: r.sessions_per_week
        for r in ScheduleRequirement.objects.filter(
            assignment_id__in=[a.assignment_id for a in assignments]
        )
    }

    existing = list(ScheduleEntry.objects.filter(school_profile_id=school_profile_id))

    # (teacher_id, day, timeslot_id) / (section_id, day, timeslot_id) -> taken
    teacher_taken = {(e.teacher_id, e.day_of_week, e.timeslot_id) for e in existing}
    section_taken = {(e.section_id, e.day_of_week, e.timeslot_id) for e in existing}
    # assignment_id -> set of days it already occupies (spread sessions across days)
    assignment_days = defaultdict(set)
    # assignment_id -> sessions already placed
    placed_count = defaultdict(int)
    for e in existing:
        assignment_days[e.assignment_id].add(e.day_of_week)
        placed_count[e.assignment_id] += 1

    # Busiest teacher (by total remaining weekly need) gets first pick of open slots.
    teacher_remaining = defaultdict(int)
    for a in assignments:
        needed = requirements.get(a.assignment_id, DEFAULT_SESSIONS_PER_WEEK)
        still_needed = max(0, needed - placed_count[a.assignment_id])
        teacher_remaining[a.teacher_id] += still_needed
    assignments.sort(key=lambda a: teacher_remaining[a.teacher_id], reverse=True)

    to_create = []
    unresolved = []

    for a in assignments:
        needed = requirements.get(a.assignment_id, DEFAULT_SESSIONS_PER_WEEK)
        still_needed = needed - placed_count[a.assignment_id]
        if still_needed <= 0:
            continue

        days_unused = [d for d in DAYS if d not in assignment_days[a.assignment_id]]
        days_used = [d for d in DAYS if d in assignment_days[a.assignment_id]]
        random.shuffle(days_unused)
        candidate_days = days_unused + days_used  # prefer a fresh day per session

        placed_here = 0
        for day in candidate_days:
            if placed_here >= still_needed:
                break
            candidate_slots = list(slot_ids)
            random.shuffle(candidate_slots)
            for timeslot_id in candidate_slots:
                t_key = (a.teacher_id, day, timeslot_id)
                s_key = (a.section_id, day, timeslot_id)
                if t_key in teacher_taken or s_key in section_taken:
                    continue
                teacher_taken.add(t_key)
                section_taken.add(s_key)
                assignment_days[a.assignment_id].add(day)
                to_create.append(ScheduleEntry(
                    school_profile_id=school_profile_id,
                    assignment_id=a.assignment_id,
                    teacher_id=a.teacher_id,
                    section_id=a.section_id,
                    mapping_id=a.mapping_id,
                    day_of_week=day,
                    timeslot_id=timeslot_id,
                ))
                placed_here += 1
                break

        if placed_here < still_needed:
            teacher = teachers.get(a.teacher_id)
            section = sections.get(a.section_id)
            mapping = mappings.get(a.mapping_id)
            unresolved.append({
                'teacher': teacher.full_name if teacher else f'#{a.teacher_id}',
                'section': section.section_name if section else f'#{a.section_id}',
                'subject': mapping.subject_name if mapping else f'#{a.mapping_id}',
                'still_needed': still_needed - placed_here,
            })

    ScheduleEntry.objects.bulk_create(to_create)
    return {'created': len(to_create), 'unresolved': unresolved}


DEFAULT_TIME_SLOTS = [
    (1, '1st', '07:30', '08:30', False),
    (2, '2nd', '08:30', '09:30', False),
    (3, 'Recess', '09:30', '10:00', True),
    (4, '3rd', '10:00', '11:00', False),
    (5, '4th', '11:00', '12:00', False),
    (6, 'Lunch Break', '12:00', '13:00', True),
    (7, '5th', '13:00', '14:00', False),
    (8, '6th', '14:00', '15:00', False),
    (9, '7th', '15:00', '16:00', False),
]


def ensure_time_slots(school_profile_id):
    """Seed the default 7-period bell schedule (+2 break rows) for this
    school the first time the scheduling page is opened. No-op if this
    school already has any TimeSlot rows."""
    if TimeSlot.objects.filter(school_profile_id=school_profile_id).exists():
        return
    TimeSlot.objects.bulk_create([
        TimeSlot(
            school_profile_id=school_profile_id,
            slot_order=order,
            label=label,
            start_time=start,
            end_time=end,
            is_break=is_break,
        )
        for order, label, start, end, is_break in DEFAULT_TIME_SLOTS
    ])
