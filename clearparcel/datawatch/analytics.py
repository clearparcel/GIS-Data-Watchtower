"""Optional privacy-first browser analytics for the anonymous public dashboard."""
from __future__ import annotations

import json
import os
import re
import urllib.parse


def _https_origin(value: str) -> str | None:
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    return f"https://{parsed.hostname}{port}"


def posthog_config() -> dict | None:
    # IP retention is controlled in PostHog, not by posthog-js. Require an
    # explicit deployment confirmation so a project token alone cannot
    # accidentally activate analytics before "Discard client IP data" is set.
    ip_discard_confirmed = os.environ.get(
        "WATCHTOWER_POSTHOG_IP_DISCARD_CONFIRMED", ""
    ).strip().lower() in {"1", "true", "yes"}
    if not ip_discard_confirmed:
        return None
    token = os.environ.get("WATCHTOWER_POSTHOG_PROJECT_TOKEN", "").strip()
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", token):
        return None
    api_host = _https_origin(os.environ.get("WATCHTOWER_POSTHOG_HOST", "https://us.i.posthog.com").strip())
    if not api_host:
        return None
    script_url = os.environ.get("WATCHTOWER_POSTHOG_SCRIPT_URL", "").strip()
    if script_url:
        parsed = urllib.parse.urlsplit(script_url)
        script_origin = _https_origin(script_url)
        if not script_origin or not parsed.path.endswith("/array.js"):
            return None
    else:
        parsed_host = urllib.parse.urlsplit(api_host)
        host = parsed_host.hostname or ""
        if host in {"us.i.posthog.com", "eu.i.posthog.com"}:
            asset_host = host.replace(".i.posthog.com", "-assets.i.posthog.com")
            script_url = f"https://{asset_host}/static/1/array.js"
            script_origin = f"https://{asset_host}"
        else:
            return None
    return {
        "token": token,
        "api_host": api_host,
        "script_url": script_url,
        "script_origin": script_origin,
    }


def posthog_csp_sources() -> tuple[str, str] | None:
    config = posthog_config()
    if not config:
        return None
    return config["script_origin"], config["api_host"]


def posthog_html(*, page: str, version: str, build: str, environment: str) -> str:
    config = posthog_config()
    if not config:
        return ""
    bootstrap = {
        "token": config["token"],
        "apiHost": config["api_host"],
        "scriptUrl": config["script_url"],
        "page": str(page)[:120],
        "version": str(version)[:80],
        "build": str(build)[:80],
        "environment": str(environment)[:40],
    }
    payload = json.dumps(bootstrap, separators=(",", ":")).replace("</", "<\\/")
    return fr"""<script>
(function(){{
 const cfg={payload};
 function clean(e){{if(!e||!e.properties)return e;['$current_url','$referrer','$referring_domain','$initial_current_url','$initial_referrer','$initial_referring_domain'].forEach(k=>delete e.properties[k]);return e}}
 function capture(name,props){{if(window.posthog&&typeof window.posthog.capture==='function')window.posthog.capture(name,props||{{}})}}
 function init(){{
   if(!window.posthog||typeof window.posthog.init!=='function')return;
   window.posthog.init(cfg.token,{{api_host:cfg.apiHost,autocapture:false,capture_pageview:false,capture_pageleave:false,capture_exceptions:false,disable_session_recording:true,person_profiles:'identified_only',persistence:'memory',advanced_disable_flags:true,before_send:clean}});
   capture('watchtower page viewed',{{page:cfg.page,version:cfg.version,build:cfg.build,environment:cfg.environment}});
   document.addEventListener('click',function(ev){{
     const county=ev.target.closest&&ev.target.closest('.mngac-county');
     if(county)capture('county selected',{{county_slug:county.dataset.slug||county.dataset.county||'unknown',surface:'gac-map',standard:new URLSearchParams(location.search).get('standard')||'parcel'}});
     const countyLink=ev.target.closest&&ev.target.closest('a[href^="/county?slug="]');
     if(countyLink){{const u=new URL(countyLink.href,location.origin);capture('county profile opened',{{county_slug:u.searchParams.get('slug')||'unknown',entry_surface:cfg.page}})}}
     const exportLink=ev.target.closest&&ev.target.closest('a[href]');
     if(exportLink&&/\.(csv|json|xlsx)(?:\?|$)/i.test(exportLink.getAttribute('href')||'')){{const href=exportLink.getAttribute('href')||'';const m=href.match(/\.(csv|json|xlsx)/i);capture('export downloaded',{{format:m?m[1].toLowerCase():'unknown',scope:href.includes('county')?'county':'statewide',standard:new URLSearchParams(href.split('?')[1]||'').get('standard')||'parcel'}})}}
   }});
   document.addEventListener('change',function(ev){{if(ev.target&&ev.target.id==='mngac-metric')capture('gac metric selected',{{standard:new URLSearchParams(location.search).get('standard')||'parcel',metric:String(ev.target.value||'').slice(0,128)}})}});
   document.addEventListener('toggle',function(ev){{if(ev.target&&ev.target.matches&&ev.target.matches('details.profile-evidence')&&ev.target.open)capture('evidence expanded',{{surface:cfg.page,county_slug:new URLSearchParams(location.search).get('slug')||'none',category:'county-source-evidence'}})}},true);
 }}
 const s=document.createElement('script');s.async=true;s.src=cfg.scriptUrl;s.crossOrigin='anonymous';s.onload=init;document.head.appendChild(s);
}})();
</script>"""
