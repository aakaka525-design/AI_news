"""Expose uppercase settings symbols from config.settings."""

from . import settings as _settings

__all__ = [name for name in dir(_settings) if name.isupper()]
globals().update({name: getattr(_settings, name) for name in __all__})
