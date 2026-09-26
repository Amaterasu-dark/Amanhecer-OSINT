"""Compatibilidade com os imports anteriores de telefone."""
from .sources.brasilapi import PhoneRegionProvider
from .sources.local import PhoneValidationProvider, phone_parts
from .core.normalization import BRAZIL_DIALING_PREFIX, BRAZIL_COUNTRY_CODE, DDD_LENGTH, MOBILE_NUMBER_LENGTH
