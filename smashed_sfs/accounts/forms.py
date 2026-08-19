from django import forms

from students.models import SchoolProfile, Section
from .models import SchoolMasterlistEntry


class SchoolProfileForm(forms.ModelForm):
    class Meta:
        model = SchoolProfile
        fields = [
            'school_name', 'school_id', 'school_year',
            'region', 'division', 'district', 'municipality',
            'registrar_name', 'registrar_designation', 'guidance_counselor',
            'principal_name', 'principal_designation', 'sds_name',
        ]


class NewSchoolProfileForm(forms.ModelForm):
    """Used only when adding a brand-new school on the Complete Your Profile
    page (accounts/views.py complete_profile's "New school details" section)
    - not by SchoolProfileForm's other use (editing an already-created
    school via school/views.py edit_school_profile), so this cascading
    picker only appears where a school doesn't exist in the system yet.

    Fields go in DepEd's geographic order - Region, Division, City/
    Municipality, District, School, School ID - each one filtered by the
    ones before it via AJAX against SchoolMasterlistEntry (DepEd's SY
    2020-2021 masterlist; see the masterlist_* views and the JS in
    complete_profile.html). Region/Municipality are select-only from that
    masterlist (a fixed, essentially-complete geographic breakdown);
    Division/District/School (and its School ID) each also accept typing a
    new value, since a school can be missing from a several-years-old list.
    """

    # division_choice/municipality/district_choice/school_choice are plain
    # CharFields (not ChoiceField) rendered with a Select widget: their
    # <option>s are populated client-side via AJAX as each level cascades
    # from the one before it, so Django can't know the valid choice list
    # up front the way it can for `region` - a ChoiceField would reject any
    # submitted value as "not a valid choice".
    region = forms.ChoiceField(label='Region')
    division_choice = forms.CharField(
        label='Division', required=False, widget=forms.Select(choices=[('', '-- Select --')]))
    division_new = forms.CharField(label='Or enter a new division', required=False, max_length=100)
    municipality = forms.CharField(
        label='City/Municipality', required=False, widget=forms.Select(choices=[('', '-- Select --')]))
    district_choice = forms.CharField(
        label='District', required=False, widget=forms.Select(choices=[('', '-- Select --')]))
    district_new = forms.CharField(label='Or enter a new district', required=False, max_length=150)
    # Labeled "School Name" rather than plain "School" - the top-level
    # school_select_form above (pick an existing profile, or "+ Add a new
    # school") already has a field literally called "School", and having
    # two fields both labeled "School" on the same page reads as a
    # duplicate/mistake.
    school_choice = forms.CharField(
        label='School Name', required=False, widget=forms.Select(choices=[('', '-- Select --')]))
    school_new = forms.CharField(label='Or enter a new school name', required=False, max_length=200)

    class Meta:
        model = SchoolProfile
        fields = [
            'school_id', 'school_year',
            'registrar_name', 'registrar_designation', 'guidance_counselor',
            'principal_name', 'principal_designation', 'sds_name',
        ]
        labels = {'school_id': 'School ID'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        regions = SchoolMasterlistEntry.objects.order_by('region').values_list('region', flat=True).distinct()
        self.fields['region'].choices = [('', '-- Select --')] + [(r, r) for r in regions]

    def clean(self):
        cleaned = super().clean()
        region = cleaned.get('region') or ''
        municipality = (cleaned.get('municipality') or '').strip()
        division = (cleaned.get('division_new') or '').strip() or (cleaned.get('division_choice') or '').strip()
        district = (cleaned.get('district_new') or '').strip() or (cleaned.get('district_choice') or '').strip()
        school_name = (cleaned.get('school_new') or '').strip() or (cleaned.get('school_choice') or '').strip()

        if not region:
            self.add_error('region', 'Select a region.')
        if not municipality:
            self.add_error('municipality', 'Select a city/municipality.')
        if not division:
            self.add_error('division_new', 'Select an existing division or enter a new one.')
        if not school_name:
            self.add_error('school_new', 'Select an existing school or enter a new one.')

        cleaned['region'] = region
        cleaned['division'] = division
        cleaned['municipality'] = municipality
        cleaned['district'] = district
        cleaned['school_name'] = school_name
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=False)
        for field_name in ('region', 'division', 'municipality', 'district', 'school_name'):
            setattr(profile, field_name, self.cleaned_data[field_name])
        if commit:
            profile.save()
        return profile


