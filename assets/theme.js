/* Platform — PJ O'Rourke II. Bag, menu, variant picker, gallery. No dependencies. */
(function () {
  'use strict';
  var PJ = window.PJ || {};
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- money ---------- */
  function money(cents) {
    if (PJ.redact) return '<span class="rx"></span>';
    var fmt = PJ.moneyFormat || '${{amount}}';
    var n = (cents / 100);
    var fixed = n.toFixed(2);
    var parts = fixed.split('.');
    var withCommas = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    var out = fmt
      .replace(/\{\{\s*amount_no_decimals_with_comma_separator\s*\}\}/g, withCommas.replace(/,/g, '.'))
      .replace(/\{\{\s*amount_with_comma_separator\s*\}\}/g, withCommas.replace(/,/g, '.') + ',' + parts[1])
      .replace(/\{\{\s*amount_no_decimals\s*\}\}/g, withCommas)
      .replace(/\{\{\s*amount\s*\}\}/g, withCommas + '.' + parts[1]);
    return out.replace(/\.00(\s|$)/, '$1').replace(/<[^>]+>/g, '');
  }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

  /* ---------- toast ---------- */
  var toastTimer;
  function toast(msg) {
    var t = $('#Toast'); if (!t) return;
    t.textContent = msg; t.classList.add('on');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.classList.remove('on'); }, 2200);
  }

  /* ---------- header ---------- */
  var nav = $('#SiteNav');
  if (nav) {
    var onScroll = function () { nav.classList.toggle('on', window.scrollY > 8); };
    window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
  }
  var menuBtn = $('[data-menu-toggle]'), menu = $('#MobileMenu');
  if (menuBtn && menu) {
    menuBtn.addEventListener('click', function () {
      var open = menu.hasAttribute('hidden');
      if (open) menu.removeAttribute('hidden'); else menu.setAttribute('hidden', '');
      menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  /* ---------- cart drawer ---------- */
  var drawer = $('#CartDrawer');
  function openDrawer() { if (!drawer) return; document.body.classList.add('cart-open'); drawer.setAttribute('aria-hidden', 'false'); var x = $('[data-cart-close]', drawer); if (x) x.focus(); }
  function closeDrawer() { document.body.classList.remove('cart-open'); if (drawer) drawer.setAttribute('aria-hidden', 'true'); }
  function setCount(n) { $$('[data-cart-count]').forEach(function (el) { el.textContent = n; }); }

  function swapHTML(fromDoc, id) {
    var src = fromDoc.querySelector('#' + id), dst = document.getElementById(id);
    if (src && dst) dst.innerHTML = src.innerHTML;
  }

  /* Real Shopify cart (AJAX API + section rendering) */
  var shopifyCart = {
    add: function (id, qty) {
      return fetch(PJ.routes.cartAdd + '.js', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ items: [{ id: id, quantity: qty }] })
      }).then(function (r) {
        if (!r.ok) return r.json().catch(function () { return {}; }).then(function (j) { throw new Error(j.description || j.message || 'Could not add to bag'); });
        return shopifyCart.refresh();
      });
    },
    change: function (key, qty) {
      return fetch(PJ.routes.cartChange + '.js', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ id: key, quantity: qty })
      }).then(function () { return shopifyCart.refresh(); });
    },
    refresh: function () {
      var page = $('[data-cart-page]');
      var jobs = [
        fetch(PJ.routes.root + '?section_id=cart-drawer').then(function (r) { return r.text(); }),
        fetch(PJ.routes.cart + '.js').then(function (r) { return r.json(); })
      ];
      if (page) jobs.push(fetch(PJ.routes.cart + '?section_id=' + page.getAttribute('data-cart-page')).then(function (r) { return r.text(); }));
      return Promise.all(jobs).then(function (res) {
        var doc = new DOMParser().parseFromString(res[0], 'text/html');
        swapHTML(doc, 'CartDrawer-body'); swapHTML(doc, 'CartDrawer-foot');
        setCount(res[1].item_count);
        if (page && res[2]) { var d2 = new DOMParser().parseFromString(res[2], 'text/html'); swapHTML(d2, 'CartPage'); }
      });
    }
  };

  /* Preview cart (static preview only; stored in this browser) */
  var previewCart = {
    key: 'pj-preview-bag',
    items: function () { try { return JSON.parse(localStorage.getItem(this.key) || '[]'); } catch (e) { return []; } },
    save: function (items) { try { localStorage.setItem(this.key, JSON.stringify(items)); } catch (e) {} },
    add: function (id, qty, meta) {
      var items = this.items(), hit = items.filter(function (i) { return i.id === id; })[0];
      if (hit) hit.qty += qty; else items.push({ id: id, key: String(id), qty: qty, title: meta.title, variant: meta.variant, price: meta.price, image: meta.image, url: meta.url });
      this.save(items); return Promise.resolve(this.render());
    },
    change: function (key, qty) {
      var items = this.items().map(function (i) { if (i.key === key) i.qty = qty; return i; }).filter(function (i) { return i.qty > 0; });
      this.save(items); return Promise.resolve(this.render());
    },
    refresh: function () { return Promise.resolve(this.render()); },
    render: function () {
      var items = this.items(), count = items.reduce(function (a, i) { return a + i.qty; }, 0), total = items.reduce(function (a, i) { return a + i.qty * i.price; }, 0);
      setCount(count);
      var body = $('#CartDrawer-body'), foot = $('#CartDrawer-foot');
      if (!body || !foot) return;
      if (!items.length) {
        body.innerHTML = '<div class="empty">' + esc(PJ.strings.empty || 'Your bag is empty.') + '</div>';
        foot.innerHTML = ''; return;
      }
      body.innerHTML = items.map(function (i) {
        return '<div class="line" data-line-key="' + esc(i.key) + '"><a class="ph" href="' + esc(i.url) + '">' + (i.image ? '<img src="' + esc(i.image) + '" alt="" width="200" height="200">' : '') + '</a>' +
          '<div><a class="nm" href="' + esc(i.url) + '">' + esc(i.title) + '</a>' + (i.variant && i.variant !== 'Default Title' ? '<div class="s">' + esc(i.variant) + '</div>' : '') +
          '<div class="qty"><button type="button" data-qty-minus aria-label="Less">−</button><input data-qty value="' + i.qty + '" inputmode="numeric" aria-label="Quantity"><button type="button" data-qty-plus aria-label="More">+</button></div>' +
          '<button type="button" class="rm" data-remove>' + esc(PJ.strings.remove || 'Remove') + '</button></div>' +
          '<div class="pr">' + money(i.price * i.qty) + '</div></div>';
      }).join('');
      foot.innerHTML = '<div class="tot"><span>' + esc(PJ.strings.subtotal || 'Subtotal') + '</span><span>' + money(total) + '</span></div>' +
        '<button type="button" class="btn" data-preview-checkout>' + esc(PJ.strings.checkout || 'Checkout') + '</button><span class="lbl">' + esc(PJ.strings.shippingNote || 'Shipping and tax at checkout.') + '</span>';
    }
  };
  var Cart = PJ.preview ? previewCart : shopifyCart;
  if (PJ.preview && drawer) previewCart.render();

  /* ---------- delegated clicks ---------- */
  document.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target : null; if (!t) return;
    var el;
    if ((el = t.closest('[data-cart-toggle]')) && drawer) { e.preventDefault(); openDrawer(); return; }
    if (t.closest('[data-cart-close]') || t.closest('#CartScrim')) { closeDrawer(); return; }
    if ((el = t.closest('[data-preview-checkout]'))) { toast('Preview only. Checkout runs on Shopify.'); return; }
    if ((el = t.closest('[data-quick-add]'))) {
      e.preventDefault();
      var id = parseInt(el.getAttribute('data-quick-add'), 10);
      el.disabled = true;
      Cart.add(id, 1, { title: el.getAttribute('data-title'), variant: el.getAttribute('data-variant-title'), price: parseInt(el.getAttribute('data-price'), 10), image: el.getAttribute('data-image'), url: el.getAttribute('data-url') })
        .then(function () { toast(PJ.strings.added); openDrawer(); })
        .catch(function (err) { toast(err.message); })
        .then(function () { el.disabled = false; });
      return;
    }
    var qbox = t.closest('.qty');
    if (qbox && !t.closest('[data-line-key]')) {
      var qi = $('[data-qty]', qbox), qv = parseInt(qi.value, 10) || 1;
      if (t.closest('[data-qty-minus]')) qi.value = Math.max(1, qv - 1);
      if (t.closest('[data-qty-plus]')) qi.value = qv + 1;
      return;
    }
    var line = t.closest('[data-line-key]');
    if (line) {
      var key = line.getAttribute('data-line-key'), input = $('[data-qty]', line), q = input ? parseInt(input.value, 10) || 1 : 1;
      if (t.closest('[data-qty-minus]')) { Cart.change(key, Math.max(0, q - 1)); return; }
      if (t.closest('[data-qty-plus]')) { Cart.change(key, q + 1); return; }
      if (t.closest('[data-remove]')) { e.preventDefault(); Cart.change(key, 0); return; }
    }
    if ((el = t.closest('[data-thumb]'))) {
      var sec = el.closest('[data-product-section]'), main = sec && $('[data-main-image]', sec);
      if (main) { main.src = el.getAttribute('data-src'); main.removeAttribute('srcset'); $$('[data-thumb]', sec).forEach(function (b) { b.setAttribute('aria-pressed', b === el ? 'true' : 'false'); }); }
    }
  });
  document.addEventListener('change', function (e) {
    var line = e.target.closest && e.target.closest('[data-line-key]');
    if (line && e.target.matches('[data-qty]')) { Cart.change(line.getAttribute('data-line-key'), Math.max(0, parseInt(e.target.value, 10) || 0)); }
    if (e.target.matches('[data-sort]')) {
      var u = new URL(window.location.href); u.searchParams.set('sort_by', e.target.value); u.searchParams.delete('page'); window.location.href = u.toString();
    }
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeDrawer(); if (menu && !menu.hasAttribute('hidden')) { menu.setAttribute('hidden', ''); if (menuBtn) menuBtn.setAttribute('aria-expanded', 'false'); } } });

  /* ---------- product form ---------- */
  function initProduct(section) {
    var dataEl = $('[data-variants]', section), form = $('form[data-product-form]', section);
    if (!dataEl || !form) return;
    var variants = JSON.parse(dataEl.textContent);
    var idInput = $('input[name="id"]', form), btn = $('[data-add-button]', form), txt = $('[data-add-text]', form);
    var price = $('[data-price]', section), main = $('[data-main] img', section);
    var title = section.getAttribute('data-product-title') || '';

    function selected() {
      var pick = $('input[name="variant-pick"]:checked', section);
      if (pick) return variants.filter(function (v) { return String(v.id) === pick.value; })[0];
      var radios = $$('input[data-option-position]:checked', section);
      if (!radios.length) return variants[0];
      radios.sort(function (a, b) { return a.getAttribute('data-option-position') - b.getAttribute('data-option-position'); });
      var opts = radios.map(function (r) { return r.value; });
      return variants.filter(function (v) { return opts.every(function (o, i) { return v.options[i] === o; }); })[0];
    }
    function markAvailability() {
      var radios = $$('input[data-option-position]', section); if (!radios.length) return;
      var checked = $$('input[data-option-position]:checked', section).map(function (r) { return { p: parseInt(r.getAttribute('data-option-position'), 10), v: r.value }; });
      radios.forEach(function (r) {
        var p = parseInt(r.getAttribute('data-option-position'), 10), val = r.value;
        var ok = variants.some(function (v) {
          if (!v.available || v.options[p - 1] !== val) return false;
          return checked.every(function (c) { return c.p === p || v.options[c.p - 1] === c.v; });
        });
        var label = r.nextElementSibling; if (label) label.classList.toggle('is-unavailable', !ok);
      });
    }
    function update() {
      var v = selected();
      if (!v) { if (btn) btn.disabled = true; if (txt) txt.textContent = PJ.strings.unavailable; return; }
      if (idInput) idInput.value = v.id;
      if (btn) btn.disabled = !v.available;
      if (txt) txt.textContent = v.available ? PJ.strings.add : PJ.strings.soldOut;
      if (price) {
        var h = '';
        if (v.compare_at_price && v.compare_at_price > v.price) h += '<s class="pr-was">' + money(v.compare_at_price) + '</s>';
        h += '<span class="pr-now">' + money(v.price) + '</span>';
        price.innerHTML = h;
      }
      if (v.featured_image && v.featured_image.src && main) {
        main.src = v.featured_image.src; main.removeAttribute('srcset');
        $$('[data-thumb]', section).forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-image-id') === String(v.featured_image.id) ? 'true' : 'false'); });
      }
      if (window.history && window.history.replaceState && !PJ.preview) {
        var u = new URL(window.location.href); u.searchParams.set('variant', v.id); window.history.replaceState({}, '', u.toString());
      }
      markAvailability();
    }
    section.addEventListener('change', function (e) {
      if (e.target.matches('input[data-option-position], input[name="variant-pick"]')) update();
    });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var v = selected(); if (!v || !v.available) return;
      var qEl = $('input[name="quantity"]', form), qty = qEl ? Math.max(1, parseInt(qEl.value, 10) || 1) : 1;
      if (btn) btn.disabled = true; if (txt) txt.textContent = PJ.strings.adding;
      var img = v.featured_image && v.featured_image.src ? v.featured_image.src : (main ? main.currentSrc || main.src : '');
      Cart.add(v.id, qty, { title: title, variant: v.title, price: v.price, image: img, url: window.location.pathname })
        .then(function () { toast(PJ.strings.added); openDrawer(); })
        .catch(function (err) { toast(err.message); })
        .then(function () { if (btn) btn.disabled = false; if (txt) txt.textContent = PJ.strings.add; });
    });
    update();
  }
  $$('[data-product-section]').forEach(initProduct);

  /* ---------- product recommendations ---------- */
  $$('[data-recommendations]').forEach(function (el) {
    var url = el.getAttribute('data-url'); if (!url || PJ.preview) return;
    fetch(url).then(function (r) { return r.text(); }).then(function (html) {
      var doc = new DOMParser().parseFromString(html, 'text/html'), inner = doc.querySelector('[data-recommendations]');
      if (inner && inner.innerHTML.trim()) el.innerHTML = inner.innerHTML;
    }).catch(function () {});
  });

  /* ---------- newsletter (preview only; Shopify posts the form itself) ---------- */
  if (PJ.preview) {
    $$('form[data-newsletter]').forEach(function (f) {
      f.addEventListener('submit', function (e) { e.preventDefault(); var ok = $('[data-newsletter-ok]', f.parentNode); if (ok) ok.removeAttribute('hidden'); f.reset(); });
    });
  }
})();
