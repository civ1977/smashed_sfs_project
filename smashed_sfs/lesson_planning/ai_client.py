import json

import requests

REQUEST_TIMEOUT_SECONDS = 90

# One entry per supported AI provider - validate_api_key/generate_json
# below are written entirely against this config, not against DeepSeek
# specifically, so adding another provider (e.g. OpenAI, which happens to
# share DeepSeek's OpenAI-compatible REST shape) is just a new entry here,
# not a new code path. A provider with a different auth header convention
# (e.g. Anthropic's `x-api-key` instead of `Authorization: Bearer`) still
# fits by giving it its own `auth_headers` function; one that can't honor
# `response_format: json_object` fits by setting `json_response_format`
# to False, which falls back to a plain prompt instruction instead.
PROVIDERS = {
    # Google's own free tier: no card required, and a fixed documented
    # daily quota per model (unlike OpenRouter's free models below, which
    # share a community capacity pool and can be randomly congested or
    # retired - both of which happened during this tool's own testing).
    # Listed first/default for that reason. Google's OpenAI-compatible
    # layer has no /models listing endpoint (confirmed: genuinely 404s),
    # so validation instead sends a real 1-token chat request - the
    # validate_method/validate_body below are what make that possible
    # without a separate code path in validate_api_key.
    'gemini': {
        'label': 'Gemini (free)',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai',
        # gemini-3.7-flash is the model Google's own OpenAI-compatibility
        # doc actually shows in its chat-completions example as of this
        # writing; the 2.5 names are kept as fallbacks in case 3.7 is ever
        # unavailable on a given account/region - both validate_api_key
        # and generate_json below iterate this same list on a 404, so a
        # renamed/retired entry doesn't require a code change here, only
        # reordering or adding to this list.
        'chat_models': ['gemini-3.7-flash', 'gemini-2.5-flash', 'gemini-2.5-flash-lite'],
        'validate_path': '/chat/completions',
        'validate_method': 'POST',
        'validate_body': lambda model: {
            'model': model,
            'messages': [{'role': 'user', 'content': 'hi'}],
            'max_tokens': 1,
        },
        'chat_path': '/chat/completions',
        'auth_headers': lambda api_key: {'Authorization': f'Bearer {api_key}'},
        'json_response_format': True,
    },
    'deepseek': {
        'label': 'DeepSeek',
        'base_url': 'https://api.deepseek.com',
        'chat_models': ['deepseek-chat'],
        'validate_path': '/models',
        'chat_path': '/chat/completions',
        'auth_headers': lambda api_key: {'Authorization': f'Bearer {api_key}'},
        'json_response_format': True,
    },
    # OpenRouter's own key is genuinely free (rate-limited, no card) when
    # pointed at one of its ":free"-suffixed models - but which specific
    # models are free rotates on OpenRouter's side as sponsorship deals
    # change (a single hardcoded model id here already 404'd once), so
    # this is a fallback list tried in order rather than one fixed model;
    # generate_json below moves to the next entry on a 404 specifically.
    # Check current free models at https://openrouter.ai/models?max_price=0
    # if every entry here ends up 404ing.
    'openrouter': {
        'label': 'OpenRouter (free)',
        'base_url': 'https://openrouter.ai/api/v1',
        'chat_models': [
            'z-ai/glm-5.2:free',
            'google/gemma-4-31b-it:free',
            'nvidia/nemotron-3-super-120b-a12b:free',
        ],
        'validate_path': '/auth/key',
        'chat_path': '/chat/completions',
        'auth_headers': lambda api_key: {'Authorization': f'Bearer {api_key}'},
        'json_response_format': True,
    },
}


class UnsupportedProviderError(Exception):
    pass


class AIProviderError(Exception):
    """Raised for anything that should surface as a plain error message to
    the teacher - a bad/expired key, a provider outage, or a malformed
    response - rather than a raw traceback."""


def _provider_config(provider):
    config = PROVIDERS.get(provider)
    if not config:
        raise UnsupportedProviderError(f'"{provider}" is not a supported AI provider.')
    return config


def _error_detail(response):
    """Best-effort extraction of a provider's own error message from its
    response body - useful for a status code this module doesn't special-
    case (e.g. Gemini returns 400, not 401, for a missing/invalid key,
    with a genuinely informative message attached) rather than showing
    just a bare HTTP code for those."""
    try:
        body = response.json()
        if isinstance(body, list) and body:
            body = body[0]
        return body.get('error', {}).get('message', '')
    except (ValueError, AttributeError, KeyError, IndexError):
        return ''


