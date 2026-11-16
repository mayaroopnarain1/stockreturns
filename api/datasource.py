# -*- coding: utf-8 -*-
"""
Single seam between the API services and the data layer.

``data`` resolves to the real ``utils.data`` (yfinance + EDGAR) normally, or to
``api.fake`` when ``STOCKLENS_FAKE_DATA=1``. The fake source is deterministic
and offline, used by tests and UI checks in environments with no network.
Resolution happens on every attribute access so tests can flip the variable.
"""

from __future__ import annotations

import importlib
import os


class _DataProxy:
    @staticmethod
    def _module():
        name = "api.fake" if os.environ.get("STOCKLENS_FAKE_DATA") == "1" else "utils.data"
        return importlib.import_module(name)

    def __getattr__(self, item: str):
        return getattr(self._module(), item)


data = _DataProxy()
