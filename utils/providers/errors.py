# -*- coding: utf-8 -*-
"""Provider error types used by the chain dispatcher."""


class ProviderError(Exception):
    """Base class for all provider failures."""


class ProviderNotCovered(ProviderError):
    """The ticker (or data class) is structurally not available from this provider.

    Raised by the EDGAR provider for ADRs / foreign issuers with no XBRL
    presence, and for capabilities EDGAR does not serve (e.g. live prices).
    The chain dispatcher catches this and falls through to the next provider.
    """


class ProviderRateLimited(ProviderError):
    """The provider is rate-limiting us and exhausted retries were unsuccessful."""