def _raise_for_error_status(config, response, *, on_auth_error):
    """Shared HTTP-status handling for both calls below - a 402 means the
    provider has no balance/payment method on file for this key (DepEd
    teachers hitting this on DeepSeek after their free trial grant runs
    out is the expected case this guards against), which is different
    from - and much more fixable by switching providers than - a bad key
    or an outage, so it gets its own message pointing at OpenRouter."""
    if response.status_code == 401:
        raise AIProviderError(on_auth_error)
    if response.status_code == 402:
        free_alternatives = [
            c['label'] for key, c in PROVIDERS.items() if c is not config and key == 'openrouter'
        ]
        switch_hint = f" or disconnect and connect with {free_alternatives[0]} instead" if free_alternatives else ''
        raise AIProviderError(
            f"{config['label']} says this account has no available balance (HTTP 402) - its free trial grant "
            f"may have run out. Add a payment method on your {config['label']} account{switch_hint}."
        )
    if response.status_code == 429:
        raise AIProviderError(f"{config['label']} rate-limited this request. Wait a moment and try again.")
    if response.status_code == 404:
        raise AIProviderError(
            f"{config['label']} doesn't recognize the model this tool is configured to use - it may have "
            'been renamed or retired on the provider\'s side. Please report this so it can be updated.'
        )
    if not response.ok:
        detail = _error_detail(response)
        suffix = f' ({detail})' if detail else ''
        raise AIProviderError(f"{config['label']} returned an unexpected error (HTTP {response.status_code}){suffix}.")


def validate_api_key(provider, api_key):
    """Confirms a key actually works before saving it - catches a bad/
    expired/mistyped key immediately instead of failing on the teacher's
    first real generation. Most providers expose a free model-listing
    endpoint for this (a GET, no completion cost) and only need trying
    once; one that doesn't (Gemini - see PROVIDERS' comment there) sets
    validate_method to POST and validate_body to a minimal real request
    instead, which - like generate_json - is retried across chat_models
    on a 404/429 rather than only ever trying the first entry, since a
    model name going stale shouldn't require a validate_api_key code
    change on top of a PROVIDERS one."""
    config = _provider_config(provider)
    method = config.get('validate_method', 'GET')
    models = config['chat_models'] if method == 'POST' else [None]

    for index, model in enumerate(models):
        is_last = index == len(models) - 1
        kwargs = {'headers': config['auth_headers'](api_key), 'timeout': 15}
        if method == 'POST':
            kwargs['json'] = config['validate_body'](model)

        try:
            response = requests.request(method, f"{config['base_url']}{config['validate_path']}", **kwargs)
        except requests.RequestException as exc:
            raise AIProviderError(f"Could not reach {config['label']}: {exc}") from exc

        if response.status_code in (404, 429) and not is_last:
            continue

        _raise_for_error_status(
            config, response,
            on_auth_error=f"{config['label']} rejected this API key. Double-check it and try again.",
        )
        return


def generate_json(provider, api_key, system_prompt, user_prompt, max_tokens=4096):
    """Sends a chat completion request constrained to JSON output and
    returns the parsed dict. Tries each of the provider's chat_models in
    order, moving to the next on a 404 (model retired/renamed on the
    provider's side - see PROVIDERS' comment on openrouter) or a 429
    (confirmed against OpenRouter's own free tier: a 429 there typically
    means that one specific free model's shared upstream capacity pool is
    briefly saturated, not that this account is rate-limited - a
    different free model routes to different upstream capacity and
    usually just works). Any other error status stops immediately rather
    than burning through the whole list for a problem no model swap would
    fix (a bad key or no balance). Raises AIProviderError on any failure
    mode a teacher should see as a plain message."""
    config = _provider_config(provider)
    models = config['chat_models']

    for index, model in enumerate(models):
        is_last = index == len(models) - 1
        body = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': 0.4,
            'max_tokens': max_tokens,
        }
        if config['json_response_format']:
            body['response_format'] = {'type': 'json_object'}

        try:
            response = requests.post(
                f"{config['base_url']}{config['chat_path']}",
                headers={**config['auth_headers'](api_key), 'Content-Type': 'application/json'},
                json=body,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise AIProviderError(f"Could not reach {config['label']}: {exc}") from exc

        if response.status_code in (404, 429) and not is_last:
            continue

        _raise_for_error_status(
            config, response,
            on_auth_error=f"{config['label']} rejected the saved API key. Reconnect with a valid key and try again.",
        )

        try:
            content = response.json()['choices'][0]['message']['content']
            return json.loads(content)
        except json.JSONDecodeError as exc:
            # The likeliest real cause at a high max_tokens is the response
            # getting cut off mid-JSON (a large item count asked for more
            # output than the model produced) rather than a wholesale
            # malformed reply, so this hints at the actual fix.
            raise AIProviderError(
                f"{config['label']}'s response was cut off before it finished (often means too many items were "
                'requested at once). Try again with a smaller count.'
            ) from exc
        except (KeyError, IndexError) as exc:
            raise AIProviderError(f"{config['label']} returned a response that could not be understood. Please try again.") from exc

    # Unreachable unless `models` is empty - _raise_for_error_status above
    # always raises or returns before falling out of the loop otherwise.
    raise AIProviderError(f"{config['label']} has no configured model to use.")
