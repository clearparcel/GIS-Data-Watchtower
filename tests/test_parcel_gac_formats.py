"""Legacy (mngac_completeness) and modern (gac_completeness, parcel) observations are equivalent."""
import datetime as dt
import unittest

from clearparcel.datawatch import dashboard
from clearparcel.datawatch.county_profile_exports import county_profiles_csv
from clearparcel.datawatch.county_profiles import FreshnessPolicy, compose_county_profiles, county_profile_counts
from clearparcel.datawatch.gac_standards import gac_payload
from clearparcel.datawatch.private_snapshot import validate_private_snapshot


STAMP = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def state_for(fmt):
    stamp = STAMP
    payload = {"fields": {"PIN": {}}, "counties": {"Aitkin": {"record_count": 1234}}}
    if fmt == "modern":
        payload = {**payload, "standard_key": "parcel"}
    key = "gac_completeness" if fmt == "modern" else "mngac_completeness"
    return {"generated_at": stamp, "sources": {"mn-state-parcels": {
        "id": "mn-state-parcels", "category": "Parcels", "status": "ok", "checked_at": stamp,
        "last_report_at": stamp, "last_success_at": stamp, "feature_count": 999999, key: payload}}}


class ParcelGacFormatTests(unittest.TestCase):
    def views(self, fmt):
        config = {"_render_state": state_for(fmt), "state_file": "unused.json"}
        state = dashboard._dashboard_state(config)
        research = dashboard.load_parcel_access()
        profiles = compose_county_profiles(state, research, now=dt.datetime.now(dt.timezone.utc),
                                           freshness_policy=FreshnessPolicy())
        county = next(c for c in dashboard._load_counties() if c["slug"] == "aitkin")
        status = dashboard._county_status(config, county, state, profiles=profiles, research=research)
        return profiles, status

    def test_county_profiles_counts_status_and_exports_match(self):
        legacy_profiles, legacy_status = self.views("legacy")
        modern_profiles, modern_status = self.views("modern")
        aitkin_legacy, aitkin_modern = legacy_profiles["aitkin"], modern_profiles["aitkin"]
        self.assertEqual(aitkin_legacy["monitoring"]["paths"], ["mngeo-open"])
        self.assertEqual(aitkin_modern["monitoring"]["paths"], aitkin_legacy["monitoring"]["paths"])
        self.assertEqual(aitkin_modern["mngac_public_parcels"]["availability"], "yes")
        self.assertEqual(county_profile_counts(modern_profiles), county_profile_counts(legacy_profiles))
        self.assertEqual(county_profiles_csv(modern_profiles), county_profiles_csv(legacy_profiles))
        for key in ("status", "actively_monitored"):
            self.assertEqual(modern_status.get(key), legacy_status.get(key), key)

    def test_helper_prefers_complete_payloads_and_respects_standard(self):
        modern = {"standard_key": "parcel", "fields": {"PIN": {}}, "counties": {"A": {}}}
        legacy = {"fields": {"PIN": {}}, "counties": {"B": {}}}
        self.assertIs(gac_payload({"gac_completeness": modern, "mngac_completeness": legacy}), modern)
        self.assertIs(gac_payload({"gac_completeness": {**modern, "counties": {}}, "mngac_completeness": legacy},
                                  require=("fields", "counties")), legacy)
        self.assertIsNone(gac_payload({"gac_completeness": {**modern, "standard_key": "road"}}))
        self.assertIsNone(gac_payload({"mngac_completeness": legacy}, "address"))
        self.assertIsNone(gac_payload(None))

    def test_private_snapshot_rejects_malformed_modern_payload(self):
        record = {"id": "s", "gac_completeness": "not an object"}
        with self.assertRaises(ValueError):
            validate_private_snapshot({"sources": {"s": record}})


if __name__ == "__main__":
    unittest.main()
