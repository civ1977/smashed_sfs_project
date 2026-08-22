import base64
import json

from cryptography.fernet import InvalidToken
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from accounts.models import Teacher
from lesson_planning import ai_client, file_extract
from lesson_planning.crypto import decrypt_api_key
from lesson_planning.models import TeacherAIConnection
from . import prompts
from .docx_builder import build_assessment_docx

MAX_ITEMS_PER_TYPE = 75
# Roughly scaled to how much output a full 3x75-item request could need -
# generate_lesson_plan's default (4096) is sized for a handful of days,
# not up to 225 items; see ai_client.generate_json's own note on a
# response getting cut off mid-JSON at a high item count.
TOKENS_PER_ITEM = 220
MIN_MAX_TOKENS = 4096
MAX_MAX_TOKENS = 16000


def _get_teacher(request):
    return Teacher.objects.filter(username=request.user.username).first()


def _get_connection(teacher):
    return TeacherAIConnection.objects.filter(teacher_id=teacher.teacher_id).first()


@login_required
def assessment_home(request):
    teacher = _get_teacher(request)
    if not teacher:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    connection = _get_connection(teacher)
    return render(request, 'assessment/home.html', {
        'connection': connection,
        'max_items': MAX_ITEMS_PER_TYPE,
    })


@login_required
def generate_assessment(request):
    if request.method != 'POST':
        return redirect('assessment_home')

    teacher = _get_teacher(request)
    if not teacher:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    connection = _get_connection(teacher)
    if not connection:
        messages.error(request, 'Connect your AI provider first.')
        return redirect('assessment_home')

    learning_area = request.POST.get('learning_area', '').strip()
    grade_section = request.POST.get('grade_section', '').strip()
    added_instructions = request.POST.get('added_instructions', '').strip()
    uploaded_file = request.FILES.get('reference_file')

    context = {
        'connection': connection,
        'max_items': MAX_ITEMS_PER_TYPE,
        'form_values': request.POST,
    }

    try:
        mc_count = int(request.POST.get('mc_count', 0))
        tf_plain_count = int(request.POST.get('tf_plain_count', 0))
        tf_modified_count = int(request.POST.get('tf_modified_count', 0))
    except ValueError:
        messages.error(request, 'Item counts must be whole numbers.')
        return render(request, 'assessment/home.html', context)

    counts = (mc_count, tf_plain_count, tf_modified_count)
    # No topic field - a reference file or added instructions is required
    # instead, so the AI always has something concrete to ground the
    # assessment in rather than generating from nothing.
    if not uploaded_file and not added_instructions:
        messages.error(request, 'Upload a reference file or enter added instructions describing what to assess.')
        return render(request, 'assessment/home.html', context)
    if any(c < 0 or c > MAX_ITEMS_PER_TYPE for c in counts):
        messages.error(request, f'Each item count must be between 0 and {MAX_ITEMS_PER_TYPE}.')
        return render(request, 'assessment/home.html', context)
    if sum(counts) == 0:
        messages.error(request, 'Enter at least one item across the three question types.')
        return render(request, 'assessment/home.html', context)

    reference_text = ''
    if uploaded_file:
        try:
            reference_text = file_extract.extract_text(uploaded_file)
        except file_extract.UnsupportedFileError as exc:
            messages.error(request, str(exc))
            return render(request, 'assessment/home.html', context)

    try:
        api_key = decrypt_api_key(connection.encrypted_api_key)
    except InvalidToken:
        messages.error(request, 'Your saved connection is no longer valid. Please reconnect your API key.')
        return render(request, 'assessment/home.html', context)

    user_prompt = prompts.build_user_prompt(
        mc_count=mc_count,
        tf_plain_count=tf_plain_count,
        tf_modified_count=tf_modified_count,
        added_instructions=added_instructions,
        reference_text=reference_text,
    )
    max_tokens = min(MAX_MAX_TOKENS, max(MIN_MAX_TOKENS, sum(counts) * TOKENS_PER_ITEM))

    try:
        assessment = ai_client.generate_json(
            connection.provider, api_key, prompts.ASSESSMENT_SYSTEM_PROMPT, user_prompt, max_tokens=max_tokens,
        )
    except (ai_client.AIProviderError, ai_client.UnsupportedProviderError) as exc:
        messages.error(request, str(exc))
        return render(request, 'assessment/home.html', context)

    header_fields = {
        'teacher_name': teacher.full_name or teacher.username,
        'learning_area': learning_area,
        'grade_section': grade_section,
    }

    download_payload = base64.b64encode(json.dumps({
        'assessment': assessment,
        'header_fields': header_fields,
    }).encode()).decode()

    return render(request, 'assessment/result.html', {
        'assessment': assessment,
        'header_fields': header_fields,
        'download_payload': download_payload,
    })


@login_required
def download_assessment(request):
    if request.method != 'POST':
        return redirect('assessment_home')

    payload = request.POST.get('payload', '')
    try:
        data = json.loads(base64.b64decode(payload))
    except (ValueError, TypeError):
        messages.error(request, 'That generated assessment has expired. Please generate it again.')
        return redirect('assessment_home')

    docx_bytes = build_assessment_docx(
        assessment=data['assessment'],
        teacher_name=data['header_fields']['teacher_name'],
        learning_area=data['header_fields']['learning_area'],
        grade_section=data['header_fields']['grade_section'],
    )

    response = HttpResponse(
        docx_bytes,
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    filename = (data['assessment'].get('assessment_title') or 'Assessment').replace(' ', '_').replace(':', '')
    response['Content-Disposition'] = f'attachment; filename="{filename}.docx"'
    return response
