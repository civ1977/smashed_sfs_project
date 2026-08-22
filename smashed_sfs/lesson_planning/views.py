import base64
import json

from cryptography.fernet import InvalidToken
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import Teacher
from . import ai_client, file_extract, prompts
from .crypto import decrypt_api_key, encrypt_api_key
from .docx_builder import build_ai_declaration, build_lesson_plan_docx
from .models import TeacherAIConnection

MAX_DAYS = 5

# The AI connection (BYOK key) is one-per-teacher, not one-per-tool - the
# Assessment tool (assessment/views.py) reuses connect_ai/disconnect_ai
# below rather than duplicating its own connect form, so a teacher who
# already connected for one tool doesn't reconnect for the other. This is
# the whitelist of pages allowed to be the "come back here after
# connecting" target - deliberately not an open redirect to any URL the
# POST body names.
CONNECT_REDIRECT_TARGETS = {'lesson_planning_home', 'assessment_home'}


def _get_teacher(request):
    return Teacher.objects.filter(username=request.user.username).first()


def _get_connection(teacher):
    return TeacherAIConnection.objects.filter(teacher_id=teacher.teacher_id).first()


def _connect_redirect(request):
    target = request.POST.get('next')
    if target not in CONNECT_REDIRECT_TARGETS:
        target = 'lesson_planning_home'
    return redirect(target)


@login_required
def lesson_planning_home(request):
    teacher = _get_teacher(request)
    if not teacher:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    connection = _get_connection(teacher)
    return render(request, 'lesson_planning/home.html', {
        'connection': connection,
        'max_days': range(1, MAX_DAYS + 1),
    })


@login_required
def connect_ai(request):
    if request.method != 'POST':
        return redirect('lesson_planning_home')

    teacher = _get_teacher(request)
    if not teacher:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    api_key = request.POST.get('api_key', '').strip()
    agreed = request.POST.get('agree') == 'on'
    provider = request.POST.get('provider', '').strip()

    if provider not in dict(TeacherAIConnection.PROVIDER_CHOICES):
        messages.error(request, 'Choose a valid AI provider.')
        return _connect_redirect(request)
    if not agreed:
        messages.error(request, 'You must agree to the disclosure statement to connect an AI provider.')
        return _connect_redirect(request)
    if not api_key:
        messages.error(request, 'Enter your API key.')
        return _connect_redirect(request)

    try:
        ai_client.validate_api_key(provider, api_key)
    except (ai_client.AIProviderError, ai_client.UnsupportedProviderError) as exc:
        messages.error(request, str(exc))
        return _connect_redirect(request)

    TeacherAIConnection.objects.update_or_create(
        teacher_id=teacher.teacher_id,
        defaults={
            'provider': provider,
            'encrypted_api_key': encrypt_api_key(api_key),
            'consented_at': timezone.now(),
        },
    )
    messages.success(request, f'Connected to {dict(TeacherAIConnection.PROVIDER_CHOICES)[provider]}.')
    return _connect_redirect(request)


@login_required
def disconnect_ai(request):
    if request.method != 'POST':
        return redirect('lesson_planning_home')

    teacher = _get_teacher(request)
    if teacher:
        TeacherAIConnection.objects.filter(teacher_id=teacher.teacher_id).delete()
        messages.info(request, 'Disconnected. Your API key has been deleted.')
    return _connect_redirect(request)


@login_required
def generate_lesson_plan(request):
    if request.method != 'POST':
        return redirect('lesson_planning_home')

    teacher = _get_teacher(request)
    if not teacher:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    connection = _get_connection(teacher)
    if not connection:
        messages.error(request, 'Connect your DeepSeek API key first.')
        return redirect('lesson_planning_home')

    learning_area = request.POST.get('learning_area', '').strip()
    grade_section = request.POST.get('grade_section', '').strip()
    teaching_dates = request.POST.get('teaching_dates', '').strip()
    num_days = int(request.POST.get('num_days', 5))
    competencies = request.POST.get('competencies', '').strip()
    added_instructions = request.POST.get('added_instructions', '').strip()

    context = {
        'connection': connection,
        'max_days': range(1, MAX_DAYS + 1),
        'form_values': request.POST,
    }

    if not (learning_area and grade_section and teaching_dates and competencies):
        messages.error(request, 'Fill in learning area, grade & section, teaching dates, and competencies.')
        return render(request, 'lesson_planning/home.html', context)
    if not 1 <= num_days <= MAX_DAYS:
        messages.error(request, f'Number of days must be between 1 and {MAX_DAYS}.')
        return render(request, 'lesson_planning/home.html', context)

    reference_text = ''
    uploaded_file = request.FILES.get('reference_file')
    if uploaded_file:
        try:
            reference_text = file_extract.extract_text(uploaded_file)
        except file_extract.UnsupportedFileError as exc:
            messages.error(request, str(exc))
            return render(request, 'lesson_planning/home.html', context)

    try:
        api_key = decrypt_api_key(connection.encrypted_api_key)
    except InvalidToken:
        messages.error(request, 'Your saved connection is no longer valid. Please reconnect your API key.')
        return render(request, 'lesson_planning/home.html', context)

    user_prompt = prompts.build_user_prompt(
        learning_area=learning_area,
        grade_section=grade_section,
        teaching_dates=teaching_dates,
        num_days=num_days,
        competencies=competencies,
        added_instructions=added_instructions,
        reference_text=reference_text,
    )

    try:
        plan = ai_client.generate_json(connection.provider, api_key, prompts.ILAW_SYSTEM_PROMPT, user_prompt)
    except (ai_client.AIProviderError, ai_client.UnsupportedProviderError) as exc:
        messages.error(request, str(exc))
        return render(request, 'lesson_planning/home.html', context)

    ai_declaration = build_ai_declaration(
        teacher_name=teacher.full_name or teacher.username,
        provider=connection.get_provider_display(),
        lesson_title=plan.get('lesson_title', ''),
        competencies=competencies,
        added_instructions=added_instructions,
    )
    header_fields = {
        'learning_area': learning_area,
        'teacher_name': teacher.full_name or teacher.username,
        'grade_section': grade_section,
        'teaching_dates': teaching_dates,
        'num_sessions': len(plan.get('days', [])),
        'references': 'AI-drafted from teacher-provided competencies'
                      + (' and uploaded reference material.' if reference_text else '.'),
    }

    download_payload = base64.b64encode(json.dumps({
        'plan': plan,
        'header_fields': header_fields,
        'ai_declaration': ai_declaration,
    }).encode()).decode()

    return render(request, 'lesson_planning/result.html', {
        'plan': plan,
        'header_fields': header_fields,
        'ai_declaration': ai_declaration,
        'download_payload': download_payload,
    })


@login_required
def download_lesson_plan(request):
    if request.method != 'POST':
        return redirect('lesson_planning_home')

    payload = request.POST.get('payload', '')
    try:
        data = json.loads(base64.b64decode(payload))
    except (ValueError, TypeError):
        messages.error(request, 'That generated plan has expired. Please generate it again.')
        return redirect('lesson_planning_home')

    docx_bytes = build_lesson_plan_docx(
        plan=data['plan'],
        header_fields=data['header_fields'],
        ai_declaration=data['ai_declaration'],
    )

    response = HttpResponse(
        docx_bytes,
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    filename = (data['plan'].get('lesson_title') or 'Lesson_Plan').replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename="{filename}.docx"'
    return response
