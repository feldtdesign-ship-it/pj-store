#!/usr/bin/env python3
"""
render.py — builds the static preview site in pj-store/ from the real Shopify theme
in ../pj-theme/, using PJ's live product data (build/data/*.json, pulled from pjorourkeii.com
by fetch_data.sh). The preview renders the theme's own Liquid files, so what you see is
what the theme produces, minus checkout.

Run:  ../../../../.venv-or-scratch/venv/bin/python render.py      (needs python-liquid)
"""
import json, re, os, sys, shutil, html, math, struct, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORE = HERE.parent
THEME = STORE.parent / 'pj-theme'
DATA = HERE / 'data'
PREFIX = '/pj-store'
SITE = 'https://feldtdesign-ship-it.github.io'
PER_PAGE = 24
for i, a in enumerate(sys.argv):
    if a == '--prefix':
        PREFIX = sys.argv[i + 1]

from liquid import Environment, DictLoader
from liquid.builtin.expressions.primitive import Blank
from liquid.undefined import Undefined

# Shopify treats nil/undefined as blank; python-liquid does not. Patch it.
_orig_blank_eq = Blank.__eq__
def _blank_eq(self, other):
    if other is None or other is False or isinstance(other, Undefined):
        return True
    return _orig_blank_eq(self, other)
Blank.__eq__ = _blank_eq

# ----------------------------------------------------------------------------- data
def load(name):
    return json.load(open(DATA / name, encoding='utf-8'))

raw_products = load('products-p1.json')['products'] + load('products-p2.json')['products']
raw_colls = {c['handle']: c for c in load('collections.json')['collections']}
coll_handles = {}
for f in sorted(DATA.glob('coll-*.json')):
    h = f.name[5:-5]
    try:
        coll_handles[h] = [p['handle'] for p in json.load(open(f, encoding='utf-8'))['products']]
    except Exception:
        pass

IMAGE_DIMS = {}

def img_key(src):
    return src.split('?')[0]

def cents(s):
    return int(round(float(s) * 100)) if s not in (None, '') else None

def mk_image(im, alt=''):
    d = {'id': im['id'], 'src': im['src'], 'alt': im.get('alt') or alt, 'width': im['width'], 'height': im['height'],
         'aspect_ratio': im['width'] / im['height'] if im['height'] else 1, 'position': im.get('position', 1)}
    IMAGE_DIMS[img_key(im['src'])] = (im['width'], im['height'])
    return d

def strip_tags(s):
    return re.sub(r'<[^>]+>', '', s or '').replace('&nbsp;', ' ').strip()

def mk_product(p):
    handle = p['handle']
    images = [mk_image(im, p['title']) for im in p['images']]
    by_id = {im['id']: im for im in images}
    variants = []
    for v in p['variants']:
        fi = None
        if v.get('featured_image'):
            fi = by_id.get(v['featured_image'].get('id'))
        opts = [o for o in (v.get('option1'), v.get('option2'), v.get('option3')) if o is not None]
        variants.append({
            'id': v['id'], 'title': v['title'], 'name': f"{p['title']} - {v['title']}", 'price': cents(v['price']),
            'compare_at_price': cents(v.get('compare_at_price')), 'available': bool(v['available']),
            'option1': v.get('option1'), 'option2': v.get('option2'), 'option3': v.get('option3'), 'options': opts,
            'featured_image': fi, 'sku': v.get('sku') or '', 'requires_shipping': v.get('requires_shipping', True),
            'url': f"{PREFIX}/products/{handle}.html?variant={v['id']}", 'product_id': p['id'],
        })
    prices = [v['price'] for v in variants]
    first_avail = next((v for v in variants if v['available']), variants[0])
    has_default = len(variants) == 1 and variants[0]['title'] == 'Default Title'
    opts = p.get('options', [])
    owv = []
    if not has_default:
        for o in opts:
            pos = o['position']
            owv.append({'name': o['name'], 'position': pos, 'values': o['values'],
                        'selected_value': first_avail['options'][pos - 1] if len(first_avail['options']) >= pos else None})
    desc = p.get('body_html') or ''
    return {
        'id': p['id'], 'title': p['title'], 'handle': handle, 'url': f"{PREFIX}/products/{handle}.html",
        'type': p.get('product_type') or '', 'vendor': p.get('vendor') or '', 'tags': p.get('tags', []),
        'description': desc, 'content': desc, 'available': any(v['available'] for v in variants),
        'price': min(prices), 'price_min': min(prices), 'price_max': max(prices), 'price_varies': min(prices) != max(prices),
        'compare_at_price': None, 'compare_at_price_min': None, 'compare_at_price_max': None,
        'featured_image': images[0] if images else None, 'images': images, 'variants': variants,
        'options': [o['name'] for o in opts] if not has_default else ['Title'], 'options_with_values': owv,
        'selected_or_first_available_variant': first_avail, 'first_available_variant': first_avail, 'selected_variant': None,
        'has_only_default_variant': has_default, 'object_type': 'product', 'created_at': p.get('created_at', ''),
        'published_at': p.get('published_at', ''), 'template_suffix': '', 'collections': [],
    }

