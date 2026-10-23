"""Statewide exports project each GAC standard once, with unchanged output."""
import unittest
from unittest.mock import patch

from clearparcel.datawatch import dashboard
from clearparcel.datawatch.gac_standards import load_gac_standard, standard_keys


def _gac(key: str, counties: list[str]) -> dict:
    schema = load_gac_standard(key)
    fields = {f["field"]: {**f, "present_in_source_schema": True, "population_scanned": True,
                           "populated": 5, "record_count": 10, "percent": 50.0} for f in schema["fields"]}
    return {"standard_key": key, "standard": schema["standard"], "record_count": 10 * len(counties),
            "field_count": len(fields), "covered_counties": len(counties), "fields": fields,
            "county_metadata": {counties[0]: {"gac_open": False, "ng911_upload": True}},
            "counties": {name: {"record_count": 10, "mandatory_population_percent": 50.0,
                                "field_population_percent": 40.0 + i % 7,
                                "fields": {k: {"populated": 5, "record_count": 10, "percent": 50.0} for k in fields}}
                         for i, name in enumerate(counties)}}


def _stable(value):
    if isinstance(value, dict):
        return {k: _stable(v) for k, v in value.items() if not str(k).startswith("snapshot_created")}
    return [_stable(v) for v in value] if isinstance(value, list) else value


class StatewideProjectionTests(unittest.TestCase):
    def setUp(self):
        counties = [c["name"] for c in dashboard._load_counties()]
        self.state = {"sources": {key: {"status": "ok", "gac_completeness": _gac(key, counties)}
                                  for key in standard_keys()}}

    def snapshot(self, *, no_reuse: bool = False):
        calls = []
        real = dashboard.project_gac

        def counting(data, *args, **kwargs):
            calls.append(data.get("standard_key"))
            return real(data, *args, **kwargs)

        patches = [patch.object(dashboard, "_dashboard_state", return_value=self.state),
                   patch.object(dashboard, "project_gac", side_effect=counting)]
        if no_reuse:
            # The previous behavior: every call projects again.
            patches.append(patch.object(dashboard, "_snapshot_gac_view",
                                        side_effect=lambda state, key, views: dashboard._gac_data(state, key)))
        for item in patches:
            item.start()
        try:
            return dashboard._statewide_snapshot({"sources": []}), calls
        finally:
            for item in reversed(patches):
                item.stop()

    def test_each_standard_is_projected_once(self):
        snapshot, calls = self.snapshot()
        self.assertEqual(sorted(calls), sorted(standard_keys()))
        self.assertEqual(snapshot["county_count"], 87)

    def test_output_matches_unshared_projection(self):
        shared, _ = self.snapshot()
        unshared, calls = self.snapshot(no_reuse=True)
        self.assertGreater(len(calls), 87)
        self.assertEqual(_stable(shared), _stable(unshared))

    def test_single_county_payload_is_unchanged(self):
        with patch.object(dashboard, "_dashboard_state", return_value=self.state):
            views = {}
            first = dashboard._county_snapshot({"sources": []}, "douglas", gac_views=views)
            direct = dashboard._county_snapshot({"sources": []}, "douglas")
        self.assertEqual(_stable(first), _stable(direct))
        self.assertEqual(set(views), set(standard_keys()))
        self.assertEqual(set(first["gac"]), set(standard_keys()))


if __name__ == "__main__":
    unittest.main()
