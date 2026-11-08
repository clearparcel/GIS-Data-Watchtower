"use strict";

const form = document.querySelector("#editor");
const fields = document.querySelector("#fields");
const countyList = document.querySelector("#counties");
const search = document.querySelector("#county-search");
const message = document.querySelector("#status");
const saveMessage = document.querySelector("#save-status");
const retry = document.querySelector("#retry");
const apply = document.querySelector("#apply");
const discard = document.querySelector("#discard");
const errorSummary = document.querySelector("#errors");
const scroller = document.querySelector(".editor-scroll");
const labels = {
  published: "Changes saved and published to the public county page.",
  pending: "Changes saved. Public publication is still pending.",
  saved_private:
    "Private changes saved. The public county page was not changed by this save.",
  superseded: "Changes saved. A newer public version is already visible.",
  revision_conflict:
    "This record changed while you were editing. Your edits are still here; compare the latest record before reloading.",
  invalid_draft:
    "Some information needs correcting. Review the highlighted fields.",
  body_too_large:
    "This record exceeds the save limit. Shorten long notes and try again.",
  storage_unavailable:
    "The save could not be confirmed. Use Retry save to resend the same request.",
  unsaved:
    "Not saved in this editor yet. Review the prefilled information before saving.",
};
const datasetNames = {
  parcel_polygons: "Parcel boundaries",
  road_centerlines: "Road data",
  address_points: "Address locations",
};
const methodNames = {
  mngeo_open: "Statewide data through MnGeo",
  direct_rest: "GIS service connection",
  direct_download: "Downloadable data",
  other: "Other access method",
};
const accessNames = {
  open: "Open GIS data",
  fee: "Fee-based GIS data",
  unknown: "Access not confirmed",
};
const chicago = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "America/Chicago",
  dateStyle: "short",
  timeStyle: "short",
});
const attachmentCache = new Map();
const filePickers = new Map();
const timeInputs = new Map();
const timeChecks = new Map();
let counties = [],
  csrf,
  scannerEnabled = false,
  monitoringProfiles = ["cloud"],
  selected = "",
  draft,
  baseline,
  revision;
let dirty = false,
  busy = false,
  pendingRequest = null,
  retryTimer,
  lastRemoved = null;

