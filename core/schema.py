"""drf-spectacular preprocessing hooks."""


def preprocess_only_api_paths(endpoints, **kwargs):
    """Keep only endpoints under /api/ in the OpenAPI schema."""
    return [e for e in endpoints if e[0].startswith('/api/')]
