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


class SectionForm(forms.ModelForm):
    """
    A Section always belongs to exactly one adviser, so this always creates a new
    row for the current teacher rather than letting them attach to someone else's.

    grade_level/track/strand/modality reuse whatever values already exist elsewhere
    in the system as selectable defaults (so with one school/strand in use today,
    that's the only option shown) but each also accepts free text, so a brand new
    grade level, track, strand, or modality doesn't require a code change.
    """

    DYNAMIC_FIELDS = ('grade_level', 'track', 'strand', 'modality')

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

    def clean(self):
        cleaned = super().clean()
        for field_name in self.DYNAMIC_FIELDS:
            chosen = cleaned.get(f'{field_name}_choice')
            typed = (cleaned.get(f'{field_name}_new') or '').strip()
            value = typed or chosen
            if not value:
                self.add_error(f'{field_name}_new', 'Select an existing value or enter a new one.')
            cleaned[field_name] = value
        return cleaned

    def save(self, commit=True):
        section = super().save(commit=False)
        for field_name in self.DYNAMIC_FIELDS:
            setattr(section, field_name, self.cleaned_data[field_name])
        if commit:
            section.save()
        return section