function status(text, saveText = text) {
  message.textContent = text;
  saveMessage.textContent = saveText;
}
function resultLabel(result) {
  const base = labels[result.status] || "Publication status is unavailable.";
  if (result.monitoring_status === "pending")
    return (
      base + " Regular check setup is pending. Use Retry updates to try again."
    );
  if (
    Number.isInteger(result.monitoring_source_count) &&
    result.monitoring_source_count > 0
  )
    return (
      base +
      ` ${result.monitoring_source_count} approved direct ${result.monitoring_source_count === 1 ? "source is" : "sources are"} registered for the next regular check.`
    );
  return base;
}
async function request(path, payload) {
  const response = await fetch(
    path,
    payload === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Watchtower-CSRF": csrf,
          },
          body: JSON.stringify(payload),
        },
  );
  if (response.status === 401 || response.status === 403 || response.redirected)
    throw new Error(
      "Your session needs attention. Sign in again or ask an administrator to check your access.",
    );
  return { code: response.status, ...(await response.json()) };
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
function checkbox(parent, title, checked, field, change) {
  const label = node("label", undefined, parent);
  const control = node("input", undefined, label);
  control.type = "checkbox";
  control.checked = checked === true;
  control.id = controlId(field);
  control.dataset.field = field;
  control.dataset.label = title;
  label.append(title);
  control.addEventListener("change", () => {
    clearFieldError(control);
    change(control.checked);
  });
  return control;
}
function help(parent, text) {
  const p = node("p", text, parent);
  p.className = "help";
  return p;
}
function group(parent, title) {
  const sectionIds = {
    Contacts: "contacts",
    "Data access": "data-access",
    Policy: "policy",
    "Private correspondence": "correspondence",
  };
  if (parent === fields) {
    const section = node("section", undefined, parent);
    section.className = "card";
    section.id = sectionIds[title];
    const heading = node("h3", title, section);
    const badge = node(
      "span",
      title.startsWith("Private") ? "Private" : "Public",
      heading,
    );
    badge.className = "visibility";
    return section;
  }
  const section = node("fieldset", undefined, parent);
  node("legend", title, section);
  return section;
}
function changed() {
  dirty = true;
  status("Unsaved changes for " + countyName() + ".");
  renderReview();
}
function countyName() {
  return (
    (counties.find((c) => c.slug === selected)?.name || selected) + " County"
  );
}
function controlId(path) {
  return "field-" + path.replaceAll(/[^a-zA-Z0-9_-]/g, "-");
}
function publicLink(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
function input(
  parent,
  title,
  object,
  key,
  type = "text",
  field = key,
  required = false,
) {
  const wrapper = node("div", undefined, parent);
  const label = node("label", title + (required ? " (required)" : ""), wrapper);
  const control = node(type === "textarea" ? type : "input", undefined, label);
  if (type !== "textarea") control.type = type;
  control.id = controlId(field);
  control.dataset.field = field;
  control.dataset.label = title;
  control.required = required;
  control.value = object[key] ?? "";
  let link;
  if (type === "url") {
    const p = node("p", undefined, wrapper);
    p.className = "url-tools";
    link = node("a", "Open link", p);
    link.target = "_blank";
    link.rel = "noopener";
  }
  function updateLink() {
    if (link) {
      const url = publicLink(control.value);
      link.hidden = !url;
      if (url) link.href = url;
      else link.removeAttribute("href");
    }
  }
  control.addEventListener("input", () => {
    object[key] = control.value;
    clearFieldError(control);
    updateLink();
    changed();
  });
  updateLink();
  return control;
}
function select(parent, title, values, current, change, field = title) {
  const control = node("select", undefined, node("label", title, parent));
  control.id = controlId(field);
  control.dataset.field = field;
  control.dataset.label = title;
  for (const [value, label] of Object.entries(values))
    node("option", label, control).value = value;
  control.value = current;
  control.addEventListener("change", () => {
    clearFieldError(control);
    change(control.value);
  });
  return control;
}
function reveal(control) {
  for (let p = control.parentElement; p; p = p.parentElement)
    if (p.tagName === "DETAILS") p.open = true;
  control.focus();
  control.scrollIntoView({ block: "nearest" });
}
function clearFieldError(control) {
  control.setCustomValidity("");
  control.removeAttribute("aria-invalid");
  control.removeAttribute("aria-describedby");
  document.getElementById(control.id + "-error")?.remove();
}
function showErrors(errors) {
  errorSummary.replaceChildren();
  errorSummary.hidden = !errors.length;
  if (!errors.length) return;
  node("h3", "Please correct these fields", errorSummary);
  const list = node("ul", undefined, errorSummary);
  for (const error of errors) {
    const control = [...fields.querySelectorAll("[data-field]")].find(
      (c) => c.dataset.field === error.field,
    );
    const row = node("li", undefined, list);
    if (control) {
      clearFieldError(control);
      control.setAttribute("aria-invalid", "true");
      const p = node("p", error.message);
      p.id = control.id + "-error";
      p.className = "field-error";
      control.closest("label").after(p);
      control.setAttribute("aria-describedby", p.id);
      button(
        row,
        (control.dataset.label || "Field") + ": " + error.message,
        () => reveal(control),
      );
    } else node("span", error.message, row);
  }
  errorSummary.focus();
  errorSummary.scrollIntoView({ block: "start" });
}
function validate() {
  for (const c of fields.querySelectorAll("[aria-invalid]")) clearFieldError(c);
  for (const [index, contact] of draft.contacts.entries()) {
    if (
      !contact.removed &&
      !(contact.name?.trim() || contact.department?.trim())
    )
      document
        .getElementById(controlId(`contacts.${index}.name`))
        .setCustomValidity("Enter a name or department for this contact.");
  }
  for (const check of timeChecks.values()) check();
  const errors = [];
  for (const c of fields.querySelectorAll("input,select,textarea")) {
    if (!c.disabled && !c.checkValidity())
      errors.push({ field: c.dataset.field, message: c.validationMessage });
  }
  for (const [dataset, data] of Object.entries(draft.access)) {
    if (data.classification === "open" && !data.methods.length)
      errors.push({
        field: `access.${dataset}.classification`,
        message: "Choose at least one way to access this data.",
      });
    for (const [index, method] of (data.methods || []).entries()) {
      const monitor = method.monitoring;
      if (!monitor?.enabled) continue;
      if (!monitoringProfiles.includes(monitor.execution_profile))
        errors.push({
          field: `access.${dataset}.methods.${index}.monitoring.execution_profile`,
          message: "Choose an available monitoring worker.",
        });
      if (data.classification !== "open")
        errors.push({
          field: `access.${dataset}.classification`,
          message: "Only open data can be included in regular checks.",
        });
      if (data.restrictions?.status !== "reviewed_none")
        errors.push({
          field: `access.${dataset}.restrictions.status`,
          message: "Review the data-use restrictions before enabling checks.",
        });
      if (monitor.terms_confirmed !== true)
        errors.push({
          field: `access.${dataset}.methods.${index}.monitoring.terms_confirmed`,
          message: "Confirm the provider terms allow regular checks.",
        });
      if (monitor.county_permission?.reply !== "permitted")
        errors.push({
          field: `access.${dataset}.methods.${index}.monitoring.county_permission.reply`,
          message: "Confirm the county approved this limited check.",
        });
    }
  }
  showErrors(errors);
  return errors.length === 0;
}

function contacts() {
  const section = group(fields, "Contacts");
  help(
    section,
    "These details appear on the public county page. Each contact needs a name or department. Other fields are optional.",
  );
  const active = draft.contacts.filter((c) => !c.removed);
  if (!active.length)
    node("p", "No listed contacts. Add an office or person below.", section);
  draft.contacts.forEach((contact, index) => {
    if (contact.removed) return;
    const card = node("div", undefined, section);
    card.className = "contact-card";
    node("h4", contact.name || contact.department || "New contact", card);
    const grid = node("div", undefined, card);
    grid.className = "grid";
    for (const [key, title, type] of [
      ["name", "Name or office"],
      ["role", "Role"],
      ["department", "Department"],
      ["phone", "Phone", "tel"],
      ["email", "Email", "email"],
      ["website", "Website", "url"],
      ["source_url", "Where this information was found", "url"],
      ["verified_on", "Contact details verified on", "date"],
    ])
      input(grid, title, contact, key, type, `contacts.${index}.${key}`);
    button(card, "Remove contact", () => {
      contact.removed = true;
      lastRemoved = contact;
      changed();
      render();
      document.getElementById("undo-contact").focus();
    }).className = "danger";
  });
  if (lastRemoved) {
    const undo = button(section, "Undo contact removal", () => {
      lastRemoved.removed = false;
      const i = draft.contacts.indexOf(lastRemoved);
      lastRemoved = null;
      changed();
      render();
      reveal(document.getElementById(controlId(`contacts.${i}.name`)));
    });
    undo.id = "undo-contact";
  }
  button(section, "Add contact", () => {
    draft.contacts.push({ id: crypto.randomUUID() });
    changed();
    render();
    reveal(
      document.getElementById(
        controlId(`contacts.${draft.contacts.length - 1}.name`),
      ),
    );
  });
}
function access() {
  const root = group(fields, "Data access");
  help(
    root,
    "Describe how to get the data. A statewide copy and county-direct access may have different terms. Access links do not grant permission for automated checks.",
  );
  for (const [dataset, title] of Object.entries(datasetNames)) {
    const data = (draft.access[dataset] ??= {
      classification: "unknown",
      methods: [],
    });
    data.methods ??= [];
    const section = node("details", undefined, root);
    section.id = dataset;
    section.className = "dataset";
    const summary = node("summary", title, section);
    node(
      "small",
      (accessNames[data.classification] || accessNames.unknown) +
        (data.classification === "open"
          ? ` · ${data.methods.length} access ${data.methods.length === 1 ? "method" : "methods"}`
          : ""),
      summary,
    );
    const choices = group(section, "How is this data available?");
    for (const [value, label] of Object.entries(accessNames)) {
      const wrapper = node("label", undefined, choices);
      const radio = node("input", undefined, wrapper);
      radio.type = "radio";
      radio.name = dataset;
      radio.id = controlId(`access.${dataset}.classification.${value}`);
      radio.dataset.field = `access.${dataset}.classification`;
      radio.dataset.label = title + " access";
      radio.checked = (data.classification || "unknown") === value;
      wrapper.append(label);
      radio.addEventListener("change", () => {
        data.classification = value;
        if (value !== "open")
          for (const method of data.methods)
            if (method.monitoring) method.monitoring.enabled = false;
        changed();
        render();
        document.getElementById(radio.id)?.focus();
      });
    }
    if (data.classification === "open") {
      const methods = group(
        section,
        "Ways to access the data (choose at least one)",
      );
      for (const [kind, label] of Object.entries(methodNames)) {
        const selectedMethod = data.methods.find((m) => m.kind === kind);
        const wrapper = node("label", undefined, methods);
        const methodCheckbox = node("input", undefined, wrapper);
        methodCheckbox.type = "checkbox";
        methodCheckbox.id = dataset + "-" + kind;
        methodCheckbox.checked = Boolean(selectedMethod);
        wrapper.append(label);
        methodCheckbox.addEventListener("change", () => {
          if (methodCheckbox.checked) data.methods.push({ kind });
          else data.methods = data.methods.filter((m) => m.kind !== kind);
          changed();
          render();
          document.getElementById(methodCheckbox.id)?.focus();
        });
        if (selectedMethod) {
          const card = node("div", undefined, methods);
          card.className = "method-card";
          selectedMethod.monitoring ??= {
            enabled: false,
            execution_profile: monitoringProfiles[0],
            terms_url: "",
            terms_reviewed_on: "",
            terms_confirmed: false,
            county_permission: {
              reply: "none",
              scope: "details-and-count",
              received_on: "",
              reference: "",
              evidence_url: "",
            },
          };
          const base = `access.${dataset}.methods.${data.methods.indexOf(selectedMethod)}`;
          input(
            card,
            "Official data link",
            selectedMethod,
            "url",
            "url",
            base + ".url",
            true,
          );
          const grid = node("div", undefined, card);
          grid.className = "grid method-meta";
          input(
            grid,
            "Link verified on",
            selectedMethod,
            "evidence_date",
            "date",
            base + ".evidence_date",
            true,
          );
          input(
            grid,
            "What this link covers",
            selectedMethod,
            "scope",
            "text",
            base + ".scope",
            true,
          );
          help(
            card,
            "For example: county parcel boundaries, or a statewide copy. Use the date you checked this link.",
          );
          if (kind === "direct_rest" || kind === "direct_download") {
            const monitor = selectedMethod.monitoring;
            const checks = node("details", undefined, card);
            checks.className = "monitoring-options";
            node("summary", "Regular Watchtower checks", checks);
            help(
              checks,
              kind === "direct_rest"
                ? "This check reads the service description and one record count. It does not read parcel records."
                : "This check reads the file's update headers only. It does not download the file.",
            );
            checkbox(
              checks,
              "Include this source in regular checks",
              monitor.enabled,
              base + ".monitoring.enabled",
              (value) => {
                monitor.enabled = value;
                if (
                  value &&
                  !monitoringProfiles.includes(monitor.execution_profile)
                )
                  monitor.execution_profile = monitoringProfiles[0];
                changed();
                render();
                const target = document.getElementById(
                  controlId(base + ".monitoring.enabled"),
                );
                if (target) {
                  target.closest("details").open = true;
                  target.focus();
                }
              },
            );
            if (monitor.enabled) {
              if (
                monitoringProfiles.length > 1 ||
                !monitoringProfiles.includes(monitor.execution_profile)
              )
                select(
                  checks,
                  "Check on this worker",
                  Object.fromEntries(
                    monitoringProfiles.map((profile) => [
                      profile,
                      profile === "cloud" ? "Cloud worker" : "Local worker",
                    ]),
                  ),
                  monitor.execution_profile || "cloud",
                  (value) => {
                    monitor.execution_profile = value;
                    changed();
                  },
                  base + ".monitoring.execution_profile",
                );
              else help(checks, "Uses the regular Watchtower schedule.");
              const terms = node("fieldset", undefined, checks);
              node("legend", "Provider terms review", terms);
              help(
                terms,
                "Record the public terms that allow this limited, recurring check.",
              );
              input(
                terms,
                "Terms or policy link",
                monitor,
                "terms_url",
                "url",
                base + ".monitoring.terms_url",
                true,
              );
              input(
                terms,
                "Reviewed on",
                monitor,
                "terms_reviewed_on",
                "date",
                base + ".monitoring.terms_reviewed_on",
                true,
              );
              checkbox(
                terms,
                kind === "direct_rest"
                  ? "I confirmed these terms allow regular service details and record-count checks"
                  : "I confirmed these terms allow regular file update checks",
                monitor.terms_confirmed,
                base + ".monitoring.terms_confirmed",
                (value) => {
                  monitor.terms_confirmed = value;
                  changed();
                },
              );
              const permission = (monitor.county_permission ??= {
                reply: "none",
                scope: "details-and-count",
                received_on: "",
                reference: "",
                evidence_url: "",
              });
              const consent = node("fieldset", undefined, checks);
              node("legend", "County permission", consent);
              help(
                consent,
                "The county must agree to this source check. The response reference stays private.",
              );
              checkbox(
                consent,
                "The county explicitly approved this limited check",
                permission.reply === "permitted",
                base + ".monitoring.county_permission.reply",
                (value) => {
                  permission.reply = value ? "permitted" : "none";
                  changed();
                },
              );
              help(
                consent,
                kind === "direct_rest"
                  ? "Approved scope: service details and one record count."
                  : "Approved scope: file update details only; no file download.",
              );
              input(
                consent,
                "Permission received on",
                permission,
                "received_on",
                "date",
                base + ".monitoring.county_permission.received_on",
                true,
              );
              input(
                consent,
                "Private reference to the response",
                permission,
                "reference",
                "text",
                base + ".monitoring.county_permission.reference",
                true,
              );
              input(
                consent,
                "Public confirmation link, if available",
                permission,
                "evidence_url",
                "url",
                base + ".monitoring.county_permission.evidence_url",
              );
            }
          }
          if (kind === "other")
            input(
              card,
              "Describe this access method",
              selectedMethod,
              "description",
              "text",
              base + ".description",
              true,
            );
        }
      }
    }
    input(
      section,
      "Public note about county data access",
      data,
      "county_direct_note",
      "textarea",
      `access.${dataset}.county_direct_note`,
    );
    const restrictions = (data.restrictions ??= { status: "unreviewed" });
    select(
      section,
      "Use restrictions",
      {
        unreviewed: "Not yet reviewed",
        reviewed_none: "No restrictions recorded — confirm provider terms",
        restricted: "Restrictions apply",
      },
      restrictions.status,
      (value) => {
        restrictions.status = value;
        if (value !== "reviewed_none")
          for (const method of data.methods)
            if (method.monitoring) method.monitoring.enabled = false;
        changed();
        render();
        document
          .getElementById(controlId(`access.${dataset}.restrictions.status`))
          ?.focus();
      },
      `access.${dataset}.restrictions.status`,
    );
    if (restrictions.status !== "unreviewed")
      input(
        section,
        "Restrictions reviewed on",
        restrictions,
        "reviewed_on",
        "date",
        `access.${dataset}.restrictions.reviewed_on`,
      );
    if (restrictions.status === "restricted") {
      input(
        section,
        "Public restriction details",
        restrictions,
        "text",
        "textarea",
        `access.${dataset}.restrictions.text`,
        true,
      );
      input(
        section,
        "Official restrictions link",
        restrictions,
        "url",
        "url",
        `access.${dataset}.restrictions.url`,
      );
    }
  }
}
function eventTime(parent, title, event, key, base) {
  const id = event.id + ":" + key,
    existing = typeof event[key] === "string" ? event[key] : "";
  if (!timeInputs.has(id))
    timeInputs.set(id, {
      date: existing.slice(0, 10),
      time: existing.slice(11, 16),
      offset: existing.slice(-6),
    });
  const values = timeInputs.get(id),
    group = node("div", undefined, parent);
  group.className = "grid method-meta";
  const date = input(
    group,
    title + " date (Central)",
    values,
    "date",
    "date",
    base + ".date",
  );
  const time = input(
    group,
    title + " time (Central)",
    values,
    "time",
    "time",
    base + ".time",
  );
  const offset = select(
    parent,
    "This Central time occurs twice — choose which one",
    {
      "": "Choose an occurrence",
      "-05:00": "First occurrence (daylight time)",
      "-06:00": "Second occurrence (standard time)",
    },
    values.offset,
    (value) => {
      values.offset = value;
      update();
    },
    base + ".offset",
  );
  function update(markChanged = true) {
    time.setCustomValidity("");
    offset.closest("label").hidden = true;
    if (!date.value && !time.value) {
      delete event[key];
      if (markChanged) changed();
      return;
    }
    const local = date.value + "T" + time.value;
    const candidates = ["-05:00", "-06:00"].filter((suffix) => {
      const instant = new Date(local + suffix);
      return (
        !Number.isNaN(instant.valueOf()) &&
        chicago.format(instant) === local.replace("T", " ")
      );
    });
    offset.closest("label").hidden = candidates.length !== 2;
    const suffix = candidates.length === 1 ? candidates[0] : values.offset;
    if (!candidates.includes(suffix)) {
      time.setCustomValidity(
        "Enter a valid Central date and time. If this time occurs twice, choose its first or second occurrence.",
      );
      return;
    }
    event[key] = local + suffix;
    if (markChanged) changed();
  }
  date.addEventListener("input", () => update());
  time.addEventListener("input", () => update());
  timeChecks.set(id, () => update(false));
  update(false);
}
function correspondence() {
  const section = group(fields, "Private correspondence");
  section.classList.add("private");
  help(
    section,
    "These records stay private. Logging an email does not send email. Dates and times use Central time.",
  );
  draft.correspondence.forEach((event, index) => {
    const base = `correspondence.${index}`;
    const card = node("div", undefined, section);
    card.className = "email-card";
    node("h4", event.subject || "Email record", card);
    const names = { "": "No linked contact" };
    for (const c of draft.contacts)
      if (c.id && (!c.removed || c.id === event.contact_id))
        names[c.id] = c.name || c.department || "Contact";
    select(
      card,
      "Linked contact",
      names,
      event.contact_id || "",
      (id) => {
        event.contact_id = id;
        if (id && !event.recipient) event.recipient = names[id];
        changed();
        render();
        document.getElementById(controlId(base + ".contact_id"))?.focus();
      },
      base + ".contact_id",
    );
    input(
      card,
      "Recipient at the time",
      event,
      "recipient",
      "text",
      base + ".recipient",
    );
    input(card, "Subject", event, "subject", "text", base + ".subject");
    eventTime(card, "Sent", event, "sent_at", base + ".sent_at");
    eventTime(card, "Reply", event, "reply_at", base + ".reply_at");
    input(card, "Private notes", event, "notes", "textarea", base + ".notes");
    event.attachment_ids ??= [];
    attachmentField(
      card,
      "Private email PDF",
      event.attachment_ids,
      "correspondence",
      event.id,
      (id) => event.attachment_ids.push(id),
      (id) => {
        event.attachment_ids = event.attachment_ids.filter((v) => v !== id);
      },
    );
  });
  button(section, "Log an email", () => {
    draft.correspondence.push({ id: crypto.randomUUID() });
    changed();
    render();
    reveal(
      document.getElementById(
        controlId(`correspondence.${draft.correspondence.length - 1}.subject`),
      ),
    );
  });
}
function attachmentField(parent, title, ids, kind, eventId, attach, detach) {
  const area = group(parent, title);
  area.classList.add("private");
  help(
    area,
    "PDF only, up to 20 MB. Upload, then Save changes to link the file to this record. It stays private and must pass a file check before download. Removing a link does not delete the stored PDF.",
  );
  const countyAtRender = selected;
  for (const id of ids) {
    const row = node("div", "Checking private file…", area);
    row.className = "file-status";
    const url = path() + "/attachments/" + encodeURIComponent(id);
    const show = (meta) => {
      if (countyAtRender !== selected || !row.isConnected) return;
      row.replaceChildren();
      const linked = !attachmentCache.has(id);
      if (meta.status === "clean" && linked)
        node("a", "Download " + meta.filename, row).href = url;
      else
        node(
          "p",
          (meta.filename || "Private file") +
            " · " +
            ({
              pending: linked
                ? "Waiting for file check"
                : "Save changes to link this file, then retry its check if needed",
              rejected: "File could not be used",
              clean: "Ready — Save changes to link this file",
            }[meta.status] || "File status unavailable"),
          row,
        );
      if (scannerEnabled && linked && meta.status === "pending")
        button(row, "Retry file check", async () => {
          lock(true);
          row.setAttribute("aria-busy", "true");
          try {
            const result = await request(url + "/scan", {});
            if ([200, 202].includes(result.code)) show(result);
            else help(row, "The file check could not finish. Try again later.");
          } catch {
            help(row, "The file check could not finish. Try again later.");
          } finally {
            row.removeAttribute("aria-busy");
            lock(false);
          }
        });
      button(row, "Remove from this record", () => {
        detach(id);
        changed();
        render();
        document.getElementById("picker-" + kind + (eventId || ""))?.focus();
      });
      lock(busy);
    };
    if (attachmentCache.has(id))
      queueMicrotask(() => show(attachmentCache.get(id)));
    else
      request(url + "/status")
        .then(show)
        .catch(() => show({}));
  }
  const key = kind + (eventId || "");
  if (!filePickers.has(key)) {
    const picker = document.createElement("input");
    picker.type = "file";
    picker.accept = ".pdf,application/pdf";
    picker.id = "picker-" + key;
    picker.addEventListener("change", () => {
      picker.dataset.uploadId = crypto.randomUUID().replaceAll("-", "");
      changed();
    });
    filePickers.set(key, picker);
  }
  const picker = filePickers.get(key);
  node("label", "Select a private PDF", area).append(picker);
  button(area, "Clear selected file", () => {
    picker.value = "";
    picker.focus();
    changed();
  });
  const feedback = node("p", undefined, area);
  feedback.className = "file-feedback";
  feedback.setAttribute("role", "status");
  button(area, "Upload PDF", async () => {
    const file = picker.files[0];
    if (!file || file.size > 20 * 1024 * 1024) {
      feedback.textContent = file
        ? "Choose a PDF no larger than 20 MB."
        : "Select a PDF first.";
      picker.focus();
      return;
    }
    const query = new URLSearchParams({ kind });
    if (eventId) query.set("event", eventId);
    lock(true);
    feedback.textContent = "Uploading PDF and checking the file…";
    try {
      const response = await fetch(path() + "/attachments?" + query, {
        method: "POST",
        headers: {
          "Content-Type": "application/pdf",
          "X-Watchtower-CSRF": csrf,
          "X-Watchtower-Filename": file.name,
          "X-Watchtower-Upload-ID": picker.dataset.uploadId,
        },
        body: file,
      });
      const result = await response.json();
      if (!response.ok) {
        feedback.textContent =
          result.status === "invalid_attachment"
            ? "Choose a valid PDF with a filename containing letters, numbers, spaces, or basic punctuation."
            : "Upload could not be confirmed. Retry this file.";
        return;
      }
      attachmentCache.set(result.id, result);
      attach(result.id);
      picker.value = "";
      changed();
      render();
      saveMessage.textContent =
        "Private PDF uploaded. Save changes to link it to " +
        countyName() +
        ".";
    } catch {
      feedback.textContent = "Upload could not be confirmed. Retry this file.";
    } finally {
      lock(false);
    }
  });
}
function render() {
  const focus = document.activeElement?.id,
    top = scroller.scrollTop;
  const open = [...fields.querySelectorAll("details[open]")].map((d) => d.id);
  fields.replaceChildren();
  draft.contacts ??= [];
  draft.access ??= {};
  draft.policy ??= {};
  draft.correspondence ??= [];
  contacts();
  access();
  const policy = group(fields, "Policy");
  help(
    policy,
    "Only the policy text and official link appear publicly. An uploaded policy PDF stays private.",
  );
  input(
    policy,
    "Public policy text",
    draft.policy,
    "text",
    "textarea",
    "policy.text",
  );
  input(
    policy,
    "Official policy link",
    draft.policy,
    "url",
    "url",
    "policy.url",
  );
  attachmentField(
    policy,
    "Private policy PDF",
    draft.policy.attachment_id ? [draft.policy.attachment_id] : [],
    "policy",
    null,
    (id) => {
      draft.policy.attachment_id = id;
    },
    () => {
      delete draft.policy.attachment_id;
    },
  );
  correspondence();
  open.forEach((id) => {
    const d = document.getElementById(id);
    if (d) d.open = true;
  });
  if (focus) document.getElementById(focus)?.focus({ preventScroll: true });
  scroller.scrollTop = top;
  lock(busy);
  renderReview();
}
// Only known editable values enter the review. Private IDs, CRM references and
// unrelated stored fields never appear in the public change preview or downloads.
function reviewRows(record) {
  const rows = new Map();
  const add = (key, label, value, privateValue = false, token = value) =>
    rows.set(key, {
      label,
      value: String(value ?? ""),
      private: privateValue,
      token: JSON.stringify(token ?? ""),
    });
  (record.contacts || []).forEach((c, i) => {
    if (!c.removed)
      for (const key of [
        "name",
        "role",
        "department",
        "phone",
        "email",
        "website",
        "source_url",
        "verified_on",
      ])
        add(
          `contact:${c.id || i}:${key}`,
          `Contact ${i + 1} · ${{ name: "name", role: "role", department: "department", phone: "phone", email: "email", website: "website", source_url: "source link", verified_on: "verification date" }[key]}`,
          c[key],
        );
  });
  for (const [key, title] of Object.entries(datasetNames)) {
    const d = record.access?.[key] || {};
    add(
      key + ":classification",
      title + " · availability",
      accessNames[d.classification] || accessNames.unknown,
    );
    add(key + ":note", title + " · public note", d.county_direct_note);
    if (d.classification === "open")
      for (const m of d.methods || [])
        for (const field of ["url", "scope", "evidence_date", "description"])
          add(
            key + ":" + m.kind + ":" + field,
            title +
              " · " +
              methodNames[m.kind] +
              " · " +
              {
                url: "data link",
                scope: "coverage",
                evidence_date: "link verified on",
                description: "description",
              }[field],
            m[field],
          );
    if (d.classification === "open")
      for (const m of d.methods || []) {
        const review = m.monitoring || {};
        add(
          key + ":" + m.kind + ":monitoring:enabled",
          title + " · " + methodNames[m.kind] + " · regular checks",
          review.enabled ? "Included" : "Not included",
          true,
        );
        if (review.enabled) {
          const permission = review.county_permission || {};
          for (const [field, label, value] of [
            ["execution_profile", "worker", review.execution_profile],
            ["terms_url", "provider terms link", review.terms_url],
            [
              "terms_reviewed_on",
              "terms reviewed on",
              review.terms_reviewed_on,
            ],
            [
              "terms_confirmed",
              "terms allow regular checks",
              review.terms_confirmed ? "Confirmed" : "Not confirmed",
            ],
            [
              "permission_reply",
              "county permission",
              permission.reply === "permitted" ? "Confirmed" : "Not confirmed",
            ],
            [
              "permission_received_on",
              "permission received on",
              permission.received_on,
            ],
            [
              "permission_reference",
              "private permission reference",
              permission.reference,
            ],
            ["permission_evidence", "permission link", permission.evidence_url],
          ])
            add(
              key + ":" + m.kind + ":monitoring:" + field,
              title + " · " + methodNames[m.kind] + " · " + label,
              value,
              true,
            );
        }
      }
    const r = d.restrictions || {};
    add(
      key + ":restriction",
      title + " · restriction review",
      {
        unreviewed: "Not yet reviewed",
        reviewed_none: "No restrictions recorded",
        restricted: "Restrictions apply",
      }[r.status] || "Not yet reviewed",
    );
    for (const field of r.status === "restricted"
      ? ["text", "url", "reviewed_on"]
      : r.status === "reviewed_none"
        ? ["reviewed_on"]
        : [])
      add(
        key + ":restriction:" + field,
        title + " · restrictions · " + field.replaceAll("_", " "),
        r[field],
      );
  }
  add("policy:text", "Public policy text", record.policy?.text);
  add("policy:url", "Official policy link", record.policy?.url);
  add(
    "policy:file",
    "Private policy PDF",
    record.policy?.attachment_id ? "PDF linked" : "No PDF",
    true,
    record.policy?.attachment_id,
  );
  (record.correspondence || []).forEach((e, i) => {
    for (const key of ["recipient", "subject", "sent_at", "reply_at", "notes"])
      add(
        `email:${e.id || i}:${key}`,
        `Private email ${i + 1} · ${key.replaceAll("_", " ")}`,
        e[key],
        true,
      );
    add(
      `email:${e.id || i}:files`,
      `Private email ${i + 1} · files`,
      `${(e.attachment_ids || []).length} PDF(s)`,
      true,
      e.attachment_ids || [],
    );
    add(
      `email:${e.id || i}:contact`,
      `Private email ${i + 1} · linked contact`,
      e.contact_id ? "Contact linked" : "No linked contact",
      true,
      e.contact_id,
    );
  });
  return rows;
}
function changesBetween(before, after) {
  const a = reviewRows(before),
    b = reviewRows(after),
    changes = [];
  for (const key of new Set([...a.keys(), ...b.keys()])) {
    const old = a.get(key),
      next = b.get(key);
    if ((old?.token || '""') !== (next?.token || '""'))
      changes.push({
        ...(next || old),
        before: old?.value || "Empty",
        after: next?.value || "Removed",
      });
  }
  return changes;
}
function renderReview() {
  const container = document.querySelector("#change-summary");
  container.replaceChildren();
  if (!draft || !baseline) return;
  const changes = changesBetween(baseline, draft);
  if (!changes.length) {
    node(
      "p",
      dirty
        ? "No displayed public fields changed. Review any private changes or selected files before saving."
        : "No unsaved changes.",
      container,
    );
    return;
  }
  for (const isPrivate of [false, true]) {
    const rows = changes.filter((c) => c.private === isPrivate);
    if (!rows.length) continue;
    node(
      "h4",
      isPrivate
        ? "Private changes — stay private"
        : "Public changes — published when saved",
      container,
    );
    for (const c of rows) {
      const row = node("div", undefined, container);
      row.className = "change-item" + (isPrivate ? " private" : "");
      node("strong", c.label, row);
      node("p", "Before: " + c.before, row);
      node("p", "After: " + c.after, row);
    }
  }
}
function path() {
  return "/api/counties/" + encodeURIComponent(selected);
}
function lock(value) {
  busy = value;
  countyList.disabled = value || !counties.length;
  apply.disabled = value;
  retry.disabled = value;
  discard.disabled = value;
  document.querySelector("#review").disabled = value;
  form.setAttribute("aria-busy", String(value));
  apply.textContent = value
    ? "Please wait…"
    : pendingRequest
      ? "Retry save"
      : "Save changes";
  for (const c of fields.querySelectorAll("input,select,button,textarea"))
    c.disabled = value || pendingRequest !== null;
}
function list() {
  const term = search.value.trim().toLocaleLowerCase();
  countyList.replaceChildren();
  let count = 0;
  node("option", "Choose a county…", countyList).value = "";
  for (const c of counties) {
    if (
      ![c.name, ...(c.search_terms || [])].some((value) =>
        value.toLocaleLowerCase().includes(term),
      )
    )
      continue;
    node(
      "option",
      c.name +
        (c.contact_count === undefined
          ? ""
          : ` — ${c.contact_count} ${c.contact_count === 1 ? "contact" : "contacts"}`),
      countyList,
    ).value = c.slug;
    count++;
  }
  countyList.value = selected;
  document.querySelector("#county-results").textContent = count
    ? `${count} ${count === 1 ? "county" : "counties"} shown`
    : "No counties match. Clear search to see all counties.";
}
async function refreshDirectory() {
  const directory = await request("/api/counties");
  if (directory.code !== 200)
    throw new Error("The county list could not refresh.");
  csrf = directory.csrf_token;
  scannerEnabled = directory.scanner_enabled === true;
  monitoringProfiles =
    Array.isArray(directory.monitoring_profiles) &&
    directory.monitoring_profiles.length
      ? directory.monitoring_profiles
      : ["cloud"];
  counties = directory.counties;
  list();
  countyList.disabled = busy;
  return directory;
}
function publicationState(result) {
  const needsRetry =
    result.status === "pending" || result.monitoring_status === "pending";
  retry.hidden = !needsRetry;
  retry.textContent =
    result.monitoring_status === "pending"
      ? "Retry updates"
      : "Retry publication";
  clearTimeout(retryTimer);
  if (needsRetry) retryTimer = setTimeout(() => retryPublication(true), 3000);
}
async function loadCounty(slug) {
  clearTimeout(retryTimer);
  lock(true);
  status("Loading county information…");
  try {
    const detail = await request("/api/counties/" + encodeURIComponent(slug));
    if (detail.code !== 200)
      throw new Error(
        "County information is temporarily unavailable. Try selecting the county again.",
      );
    selected = slug;
    attachmentCache.clear();
    filePickers.clear();
    timeInputs.clear();
    timeChecks.clear();
    lastRemoved = null;
    draft = detail.draft;
    revision = detail.revision;
    pendingRequest = null;
    dirty = false;
    baseline = structuredClone(draft);
    list();
    document.querySelector("#county-title").textContent =
      detail.county.name + " County";
    const link = document.querySelector("#public-page");
    link.href =
      "https://gis-watchtower.clear-parcel.com/county?slug=" +
      encodeURIComponent(slug);
    link.hidden = false;
    document.querySelector("#sections").hidden = false;
    form.hidden = false;
    errorSummary.hidden = true;
    document.querySelector("#conflict").hidden = true;
    document.querySelector("#change-review").open = false;
    document.querySelector("#change-review").hidden = true;
    render();
    scroller.scrollTop = 0;
    try {
      const result = await request(path() + "/publication");
      status(
        resultLabel(result),
        result.status === "unsaved" ? "No unsaved edits." : resultLabel(result),
      );
      publicationState(result);
    } catch {
      status(
        "County record loaded. Publication status could not be checked. Your record is available to edit.",
      );
      retry.hidden = false;
    }
    document.querySelector("#county-title").focus();
  } catch (error) {
    status(error.message || "County information is temporarily unavailable.");
    list();
  } finally {
    lock(false);
  }
}
async function retryPublication(automatic = false) {
  if (busy || pendingRequest || (automatic && dirty)) return;
  lock(true);
  saveMessage.textContent = "Checking pending updates…";
  try {
    const result = await request(path() + "/publication", {});
    status(resultLabel(result));
    retry.hidden =
      result.status !== "pending" && result.monitoring_status !== "pending";
    if (
      !automatic &&
      (result.status === "pending" || result.monitoring_status === "pending")
    )
      publicationState(result);
  } catch (error) {
    status(
      error.message || "Publication status is unavailable. Try again later.",
    );
    retry.hidden = false;
  } finally {
    lock(false);
  }
}
async function showConflict() {
  const box = document.querySelector("#conflict");
  box.replaceChildren();
  box.hidden = false;
  node("h3", "This record changed while you were editing", box);
  node(
    "p",
    "Your edits are still in the form. Compare them with the latest saved record, and download your edits before reloading if you need to keep a copy. The download includes private information.",
    box,
  );
  button(box, "Download my edits (private text)", () => {
    const text =
      countyName() +
      "\nPrivate editing copy\n\n" +
      [...reviewRows(draft).values()]
        .map(
          (r) => `${r.private ? "Private" : "Public"} · ${r.label}: ${r.value}`,
        )
        .join("\n");
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const link = node("a", undefined, box);
    link.href = url;
    link.download = "county-editing-copy.txt";
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  button(box, "Load latest saved record", () => {
    if (
      confirm(
        "Load the latest record and discard your unsaved edits? Download your editing copy first if you need it.",
      )
    )
      loadCounty(selected);
  });
  const comparison = node("details", undefined, box);
  node("summary", "Compare my draft with the latest saved record", comparison);
  button(comparison, "Load comparison", async () => {
    try {
      const latest = await request(path());
      if (latest.code !== 200) throw new Error();
      const rows = changesBetween(draft, latest.draft);
      comparison.replaceChildren();
      node("summary", "My draft → latest saved record", comparison);
      for (const c of rows) {
        const row = node("div", undefined, comparison);
        row.className = "change-item" + (c.private ? " private" : "");
        node("strong", (c.private ? "Private · " : "Public · ") + c.label, row);
        node("p", "My draft: " + c.before, row);
        node("p", "Latest saved: " + c.after, row);
      }
      if (!rows.length)
        node("p", "No displayed field differences.", comparison);
    } catch {
      help(
        comparison,
        "The latest record could not be loaded. Your edits are still here.",
      );
    }
  });
  box.scrollIntoView({ block: "start" });
}
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || !draft) return;
  if (!pendingRequest && !validate()) {
    saveMessage.textContent =
      "Please correct the highlighted fields before saving.";
    return;
  }
  if ([...filePickers.values()].some((p) => p.files.length)) {
    status(
      "A selected PDF has not been uploaded. Upload it or clear the file selection before saving.",
    );
    return;
  }
  pendingRequest ??= {
    expected_revision: revision,
    request_id: crypto.randomUUID(),
    draft: structuredClone(draft),
  };
  lock(true);
  status("Saving changes…");
  try {
    const result = await request(path(), pendingRequest);
    status(resultLabel(result));
    if ([200, 202].includes(result.code)) {
      revision = result.revision;
      dirty = false;
      pendingRequest = null;
      baseline = structuredClone(draft);
      lastRemoved = null;
      if (attachmentCache.size) {
        attachmentCache.clear();
        render();
      } else renderReview();
      publicationState(result);
      try {
        await refreshDirectory();
      } catch {
        document.querySelector("#county-results").textContent =
          "Changes saved. The county list could not refresh. Use Refresh county list.";
        document.querySelector(".county-search").open = true;
      }
    } else if (result.code < 500) {
      pendingRequest = null;
      if (result.monitoring_status === "pending") publicationState(result);
      if (result.status === "revision_conflict") await showConflict();
      else if (result.status === "invalid_draft")
        showErrors(
          result.errors || [
            {
              message:
                "Check the record, including private dates and file links. Your edits have been kept.",
            },
          ],
        );
    }
  } catch (error) {
    status(
      error.message?.startsWith("Your session")
        ? error.message
        : "The save could not be confirmed. Use Retry save to resend the same request.",
    );
  } finally {
    lock(false);
  }
});
discard.addEventListener("click", () => {
  if (
    !(dirty || pendingRequest) ||
    confirm(
      "Discard unsaved changes for " +
        countyName() +
        " and reload the saved record?",
    )
  )
    loadCounty(selected);
});
retry.addEventListener("click", () => retryPublication());
search.addEventListener("input", list);
document.querySelector("#clear-search").addEventListener("click", () => {
  search.value = "";
  list();
  search.focus();
});
document
  .querySelector("#refresh-directory")
  .addEventListener("click", async () => {
    try {
      await refreshDirectory();
    } catch (error) {
      document.querySelector("#county-results").textContent =
        error.message ||
        "The county list is temporarily unavailable. Try again.";
    }
  });
