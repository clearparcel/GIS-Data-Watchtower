"""A bounded three-page public county profile, composed from summary fields only."""
from __future__ import annotations
import io
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode
from xml.sax.saxutils import escape, quoteattr
from .public_values import safe_public_url
from .gac_standards import load_gac_standard

_TEMPLATE_VERSION = 3
_MAX_PDF_BYTES = 4 * 1024 * 1024


def _plain(value, limit=2000):
    if value is None:
        return ''
    return re.sub(r'[\x00-\x1f\x7f\ud800-\udfff]', ' ', str(value))[:limit]


def _number(value):
    return value if type(value) in (float, int) and math.isfinite(value) and value >= 0 else None


def _summary(snapshot):
    directory = snapshot.get('county_directory') or {}
    profile = snapshot.get('parcel_source_profile') or {}
    identity = profile.get('county') or directory.get('county') or {}
    contacts = directory.get('contacts', snapshot.get('contacts') or [])
    result = {'county': _plain(snapshot.get('county'), 100),
              'url': 'https://gis-watchtower.clear-parcel.com/county?' + urlencode({'slug': identity.get('slug') or ''}),
              'captured': _plain(snapshot.get('snapshot_created_central') or snapshot.get('snapshot_created_utc'), 40),
              'revision': directory.get('public_revision'),
              'contacts': [{k: _plain(p.get(k)) for k in ('name', 'role', 'title', 'department', 'phone', 'email', 'website', 'source_url')} for p in contacts[:3]],
              'contact_count': len(contacts), 'access': {}, 'policy': {}, 'gac': {}}
    for k in ('text', 'url'):
        result['policy'][k] = _plain((directory.get('policy') or {}).get(k))
    for key in ('parcel_polygons', 'road_centerlines', 'address_points'):
        item = (directory.get('access') or {}).get(key) or {}
        restriction = item.get('restrictions') or {}
        result['access'][key] = {'classification': item.get('classification', 'unknown'),
            'note': _plain(item.get('county_direct_note')), 'restrictions': {k: _plain(restriction.get(k)) for k in ('status', 'text', 'url')},
            'methods': [{k: _plain(m.get(k)) for k in ('kind', 'url', 'scope', 'evidence_date', 'description')} for m in (item.get('methods') or [])[:4]]}
    monitoring = profile.get('monitoring') or {}
    result['monitoring'] = {'path': _plain(snapshot.get('monitoring_path_label')),
        'direct_count': len(snapshot.get('direct_sources') or []),
        'last_check': _plain(monitoring.get('last_checked_at')), 'status': _plain(snapshot.get('status'))}
    for key in ('parcel', 'road', 'address'):
        g = (snapshot.get('gac') or {}).get(key) or (snapshot.get('mngac') if key == 'parcel' else {}) or {}
        county = g.get('county') or {}
        fields = county.get('fields') or {}
        if not isinstance(fields, dict):
            fields = {}
        spec = load_gac_standard(key)
        gaps = []
        for f in spec['fields']:
            v = fields.get(f['field']) or {}
            pct = _number(v.get('percent'))
            if f['inclusion'] == 'Mandatory' and v.get('population_scanned') is not False and pct is not None and pct < 100:
                gaps.append({'label': f['label'], 'percent': pct})
        names = [v.get('present_in_source_schema') for v in fields.values()]
        result['gac'][key] = {k: _number(county.get(k)) for k in ('record_count', 'field_count', 'scanned_field_count', 'mandatory_field_count', 'mandatory_fields_full', 'mandatory_population_percent', 'field_population_percent')}
        result['gac'][key].update({'present': sum(v is True for v in names) if names and all(type(v) is bool for v in names) else None,
            'gaps': sorted(gaps, key=lambda g: g['percent'])[:3], 'standard_url': spec['standard']['source_url'], 'version': spec['standard']['version']})
    return result