class Keyed(list):
    """A list that can also be indexed by handle, like Shopify's collections / all_products / linklists."""
    SPECIAL = {'size': lambda s: len(s), 'first': lambda s: s[0] if s else None, 'last': lambda s: s[-1] if s else None}
    def __init__(self, items, key='handle'):
        super().__init__(items)
        self._k = {i[key]: i for i in items}
    def __getitem__(self, k):
        if isinstance(k, str):
            if k in self.SPECIAL:
                return self.SPECIAL[k](self)
            return self._k.get(k)
        return super().__getitem__(k)

PRODUCTS = [mk_product(p) for p in raw_products]
ALL_PRODUCTS = Keyed(PRODUCTS)

SORT_OPTIONS = [
    {'name': 'Featured', 'value': 'manual'}, {'name': 'Best selling', 'value': 'best-selling'},
    {'name': 'Alphabetically, A–Z', 'value': 'title-ascending'}, {'name': 'Alphabetically, Z–A', 'value': 'title-descending'},
    {'name': 'Price, low to high', 'value': 'price-ascending'}, {'name': 'Price, high to low', 'value': 'price-descending'},
    {'name': 'Date, old to new', 'value': 'created-ascending'}, {'name': 'Date, new to old', 'value': 'created-descending'},
]

def mk_collection(handle, title, products, description=''):
    tags = sorted({t for p in products for t in p['tags']})
    return {'id': raw_colls.get(handle, {}).get('id', 0), 'title': title, 'handle': handle,
            'url': f"{PREFIX}/collections/{handle}.html", 'description': description, 'image': None,
            'featured_image': products[0]['featured_image'] if products else None, 'products': products,
            'products_count': len(products), 'all_products_count': len(products), 'all_tags': tags,
            'sort_by': '', 'default_sort_by': 'manual', 'sort_options': SORT_OPTIONS, 'template_suffix': '',
            'filters': [], 'current_type': None, 'current_vendor': None}

# Names the collections should carry on the real store (see pj-theme/README.md). The feed still has PJ's old names.
COLLECTION_TITLES = {'signed-unsigned': 'Prints', 'buttery-soft-tees': 'Tees', 'post-cards': 'Postcards',
                     'hats-buckets': 'Hats & beanies', 'jackets-coats': 'Outerwear', 'hoodie': 'Hoodies & crewnecks'}
colls = []
for h, handles in coll_handles.items():
    prods = [ALL_PRODUCTS[x] for x in handles if ALL_PRODUCTS[x]]
    meta = raw_colls.get(h, {})
    colls.append(mk_collection(h, COLLECTION_TITLES.get(h, meta.get('title', h)), prods, meta.get('body_html') or ''))
colls.append(mk_collection('all', 'All products', PRODUCTS))
COLLECTIONS = Keyed(colls)

MENUS = {
    'main-menu': [('Prints', '/collections/signed-unsigned'), ('Tees', '/collections/buttery-soft-tees'),
                  ('Postcards', '/collections/post-cards'), ('Hats & beanies', '/collections/hats-buckets'),
                  ('Outerwear', '/collections/jackets-coats'), ('Story', '/pages/story')],
    'footer': [('Prints', '/collections/signed-unsigned'), ('Tees', '/collections/buttery-soft-tees'),
               ('Postcards', '/collections/post-cards'), ('Hats & beanies', '/collections/hats-buckets'),
               ('Hoodies & crewnecks', '/collections/hoodie'), ('Outerwear', '/collections/jackets-coats'),
               ('All products', '/collections/all')],
    'footer-brand': [('The story', '/pages/story'), ('Contact', '/pages/contact'), ('Instagram', 'https://www.instagram.com/pjorourkeii/')],
    'footer-help': [('Shipping', '/pages/contact'), ('Returns', '/pages/contact'), ('Sizing', '/pages/contact'), ('Contact', '/pages/contact')],
}

