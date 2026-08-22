from django.db import models


class TeacherAIConnection(models.Model):
    """A teacher's own bring-your-own-key connection to an AI provider,
    used by the Lesson Planning tool. The API key is the only thing this
    app persists - uploaded reference files and generated lesson plans are
    never written to the database (see lesson_planning/views.py); this row
    exists purely so a teacher doesn't have to re-paste their key every
    visit. `consented_at` doubles as the DO 003, s. 2026 transparency
    consent record: agreeing to connect and providing a key are the same
    action in this tool's UI."""

    PROVIDER_DEEPSEEK = 'deepseek'
    PROVIDER_OPENROUTER = 'openrouter'
    PROVIDER_CHOICES = [
        (PROVIDER_DEEPSEEK, 'DeepSeek'),
        (PROVIDER_OPENROUTER, 'OpenRouter (free)'),
    ]

    teacher_id = models.IntegerField(unique=True)
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES, default=PROVIDER_DEEPSEEK)
    encrypted_api_key = models.TextField()
    consented_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'lesson_planning_teacher_ai_connection'
