"use strict";

const form = document.querySelector("#editor");
const fields = document.querySelector("#fields");
const countyList = document.querySelector("#counties");
const search = document.querySelector("#county-search");
const message = document.querySelector("#status");
const retry = document.querySelector("#retry");
const apply = document.querySelector("#apply");
const discard = document.querySelector("#discard");
const labels = {
    published: "Published.",
    pending: "Saved privately. Publication is pending.",
    saved_private: "Private changes saved.",
    superseded: "Saved. A newer public revision is already visible.",
    revision_conflict: "This county changed elsewhere. Discard to load the current record.",
    invalid_draft: "Check the contact fields, public links, access evidence, and restriction details.",
    body_too_large: "The county record exceeds the save limit.",
    storage_unavailable: "The save could not be confirmed. Retry the same request.",
    unsaved: "Review the packaged starting values and apply to save.",
};
const datasetNames = {
    parcel_polygons: "Parcel Polygons",
    road_centerlines: "Road Centerlines",
    address_points: "Address Points",
};
const methodNames = {
    mngeo_open: "MnGeo open",
    direct_rest: "Direct REST",
    direct_download: "Direct Download",
    other: "Other",
};
const chicago = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "America/Chicago", dateStyle: "short", timeStyle: "short",
});
const attachmentCache = new Map();

let counties = [];
let csrf;
let selected = "";
let draft;
let revision;
let dirty = false;
let busy = false;
let pendingRequest = null;
let retryTimer;

async function request(path, payload) {
    const response = await fetch(path, payload === undefined ? {} : {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-Watchtower-CSRF": csrf},
        body: JSON.stringify(payload),
    });
    return {code: response.status, ...await response.json()};
}

function node(tag, text, parent) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (parent) parent.append(element);
    return element;
}

function button(parent, text, action) {
    const control = node("button", text, parent);
    control.type = "button";
    control.addEventListener("click", action);
    return control;
}

function group(parent, title) {
    const group = node("fieldset", undefined, parent);
    node("legend", title, group);
    return group;
}

function changed() {
    dirty = true;
    message.textContent = "Unsaved changes.";
}

function input(parent, title, object, key, type = "text") {
    const label = node("label", title, parent);
    const control = node(type === "textarea" ? type : "input", undefined, label);
    if (type !== "textarea") control.type = type;
    control.value = object[key] ?? "";
    control.addEventListener("input", () => {
        object[key] = control.value;
        changed();
    });
    return control;
}

function select(parent, title, values, current, change) {
    const control = node("select", undefined, node("label", title, parent));
    for (const [value, label] of Object.entries(values)) node("option", label, control).value = value;
    control.value = current;
    control.addEventListener("change", () => change(control.value));
    return control;
}

function contacts() {
    const section = group(fields, "Public contacts");
    const active = draft.contacts.filter(contact => !contact.removed);
    if (!active.length) node("p", "No listed contacts.", section);
    for (const contact of active) {
        const card = group(section, contact.name || contact.department || "New contact");
        const grid = node("div", undefined, card);
        grid.className = "grid";
        for (const [key, title, type] of [
            ["name", "Name or office"], ["role", "Role"], ["department", "Department"],
            ["phone", "Phone", "tel"], ["email", "Email", "email"], ["website", "Website", "url"],
            ["source_url", "Public source link", "url"], ["verified_on", "Verified on", "date"],
        ]) input(grid, title, contact, key, type);
        button(card, "Remove contact", () => {
            contact.removed = true;
            changed();
            render();
        });
    }
    button(section, "Add contact", () => {
        draft.contacts.push({id: crypto.randomUUID()});
        changed();
        render();
        fields.querySelectorAll("input")[active.length * 8]?.focus();
    });
}