class SchoolOfficialsForm(forms.ModelForm):
    """Subset of SchoolProfileForm's fields - lets a Class Adviser fill in
    the principal/registrar/guidance counselor names, and correct the
    division/school (e.g. after a transfer to a different station), from
    their own section edit page - without granting them access to the rest
    of the school-wide profile (school_id/school_year/region/district/
    municipality etc. stay registrar/principal-only via SchoolProfileForm).
    Note: division/school_name live on the shared SchoolProfile row, so an
    edit here changes it for every teacher/student still linked to that
    same school, not just the adviser editing it.

    division/school_name reuse the same choice-or-free-text pattern as
    SectionForm's grade_level/track/strand/modality: existing values across
    every SchoolProfile become dropdown options (so picking a division
    filters the school dropdown down to schools already on file in it,
    via JS in the template - self.schools_by_division carries that mapping),
    but typing a new value is always allowed for a school that isn't listed
    yet."""

    division_choice = forms.ChoiceField(label='Division', required=False)
    division_new = forms.CharField(label='Or enter a new division', required=False, max_length=200)
    school_name_choice = forms.ChoiceField(label='School', required=False)
    school_name_new = forms.CharField(label='Or enter a new school name', required=False, max_length=200)

    class Meta:
        model = SchoolProfile
        fields = ['principal_name', 'registrar_name', 'guidance_counselor']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profiles = list(
            SchoolProfile.objects.exclude(division='').order_by('division', 'school_name')
        )
        divisions = sorted(set(p.division for p in profiles))
        self.fields['division_choice'].choices = [('', '-- Select --')] + [(d, d) for d in divisions]

        school_names = sorted(set(p.school_name for p in profiles if p.school_name))
        self.fields['school_name_choice'].choices = [('', '-- Select --')] + [(s, s) for s in school_names]

        self.schools_by_division = {}
        for p in profiles:
            self.schools_by_division.setdefault(p.division, []).append(p.school_name)

        if self.instance and self.instance.pk:
            if self.instance.division:
                self.fields['division_choice'].initial = self.instance.division
            if self.instance.school_name:
                self.fields['school_name_choice'].initial = self.instance.school_name

    def clean(self):
        cleaned = super().clean()
        division = (cleaned.get('division_new') or '').strip() or cleaned.get('division_choice') or ''
        school_name = (cleaned.get('school_name_new') or '').strip() or cleaned.get('school_name_choice') or ''
        if not division:
            self.add_error('division_new', 'Select an existing division or enter a new one.')
        if not school_name:
            self.add_error('school_name_new', 'Select an existing school or enter a new one.')
        cleaned['division'] = division
        cleaned['school_name'] = school_name
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.division = self.cleaned_data['division']
        profile.school_name = self.cleaned_data['school_name']
        if commit:
            profile.save()
        return profile


class SectionForm(forms.ModelForm):
    """
    A Section always belongs to exactly one adviser, so this always creates a new
    row for the current teacher rather than letting them attach to someone else's.

    grade_level/track/strand/modality reuse whatever values already exist elsewhere
    in the system as selectable defaults (so with one school/strand in use today,
    that's the only option shown) but each also accepts free text, so a brand new
    grade level, track, strand, or modality doesn't require a code change.

    Only grade_level is required - track, strand, and modality can be left
    blank (e.g. a Junior High section has no track/strand).
    """

    DYNAMIC_FIELDS = ('grade_level', 'track', 'strand', 'modality')
    REQUIRED_FIELDS = ('grade_level',)

    grade_level_choice = forms.ChoiceField(label='Grade Level', required=False)
    grade_level_new = forms.CharField(label='Or enter a new grade level', required=False, max_length=10)
    track_choice = forms.ChoiceField(label='Track', required=False)
    track_new = forms.CharField(label='Or enter a new track', required=False, max_length=50)
    strand_choice = forms.ChoiceField(label='Strand', required=False)
    strand_new = forms.CharField(label='Or enter a new strand', required=False, max_length=50)
    modality_choice = forms.ChoiceField(label='Modality', required=False)
    modality_new = forms.CharField(label='Or enter a new modality', required=False, max_length=50)

    class Meta:
        model = Section
        fields = ['section_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.DYNAMIC_FIELDS:
            existing = list(
                Section.objects.exclude(**{field_name: ''})
                .order_by(field_name)
                .values_list(field_name, flat=True)
                .distinct()
            )
            choice_field = self.fields[f'{field_name}_choice']
            choice_field.choices = [('', '-- Select --')] + [(v, v) for v in existing]
            if len(existing) == 1:
                choice_field.initial = existing[0]
            # Editing an existing section: default each dropdown to its
            # current value rather than whatever the single-option shortcut
            # above picked (or blank).
            if self.instance and self.instance.pk:
                current = getattr(self.instance, field_name, '')
                if current:
                    choice_field.initial = current

    def clean(self):
        cleaned = super().clean()
        for field_name in self.DYNAMIC_FIELDS:
            chosen = cleaned.get(f'{field_name}_choice')
            typed = (cleaned.get(f'{field_name}_new') or '').strip()
            value = typed or chosen
            if not value and field_name in self.REQUIRED_FIELDS:
                self.add_error(f'{field_name}_new', 'Select an existing value or enter a new one.')
            cleaned[field_name] = value or ''
        return cleaned

    def save(self, commit=True):
        section = super().save(commit=False)
        for field_name in self.DYNAMIC_FIELDS:
            setattr(section, field_name, self.cleaned_data[field_name])
        if commit:
            section.save()
        return section
