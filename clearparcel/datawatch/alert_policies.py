"""Cloud Monitoring alert policies for provider-run health, as reviewable code.

Three policies replace the original "provider job execution did not succeed"
policy, which fired on every non-zero exit (including exit 2 for a single
county source error):

1. **Tool failure** - the provider job's container exited 3 (Watchtower
   itself failed). Exits 1 and 2 stay with the per-source alert digest.
2. **Provider run overdue** - the public publisher's provider-run watchdog
   logged ``watchtower_provider_run_overdue`` (no worker report for 26 hours).
   A metric-absence condition cannot express this directly: Cloud Monitoring
   caps the absence duration at 23.5 hours, shorter than one daily cycle.
3. **Publisher absent** - the publisher itself completed no successful run for
   an hour, which also covers a scheduling stop while the job still exists.

A fourth, informational policy, **weekly digest**, emails the Monday
``weekly-digest`` run's data-freshness summary (subject and body come from the
log line). Stale publisher data is never an outage alert.

Deployment identifiers (project, job names, notification channel) are private
and are supplied only when rendering; nothing here is project-specific.
"""
from __future__ import annotations

import re

from clearparcel.datawatch.provider_watchdog import ERROR_KEY, LOG_KEY
from clearparcel.datawatch.weekly_digest import LOG_KEY as DIGEST_KEY

_JOB = re.compile(r"^[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_CHANNEL = re.compile(r"^projects/[a-z][a-z0-9-]{4,28}[a-z0-9]/notificationChannels/[0-9]+$")

RUNBOOK = "docs/operations-triage.md"
PUBLISHER_ABSENT_SECONDS = 3600
OVERDUE_NOTIFY_EVERY_SECONDS = 6 * 3600


def _check(provider_job: str, publisher_job: str, channel: str, digest_job: str) -> None:
    for label, value in (("provider job", provider_job), ("publisher job", publisher_job),
                         ("digest job", digest_job)):
        if not isinstance(value, str) or not _JOB.fullmatch(value):
            raise ValueError(f"{label} name is not a valid Cloud Run job name")
    if publisher_job in (provider_job, digest_job):
        raise ValueError("the publisher job must differ from the provider and digest jobs")
    if not isinstance(channel, str) or not _CHANNEL.fullmatch(channel):
        raise ValueError("channel must look like projects/<project>/notificationChannels/<id>")


def _docs(text: str) -> dict:
    return {"content": f"{text}\n\nRunbook: `{RUNBOOK}` in the Watchtower repository.",
            "mimeType": "text/markdown"}


def build_policies(*, provider_job: str, publisher_job: str, channel: str,
                   digest_job: str | None = None) -> dict[str, dict]:
    """Return ``{file stem: AlertPolicy}`` ready for ``gcloud monitoring policies create``.

    ``digest_job`` is the Cloud Run job that runs ``weekly-digest``. It defaults
    to the provider job; a dedicated job with fixed arguments lets the scheduler
    start it without permission to override a job's arguments.
    """
    digest_job = provider_job if digest_job is None else digest_job
    _check(provider_job, publisher_job, channel, digest_job)
    job = 'resource.type="cloud_run_job" AND resource.labels.job_name="{}"'
    return {
        "provider-tool-failure": {
            "displayName": "Watchtower provider job: tool failure (exit 3)",
            "combiner": "OR",
            "severity": "CRITICAL",
            "conditions": [{
                "displayName": "Provider job container exited 3",
                "conditionMatchedLog": {
                    "filter": job.format(provider_job) + ' AND textPayload:"Container called exit(3)"',
                },
            }],
            "alertStrategy": {"notificationRateLimit": {"period": "3600s"}, "autoClose": "86400s"},
            "notificationChannels": [channel],
            "documentation": _docs(
                "Watchtower itself failed during a provider run (exit 3). Single-source errors "
                "(exit 1 or 2) are not reported here; they arrive in the source alert digest."),
            "enabled": True,
        },
        "provider-run-overdue": {
            "displayName": "Watchtower: no provider run reported in 26 hours",
            "combiner": "OR",
            "severity": "ERROR",
            "conditions": [{
                "displayName": "Publisher watchdog reports an overdue provider worker",
                "conditionMatchedLog": {
                    "filter": (job.format(publisher_job) + " AND severity=ERROR"
                               f" AND (jsonPayload.{LOG_KEY}.worker:* OR jsonPayload.{ERROR_KEY}:*)"),
                    "labelExtractors": {"worker": f"EXTRACT(jsonPayload.{LOG_KEY}.worker)",
                                        "reason": f"EXTRACT(jsonPayload.{LOG_KEY}.reason)"},
                },
            }],
            "alertStrategy": {"notificationRateLimit": {"period": f"{OVERDUE_NOTIFY_EVERY_SECONDS}s"},
                              "autoClose": "1800s"},
            "notificationChannels": [channel],
            "documentation": _docs(
                "No provider worker report within the staleness window (26 hours by default), or the "
                "watchdog itself failed. Check the scheduler, the provider job's recent executions, "
                "and the dispatch guard."),
            "enabled": True,
        },
        "weekly-digest": {
            "displayName": "Watchtower weekly digest",
            "combiner": "OR",
            "conditions": [{
                "displayName": "Weekly digest logged by the digest job",
                "conditionMatchedLog": {
                    "filter": (job.format(digest_job)
                               + f" AND jsonPayload.{DIGEST_KEY}.schema_version=1"),
                    "labelExtractors": {"subject": "EXTRACT(jsonPayload.message)",
                                        "body": f"EXTRACT(jsonPayload.{DIGEST_KEY}.body)",
                                        "digest_id": f"EXTRACT(jsonPayload.{DIGEST_KEY}.digest_id)"},
                },
            }],
            "alertStrategy": {"notificationRateLimit": {"period": "3600s"}, "autoClose": "1800s"},
            "notificationChannels": [channel],
            "documentation": {
                "content": ("**${log.extracted_label.subject}**\n\n```\n${log.extracted_label.body}\n```\n\n"
                            "Digest ${log.extracted_label.digest_id}. Stale publisher data is informational, not an "
                            "outage. See `docs/configuration.md` (Data freshness); runbook: "
                            f"`{RUNBOOK}` in the Watchtower repository."),
                "mimeType": "text/markdown",
                "subject": "${log.extracted_label.subject}",
            },
            "enabled": True,
        },
        "publisher-absent": {
            "displayName": "Watchtower publisher: no successful run in 1 hour",
            "combiner": "OR",
            "severity": "ERROR",
            "conditions": [{
                "displayName": "Publisher job completed no successful executions",
                "conditionAbsent": {
                    # Only successful runs count: a publisher failing every run (for
                    # example, an unreadable aggregate) never reaches the watchdog.
                    "filter": ('metric.type="run.googleapis.com/job/completed_execution_count" AND '
                               + job.format(publisher_job) + ' AND metric.labels.result="succeeded"'),
                    "aggregations": [{"alignmentPeriod": "600s", "perSeriesAligner": "ALIGN_DELTA",
                                      "crossSeriesReducer": "REDUCE_SUM",
                                      "groupByFields": ["resource.label.job_name"]}],
                    "duration": f"{PUBLISHER_ABSENT_SECONDS}s",
                    "trigger": {"count": 1},
                },
            }],
            "alertStrategy": {"autoClose": "3600s"},
            "notificationChannels": [channel],
            "documentation": _docs(
                "The public publisher has not completed a successful run for an hour. The provider-run "
                "watchdog lives in the publisher, so while this is open, overdue provider runs are not "
                "detected."),
            "enabled": True,
        },
    }