function access() {
    for (const [dataset, title] of Object.entries(datasetNames)) {
        const data = draft.access[dataset] ??= {classification: "unknown", methods: []};
        data.methods ??= [];
        const section = group(fields, title);
        const choices = group(section, "Access classification");
        for (const [value, label] of Object.entries({open: "Open GIS Data", fee: "Fee Based GIS Data", unknown: "Unknown"})) {
            const wrapper = node("label", undefined, choices);
            const radio = node("input", undefined, wrapper);
            radio.type = "radio";
            radio.name = dataset;
            radio.checked = (data.classification || "unknown") === value;
            wrapper.append(label);
            radio.addEventListener("change", () => {
                data.classification = value;
                changed();
                render();
                fields.querySelector("input[name=" + dataset + "]:checked")?.focus();
            });
        }
        if (data.classification === "open") {
            const methods = group(section, "Open delivery methods");
            for (const [kind, label] of Object.entries(methodNames)) {
                const selectedMethod = data.methods.find(method => method.kind === kind);
                const wrapper = node("label", undefined, methods);
                const checkbox = node("input", undefined, wrapper);
                checkbox.type = "checkbox";
                checkbox.id = dataset + "-" + kind;
                checkbox.checked = Boolean(selectedMethod);
                wrapper.append(label);
                checkbox.addEventListener("change", () => {
                    if (checkbox.checked) data.methods.push({kind});
                    else data.methods = data.methods.filter(method => method.kind !== kind);
                    changed();
                    render();
                    document.getElementById(checkbox.id)?.focus();
                });
                if (selectedMethod) {
                    input(methods, label + " evidence URL", selectedMethod, "url", "url").required = true;
                    input(methods, label + " evidence date", selectedMethod, "evidence_date", "date").required = true;
                    input(methods, label + " scope", selectedMethod, "scope").required = true;
                    if (kind === "other") input(methods, "Other method description", selectedMethod, "description").required = true;
                }
            }
        }
        input(section, "Public county-direct access note", data, "county_direct_note", "textarea");
        const restrictions = data.restrictions ??= {status: "unreviewed"};
        const restrictionSelect = select(section, "Use restrictions", {
            unreviewed: "Not yet reviewed", reviewed_none: "None recorded", restricted: "Restrictions apply",
        }, restrictions.status, value => {
            restrictions.status = value;
            changed();
            render();
            document.getElementById(dataset + "-restrictions")?.focus();
        });
        restrictionSelect.id = dataset + "-restrictions";
        if (restrictions.status !== "unreviewed") input(section, "Reviewed on", restrictions, "reviewed_on", "date");
        if (restrictions.status === "restricted") {
            input(section, "Public restriction details", restrictions, "text", "textarea").required = true;
            input(section, "Official restrictions URL", restrictions, "url", "url");
        }
    }
}

function eventTime(parent, title, event, key) {
    const existing = typeof event[key] === "string" ? event[key] : "";
    const values = {date: existing.slice(0, 10), time: existing.slice(11, 16)};
    const date = input(parent, title + " date (Central)", values, "date", "date");
    const time = input(parent, title + " time (Central)", values, "time", "time");
    const offset = select(parent, title + " offset if the time occurs twice", {
        "": "Select for the repeated fall hour", "-05:00": "Daylight time (UTC−05)", "-06:00": "Standard time (UTC−06)",
    }, existing.slice(-6), update);
    function update(markChanged = true) {
        time.setCustomValidity("");
        if (!date.value && !time.value) {
            delete event[key];
            return;
        }
        const local = date.value + "T" + time.value;
        const candidates = ["-05:00", "-06:00"].filter(suffix => {
            const instant = new Date(local + suffix);
            return !Number.isNaN(instant.valueOf()) && chicago.format(instant) === local.replace("T", " ");
        });
        const suffix = candidates.length === 1 ? candidates[0] : offset.value;
        if (!candidates.includes(suffix)) {
            time.setCustomValidity("Enter a valid Central date and time. Choose an offset for the repeated fall hour.");
            return;
        }
        event[key] = local + suffix;
        if (markChanged) changed();
    }
    date.addEventListener("input", update);
    time.addEventListener("input", update);
    update(false);
}

