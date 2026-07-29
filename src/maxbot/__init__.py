"""Локальная основа MAX-бота без внешних подключений."""

from .models import Referral
from .service import ProcessingResult, ReferralProcessor

__all__ = ["ProcessingResult", "Referral", "ReferralProcessor"]

