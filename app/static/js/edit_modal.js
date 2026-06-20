/* ============================================================================
   Shared editing-modal component.

   One config-driven modal used at every viewport width to edit any entity
   (artist / album / song / misc-artist), replacing the old desktop edit-mode
   inline editors and the bespoke mobile edit modals. Triggered by always-visible
   green "edit" buttons (see the delegated listener at the bottom of this file).

   openEditModal owns the chrome (backdrop/modal/title/body/footer), the
   info<->edit toggle, the dirty/reload-on-close lifecycle, and a declarative
   field renderer for simple entities (artist). Entities with bespoke UI
   (album song-reorder, song info view) supply renderInfoBody / renderEditBody
   hooks and render through the same chrome and `ui` helpers.

   Depends on helpers from core.js (_csrfHeaders, showBriefToast) and ratings.js
   (closeMobileModal/activeMobileModal, showMobilePicker, showMobilePassword,
   showConfirm), all loaded before this file.
   ============================================================================ */

/* Page-lifetime cache of lookup tables, keyed by URL, shared across modals. */
var _emLookupCache = {};

function _emEnsure(url, cb) {
    if (_emLookupCache[url]) { cb(_emLookupCache[url]); return; }
    fetch(url, { headers: { 'Accept': 'application/json' } })
        .then(function(r) { return r.ok ? r.json() : []; })
        .then(function(rows) { _emLookupCache[url] = rows; cb(rows); })
        .catch(function() { cb([]); });
}

function _emHeaders(extra) {
    return _csrfHeaders(extra || { 'Content-Type': 'application/x-www-form-urlencoded' });
}

function _emToast(msg) {
    if (typeof showBriefToast === 'function') showBriefToast(msg);
}

/* Styled button matching the mobile modals' _btnEl. */
function _emBtn(label, kind) {
    var b = document.createElement('button');
    b.textContent = label;
    var base = 'padding:0.5rem 1rem; font-size:0.875rem; border-radius:0.375rem; cursor:pointer;';
    if (kind === 'primary') b.style.cssText = base + 'background:var(--link,#2563EB); color:#fff; border:none;';
    else if (kind === 'danger') b.style.cssText = base + 'background:var(--delete-button,#DC2626); color:#fff; border:none;';
    else b.style.cssText = base + 'background:var(--bg-primary,#fff); color:var(--text-primary); border:0.0625rem solid var(--border,#ccc);';
    return b;
}

/* Read-only labelled value row (uppercase label / value). */
function _emInfoRow(label, valueNode) {
    var row = document.createElement('div');
    row.style.cssText = 'margin-bottom:0.625rem;';
    var l = document.createElement('div');
    l.textContent = label;
    l.style.cssText = 'font-size:0.6875rem; text-transform:uppercase; letter-spacing:0.03em; color:var(--text-secondary,#6B7280); margin-bottom:0.125rem;';
    row.appendChild(l);
    if (typeof valueNode === 'string' || typeof valueNode === 'number') {
        var v = document.createElement('div');
        v.textContent = (valueNode === '' || valueNode == null) ? '—' : valueNode;
        v.style.cssText = 'font-size:0.875rem; color:var(--text-primary); white-space:pre-wrap; line-height:1.4; word-wrap:break-word;';
        row.appendChild(v);
    } else {
        row.appendChild(valueNode);
    }
    return row;
}

/* Labelled <input>/<textarea> appended to a container; used by the declarative renderer. */
function _emLabeledInput(container, field, data) {
    var l = document.createElement('div');
    l.textContent = field.label;
    l.style.cssText = 'font-size:0.75rem; color:var(--text-secondary,#6B7280); margin-bottom:0.25rem;';
    container.appendChild(l);
    var inp = field.type === 'textarea' ? document.createElement('textarea') : document.createElement('input');
    if (field.type === 'textarea') inp.rows = 3; else inp.type = 'text';
    inp.value = data[field.key] || '';
    if (field.placeholder) inp.placeholder = field.placeholder;
    inp.style.cssText = 'width:100%; border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; padding:0.5rem; font-size:0.875rem; font-family:inherit; background:var(--bg-primary,#fff); color:var(--text-primary); box-sizing:border-box;' + (field.hint ? '' : ' margin-bottom:0.75rem;');
    container.appendChild(inp);
    if (field.hint) {
        var h = document.createElement('div');
        h.textContent = field.hint;
        h.style.cssText = 'font-size:0.6875rem; color:var(--text-secondary,#6B7280); margin-top:0.25rem; margin-bottom:0.75rem;';
        container.appendChild(h);
    }
    return inp;
}

/* One text box per name, with add/remove buttons. data[field.key] is a string[].
   Returns { collect } yielding the trimmed, de-duped (case-insensitive) names. */
function _emNameListField(container, field, data) {
    var l = document.createElement('div');
    l.textContent = field.label;
    l.style.cssText = 'font-size:0.75rem; color:var(--text-secondary,#6B7280); margin-bottom:0.25rem;';
    container.appendChild(l);
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex; flex-direction:column; gap:0.375rem; margin-bottom:0.5rem;';
    container.appendChild(wrap);
    function addRow(name) {
        var row = document.createElement('div');
        row.style.cssText = 'display:flex; gap:0.375rem; align-items:center;';
        var inp = document.createElement('input');
        inp.type = 'text'; inp.value = name || ''; inp.placeholder = field.placeholder || 'Alternate name';
        inp.className = 'namelist-name';
        inp.style.cssText = 'flex:1; min-width:0; border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; padding:0.375rem 0.5rem; font-size:0.875rem; background:var(--bg-primary,#fff); color:var(--text-primary); box-sizing:border-box;';
        var del = _emBtn('✕', 'secondary');
        del.style.padding = '0.375rem 0.625rem';
        del.onclick = function() { wrap.removeChild(row); };
        row.appendChild(inp); row.appendChild(del);
        wrap.appendChild(row);
    }
    (data[field.key] || []).forEach(function(n) { addRow(n); });
    var addBtn = _emBtn('+ Add name', 'secondary');
    addBtn.style.cssText += 'margin-bottom:0.75rem;';
    addBtn.onclick = function() { addRow(''); };
    container.appendChild(addBtn);
    return {
        collect: function() {
            var out = [], seen = {};
            var rows = wrap.children;
            for (var i = 0; i < rows.length; i++) {
                var nm = rows[i].querySelector('.namelist-name');
                if (!nm) continue;
                var v = nm.value.trim();
                if (!v) continue;
                var key = v.toLowerCase();
                if (seen[key]) continue;
                seen[key] = 1;
                out.push(v);
            }
            return out;
        }
    };
}

/* ----------------------------------------------------------------------------
   openEditModal(config) — see file header for the config schema.
   ---------------------------------------------------------------------------- */
