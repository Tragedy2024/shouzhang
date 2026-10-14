"""Provider configuration; keys live in the environment or private local settings."""
import json
import os
from pathlib import Path


def _provider_setting(name, default=''):
    configured = os.environ.get(name)
    if configured is not None:
        return configured
    private_settings = Path(__file__).resolve().parent / 'instance' / 'provider-secrets.json'
    if private_settings.exists():
        try:
            return json.loads(private_settings.read_text(encoding='utf-8')).get(name, default)
        except (OSError, ValueError):
            return default
    return default

VISION_CONFIG = {'api_key': _provider_setting('VISION_API_KEY'), 'model': 'qwen2.5-vl-72b', 'url': 'https://api.modelarts-maas.com/v1/chat/completions'}
TEXT_CONFIG = {
    'api_key': _provider_setting('TEXT_API_KEY'),
    'model': _provider_setting('TEXT_MODEL', 'deepseek-flash'),
    'url': _provider_setting('TEXT_API_URL', 'https://api.deepseek.com/chat/completions'),
    'thinking': {'type': 'disabled'},
}
BAIDU_MAP_CONFIG = {'api_key': _provider_setting('BAIDU_MAP_API_KEY'), 'reverse_geocode_url': 'https://api.map.baidu.com/reverse_geocoding/v3/', 'place_search_url': 'https://api.map.baidu.com/place/v2/search'}
UPLOAD_FOLDER = 'uploads'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