def map_url(u):
    if not u:
        return ''
    u = u.replace('shopify://', '/')
    if u.startswith('http'):
        return u
    m = re.match(r'^/(collections|products|pages)/([^/?#]+)/?$', u)
    if m:
        return f"{PREFIX}/{m.group(1)}/{m.group(2)}.html"
    if u in ('/', ''):
        return f"{PREFIX}/"
    if u == '/collections':
        return f"{PREFIX}/collections.html"
    return u

def linklists_for(path):
    out = []
    for handle, links in MENUS.items():
        ls = []
        for title, url in links:
            u = map_url(url)
            ls.append({'title': title, 'url': u, 'active': u == path, 'current': u == path, 'child_active': False, 'links': [], 'levels': 0, 'type': 'collection_link'})
        out.append({'handle': handle, 'title': handle, 'links': ls, 'levels': 1})
    return Keyed(out)

def image_dims(path):
    try:
        with open(path, 'rb') as f:
            head = f.read(26)
            if head[:8] == b'\x89PNG\r\n\x1a\n':
                w, h = struct.unpack('>II', head[16:24]); return w, h
            f.seek(0); data = f.read()
            if data[:2] == b'\xff\xd8':
                i = 2
                while i < len(data):
                    if data[i] != 0xFF: i += 1; continue
                    marker = data[i + 1]
                    if marker in (0xC0, 0xC1, 0xC2):
                        h, w = struct.unpack('>HH', data[i + 5:i + 9]); return w, h
                    seg = struct.unpack('>H', data[i + 2:i + 4])[0]; i += 2 + seg
    except Exception:
        pass
    return 1200, 900

def shop_image(ref):
    """shopify://shop_images/x.jpg -> the preview's copy in assets/story/."""
    name = ref.split('/')[-1]
    local = STORE / 'assets' / 'story' / name
    if not local.exists():
        return None
    w, h = image_dims(local)
    src = f"{PREFIX}/assets/story/{name}"
    IMAGE_DIMS[img_key(src)] = (w, h)
    return {'id': name, 'src': src, 'alt': '', 'width': w, 'height': h, 'aspect_ratio': w / h}

SETTINGS_SCHEMA = json.load(open(THEME / 'config' / 'settings_schema.json'))
SETTINGS_DATA = json.load(open(THEME / 'config' / 'settings_data.json'))
LOCALE = json.load(open(THEME / 'locales' / 'en.default.json', encoding='utf-8'))

def schema_defaults(settings):
    out = {}
    for s in settings:
        if s.get('type') in ('header', 'paragraph'):
            continue
        out[s['id']] = s.get('default')
    return out

def resolve(schema_settings, values):
    out = {}
    values = values or {}
    for s in schema_settings:
        t = s.get('type')
        if t in ('header', 'paragraph'):
            continue
        sid = s['id']
        v = values.get(sid, s.get('default'))
        if t == 'product':
            v = ALL_PRODUCTS[v] if v else None
        elif t == 'collection':
            v = COLLECTIONS[v] if v else None
        elif t == 'image_picker':
            v = shop_image(v) if v else None
        elif t == 'url':
            v = map_url(v) if v else ''
        elif t in ('text', 'textarea', 'richtext', 'inline_richtext', 'html', 'liquid', 'link_list', 'select', 'radio'):
            v = v if v is not None else ''
        elif t == 'checkbox':
            v = bool(v) if v is not None else False
        elif t == 'range':
            v = v if v is not None else s.get('min', 0)
        out[sid] = v
    for k, v in values.items():
        if k not in out:
            out[k] = v
    return out

THEME_SETTINGS = {}
for group in SETTINGS_SCHEMA:
    if 'settings' in group:
        THEME_SETTINGS.update(resolve(group['settings'], SETTINGS_DATA.get('current', {})))