function openEditModal(config) {
    closeMobileModal();

    var data = {};
    var dirty = false;
    function markDirty() { dirty = true; }

    var backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:200; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; padding:1rem;';
    var modal = document.createElement('div');
    modal.style.cssText = 'background:var(--bg-secondary,#fff); border:0.0625rem solid var(--border,#ccc); border-radius:0.5rem; padding:1rem; width:100%; max-width:21.25rem; max-height:85vh; display:flex; flex-direction:column; box-shadow:0 0.25rem 1rem rgba(0,0,0,0.3);';

    var title = document.createElement('div');
    title.style.cssText = 'font-size:1rem; font-weight:600; color:var(--text-primary); margin-bottom:0.75rem; word-wrap:break-word;';
    modal.appendChild(title);
    var bodyArea = document.createElement('div');
    bodyArea.style.cssText = 'overflow-y:auto; flex:1; padding-right:1.25rem; margin-right:-0.75rem; scrollbar-gutter:stable;';
    bodyArea.textContent = 'Loading…';
    modal.appendChild(bodyArea);
    var footerArea = document.createElement('div');
    footerArea.style.cssText = 'margin-top:0.875rem; flex-shrink:0;';
    modal.appendChild(footerArea);

    function doClose() {
        if (dirty) {
            if (typeof config.onDirtyClose === 'function') { config.onDirtyClose(data); return; }
            window.location.reload();
        } else {
            closeMobileModal();
        }
    }

    function _titleText() { return config.title ? config.title(data) : (data.name || ''); }

    var ui = {
        markDirty: markDirty,
        headers: _emHeaders,
        toast: _emToast,
        btn: _emBtn,
        ensure: _emEnsure,
        infoRow: _emInfoRow,
        labeledInput: _emLabeledInput,
        nameListField: _emNameListField,
        close: closeMobileModal,
        doClose: doClose,
        reload: function() { window.location.reload(); },
        showInfo: function() { renderInfo(); },
        showEdit: function() { renderEdit(); },
    };

    /* ---- default declarative renderers (artist) ---- */
    var VALUE_TYPES = { text: 1, url: 1, date: 1, textarea: 1 };

    function _saveValueField(field, inputEl) {
        var v = inputEl.value;
        if (field.type !== 'textarea') v = v.trim();
        var prev = data[field.key] || '';
        if (v === prev) return null;
        if (field.type === 'text' && !v) return null;
        var body = field.payload ? field.payload(v) : ('value=' + encodeURIComponent(v));
        return fetch(field.endpoint, { method: 'POST', headers: _emHeaders(), body: body })
            .then(function(r) {
                if (r.ok) { data[field.key] = v; dirty = true; }
                else if (field.errorMsg) _emToast(field.errorMsg);
            });
    }

    function _saveNameListField(field, widget) {
        var names = widget.collect();
        var prev = data[field.key] || [];
        var unchanged = names.length === prev.length && names.every(function(n, i) { return n === prev[i]; });
        if (unchanged) return null;
        var body = 'value=' + encodeURIComponent(names.join('\n'));
        return fetch(field.endpoint, { method: 'POST', headers: _emHeaders(), body: body })
            .then(function(r) { if (r.ok) { data[field.key] = names; dirty = true; } });
    }

    function _booleanRow(field) {
        var lab = document.createElement('label');
        lab.style.cssText = 'display:flex; align-items:center; gap:0.5rem; font-size:0.875rem; color:var(--text-primary); margin-bottom:0.5rem; cursor:pointer;';
        var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!data[field.key]; cb.style.cssText = 'cursor:pointer;';
        cb.onchange = function() {
            var body = field.payload ? field.payload(cb.checked) : ('value=' + (cb.checked ? '1' : '0'));
            fetch(field.endpoint, { method: 'POST', headers: _emHeaders(), body: body })
                .then(function(r) { if (r.ok) { data[field.key] = cb.checked; dirty = true; } else { cb.checked = !cb.checked; _emToast('Failed'); } });
        };
        var sp = document.createElement('span'); sp.textContent = field.label;
        lab.appendChild(cb); lab.appendChild(sp);
        bodyArea.appendChild(lab);
    }

    function _pickerField(field, actWrap) {
        var b = _emBtn(field.label, 'secondary');
        b.onclick = function() {
            if (field.type === 'multiselect') {
                _emEnsure(field.lookupUrl, function(opts) {
                    showMobilePicker({ title: field.label, mode: 'multiselect',
                        options: opts.map(function(o) { return { id: o.id, label: o.name }; }),
                        selectedIds: (data[field.idsKey] || []),
                        onDone: function(ids) {
                            var param = (field.paramName || 'ids') + '=' + ids.join(',');
                            fetch(field.endpoint, { method: 'POST', headers: _emHeaders(), body: param })
                                .then(function(r) { return r.ok ? r.json() : null; })
                                .then(function(res) { if (res) { data[field.key] = res; data[field.idsKey] = ids; dirty = true; } });
                        } });
                });
                return;
            }
            _emEnsure(field.lookupUrl, function(opts) {
                var mapped = opts.map(function(o) { return { id: o.id, label: o.name, selected: o.id === data[field.idKey] }; });
                if (field.type === 'user') {
                    mapped = [{ id: '', label: '— None —', selected: !data[field.idKey] }].concat(mapped);
                }
                showMobilePicker({ title: field.label, mode: 'select', options: mapped,
                    onSelect: function(o) {
                        var idVal = (o.id === '' ? '' : o.id);
                        var param = field.type === 'user' ? ('user_id=' + idVal) : (field.idParam + '=' + idVal);
                        fetch(field.endpoint, { method: 'POST', headers: _emHeaders(), body: param })
                            .then(function(r) { if (r.ok) {
                                data[field.key] = (o.id === '' ? '' : o.label);
                                data[field.idKey] = (o.id === '' ? null : o.id);
                                dirty = true;
                            } });
                    } });
            });
        };
        actWrap.appendChild(b);
    }

    function _defaultEditBody() {
        var fields = config.fields || [];
        var valueInputs = [];
        var nameLists = [];
        fields.forEach(function(field) {
            if (VALUE_TYPES[field.type]) valueInputs.push({ field: field, input: _emLabeledInput(bodyArea, field, data) });
            else if (field.type === 'namelist') nameLists.push({ field: field, widget: _emNameListField(bodyArea, field, data) });
        });
        if (valueInputs.length || nameLists.length) {
            var saveRow = document.createElement('div');
            saveRow.style.cssText = 'display:flex; gap:0.5rem; justify-content:flex-end; margin-bottom:0.625rem;';
            var cancelBtn = _emBtn('Cancel', 'secondary'); cancelBtn.onclick = renderInfo;
            var saveBtn = _emBtn('Save', 'primary');
            saveBtn.onclick = function() {
                var promises = [];
                valueInputs.forEach(function(vi) { var p = _saveValueField(vi.field, vi.input); if (p) promises.push(p); });
                nameLists.forEach(function(nl) { var p = _saveNameListField(nl.field, nl.widget); if (p) promises.push(p); });
                Promise.all(promises).then(renderInfo);
            };
            saveRow.appendChild(cancelBtn); saveRow.appendChild(saveBtn);
            bodyArea.appendChild(saveRow);
        }
        fields.forEach(function(field) { if (field.type === 'boolean') _booleanRow(field); });

        var pickerFields = fields.filter(function(f) { return f.type === 'select' || f.type === 'user' || f.type === 'multiselect'; });
        var actions = typeof config.actions === 'function' ? config.actions(data) : (config.actions || []);
        if (pickerFields.length || actions.length) {
            bodyArea.appendChild(_sep());
            bodyArea.appendChild(_actionsLabel());
            var actWrap = document.createElement('div');
            actWrap.style.cssText = 'display:flex; flex-wrap:wrap; gap:0.5rem;';
            bodyArea.appendChild(actWrap);
            pickerFields.forEach(function(field) { _pickerField(field, actWrap); });
            actions.forEach(function(act) { actWrap.appendChild(_actionBtn(act)); });
        }
    }

    function _sep() {
        var sep = document.createElement('div');
        sep.style.cssText = 'border-top:0.0625rem solid var(--border,#ccc); margin:0.5rem 0 0.625rem;';
        return sep;
    }
    function _actionsLabel() {
        var l = document.createElement('div');
        l.textContent = 'Actions';
        l.style.cssText = 'font-size:0.6875rem; text-transform:uppercase; letter-spacing:0.03em; color:var(--text-secondary,#6B7280); margin-bottom:0.5rem;';
        return l;
    }
    function _actionBtn(act) {
        var b = _emBtn(act.label, act.kind || 'secondary');
        b.onclick = function() {
            var ctx = { id: config.id, data: data, close: closeMobileModal, markDirty: markDirty, toast: _emToast };
            if (act.confirm) {
                showMobilePassword({ title: act.confirm.title,
                    message: typeof act.confirm.message === 'function' ? act.confirm.message(data) : act.confirm.message,
                    confirmLabel: act.confirm.confirmLabel || 'Confirm',
                    onConfirm: function(pw, helpers) { act.run(ctx, pw, helpers); } });
            } else {
                act.run(ctx);
            }
        };
        return b;
    }

    /* ---- view orchestration ---- */
    function renderInfo() {
        title.textContent = _titleText();
        bodyArea.innerHTML = '';
        if (config.renderInfoBody) {
            config.renderInfoBody(bodyArea, data, ui);
        } else {
            (config.infoRows ? config.infoRows(data) : []).forEach(function(pair) {
                if (pair) bodyArea.appendChild(_emInfoRow(pair[0], pair[1]));
            });
        }
        footerArea.innerHTML = '';
        var f = document.createElement('div');
        f.style.cssText = 'display:flex; align-items:center;';
        var editBtn = _emBtn('Edit', 'secondary');
        editBtn.onclick = renderEdit;
        f.appendChild(editBtn);
        var sp = document.createElement('div'); sp.style.cssText = 'flex:1;'; f.appendChild(sp);
        var closeBtn = _emBtn('Close', 'secondary');
        closeBtn.onclick = doClose;
        f.appendChild(closeBtn);
        footerArea.appendChild(f);
    }

    function renderEdit() {
        title.textContent = _titleText();
        bodyArea.innerHTML = '';
        footerArea.innerHTML = '';
        if (config.renderEditBody) config.renderEditBody(bodyArea, data, ui);
        else _defaultEditBody();
    }

    config.loader(function(d) {
        if (!d) { bodyArea.textContent = 'Failed to load.'; return; }
        data = d;
        if (config.startEdit) renderEdit(); else renderInfo();
    });

    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    activeMobileModal = backdrop;
    backdrop.addEventListener('click', function(e) { if (e.target === backdrop) doClose(); });
}