function correspondence() {
    const section = group(fields, "Private correspondence");
    section.className = "private";
    node("p", "These records stay private. Recording an event does not send email.", section);
    for (const event of draft.correspondence) {
        const card = group(section, event.subject || "Email event");
        const names = {"": "No linked contact"};
        for (const contact of draft.contacts) {
            if (contact.id && (!contact.removed || contact.id === event.contact_id)) {
                names[contact.id] = contact.name || contact.department || "Contact";
            }
        }
        select(card, "Linked contact", names, event.contact_id || "", id => {
            event.contact_id = id;
            if (id && !event.recipient) event.recipient = names[id];
            changed();
            render();
        });
        input(card, "Historical recipient", event, "recipient");
        input(card, "Subject", event, "subject");
        eventTime(card, "Sent", event, "sent_at");
        eventTime(card, "Reply", event, "reply_at");
        input(card, "Private notes", event, "notes", "textarea");
        event.attachment_ids ??= [];
        attachmentField(card, "Private email PDF", event.attachment_ids, "correspondence", event.id,
            id => event.attachment_ids.push(id),
            id => { event.attachment_ids = event.attachment_ids.filter(value => value !== id); });
    }
    button(section, "Add email event", () => {
        draft.correspondence.push({id: crypto.randomUUID()});
        changed();
        render();
    });
}

function attachmentField(parent, title, ids, kind, eventId, attach, detach) {
    const area = group(parent, title);
    area.className = "private";
    for (const id of ids) {
        const row = node("p", "Checking private file…", area);
        const url = path() + "/attachments/" + encodeURIComponent(id);
        const show = meta => {
            row.replaceChildren();
            if (meta.status === "clean") {
                node("a", meta.filename, row).href = url;
            } else {
                const status = {pending: "Quarantined, awaiting scan", rejected: "Rejected by scan"};
                row.textContent = (meta.filename || "Private file") + " · " + (status[meta.status] || "Status unavailable");
            }
            button(row, "Detach", () => { detach(id); changed(); render(); });
            lock(busy);
        };
        if (attachmentCache.has(id)) show(attachmentCache.get(id));
        else request(url + "/status").then(show).catch(() => show({}));
    }
    const picker = node("input", undefined, node("label", "Select a private PDF", area));
    picker.type = "file";
    picker.accept = ".pdf,application/pdf";
    let uploadId;
    picker.addEventListener("change", () => { uploadId = crypto.randomUUID().replaceAll("-", ""); });
    button(area, "Upload to quarantine", async () => {
        const file = picker.files[0];
        if (!file) {
            message.textContent = "Select a PDF first.";
            return;
        }
        if (file.size > 20 * 1024 * 1024) {
            message.textContent = "The file exceeds the 20 MB upload limit.";
            return;
        }
        const query = new URLSearchParams({kind});
        if (eventId) query.set("event", eventId);
        lock(true);
        try {
            const response = await fetch(path() + "/attachments?" + query, {
                method: "POST",
                headers: {"Content-Type": "application/pdf", "X-Watchtower-CSRF": csrf,
                    "X-Watchtower-Filename": file.name, "X-Watchtower-Upload-ID": uploadId},
                body: file,
            });
            const result = await response.json();
            if (!response.ok) {
                message.textContent = result.status === "invalid_attachment"
                    ? "Choose a valid PDF with a filename containing letters, numbers, spaces, or basic punctuation."
                    : "The upload could not be confirmed. Retry this file.";
                return;
            }
            attachmentCache.set(result.id, result);
            attach(result.id);
            changed();
            render();
            message.textContent = "File saved to private quarantine. Apply to link it to this county record.";
        } catch {
            message.textContent = "The upload could not be confirmed. Retry this file.";
        } finally {
            lock(false);
        }
    });
}

function render() {
    fields.replaceChildren();
    draft.contacts ??= [];
    draft.access ??= {};
    draft.policy ??= {};
    draft.correspondence ??= [];
    contacts();
    access();
    const policy = group(fields, "County policy");
    input(policy, "Public policy text", draft.policy, "text", "textarea");
    input(policy, "Official policy URL", draft.policy, "url", "url");
    attachmentField(policy, "Private policy PDF", draft.policy.attachment_id ? [draft.policy.attachment_id] : [],
        "policy", null, id => { draft.policy.attachment_id = id; }, () => { delete draft.policy.attachment_id; });
    correspondence();
    lock(busy);
}

