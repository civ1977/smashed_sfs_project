"""Shared roster-shaping helpers used across the grades and reports apps."""


def split_by_sex(students):
    """Splits a roster into (males, females) using this app's sex-value
    convention (some rows store 'MALE'/'FEMALE', others the abbreviated
    'M'/'F') - the single source of truth other helpers and call sites
    that need the two groups separately (e.g. SF2's male/female row
    blocks) build on."""
    males = [s for s in students if s.sex in ('MALE', 'M')]
    females = [s for s in students if s.sex in ('FEMALE', 'F')]
    return males, females


def male_then_female(students):
    """Roster convention used throughout the app: male students first,
    then female, each group keeping whatever order `students` was already
    in (always alphabetical by surname/name via .order_by() beforehand)."""
    males, females = split_by_sex(students)
    return males + females