THEME_SETTINGS['share_image'] = {'id': 'og', 'src': f"{SITE}{PREFIX}/og.jpg", 'alt': "PJ O'Rourke II", 'width': 1200, 'height': 630, 'aspect_ratio': 1200 / 630}
THEME_SETTINGS['logo'] = None
THEME_SETTINGS['favicon'] = None

# ----------------------------------------------------------------------------- filters
def money(c, fmt=None):
    try:
        v = int(c) / 100.0
    except Exception:
        return ''
    return '${:,.2f}'.format(v)

def money_without_trailing_zeros(c):
    s = money(c)
    return s[:-3] if s.endswith('.00') else s

def money_with_currency(c):
    return money(c) + ' USD'

def money_without_currency(c):
    return money(c)[1:]

def image_src(obj):
    if isinstance(obj, dict):
        src = obj.get('src') or (obj.get('featured_image') or {}).get('src') if isinstance(obj.get('featured_image'), dict) else obj.get('src')
        return src or ''
    if obj is None or isinstance(obj, Undefined):
        return ''
    return str(obj)

def image_url(obj, width=None, height=None, crop=None, format=None, pad_color=None):
    src = image_src(obj)
    if not src:
        return ''
    if 'cdn.shopify.com' in src:
        params = []
        if width: params.append(f'width={int(width)}')
        if height: params.append(f'height={int(height)}')
        if crop: params.append(f'crop={crop}')
        if params:
            src = src + ('&' if '?' in src else '?') + '&'.join(params)
    if src.startswith('https://'):
        src = src[6:]
    elif src.startswith('http://'):
        src = src[5:]
    return src

def with_width(url, w):
    base = re.sub(r'([?&])width=\d+&?', r'\1', url).rstrip('?&')
    return base + ('&' if '?' in base else '?') + f'width={w}'

def image_tag(url, **kw):
    if not url:
        return ''
    attrs = []
    widths = kw.pop('widths', None)
    sizes = kw.pop('sizes', None)
    alt = kw.pop('alt', '') or ''
    key = img_key(url if not url.startswith('//') else 'https:' + url)
    dims = IMAGE_DIMS.get(key)
    m = re.search(r'[?&]width=(\d+)', url)
    req_w = int(m.group(1)) if m else None
    w = h = None
    if dims:
        w0, h0 = dims
        w = min(req_w, w0) if req_w else w0
        h = round(w * h0 / w0) if w0 else None
    if widths and 'cdn.shopify.com' in url:
        ws = [int(x) for x in str(widths).split(',') if x.strip()]
        if dims:
            ws = [x for x in ws if x <= dims[0]] or [dims[0]]
        attrs.append('srcset="' + ', '.join(f'{with_width(url, x)} {x}w' for x in ws) + '"')
    attrs.append(f'src="{html.escape(url, quote=True)}"')
    if sizes:
        attrs.append(f'sizes="{html.escape(str(sizes), quote=True)}"')
    if w and h:
        attrs.append(f'width="{w}" height="{h}"')
    attrs.append(f'alt="{html.escape(str(alt), quote=True)}"')
    for k, v in kw.items():
        if v is None or v == '':
            if k.startswith('data-'):
                attrs.append(k)
            continue
        attrs.append(f'{k}="{html.escape(str(v), quote=True)}"')
    return '<img ' + ' '.join(attrs) + '>'

def asset_url(name):
    name = str(name)
    if name.endswith('.liquid'):
        name = name[:-7]
    return f"{PREFIX}/assets/{name}"

def stylesheet_tag(url, preload=False):
    return f'<link href="{url}" rel="stylesheet" type="text/css" media="all">'

def script_tag(url):
    return f'<script src="{url}" type="text/javascript"></script>'

def preload_tag(url, **kw):
    a = ' '.join(f'{k.rstrip("_")}="{v}"' for k, v in kw.items())
    return f'<link rel="preload" href="{url}" {a}>'

def inline_asset_content(name):
    try:
        return (THEME / 'assets' / str(name)).read_text(encoding='utf-8')
    except Exception:
        return ''

def t(key, **kw):
    node = LOCALE
    for part in str(key).split('.'):
        node = node.get(part) if isinstance(node, dict) else None
    if node is None:
        print(f'  [t] missing translation: {key}', file=sys.stderr)
        return f'translation missing: en.{key}'
    if isinstance(node, dict):
        c = kw.get('count')
        node = node.get('one' if c == 1 else 'other', '')
    s = str(node)
    for k, v in kw.items():
        s = re.sub(r'\{\{\s*' + re.escape(k) + r'\s*\}\}', str(v), s)
    return s