function path() {
    return "/api/counties/" + encodeURIComponent(selected);
}

function lock(value) {
    busy = value;
    countyList.disabled = value;
    apply.disabled = value;
    retry.disabled = value;
    discard.disabled = value;
    for (const control of fields.querySelectorAll("input,select,button,textarea")) {
        control.disabled = value || pendingRequest !== null;
    }
}

function list() {
    const term = search.value.trim().toLocaleLowerCase();
    countyList.replaceChildren();
    for (const county of counties) {
        if (![county.name, ...(county.search_terms || [])].some(value => value.toLocaleLowerCase().includes(term))) continue;
        const name = county.name + (county.contact_count === undefined ? "" : " (" + county.contact_count + ")");
        node("option", name, countyList).value = county.slug;
    }
    countyList.value = selected;
}

function publicationState(result) {
    retry.hidden = result.status !== "pending";
    if (result.status === "pending") {
        clearTimeout(retryTimer);
        retryTimer = setTimeout(() => retryPublication(true), 3000);
    }
}

async function loadCounty(slug) {
    clearTimeout(retryTimer);
    lock(true);
    try {
        const detail = await request("/api/counties/" + encodeURIComponent(slug));
        if (detail.code !== 200) throw new Error("Unavailable");
        selected = slug;
        attachmentCache.clear();
        draft = detail.draft;
        revision = detail.revision;
        pendingRequest = null;
        dirty = false;
        list();
        document.querySelector("#county-title").textContent = detail.county.name + " County";
        form.hidden = false;
        render();
        const status = await request(path() + "/publication");
        message.textContent = labels[status.status] || "County record loaded.";
        publicationState(status);
    } catch {
        message.textContent = "County details or publication status are temporarily unavailable.";
        list();
    } finally {
        lock(false);
    }
}

async function retryPublication(automatic = false) {
    if (busy || pendingRequest || (automatic && dirty)) return;
    lock(true);
    try {
        const result = await request(path() + "/publication", {});
        message.textContent = labels[result.status] || "Publication status is unavailable.";
        retry.hidden = result.status !== "pending";
        if (!automatic && result.status === "pending") publicationState(result);
    } catch {
        message.textContent = "Publication status is unavailable. Retry when the service is reachable.";
    } finally {
        lock(false);
    }
}

form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy) return;
    pendingRequest ??= {expected_revision: revision, request_id: crypto.randomUUID(), draft: structuredClone(draft)};
    lock(true);
    try {
        const result = await request(path(), pendingRequest);
        message.textContent = labels[result.status] || "The request could not be completed.";
        if (result.code === 200 || result.code === 202) {
            revision = result.revision;
            dirty = false;
            pendingRequest = null;
            if (result.status !== "saved_private") publicationState(result);
            const directory = await request("/api/counties");
            if (directory.code === 200) {
                counties = directory.counties;
                list();
            }
        } else if (result.code < 500) {
            pendingRequest = null;
        }
    } catch {
        message.textContent = "The request could not be confirmed. Click Apply to retry the same save.";
    } finally {
        lock(false);
    }
});
discard.addEventListener("click", () => loadCounty(selected));
retry.addEventListener("click", () => retryPublication());
search.addEventListener("input", list);
countyList.addEventListener("change", () => {
    if (countyList.value && (!(dirty || pendingRequest) || confirm("Leave this county and discard unsaved changes?"))) {
        loadCounty(countyList.value);
    } else list();
});
window.addEventListener("beforeunload", event => {
    if (dirty || pendingRequest) event.preventDefault();
});

request("/api/counties").then(directory => {
    if (directory.code !== 200) throw new Error("Unavailable");
    csrf = directory.csrf_token;
    counties = directory.counties;
    list();
}).catch(() => { message.textContent = "The county directory is temporarily unavailable."; });
