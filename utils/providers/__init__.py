# -*- coding: utf-8 -*-
"""
Data-provider abstraction.

The façade in ``utils/data.py`` dispatches each fetch through a short chain of
providers. For US issuers, SEC EDGAR (authoritative XBRL) is primary for
fundamentals, statements, dividends and historical earnings dates. yfinance
stays primary for anything price-shaped (quotes, macro, daily changes) and is
the fallback when EDGAR does not cover a ticker (ADRs, foreign issuers).
"""

from .errors import ProviderError, ProviderNotCovered, ProviderRateLimited

__all__ = ["ProviderError", "ProviderNotCovered", "ProviderRateLimited"]