def to_json(obj):
    if isinstance(obj, Undefined):
        return 'null'
    return json.dumps(obj, ensure_ascii=False, default=str)

def handleize(s):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')

def placeholder_svg_tag(name, cls=''):
    return (f'<svg class="{cls}" viewBox="0 0 525 525" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
            f'<rect width="525" height="525" fill="currentColor" opacity=".35"/>'
            f'<path d="M150 370l90-120 65 75 45-55 85 100z" fill="currentColor" opacity=".55"/></svg>')

def format_address(addr):
    if not isinstance(addr, dict):
        return ''
    parts = [addr.get(k) for k in ('name', 'company', 'address1', 'address2', 'city', 'province', 'zip', 'country')]
    return '<br>'.join(html.escape(str(p)) for p in parts if p)

def sort_by_filter(url, v):
    return f"{url}{'&' if '?' in url else '?'}sort_by={v}"

def link_to(text, url, title=''):
    return f'<a href="{url}" title="{title}">{text}</a>'

def paginate_obj(items, per_page):
    per_page = int(per_page or PER_PAGE)
    items = list(items) if items else []
    cur = int(G.get('current_page') or 1)
    base = G.get('page_base') or ''
    pages = max(1, math.ceil(len(items) / per_page))
    def url_for(n):
        return f"{base}.html" if n == 1 else f"{base}-p{n}.html"
    parts = []
    for n in range(1, pages + 1):
        parts.append({'title': str(n), 'url': url_for(n), 'is_link': n != cur})
    return {'pages': pages, 'current_page': cur, 'page_size': per_page, 'items': len(items),
            'current_offset': (cur - 1) * per_page,
            'previous': {'title': 'Previous', 'url': url_for(cur - 1), 'is_link': True} if cur > 1 else None,
            'next': {'title': 'Next', 'url': url_for(cur + 1), 'is_link': True} if cur < pages else None,
            'parts': parts}

def paginate_slice(root, attr, per_page):
    per_page = int(per_page or PER_PAGE)
    cur = int(G.get('current_page') or 1)
    if not isinstance(root, dict):
        return root
    copy = dict(root)
    items = list(copy.get(attr) or [])
    copy[attr] = items[(cur - 1) * per_page: cur * per_page]
    return copy

# ----------------------------------------------------------------------------- liquid env
def split_args(s):
    out, buf, q = [], '', None
    for ch in s:
        if q:
            buf += ch
            if ch == q: q = None
        elif ch in ("'", '"'):
            q = ch; buf += ch
        elif ch == ',':
            out.append(buf); buf = ''
        else:
            buf += ch
    if buf.strip():
        out.append(buf)
    return out

FORM_ACTIONS = {'product': '/cart/add', 'customer': '/contact#contact_form', 'contact': '/contact#contact_form', 'cart': '/cart',
                'customer_login': '/account/login', 'create_customer': '/account', 'recover_customer_password': '/account/recover',
                'customer_address': '/account/addresses', 'activate_customer_password': '/account/activate',
                'reset_customer_password': '/account/reset', 'storefront_password': '/password', 'guest_login': '/account/login'}

def form_repl(m):
    parts = split_args(m.group(1))
    ftype = parts[0].strip().strip("'\"")
    attrs = []
    for p in parts[1:]:
        p = p.strip()
        mm = re.match(r'^([\w-]+)\s*:\s*(.+)$', p)
        if mm:
            k, v = mm.group(1), mm.group(2).strip()
            val = v.strip("'\"") if v[:1] in "'\"" else '{{ ' + v + ' }}'
            attrs.append(f'{k}="{val}"')
    return (f'<form method="post" action="{FORM_ACTIONS.get(ftype, "#")}" accept-charset="UTF-8" {" ".join(attrs)}>'
            f'<input type="hidden" name="form_type" value="{ftype}"><input type="hidden" name="utf8" value="✓">')

def pag_repl(m):
    expr, by = m.group(1).strip(), m.group(2).strip()
    root, attr = expr.split('.', 1)
    return f"{{% assign paginate = {expr} | paginate_obj: {by} %}}{{% assign {root} = {root} | paginate_slice: '{attr}', {by} %}}"

