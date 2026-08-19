from django import forms

from students.models import SchoolProfile, Section


class SchoolProfileSelectForm(forms.Form):
    """Lets a teacher pick an existing school, or flag that they want to add a new one."""

    NEW_SCHOOL_VALUE = 'new'

    school_profile = forms.ChoiceField(label='School')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profiles = list(SchoolProfile.objects.filter(is_active=True).order_by('school_name'))
        choices = [(str(p.profile_id), p.school_name) for p in profiles]
        choices.append((self.NEW_SCHOOL_VALUE, '+ Add a new school'))
        self.fields['school_profile'].choices = choices
        if len(profiles) == 1:
            self.fields['school_profile'].initial = str(profiles[0].profile_id)

    def is_new_school(self):
        return self.cleaned_data.get('school_profile') == self.NEW_SCHOOL_VALUE


class SchoolProfileForm(forms.ModelForm):
    class Meta:
        model = SchoolProfile
        fields = [
            'school_name', 'school_id', 'school_year',
            'region', 'division', 'district', 'municipality',
            'registrar_name', 'registrar_designation', 'guidance_counselor',
            'principal_name', 'principal_designation', 'sds_name',
        ]


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
