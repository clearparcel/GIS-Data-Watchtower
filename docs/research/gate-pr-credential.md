# Gate-PR credential: fine-grained PAT vs. GitHub App

Research for [#189](https://github.com/clearparcel/GIS-Data-Watchtower/issues/189). Researched 2026-11-03 against GitHub and Google Cloud documentation.

## Question

The Cloud Run service behind IAP must create one branch and open one pull request on this repository when the owner clicks "Draft gate change." What is the narrowest GitHub credential for that, and how is it rotated?

Known repository state (read from the REST API on 2026-11-03): the repository is owned by an organization and is public. `main` requires 7 status checks with strict (up-to-date) mode, `enforce_admins` is on, there are no push restrictions, and the required approving review count is 0. No rulesets are defined.

## Recommendation

**Use a GitHub App installed on this repository only**, with repository permissions `Contents: write` and `Pull requests: write` (plus the mandatory `Metadata: read`). Do not grant `Workflows`, `Administration`, or any organization permission. Store the App private key in Secret Manager, or for a stronger setup import it into Cloud KMS as a sign-only key. Mint a one-hour installation token per click, scoped in the request body to this one repository and these two permissions. Do not add the App to any bypass list.

A fine-grained PAT works, but it is tied to a person, expires on a schedule that someone has to remember, and makes bot-drafted PRs look like the owner's own work. Use it only as a short-lived stopgap.

## Comparison

| Concern | Fine-grained PAT | GitHub App installation token |
| --- | --- | --- |
| Minimum permissions | `Contents: write` (branch ref, blobs, trees, commits, or the contents API) and `Pull requests: write` (create the PR) [1] | Same two permissions, set on the App and narrowed again per token [1][3] |
| Limit to one repo | Yes: one resource owner and selected repositories [2]. It still gets read-only access to all public repositories [2] | Yes: install on selected repositories, then pass `repositories` or `repository_ids` when minting [3] |
| Stored secret | The token itself, valid until it expires | The App private key. It does not expire and must be revoked manually [5] |
| Credential lifetime | Chosen at creation. Organization default maximum is 366 days, and "no expiration" is possible unless a policy blocks it [2][4] | Installation token: 1 hour [3]. JWT used to mint it: 10 minutes or less, RS256 [6] |
| Rotation | Manual: create a new token, store a new secret version, revoke the old one. Secret Manager rotation schedules only send Pub/Sub notifications. You have to build the rotation yourself [7] | No per-use rotation, because a new token is minted on every use. To rotate the key, add a second key (multiple keys are allowed), deploy it, then delete the old one [5] |
| Audit attribution | The token is "tied to the user who generated them" [2]. Activity looks like the owner's own | Activity is attributed to the App (shown as `<app>[bot]`) when it authenticates as an installation [8] |
| Organization policy | Fine-grained PATs are allowed by default. Owners may require approval (the default) and set a maximum lifetime [4]. Tokens created by an organization owner are approved automatically [2][4] | Installing the App on the repository requires an organization owner. There is no PAT policy to satisfy |
| Branch protection bypass | Acts with its owner's role, limited by the token permissions. Admins can bypass by default, but `enforce_admins` (that is, "Do not allow bypassing the above settings") also applies the rules to admins and bypass roles [9][10] | Can bypass only if it is added to a bypass or push-allowance list, and actors can be added to bypass lists only for organization repositories [10]. Do not add it |
| Triggers CI on the PR | Yes. Events created by `GITHUB_TOKEN` do not start new runs (except `workflow_dispatch`/`repository_dispatch`), and the docs name a PAT or an App installation token as the alternatives. These also let `pull_request` workflows run without approval [11] | Yes, for the same reason [11] |
| Dependencies | stdlib `urllib` only | An RS256 signer for the JWT: the `cryptography` package via `google-auth`'s `google.auth.crypt.RSASigner` [12], or Cloud KMS `asymmetricSign` with an imported `rsa-sign-pkcs1-2048-sha256` key [13] |

## Risks to note in the implementation

- **`Contents: write` can also merge.** `PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge` requires only `Contents: write` [1]. Because `main` requires 0 approving reviews, the credential could merge its own PR once all 7 checks pass. Branch protection blocks merging before then. The service must never call the merge endpoint. If a hard guarantee is wanted, require at least one approving review on `main`. Note that this would also gate the owner's own PRs, so it is an owner decision.
- **Workflow files stay out of reach.** Without the `Workflows` permission, the contents and refs endpoints cannot change `.github/workflows` [1]. Leave it off so a drafted gate change cannot edit CI.
- **Narrow every mint.** Pass `repositories` and `permissions` on each installation-token request even though the installation is already narrow. A token "cannot be granted permissions that the app was not granted" [3].
- **Protect the private key.** Store it outside environment variables and source control. GitHub recommends a key vault so the key is used only for signing [5]. If the key sits in Secret Manager, grant `secretAccessor` only to the service's runtime service account.
- **Public repository.** The App ID, installation ID, and key belong in Secret Manager or runtime configuration, never in the repository (see `AGENTS.md`).

## Sources

1. GitHub Docs, [Permissions required for fine-grained personal access tokens](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens). The same permission model applies to GitHub Apps.
2. GitHub Docs, [Managing your personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
3. GitHub Docs, [Generating an installation access token for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)
4. GitHub Docs, [Setting a personal access token policy for your organization](https://docs.github.com/en/organizations/managing-programmatic-access-to-your-organization/setting-a-personal-access-token-policy-for-your-organization)
5. GitHub Docs, [Managing private keys for GitHub Apps](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps)
6. GitHub Docs, [Generating a JSON Web Token (JWT) for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app)
7. Google Cloud, [Create rotation schedules in Secret Manager](https://docs.cloud.google.com/secret-manager/docs/secret-rotation)
8. GitHub Docs, [About authentication with a GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/about-authentication-with-a-github-app)
9. GitHub Changelog, [Bypass branch protections with a new permission](https://github.blog/changelog/2022-08-18-bypass-branch-protections-with-a-new-permission/) (2022-08-18)
10. GitHub Docs, [Managing a branch protection rule](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule)
11. GitHub Docs, [Triggering a workflow](https://docs.github.com/en/actions/using-workflows/triggering-a-workflow) ("Triggering a workflow from a workflow")
12. google-auth, [`google.auth.crypt` package](https://googleapis.dev/python/google-auth/latest/reference/google.auth.crypt.html)
13. Google Cloud, [`gcloud kms keys versions import`](https://docs.cloud.google.com/sdk/gcloud/reference/kms/keys/versions/import)

Not verified from a primary source: the exact `<app>[bot]` display name format. It is consistent with [8], but this research did not find it quoted. The private-key page was read from a GitHub Enterprise Server copy because the dotcom page was unreachable from this environment.