document.querySelector("#review").addEventListener("click", () => {
  renderReview();
  document.querySelector("#change-review").hidden = false;
  document.querySelector("#change-review").open = true;
  document.querySelector("#change-review summary").focus();
});
countyList.addEventListener("change", () => {
  if (
    countyList.value &&
    (!(dirty || pendingRequest) ||
      confirm("Leave this county and discard unsaved changes?"))
  )
    loadCounty(countyList.value);
  else list();
});
for (const link of document.querySelectorAll("#sections a"))
  link.addEventListener("click", (event) => {
    event.preventDefault();
    for (const a of document.querySelectorAll("#sections a"))
      a.removeAttribute("aria-current");
    link.setAttribute("aria-current", "location");
    document
      .querySelector(link.getAttribute("href"))
      ?.scrollIntoView({ block: "start" });
  });
window.addEventListener("beforeunload", (event) => {
  if (dirty || pendingRequest) event.preventDefault();
});
const compact = matchMedia("(max-width:48rem)");
function sizeCountyList() {
  countyList.size = compact.matches ? 1 : 12;
  document.querySelector(".county-search").open = !compact.matches;
}
compact.addEventListener("change", sizeCountyList);
sizeCountyList();
refreshDirectory().catch((error) => {
  document.querySelector(".county-search").open = true;
  document.querySelector("#county-results").textContent =
    error.message ||
    "The county directory is temporarily unavailable. Use Refresh county list to retry.";
});
