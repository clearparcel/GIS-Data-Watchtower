# Contributing

Contributions are welcome after the repository is approved for public release.

Before submitting a change:

1. Do not add a provider unless its automated-access and redistribution terms have been reviewed.
2. Keep polling conservative and bounded.
3. Do not add secrets, private machine paths, operational state, or raw parcel-owner data.
4. Add or update tests for behavioral changes.
5. Run:
   ```bash
   python -W error::ResourceWarning -m unittest discover -s tests -q
   python -m compileall -q clearparcel tests
   ```
6. Keep dashboard language understandable to non-technical users.

Changes that increase provider request volume should document the expected request count and cadence.