def preprocess(src):
    src = re.sub(r'{%-?\s*schema\s*-?%}.*?{%-?\s*endschema\s*-?%}', '', src, flags=re.S)
    src = re.sub(r'{%-?\s*style\s*-?%}', '<style>', src)
    src = re.sub(r'{%-?\s*endstyle\s*-?%}', '</style>', src)
    src = src.replace('posted_successfully?', 'posted_successfully')
    src = src.replace('preload_tag: as:', 'preload_tag: as_:')
    src = re.sub(r'{%-?\s*layout\s+none\s*-?%}', '', src)
    src = re.sub(r'{%-?\s*render\s+block\s*-?%}', '', src)
    src = re.sub(r'{%-?\s*form\s+(.*?)\s*-?%}', form_repl, src, flags=re.S)
    src = re.sub(r'{%-?\s*endform\s*-?%}', '</form>', src)
    src = re.sub(r'{%-?\s*paginate\s+(.+?)\s+by\s+(.+?)\s*-?%}', pag_repl, src)
    src = re.sub(r'{%-?\s*endpaginate\s*-?%}', '', src)
    src = re.sub(r"{%-?\s*sections\s+'([^']+)'\s*-?%}", r"{{ '\1' | render_group }}", src)
    src = re.sub(r"{%-?\s*section\s+'([^']+)'\s*-?%}", r"{{ '\1' | render_section }}", src)
    return src

snippets = {}
for f in (THEME / 'snippets').glob('*.liquid'):
    snippets[f.stem] = preprocess(f.read_text(encoding='utf-8'))

G = {'_': 1}
env = Environment(loader=DictLoader(snippets), globals=G)
env.globals = G  # python-liquid replaces an empty globals dict with its own; make sure ours is used
for name, fn in {
    'money': money, 'money_without_trailing_zeros': money_without_trailing_zeros, 'money_with_currency': money_with_currency,
    'money_without_currency': money_without_currency, 'image_url': image_url, 'image_tag': image_tag, 'img_url': image_url,
    'asset_url': asset_url, 'asset_img_url': asset_url, 'stylesheet_tag': stylesheet_tag, 'script_tag': script_tag,
    'preload_tag': preload_tag, 'inline_asset_content': inline_asset_content, 't': t, 'json': to_json, 'handleize': handleize,
    'handle': handleize, 'placeholder_svg_tag': placeholder_svg_tag, 'format_address': format_address, 'format_code': lambda s: s,
    'default_errors': lambda e: '', 'payment_button': lambda f: '', 'within': lambda u, c=None: u, 'sort_by': sort_by_filter,
    'link_to': link_to, 'url_for_type': lambda s: '#', 'url_for_vendor': lambda s: '#', 'paginate_obj': paginate_obj,
    'paginate_slice': paginate_slice, 'default_pagination': lambda p: '', 'customer_login_link': lambda s: '',
    'time_tag': lambda d, fmt='%B %d, %Y': f'<time>{d}</time>', 'weight_with_unit': lambda w: f'{w} g',
    'url_param_escape': lambda s: html.escape(str(s)), 'highlight': lambda s, q='': s, 'class_list': lambda s: '',
}.items():
    env.add_filter(name, fn)

SECTION_CACHE = {}
def section_template(stype):
    """Preprocessed source + schema, cached. Compiled fresh per render so page globals are current."""
    if stype not in SECTION_CACHE:
        src = (THEME / 'sections' / f'{stype}.liquid').read_text(encoding='utf-8')
        m = re.search(r'{%-?\s*schema\s*-?%}(.*?){%-?\s*endschema\s*-?%}', src, re.S)
        schema = json.loads(m.group(1)) if m else {}
        SECTION_CACHE[stype] = (preprocess(src), schema)
    src, schema = SECTION_CACHE[stype]
    return env.from_string(src, name=f'sections/{stype}'), schema