/* ============================================================================
   Config factories — one per entity.
   ============================================================================ */

function artistEditConfig(artistId) {
    var id = artistId;
    var pfx = '/edit/artist/' + id;
    return {
        entity: 'artist', id: id,
        startEdit: true,
        loader: function(done) {
            fetch('/artist/' + id + '/edit-info', { headers: { 'Accept': 'application/json' } })
                .then(function(r) { return r.ok ? r.json() : null; })
                .then(function(d) {
                    if (!d) { done(null); return; }
                    done({
                        name: d.name || '', spotify_url: d.spotify_url || '',
                        image_url: d.image_url || '',
                        gender_id: d.gender_id, gender: d.gender || '',
                        country_id: d.country_id, country: d.country || '',
                        owner_id: d.owner_id, owner: d.owner || '',
                        maintainer_id: d.maintainer_id, maintainer: d.maintainer || '',
                        is_disbanded: !!d.is_disbanded, is_complete: !!d.is_complete, is_tracked: !!d.is_tracked,
                        alt_names: d.alt_names || [],
                        links: d.links || [],
                    });
                })
                .catch(function() { done(null); });
        },
        infoRows: function(data) {
            var flags = [];
            if (data.is_disbanded) flags.push('Inactive');
            if (data.is_complete) flags.push('Complete');
            if (data.is_tracked) flags.push('Tracked');
            var altNames = data.alt_names || [];
            return [
                ['Gender', data.gender], ['Country', data.country],
                ['Owner', data.owner], ['Maintainer', data.maintainer],
                altNames.length ? ['Alternate Names', altNames.join(', ')] : null,
                flags.length ? ['Status', flags.join(', ')] : null,
            ];
        },
        fields: [
            { type: 'text', key: 'name', label: 'Artist Name', endpoint: pfx + '/name' },
            { type: 'namelist', key: 'alt_names', label: 'Alternate Names', endpoint: pfx + '/alt-names' },
            { type: 'url', key: 'spotify_url', label: 'Spotify URL', placeholder: 'https://open.spotify.com/…', endpoint: pfx + '/spotify-url', errorMsg: 'Invalid URL' },
            { type: 'url', key: 'image_url', label: 'Image URL', placeholder: 'https://…', hint: 'Cropped to a 2:3 portrait ratio (centered) and shown at 60×90. Larger images are scaled down.', endpoint: pfx + '/image-url', errorMsg: 'Invalid URL' },
            { type: 'boolean', key: 'is_disbanded', label: 'Inactive', endpoint: pfx + '/is-disbanded' },
            { type: 'boolean', key: 'is_complete', label: 'Complete', endpoint: pfx + '/is-complete' },
            { type: 'boolean', key: 'is_tracked', label: 'Tracked', endpoint: pfx + '/is-tracked' },
            { type: 'select', key: 'gender', idKey: 'gender_id', idParam: 'gender_id', label: 'Gender', endpoint: pfx + '/gender', lookupUrl: '/lookups/genders' },
            { type: 'select', key: 'country', idKey: 'country_id', idParam: 'country_id', label: 'Country', endpoint: pfx + '/country', lookupUrl: '/lookups/countries' },
        ],
        actions: function(data) {
            var links = data.links || [];
            var isSubunit = links.some(function(l) { return l.rel === 'subunit'; });
            var soloistLinks = links.filter(function(l) { return l.rel === 'soloist'; });
            function swapRole(to) {
                fetch(pfx + '/swap-role', { method: 'POST', headers: _emHeaders(), body: 'to=' + to })
                    .then(function(r) {
                        if (r.ok) { closeMobileModal(); window.location.reload(); }
                        else { r.text().then(function(t) { _emToast(t || 'Could not convert artist'); }); }
                    });
            }
            var acts = [
                { label: '+ Add album', run: function() { closeMobileModal(); if (typeof resetAddAlbumModal === 'function') resetAddAlbumModal(); var m = document.getElementById('add-album-modal'); if (m) m.style.display = 'flex'; } },
            ];
            if (isSubunit) {
                acts.push({ label: 'Convert to soloist', run: function() { swapRole('soloist'); } });
            } else if (soloistLinks.length >= 1) {
                // Single-parent soloist can be swapped to a subunit; multi-parent soloists
                // cannot (a subunit may only have one parent).
                if (soloistLinks.length === 1) {
                    acts.push({ label: 'Convert to subunit', run: function() { swapRole('subunit'); } });
                }
                acts.push({ label: 'Add as soloist of another group', run: function() { closeMobileModal(); if (typeof showConvertArtist === 'function') showConvertArtist('soloist'); } });
            } else {
                acts.push({ label: 'Convert to subunit', run: function() { closeMobileModal(); if (typeof showConvertArtist === 'function') showConvertArtist('subunit'); } });
                acts.push({ label: 'Convert to soloist', run: function() { closeMobileModal(); if (typeof showConvertArtist === 'function') showConvertArtist('soloist'); } });
            }
            acts.push({ label: 'Link related group', run: function() { closeMobileModal(); if (typeof showConvertArtist === 'function') showConvertArtist('related'); } });
            acts.push.apply(acts, [
                { label: 'Manage genres', run: function(ctx) { closeMobileModal(); if (typeof showBulkGenreModal === 'function') showBulkGenreModal(id, ctx.data.name); } },
                { label: 'Auto-fill Spotify', run: function(ctx) { if (typeof autoPopulateSpotify === 'function') autoPopulateSpotify(id, ctx && ctx.data ? ctx.data.spotify_url : null); } },
            ]);
            (data.links || []).forEach(function(lnk) {
                acts.push({ label: 'Unlink: ' + lnk.name, kind: 'danger',
                    confirm: { title: 'Unlink from ' + lnk.name + '?', confirmLabel: 'Unlink',
                        message: 'Removes the ' + lnk.rel + ' link to "' + lnk.name + '". Their songs and albums are unaffected. Enter your password to confirm.' },
                    run: function(ctx, pw, helpers) {
                        fetch(pfx + '/unlink?parent_id=' + lnk.id, { method: 'POST', headers: _emHeaders(), body: 'password=' + encodeURIComponent(pw), redirect: 'manual' })
                            .then(function(r) { if (r.status === 403) { helpers.error('Incorrect password.'); return; } helpers.close(); window.location.reload(); });
                    } });
            });
            acts.push({ label: 'Delete artist', kind: 'danger',
                confirm: { title: 'Delete artist?', confirmLabel: 'Delete',
                    message: function(d) { return '"' + d.name + '" and all related data will be permanently deleted. Enter your password to confirm.'; } },
                run: function(ctx, pw, helpers) {
                    fetch(pfx + '/delete', { method: 'POST', headers: _emHeaders(), body: 'password=' + encodeURIComponent(pw), redirect: 'manual' })
                        .then(function(r) { if (r.status === 403) { helpers.error('Incorrect password.'); return; } helpers.close(); window.location = '/'; });
                } });
            return acts;
        },
        onDirtyClose: 'reload',
    };
}

