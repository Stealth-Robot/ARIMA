/* ============================================================================
   Desktop edit mode.

   The switch beside an artist/misc page's pencil turns the page into a
   selectable list with an inspector panel docked on the right. Arrows move a
   highlight (with nothing highlighted they jump to the first/last item), Enter
   selects it, and Shift+arrows / Ctrl+click / checkboxes build a selection of
   one kind (songs or albums) for bulk edits. Every inspector field saves on
   change, then the page content refreshes in place.

   Mobile keeps the edit modals (edit_modal.js); this file stays inert there.
   Depends on core.js, ratings.js, edit_modal.js and edit.js, loaded before it.
   ============================================================================ */
(function() {
    var ALIAS_LANGS = [['', '—'], ['en', 'English'], ['rom', 'Romanized'], ['ko', 'Native KR'], ['ja', 'Native JP'], ['zh', 'Native CN'], ['other', 'Native Other']];

    var on = false;
    var cur = null;       // key of the highlighted row
    var sel = [];         // selected keys, all of one kind
    var selKind = null;   // 'song' | 'album' | 'artist'
    var pageArtistId = null;
    var panel = null;
    var loaded = null;    // { key, data } of the single selection on show
    var renderSeq = 0;
    var linkPop = null;

    /* ---- page model ---- */

    function root() { return document.getElementById('discography') || document.getElementById('misc-table'); }
    function isMiscPage() { return !document.getElementById('discography'); }
    function currentArtistId() {
        var el = document.querySelector('#discography [data-current-artist-id]');
        return el ? el.getAttribute('data-current-artist-id') : null;
    }
    function isItemRow(tr) { return tr.hasAttribute('data-song-id') || /^album-\d+$/.test(tr.id); }
    function rowKind(tr) { return tr.hasAttribute('data-song-id') ? 'song' : 'album'; }
    function baseKey(tr) {
        if (tr.hasAttribute('data-song-id')) return 'song:' + tr.getAttribute('data-song-id') + ':' + (tr.getAttribute('data-album-id') || '');
        return 'album:' + tr.id.slice(6);
    }
    // A song can be listed twice (misc genres, child sections), so repeats get an occurrence suffix.
    function assignKeys() {
        var seen = {};
        allRows().forEach(function(tr) {
            var b = baseKey(tr);
            seen[b] = (seen[b] || 0) + 1;
            tr.setAttribute('data-em-key', seen[b] > 1 ? b + '#' + seen[b] : b);
        });
    }
    function keyOf(tr) {
        if (!tr.hasAttribute('data-em-key')) assignKeys();
        return tr.getAttribute('data-em-key');
    }
    function kindOf(key) { return key.split(':')[0]; }
    function idOf(key) { return parseInt(key.split(':')[1], 10); }
    function albumOf(key) { var a = parseInt(key.split(':')[2], 10); return isNaN(a) ? null : a; }
    function allRows() {
        var r = root();
        if (!r) return [];
        return Array.prototype.filter.call(r.querySelectorAll('tr[id^="album-"], tr[data-song-id]'), isItemRow);
    }
    function visibleRows() { return allRows().filter(function(tr) { return tr.offsetParent !== null; }); }
    function rowFor(key) {
        var rows = allRows();
        for (var i = 0; i < rows.length; i++) if (keyOf(rows[i]) === key) return rows[i];
        return null;
    }
    function nameCell(tr) { return tr && tr.querySelector('td.song-name-cell, td.album-name-cell'); }
    function sortSel() {
        var order = allRows().map(keyOf);
        sel.sort(function(a, b) { return order.indexOf(a) - order.indexOf(b); });
    }

    /* ---- helpers ---- */

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text != null) n.textContent = text;
        return n;
    }
    function btn(label, cls, onclick) {
        var b = el('button', cls, label);
        b.type = 'button';
        if (onclick) b.onclick = onclick;
        return b;
    }
    function toast(msg) { if (typeof showBriefToast === 'function') showBriefToast(msg); }
    function getJSON(url) {
        return fetch(url, { headers: { 'Accept': 'application/json' } }).then(function(r) { return r.ok ? r.json() : null; });
    }
    function post(url, body, isJson) {
        return fetch(url, {
            method: 'POST',
            headers: _emHeaders(isJson ? { 'Content-Type': 'application/json' } : undefined),
            body: isJson ? JSON.stringify(body) : (body || ''),
            redirect: 'manual',
        });
    }
    function okOrThrow(r) { if (!r.ok) throw new Error('failed'); return r; }
    // Runs one request at a time so a bulk edit doesn't pile writes onto SQLite at once.
    function runEach(items, fn) {
        var failed = 0;
        return items.reduce(function(p, item) {
            return p.then(function() { return fn(item).then(function(r) { if (r && r.ok === false) failed++; }, function() { failed++; }); });
        }, Promise.resolve()).then(function() { return failed; });
    }

    // The page's own query, plus dupes=1 so edit mode lists a song under each album it's on.
    function discoQuery() {
        var p = new URLSearchParams(window.location.search);
        if (on) p.set('dupes', '1');
        var q = p.toString();
        return q ? '?' + q : '';
    }
    window._discoQuery = discoQuery;

    var refreshTimer = null, ownSwap = false;
    function refreshPage() {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(function() {
            var id = currentArtistId();
            if (id && window.htmx) { ownSwap = true; htmx.ajax('GET', '/artists/' + id + discoQuery(), { target: '#discography', swap: 'innerHTML' }); }
            else if (typeof window._miscRefreshExpanded === 'function') window._miscRefreshExpanded();
        }, 150);
    }

    /* ---- on / off ---- */

    function setOn(v) {
        if (v === on || (v && _isMobile())) return;
        on = v;
        window._editMode = v;
        document.body.classList.toggle('em-on', v);
        if (v) {
            pageArtistId = currentArtistId();
            ensurePanel();
            panel.hidden = false;
            hintBar.hidden = false;
            positionPanel();
        } else {
            cur = null; anchor = null; sel = []; selKind = null; loaded = null;
            closeLinkPop();
            if (panel) { panel.hidden = true; hintBar.hidden = true; }
        }
        decorate();
        if (v) renderPanel();
    }

    var hintBar = null;
    function ensurePanel() {
        if (panel) return;
        panel = el('aside');
        panel.id = 'em-panel';
        panel.setAttribute('aria-label', 'Inspector');
        panel.addEventListener('keydown', onPanelKey);
        document.body.appendChild(panel);
        // Ctrl-click on a Mac opens the context menu, so name the key that actually works there.
        var multi = /Mac/.test(navigator.platform) ? '⌘' : 'Ctrl';
        hintBar = el('div');
        hintBar.id = 'em-bar';
        hintBar.innerHTML = '<b>Edit mode</b><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>Enter</kbd> edit name</span>' +
            '<span><kbd>Shift</kbd>+<kbd>↑</kbd><kbd>↓</kbd>, <kbd>' + multi + '</kbd>+click or checkboxes to select several</span><span><kbd>Esc</kbd> back</span>';
        document.body.appendChild(hintBar);
    }
    function positionPanel() {
        if (!panel) return;
        var nav = document.querySelector('body > nav');
        var bar = document.querySelector('.artist-nav-container');
        var navH = nav ? nav.offsetHeight : 0;
        hintBar.style.top = navH + 'px';
        panel.style.top = (navH + hintBar.offsetHeight) + 'px';
        panel.style.bottom = (bar ? bar.offsetHeight : 0) + 'px';
        document.documentElement.style.setProperty('--em-bar-h', hintBar.offsetHeight + 'px');
    }

    /* ---- row decoration ---- */

    function decorate() {
        assignKeys();
        allRows().forEach(function(tr) {
            var key = keyOf(tr), cell = nameCell(tr);
            var ck = cell ? cell.querySelector(':scope > .em-ck') : null;
            if (on && cell && !ck) {
                ck = el('input', 'em-ck');
                ck.type = 'checkbox'; ck.tabIndex = -1;
                ck.setAttribute('aria-label', 'Select');
                cell.insertBefore(ck, cell.firstChild);
            } else if (!on && ck) {
                ck.remove(); ck = null;
            }
            if (ck) {
                ck.checked = sel.indexOf(key) !== -1;
                ck.disabled = !!selKind && selKind !== 'artist' && selKind !== rowKind(tr);
            }
            tr.classList.toggle('em-cur', on && key === cur);
            tr.classList.toggle('em-sel', on && sel.indexOf(key) !== -1);
        });
        document.querySelectorAll('.em-switch').forEach(function(s) { s.setAttribute('aria-checked', on ? 'true' : 'false'); });
    }

    function scrollToCur() {
        var tr = cur && rowFor(cur);
        if (tr) tr.scrollIntoView({ block: 'nearest' });
    }

    /* ---- selection ---- */

    var anchor = null;
    function selectOnly(key, focusTitle) {
        sel = [key];
        selKind = kindOf(key);
        if (selKind !== 'artist') { cur = key; anchor = key; }
        decorate();
        renderPanel(focusTitle);
    }
    function toggleInSel(key) {
        var kind = kindOf(key);
        if (selKind && selKind !== 'artist' && selKind !== kind) return;
        if (selKind === 'artist') sel = [];
        var i = sel.indexOf(key);
        if (i === -1) sel.push(key); else sel.splice(i, 1);
        sortSel();
        selKind = sel.length ? kind : null;
        cur = key;
        anchor = key;
        decorate();
        renderPanel();
    }
    // Shift-click: every visible row of the clicked kind between the last plain/Ctrl click and this one.
    function selectRange(key) {
        var keys = visibleRows().map(keyOf), kind = kindOf(key);
        var a = anchor ? keys.indexOf(anchor) : -1, b = keys.indexOf(key);
        if (a === -1 || b === -1 || kindOf(anchor) !== kind) { selectOnly(key); return; }
        sel = keys.slice(Math.min(a, b), Math.max(a, b) + 1).filter(function(k) { return kindOf(k) === kind; });
        selKind = kind;
        cur = key;
        decorate();
        renderPanel();
    }
    // Shift-checkbox: the whole range takes the clicked box's new state, keeping checks outside it.
    function checkRange(key) {
        var keys = visibleRows().map(keyOf), kind = kindOf(key);
        var a = anchor ? keys.indexOf(anchor) : -1, b = keys.indexOf(key);
        if (a === -1 || b === -1 || kindOf(anchor) !== kind || (selKind && selKind !== 'artist' && selKind !== kind)) { toggleInSel(key); return; }
        var want = sel.indexOf(key) === -1;
        if (selKind === 'artist') sel = [];
        keys.slice(Math.min(a, b), Math.max(a, b) + 1).forEach(function(k) {
            if (kindOf(k) !== kind) return;
            var i = sel.indexOf(k);
            if (want && i === -1) sel.push(k);
            else if (!want && i !== -1) sel.splice(i, 1);
        });
        sortSel();
        selKind = sel.length ? kind : null;
        cur = key;
        anchor = key;
        decorate();
        renderPanel();
    }
    function clearSel() { sel = []; selKind = null; decorate(); renderPanel(); }

    function move(dir, extend) {
        var keys = visibleRows().map(keyOf);
        if (!keys.length) return;
        var i = cur ? keys.indexOf(cur) : -1;
        if (i === -1) {
            cur = keys[dir < 0 ? 0 : keys.length - 1];
        } else if (extend) {
            var kind = kindOf(cur), j = i + dir;
            while (j >= 0 && j < keys.length && kindOf(keys[j]) !== kind) j += dir;
            if (j < 0 || j >= keys.length) return;
            if (selKind !== kind) { sel = [cur]; selKind = kind; }
            else if (sel.indexOf(cur) === -1) sel.push(cur);
            if (sel.indexOf(keys[j]) === -1) sel.push(keys[j]); else sel.splice(sel.indexOf(cur), 1);
            sortSel();
            cur = keys[j];
            decorate(); scrollToCur(); renderPanel();
            return;
        } else {
            cur = keys[Math.max(0, Math.min(keys.length - 1, i + dir))];
        }
        selectOnly(cur);
        scrollToCur();
    }

    /* ---- inspector ---- */

    function loadEntity(key) {
        var kind = kindOf(key), id = idOf(key);
        if (kind === 'artist') return getJSON('/artist/' + id + '/edit-info');
        if (kind === 'album') return getJSON('/album/' + id + '/songs');
        var albumId = albumOf(key);
        return Promise.all([getJSON('/song/' + id + '/info'), albumId ? getJSON('/album/' + albumId + '/songs') : null]).then(function(res) {
            var d = res[0];
            if (!d) return null;
            if (res[1]) {
                var pos = res[1].songs.map(function(s) { return s.id; }).indexOf(id);
                if (pos !== -1) d.track = { n: pos + 1, of: res[1].songs.length, album: res[1].album_name };
            }
            return d;
        });
    }

    function renderPanel(focusTitle) {
        if (!panel || !on) return;
        var seq = ++renderSeq;
        closeLinkPop();
        panel.classList.remove('em-loading');
        if (sel.length < 2) bulkCache = {};
        if (!sel.length) {
            loaded = null;
            panel.innerHTML = '';
            panel.appendChild(el('div', 'em-empty', 'Nothing selected'));
            return;
        }
        if (sel.length > 1) { loaded = null; renderBulk(seq); return; }
        var key = sel[0];
        if (!loaded) { panel.innerHTML = ''; panel.appendChild(el('div', 'em-empty', 'Loading…')); }
        else if (loaded.key !== key) panel.classList.add('em-loading');
        loadEntity(key).then(function(data) {
            if (seq !== renderSeq) return;
            panel.classList.remove('em-loading');
            if (!data) { panel.innerHTML = ''; panel.appendChild(el('div', 'em-empty', 'Failed to load.')); return; }
            loaded = { key: key, data: data };
            draw(key, data);
            if (focusTitle) {
                var t = panel.querySelector('.em-title');
                if (t) { t.focus(); t.select(); }
            }
        });
    }

    // Picks up changes made elsewhere (popovers, other editors) without clobbering a field being typed in.
    function softRefreshPanel() {
        if (!loaded || sel.length !== 1 || panel.contains(document.activeElement)) return;
        var key = loaded.key, seq = renderSeq;
        loadEntity(key).then(function(data) {
            if (!data || seq !== renderSeq || !loaded || loaded.key !== key || panel.contains(document.activeElement)) return;
            if (JSON.stringify(data) === JSON.stringify(loaded.data)) return;
            loaded.data = data;
            var top = panel.scrollTop;
            draw(key, data);
            panel.scrollTop = top;
        });
    }

    function draw(key, data) {
        panel.innerHTML = '';
        var kind = kindOf(key);
        if (kind === 'artist') drawArtist(idOf(key), data);
        else if (kind === 'album') drawAlbum(idOf(key), data);
        else drawSong(key, data);
        wrapSelects(panel);
    }

    // Native select arrows sit flush with the border; a wrapper draws a padded chevron instead.
    function wrapSelects(scope) {
        scope.querySelectorAll('select').forEach(function(s) {
            if (s.parentNode.classList.contains('em-select')) return;
            var w = el('span', 'em-select');
            s.parentNode.insertBefore(w, s);
            w.appendChild(s);
        });
    }

    /* ---- inspector building blocks ---- */

    function field(label, parent) {
        var f = el('div', 'em-field');
        if (label) f.appendChild(el('div', 'em-label', label));
        (parent || panel).appendChild(f);
        return f;
    }
    function section(label) { panel.appendChild(el('div', 'em-sec', label)); }
    // Each part is a list of plain strings, { b: text } for emphasis, or ready-made nodes.
    function facts(parts) {
        var row = el('div', 'em-facts');
        parts.forEach(function(p) {
            if (!p) return;
            var s = el('span');
            p.forEach(function(bit) {
                if (bit instanceof Node) s.appendChild(bit);
                else if (typeof bit === 'object') s.appendChild(el('b', null, bit.b));
                else s.appendChild(document.createTextNode(bit));
            });
            row.appendChild(s);
        });
        panel.appendChild(row);
    }
    function plural(n, word) { return n === 1 ? word : word + 's'; }

    // Saves an input on change (Enter or leaving the field); reverts it if the server refuses.
    function saveOnChange(inp, url, opts) {
        opts = opts || {};
        var saved = inp.value.trim();
        inp.addEventListener('change', function() {
            var v = inp.value.trim();
            if (v === saved) return;
            if (opts.required && !v) { inp.value = saved; return; }
            post(url, (opts.param || 'value') + '=' + encodeURIComponent(v)).then(okOrThrow).then(function() {
                saved = v;
                if (opts.key && loaded) loaded.data[opts.key] = v;
                refreshPage();
            }).catch(function() { inp.value = saved; toast(opts.error || 'Failed to save — try again'); });
        });
    }
    function textInput(parent, value, placeholder, id) {
        var inp = el('input');
        inp.type = 'text'; inp.value = value || ''; inp.placeholder = placeholder || '';
        if (id) inp.id = id;
        parent.appendChild(inp);
        return inp;
    }
    function titleInput(value, url, key, parent) {
        var inp = el('input', 'em-title');
        inp.type = 'text'; inp.value = value || ''; inp.id = 'em-name';
        inp.setAttribute('aria-label', 'Name');
        (parent || panel).appendChild(inp);
        saveOnChange(inp, url, { required: true, key: key });
        return inp;
    }
    // Title with a 🔄 that moves it into the alternate names; the move only lands once a new title is saved.
    function convertibleTitle(value, url, key, addAlias) {
        var row = el('div', 'em-row');
        panel.appendChild(row);
        var inp = titleInput(value, url, key, row);
        var pending = null;
        var b = btn('🔄', 'em-x', function() {
            var v = inp.value.trim();
            if (!v) return;
            pending = v;
            inp.value = '';
            inp.focus();
        });
        b.title = 'Convert the title to an alternative name';
        row.appendChild(b);
        inp.addEventListener('change', function() {
            var v = inp.value.trim();
            if (pending && v && v !== pending) addAlias(pending);
            pending = null;
        });
        inp.addEventListener('blur', function() {
            if (pending && !inp.value.trim()) { inp.value = pending; pending = null; }
        });
        return inp;
    }
    function urlField(label, value, url, placeholder, key) {
        var f = field(label);
        saveOnChange(textInput(f, value, placeholder), url, { key: key, error: 'Invalid URL — must start with https://' });
    }
    function noteField(value, url, key) {
        var f = field('Note');
        var ta = el('textarea');
        ta.rows = 2; ta.value = value || ''; ta.placeholder = 'Add a note…';
        f.appendChild(ta);
        saveOnChange(ta, url, { key: key });
    }
    function lookupSelect(parent, lookupUrl, selectedId, url, param, key) {
        var s = el('select');
        parent.appendChild(s);
        _emEnsure(lookupUrl, function(opts) {
            opts.forEach(function(o) {
                var op = el('option', null, o.name);
                op.value = o.id;
                if (o.id === selectedId) op.selected = true;
                s.appendChild(op);
            });
        });
        var saved = String(selectedId);
        s.onchange = function() {
            post(url, param + '=' + s.value).then(okOrThrow).then(function() {
                saved = s.value;
                if (loaded) loaded.data[key] = parseInt(s.value, 10);
                refreshPage();
            }).catch(function() { s.value = saved; toast('Failed to save — try again'); });
        };
        return s;
    }
    function tokenField(label, tokens, editLabel, onEdit) {
        var f = field(label);
        var wrap = el('div', 'em-tokens');
        tokens.forEach(function(t) {
            var s = el('span', 'em-tok', t[0]);
            if (t[1]) s.appendChild(el('i', null, t[1]));
            wrap.appendChild(s);
        });
        var b = btn(editLabel, 'em-add', function() { onEdit(b); });
        wrap.appendChild(b);
        f.appendChild(wrap);
        return wrap;
    }
    function genrePicker(title, selectedIds, onDone, onlyIds) {
        _emEnsure('/lookups/genres', function(opts) {
            if (onlyIds) opts = opts.filter(function(g) { return onlyIds.indexOf(g.id) !== -1; });
            showMobilePicker({ title: title, mode: 'multiselect',
                options: opts.map(function(g) { return { id: g.id, label: g.name }; }),
                selectedIds: selectedIds, onDone: onDone });
        });
    }
    function actions(list) {
        section('Actions');
        var wrap = el('div', 'em-acts');
        list.forEach(function(a) {
            if (!a) return;
            var b = btn(a[0], 'em-btn' + (a[2] ? ' danger' : ''), function() { a[1](b); });
            if (a[3]) b.appendChild(el('small', null, a[3]));
            wrap.appendChild(b);
        });
        panel.appendChild(wrap);
    }
    // Anchored popovers open next to their row; move them beside the panel so the cursor stays close.
    function besidePanel(anchor, open) {
        var before = Array.prototype.slice.call(document.body.children);
        open();
        Array.prototype.forEach.call(document.body.children, function(n) {
            if (before.indexOf(n) !== -1 || getComputedStyle(n).position !== 'fixed' || n.offsetWidth >= window.innerWidth) return;
            var a = anchor.getBoundingClientRect(), p = panel.getBoundingClientRect();
            n.style.left = Math.max(8, p.left - n.offsetWidth - 8) + 'px';
            n.style.top = Math.max(8, Math.min(a.top, window.innerHeight - n.offsetHeight - 8)) + 'px';
        });
    }
    function searchPicker(title, placeholder, searchUrl, mapItems, onSelect) {
        showMobilePicker({ title: title, mode: 'search', placeholder: placeholder,
            searchUrl: searchUrl, mapItems: mapItems, onSelect: onSelect });
    }
    function albumPicker(title, onSelect) {
        searchPicker(title, 'Search albums…', function(q) { return '/misc/search-albums?q=' + encodeURIComponent(q); },
            function(d) { return d.map(function(a) { return { id: a.id, label: a.name + (a.release_date ? ' (' + a.release_date.slice(0, 4) + ')' : '') }; }); },
            onSelect);
    }
    function artistPicker(title, onSelect) {
        searchPicker(title, 'Search artists…', function(q) { return '/misc/search-real-artists?q=' + encodeURIComponent(q); },
            function(d) { return d.map(function(a) { return { id: a.artist_id, label: a.name }; }); },
            onSelect);
    }
    function passwordConfirm(opts, runWithPw) {
        opts.onConfirm = function(pw, helpers) {
            runWithPw(pw).then(function(wrongPw) {
                if (wrongPw) { helpers.error('Incorrect password.'); return; }
                helpers.close();
                clearSel();
                refreshPage();
            });
        };
        showMobilePassword(opts);
    }

    // Alt-name rows (name + language); the whole list saves whenever a row changes.
    function aliasEditor(label, list, url, readBack) {
        var f = field(label);
        var wrap = el('div');
        f.appendChild(wrap);
        var saved = JSON.stringify(list);
        function collect() {
            var out = [], seen = {};
            wrap.querySelectorAll('.em-row').forEach(function(row) {
                var v = row.querySelector('input').value.trim(), lg = row.querySelector('select').value;
                if (!v || seen[v.toLowerCase()]) return;
                seen[v.toLowerCase()] = 1;
                out.push({ name: v, native_lang: lg || null });
            });
            return out;
        }
        function save() {
            var out = collect();
            if (JSON.stringify(out) === saved) return;
            post(url, readBack.wrap(out), true).then(okOrThrow).then(function(r) { return r.json(); }).then(function(j) {
                saved = JSON.stringify(readBack.unwrap(j) || out);
                refreshPage();
            }).catch(function() { toast('Could not save alternative names — Native JP/KR/CN/Other are mutually exclusive, and one each of the others.'); });
        }
        function addRow(name, lang) {
            var row = el('div', 'em-row');
            var inp = textInput(row, name, 'Alternative name');
            var s = el('select');
            s.setAttribute('aria-label', 'Language');
            ALIAS_LANGS.forEach(function(o) {
                var op = el('option', null, o[1]);
                op.value = o[0];
                if (o[0] === (lang || '')) op.selected = true;
                s.appendChild(op);
            });
            row.appendChild(s);
            if (readBack.title) {
                var up = btn('⬆', 'em-x', function() { promote(row, inp, s); });
                up.title = 'Make this the main name';
                row.appendChild(up);
            }
            row.appendChild(btn('✕', 'em-x', function() { row.remove(); _emRefreshLangOpts(wrap, 'select'); save(); }));
            inp.onchange = save;
            s.onchange = function() { _emRefreshLangOpts(wrap, 'select'); save(); };
            wrap.appendChild(row);
            wrapSelects(row);
            return inp;
        }
        function hasName(name, except) {
            return Array.prototype.some.call(wrap.querySelectorAll('.em-row'), function(r) {
                return r !== except && r.querySelector('input').value.trim().toLowerCase() === name.toLowerCase();
            });
        }
        // Same swap as the song modal: a plain alias is consumed, a language-tagged one stays tagged.
        function promote(row, inp, s) {
            var title = readBack.title, newMain = inp.value.trim(), oldMain = title.value.trim();
            if (!newMain) return;
            title.value = newMain;
            title.dispatchEvent(new Event('change'));
            var dup = hasName(oldMain, row);
            if (!s.value) row.remove();
            if (oldMain && oldMain.toLowerCase() !== newMain.toLowerCase() && !dup) addRow(oldMain, '');
            _emRefreshLangOpts(wrap, 'select');
            save();
        }
        list.forEach(function(a) { addRow(a.name, a.native_lang); });
        _emRefreshLangOpts(wrap, 'select');
        f.appendChild(btn('+ Add name', 'em-add', function() { addRow('', '').focus(); _emRefreshLangOpts(wrap, 'select'); }));
        return {
            add: function(name) {
                if (hasName(name)) return;
                addRow(name, '');
                _emRefreshLangOpts(wrap, 'select');
                save();
            },
        };
    }

    /* ---- artist ---- */

    function drawArtist(id, d) {
        var pfx = '/edit/artist/' + id;
        titleInput(d.name, pfx + '/name', 'name');
        facts([[{ b: String(d.album_count) }, ' ' + plural(d.album_count, 'album')], [{ b: String(d.song_count) }, ' ' + plural(d.song_count, 'song')]]);

        var af = field('Alternate names');
        var wrap = el('div');
        af.appendChild(wrap);
        var saved = d.alt_names.join('\n');
        function saveAlt() {
            var out = [], seen = {};
            wrap.querySelectorAll('input').forEach(function(i) {
                var v = i.value.trim();
                if (v && !seen[v.toLowerCase()]) { seen[v.toLowerCase()] = 1; out.push(v); }
            });
            if (out.join('\n') === saved) return;
            post(pfx + '/alt-names', 'value=' + encodeURIComponent(out.join('\n'))).then(okOrThrow)
                .then(function() { saved = out.join('\n'); refreshPage(); })
                .catch(function() { toast('Failed to save — try again'); });
        }
        function addAlt(name) {
            var row = el('div', 'em-row');
            var inp = textInput(row, name, 'Alternate name');
            inp.onchange = saveAlt;
            row.appendChild(btn('✕', 'em-x', function() { row.remove(); saveAlt(); }));
            wrap.appendChild(row);
            return inp;
        }
        d.alt_names.forEach(addAlt);
        af.appendChild(btn('+ Add name', 'em-add', function() { addAlt('').focus(); }));

        var sf = field('Status');
        var chips = el('div', 'em-chips');
        [['Tracked', 'is_tracked', 'is-tracked'], ['Complete', 'is_complete', 'is-complete'], ['Inactive', 'is_disbanded', 'is-disbanded']].forEach(function(s) {
            var c = btn(s[0], 'em-chip' + (d[s[1]] ? ' on' : ''));
            c.onclick = function() {
                var next = !d[s[1]];
                post(pfx + '/' + s[2], 'value=' + (next ? '1' : '0')).then(okOrThrow).then(function() {
                    d[s[1]] = next;
                    c.classList.toggle('on', next);
                    refreshPage();
                }).catch(function() { toast('Failed to save — try again'); });
            };
            chips.appendChild(c);
        });
        sf.appendChild(chips);

        var two = el('div', 'em-two');
        panel.appendChild(two);
        lookupSelect(field('Gender', two), '/lookups/genders', d.gender_id, pfx + '/gender', 'gender_id', 'gender_id');
        lookupSelect(field('Country', two), '/lookups/countries', d.country_id, pfx + '/country', 'country_id', 'country_id');
        urlField('Spotify URL', d.spotify_url, pfx + '/spotify-url', 'https://open.spotify.com/…', 'spotify_url');
        urlField('Image URL', d.image_url, pfx + '/image-url', 'https://…', 'image_url');

        // Same actions as the artist modal, so convert/link/unlink/delete behave identically.
        var acts = artistEditConfig(id).actions(d);
        var ctx = { id: id, data: d, close: closeMobileModal, markDirty: function() {}, toast: toast };
        var REL = { soloist: 'Soloist of ', subunit: 'Subunit of ', related: 'Related to ' };
        var unlinks = d.links.slice();
        actions(acts.map(function(a) {
            // The modal's unlink actions come in d.links order, so pair them up to say which link each removes.
            var lnk = a.label.indexOf('Unlink: ') === 0 ? unlinks.shift() : null;
            return [a.label, function() {
                if (!a.confirm) { a.run(ctx); return; }
                showMobilePassword({ title: a.confirm.title, confirmLabel: a.confirm.confirmLabel || 'Confirm',
                    message: typeof a.confirm.message === 'function' ? a.confirm.message(d) : a.confirm.message,
                    onConfirm: function(pw, helpers) { a.run(ctx, pw, helpers); } });
            }, a.kind === 'danger', lnk ? REL[lnk.rel] + lnk.name : null];
        }));
    }

    /* ---- album ---- */

    function drawAlbum(id, d) {
        var pfx = '/edit/album/' + id;
        var alts;
        convertibleTitle(d.album_name, pfx + '/name', 'album_name', function(n) { alts.add(n); });
        facts([[{ b: String(d.songs.length) }, ' ' + plural(d.songs.length, 'song')], d.date_confirmed ? ['date ', { b: 'confirmed' }] : ['date unconfirmed']]);

        var two = el('div', 'em-two');
        panel.appendChild(two);
        var df = field('Release date', two);
        var dateInp = textInput(df, d.release_date, 'YYYY-MM-DD');
        dateInp.setAttribute('data-date-format', '');
        if (typeof applyDateFormat === 'function') applyDateFormat(dateInp);
        // The formatter rewrites every keystroke from script, so the browser never fires change on its own.
        dateInp.addEventListener('blur', function() { dateInp.dispatchEvent(new Event('change')); });
        saveOnChange(dateInp, pfx + '/release-date', { key: 'release_date', error: 'Invalid date' });
        lookupSelect(field('Type', two), '/lookups/album-types', d.album_type_id, pfx + '/type', 'album_type_id', 'album_type_id');

        tokenField('Genres', d.genres.map(function(g) { return [g]; }), 'Edit', function() {
            genrePicker('Album genres', d.genre_ids, function(ids) {
                post(pfx + '/genres', 'genre_ids=' + ids.join(',')).then(okOrThrow).then(function() { refreshPage(); softRefreshAfter(); })
                    .catch(function() { toast('Failed to save — try again'); });
            });
        });
        alts = aliasEditor('Alternate names', d.alt_names, pfx + '/alt-names', {
            wrap: function(out) { return { alt_names: out }; },
            unwrap: function(j) { return j.alt_names; },
        });
        urlField('Spotify URL', d.spotify_url, pfx + '/spotify-url', 'https://open.spotify.com/…', 'spotify_url');
        noteField(d.note, pfx + '/note', 'note');
        if (d.songs.length) trackList(pfx, d.songs);

        actions([
            ['Add song…', function() {
                searchPicker('Add which song?', 'Search songs…', function(q) { return pfx + '/search-songs?q=' + encodeURIComponent(q); },
                    function(res) { return res.map(function(s) { return { id: s.id, label: s.name + ' — ' + s.artist }; }); },
                    function(item) { post(pfx + '/add-song', 'song_id=' + item.id).then(okOrThrow).then(refreshPage).catch(function() { toast('Add failed'); }); });
            }],
            ['Create new song…', function() { showCreateSongSheet(pfx); }],
            isMiscPage() ? null : ['Move songs to artist…', function() {
                artistPicker('Move all songs to…', function(item) {
                    post(pfx + '/move-artist', 'source_artist_id=' + currentArtistId() + '&target_artist_id=' + item.id)
                        .then(okOrThrow).then(function() { clearSel(); refreshPage(); }).catch(function() { toast('Move failed'); });
                });
            }],
            ['Delete album', function() { deleteAlbums([id], d.album_name); }, true],
        ]);
    }

    function softRefreshAfter() { setTimeout(softRefreshPanel, 400); }

    // Drag a track onto another to move it before/after it, same endpoint as the modal's arrows.
    function trackList(pfx, songs) {
        var f = field('Track order (drag to reorder)');
        var dragIdx = null;
        function render() {
            f.querySelectorAll('.em-track').forEach(function(n) { n.remove(); });
            songs.forEach(function(s, i) {
                var row = el('div', 'em-track');
                row.draggable = true;
                row.appendChild(el('span', null, (i + 1) + '.'));
                row.appendChild(el('span', null, s.name));
                row.addEventListener('dragstart', function(e) { dragIdx = i; e.dataTransfer.effectAllowed = 'move'; });
                row.addEventListener('dragover', function(e) {
                    if (dragIdx === null || dragIdx === i) return;
                    e.preventDefault();
                    var box = row.getBoundingClientRect();
                    var below = e.clientY > box.top + box.height / 2;
                    row.classList.toggle('em-drop-below', below);
                    row.classList.toggle('em-drop-above', !below);
                });
                row.addEventListener('dragleave', function() { row.classList.remove('em-drop-above', 'em-drop-below'); });
                row.addEventListener('drop', function(e) {
                    e.preventDefault();
                    var below = row.classList.contains('em-drop-below');
                    row.classList.remove('em-drop-above', 'em-drop-below');
                    var from = dragIdx;
                    dragIdx = null;
                    if (from === null || from === i) return;
                    var moving = songs[from];
                    post(pfx + '/move-song', 'song_id=' + moving.id + '&target_song_id=' + s.id + '&direction=' + (below ? 'after' : 'before'))
                        .then(okOrThrow).then(function() {
                            songs.splice(from, 1);
                            songs.splice(songs.indexOf(s) + (below ? 1 : 0), 0, moving);
                            render();
                            refreshPage();
                        }).catch(function() { toast('Reorder failed — try again'); });
                });
                row.addEventListener('dragend', function() { dragIdx = null; });
                f.appendChild(row);
            });
        }
        render();
    }

    function deleteAlbums(ids, name) {
        Promise.all(ids.map(function(id) { return getJSON('/edit/album/' + id + '/delete-info'); })).then(function(infos) {
            var n = 0, names = {};
            infos.forEach(function(info) {
                if (!info) return;
                n += info.other_artist_songs || 0;
                (info.other_artists || []).forEach(function(a) { names[a] = 1; });
            });
            var others = Object.keys(names);
            var opts = { title: ids.length === 1 ? 'Delete album?' : 'Delete ' + ids.length + ' albums?', confirmLabel: 'Delete',
                message: (ids.length === 1 ? '"' + name + '" and its' : 'These albums and their') + ' songs/ratings may be permanently deleted. Enter your password to confirm.' };
            if (n > 0) {
                opts.checkboxLabel = 'I acknowledge this also permanently deletes ' + n + ' song' + (n === 1 ? '' : 's') +
                    (others.length === 1 ? ' belonging to another artist' : ' belonging to other artists') +
                    (others.length ? ' (' + others.join(', ') + ')' : '') + '.';
            }
            passwordConfirm(opts, function(pw) { return deleteEach(ids.map(function(id) { return '/edit/album/' + id + '/delete'; }), pw); });
        });
    }
    // Resolves true when the password was wrong, so the dialog can say so and stay open.
    function deleteEach(urls, pw) {
        var wrong = false;
        return urls.reduce(function(p, url) {
            return p.then(function() {
                if (wrong) return;
                return post(url, 'password=' + encodeURIComponent(pw)).then(function(r) { if (r.status === 403) wrong = true; });
            });
        }, Promise.resolve()).then(function() { return wrong; });
    }

    /* ---- song ---- */

    function drawSong(key, d) {
        var id = idOf(key), albumId = albumOf(key), pfx = '/edit/song/' + id;
        var tr = rowFor(key), cell = nameCell(tr);
        var aliases;
        var title = convertibleTitle(d.name, pfx + '/name', 'name', function(n) { aliases.add(n); });
        facts([
            d.rating_count ? [{ b: String(d.rating_count) }, ' ' + plural(d.rating_count, 'rating') + ' · avg ', { b: String(d.rating_avg) }, el('span', 'em-star', '★')] : ['No ratings'],
            d.track ? ['Track ', { b: '#' + d.track.n + '/' + d.track.of }, ' on ' + d.track.album] : null,
        ]);

        var ff = field('Flags');
        var chips = el('div', 'em-chips');
        ff.appendChild(chips);
        function drawFlags() {
            chips.innerHTML = '';
            [['★ Lead', 'lead'], ['Promoted', 'promoted'], ['Remix', 'remix'], ['Cover', 'cover']].forEach(function(f) {
                chips.appendChild(btn(f[0], 'em-chip' + (f[1] === 'lead' ? ' em-lead' : '') + (d['is_' + f[1]] ? ' on' : ''), function() {
                    toggleFlag(id, f[1], d).then(drawFlags, function() { toast('Failed to save — try again'); });
                }));
            });
        }
        drawFlags();

        var artistTokens = (d.main_artists || []).map(function(n) { return [n, 'Main']; })
            .concat((d.featured_artists || []).map(function(n) { return [n, 'Feat']; }));
        tokenField('Artists', artistTokens, 'Edit', function(anchor) {
            if (isMiscPage()) _showMiscArtistSelector(id);
            else besidePanel(anchor, function() { showSongArtists({ stopPropagation: function() {} }, id, cell); });
        });
        tokenField('Genres', d.genres.map(function(g) { return [g]; }), 'Edit', function() {
            genrePicker('Song genres', d.genre_ids, function(ids) {
                post(pfx + '/genres', 'genre_ids=' + ids.join(',')).then(okOrThrow).then(function() { refreshPage(); softRefreshAfter(); })
                    .catch(function() { toast('Failed to save — try again'); });
            });
        });
        urlField('Spotify URL', d.spotify_url, pfx + '/spotify-url', 'https://open.spotify.com/… (or n/a)', 'spotify_url');
        urlField('YouTube URL', d.youtube_url, pfx + '/youtube-url', 'https://…', 'youtube_url');
        aliases = aliasEditor('Alternative names', d.aliases, pfx + '/aliases', {
            wrap: function(out) { return { aliases: out }; },
            unwrap: function(j) { return j; },
            title: title,
        });
        noteField(d.note, pfx + '/note', 'note');
        var tf = field('Anime OST');
        var picker = themeSongPicker(d.theme_type, d.theme_number, function() {
            var v = picker.getValue();
            post(pfx + '/theme', 'type=' + encodeURIComponent(v.type) + '&number=' + (v.number || '')).then(okOrThrow)
                .then(function(r) { return r.json(); })
                .then(function(t) { d.theme_type = t.theme_type; d.theme_number = t.theme_number; refreshPage(); })
                .catch(function() { toast('Failed to save — try again'); });
        });
        // Restyle the shared picker for the panel instead of its dialog-sized inline styles.
        picker.className = 'em-theme';
        picker.style.cssText = '';
        picker.querySelectorAll('select, input').forEach(function(n) { n.style.cssText = ''; });
        tf.appendChild(picker);

        // Misc rows are songs only, so their album is edited from here rather than by selecting an album row.
        var miscAlbum = isMiscPage() && tr ? tr.querySelector('[data-misc-album]') : null;
        actions([
            miscAlbum ? ['Edit album…', function() { _showAlbumEditor(id, parseInt(miscAlbum.getAttribute('data-misc-album'), 10)); }] : null,
            ['Move to album…', function() { albumPicker('Move to which album?', function(item) { songAlbumAction(pfx + '/move-album', item.id, albumId); }); }],
            ['Add to album…', function() { albumPicker('Add to which album?', function(item) { songAlbumAction(pfx + '/add-to-album', item.id); }); }],
            isMiscPage() ? ['Move to artist…', function() { _showMoveSongToArtist({ stopPropagation: function() {} }, id, d.name); }] : null,
            ['Merge…', function(anchor) { besidePanel(anchor, function() { _openMergePopover(id, d.name, cell); }); }],
            albumId ? ['Split', function() {
                post(pfx + '/split', 'album_id=' + albumId).then(okOrThrow).then(refreshPage).catch(function() { toast('Split failed'); });
            }] : null,
            albumId ? ['Remove from album', function() {
                showConfirm('Remove from album?', 'Remove "' + d.name + '" from this album. If it is the only album, the song is deleted.', function() {
                    post(pfx + '/remove-from-album/' + albumId).then(okOrThrow).then(function() { clearSel(); refreshPage(); })
                        .catch(function() { toast('Remove failed'); });
                }, 'Remove');
            }] : null,
            ['Delete song', function() {
                passwordConfirm({ title: 'Delete song?', confirmLabel: 'Delete',
                    message: '"' + d.name + '" will be permanently deleted. Enter your password to confirm.' },
                    function(pw) { return deleteEach([pfx + '/delete'], pw); });
            }, true],
        ]);
    }

    function songAlbumAction(url, albumId, fromAlbumId) {
        post(url, 'album_id=' + albumId + (fromAlbumId ? '&from_album_id=' + fromAlbumId : '')).then(okOrThrow).then(function() {
            // A moved song's row now sits under the target album; keep it selected there.
            if (fromAlbumId && sel.length === 1) { sel = ['song:' + idOf(sel[0]) + ':' + albumId]; cur = anchor = sel[0]; }
            refreshPage();
        }).catch(function() { toast('Failed'); });
    }

    // Lead toggles server-side (and implies promoted); the other flags take an explicit value.
    function toggleFlag(songId, flag, d, want) {
        var next = want === undefined ? !d['is_' + flag] : want;
        if (flag === 'lead') {
            if (next === !!d.is_lead) return Promise.resolve();
            return post('/edit/song/' + songId + '/is-lead').then(okOrThrow).then(function(r) { return r.json(); }).then(function(res) {
                d.is_lead = res.is_lead; d.is_promoted = res.is_promoted;
                refreshPage();
            });
        }
        if (want !== undefined && next === !!d['is_' + flag]) return Promise.resolve();
        return post('/edit/song/' + songId + '/is-' + flag, 'checked=' + (next ? 'true' : '')).then(okOrThrow).then(function() {
            d['is_' + flag] = next;
            if (flag === 'promoted' && !next) d.is_lead = false;
            refreshPage();
        });
    }

    /* ---- several selected ---- */

    // Per-item promises, so growing a selection only fetches the rows it adds, even mid-flight.
    var bulkCache = {};
    function renderBulk(seq) {
        var kind = selKind, keys = sel.slice();
        var missing = keys.map(idOf).filter(function(id, i, a) { return !bulkCache[kind + ':' + id] && a.indexOf(id) === i; });
        if (missing.length) {
            // POST because a large range of ids overflows gunicorn's request-line limit as a query string.
            var req = post('/edit/bulk-info', { kind: kind, ids: missing }, true).then(okOrThrow).then(function(r) { return r.json(); });
            missing.forEach(function(id) {
                var k = kind + ':' + id;
                bulkCache[k] = req.then(function(res) {
                    if (!res[id]) throw new Error('missing');
                    return res[id];
                }).catch(function(err) { delete bulkCache[k]; throw err; });
            });
        }
        if (!panel.querySelector('.em-bulk-names')) { panel.innerHTML = ''; panel.appendChild(el('div', 'em-empty', 'Loading…')); }
        else panel.classList.add('em-loading');
        Promise.all(keys.map(function(k) { return bulkCache[kind + ':' + idOf(k)]; })).then(function(datas) {
            if (seq !== renderSeq) return;
            panel.classList.remove('em-loading');
            panel.innerHTML = '';
            var items = keys.map(function(k, i) { return { key: k, id: idOf(k), album: albumOf(k), d: datas[i] }; });
            if (kind === 'song') drawBulkSongs(items); else drawBulkAlbums(items);
            wrapSelects(panel);
        }, function() {
            // Drawing with empty data would let "Add genre to all" overwrite each song's existing genres.
            if (seq !== renderSeq) return;
            panel.classList.remove('em-loading');
            panel.innerHTML = '';
            panel.appendChild(el('div', 'em-empty', 'Failed to load.'));
        });
    }
    function bulkHeader(items, noun) {
        panel.appendChild(el('div', 'em-title', items.length + ' ' + noun));
        var wrap = el('div', 'em-tokens em-bulk-names');
        items.forEach(function(it) { wrap.appendChild(el('span', 'em-tok', it.d.name || it.d.album_name || '')); });
        panel.appendChild(wrap);
    }
    function bulkDone(failed, verb) {
        if (failed) toast(failed + ' could not be ' + verb);
        bulkCache = {};
        refreshPage();
        renderPanel();
    }

    // Each item keeps its other genres; only items whose list actually changes are saved.
    function bulkGenreField(items, noun, pfx) {
        function setEach(change) {
            var todo = items.map(function(it) {
                var cur = it.d.genre_ids || [];
                return { it: it, next: change(cur), cur: cur };
            }).filter(function(t) { return t.next.join(',') !== t.cur.join(','); });
            runEach(todo, function(t) { return post(pfx + t.it.id + '/genres', 'genre_ids=' + t.next.join(',')); })
                .then(function(failed) { bulkDone(failed, 'updated'); });
        }
        var wrap = tokenField('Genres', [], 'Add genre to all', function() {
            genrePicker('Add genres to ' + items.length + ' ' + noun, [], function(ids) {
                if (ids.length) setEach(function(cur) { return cur.concat(ids.filter(function(g) { return cur.indexOf(g) === -1; })); });
            });
        });
        wrap.appendChild(btn('Remove genre from all', 'em-add', function() {
            var present = [];
            items.forEach(function(it) { (it.d.genre_ids || []).forEach(function(g) { if (present.indexOf(g) === -1) present.push(g); }); });
            if (!present.length) { toast('None of these ' + noun + ' have genres'); return; }
            genrePicker('Remove genres from ' + items.length + ' ' + noun, [], function(ids) {
                if (ids.length) setEach(function(cur) { return cur.filter(function(g) { return ids.indexOf(g) === -1; }); });
            }, present);
        }));
    }

    function drawBulkSongs(rows) {
        // Duplicate rows of one song act once; only album moves and removals are per row.
        var items = rows.filter(function(it, i) { return rows.findIndex(function(o) { return o.id === it.id; }) === i; });
        bulkHeader(items, 'songs');
        var ff = field('Set on all');
        var chips = el('div', 'em-chips');
        ff.appendChild(chips);
        [['★ Lead', 'lead'], ['Promoted', 'promoted'], ['Remix', 'remix'], ['Cover', 'cover']].forEach(function(f) {
            var n = items.filter(function(it) { return it.d['is_' + f[1]]; }).length;
            var all = n === items.length;
            chips.appendChild(btn(f[0], 'em-chip' + (f[1] === 'lead' ? ' em-lead' : '') + (all ? ' on' : (n ? ' em-mixed' : '')), function() {
                runEach(items, function(it) { return toggleFlag(it.id, f[1], it.d, !all); }).then(function(failed) { bulkDone(failed, 'updated'); });
            }));
        });

        bulkGenreField(items, 'songs', '/edit/song/');
        if (!isMiscPage()) {
            tokenField('Artists', [], 'Add featured artist to all', function() {
                artistPicker('Add which artist?', function(a) {
                    runEach(items, function(it) { return post('/edit/song/' + it.id + '/artists', 'artist_id=' + a.id + '&is_main=false'); })
                        .then(function(failed) { bulkDone(failed, 'updated'); });
                });
            });
        } else {
            // Misc songs save their whole artist list at once, so append to each song's current list.
            var addMiscFeat = function(entry, has) {
                runEach(items, function(it) {
                    return getJSON('/misc/song/' + it.id + '/artists').then(function(cur) {
                        if (!cur) throw new Error('failed');
                        var misc = cur.misc_artists.map(function(m) { return { id: m.id, is_main: m.is_main }; });
                        var real = cur.real_artists.map(function(r) { return { artist_id: r.artist_id, is_main: r.is_main }; });
                        if (has(misc, real)) return null;
                        (entry.id ? misc : real).push(entry);
                        return post('/misc/song/' + it.id + '/misc-artists', { misc_artists: misc, real_artists: real }, true);
                    });
                }).then(function(failed) { bulkDone(failed, 'updated'); });
            };
            tokenField('Artists', [], 'Add featured artist to all', function() {
                artistPicker('Add which artist?', function(a) {
                    addMiscFeat({ artist_id: a.id, is_main: false }, function(m, r) { return r.some(function(x) { return x.artist_id === a.id; }); });
                });
            });
            tokenField('Misc artists', [], 'Add featured misc artist to all', function() {
                searchPicker('Add which misc artist?', 'Search misc artists…', function(q) { return '/misc/search-artists?q=' + encodeURIComponent(q); },
                    function(d) { return d.map(function(m) { return { id: m.id, label: m.name }; }); },
                    function(m) { addMiscFeat({ id: m.id, is_main: false }, function(mi) { return mi.some(function(x) { return x.id === m.id; }); }); });
            });
        }

        var inAlbum = rows.filter(function(it) { return it.album; });
        actions([
            ['Move to album…', function() {
                albumPicker('Move ' + items.length + ' songs to which album?', function(al) {
                    runEach(rows, function(it) { return post('/edit/song/' + it.id + '/move-album', 'album_id=' + al.id + (it.album ? '&from_album_id=' + it.album : '')); })
                        .then(function(failed) { clearSel(); bulkDone(failed, 'moved'); });
                });
            }],
            ['Add to album…', function() {
                albumPicker('Add ' + items.length + ' songs to which album?', function(al) {
                    runEach(items, function(it) { return post('/edit/song/' + it.id + '/add-to-album', 'album_id=' + al.id); })
                        .then(function(failed) { bulkDone(failed, 'added'); });
                });
            }],
            inAlbum.length ? ['Remove from album', function() {
                showConfirm('Remove ' + inAlbum.length + ' songs from their album?', 'Songs that are only on this album are deleted.', function() {
                    runEach(inAlbum, function(it) { return post('/edit/song/' + it.id + '/remove-from-album/' + it.album); })
                        .then(function(failed) { clearSel(); bulkDone(failed, 'removed'); });
                }, 'Remove');
            }] : null,
            ['Delete ' + items.length + ' songs', function() {
                passwordConfirm({ title: 'Delete ' + items.length + ' songs?', confirmLabel: 'Delete',
                    message: 'These songs and their ratings will be permanently deleted. Enter your password to confirm.' },
                    function(pw) { return deleteEach(items.map(function(it) { return '/edit/song/' + it.id + '/delete'; }), pw); });
            }, true],
        ]);
    }

    function drawBulkAlbums(items) {
        bulkHeader(items, 'albums');
        var tf = field('Set type on all');
        var s = el('select');
        s.appendChild(el('option', null, '—'));
        tf.appendChild(s);
        _emEnsure('/lookups/album-types', function(opts) {
            opts.forEach(function(o) { var op = el('option', null, o.name); op.value = o.id; s.appendChild(op); });
        });
        s.onchange = function() {
            if (!s.value || s.value === '—') return;
            runEach(items, function(it) { return post('/edit/album/' + it.id + '/type', 'album_type_id=' + s.value); })
                .then(function(failed) { bulkDone(failed, 'updated'); });
        };
        bulkGenreField(items, 'albums', '/edit/album/');
        actions([
            isMiscPage() ? null : ['Move songs to artist…', function() {
                artistPicker('Move these albums\' songs to…', function(a) {
                    runEach(items, function(it) { return post('/edit/album/' + it.id + '/move-artist', 'source_artist_id=' + currentArtistId() + '&target_artist_id=' + a.id); })
                        .then(function(failed) { clearSel(); bulkDone(failed, 'moved'); });
                });
            }],
            ['Delete ' + items.length + ' albums', function() { deleteAlbums(items.map(function(it) { return it.id; })); }, true],
        ]);
    }

    /* ---- link popup ---- */

    function closeLinkPop() { if (linkPop) { linkPop.remove(); linkPop = null; } }

    // Small anchored popup holding one URL field: Enter saves, Esc cancels, empty removes.
    function valuePop(anchorEl, spec) {
        closeLinkPop();
        var pop = el('div', 'em-linkpop');
        var head = el('div', 'em-linkhead');
        head.appendChild(el('span', null, spec.label));
        var open = el('a', null, 'Open ↗');
        open.target = '_blank'; open.rel = 'noopener'; open.hidden = true;
        head.appendChild(open);
        pop.appendChild(head);
        var inp = el('input');
        inp.type = 'text'; inp.disabled = true; inp.placeholder = 'Loading…';
        inp.setAttribute('aria-label', spec.label);
        pop.appendChild(inp);
        pop.appendChild(el('div', 'em-linkhint', 'Enter saves · Esc cancels · clear it to remove the link'));
        if (spec.extra) spec.extra(pop, inp);
        document.body.appendChild(pop);
        var r = anchorEl.getBoundingClientRect();
        pop.style.top = (r.bottom + 6) + 'px';
        pop.style.left = Math.max(8, Math.min(r.left - 16, window.innerWidth - pop.offsetWidth - 8)) + 'px';
        linkPop = pop;

        var saved = '';
        spec.load().then(function(v) {
            if (linkPop !== pop) return;
            saved = v || '';
            inp.disabled = false;
            inp.placeholder = spec.placeholder;
            inp.value = saved;
            if (saved && saved !== 'n/a') { open.href = saved; open.hidden = false; }
            inp.focus();
            inp.select();
        });
        inp.addEventListener('keydown', function(e) {
            e.stopPropagation();
            if (e.key === 'Escape') { e.preventDefault(); closeLinkPop(); }
            else if (e.key === 'Enter') {
                e.preventDefault();
                var v = inp.value.trim();
                if (v === saved) { closeLinkPop(); return; }
                post(spec.saveUrl, 'value=' + encodeURIComponent(v)).then(okOrThrow)
                    .then(function() { closeLinkPop(); spec.onSaved(v); })
                    .catch(function() { toast('Invalid URL — must start with https://'); });
            }
        });
    }

    // target is an item row, or { kind: 'artist', id } for the page header's icon.
    function openLinkPop(link, target) {
        var isYt = /YouTube/.test(link.getAttribute('title') || '');
        var kind = target.kind || rowKind(target);
        var id = target.id && target.kind ? target.id : (kind === 'song' ? target.getAttribute('data-song-id') : target.id.slice(6));
        var urlKey = isYt ? 'youtube_url' : 'spotify_url';
        var infoUrl = { song: '/song/' + id + '/info', album: '/album/' + id + '/songs', artist: '/artist/' + id + '/edit-info' }[kind];
        valuePop(link, {
            label: isYt ? 'YouTube link' : 'Spotify link',
            placeholder: isYt ? 'https://youtube.com/…' : 'https://open.spotify.com/…' + (kind === 'song' ? ' (or n/a)' : ''),
            load: function() { return getJSON(infoUrl).then(function(d) { return d && d[urlKey]; }); },
            saveUrl: '/edit/' + kind + '/' + id + '/' + (isYt ? 'youtube-url' : 'spotify-url'),
            onSaved: function() { refreshPage(); softRefreshAfter(); },
            extra: kind !== 'artist' ? null : function(pop, inp) {
                pop.appendChild(btn('Auto-fill Spotify', 'em-btn em-autofill', function() {
                    closeLinkPop();
                    autoPopulateSpotify(id, inp.value.trim());
                }));
            },
        });
    }

    // The header image (or its "+ Image" stand-in) on an artist page or the misc page.
    function openImagePop(anchorEl) {
        var artistId = currentArtistId();
        var current = anchorEl.tagName === 'A' ? anchorEl.getAttribute('href') : '';
        valuePop(anchorEl, {
            label: 'Image link',
            placeholder: 'https://… (cropped to 2:3 portrait)',
            load: function() { return Promise.resolve(current); },
            saveUrl: artistId ? '/edit/artist/' + artistId + '/image-url' : '/misc/set-image',
            onSaved: function(v) {
                if (artistId) { refreshPage(); softRefreshAfter(); return; }
                // The misc header isn't part of any refreshed fragment, so swap the image in place.
                var a;
                if (v) {
                    a = el('a', 'flex-shrink-0');
                    a.href = v; a.target = '_blank'; a.rel = 'noopener'; a.title = 'Open image in new tab';
                    var img = el('img', 'rounded object-cover');
                    img.src = v; img.alt = 'Misc Artists'; img.referrerPolicy = 'no-referrer';
                    img.style.cssText = 'width:3.75rem; height:5.625rem; object-position:center;';
                    a.appendChild(img);
                } else {
                    a = el('span', 'em-img-add flex-shrink-0', '+ Image');
                    a.title = 'Add image';
                }
                a.setAttribute('data-em-image', '');
                anchorEl.replaceWith(a);
            },
        });
    }

    /* ---- events ---- */

    function onPanelKey(e) {
        var t = e.target;
        var leave = e.key === 'Escape' || (e.key === 'Enter' && t.tagName === 'INPUT' && t.type === 'text');
        if (!leave) return;
        e.preventDefault();
        e.stopPropagation();
        t.blur();
    }

    // Capture phase so edit-mode clicks win over the always-on modal openers and link navigation.
    document.addEventListener('click', function(e) {
        if (e.target.closest('.em-toggle') && !_isMobile()) {
            e.preventDefault();
            e.stopPropagation();
            setOn(!on);
            // Duplicates only list in edit mode, so redraw the discography whenever it toggles.
            if (currentArtistId()) refreshPage();
            return;
        }
        if (!on) return;
        if (linkPop && !linkPop.contains(e.target)) closeLinkPop();
        if (e.target.closest('#em-panel, .em-linkpop')) return;
        var pencil = e.target.closest('[data-edit-artist]');
        if (pencil) {
            e.preventDefault();
            e.stopPropagation();
            selectOnly('artist:' + pencil.getAttribute('data-edit-artist'));
            return;
        }
        var img = e.target.closest('[data-em-image]');
        if (img) {
            e.preventDefault();
            e.stopPropagation();
            openImagePop(img);
            return;
        }
        var miscHead = e.target.closest('[data-misc-header] h2');
        if (miscHead) {
            if (!e.target.closest('a, button, input, label, [onclick]')) {
                e.preventDefault();
                e.stopPropagation();
                showMiscEdit();
            }
            return;
        }
        var head = e.target.closest('#discography [data-current-artist-id] h2');
        if (head) {
            var artistId = head.closest('[data-current-artist-id]').getAttribute('data-current-artist-id');
            var spot = e.target.closest('a[title="Spotify"], .spotify-na');
            if (spot) {
                e.preventDefault();
                e.stopPropagation();
                openLinkPop(spot, { kind: 'artist', id: artistId });
            } else if (!e.target.closest('a, button, input, label, [onclick]')) {
                e.preventDefault();
                e.stopPropagation();
                selectOnly('artist:' + artistId);
            }
            return;
        }
        var r = root(), tr = e.target.closest('tr');
        if (!r || !tr || !r.contains(tr) || !isItemRow(tr)) return;
        if (e.target.closest('td[id^="rating-"]')) return;
        var link = e.target.closest('a[title="Spotify"], .spotify-na, a[title="YouTube"], a[title="Search YouTube"]');
        if (link) {
            e.preventDefault();
            e.stopPropagation();
            openLinkPop(link, tr);
            return;
        }
        var key = keyOf(tr);
        if (e.target.classList.contains('em-ck')) {
            e.stopPropagation();
            e.target.blur();
            if (e.shiftKey) checkRange(key); else toggleInSel(key);
            return;
        }
        if (e.target.closest('.collapse-arrow')) return;
        var dup = e.target.closest('.duplicate-tag[data-dup-override]');
        if (dup) {
            e.preventDefault();
            e.stopPropagation();
            var p = dup.getAttribute('data-dup-override').split(':');
            post('/edit/song/' + p[0] + '/duplicate-override', 'album_id=' + p[1] + '&artist_id=' + p[2]).then(okOrThrow)
                .then(function() { toast('Shown under this album outside edit mode'); refreshPage(); })
                .catch(function() { toast('Failed'); });
            return;
        }
        // .mobile-tap handlers only act on mobile, so on desktop they are plain row text.
        var own = e.target.closest('a, button, input, select, textarea, [onclick]:not(.mobile-tap)');
        if (own && own !== tr && tr.contains(own)) return;
        e.preventDefault();
        e.stopPropagation();
        if (e.shiftKey) selectRange(key);
        else if (e.ctrlKey || e.metaKey) toggleInSel(key);
        else selectOnly(key);
    }, true);

    // Shift/Ctrl-click would otherwise drag-select the row text.
    document.addEventListener('mousedown', function(e) {
        if (on && (e.shiftKey || e.ctrlKey || e.metaKey) && e.target.closest && e.target.closest('tr[data-song-id], tr[id^="album-"]')) e.preventDefault();
    }, true);

    document.addEventListener('keydown', function(e) {
        if (!on || e.altKey || e.metaKey || e.ctrlKey) return;
        var a = document.activeElement;
        if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT' || a.isContentEditable)) return;
        if (activeInput || activeNote || activeMobileModal) return;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            move(e.key === 'ArrowDown' ? 1 : -1, e.shiftKey);
        } else if (e.key === 'Enter' && sel.length === 1 && !e.shiftKey) {
            e.preventDefault();
            var t = panel.querySelector('.em-title');
            if (t) { t.focus(); t.select(); }
        } else if (e.key === 'Escape') {
            cur = null;
            clearSel();
        }
    });

    // Content refreshes (own saves, live updates, misc country loads) replace rows; re-apply state.
    var domPending = false;
    function afterDomChange() {
        domPending = false;
        if (!on) return;
        if (!root() || pageArtistId !== currentArtistId()) { setOn(false); return; }
        assignKeys();
        var keys = allRows().map(keyOf), before = sel.join(',');
        sel = sel.filter(function(k) { return kindOf(k) === 'artist' || keys.indexOf(k) !== -1; });
        if (!sel.length) selKind = null;
        if (cur && keys.indexOf(cur) === -1) cur = null;
        decorate();
        if (sel.join(',') !== before) renderPanel(); else softRefreshPanel();
    }
    // Our own refresh can land on the parent's page (an artist converted to a subunit); stay in edit mode there.
    document.addEventListener('htmx:afterSwap', function(e) {
        if (!e.detail || !e.detail.target || e.detail.target.id !== 'discography') return;
        if (ownSwap && on && root()) pageArtistId = currentArtistId();
        ownSwap = false;
    });
    var mc = document.getElementById('main-content');
    if (mc) {
        new MutationObserver(function() {
            if (!on || domPending) return;
            domPending = true;
            requestAnimationFrame(afterDomChange);
        }).observe(mc, { childList: true, subtree: true });
    }

    window.addEventListener('resize', function() {
        if (on && _isMobile()) setOn(false);
        positionPanel();
    });

    window._emRefresh = refreshPage;
})();
