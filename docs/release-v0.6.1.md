# GIS Data Watchtower v0.6.1

Watchtower honors a provider's HTTP 429 and `Retry-After` if curl is interrupted
after receiving the response headers. A saved worker run stops requests to the
affected host and retains the backoff across subsequent runs.
See [PR #288](https://github.com/clearparcel/GIS-Data-Watchtower/pull/288).