function albumEditConfig(albumId, albumName) {
    var id = albumId;
    var pfx = '/edit/album/' + id;
    return {
        entity: 'album', id: id,
        title: function(data) { return data.name; },
        loader: function(done) {
            fetch('/album/' + id + '/songs', { headers: { 'Accept': 'application/json' } })
                .then(function(r) { return r.ok ? r.json() : null; })
                .then(function(d) {
                    if (!d) { done(null); return; }
                    done({
                        name: d.album_name || albumName || '',
                        release_date: d.release_date || '', album_type: d.album_type || '',
                        album_type_id: d.album_type_id || null, spotify_url: d.spotify_url || '',
                        genres: d.genres || [], genre_ids: d.genre_ids || [], songs: d.songs || [],
                        alt_names: d.alt_names || [],
                    });
                })
                .catch(function() { done(null); });
        },
        renderInfoBody: function(bodyArea, data, ui) {
            var metaBits = [];
            if (data.release_date) metaBits.push(data.release_date.slice(0, 4));
            if (data.album_type) metaBits.push(data.album_type);
            if (data.genres.length) metaBits.push(data.genres.join(', '));
            if (metaBits.length) {
                var meta = document.createElement('div');
                meta.textContent = metaBits.join(' · ');
                meta.style.cssText = 'font-size:0.75rem; color:var(--text-secondary,#6B7280); margin-bottom:0.625rem;';
                bodyArea.appendChild(meta);
            }
            if (data.alt_names && data.alt_names.length) {
                bodyArea.appendChild(ui.infoRow('Alternate Names', data.alt_names.join(', ')));
            }
            if (data.songs.length) {
                var listWrap = document.createElement('div');
                data.songs.forEach(function(song, i) {
                    var row = document.createElement('div');
                    row.style.cssText = 'display:flex; gap:0.5rem; font-size:0.875rem; color:var(--text-primary); padding:0.1875rem 0; align-items:baseline;';
                    var num = document.createElement('span');
                    num.textContent = (i + 1) + '.';
                    num.style.cssText = 'color:var(--text-secondary,#6B7280); font-size:0.75rem; flex-shrink:0; min-width:1.125rem;';
                    var tags = [];
                    if (song.is_lead) tags.push('★ lead');
                    if (song.is_promoted) tags.push('promoted');
                    if (song.is_remix) tags.push('remix');
                    if (song.is_cover) tags.push('cover');
                    var nm = document.createElement('span');
                    nm.textContent = song.name + (tags.length ? '  (' + tags.join(', ') + ')' : '');
                    row.appendChild(num); row.appendChild(nm);
                    listWrap.appendChild(row);
                });
                bodyArea.appendChild(listWrap);
            }
        },
        renderEditBody: function(bodyArea, data, ui) {
            var songs = data.songs;
            var songListContainer = null;

            var nameInput = ui.labeledInput(bodyArea, { label: 'Album Name', key: 'name' }, data);
            var dateInput = ui.labeledInput(bodyArea, { label: 'Release Date', key: 'release_date', placeholder: 'YYYY-MM-DD' }, data);
            var spotifyInput = ui.labeledInput(bodyArea, { label: 'Spotify URL', key: 'spotify_url', placeholder: 'https://open.spotify.com/…' }, data);
            var altWidget = ui.nameListField(bodyArea, { key: 'alt_names', label: 'Alternate Names', endpoint: pfx + '/alt-names' }, data);

            var saveRow = document.createElement('div');
            saveRow.style.cssText = 'display:flex; gap:0.5rem; justify-content:flex-end; margin-bottom:0.375rem;';
            var cancelBtn = ui.btn('Cancel', 'secondary'); cancelBtn.onclick = ui.showInfo;
            var saveBtn = ui.btn('Save', 'primary');
            saveBtn.onclick = function() {
                var promises = [];
                if (nameInput.value.trim() && nameInput.value.trim() !== data.name) {
                    promises.push(fetch(pfx + '/name', { method: 'POST', headers: ui.headers(), body: 'value=' + encodeURIComponent(nameInput.value.trim()) })
                        .then(function(r) { if (r.ok) { data.name = nameInput.value.trim(); ui.markDirty(); } }));
                }
                if (dateInput.value.trim() !== data.release_date) {
                    promises.push(fetch(pfx + '/release-date', { method: 'POST', headers: ui.headers(), body: 'value=' + encodeURIComponent(dateInput.value.trim()) })
                        .then(function(r) { if (r.ok) { data.release_date = dateInput.value.trim(); ui.markDirty(); } else ui.toast('Invalid date'); }));
                }
                if (spotifyInput.value.trim() !== data.spotify_url) {
                    promises.push(fetch(pfx + '/spotify-url', { method: 'POST', headers: ui.headers(), body: 'value=' + encodeURIComponent(spotifyInput.value.trim()) })
                        .then(function(r) { if (r.ok) { data.spotify_url = spotifyInput.value.trim(); ui.markDirty(); } else ui.toast('Invalid URL'); }));
                }
                var altNames = altWidget.collect();
                var prevAlt = data.alt_names || [];
                var altChanged = altNames.length !== prevAlt.length || altNames.some(function(n, i) { return n !== prevAlt[i]; });
                if (altChanged) {
                    promises.push(fetch(pfx + '/alt-names', { method: 'POST', headers: ui.headers(), body: 'value=' + encodeURIComponent(altNames.join('\n')) })
                        .then(function(r) { if (r.ok) { data.alt_names = altNames; ui.markDirty(); } }));
                }
                Promise.all(promises).then(ui.showInfo);
            };
            saveRow.appendChild(cancelBtn); saveRow.appendChild(saveBtn);
            bodyArea.appendChild(saveRow);

            function reorder(idx, dir) {
                var cur = songs[idx];
                var target = dir === 'up' ? songs[idx - 1] : songs[idx + 1];
                if (!cur || !target) return;
                fetch(pfx + '/move-song', { method: 'POST', headers: ui.headers(),
                    body: 'song_id=' + cur.id + '&target_song_id=' + target.id + '&direction=' + (dir === 'up' ? 'before' : 'after') })
                    .then(function(r) { if (!r.ok) throw new Error('failed');
                        ui.markDirty();
                        songs.splice(idx, 1);
                        songs.splice(dir === 'up' ? idx - 1 : idx + 1, 0, cur);
                        if (songListContainer) renderSongList(songListContainer);
                    }).catch(function() { ui.toast('Reorder failed — try again'); });
            }
            function toggleFlag(song, field, checkbox) {
                fetch('/edit/song/' + song.id + '/is-' + field, { method: 'POST', headers: ui.headers(), body: 'checked=' + (checkbox.checked ? 'true' : '') })
                    .then(function(r) { if (!r.ok) throw new Error('failed');
                        ui.markDirty();
                        song['is_' + field] = checkbox.checked;
                        if (field === 'promoted' && !checkbox.checked) { song.is_lead = false; if (songListContainer) renderSongList(songListContainer); }
                    }).catch(function() { checkbox.checked = !checkbox.checked; ui.toast('Failed to save — try again'); });
            }
            function toggleLead(song) {
                fetch('/edit/song/' + song.id + '/is-lead', { method: 'POST', headers: ui.headers() })
                    .then(function(r) { if (!r.ok) throw new Error('failed'); return r.json(); })
                    .then(function(d) { ui.markDirty(); song.is_lead = d.is_lead; song.is_promoted = d.is_promoted; if (songListContainer) renderSongList(songListContainer); })
                    .catch(function() { ui.toast('Failed to save — try again'); });
            }
            function _leadStar(song) {
                var star = document.createElement('span');
                star.textContent = '★'; star.title = 'Lead track';
                star.setAttribute('role', 'checkbox'); star.setAttribute('aria-checked', song.is_lead ? 'true' : 'false');
                star.style.cssText = 'cursor:pointer; font-size:1.1875rem; line-height:1; padding:0.125rem 0.25rem; color:' + (song.is_lead ? 'var(--lead-song,#f5a623)' : '#888') + ';';
                star.onclick = function() { toggleLead(song); };
                return star;
            }
            function _chevron(glyph, enabled, onclick) {
                var b = document.createElement('button');
                b.innerHTML = glyph; b.disabled = !enabled;
                b.style.cssText = 'width:1.75rem; height:1.5rem; line-height:1; font-size:0.75rem; border:0.0625rem solid var(--border,#ccc); border-radius:0.25rem; background:var(--bg-primary,#fff); color:var(--text-primary); cursor:' + (enabled ? 'pointer' : 'default') + '; opacity:' + (enabled ? '1' : '0.35') + ';';
                if (enabled) b.onclick = onclick;
                return b;
            }
            function _flagToggle(song, label, field) {
                var wrap = document.createElement('label');
                wrap.style.cssText = 'display:inline-flex; align-items:center; gap:0.25rem; font-size:0.75rem; color:var(--text-primary); cursor:pointer;';
                var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!song['is_' + field]; cb.style.cssText = 'cursor:pointer;';
                cb.onchange = function() { toggleFlag(song, field, cb); };
                var txt = document.createElement('span'); txt.textContent = label;
                wrap.appendChild(cb); wrap.appendChild(txt);
                return wrap;
            }
            function renderSongList(container) {
                container.innerHTML = '';
                if (!songs.length) {
                    var empty = document.createElement('div');
                    empty.textContent = 'No songs in this album.';
                    empty.style.cssText = 'font-size:0.8125rem; color:var(--text-secondary,#6B7280);';
                    container.appendChild(empty); return;
                }
                songs.forEach(function(song, i) {
                    var card = document.createElement('div');
                    card.style.cssText = 'border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; padding:0.5rem; margin-bottom:0.5rem;';
                    var top = document.createElement('div');
                    top.style.cssText = 'display:flex; align-items:center; gap:0.375rem;';
                    var reorderBox = document.createElement('div');
                    reorderBox.style.cssText = 'display:flex; gap:0.1875rem; flex-shrink:0;';
                    reorderBox.appendChild(_chevron('&#9650;', i > 0, function() { reorder(i, 'up'); }));
                    reorderBox.appendChild(_chevron('&#9660;', i < songs.length - 1, function() { reorder(i, 'down'); }));
                    top.appendChild(reorderBox);
                    var name = document.createElement('div');
                    name.textContent = song.name;
                    name.style.cssText = 'flex:1; font-size:0.875rem; font-weight:500; color:var(--text-primary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
                    top.appendChild(name);
                    card.appendChild(top);
                    var flags = document.createElement('div');
                    flags.style.cssText = 'display:flex; flex-wrap:wrap; align-items:center; gap:0.375rem; margin-top:0.5rem; padding-left:0.125rem;';
                    flags.appendChild(_leadStar(song));
                    var flagGroup = document.createElement('div');
                    flagGroup.style.cssText = 'display:flex; flex-wrap:wrap; align-items:center; gap:0.75rem;';
                    flagGroup.appendChild(_flagToggle(song, 'Promoted', 'promoted'));
                    flagGroup.appendChild(_flagToggle(song, 'Remix', 'remix'));
                    flagGroup.appendChild(_flagToggle(song, 'Cover', 'cover'));
                    flags.appendChild(flagGroup);
                    card.appendChild(flags);
                    container.appendChild(card);
                });
            }

            if (songs.length) {
                var songsSep = document.createElement('div');
                songsSep.style.cssText = 'border-top:0.0625rem solid var(--border,#ccc); margin:0.875rem 0 0.625rem;';
                bodyArea.appendChild(songsSep);
                var songsLabel = document.createElement('div');
                songsLabel.textContent = 'Songs';
                songsLabel.style.cssText = 'font-size:0.6875rem; text-transform:uppercase; letter-spacing:0.03em; color:var(--text-secondary,#6B7280); margin-bottom:0.5rem;';
                bodyArea.appendChild(songsLabel);
                var songsWrap = document.createElement('div');
                bodyArea.appendChild(songsWrap);
                songListContainer = songsWrap;
                renderSongList(songsWrap);
            }

            var sep = document.createElement('div');
            sep.style.cssText = 'border-top:0.0625rem solid var(--border,#ccc); margin:0.875rem 0 0.625rem;';
            bodyArea.appendChild(sep);
            var actLabel = document.createElement('div');
            actLabel.textContent = 'Actions';
            actLabel.style.cssText = 'font-size:0.6875rem; text-transform:uppercase; letter-spacing:0.03em; color:var(--text-secondary,#6B7280); margin-bottom:0.5rem;';
            bodyArea.appendChild(actLabel);
            var actWrap = document.createElement('div');
            actWrap.style.cssText = 'display:flex; flex-wrap:wrap; gap:0.5rem;';
            bodyArea.appendChild(actWrap);
            function _act(label, kind, fn) { var b = ui.btn(label, kind || 'secondary'); b.onclick = fn; actWrap.appendChild(b); }

            _act('Edit genres', 'secondary', function() {
                ui.ensure('/lookups/genres', function(opts) {
                    showMobilePicker({ title: 'Album genres', mode: 'multiselect',
                        options: opts.map(function(g) { return { id: g.id, label: g.name }; }),
                        selectedIds: data.genre_ids,
                        onDone: function(ids) {
                            fetch(pfx + '/genres', { method: 'POST', headers: ui.headers(), body: 'genre_ids=' + ids.join(',') })
                                .then(function(r) { return r.ok ? r.json() : null; })
                                .then(function(names) { if (names) { data.genres = names; data.genre_ids = ids; ui.markDirty(); } });
                        } });
                });
            });
            _act('Edit type', 'secondary', function() {
                ui.ensure('/lookups/album-types', function(opts) {
                    showMobilePicker({ title: 'Album type', mode: 'select',
                        options: opts.map(function(t) { return { id: t.id, label: t.name, selected: t.id === data.album_type_id }; }),
                        onSelect: function(o) {
                            fetch(pfx + '/type', { method: 'POST', headers: ui.headers(), body: 'album_type_id=' + o.id })
                                .then(function(r) { if (r.ok) { data.album_type = o.label; data.album_type_id = o.id; ui.markDirty(); } });
                        } });
                });
            });
            _act('Add song', 'secondary', function() {
                showMobilePicker({ title: 'Add which song?', mode: 'search', placeholder: 'Search songs…',
                    searchUrl: function(q) { return pfx + '/search-songs?q=' + encodeURIComponent(q); },
                    mapItems: function(d) { return d.map(function(s) { return { id: s.id, label: s.name + ' — ' + s.artist }; }); },
                    onSelect: function(item) {
                        fetch(pfx + '/add-song', { method: 'POST', headers: ui.headers(), body: 'song_id=' + item.id })
                            .then(function(r) { if (r.ok) window.location.reload(); else ui.toast('Add failed'); });
                    } });
            });
            _act('Move songs to artist', 'secondary', function() {
                var srcEl = document.querySelector('[data-current-artist-id]');
                var sourceId = srcEl ? srcEl.getAttribute('data-current-artist-id') : null;
                if (!sourceId) { ui.toast('Could not determine current artist'); return; }
                showMobilePicker({ title: 'Move all songs to…', mode: 'search', placeholder: 'Search artists…',
                    searchUrl: function(q) { return '/misc/search-real-artists?q=' + encodeURIComponent(q); },
                    mapItems: function(d) { return d.map(function(a) { return { id: a.artist_id, label: a.name }; }); },
                    onSelect: function(item) {
                        fetch(pfx + '/move-artist', { method: 'POST', headers: ui.headers(), body: 'source_artist_id=' + sourceId + '&target_artist_id=' + item.id })
                            .then(function(r) { if (r.ok) window.location.reload(); else ui.toast('Move failed'); });
                    } });
            });
            _act('Delete album', 'danger', function() {
                fetch(pfx + '/delete-info', { headers: { 'Accept': 'application/json' } })
                    .then(function(r) { return r.ok ? r.json() : null; })
                    .then(function(info) {
                        var opts = { title: 'Delete album?',
                            message: '"' + data.name + '" and its songs/ratings may be permanently deleted. Enter your password to confirm.',
                            confirmLabel: 'Delete',
                            onConfirm: function(pw, helpers) {
                                fetch(pfx + '/delete', { method: 'POST', headers: ui.headers(), body: 'password=' + encodeURIComponent(pw), redirect: 'manual' })
                                    .then(function(r) { if (r.status === 403) { helpers.error('Incorrect password.'); return; } helpers.close(); window.location.reload(); });
                            } };
                        if (info && info.other_artist_songs > 0) {
                            var n = info.other_artist_songs;
                            var names = (info.other_artists || []);
                            opts.checkboxLabel = 'I acknowledge this also permanently deletes ' + n + ' song' + (n === 1 ? '' : 's') +
                                (names.length === 1 ? ' belonging to another artist' : ' belonging to other artists') +
                                (names.length ? ' (' + names.join(', ') + ')' : '') + '.';
                        }
                        showMobilePassword(opts);
                    });
            });
        },
        onDirtyClose: 'reload',
    };
}