def render_section(sid, stype, settings=None, blocks=None, block_order=None, index=0):
    tpl, schema = section_template(stype)
    sset = resolve(schema.get('settings', []), settings or {})
    bschemas = {b['type']: b for b in schema.get('blocks', [])}
    blist = []
    for bid in (block_order or list((blocks or {}).keys())):
        b = (blocks or {})[bid]
        bs = bschemas.get(b['type'], {})
        blist.append({'id': bid, 'type': b['type'], 'settings': resolve(bs.get('settings', []), b.get('settings', {})), 'shopify_attributes': ''})
    section = {'id': sid, 'settings': sset, 'blocks': blist, 'index': index, 'location': 'template'}
    try:
        out = tpl.render(section=section)
    except Exception as e:
        raise RuntimeError(f'section {stype} ({sid}): {e}') from e
    return f'<div id="shopify-section-{sid}" class="shopify-section">{out}</div>'

def render_static_section(name):
    conf = SETTINGS_DATA.get('current', {}).get('sections', {}).get(name, {})
    return render_section(name, name, conf.get('settings'), conf.get('blocks'), conf.get('block_order'))

def render_group(name):
    gj = json.load(open(THEME / 'sections' / f'{name}.json', encoding='utf-8'))
    return ''.join(render_section(sid, gj['sections'][sid]['type'], gj['sections'][sid].get('settings'),
                                  gj['sections'][sid].get('blocks'), gj['sections'][sid].get('block_order'), i)
                   for i, sid in enumerate(gj['order']))

env.add_filter('render_section', render_static_section)
env.add_filter('render_group', render_group)

LAYOUTS = {}
def layout_template(name):
    if name not in LAYOUTS:
        LAYOUTS[name] = preprocess((THEME / 'layout' / f'{name}.liquid').read_text(encoding='utf-8'))
    return env.from_string(LAYOUTS[name], name=f'layout/{name}')

# ----------------------------------------------------------------------------- globals
SHOP = {'name': "PJ O'Rourke II", 'email': 'hello@pjorourkeii.com', 'url': 'https://pjorourkeii.com', 'secure_url': 'https://pjorourkeii.com',
        'domain': 'pjorourkeii.com', 'permanent_domain': 'pjorourkeii.myshopify.com', 'currency': 'USD', 'money_format': '${{amount}}',
        'description': "Streetwear and screenprints by PJ O'Rourke II. Made in New York, sold on the platform since 2012.",
        'checkout': {'guest_login': False}, 'policies': [], 'enabled_currencies': []}
ROUTES = {'root_url': f'{PREFIX}/', 'cart_url': f'{PREFIX}/cart.html', 'cart_add_url': '#', 'cart_change_url': '#', 'cart_update_url': '#',
          'search_url': f'{PREFIX}/search.html', 'account_url': '#', 'account_login_url': '#', 'account_logout_url': '#',
          'account_register_url': '#', 'account_addresses_url': '#', 'collections_url': f'{PREFIX}/collections.html',
          'all_products_collection_url': f'{PREFIX}/collections/all.html', 'predictive_search_url': '#', 'product_recommendations_url': '#'}
CART = {'item_count': 0, 'items': [], 'total_price': 0, 'note': '', 'currency': {'iso_code': 'USD'}, 'empty': True}
FORM = {'posted_successfully': False, 'errors': None, 'email': '', 'name': '', 'body': '', 'first_name': '', 'last_name': '',
        'company': '', 'address1': '', 'address2': '', 'city': '', 'zip': '', 'country': '', 'province': '', 'phone': ''}

BASE = {'shop': SHOP, 'settings': THEME_SETTINGS, 'routes': ROUTES, 'cart': CART, 'collections': COLLECTIONS, 'all_products': ALL_PRODUCTS,
        'pages': Keyed([]), 'blogs': Keyed([]), 'form': FORM, 'content_for_header': '<!-- content_for_header -->', 'current_tags': None,
        'current_page': 1, 'customer': None, 'recommendations': {'performed': False, 'products_count': 0, 'products': []},
        'search': {'performed': False, 'terms': '', 'results': [], 'results_count': 0}, 'product': None, 'collection': None,
        'page': None, 'blog': None, 'article': None, 'powered_by_link': '', 'all_country_option_tags': '<option value="United States">United States</option>',
        'localization': None, 'predictive_search': None, 'page_image': None, 'template': {'name': 'index', 'suffix': None, 'directory': None}}

