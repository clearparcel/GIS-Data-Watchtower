# Official product name — ClearParcel GIS Data Watchtower

- Objective and acceptance criteria:
  Use the owner-decided name **ClearParcel GIS Data Watchtower** on current
  user-facing surfaces. Define it once and reference that value from
  application code. Do not rename URLs, slugs, packages, modules, the
  repository, files, or commands. Do not edit historical changelog entries,
  dated audits, or release notes for past versions. Open a pull request and
  stop. Do not merge or deploy.
- Repository, branch/worktree, exact base/head:
  - Repository: `clearparcel/GIS-Data-Watchtower`.
  - Branch: `cursor/official-product-name-e5f2`.
  - Base: `f0984c339a77d795f1c3ba94be261bace5fdaa37` (`main`).
  - Naming commit: `e423a01a3c753caf037ee6017572076a71195538`.
  - Head: the published tip of this branch. The pull request records it. A
    later commit on this branch only fills in this SHA and does not change
    behavior.
- Implementer and requested reviewer:
  - Implementer: Cursor cloud agent.
  - Requested reviewer: none. An independent review was not requested in this
    task. Merge and deployment remain separately gated.
- Shared-memory revision, IDs/hashes, freshness, and conflicts/unavailable context:
  Published CCE memory `gis-data-watchtower` was not available in this
  environment. No catalog checkout was mounted, so revision, hash, and
  freshness were not re-read. Current repository instructions and this task
  take precedence. No conflict with a retrieved record was found because the
  record could not be retrieved.
- Files and resulting behavior:
  `clearparcel/datawatch/product.py` defines `PRODUCT_NAME`. Dashboard
  headers, document titles, the application-name meta tag, public and private
  footers, alert subjects and digest bodies, the CLI status line and help
  text, the User-Agent comment, snapshot JSON titles, and workbook core
  properties read that constant. The public eyebrow uses the same text with
  CSS `text-transform: uppercase`. README, the public user guide, the docs
  index title, contributing text, package description, and current (non-archive)
  docs that named the product now use the official spelling. Markdown cannot
  import the Python constant, so those files repeat the spelling; tests pin
  the README heading and package description to the constant.
- Actual checks and results; untested paths:
  - `python3 -W error::ResourceWarning -m unittest discover -s tests -q`:
    784 tests, OK, 29.539 seconds.
  - `python3 -m compileall -q clearparcel tests scripts`: pass.
  - `python3 scripts/sync_current_status.py --check`: pass.
  - `git diff --check`: pass.
  - Local Node is v22.23.4. JavaScript behavior tests that run under Node
    were included in the suite above and passed. CI still requires Node 24.
  - Headless Chrome rendered synthetic public and private pages at desktop
    and phone widths. The official name is the header text; the public
    eyebrow is the same text in uppercase. This was not a signed-in
    production or authenticated private walkthrough.
- Review findings addressed; remaining risks:
  None received. The GitHub repository About text is a repository setting,
  not a file in this checkout, and was not changed. Short in-sentence
  "Watchtower" references remain where the full name already appears on that
  page, email, or document. See the pull request for the before/after list
  and which short references were kept.
- Next concrete step and separate approval gates:
  Review the pull request. Do not merge or deploy without a separate owner
  approval. No provider polling, schedule change, or production write was
  performed.