/* ============================================================================
   Delegated trigger — always-visible green ".edit-btn" buttons carry
   data-edit-entity / data-edit-id (+ data-edit-name for albums). Survives HTMX
   re-renders since the listener lives on document.
   ============================================================================ */
document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-edit-entity]');
    if (!btn || !window._canEdit) return;
    e.preventDefault();
    e.stopPropagation();
    var ent = btn.getAttribute('data-edit-entity');
    var id = btn.getAttribute('data-edit-id');
    if (ent === 'artist') {
        openEditModal(artistEditConfig(parseInt(id, 10)));
    } else if (ent === 'album') {
        openEditModal(albumEditConfig(parseInt(id, 10), btn.getAttribute('data-edit-name') || ''));
    } else if (ent === 'song') {
        var cell = btn.closest('td.song-name-cell');
        if (!cell && id) cell = document.querySelector('td.song-name-cell[data-song-id="' + id + '"]');
        if (cell) openEditModal(songEditConfig(cell));
    }
});

function songEditConfig(cell) {
    var songId = cell.getAttribute('data-song-id');
    var _row = cell.closest('tr');
    var albumId = _row ? parseInt(_row.getAttribute('data-album-id'), 10) : NaN;
    if (isNaN(albumId)) albumId = null;
    var seedName = (typeof _getSongNameFromCell === 'function') ? _getSongNameFromCell(cell) : (cell.getAttribute('title') || cell.textContent.trim());
    // Misc page songs use misc-specific artist management + a "move to artist" flow
    // (the generic showSongArtists relies on _allArtists, which the misc page lacks).
    var isMisc = !!cell.closest('#misc-table');

    return {
        entity: 'song', id: songId,
        title: function(data) { return data.name; },
        loader: function(done) {
            var seed = {
                name: seedName, note: cell.getAttribute('data-song-note') || '',
                main_artists: [], featured_artists: [], albums: [], genres: [],
                is_lead: false, is_promoted: false, is_cover: false, is_remix: false,
                spotify_url: '', youtube_url: '', aliases: [],
            };
            if (!songId) { done(seed); return; }
            fetch('/song/' + songId + '/info', { headers: { 'Accept': 'application/json' } })
                .then(function(r) { return r.ok ? r.json() : null; })
                .then(function(d) {
                    if (d) {
                        seed.name = d.name || seed.name;
                        seed.main_artists = d.main_artists || [];
                        seed.featured_artists = d.featured_artists || [];
                        seed.albums = d.albums || []; seed.genres = d.genres || [];
                        seed.is_lead = !!d.is_lead; seed.is_promoted = !!d.is_promoted;
                        seed.is_cover = !!d.is_cover; seed.is_remix = !!d.is_remix;
                        seed.note = d.note || ''; seed.spotify_url = d.spotify_url || ''; seed.youtube_url = d.youtube_url || '';
                        seed.aliases = d.aliases || [];
                    }
                    done(seed);
                })
                .catch(function() { done(seed); });
        },
        renderInfoBody: function(bodyArea, data, ui) {
            var nameDiv = document.createElement('div');
            nameDiv.textContent = data.name;
            nameDiv.style.cssText = 'font-size:1rem; font-weight:600; color:var(--text-primary); line-height:1.3; word-wrap:break-word;';
            bodyArea.appendChild(ui.infoRow('Song', nameDiv));

            var artistsText = (data.main_artists || []).join(', ');
            if (data.featured_artists && data.featured_artists.length) {
                artistsText += (artistsText ? ' ' : '') + 'feat. ' + data.featured_artists.join(', ');
            }
            if (artistsText) bodyArea.appendChild(ui.infoRow('Artists', artistsText));

            if (data.albums && data.albums.length) {
                var albumWrap = document.createElement('div');
                albumWrap.style.cssText = 'font-size:0.875rem; color:var(--text-primary); line-height:1.4;';
                data.albums.forEach(function(al) {
                    var line = al.name;
                    if (al.year) line += ' (' + al.year + ')';
                    if (al.genres && al.genres.length) line += ' · ' + al.genres.join(', ');
                    var d = document.createElement('div'); d.textContent = line; albumWrap.appendChild(d);
                });
                bodyArea.appendChild(ui.infoRow(data.albums.length > 1 ? 'Albums' : 'Album', albumWrap));
            }
            if (data.genres && data.genres.length) bodyArea.appendChild(ui.infoRow('Genres', data.genres.join(', ')));

            if (data.aliases && data.aliases.length) {
                var aliasText = data.aliases.map(function(a) {
                    var tag = a.native_lang === 'ja' ? ' (native JP)' : (a.native_lang === 'ko' ? ' (native KR)' : '');
                    return a.name + tag;
                }).join(', ');
                bodyArea.appendChild(ui.infoRow('Alt names', aliasText));
            }

            var tags = [];
            if (data.is_lead) tags.push('Lead');
            if (data.is_promoted) tags.push('Promoted');
            if (data.is_cover) tags.push('Cover');
            if (data.is_remix) tags.push('Remix');
            if (tags.length) bodyArea.appendChild(ui.infoRow('Tags', tags.join(', ')));
            if (data.note) bodyArea.appendChild(ui.infoRow('Note', data.note));

            if (data.spotify_url || data.youtube_url) {
                var links = document.createElement('div');
                links.style.cssText = 'display:flex; gap:0.875rem; font-size:0.875rem;';
                if (data.spotify_url && data.spotify_url !== 'n/a') {
                    var sp = document.createElement('a');
                    sp.href = data.spotify_url; sp.target = '_blank'; sp.rel = 'noopener'; sp.title = 'Spotify';
                    sp.innerHTML = '<img src="/static/img/spotify.png" class="inline align-middle" style="width:1rem;height:1rem;">';
                    links.appendChild(sp);
                }
                if (data.youtube_url) {
                    var yt = document.createElement('a');
                    yt.href = data.youtube_url; yt.target = '_blank'; yt.rel = 'noopener'; yt.title = 'YouTube';
                    yt.innerHTML = '<img src="/static/img/youtube.png" class="inline align-middle" style="width:1rem;height:1rem;">';
                    links.appendChild(yt);
                }
                if (links.children.length) bodyArea.appendChild(ui.infoRow('Links', links));
            }
        },
        renderEditBody: function(bodyArea, data, ui) {
            var nameInput = ui.labeledInput(bodyArea, { label: 'Song Name', key: 'name' }, data);

            var noteLabel = document.createElement('div');
            noteLabel.textContent = 'Note';
            noteLabel.style.cssText = 'font-size:0.75rem; color:var(--text-secondary,#6B7280); margin-bottom:0.375rem;';
            bodyArea.appendChild(noteLabel);
            var textarea = document.createElement('textarea');
            textarea.value = data.note; textarea.rows = 3; textarea.placeholder = 'Add a note...';
            textarea.style.cssText = 'width:100%; border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; padding:0.5rem; font-size:0.875rem; font-family:inherit; resize:vertical; background:var(--bg-primary,#fff); color:var(--text-primary); box-sizing:border-box; margin-bottom:0.875rem;';
            bodyArea.appendChild(textarea);

            var spotifyInput = ui.labeledInput(bodyArea, { label: 'Spotify URL', key: 'spotify_url', placeholder: 'https://open.spotify.com/… (or n/a)' }, data);
            var youtubeInput = ui.labeledInput(bodyArea, { label: 'YouTube URL', key: 'youtube_url', placeholder: 'https://…' }, data);

            // Flags — same lead-star + checkbox-toggle component as the album edit modal,
            // saved immediately on toggle and synced to any visible page tables/pills.
            var flagsLabel = document.createElement('div');
            flagsLabel.textContent = 'Flags';
            flagsLabel.style.cssText = 'font-size:0.75rem; color:var(--text-secondary,#6B7280); margin-bottom:0.375rem;';
            bodyArea.appendChild(flagsLabel);
            var flagsRow = document.createElement('div');
            flagsRow.style.cssText = 'display:flex; flex-wrap:wrap; align-items:center; gap:0.375rem; margin-bottom:0.875rem; padding-left:0.125rem;';
            bodyArea.appendChild(flagsRow);

            function _syncFlagTable(field, checked) {
                var others = document.querySelectorAll('input[type="checkbox"][data-song-id="' + songId + '"][data-field="is-' + field + '"]');
                for (var i = 0; i < others.length; i++) { others[i].checked = checked; if (typeof updateSongPill === 'function') updateSongPill(others[i]); }
            }
            function _syncLeadTable(isLead, promoted) {
                var rows = document.querySelectorAll('tr[data-song-id="' + songId + '"]');
                for (var i = 0; i < rows.length; i++) {
                    if (promoted && typeof _ensurePromotedVisual === 'function') _ensurePromotedVisual(rows[i]);
                    if (typeof _setLeadVisual === 'function') _setLeadVisual(rows[i], songId, isLead);
                }
            }
            function toggleFlag(field, checkbox) {
                fetch('/edit/song/' + songId + '/is-' + field, { method: 'POST', headers: ui.headers(), body: 'checked=' + (checkbox.checked ? 'true' : '') })
                    .then(function(r) { if (!r.ok) throw new Error('failed');
                        data['is_' + field] = checkbox.checked;
                        _syncFlagTable(field, checkbox.checked);
                        if (field === 'promoted' && !checkbox.checked) { data.is_lead = false; _syncLeadTable(false, false); renderFlags(); }
                    }).catch(function() { checkbox.checked = !checkbox.checked; ui.toast('Failed to save — try again'); });
            }
            function toggleLead() {
                fetch('/edit/song/' + songId + '/is-lead', { method: 'POST', headers: ui.headers() })
                    .then(function(r) { if (!r.ok) throw new Error('failed'); return r.json(); })
                    .then(function(d) {
                        data.is_lead = d.is_lead; data.is_promoted = d.is_promoted;
                        if (d.is_promoted) _syncFlagTable('promoted', true);
                        _syncLeadTable(d.is_lead, d.is_promoted);
                        renderFlags();
                    }).catch(function() { ui.toast('Failed to save — try again'); });
            }
            function _leadStar() {
                var star = document.createElement('span');
                star.textContent = '★'; star.title = 'Lead track';
                star.setAttribute('role', 'checkbox'); star.setAttribute('aria-checked', data.is_lead ? 'true' : 'false');
                star.style.cssText = 'cursor:pointer; font-size:1.1875rem; line-height:1; padding:0.125rem 0.25rem; color:' + (data.is_lead ? 'var(--lead-song,#f5a623)' : '#888') + ';';
                star.onclick = function() { toggleLead(); };
                return star;
            }
            function _flagToggle(label, field) {
                var wrap = document.createElement('label');
                wrap.style.cssText = 'display:inline-flex; align-items:center; gap:0.25rem; font-size:0.75rem; color:var(--text-primary); cursor:pointer;';
                var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!data['is_' + field]; cb.style.cssText = 'cursor:pointer;';
                cb.onchange = function() { toggleFlag(field, cb); };
                var txt = document.createElement('span'); txt.textContent = label;
                wrap.appendChild(cb); wrap.appendChild(txt);
                return wrap;
            }
            function renderFlags() {
                flagsRow.innerHTML = '';
                flagsRow.appendChild(_leadStar());
                var flagGroup = document.createElement('div');
                flagGroup.style.cssText = 'display:flex; flex-wrap:wrap; align-items:center; gap:0.75rem;';
                flagGroup.appendChild(_flagToggle('Promoted', 'promoted'));
                flagGroup.appendChild(_flagToggle('Remix', 'remix'));
                flagGroup.appendChild(_flagToggle('Cover', 'cover'));
                flagsRow.appendChild(flagGroup);
            }
            renderFlags();

            var aliasLabel = document.createElement('div');
            aliasLabel.textContent = 'Alternative names';
            aliasLabel.style.cssText = 'font-size:0.75rem; color:var(--text-secondary,#6B7280); margin-bottom:0.375rem;';
            bodyArea.appendChild(aliasLabel);
            var aliasWrap = document.createElement('div');
            aliasWrap.style.cssText = 'display:flex; flex-direction:column; gap:0.375rem; margin-bottom:0.5rem;';
            bodyArea.appendChild(aliasWrap);
            function addAliasRow(name, lang) {
                var row = document.createElement('div');
                row.style.cssText = 'display:flex; gap:0.375rem; align-items:center;';
                var nameInp = document.createElement('input');
                nameInp.type = 'text'; nameInp.value = name || ''; nameInp.placeholder = 'Alternative name';
                nameInp.className = 'alias-name';
                nameInp.style.cssText = 'flex:1; min-width:0; border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; padding:0.375rem 0.5rem; font-size:0.875rem; background:var(--bg-primary,#fff); color:var(--text-primary); box-sizing:border-box;';
                var sel = document.createElement('select');
                sel.className = 'alias-lang';
                sel.style.cssText = 'border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; padding:0.375rem; font-size:0.8125rem; background:var(--bg-primary,#fff); color:var(--text-primary);';
                [['', '—'], ['ja', 'Native JP'], ['ko', 'Native KR']].forEach(function(o) {
                    var opt = document.createElement('option'); opt.value = o[0]; opt.textContent = o[1];
                    if (o[0] === (lang || '')) opt.selected = true;
                    sel.appendChild(opt);
                });
                var del = ui.btn('✕', 'secondary');
                del.style.padding = '0.375rem 0.625rem';
                del.onclick = function() { aliasWrap.removeChild(row); };
                row.appendChild(nameInp); row.appendChild(sel); row.appendChild(del);
                aliasWrap.appendChild(row);
            }
            (data.aliases || []).forEach(function(a) { addAliasRow(a.name, a.native_lang); });
            var addAliasBtn = ui.btn('+ Add name', 'secondary');
            addAliasBtn.style.cssText += 'margin-bottom:0.875rem;';
            addAliasBtn.onclick = function() { addAliasRow('', ''); };
            bodyArea.appendChild(addAliasBtn);
            function collectAliases() {
                var out = [];
                var rows = aliasWrap.children;
                for (var i = 0; i < rows.length; i++) {
                    var nm = rows[i].querySelector('.alias-name');
                    var lg = rows[i].querySelector('.alias-lang');
                    if (!nm) continue;
                    var v = nm.value.trim();
                    if (!v) continue;
                    out.push({ name: v, native_lang: lg && lg.value ? lg.value : null });
                }
                return out;
            }

            var actionRow = document.createElement('div');
            actionRow.style.cssText = 'display:flex; gap:0.5rem; justify-content:flex-end;';
            var clearBtn = ui.btn('Clear', 'danger');
            clearBtn.onclick = function() {
                var fd = new FormData(); fd.append('value', '');
                fetch('/edit/song/' + songId + '/note', { method: 'POST', headers: ui.headers({}), body: fd })
                    .then(function(r) { return r.text(); })
                    .then(function() { data.note = ''; cell.classList.remove('has-song-note'); cell.removeAttribute('data-song-note'); ui.showInfo(); });
            };
            var cancelBtn = ui.btn('Cancel', 'secondary'); cancelBtn.onclick = function() { ui.showInfo(); };
            var saveBtn = ui.btn('Save', 'primary');
            saveBtn.onclick = function() {
                var newName = nameInput.value.trim();
                var nameChanged = newName && newName !== data.name;
                var noteVal = textarea.value.trim();
                var namePromise = nameChanged
                    ? fetch('/edit/song/' + songId + '/name', { method: 'POST', headers: ui.headers(), body: 'value=' + encodeURIComponent(newName) }).then(function(r) { return r.ok ? r.text() : null; })
                    : Promise.resolve(null);
                var noteFd = new FormData(); noteFd.append('value', noteVal);
                var notePromise = fetch('/edit/song/' + songId + '/note', { method: 'POST', headers: ui.headers({}), body: noteFd }).then(function(r) { return r.text(); });
                function _urlPromise(field, newVal, oldVal) {
                    if ((newVal || '') === (oldVal || '')) return Promise.resolve({ changed: false });
                    return fetch('/edit/song/' + songId + '/' + field, { method: 'POST', headers: ui.headers(), body: 'value=' + encodeURIComponent(newVal) })
                        .then(function(r) { return { changed: true, ok: r.ok, value: r.ok ? r.text() : null }; });
                }
                var spotifyPromise = _urlPromise('spotify-url', spotifyInput.value.trim(), data.spotify_url);
                var youtubePromise = _urlPromise('youtube-url', youtubeInput.value.trim(), data.youtube_url);
                var aliasPromise = fetch('/edit/song/' + songId + '/aliases', {
                    method: 'POST', headers: ui.headers({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({ aliases: collectAliases() })
                }).then(function(r) {
                    if (!r.ok) return { ok: false };
                    return r.json().then(function(j) { return { ok: true, aliases: j }; });
                });
                Promise.all([namePromise, notePromise, spotifyPromise, youtubePromise, aliasPromise]).then(function(results) {
                    var savedName = results[0];
                    var savedNote = results[1] ? results[1].trim() : '';
                    if (savedName) {
                        var displayName = savedName.trim();
                        data.name = displayName;
                        cell.setAttribute('title', displayName);
                        var editSpan = cell.querySelector('.edit-inline');
                        if (editSpan) editSpan.textContent = displayName;
                    }
                    data.note = savedNote;
                    if (savedNote) { cell.classList.add('has-song-note'); cell.setAttribute('data-song-note', savedNote); }
                    else { cell.classList.remove('has-song-note'); cell.removeAttribute('data-song-note'); }
                    var aliasRes = results[4];
                    if (aliasRes.ok) data.aliases = aliasRes.aliases || [];
                    else ui.toast('Could not save alternative names — only one native JP and one native KR allowed.');
                    var sp = results[2], yt = results[3];
                    var badUrl = (sp.changed && !sp.ok) || (yt.changed && !yt.ok);
                    Promise.all([
                        sp.changed && sp.ok ? sp.value : Promise.resolve(null),
                        yt.changed && yt.ok ? yt.value : Promise.resolve(null),
                    ]).then(function(urls) {
                        if (sp.changed && sp.ok) data.spotify_url = urls[0] || '';
                        if (yt.changed && yt.ok) data.youtube_url = urls[1] || '';
                        if (badUrl) ui.toast('Invalid URL — must start with https://');
                        ui.showInfo();
                    });
                });
            };
            actionRow.appendChild(clearBtn); actionRow.appendChild(cancelBtn); actionRow.appendChild(saveBtn);
            bodyArea.appendChild(actionRow);

            var sep = document.createElement('div');
            sep.style.cssText = 'border-top:0.0625rem solid var(--border,#ccc); margin:1rem 0 0.625rem;';
            bodyArea.appendChild(sep);
            var actLabel = document.createElement('div');
            actLabel.textContent = 'Actions';
            actLabel.style.cssText = 'font-size:0.6875rem; text-transform:uppercase; letter-spacing:0.03em; color:var(--text-secondary,#6B7280); margin-bottom:0.5rem;';
            bodyArea.appendChild(actLabel);
            var actWrap = document.createElement('div');
            actWrap.style.cssText = 'display:flex; flex-wrap:wrap; gap:0.5rem;';
            bodyArea.appendChild(actWrap);
            function _action(label, kind, onclick) { var b = ui.btn(label, kind || 'secondary'); b.onclick = onclick; actWrap.appendChild(b); }

            function _albumSearch(titleText, endpoint) {
                showMobilePicker({ title: titleText, mode: 'search', placeholder: 'Search albums…',
                    searchUrl: function(q) { return '/misc/search-albums?q=' + encodeURIComponent(q); },
                    mapItems: function(d) { return d.map(function(a) { return { id: a.id, label: a.name + (a.release_date ? ' (' + a.release_date.slice(0, 4) + ')' : '') }; }); },
                    onSelect: function(item) {
                        fetch('/edit/song/' + songId + '/' + endpoint, { method: 'POST', headers: ui.headers(), body: 'album_id=' + item.id })
                            .then(function(r) { if (r.ok) window.location.reload(); else ui.toast('Failed'); });
                    } });
            }
            _action('Move to album', 'secondary', function() { _albumSearch('Move to which album?', 'move-album'); });
            _action('Add to album', 'secondary', function() { _albumSearch('Add to which album?', 'add-to-album'); });
            _action('Manage artists', 'secondary', function() {
                closeMobileModal();
                if (isMisc) {
                    if (typeof _showMiscArtistSelector === 'function') _showMiscArtistSelector(parseInt(songId, 10));
                } else if (typeof showSongArtists === 'function') {
                    showSongArtists({ stopPropagation: function() {} }, parseInt(songId, 10), cell);
                }
            });
            if (isMisc) {
                _action('Move to artist', 'secondary', function() {
                    closeMobileModal();
                    if (typeof _showMoveSongToArtist === 'function') _showMoveSongToArtist({ stopPropagation: function() {} }, parseInt(songId, 10), data.name);
                });
            }
            _action('Merge', 'secondary', function() {
                closeMobileModal();
                if (typeof _openMergePopover === 'function') _openMergePopover(parseInt(songId, 10), data.name, cell);
            });
            if (albumId) {
                _action('Remove from album', 'secondary', function() {
                    if (typeof showConfirm === 'function') {
                        showConfirm('Remove from album?', 'Remove "' + data.name + '" from this album. If it is the only album, the song is deleted.', function() {
                            fetch('/edit/song/' + songId + '/remove-from-album/' + albumId, { method: 'POST', headers: ui.headers({}) })
                                .then(function(r) { if (r.ok) window.location.reload(); else ui.toast('Remove failed'); });
                        }, 'Remove');
                    }
                });
                _action('Split', 'secondary', function() {
                    fetch('/edit/song/' + songId + '/split', { method: 'POST', headers: ui.headers(), body: 'album_id=' + albumId })
                        .then(function(r) { if (r.ok) window.location.reload(); else ui.toast('Split failed'); });
                });
            }
            _action('Delete', 'danger', function() {
                showMobilePassword({ title: 'Delete song?',
                    message: '"' + data.name + '" will be permanently deleted. Enter your password to confirm.',
                    confirmLabel: 'Delete',
                    onConfirm: function(pw, helpers) {
                        fetch('/edit/song/' + songId + '/delete', { method: 'POST', headers: ui.headers(), body: 'password=' + encodeURIComponent(pw), redirect: 'manual' })
                            .then(function(r) { if (r.status === 403) { helpers.error('Incorrect password.'); return; } helpers.close(); window.location.reload(); });
                    } });
            });
        },
    };
}