def page_globals(page_type, path, title, description='', **extra):
    g = dict(BASE)
    g.update({
        'request': {'page_type': page_type, 'path': path, 'host': SITE.replace('https://', ''), 'origin': SITE, 'locale': {'iso_code': 'en'}, 'design_mode': False, 'visual_preview_mode': False},
        'page_title': title, 'page_description': description, 'canonical_url': f'{SITE}{path}',
        'linklists': linklists_for(path), 'template': {'name': page_type if page_type != 'index' else 'index', 'suffix': extra.pop('suffix', None), 'directory': None},
    })
    g.update(extra)
    return g

def render_template(tname, g):
    G.clear(); G.update(g)
    tj = json.load(open(THEME / 'templates' / f'{tname}.json', encoding='utf-8'))
    body = ''.join(render_section(sid, tj['sections'][sid]['type'], tj['sections'][sid].get('settings'),
                                  tj['sections'][sid].get('blocks'), tj['sections'][sid].get('block_order'), i)
                   for i, sid in enumerate(tj['order']))
    G['content_for_layout'] = body
    out = layout_template(tj.get('layout', 'theme')).render()
    return out.replace('preview: false,', 'preview: true,')

def write(rel, content):
    p = STORE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')

# ----------------------------------------------------------------------------- build
def build():
    # assets
    adir = STORE / 'assets'
    adir.mkdir(exist_ok=True)
    for f in (THEME / 'assets').iterdir():
        if f.name.endswith('.liquid'):
            G.clear(); G.update(BASE)
            write(f'assets/{f.name[:-7]}', env.from_string(f.read_text(encoding='utf-8')).render())
        else:
            shutil.copy2(f, adir / f.name)
    count = 0
    # home
    write('index.html', render_template('index', page_globals('index', f'{PREFIX}/', SHOP['name'], SHOP['description']))); count += 1
    # products
    first_coll_of = {}
    for c in colls:
        for p in c['products']:
            first_coll_of.setdefault(p['handle'], c)
    for p in PRODUCTS:
        c = first_coll_of.get(p['handle'])
        pool = [x for x in (c['products'] if c else PRODUCTS) if x['handle'] != p['handle']][:4]
        g = page_globals('product', p['url'], p['title'], strip_tags(p['description'])[:160], product=p, page_image=p['featured_image'],
                         recommendations={'performed': True, 'products_count': len(pool), 'products': pool, 'intent': 'related'})
        write(f"products/{p['handle']}.html", render_template('product', g)); count += 1
    # collections (paginated)
    for c in colls:
        pages = max(1, math.ceil(len(c['products']) / PER_PAGE))
        for n in range(1, pages + 1):
            path = c['url'] if n == 1 else c['url'].replace('.html', f'-p{n}.html')
            g = page_globals('collection', path, c['title'], strip_tags(c['description'])[:160], collection=c,
                             page_image=c['featured_image'], current_page=n, page_base=c['url'][:-5])
            write(path[len(PREFIX) + 1:], render_template('collection', g)); count += 1
    # pages
    story = {'title': 'The story', 'handle': 'story', 'url': f'{PREFIX}/pages/story.html', 'content': ''}
    write('pages/story.html', render_template('page.story', page_globals('page', story['url'], story['title'], 'How a Home Depot cart became a brand.', page=story, suffix='story'))); count += 1
    contact = {'title': 'Contact', 'handle': 'contact', 'url': f'{PREFIX}/pages/contact.html',
               'content': '<p>Questions about an order, a size, or a print? Write to us. Wholesale and press, same door.</p>'}
    write('pages/contact.html', render_template('page.contact', page_globals('page', contact['url'], contact['title'], 'Write to the shoppe.', page=contact, suffix='contact'))); count += 1
    # the rest
    write('cart.html', render_template('cart', page_globals('cart', ROUTES['cart_url'], 'Bag'))); count += 1
    write('search.html', render_template('search', page_globals('search', ROUTES['search_url'], 'Search'))); count += 1
    write('404.html', render_template('404', page_globals('404', f'{PREFIX}/404.html', 'Not here'))); count += 1
    write('collections.html', render_template('list-collections', page_globals('list-collections', ROUTES['collections_url'], 'Collections'))); count += 1
    write('password.html', render_template('password', page_globals('password', f'{PREFIX}/password.html', SHOP['name']))); count += 1
    print(f'rendered {count} pages into {STORE}')

if __name__ == '__main__':
    build()
