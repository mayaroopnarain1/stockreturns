# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from api.serialize import frame_records, iso, series_xy, to_jsonable


class SerializeTests(unittest.TestCase):
    def test_nan_inf_become_none(self):
        out = to_jsonable({"a": float("nan"), "b": np.inf, "c": np.float64(1.5), "d": np.int64(3)})
        self.assertEqual(out, {"a": None, "b": None, "c": 1.5, "d": 3})
        json.dumps(out, allow_nan=False)  # strict JSON must succeed

    def test_series_with_datetime_index(self):
        s = pd.Series([1.0, np.nan, 3.0], index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
        out = series_xy(s)
        self.assertEqual(out["x"], ["2024-01-01", "2024-01-02", "2024-01-03"])
        self.assertEqual(out["y"], [1.0, None, 3.0])

    def test_tz_aware_timestamps_drop_timezone(self):
        ts = pd.Timestamp("2024-03-01 16:00", tz="America/New_York")
        self.assertEqual(iso(ts), "2024-03-01")

    def test_frame_records_with_index(self):
        df = pd.DataFrame({"x": [1, 2], "y": [np.nan, 4.0]}, index=["a", "b"])
        recs = frame_records(df, index_name="k")
        self.assertEqual(recs, [{"k": "a", "x": 1, "y": None}, {"k": "b", "x": 2, "y": 4.0}])

    def test_empty_inputs(self):
        self.assertEqual(series_xy(pd.Series(dtype=float)), {"x": [], "y": []})
        self.assertEqual(frame_records(pd.DataFrame()), [])

    def test_dataframe_shape(self):
        df = pd.DataFrame({"a": [1.0, np.nan]}, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
        out = to_jsonable(df)
        self.assertEqual(out["columns"], ["a"])
        self.assertEqual(out["data"], [[1.0], [None]])
        self.assertEqual(out["index"], ["2024-01-01", "2024-01-02"])


if __name__ == "__main__":
    unittest.main()