@lru_cache(maxsize=16)
def _render(template, payload):
    import reportlab
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from .county_profile_panel import profile_time
    data = json.loads(payload)
    fonts = Path(reportlab.__file__).with_name('fonts')
    for name, filename in (('WatchtowerVera', 'Vera.ttf'), ('WatchtowerVeraBold', 'VeraBd.ttf')):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=(612, 792))
    c.setTitle(data['county'] + ' County GIS summary')
    c.setAuthor('GIS Data Watchtower')
    navy, green, muted, line, pale, gray = '#102C3D', '#087F72', '#536874', '#D9E4E8', '#F1F7F6', '#F4F6F8'

    def text(value, x, y, size=10, color=navy, bold=False):
        c.setFillColor(HexColor(color)); c.setFont('WatchtowerVeraBold' if bold else 'WatchtowerVera', size)
        c.drawString(x, y, _plain(value))

    def para(value, x, top, width, height=40, size=10, color=navy, url=None):
        # Fit editable text into its reserved area and visibly mark any omission.
        raw = _plain(value)
        style = ParagraphStyle('summary', fontName='WatchtowerVera', fontSize=size, leading=size * 1.4, textColor=HexColor(color))
        def make(s):
            markup = escape(s)
            if safe := safe_public_url(url):
                markup = f'<link href={quoteattr(safe)} color="{green}">{markup}</link>'
            p = Paragraph(markup, style); _, h = p.wrap(width, 700)
            return p, h
        p, h = make(raw)
        if h > height:
            lo, hi = 0, len(raw)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if make(raw[:mid] + '... (full text online)')[1] <= height: lo = mid
                else: hi = mid - 1
            p, h = make(raw[:lo] + '... (full text online)')
        p.drawOn(c, x, top - h)

    def panel(y, height, fill=gray):
        c.setFillColor(HexColor(fill)); c.setStrokeColor(HexColor(line)); c.setLineWidth(.6)
        c.roundRect(44, y, 524, height, 10, fill=1, stroke=1)

    def link(label, url, x, top, width=480):
        para(label, x, top, width, 20, 9, green, url)

    def frame(page, subtitle):
        c.setFillColor(HexColor(green)); c.rect(0, 784, 612, 8, fill=1, stroke=0)
        c.drawImage(ImageReader(str(Path(__file__).with_name('watchtower-logo.webp'))), 44, 726, 44, 44, mask='auto')
        text('GIS Data Watchtower', 100, 742, 17, bold=True)
        c.setStrokeColor(HexColor(line)); c.line(44, 715, 568, 715)
        para(data['county'] + ' County', 44, 700, 524, 48, 28)
        text(subtitle, 44, 651, 11, muted)
        c.line(44, 48, 568, 48)
        text('Public snapshot: ' + (profile_time(data['captured']) if data['captured'] else 'Date unavailable'), 44, 31, 8, muted)
        text(f'{page} / 3', 542, 31, 8, muted)

    frame(1, 'GIS contacts and data access')
    text('COUNTY GIS CONTACTS', 44, 616, 9, green, True)
    panel(486, 113, pale)
    if not data['contacts']: text('No contact currently published.', 60, 568, 11, muted)
    for i, p in enumerate(data['contacts']):
        y = 582 - i * 28
        para(' | '.join(filter(None, (p['name'], p['role'] or p['title'], p['department']))), 60, y, 492, 15, 10)
        para(' | '.join(filter(None, (p['phone'], p['email']))), 60, y - 14, 492, 13, 9, muted)
    link('County GIS contacts and website online', data['url'], 60, 500)
    if data['contact_count'] > 3: text(f"{data['contact_count'] - 3} additional contacts online", 335, 490, 8, muted)
    text('DATA ACCESS', 44, 461, 9, green, True)
    for key, title, y, height in (('parcel_polygons', 'Parcel Polygons', 288, 154), ('road_centerlines', 'Road Centerlines', 193, 78), ('address_points', 'Address Points', 98, 78)):
        item = data['access'][key]; top = y + height
        panel(y, height, pale if key == 'parcel_polygons' else gray)
        text(title, 60, top - 25, 15, bold=True)
        classification = {'open': 'OPEN GIS DATA', 'fee': 'FEE BASED GIS DATA'}.get(item['classification'], 'UNKNOWN')
        c.setFont('WatchtowerVeraBold', 8); c.setFillColor(HexColor(green)); c.drawRightString(552, top - 24, classification)
        methods = item['methods'] if item['classification'] == 'open' else []
        labels = {'mngeo_open': 'MnGeo open', 'direct_rest': 'Direct REST', 'direct_download': 'Direct Download', 'other': 'Other'}
        if methods:
            for i, m in enumerate(methods):
                # All selected access links fit even on compact road/address cards.
                if height == 78:
                    link(labels.get(m['kind'], 'Other'), m['url'], 60 + i * 123, top - 40, 119)
                else:
                    spacing = 38 if len(methods) <= 2 else 23
                    link(labels.get(m['kind'], 'Other'), m['url'], 60, top - 44 - i * spacing)
                    if len(methods) <= 2:
                        para(m['scope'], 60, top - 60 - i * spacing, 492, 15, 8.5, muted)
            if height > 78:
                dates = '; '.join(labels.get(m['kind'], 'Other') + ': ' + m['evidence_date'] for m in methods if m['evidence_date'])
                para('Evidence: ' + dates, 60, y + 22, 492, 17, 8, muted)
        else:
            para('Availability not confirmed.' if item['classification'] == 'unknown' else 'Contact county GIS staff for fees and access.', 60, top - 42, 492, 27, 9, muted)
    link('Full access details and evidence dates online', data['url'], 44, 77)
    c.showPage()
    frame(2, 'Policy, use restrictions and monitoring')
    text('COUNTY GIS POLICY', 44, 615, 9, green, True); panel(495, 103)
    para(data['policy']['text'] or 'No policy summary published. Contact county GIS staff for current terms.', 60, 580, 492, 55, 10)
    if safe_public_url(data['policy']['url']): link('Official county policy', data['policy']['url'], 60, 520)
    else: text('No official policy link recorded.', 60, 510, 9, muted)
    text('USE RESTRICTIONS', 44, 471, 9, green, True); panel(375, 80)
    notes = []
    for i, (key, title) in enumerate((('parcel_polygons', 'Parcels'), ('road_centerlines', 'Roads'), ('address_points', 'Addresses'))):
        r = data['access'][key]['restrictions']; x = 60 + i * 169
        text(title, x, 432, 10, bold=True)
        label = {'restricted': 'Use restrictions apply', 'reviewed_none': 'None recorded; confirm terms'}.get(r['status'], 'Not yet reviewed')
        para(label, x, 419, 153, 30, 9, muted, r['url'])
        if r['status'] == 'restricted': notes.append(title + ': ' + r['text'])
    para(' | '.join(notes) or 'Not reviewed does not mean unrestricted use.', 44, 365, 524, 38, 9, muted)
    panel(260, 65, '#FFF8E9'); text('Published county-direct access note', 60, 303, 10, bold=True)
    para(data['access']['parcel_polygons']['note'] or 'No additional public note.', 60, 288, 492, 24, 9, muted)
    text('WATCHTOWER MONITORING', 44, 239, 9, green, True)
    m = data['monitoring']
    for i, (label, value) in enumerate((('Monitoring path', m['path'] or 'Not available'), ('County-direct monitored sources', str(m['direct_count'])), ('Last check', profile_time(m['last_check'])))):
        y = 215 - 27 * i
        text(label, 44, y, 9, muted); para(value, 274, y + 9, 294, 22, 9)
        c.setStrokeColor(HexColor(line)); c.line(44, y - 8, 568, y - 8)
    para('Access methods and monitoring coverage are tracked separately. Current policy text, restrictions and supporting links are available in the full county profile.', 44, 130, 524, 42, 9, muted)
    link('Open the full county profile', data['url'], 44, 76)
    c.showPage()
    frame(3, 'MN GAC field summaries')
    para('Observed in statewide sources. Field population describes available values; it is not a compliance grade or a county-direct schema assessment.', 44, 632, 524, 30, 9, muted)
    for key, title, y in (('parcel', 'Parcel Polygons', 450), ('road', 'Road Centerlines', 290), ('address', 'Address Points', 130)):
        g = data['gac'][key]; top = y + 145
        panel(y, 145, pale if key == 'parcel' else gray); text(title, 60, top - 24, 15, bold=True)
        link('MN GAC standard v' + g['version'], g['standard_url'], 60, top - 34, 280)
        pct = g['mandatory_population_percent']
        if pct is not None and pct > 100: pct = None
        text(f'{pct:.2f}%' if pct is not None else 'No data', 447, top - 25, 18, green, True)
        text('Mandatory population', 443, top - 42, 8, muted)
        def n(v): return f'{v:,}' if v is not None else 'Unknown'
        metrics = f"{n(g['record_count'])} records | {n(g['present'])}/{n(g['field_count'])} field names | {n(g['mandatory_fields_full'])}/{n(g['mandatory_field_count'])} mandatory fields full"
        para(metrics, 60, top - 55, 492, 28, 8.5)
        c.setFillColor(HexColor(line)); c.roundRect(60, top - 84, 492, 4, 2, fill=1, stroke=0)
        if pct:
            c.setFillColor(HexColor(green)); c.roundRect(60, top - 84, 492 * pct / 100, 4, 2, fill=1, stroke=0)
        gaps = '; '.join(f"{f['label']}: {f['percent']:.2f}%" for f in g['gaps'])
        para('Selected gaps: ' + gaps if gaps else 'No partial mandatory-field results available.' if pct is None else 'No partial mandatory-field results recorded.', 60, top - 96, 492, 26, 8.5, muted)
        scan = f"Population scan: {n(g['scanned_field_count'])} of {n(g['field_count'])} standard fields."
        scan += f" All-field population: {g['field_population_percent']:.2f}%." if g["field_population_percent"] is not None else " Unscanned fields are not scored."
        para(scan, 60, top - 124, 492, 18, 8, muted)
    para('Population = the share of evaluated field values containing data. Full means populated for every record. Road/address observations are separate from access classifications.', 44, 112, 524, 34, 8.5, muted)
    link('View all MN GAC field results online', data['url'], 44, 69)
    c.showPage(); c.save()
    result = output.getvalue()
    if len(result) > _MAX_PDF_BYTES: raise ValueError('county PDF exceeds output limit')
    return result


def county_profile_pdf(snapshot: dict) -> bytes:
    """Return a three-page summary; detailed data remains in online exports."""
    payload = json.dumps(_summary(snapshot), ensure_ascii=True, allow_nan=False).encode('ascii')
    return _render(_TEMPLATE_VERSION, payload)
