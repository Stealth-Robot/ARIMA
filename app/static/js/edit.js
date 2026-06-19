/* Toggle song remix/promoted checkbox via fetch with error handling */
function toggleSongFlag(cb, url) {
    var songId = cb.getAttribute('data-song-id');
    var field = cb.getAttribute('data-field');
    updateSongPill(cb);
    fetch(url, {
        method: 'POST',
        headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
        body: 'checked=' + (cb.checked ? 'true' : '')
    }).then(function(r) {
        if (!r.ok) {
            cb.checked = !cb.checked;
            updateSongPill(cb);
            showToast('Failed to save — try refreshing');
            return;
        }
        if (!songId || !field) return;
        var others = document.querySelectorAll('input[type="checkbox"][data-song-id="' + songId + '"][data-field="' + field + '"]');
        for (var i = 0; i < others.length; i++) {
            if (others[i] !== cb) {
                others[i].checked = cb.checked;
                updateSongPill(others[i]);
            }
        }
    }).catch(function() {
        cb.checked = !cb.checked;
        updateSongPill(cb);
        showToast('Network error — try again');
    });
}

/* Inline text/date edit — edit mode only */

var SONG_PILL_META = {
    'is-remix': { cls: 'remix-tag', bg: 'bg-remix', label: 'remix' },
    'is-cover': { cls: 'cover-tag', bg: 'bg-cover', label: 'cover' },
    'is-promoted': { cls: 'promoted-tag', bg: 'bg-promoted', label: 'promoted' }
};
var SONG_PILL_ORDER = ['promoted-tag', 'cover-tag', 'remix-tag'];

function updateSongPill(checkbox) {
    var meta = SONG_PILL_META[checkbox.getAttribute('data-field')];
    if (!meta) return;
    var row = checkbox.closest('tr');
    var cell = row ? row.querySelector('td:first-child') : null;
    if (!cell) return;
    if (meta.cls === 'promoted-tag') {
        cell.style.borderLeft = checkbox.checked ? '4px solid var(--promoted-song)' : '1px solid var(--grid-line)';
        if (!checkbox.checked) {
            var leadStar = cell.querySelector('.lead-star');
            if (leadStar) leadStar.remove();
            var cellStar = row ? row.querySelector('.lead-cell-star') : null;
            if (cellStar) cellStar.style.color = '#888';
        }
    }
    var tag = cell.querySelector('.' + meta.cls);
    if (checkbox.checked) {
        if (!tag) {
            tag = document.createElement('span');
            tag.className = meta.cls + ' rounded ' + meta.bg + ' text-primary-text ml-1';
            tag.style.cssText = 'font-size: 9px; padding: 1px 5px;';
            tag.textContent = meta.label;
            var myIdx = SONG_PILL_ORDER.indexOf(meta.cls);
            var nextPill = null;
            for (var k = myIdx + 1; k < SONG_PILL_ORDER.length; k++) {
                nextPill = cell.querySelector('.' + SONG_PILL_ORDER[k]);
                if (nextPill) break;
            }
            if (nextPill) {
                nextPill.parentNode.insertBefore(tag, nextPill);
            } else {
                var ref = null;
                for (var j = myIdx - 1; j >= 0; j--) {
                    ref = cell.querySelector('.' + SONG_PILL_ORDER[j]);
                    if (ref) break;
                }
                if (!ref) {
                    var dupTag = cell.querySelector('.duplicate-tag');
                    ref = dupTag ? (dupTag.nextElementSibling || dupTag) : cell.querySelector('.edit-inline');
                }
                if (ref) ref.insertAdjacentElement('afterend', tag);
                else cell.prepend(tag);
            }
        }
    } else {
        if (tag) tag.remove();
    }
}

function _ensurePromotedVisual(row) {
    var cell = row.querySelector('td:first-child');
    if (!cell) return;
    var cb = row.querySelector('input[data-field="is-promoted"]');
    if (cb && !cb.checked) {
        cb.checked = true;
        updateSongPill(cb);
    }
    var cellStar = row.querySelector('.lead-cell-star');
    if (cellStar) cellStar.classList.remove('hidden');
}

function _setLeadVisual(row, songId, isLead) {
    var cell = row.querySelector('td:first-child');
    if (!cell) return;
    var star = cell.querySelector('.lead-star');
    if (isLead) {
        if (!star) {
            star = document.createElement('span');
            star.className = 'lead-star mr-1';
            star.style.cssText = 'color: var(--lead-song); font-size: 19px; cursor: pointer; line-height: 1;';
            star.textContent = '★';
            star.setAttribute('data-song-id', songId);
            var pill = cell.querySelector('.promoted-tag');
            if (pill) {
                pill.insertAdjacentElement('beforebegin', star);
            } else {
                var editSpan = cell.querySelector('.edit-inline');
                var dupTag = cell.querySelector('.duplicate-tag');
                var ref = dupTag || editSpan;
                if (ref) ref.insertAdjacentElement('afterend', star);
                else cell.prepend(star);
            }
        }
    } else {
        if (star) star.remove();
    }
    var cellStar = row.querySelector('.lead-cell-star');
    if (cellStar) cellStar.style.color = isLead ? 'var(--lead-song)' : '#888';
}

function toggleLeadTrack(songId, nameCell) {
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var headers = {};
    if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
    if (window._canEdit) headers['X-Edit-Source'] = 'editor';
    fetch('/edit/song/' + songId + '/is-lead', {
        method: 'POST',
        headers: headers,
    }).then(function(r) {
        if (!r.ok) { showToast('Failed to save — try refreshing'); return; }
        return r.json();
    }).then(function(data) {
        if (!data) return;
        var rows = document.querySelectorAll('tr[data-song-id="' + songId + '"]');
        for (var i = 0; i < rows.length; i++) {
            if (data.is_promoted) _ensurePromotedVisual(rows[i]);
            _setLeadVisual(rows[i], songId, data.is_lead);
        }
    }).catch(function() { showToast('Network error — try again'); });
}

// Clicking anywhere in a remix/cover/promoted cell toggles its checkbox.
document.addEventListener('click', function(e) {
    if (!e.target || e.target.tagName === 'INPUT') return;
    var cell = e.target.closest ? e.target.closest('.checkbox-cell') : null;
    if (!cell) return;
    var cb = cell.querySelector('input[type="checkbox"]');
    if (cb) cb.click();
});

// Clicking a promoted pill or lead star toggles lead status.
document.addEventListener('click', function(e) {
    if (!e.target) return;
    var isPill = e.target.classList.contains('promoted-tag');
    var isStar = e.target.classList.contains('lead-star');
    if (!isPill && !isStar) return;
    var row = e.target.closest('tr');
    if (!row) return;
    var songId = row.dataset.songId;
    if (!songId) return;
    var nameCell = row.querySelector('td:first-child');
    if (nameCell) toggleLeadTrack(parseInt(songId), nameCell);
});

function showArtistNameEdit(event, endpoint, span) {
    event.stopPropagation();
    var original = span.textContent.trim();
    var input = document.createElement('input');
    input.type = 'text';
    input.value = original;
    input.style.cssText = 'border:1px solid var(--link,#2563EB); border-radius:2px; font-size:inherit; font-family:inherit; font-weight:inherit; padding:0 2px; width:' + Math.max(80, span.offsetWidth + 20) + 'px; background:var(--bg-primary); color:var(--text-primary);';
    span.replaceWith(input);
    input.focus();
    input.select();

    function commit() {
        var val = input.value.trim();
        if (!val || val === original) { restore(); return; }
        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
    if (window._canEdit) headers['X-Edit-Source'] = 'editor';
        fetch(endpoint, { method: 'POST', headers: headers, body: 'value=' + encodeURIComponent(val) })
        .then(function(r) { if (!r.ok) { restore(); return null; } return r.json(); })
        .then(function(data) {
            if (!data) return;
            var newSpan = document.createElement('span');
            newSpan.className = 'edit-inline';
            newSpan.style.cursor = 'pointer';
            newSpan.setAttribute('onclick', "showArtistNameEdit(event, '" + endpoint + "', this)");
            newSpan.textContent = data.name;
            input.replaceWith(newSpan);
        });
    }

    function restore() {
        var newSpan = document.createElement('span');
        newSpan.className = 'edit-inline';
        newSpan.style.cursor = 'pointer';
        newSpan.setAttribute('onclick', "showArtistNameEdit(event, '" + endpoint + "', this)");
        newSpan.textContent = original;
        input.replaceWith(newSpan);
    }

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); commit(); }
        else if (e.key === 'Escape') { e.preventDefault(); restore(); }
    });
    input.addEventListener('blur', function() {
        setTimeout(function() { if (document.activeElement !== input) restore(); }, 300);
    });
}

var _activeUrlPopover = null;
function closeUrlPopover() {
    if (_activeUrlPopover) { _activeUrlPopover.remove(); _activeUrlPopover = null; }
}

document.addEventListener('mousedown', function(e) {
    if (_activeUrlPopover && !_activeUrlPopover.contains(e.target)) {
        closeUrlPopover();
    }
});


function promptLocalUrl(btnEl, dataKey, label, opts) {
    opts = opts || {};
    closeUrlPopover();
    var songDiv = btnEl.closest('[id^="song-"], [id^="new-song-"]');
    var currentValue = songDiv ? (songDiv.dataset[dataKey.replace(/_([a-z])/g, function(m,c){return c.toUpperCase();})] || '') : '';

    var popover = document.createElement('div');
    popover.style.cssText = 'position:fixed; z-index:110; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB); border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:320px; top:50%; left:50%; transform:translate(-50%,-50%);';

    var title = document.createElement('div');
    title.textContent = label;
    title.style.cssText = 'font-size:12px; font-weight:bold; margin-bottom:6px; color:var(--text-primary);';
    popover.appendChild(title);
    _makeDraggable(popover, title);

    var input = document.createElement(opts.multiline ? 'textarea' : 'input');
    if (!opts.multiline) input.type = 'text';
    input.value = currentValue;
    input.placeholder = opts.placeholder || 'https://...';
    input.style.cssText = 'width:100%; font-size:12px; padding:4px 6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box; margin-bottom:6px;' + (opts.multiline ? ' min-height:60px; resize:vertical;' : '');
    popover.appendChild(input);

    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex; gap:4px; justify-content:flex-end;';

    var cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'padding:3px 10px; font-size:11px; background:var(--button-secondary,#6B7280); color:var(--button-text,#fff); border:none; border-radius:3px; cursor:pointer;';
    cancelBtn.onclick = closeUrlPopover;

    var saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'padding:3px 10px; font-size:11px; background:var(--link,#2563EB); color:#fff; border:none; border-radius:3px; cursor:pointer;';
    saveBtn.onclick = function() {
        var val = input.value.trim();
        var camelKey = dataKey.replace(/_([a-z])/g, function(m,c){return c.toUpperCase();});
        if (songDiv) {
            if (val) songDiv.dataset[camelKey] = val;
            else delete songDiv.dataset[camelKey];
        }
        closeUrlPopover();
    };

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    popover.appendChild(btnRow);
    popover.addEventListener('mousedown', function(e) { e.stopPropagation(); });
    document.body.appendChild(popover);
    input.focus();
    input.select();
    _activeUrlPopover = popover;

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !opts.multiline) { e.preventDefault(); saveBtn.click(); }
        else if (e.key === 'Escape') { e.preventDefault(); closeUrlPopover(); }
    });
}

function showInlineEdit(event, endpoint, span) {
    if (window.innerWidth <= 768 && span.closest('td.song-name-cell')) return;
    event.stopPropagation();

    const original = span.textContent.trim();
    const input = document.createElement('input');
    input.type = 'text';
    input.value = original === 'date' ? '' : original;
    input.style.cssText = `
        border: 1px solid var(--link, #2563EB); border-radius: 2px;
        font-size: inherit; font-family: inherit; font-weight: inherit;
        padding: 0 2px;
        width: ${Math.max(80, span.offsetWidth + 20)}px;
        background: var(--bg-primary); color: var(--text-primary);
    `;

    span.replaceWith(input);
    var settled = false;
    var submitted = false;
    var blurTimer = null;
    setTimeout(function() { settled = true; }, 300);
    input.focus();
    input.select();

    function commit() {
        submitted = true;
        clearTimeout(blurTimer);
        const val = input.value.trim();
        const csrfToken = document.querySelector('meta[name="csrf-token"]');
        const headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
    if (window._canEdit) headers['X-Edit-Source'] = 'editor';
        fetch(endpoint, {
            method: 'POST',
            headers: headers,
            body: 'value=' + encodeURIComponent(val),
        }).then(function(r) {
            if (!r.ok) { restore(); return; }
            return r.text();
        }).then(function(text) {
            if (text === undefined) return;
            const newSpan = document.createElement('span');
            newSpan.className = 'edit-inline';
            newSpan.style.cursor = 'pointer';
            newSpan.setAttribute('onclick', 'showInlineEdit(event, \'' + endpoint + '\', this)');
            newSpan.textContent = text || original;
            input.replaceWith(newSpan);
        }).catch(function() { restore(); });
    }

    function restore() {
        clearTimeout(blurTimer);
        const newSpan = document.createElement('span');
        newSpan.className = 'edit-inline';
        newSpan.style.cursor = 'pointer';
        newSpan.setAttribute('onclick', 'showInlineEdit(event, \'' + endpoint + '\', this)');
        newSpan.textContent = original;
        input.replaceWith(newSpan);
    }

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); commit(); }
        else if (e.key === 'Escape') { e.preventDefault(); restore(); }
    });

    input.addEventListener('blur', function() {
        blurTimer = setTimeout(function() {
            if (settled && !submitted && document.activeElement !== input) restore();
        }, 200);
    });
}

function showInlineDateEdit(event, endpoint, span, currentFullDate) {
    event.stopPropagation();

    const original = span.textContent.trim();
    const input = document.createElement('input');
    input.value = currentFullDate || '';
    input.style.cssText = `
        border: 1px solid var(--link, #2563EB); border-radius: 2px;
        font-size: inherit; padding: 0 2px;
        background: var(--bg-primary); color: var(--text-primary);
        width: 100px;
    `;
    applyDateFormat(input);

    var dateWrapper = input._dateWrapper || input;
    span.replaceWith(dateWrapper);
    input.focus();

    var committed = false;
    function commit() {
        if (committed) return;
        committed = true;
        const val = input.value.trim();
        if (val && !isRealDate(val)) {
            input.style.borderColor = 'var(--delete-button, red)';
            committed = false;
            return;
        }
        const csrfToken = document.querySelector('meta[name="csrf-token"]');
        const headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
    if (window._canEdit) headers['X-Edit-Source'] = 'editor';
        fetch(endpoint, {
            method: 'POST',
            headers: headers,
            body: 'value=' + encodeURIComponent(val),
        }).then(function(r) {
            if (!r.ok) { restore(); return; }
            return r.text();
        }).then(function(text) {
            if (text === undefined) return;
            var displayYear = text ? text.substring(0, 4) : 'date';
            const newSpan = document.createElement('span');
            newSpan.className = 'edit-inline';
            newSpan.style.cursor = 'pointer';
            newSpan.dataset.fullDate = text || '';
            if (!text) newSpan.style.color = 'var(--text-secondary)';
            newSpan.setAttribute('onclick', "showInlineDateEdit(event, '" + endpoint + "', this, this.dataset.fullDate)");
            newSpan.textContent = displayYear;
            dateWrapper.replaceWith(newSpan);
        }).catch(function() { restore(); });
    }

    function restore() {
        const newSpan = document.createElement('span');
        newSpan.className = 'edit-inline';
        newSpan.style.cursor = 'pointer';
        newSpan.dataset.fullDate = currentFullDate || '';
        if (!currentFullDate) newSpan.style.color = 'var(--text-secondary)';
        newSpan.setAttribute('onclick', "showInlineDateEdit(event, '" + endpoint + "', this, this.dataset.fullDate)");
        newSpan.textContent = original;
        dateWrapper.replaceWith(newSpan);
    }

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); commit(); }
        else if (e.key === 'Escape') { e.preventDefault(); restore(); }
    });

    input.addEventListener('change', function() { commit(); });

    input.addEventListener('blur', function() {
        setTimeout(function() {
            if (!committed && document.activeElement !== input) restore();
        }, 300);
    });
}

/* Inline genre edit — checkbox popover */

var activeGenrePopover = null;

function closeGenrePopover() {
    if (activeGenrePopover) {
        activeGenrePopover.remove();
        activeGenrePopover = null;
    }
}

function showGenreEdit(event, albumId, span, allGenres, currentIds) {
    event.stopPropagation();
    closeGenrePopover();

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:180px; max-height:240px; display:flex; flex-direction:column;';

    var listWrap = document.createElement('div');
    listWrap.style.cssText = 'overflow-y:auto; flex:1; padding:8px 8px 0;';
    popover.appendChild(listWrap);

    var selected = currentIds.slice();

    allGenres.forEach(function(g) {
        var label = document.createElement('label');
        label.style.cssText = 'display:block; font-size:12px; padding:2px 0; cursor:pointer;';
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = g.id;
        cb.checked = selected.indexOf(g.id) !== -1;
        cb.style.marginRight = '4px';
        cb.addEventListener('change', function() {
            if (this.checked) { selected.push(g.id); }
            else { selected = selected.filter(function(x) { return x !== g.id; }); }
        });
        label.appendChild(cb);
        label.appendChild(document.createTextNode(g.name));
        listWrap.appendChild(label);
    });

    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex; gap:4px; padding:6px 8px; justify-content:flex-end; flex-shrink:0; border-top:1px solid var(--border,#ccc);';

    var saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'padding:2px 10px; font-size:12px; background:var(--link,#2563EB); color:#fff; border:none; border-radius:3px; cursor:pointer;';
    saveBtn.onclick = function() {
        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
    if (window._canEdit) headers['X-Edit-Source'] = 'editor';
        var ids = [];
        popover.querySelectorAll('input[type="checkbox"]:checked').forEach(function(cb) {
            ids.push(parseInt(cb.value));
        });
        fetch('/edit/album/' + albumId + '/genres', {
            method: 'POST',
            headers: headers,
            body: 'genre_ids=' + encodeURIComponent(ids.join(',')),
        }).then(function(r) {
            if (!r.ok) throw new Error('save failed');
            return r.json();
        }).then(function(names) {
            span.textContent = names.length ? names.join(', ') : 'genres';
            if (!names.length) span.style.color = 'var(--text-secondary)';
            else span.style.color = '';
            span.setAttribute('data-genre-ids', JSON.stringify(ids));
            closeGenrePopover();
        }).catch(function() {
            showToast('Failed to save genres — try again');
            closeGenrePopover();
        });
    };

    var cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'padding:2px 10px; font-size:12px; background:#6B7280; color:#fff; border:none; border-radius:3px; cursor:pointer;';
    cancelBtn.onclick = closeGenrePopover;

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    popover.appendChild(btnRow);

    var rect = getZoomedRect(span);
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    if (rect.bottom + 2 + popover.offsetHeight + 30 > viewH) {
        popover.style.top = Math.max(0, viewH - popover.offsetHeight - 30) + 'px';
    } else {
        popover.style.top = rect.bottom + 2 + 'px';
    }
    activeGenrePopover = popover;
}

document.addEventListener('mousedown', function(e) {
    if (activeGenrePopover && !activeGenrePopover.contains(e.target)) {
        closeGenrePopover();
    }
});

/* Inline country edit — dropdown popover */

var activeCountryPopover = null;

function closeCountryPopover() {
    if (activeCountryPopover) {
        activeCountryPopover.remove();
        activeCountryPopover = null;
    }
}


document.addEventListener('mousedown', function(e) {
    if (activeCountryPopover && !activeCountryPopover.contains(e.target)) {
        closeCountryPopover();
    }
    if (activeGenderPopover && !activeGenderPopover.contains(e.target)) {
        closeGenderPopover();
    }
    if (activeAlbumTypePopover && !activeAlbumTypePopover.contains(e.target)) {
        closeAlbumTypePopover();
    }
    if (activeArtistUserPopover && !activeArtistUserPopover.contains(e.target)) {
        closeArtistUserPopover();
    }
});

/* Inline artist owner/maintainer edit — avatar + name popover */

var activeArtistUserPopover = null;

function closeArtistUserPopover() {
    if (activeArtistUserPopover) {
        activeArtistUserPopover.remove();
        activeArtistUserPopover = null;
    }
}

function _renderUserRow(userId, username, imageUrl, isCurrent) {
    var row = document.createElement('div');
    row.style.cssText = 'padding:4px 6px; font-size:12px; cursor:pointer; border-radius:2px; display:flex; align-items:center; gap:6px;';
    if (isCurrent) row.style.fontWeight = 'bold';
    row.addEventListener('mouseenter', function() { row.style.background = _hoverBg(); });
    row.addEventListener('mouseleave', function() { row.style.background = ''; });
    if (userId !== null) {
        var img = document.createElement('img');
        img.src = imageUrl || '/static/img/default_image.png';
        img.referrerPolicy = 'no-referrer';
        img.style.cssText = 'width:18px;height:18px;border-radius:50%;object-fit:cover;flex-shrink:0;';
        img.onerror = function() { img.onerror = null; img.src = '/static/img/default_image.png'; };
        row.appendChild(img);
    } else {
        var placeholder = document.createElement('span');
        placeholder.style.cssText = 'width:18px;height:18px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;';
        placeholder.textContent = '—';
        row.appendChild(placeholder);
    }
    var label = document.createElement('span');
    label.textContent = username;
    row.appendChild(label);
    return row;
}

function _updateArtistUserSpan(span, userId, username, imageUrl) {
    var content = span.querySelector('.user-pill-content') || span;
    content.innerHTML = '';
    if (userId == null) {
        content.textContent = '—';
        return;
    }
    var img = document.createElement('img');
    img.src = imageUrl || '/static/img/default_image.png';
    img.referrerPolicy = 'no-referrer';
    img.className = 'rounded-full object-cover';
    img.style.cssText = 'width:18px;height:18px;';
    img.onerror = function() { img.onerror = null; img.src = '/static/img/default_image.png'; };
    content.appendChild(img);
    content.appendChild(document.createTextNode(username));
}

function showArtistUserEdit(event, artistId, span, kind, onCommit) {
    event.stopPropagation();
    closeArtistUserPopover();

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:220px; max-height:320px; overflow-y:auto;';

    var currentAttr = kind === 'owner' ? 'ownerId' : (kind === 'creator' ? 'creatorId' : 'maintainerId');
    var current = span.dataset[currentAttr];
    var currentId = current ? parseInt(current) : null;

    function commit(userId, username, imageUrl) {
        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
    if (window._canEdit) headers['X-Edit-Source'] = 'editor';
        fetch('/edit/artist/' + artistId + '/' + kind, {
            method: 'POST',
            headers: headers,
            body: 'user_id=' + (userId == null ? '' : userId),
        }).then(function(r) {
            if (!r.ok) throw new Error('save failed');
            return r.json();
        }).then(function(data) {
            var newId = data[kind + '_id'];
            span.dataset[currentAttr] = newId == null ? '' : newId;
            _updateArtistUserSpan(span, newId, username, imageUrl);
            closeArtistUserPopover();
            if (typeof onCommit === 'function') onCommit(newId);
        }).catch(function() {
            showToast('Failed to save — try again');
            closeArtistUserPopover();
        });
    }

    var noneRow = _renderUserRow(null, 'Unassigned', null, currentId === null);
    noneRow.addEventListener('click', function() { commit(null, null, null); });
    popover.appendChild(noneRow);

    (window._assignableUsers || []).forEach(function(u) {
        var row = _renderUserRow(u.id, u.username, u.profileImage, u.id === currentId);
        row.addEventListener('click', function() { commit(u.id, u.username, u.profileImage); });
        popover.appendChild(row);
    });

    var rect = getZoomedRect(span);
    popover.style.left = rect.left + 'px';
    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    if (rect.bottom + 2 + popover.offsetHeight + 30 > viewH) {
        popover.style.top = Math.max(0, viewH - popover.offsetHeight - 30) + 'px';
    } else {
        popover.style.top = rect.bottom + 2 + 'px';
    }
    activeArtistUserPopover = popover;
}

/* Called from the Complete checkbox to clear the owner span when marking complete */
function setOwnerSpanComplete(artistId, isComplete) {
    var span = document.getElementById('owner-span-' + artistId);
    if (!span) return;
    if (isComplete) {
        span.style.display = 'none';
        span.dataset.ownerId = '';
        span.onclick = null;
    } else {
        span.style.display = '';
        span.classList.add('edit-inline', 'cursor-pointer', 'hover:bg-hover-bg');
        span.onclick = function(e) { showArtistUserEdit(e, artistId, span, 'owner'); };
    }
}

/* Mark-complete checklist — show a reminder popup before completing a tab */
var _completeTabCtx = null;

function _postArtistComplete(cb, artistId, value) {
    fetch('/edit/artist/' + artistId + '/is-complete', {
        method: 'POST',
        headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
        body: 'value=' + value
    }).then(function (r) {
        if (!r.ok) { cb.checked = !cb.checked; return; }
        setOwnerSpanComplete(artistId, cb.checked);
    });
}

function confirmCompleteTab(cb, artistId, artistName) {
    // Unchecking (un-completing) is immediate — no checklist.
    if (!cb.checked) { _postArtistComplete(cb, artistId, '0'); return; }

    var modal = document.getElementById('complete-checklist-modal');
    if (!modal) { _postArtistComplete(cb, artistId, '1'); return; }

    _completeTabCtx = { cb: cb, artistId: artistId };
    var nameEl = document.getElementById('complete-checklist-artist');
    if (nameEl) nameEl.textContent = artistName || '';
    document.querySelectorAll('#complete-checklist-modal .complete-checklist-item').forEach(function (c) {
        c.checked = false;
    });
    syncCompleteTabBtn();
    modal.style.display = 'flex';
}

function syncCompleteTabBtn() {
    var btn = document.getElementById('complete-checklist-confirm-btn');
    if (!btn) return;
    var items = document.querySelectorAll('#complete-checklist-modal .complete-checklist-item');
    var allChecked = items.length > 0 && Array.prototype.every.call(items, function (c) { return c.checked; });
    btn.disabled = !allChecked;
    btn.style.opacity = allChecked ? '1' : '0.5';
    btn.style.cursor = allChecked ? 'pointer' : 'not-allowed';
}

function cancelCompleteTab() {
    var modal = document.getElementById('complete-checklist-modal');
    if (modal) modal.style.display = 'none';
    if (_completeTabCtx && _completeTabCtx.cb) _completeTabCtx.cb.checked = false;
    _completeTabCtx = null;
}

function confirmCompleteTabFinalize() {
    var modal = document.getElementById('complete-checklist-modal');
    if (modal) modal.style.display = 'none';
    if (_completeTabCtx) _postArtistComplete(_completeTabCtx.cb, _completeTabCtx.artistId, '1');
    _completeTabCtx = null;
}

/* Inline album type edit — pick type popover */

var activeAlbumTypePopover = null;

function closeAlbumTypePopover() {
    if (activeAlbumTypePopover) {
        activeAlbumTypePopover.remove();
        activeAlbumTypePopover = null;
    }
}


/* Inline gender edit — pick gender popover */

var activeGenderPopover = null;
var GENDER_CSS_MAP = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed', 3: '--gender-anime'};

function closeGenderPopover() {
    if (activeGenderPopover) {
        activeGenderPopover.remove();
        activeGenderPopover = null;
    }
}


/* Global Escape handler — closes all popovers and modals */
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        closeArtistMenu();
        closeAlbumMovePopover();
        closeAlbumArtistMovePopover();
        closeAlbumAddPopover();
        closeAlbumSongSearchPopover();
        closeSongArtistPopover();
        closeMergePopover();
        closeSearchOverlay();
        var deleteModal = document.getElementById('confirm-delete-modal');
        if (deleteModal) deleteModal.style.display = 'none';
        var addAlbumModal = document.getElementById('add-album-modal');
        if (addAlbumModal) addAlbumModal.style.display = 'none';
        var convertModal = document.getElementById('convert-artist-modal');
        if (convertModal) convertModal.style.display = 'none';
    }
});
/* Shared search popover scaffolding */

function _createSearchPopover(opts) {
    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:' + (opts.width || '280px') +
        '; max-height:' + (opts.maxHeight || '320px') + '; display:flex; flex-direction:column;';

    var title = document.createElement('div');
    title.textContent = opts.title || '';
    title.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:4px; color:var(--text-secondary);';
    popover.appendChild(title);
    _makeDraggable(popover, title);

    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = opts.placeholder || 'Search...';
    searchInput.style.cssText = 'width:100%; font-size:11px; padding:4px 6px; margin-bottom:6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box;';
    popover.appendChild(searchInput);

    var listContainer = document.createElement('div');
    listContainer.style.cssText = 'overflow-y:auto; flex:1;';
    popover.appendChild(listContainer);

    var rect = getZoomedRect(opts.anchor);
    popover.style.left = rect.left + 'px';
    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    var pH = parseInt(opts.maxHeight || '320', 10);
    if (rect.bottom + 2 + pH <= viewH) {
        // Fits below anchor
        popover.style.top = rect.bottom + 2 + 'px';
    } else if (rect.top - 2 - pH >= 0) {
        // Fits above anchor
        popover.style.top = (rect.top - 2 - pH) + 'px';
    } else {
        // Doesn't fit either way — pin to bottom of viewport
        popover.style.top = Math.max(0, viewH - pH - 10) + 'px';
    }
    searchInput.focus();

    return { popover: popover, listContainer: listContainer, searchInput: searchInput, title: title };
}

/* Inline album move — pick album popover */

var activeAlbumMovePopover = null;

function closeAlbumMovePopover() {
    if (activeAlbumMovePopover) {
        activeAlbumMovePopover.remove();
        activeAlbumMovePopover = null;
    }
}

function _renderAlbumResults(albums, listContainer, onSelect) {
    listContainer.innerHTML = '';
    var parentMap = (typeof _artistParentMap !== 'undefined') ? _artistParentMap : {};
    var grouped = {};
    var groupOrder = [];
    var entryMap = {};
    albums.forEach(function(a) {
        var group = parentMap[a.artist] || a.artist;
        var isChild = a.artist !== group;
        var key = group + '::' + a.id;
        if (entryMap[key] && !isChild) return;
        var label = isChild ? a.name + ' (' + a.artist + ')' : a.name;
        var entry = { id: a.id, label: label, subgroup: isChild ? a.artist : '' };
        if (entryMap[key]) {
            var arr = grouped[group];
            for (var i = 0; i < arr.length; i++) { if (arr[i].id === a.id) { arr[i] = entry; break; } }
        } else {
            if (!grouped[group]) { grouped[group] = []; groupOrder.push(group); }
            grouped[group].push(entry);
        }
        entryMap[key] = true;
    });
    var currentArtistName = (typeof _pageArtistName !== 'undefined') ? _pageArtistName : null;
    groupOrder.sort(function(a, b) {
        var aIsMisc = a === 'Misc. Artists' && a !== currentArtistName;
        var bIsMisc = b === 'Misc. Artists' && b !== currentArtistName;
        var aRank = a === currentArtistName ? 0 : aIsMisc ? 2 : 1;
        var bRank = b === currentArtistName ? 0 : bIsMisc ? 2 : 1;
        if (aRank !== bRank) return aRank - bRank;
        return a.toLowerCase() < b.toLowerCase() ? -1 : a.toLowerCase() > b.toLowerCase() ? 1 : 0;
    });
    groupOrder.forEach(function(group) {
        var header = document.createElement('div');
        header.textContent = group;
        header.style.cssText = 'font-size:10px; font-weight:bold; padding:4px 6px 2px; color:var(--text-secondary); text-transform:uppercase;';
        listContainer.appendChild(header);
        grouped[group].sort(function(a, b) {
            if (!a.subgroup && b.subgroup) return -1;
            if (a.subgroup && !b.subgroup) return 1;
            if (a.subgroup !== b.subgroup) return a.subgroup.toLowerCase() < b.subgroup.toLowerCase() ? -1 : 1;
            return a.label.toLowerCase() < b.label.toLowerCase() ? -1 : a.label.toLowerCase() > b.label.toLowerCase() ? 1 : 0;
        });
        grouped[group].forEach(function(item) {
            var btn = document.createElement('div');
            btn.textContent = item.label;
            btn.style.cssText = 'padding:3px 6px 3px 14px; font-size:12px; cursor:pointer; border-radius:2px;';
            btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
            btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
            btn.addEventListener('click', function() { onSelect(item); });
            listContainer.appendChild(btn);
        });
    });
    if (!groupOrder.length) {
        var empty = document.createElement('div');
        empty.textContent = 'No matches';
        empty.style.cssText = 'font-size:11px; color:var(--text-secondary); padding:6px;';
        listContainer.appendChild(empty);
    }
}

function _fetchAlbums(q, excludeId, callback) {
    var url = '/edit/picker/albums?q=' + encodeURIComponent(q || '') + '&exclude=' + (excludeId || '');
    fetch(url, { headers: _csrfHeaders({}) }).then(function(r) { return r.json(); }).then(callback).catch(function() { callback([]); });
}

function _fetchSongs(q, excludeId, callback) {
    var url = '/edit/picker/songs?q=' + encodeURIComponent(q || '') + '&exclude=' + (excludeId || '');
    fetch(url, { headers: _csrfHeaders({}) }).then(function(r) { return r.json(); }).then(callback).catch(function() { callback([]); });
}


/* Move album songs to another artist popover */

var activeAlbumArtistMovePopover = null;

function closeAlbumArtistMovePopover() {
    if (activeAlbumArtistMovePopover) {
        activeAlbumArtistMovePopover.remove();
        activeAlbumArtistMovePopover = null;
    }
}


/* Add song to additional album popover */

var activeAlbumAddPopover = null;

function closeAlbumAddPopover() {
    if (activeAlbumAddPopover) {
        activeAlbumAddPopover.remove();
        activeAlbumAddPopover = null;
    }
}


/* Add existing song to album (search popover) */

var activeAlbumSongSearchPopover = null;

function closeAlbumSongSearchPopover() {
    if (activeAlbumSongSearchPopover) {
        activeAlbumSongSearchPopover.remove();
        activeAlbumSongSearchPopover = null;
    }
}


document.addEventListener('mousedown', function(e) {
    if (activeAlbumMovePopover && !activeAlbumMovePopover.contains(e.target)) {
        closeAlbumMovePopover();
    closeAlbumArtistMovePopover();
    }
    if (activeAlbumAddPopover && !activeAlbumAddPopover.contains(e.target)) {
        closeAlbumAddPopover();
    }
    if (activeAlbumSongSearchPopover && !activeAlbumSongSearchPopover.contains(e.target)) {
        closeAlbumSongSearchPopover();
    }
    if (activeSongArtistPopover && !activeSongArtistPopover.contains(e.target)) {
        closeSongArtistPopover();
    }
    if (activeMergePopover && !activeMergePopover.contains(e.target)) {
        closeMergePopover();
    }
});

/* Song merge popover */

var activeMergePopover = null;

function closeMergePopover() {
    if (activeMergePopover) {
        activeMergePopover.remove();
        activeMergePopover = null;
    }
}

document.addEventListener('click', function(e) {
    var btn = e.target.closest('.merge-btn');
    if (!btn) return;
    e.stopPropagation();
    var songId = parseInt(btn.dataset.songId);
    var songName = btn.dataset.songName;
    _openMergePopover(songId, songName, btn);
});

function _openMergePopover(songId, songName, span) {
    closeMergePopover();

    var parts = _createSearchPopover({
        title: 'Merge into "' + songName + '":',
        placeholder: 'Search songs...',
        width: '340px',
        maxHeight: '360px',
        anchor: span,
    });
    var listContainer = parts.listContainer;

    var exactContainer = document.createElement('div');
    exactContainer.style.cssText = 'flex-shrink:0;';
    listContainer.parentNode.insertBefore(exactContainer, listContainer);

    var songNameLower = songName.toLowerCase();
    var timer;

    function _makeMergeBtn(item, group) {
        var label = !group ? item.name + ' (' + item.artist + ' / ' + item.album + ')'
            : item.artist !== group ? item.name + ' (' + item.artist + ' / ' + item.album + ')'
            : item.name + ' (' + item.album + ')';
        var btn = document.createElement('div');
        btn.textContent = label;
        btn.style.cssText = 'padding:3px 6px 3px 14px; font-size:12px; cursor:pointer; border-radius:2px;';
        btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
        btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
        btn.addEventListener('click', function() {
            closeMergePopover();
            showMergeDiffModal(songId, songName, item.id, item.name, item.artist, item.album);
        });
        return btn;
    }

    function doSearch() {
        clearTimeout(timer);
        timer = setTimeout(function() {
            _fetchSongs(parts.searchInput.value, songId, function(songs) {
                exactContainer.innerHTML = '';
                listContainer.innerHTML = '';
                var parentMap = (typeof _artistParentMap !== 'undefined') ? _artistParentMap : {};
                var currentArtistName = (typeof _pageArtistName !== 'undefined') ? _pageArtistName : null;
                var exactMatches = [];
                var grouped = {};
                var groupOrder = [];
                songs.forEach(function(s) {
                    if (s.name.toLowerCase() === songNameLower) {
                        exactMatches.push(s);
                    } else {
                        var group = parentMap[s.artist] || s.artist;
                        if (!grouped[group]) { grouped[group] = []; groupOrder.push(group); }
                        grouped[group].push(s);
                    }
                });
                if (exactMatches.length) {
                    var sameArtist = [];
                    var diffArtist = [];
                    exactMatches.forEach(function(item) {
                        var resolved = parentMap[item.artist] || item.artist;
                        if (resolved === currentArtistName) sameArtist.push(item);
                        else diffArtist.push(item);
                    });
                    var sortByArtist = function(a, b) {
                        return a.artist.toLowerCase() < b.artist.toLowerCase() ? -1 : a.artist.toLowerCase() > b.artist.toLowerCase() ? 1 : 0;
                    };
                    if (sameArtist.length) {
                        var h1 = document.createElement('div');
                        h1.textContent = 'Exact Matches — Same Artist';
                        h1.style.cssText = 'font-size:10px; font-weight:bold; padding:4px 6px 2px; color:var(--text-secondary); text-transform:uppercase;';
                        exactContainer.appendChild(h1);
                        sameArtist.sort(sortByArtist);
                        sameArtist.forEach(function(item) {
                            exactContainer.appendChild(_makeMergeBtn(item, null));
                        });
                    }
                    if (diffArtist.length) {
                        var h2 = document.createElement('div');
                        h2.textContent = 'Exact Matches — Different Artist';
                        h2.style.cssText = 'font-size:10px; font-weight:bold; padding:4px 6px 2px; color:var(--text-secondary); text-transform:uppercase;';
                        exactContainer.appendChild(h2);
                        diffArtist.sort(sortByArtist);
                        diffArtist.forEach(function(item) {
                            exactContainer.appendChild(_makeMergeBtn(item, null));
                        });
                    }
                    var sep = document.createElement('div');
                    sep.style.cssText = 'border-bottom:1px solid var(--border,#ccc); margin:4px 0;';
                    exactContainer.appendChild(sep);
                }
                groupOrder.sort(function(a, b) {
                    var aIsMisc = a === 'Misc. Artists' && a !== currentArtistName;
                    var bIsMisc = b === 'Misc. Artists' && b !== currentArtistName;
                    var aRank = a === currentArtistName ? 0 : aIsMisc ? 2 : 1;
                    var bRank = b === currentArtistName ? 0 : bIsMisc ? 2 : 1;
                    if (aRank !== bRank) return aRank - bRank;
                    return a.toLowerCase() < b.toLowerCase() ? -1 : a.toLowerCase() > b.toLowerCase() ? 1 : 0;
                });
                groupOrder.forEach(function(group) {
                    var header = document.createElement('div');
                    header.textContent = group;
                    header.style.cssText = 'font-size:10px; font-weight:bold; padding:4px 6px 2px; color:var(--text-secondary); text-transform:uppercase;';
                    listContainer.appendChild(header);
                    grouped[group].sort(function(a, b) {
                        return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : a.name.toLowerCase() > b.name.toLowerCase() ? 1 : 0;
                    });
                    grouped[group].forEach(function(item) {
                        listContainer.appendChild(_makeMergeBtn(item, group));
                    });
                });
                if (!exactMatches.length && !groupOrder.length) {
                    var empty = document.createElement('div');
                    empty.textContent = 'No matches';
                    empty.style.cssText = 'font-size:11px; color:var(--text-secondary); padding:6px;';
                    listContainer.appendChild(empty);
                }
            });
        }, 150);
    }

    doSearch();
    parts.searchInput.addEventListener('input', doSearch);
    activeMergePopover = parts.popover;
}

function showMergeDiffModal(keptId, keptName, absorbedId, absorbedName, absorbedArtist, absorbedAlbum, options) {
    var overlay = document.createElement('div');
    var _z = (options && options.zIndex) || 100;
    overlay.style.cssText = 'position:fixed;inset:0;z-index:' + _z + ';background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;';
    overlay.addEventListener('click', function(e) { if (e.target === overlay) _closeMergeModal(overlay); });

    var container = document.createElement('div');
    container.style.cssText = 'background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;width:700px;max-width:90vw;max-height:85vh;display:flex;flex-direction:column;';
    overlay.appendChild(container);

    var header = document.createElement('div');
    header.style.cssText = 'padding:20px 24px 12px;flex-shrink:0;';
    header.innerHTML = '<div style="font-size:16px;font-weight:bold;color:var(--text-primary);">Merge Songs</div><div style="font-size:12px;color:var(--text-secondary);margin-top:4px;">Loading...</div>';
    container.appendChild(header);
    // Insert at top of <body> so password managers (which cap field collection in DOM order) see the pw field despite thousands of page inputs
    document.body.insertBefore(overlay, document.body.firstChild);

    fetch('/edit/song/' + keptId + '/merge-preview/' + absorbedId, {headers: _csrfHeaders({})})
    .then(function(r) { if (!r.ok) throw new Error('failed'); return r.json(); })
    .then(function(data) { _buildMergeDiff(overlay, container, header, data, keptId, absorbedId, options); })
    .catch(function() { header.lastChild.textContent = 'Failed to load merge data.'; });
}

function _ratingStyle(score) {
    if (score === null || score === undefined || score === '') return '';
    var s = parseInt(score);
    var root = document.documentElement;
    var bg = getComputedStyle(root).getPropertyValue('--rating-' + s + '-bg').trim();
    var text = getComputedStyle(root).getPropertyValue('--rating-' + s + '-text').trim();
    if (bg) return 'background:' + bg + ';color:' + text + ';';
    return '';
}

function _makeChip(text, side, active) {
    var chip = document.createElement('span');
    chip.textContent = text || '(none)';
    chip.dataset.side = side;
    chip.style.cssText = 'padding:2px 8px;border-radius:4px;border:1px solid var(--border);cursor:pointer;font-size:12px;white-space:nowrap;max-width:200px;overflow:hidden;text-overflow:ellipsis;display:inline-block;' + (text ? '' : 'color:var(--text-secondary);font-style:italic;');
    if (active) chip.style.outline = '2px solid var(--link)';
    return chip;
}

function _buildMergeDiff(overlay, container, header, data, keptId, absorbedId, options) {
    var opts = options || {};
    var k = data.kept, a = data.absorbed;
    header.lastChild.innerHTML = '<span style="color:var(--text-primary);">Kept:</span> ' + _escHtml(k.name) + ' <span style="color:var(--text-secondary);">(' + _escHtml(k.artist || '?') + ')</span> &larr; <span style="color:var(--text-primary);">Absorbed:</span> ' + _escHtml(a.name) + ' <span style="color:var(--text-secondary);">(' + _escHtml(a.artist || '?') + ')</span>';

    var body = document.createElement('div');
    body.style.cssText = 'padding:0 24px 16px;overflow-y:auto;flex:1;';
    container.appendChild(body);

    var inputs = {};
    var ratingInputs = [];

    function addTextRow(label, field, keptVal, absorbedVal, useTextarea) {
        var section = document.createElement('div');
        section.style.cssText = 'margin-bottom:14px;';
        var lbl = document.createElement('div');
        lbl.textContent = label;
        lbl.style.cssText = 'font-size:11px;font-weight:bold;color:var(--text-secondary);margin-bottom:4px;text-transform:uppercase;';
        section.appendChild(lbl);

        var row = document.createElement('div');
        row.style.cssText = 'display:flex;gap:6px;align-items:' + (useTextarea ? 'flex-start' : 'center') + ';';

        var defaultVal = keptVal || absorbedVal || '';
        var chipK = _makeChip(keptVal, 'kept', defaultVal === keptVal && keptVal);
        var chipA = _makeChip(absorbedVal, 'absorbed', false);
        var arrow = document.createElement('span');
        arrow.textContent = '\u2192';
        arrow.style.cssText = 'color:var(--text-secondary);font-size:14px;flex-shrink:0;';

        var input;
        if (useTextarea) {
            input = document.createElement('textarea');
            input.rows = 3;
            input.style.cssText = 'flex:1;min-width:0;padding:4px 6px;border:1px solid var(--border);border-radius:4px;font-size:12px;background:var(--bg-primary);color:var(--text-primary);resize:vertical;';
        } else {
            input = document.createElement('input');
            input.type = 'text';
            input.style.cssText = 'flex:1;min-width:0;padding:4px 6px;border:1px solid var(--border);border-radius:4px;font-size:12px;background:var(--bg-primary);color:var(--text-primary);';
        }
        input.value = defaultVal;
        inputs[field] = input;

        function selectChip(chip, val) {
            chipK.style.outline = '';
            chipA.style.outline = '';
            chip.style.outline = '2px solid var(--link)';
            input.value = val || '';
        }
        chipK.addEventListener('click', function() { selectChip(chipK, keptVal); });
        chipA.addEventListener('click', function() { selectChip(chipA, absorbedVal); });

        if (useTextarea && keptVal && absorbedVal && keptVal !== absorbedVal) {
            var combineChip = document.createElement('span');
            combineChip.textContent = 'Combine';
            combineChip.style.cssText = 'padding:2px 8px;border-radius:4px;border:1px dashed var(--border);cursor:pointer;font-size:11px;color:var(--text-secondary);white-space:nowrap;';
            combineChip.addEventListener('click', function() {
                chipK.style.outline = '';
                chipA.style.outline = '';
                combineChip.style.outline = '2px solid var(--link)';
                input.value = keptVal + '\n' + absorbedVal;
            });
            row.appendChild(chipK);
            row.appendChild(chipA);
            row.appendChild(combineChip);
        } else {
            row.appendChild(chipK);
            row.appendChild(chipA);
        }
        row.appendChild(arrow);
        row.appendChild(input);
        section.appendChild(row);
        body.appendChild(section);
    }

    addTextRow('Song Name', 'name', k.name, a.name, false);

    var flagFields = [
        {field: 'is_promoted', label: 'Promoted'},
        {field: 'is_lead', label: 'Lead'},
        {field: 'is_remix', label: 'Remix'},
        {field: 'is_cover', label: 'Cover'}
    ];
    var flagSection = document.createElement('div');
    flagSection.style.cssText = 'margin-bottom:14px;';
    var flagLbl = document.createElement('div');
    flagLbl.textContent = 'FLAGS';
    flagLbl.style.cssText = 'font-size:11px;font-weight:bold;color:var(--text-secondary);margin-bottom:4px;text-transform:uppercase;';
    flagSection.appendChild(flagLbl);
    var flagGrid = document.createElement('div');
    flagGrid.style.cssText = 'display:grid;grid-template-columns:repeat(4,1fr);gap:8px;';

    flagFields.forEach(function(ff) {
        var cell = document.createElement('div');
        cell.style.cssText = 'text-align:center;';
        var title = document.createElement('div');
        title.textContent = ff.label;
        title.style.cssText = 'font-size:11px;color:var(--text-secondary);margin-bottom:4px;';
        cell.appendChild(title);

        var kVal = k[ff.field], aVal = a[ff.field];
        var chipRow = document.createElement('div');
        chipRow.style.cssText = 'display:flex;gap:4px;justify-content:center;margin-bottom:4px;';
        var cK = document.createElement('span');
        cK.textContent = kVal ? 'Yes' : 'No';
        cK.style.cssText = 'font-size:10px;padding:1px 6px;border-radius:3px;cursor:pointer;border:1px solid var(--border);' + (kVal ? 'background:var(--promoted-song);color:#000;' : '');
        var cA = document.createElement('span');
        cA.textContent = aVal ? 'Yes' : 'No';
        cA.style.cssText = 'font-size:10px;padding:1px 6px;border-radius:3px;cursor:pointer;border:1px solid var(--border);' + (aVal ? 'background:var(--promoted-song);color:#000;' : '');
        chipRow.appendChild(cK);
        chipRow.appendChild(cA);
        cell.appendChild(chipRow);

        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = kVal || aVal;
        inputs[ff.field] = cb;
        cK.addEventListener('click', function() { cb.checked = kVal; });
        cA.addEventListener('click', function() { cb.checked = aVal; });
        cell.appendChild(cb);
        flagGrid.appendChild(cell);
    });
    flagSection.appendChild(flagGrid);
    body.appendChild(flagSection);

    addTextRow('Spotify URL', 'spotify_url', k.spotify_url, a.spotify_url, false);
    addTextRow('YouTube URL', 'youtube_url', k.youtube_url, a.youtube_url, false);
    addTextRow('Song Note', 'note', k.note, a.note, true);

    if (data.ratings.length) {
        var ratSection = document.createElement('div');
        ratSection.style.cssText = 'margin-bottom:14px;';
        var ratLbl = document.createElement('div');
        ratLbl.textContent = 'RATINGS';
        ratLbl.style.cssText = 'font-size:11px;font-weight:bold;color:var(--text-secondary);margin-bottom:6px;text-transform:uppercase;';
        ratSection.appendChild(ratLbl);

        var ratTable = document.createElement('table');
        ratTable.style.cssText = 'width:100%;border-collapse:collapse;font-size:12px;';
        var thead = document.createElement('thead');
        thead.innerHTML = '<tr><th style="text-align:left;padding:4px 6px;color:var(--text-secondary);font-size:10px;">User</th><th style="text-align:center;padding:4px 6px;color:var(--text-secondary);font-size:10px;">Kept</th><th style="text-align:center;padding:4px 6px;color:var(--text-secondary);font-size:10px;">Absorbed</th><th style="text-align:center;padding:4px 6px;color:var(--text-secondary);font-size:10px;">Result</th></tr>';
        ratTable.appendChild(thead);

        var ratBody = document.createElement('tbody');

        data.ratings.forEach(function(r) {
            var tr = document.createElement('tr');
            tr.style.cssText = 'border-top:1px solid var(--border);';

            var tdUser = document.createElement('td');
            tdUser.textContent = r.username;
            tdUser.style.cssText = 'padding:6px;color:var(--text-primary);white-space:nowrap;';
            tr.appendChild(tdUser);

            function makeRatingChip(score, note) {
                var wrapper = document.createElement('div');
                wrapper.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:2px;cursor:pointer;';
                var badge = document.createElement('span');
                badge.textContent = score !== null && score !== undefined ? score : '-';
                badge.style.cssText = 'padding:2px 8px;border-radius:4px;font-weight:bold;min-width:24px;text-align:center;border:1px solid var(--border);' + _ratingStyle(score);
                wrapper.appendChild(badge);
                if (note) {
                    var noteEl = document.createElement('div');
                    noteEl.textContent = note.length > 30 ? note.substring(0, 30) + '...' : note;
                    noteEl.title = note;
                    noteEl.style.cssText = 'font-size:10px;color:var(--text-secondary);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
                    wrapper.appendChild(noteEl);
                }
                return wrapper;
            }

            var tdKept = document.createElement('td');
            tdKept.style.cssText = 'padding:6px;text-align:center;';
            var kChip = makeRatingChip(r.kept_rating, r.kept_note);
            tdKept.appendChild(kChip);
            tr.appendChild(tdKept);

            var tdAbsorbed = document.createElement('td');
            tdAbsorbed.style.cssText = 'padding:6px;text-align:center;';
            var aChip = makeRatingChip(r.absorbed_rating, r.absorbed_note);
            tdAbsorbed.appendChild(aChip);
            tr.appendChild(tdAbsorbed);

            var tdResult = document.createElement('td');
            tdResult.style.cssText = 'padding:6px;text-align:center;';
            var resultWrap = document.createElement('div');
            resultWrap.style.cssText = 'display:flex;gap:4px;align-items:center;justify-content:center;';
            var scoreInput = document.createElement('input');
            scoreInput.type = 'number';
            scoreInput.min = '0';
            scoreInput.max = '5';
            scoreInput.style.cssText = 'width:42px;padding:3px 4px;border:1px solid var(--border);border-radius:4px;font-size:12px;text-align:center;background:var(--bg-primary);color:var(--text-primary);';
            var defaultScore = r.kept_rating !== null && r.kept_rating !== undefined ? r.kept_rating : r.absorbed_rating;
            scoreInput.value = defaultScore !== null && defaultScore !== undefined ? defaultScore : '';

            var noteInput = document.createElement('input');
            noteInput.type = 'text';
            noteInput.placeholder = 'note';
            noteInput.style.cssText = 'flex:1;min-width:0;width:80px;padding:3px 4px;border:1px solid var(--border);border-radius:4px;font-size:11px;background:var(--bg-primary);color:var(--text-primary);';
            var defaultNote = r.kept_note !== null && r.kept_note !== undefined ? r.kept_note : r.absorbed_note;
            noteInput.value = defaultNote || '';

            function highlightChips(side) {
                kChip.style.outline = side === 'kept' ? '2px solid var(--link)' : '';
                aChip.style.outline = side === 'absorbed' ? '2px solid var(--link)' : '';
            }
            kChip.addEventListener('click', function() {
                scoreInput.value = r.kept_rating !== null && r.kept_rating !== undefined ? r.kept_rating : '';
                noteInput.value = r.kept_note || '';
                highlightChips('kept');
            });
            aChip.addEventListener('click', function() {
                scoreInput.value = r.absorbed_rating !== null && r.absorbed_rating !== undefined ? r.absorbed_rating : '';
                noteInput.value = r.absorbed_note || '';
                highlightChips('absorbed');
            });

            if (r.kept_rating !== null && r.kept_rating !== undefined) highlightChips('kept');
            else if (r.absorbed_rating !== null && r.absorbed_rating !== undefined) highlightChips('absorbed');

            resultWrap.appendChild(scoreInput);
            resultWrap.appendChild(noteInput);
            tdResult.appendChild(resultWrap);
            tr.appendChild(tdResult);
            ratBody.appendChild(tr);

            ratingInputs.push({userId: r.user_id, scoreInput: scoreInput, noteInput: noteInput});
        });

        ratTable.appendChild(ratBody);
        ratSection.appendChild(ratTable);
        body.appendChild(ratSection);
    }

    var footer = document.createElement('div');
    footer.style.cssText = 'padding:12px 24px 20px;border-top:1px solid var(--border);flex-shrink:0;';

    // Reuse the persistent credential form rendered in the page at load. Because it was
    // present (hidden) during the password manager's initial page scan, the manager has
    // already attached its listeners to the password field. Relocating the form into the
    // modal and focusing the field then registers it as the focused login field
    // deterministically — no timing race, so the manager's Fill reliably targets it.
    var pwInput = null;
    if (!opts.noPassword) {
        var credForm = document.getElementById('merge-cred-form');
        pwInput = document.getElementById('merge-pw-input');
        pwInput.value = '';
        pwInput.required = true;
        pwInput.style.cssText = 'width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:4px;background:var(--bg-primary);color:var(--text-primary);box-sizing:border-box;';

        var pwLabel = document.createElement('label');
        pwLabel.textContent = 'Enter your password to confirm';
        pwLabel.htmlFor = 'merge-pw-input';
        pwLabel.style.cssText = 'display:block;font-size:13px;margin-bottom:4px;color:var(--text-primary);';
        footer.appendChild(pwLabel);
        footer.appendChild(credForm);
    }

    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;margin-top:12px;';
    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'padding:8px 16px;border-radius:4px;font-size:13px;cursor:pointer;border:none;background:var(--button-secondary);color:var(--text-primary);';
    cancelBtn.addEventListener('click', function() { _closeMergeModal(overlay); });

    var mergeBtn = document.createElement('button');
    mergeBtn.type = 'button';
    var mergeLabel = opts.confirmLabel || 'Merge';
    mergeBtn.textContent = mergeLabel;
    mergeBtn.style.cssText = 'padding:8px 16px;border-radius:4px;font-size:13px;cursor:pointer;border:none;background:var(--button-primary);color:#fff;font-weight:bold;';

    mergeBtn.addEventListener('click', function() {
        if (!inputs.name.value.trim()) { alert('Song name is required.'); return; }
        if (!opts.noPassword && !pwInput.value) { alert('Password is required.'); return; }
        mergeBtn.disabled = true;
        mergeBtn.textContent = 'Merging...';

        var payload = {
            absorbed_song_id: absorbedId,
            name: inputs.name.value.trim(),
            is_promoted: inputs.is_promoted.checked,
            is_lead: inputs.is_lead.checked,
            is_remix: inputs.is_remix.checked,
            is_cover: inputs.is_cover.checked,
            spotify_url: inputs.spotify_url.value.trim() || null,
            youtube_url: inputs.youtube_url.value.trim() || null,
            note: inputs.note.value.trim() || null,
            ratings: ratingInputs.map(function(ri) {
                return {
                    user_id: ri.userId,
                    rating: ri.scoreInput.value !== '' ? parseInt(ri.scoreInput.value) : null,
                    note: ri.noteInput.value.trim() || null
                };
            })
        };
        if (!opts.noPassword) payload.password = pwInput.value;
        if (opts.extraPayload) {
            for (var key in opts.extraPayload) {
                if (opts.extraPayload.hasOwnProperty(key)) payload[key] = opts.extraPayload[key];
            }
        }

        fetch(opts.submitUrl || ('/edit/song/' + keptId + '/merge'), {
            method: 'POST',
            headers: _csrfHeaders({'Content-Type': 'application/json'}),
            body: JSON.stringify(payload)
        }).then(function(r) {
            if (r.status === 403 && !opts.noPassword) { alert('Incorrect password.'); mergeBtn.disabled = false; mergeBtn.textContent = mergeLabel; return; }
            if (!r.ok) throw new Error('failed');
            return r.json().catch(function() { return {}; });
        }).then(function(resp) {
            if (resp === undefined) return;  // 403 path already handled
            if (opts.onSuccess) { _closeMergeModal(overlay); opts.onSuccess(resp); }
            else { window.location.reload(); }
        }).catch(function() {
            showToast('Merge failed \u2014 try again');
            mergeBtn.disabled = false;
            mergeBtn.textContent = mergeLabel;
        });
    });

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(mergeBtn);
    footer.appendChild(btnRow);
    container.appendChild(footer);

    // Focus the now-visible password field. The manager's listener is already attached
    // (the field existed at page load), so this single focus registers it as the
    // focused login field.
    if (pwInput) pwInput.focus();
}

// Focus a confirm-password modal's password field when the modal is shown. The field
// is present (hidden) in the page at load, so the password manager already has its
// listeners attached; focusing the now-visible field registers it as the focused login
// field, so the manager's Fill reliably targets it without the user clicking it first.
function focusModalPassword(modalId) {
    var modal = document.getElementById(modalId);
    if (!modal) return;
    var pw = modal.querySelector('input[type="password"]');
    if (pw) setTimeout(function() { pw.focus(); }, 0);
}

// Move the persistent credential form back to its hidden home and clear it. Must run
// before the merge overlay is removed, otherwise the form (with the password manager's
// listeners) would be torn out of the DOM along with the overlay.
function _closeMergeModal(overlay) {
    var form = document.getElementById('merge-cred-form');
    var home = document.getElementById('merge-cred-home');
    var pw = document.getElementById('merge-pw-input');
    if (pw) pw.value = '';
    if (form && home && form.parentNode !== home) home.appendChild(form);
    if (overlay) overlay.remove();
}

/* Song artist management popover */

var activeSongArtistPopover = null;

function closeSongArtistPopover() {
    if (activeSongArtistPopover) {
        activeSongArtistPopover.remove();
        activeSongArtistPopover = null;
    }
}


function _updateCollabLabel(songId, artists) {
    var row = document.getElementById('song-' + songId);
    if (!row) return;
    var td = row.querySelector('td');
    if (!td) return;
    // Remove existing collab label span (server-rendered class or client-rendered inline style)
    var existing = td.querySelector('span.text-secondary-text.italic') || td.querySelector('span[style*="font-style: italic"]');
    if (existing) {
        // Clean up adjacent whitespace text nodes to avoid accumulation on repeated updates
        while (existing.nextSibling && existing.nextSibling.nodeType === 3) existing.nextSibling.remove();
        existing.remove();
    }
    var currentId = (typeof _currentArtistId !== 'undefined') ? _currentArtistId : null;
    var isAnimePage = (typeof _isAnimePage !== 'undefined') ? _isAnimePage : false;
    var ANIME_GENDER_ID = 3;
    // Bucket artists the same way the server does
    var withEntries = [], soloNames = [], byNames = [], forNames = [], featNames = [];
    var soloParentIds = {};
    var mainIds = {};
    artists.forEach(function(a) { if (a.is_main) mainIds[a.artist_id] = true; });
    artists.forEach(function(a) {
        // Solo rules only apply when the soloist's parent group is itself a
        // main credit on the song; otherwise they are a normal artist.
        var isSoloCredit = a.is_main && a.is_soloist &&
            (a.soloist_parent_ids || []).some(function(p) { return mainIds[p]; });
        if (a.artist_id === currentId) {
            if (isSoloCredit) {
                soloNames.push(a.name);
                (a.soloist_parent_ids || []).forEach(function(p) { soloParentIds[p] = true; });
            }
            return;
        }
        var isOtherAnime = a.gender_id === ANIME_GENDER_ID;
        if (isAnimePage && !isOtherAnime && a.is_main) {
            byNames.push(a.name);
        } else if (!isAnimePage && isOtherAnime) {
            forNames.push(a.name);
        } else if (a.is_main) {
            if (isSoloCredit) {
                soloNames.push(a.name);
                (a.soloist_parent_ids || []).forEach(function(p) { soloParentIds[p] = true; });
            } else {
                withEntries.push({ id: a.artist_id, name: a.name });
            }
        } else {
            featNames.push(a.name);
        }
    });
    var miscArtists = (typeof _songMiscArtists !== 'undefined' && _songMiscArtists[songId]) ? _songMiscArtists[songId] : [];
    miscArtists.forEach(function(m) {
        // On anime pages a main misc artist is the primary singer ("by"),
        // mirroring how main real artists are bucketed.
        if (!m.is_main) featNames.push(m.name);
        else if (isAnimePage) byNames.push(m.name);
        else withEntries.push({ id: null, name: m.name });
    });
    // Credited parents of Solo-group members are dropped from "with".
    var mainNames = withEntries.filter(function(e) {
        return !(soloNames.length && e.id !== null && soloParentIds[e.id]);
    }).map(function(e) { return e.name; });
    var parts = [];
    if (mainNames.length) parts.push('(with ' + mainNames.join(', ') + ')');
    if (soloNames.length) {
        var soloJoined = soloNames.length === 1 ? soloNames[0]
            : soloNames.slice(0, -1).join(', ') + ' & ' + soloNames[soloNames.length - 1];
        parts.push('(' + soloJoined + ' Solo)');
    }
    if (byNames.length) parts.push('(by ' + byNames.join(', ') + ')');
    if (forNames.length) parts.push('(for ' + forNames.join(', ') + ')');
    if (featNames.length) parts.push('(feat. ' + featNames.join(', ') + ')');
    if (parts.length) {
        var label = document.createElement('span');
        label.style.cssText = 'color: var(--text-secondary); font-style: italic;';
        label.textContent = ' ' + parts.join(' ');
        var songLinks = td.querySelector('.song-links');
        if (songLinks) {
            td.insertBefore(label, songLinks);
            td.insertBefore(document.createTextNode(' '), songLinks);
        } else {
            td.appendChild(label);
        }
    }
}

function showSongArtists(event, songId, span) {
    event.stopPropagation();
    closeSongArtistPopover();
    closeAlbumMovePopover();
    closeAlbumArtistMovePopover();
    closeAlbumAddPopover();
    closeAlbumSongSearchPopover();

    var artists = (typeof _songArtists !== 'undefined' && _songArtists[songId]) ? _songArtists[songId] : [];
    var allArtists = (typeof _allArtists !== 'undefined') ? _allArtists : [];

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:260px; max-height:320px; overflow-y:auto;';

    var title = document.createElement('div');
    title.textContent = 'Song artists:';
    title.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:6px; color:var(--text-secondary);';
    popover.appendChild(title);
    _makeDraggable(popover, title);

    var listContainer = document.createElement('div');
    listContainer.id = 'song-artist-list-' + songId;

    function renderList() {
        listContainer.innerHTML = '';
        artists.forEach(function(a) {
            var row = document.createElement('div');
            row.style.cssText = 'display:flex; align-items:center; gap:6px; padding:2px 0;';

            var name = document.createElement('span');
            name.textContent = a.name;
            name.style.cssText = 'font-size:12px; flex:1;';
            row.appendChild(name);

            var roleBtn = document.createElement('button');
            roleBtn.textContent = a.is_main ? 'Main' : 'Feat';
            roleBtn.style.cssText = 'font-size:10px; padding:1px 6px; border:1px solid var(--border); border-radius:3px; cursor:pointer; background:' + (a.is_main ? 'var(--link,#2563EB)' : 'transparent') + '; color:' + (a.is_main ? '#fff' : 'var(--text-secondary)') + ';';
            roleBtn.addEventListener('click', function() {
                fetch('/edit/song/' + songId + '/artists/' + a.artist_id + '/role', {
                    method: 'POST',
                    headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
                }).then(function(r) {
                    if (!r.ok) throw new Error('failed');
                    return r.json();
                }).then(function(data) {
                    a.is_main = data.is_main;
                    renderList();
                    _updateCollabLabel(songId, artists);
                });
            });
            row.appendChild(roleBtn);

            if (artists.length + miscArtists.length > 1) {
                var removeBtn = document.createElement('button');
                removeBtn.textContent = '\u00d7';
                removeBtn.style.cssText = 'font-size:13px; color:var(--delete-button,#DC2626); background:none; border:none; cursor:pointer; padding:0 2px;';
                removeBtn.addEventListener('click', function() {
                    fetch('/edit/song/' + songId + '/artists/' + a.artist_id, {
                        method: 'DELETE',
                        headers: _csrfHeaders({}),
                    }).then(function(r) {
                        if (!r.ok) throw new Error('failed');
                        // If removed artist is the page artist or a child, the song leaves this discography
                        var childIds = (typeof _childArtists !== 'undefined') ? _childArtists.map(function(c) { return c.id; }) : [];
                        if (a.artist_id === _currentArtistId || childIds.indexOf(a.artist_id) !== -1) {
                            window.location.reload();
                            return;
                        }
                        artists = artists.filter(function(x) { return x.artist_id !== a.artist_id; });
                        _songArtists[songId] = artists;
                        _promoteSoleArtist();
                        renderList();
                        renderMiscList();
                        _updateCollabLabel(songId, artists);
                    });
                });
                row.appendChild(removeBtn);
            }

            listContainer.appendChild(row);
        });
    }

    // Misc artists (from song_misc_artist table) — declared before renderList()
    // so the real-artist list can count them toward the "keep at least one" rule.
    var miscArtists = (typeof _songMiscArtists !== 'undefined' && _songMiscArtists[songId]) ? _songMiscArtists[songId].slice() : [];

    // After a removal, if a single featured artist remains, promote it to main
    // (mirrors the backend so the Main/Feat label updates without a reload).
    function _promoteSoleArtist() {
        if (artists.length + miscArtists.length !== 1) return;
        if (artists.length === 1) {
            artists[0].is_main = true;
            _songArtists[songId] = artists;
        } else if (miscArtists.length === 1) {
            miscArtists[0].is_main = true;
            if (typeof _songMiscArtists !== 'undefined') _songMiscArtists[songId] = miscArtists.slice();
        }
    }

    renderList();
    popover.appendChild(listContainer);

    function _saveMiscArtists() {
        fetch('/misc/song/' + songId + '/misc-artists', {
            method: 'POST',
            headers: _csrfHeaders({'Content-Type': 'application/json'}),
            body: JSON.stringify({ misc_artists: miscArtists.map(function(m) {
                return { id: m.misc_artist_id, is_main: m.is_main };
            })}),
        }).then(function(r) { if (!r.ok) throw new Error('failed'); });
        if (typeof _songMiscArtists !== 'undefined') _songMiscArtists[songId] = miscArtists.slice();
        _updateCollabLabel(songId, artists);
    }

    var miscSection = document.createElement('div');
    miscSection.style.cssText = 'margin-top:6px; border-top:1px solid var(--border); padding-top:6px;';
    var miscTitle = document.createElement('div');
    miscTitle.textContent = 'Misc artists:';
    miscTitle.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:4px; color:var(--text-secondary);';
    miscSection.appendChild(miscTitle);

    var miscListContainer = document.createElement('div');

    function renderMiscList() {
        miscListContainer.innerHTML = '';
        miscArtists.forEach(function(m) {
            var row = document.createElement('div');
            row.style.cssText = 'display:flex; align-items:center; gap:6px; padding:2px 0;';
            var name = document.createElement('span');
            name.textContent = m.name;
            name.style.cssText = 'font-size:12px; flex:1;';
            row.appendChild(name);
            var roleBtn = document.createElement('button');
            roleBtn.textContent = m.is_main ? 'Main' : 'Feat';
            roleBtn.style.cssText = 'font-size:10px; padding:1px 6px; border:1px solid var(--border); border-radius:3px; cursor:pointer; background:' + (m.is_main ? 'var(--link,#2563EB)' : 'transparent') + '; color:' + (m.is_main ? '#fff' : 'var(--text-secondary)') + ';';
            roleBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                m.is_main = !m.is_main;
                _saveMiscArtists();
                renderMiscList();
            });
            row.appendChild(roleBtn);
            if (artists.length + miscArtists.length > 1) {
                var removeBtn = document.createElement('button');
                removeBtn.textContent = '×';
                removeBtn.style.cssText = 'font-size:13px; color:var(--delete-button,#DC2626); background:none; border:none; cursor:pointer; padding:0 2px;';
                removeBtn.addEventListener('click', function(e) {
                    e.stopPropagation();
                    miscArtists = miscArtists.filter(function(x) { return x.misc_artist_id !== m.misc_artist_id; });
                    _promoteSoleArtist();
                    _saveMiscArtists();
                    renderMiscList();
                    renderList();
                });
                row.appendChild(removeBtn);
            }
            miscListContainer.appendChild(row);
        });
    }

    renderMiscList();
    miscSection.appendChild(miscListContainer);

    // Shared filterable dropdown builder
    // opts: { placeholder, getItems(query, callback), getUsedIds(), onSelect(item) }
    function _buildSearchDropdown(opts) {
        var container = document.createElement('div');
        container.style.cssText = 'margin-top:4px; position:relative;';
        var input = document.createElement('input');
        input.type = 'text';
        input.placeholder = opts.placeholder;
        input.style.cssText = 'font-size:11px; width:100%; padding:2px 4px; border:1px solid var(--border); border-radius:3px; box-sizing:border-box;';
        var results = document.createElement('div');
        results.style.cssText = 'max-height:150px; overflow-y:auto;';
        var timer;
        function refresh() {
            clearTimeout(timer);
            var q = input.value.trim();
            timer = setTimeout(function() {
                opts.getItems(q, function(items) {
                    results.innerHTML = '';
                    var usedIds = opts.getUsedIds();
                    // Inline "Create" option whenever something is typed
                    if (opts.onCreate && q) {
                        var createRow = document.createElement('div');
                        createRow.textContent = '+ Create "' + q + '"';
                        createRow.style.cssText = 'font-size:11px; padding:2px 4px; cursor:pointer; border-radius:2px; color:var(--link,#2563EB); font-weight:bold;';
                        createRow.addEventListener('mouseenter', function() { createRow.style.background = 'var(--link,#2563EB)'; createRow.style.color = '#fff'; });
                        createRow.addEventListener('mouseleave', function() { createRow.style.background = ''; createRow.style.color = 'var(--link,#2563EB)'; });
                        createRow.addEventListener('mousedown', function(e) {
                            e.preventDefault();
                        });
                        createRow.addEventListener('click', function(e) {
                            e.stopPropagation();
                            opts.onCreate(q, function() { input.value = ''; results.innerHTML = ''; });
                        });
                        results.appendChild(createRow);
                    }
                    items.forEach(function(item) {
                        if (usedIds.indexOf(item.id) !== -1) return;
                        var row = document.createElement('div');
                        row.textContent = item.name;
                        row.style.cssText = 'font-size:11px; padding:2px 4px; cursor:pointer; border-radius:2px;';
                        row.addEventListener('mouseenter', function() { row.style.background = 'var(--link,#2563EB)'; row.style.color = '#fff'; });
                        row.addEventListener('mouseleave', function() { row.style.background = ''; row.style.color = ''; });
                        row.addEventListener('mousedown', function(e) {
                            e.preventDefault();
                        });
                        row.addEventListener('click', function(e) {
                            e.stopPropagation();
                            opts.onSelect(item);
                            input.value = '';
                            results.innerHTML = '';
                        });
                        results.appendChild(row);
                    });
                });
            }, opts.debounce || 0);
        }
        input.addEventListener('input', refresh);
        input.addEventListener('focus', refresh);
        container.appendChild(input);
        container.appendChild(results);
        return container;
    }

    miscSection.appendChild(_buildSearchDropdown({
        placeholder: '+ Add misc artist...',
        debounce: 150,
        getItems: function(q, cb) {
            fetch('/misc/search-artists?q=' + encodeURIComponent(q), {
                headers: _csrfHeaders({}),
            }).then(function(r) { return r.json(); }).then(cb);
        },
        getUsedIds: function() { return miscArtists.map(function(m) { return m.misc_artist_id; }); },
        onSelect: function(item) {
            miscArtists.push({ misc_artist_id: item.id, name: item.name, is_main: false });
            _saveMiscArtists();
            renderMiscList();
            renderList();
        },
        onCreate: function(name, done) {
            var countryId = (typeof _currentArtistCountryId !== 'undefined') ? _currentArtistCountryId : null;
            fetch('/misc/add-misc-artist', {
                method: 'POST',
                headers: _csrfHeaders({'Content-Type': 'application/json'}),
                body: JSON.stringify({ name: name, country_id: countryId }),
            }).then(function(r) { return r.json(); }).then(function(d) {
                miscArtists.push({ misc_artist_id: d.id, name: d.name, is_main: false });
                _saveMiscArtists();
                renderMiscList();
                renderList();
                if (done) done();
            });
        },
    }));
    popover.appendChild(miscSection);

    // Real artist dropdown
    var addRow = document.createElement('div');
    addRow.style.cssText = 'margin-top:6px; border-top:1px solid var(--border); padding-top:6px;';
    addRow.appendChild(_buildSearchDropdown({
        placeholder: '+ Add artist...',
        getItems: function(q, cb) {
            var lc = q.toLowerCase();
            cb(allArtists.filter(function(a) { return !lc || a.name.toLowerCase().indexOf(lc) !== -1; })
               .map(function(a) { return { id: a.id, name: a.name, isSoloist: a.isSoloist, soloistParentIds: a.soloistParentIds }; }));
        },
        getUsedIds: function() { return artists.map(function(a) { return a.artist_id; }); },
        onSelect: function(item) {
            fetch('/edit/song/' + songId + '/artists', {
                method: 'POST',
                headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
                body: 'artist_id=' + item.id + '&is_main=false',
            }).then(function(r) {
                if (!r.ok) throw new Error('failed');
                artists.push({ artist_id: item.id, name: item.name, is_main: false, is_soloist: !!item.isSoloist, soloist_parent_ids: item.soloistParentIds || [] });
                _songArtists[songId] = artists;
                renderList();
                renderMiscList();
                _updateCollabLabel(songId, artists);
            });
        },
    }));
    popover.appendChild(addRow);

    var rect = getZoomedRect(span);
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    if (rect.bottom + 2 + popover.offsetHeight + 30 > viewH) {
        popover.style.top = Math.max(0, viewH - popover.offsetHeight - 30) + 'px';
    } else {
        popover.style.top = rect.bottom + 2 + 'px';
    }
    activeSongArtistPopover = popover;
}

/* Add album modal helpers */

var _newAlbumSongCount = 0;
var _newAlbumSpotifyUrl = null;

function _onTargetArtistChange() {
    var select = document.getElementById('add-album-target-artist');
    if (!select) return;
    var newId = select.value;
    var newName = select.options[select.selectedIndex].text;
    // Update the first (auto-added) artist on every song row
    for (var i = 1; i <= _newAlbumSongCount; i++) {
        var container = document.getElementById('new-song-artists-' + i);
        if (!container) continue;
        var firstRow = container.querySelector('.new-song-artist-row');
        if (!firstRow) continue;
        firstRow.dataset.artistId = newId;
        var nameSpan = firstRow.querySelector('span');
        if (nameSpan) nameSpan.textContent = newName;
        updateNewSongArtistDropdown(i);
    }
}

document.addEventListener('change', function(e) {
    if (e.target.id === 'add-album-target-artist') _onTargetArtistChange();
    if (e.target.id === 'new-album-type') _autofillSingleName();
});
document.addEventListener('change', function(e) {
    if (e.target.id === 'new-album-name') _autofillSingleName();
});

function _autofillSingleName() {
    var type = document.getElementById('new-album-type');
    if (!type || type.value !== '2') return;
    var albumName = (document.getElementById('new-album-name') || {}).value || '';
    if (!albumName.trim()) return;
    // Add a song if none exist
    var firstSong = document.querySelector('#new-album-songs .new-album-song-name');
    if (!firstSong) {
        var targetSelect = document.getElementById('add-album-target-artist');
        var artistId = targetSelect ? parseInt(targetSelect.value) : (typeof _currentArtistId !== 'undefined' ? _currentArtistId : 0);
        addNewAlbumSong(artistId);
        firstSong = document.querySelector('#new-album-songs .new-album-song-name');
    }
    if (firstSong && !firstSong.value.trim()) {
        firstSong.value = albumName.trim();
        firstSong.dispatchEvent(new Event('input', {bubbles: true}));
    }
}

function resetAddAlbumModal() {
    _newAlbumSongCount = 0;
    _newAlbumSpotifyUrl = null;
    var targetArtist = document.getElementById('add-album-target-artist');
    if (targetArtist) targetArtist.selectedIndex = 0;
    var name = document.getElementById('new-album-name');
    if (name) name.value = '';
    var date = document.getElementById('new-album-date');
    if (date) { date.value = ''; date.dispatchEvent(new Event('input', {bubbles: true})); }
    var type = document.getElementById('new-album-type');
    if (type) type.selectedIndex = 0;
    var note = document.getElementById('new-album-note');
    if (note) note.value = '';
    document.querySelectorAll('#new-album-genres input').forEach(function(cb) { cb.checked = false; });
    var songs = document.getElementById('new-album-songs');
    if (songs) songs.innerHTML = '';
    var searchInput = document.getElementById('album-song-search');
    if (searchInput) searchInput.value = '';
    var searchResults = document.getElementById('album-song-search-results');
    if (searchResults) { searchResults.style.display = 'none'; searchResults.innerHTML = ''; }
    var spotifyUrl = document.getElementById('spotify-album-url');
    if (spotifyUrl) spotifyUrl.value = '';
    validateAddAlbum();
}

function validateAddAlbum() {
    var btn = document.getElementById('add-album-submit-btn');
    if (!btn) return;
    var valid = true;

    var name = document.getElementById('new-album-name');
    if (!name || !name.value.trim()) valid = false;

    var date = document.getElementById('new-album-date');
    if (!date || !isRealDate(date.value.trim())) valid = false;

    var genreChecked = document.querySelector('#new-album-genres input:checked');
    if (!genreChecked) valid = false;

    var songDivs = document.querySelectorAll('#new-album-songs > [id^="new-song-"]');
    if (!songDivs.length) valid = false;

    songDivs.forEach(function(div) {
        // Existing songs are always valid
        if (div.dataset.existingSongId) return;
        var songName = div.querySelector('.new-album-song-name');
        if (!songName || !songName.value.trim()) valid = false;
        var hasMain = false;
        div.querySelectorAll('.new-song-artist-row').forEach(function(row) {
            var role = row.querySelector('.new-song-artist-role');
            if (role && role.value === 'main') hasMain = true;
        });
        if (!hasMain) valid = false;
    });

    btn.disabled = !valid;
    btn.style.opacity = valid ? '1' : '0.5';
    btn.style.cursor = valid ? 'pointer' : 'not-allowed';
}

function addNewAlbumSong(currentArtistId) {
    _newAlbumSongCount++;
    var n = _newAlbumSongCount;
    var container = document.getElementById('new-album-songs');
    var row = document.createElement('div');
    row.id = 'new-song-' + n;
    row.className = 'mb-2 p-2 border rounded';
    row.style.borderColor = 'var(--border)';
    row.innerHTML =
        '<div class="flex gap-2 items-center mb-1">' +
            '<input type="text" placeholder="Song name" class="flex-1 px-2 py-1 border rounded text-sm new-album-song-name" style="border-color:var(--border);" oninput="validateAddAlbum()">' +
            '<label class="text-xs"><input type="checkbox" class="new-song-promoted"> Promoted</label>' +
            '<label class="text-xs"><input type="checkbox" class="new-song-remix"> Remix</label>' +
            '<label class="text-xs"><input type="checkbox" class="new-song-cover"> Cover</label>' +
            '<button type="button" onclick="this.closest(\'[id^=new-song-]\').remove();validateAddAlbum()" class="text-xs px-1" style="color:var(--delete-button,#DC2626);">&times;</button>' +
        '</div>' +
        '<div class="flex items-center flex-wrap gap-2" style="padding: 4px 8px;">' +
            '<span class="text-xs" style="color:var(--text-secondary);">Artists:</span>' +
            '<div id="new-song-artists-' + n + '" class="flex flex-wrap gap-2" style="margin-right: 4px;"></div>' +
            '<select class="new-song-artist-select text-xs px-1 border rounded" style="border-color:var(--border); max-width:150px;" onchange="onNewSongArtistChange(this,' + n + ')">' +
                newSongArtistOptions(n) +
            '</select>' +
            '<span style="cursor:pointer; margin-left:4px;" onclick="event.stopPropagation();promptLocalUrl(this, \'spotify_url\', \'Spotify URL\')" title="Set Spotify URL"><img src="/static/img/spotify.png" style="width:12px; height:12px; filter:grayscale(1) invert(1);"></span>' +
            '<span style="cursor:pointer;" onclick="event.stopPropagation();promptLocalUrl(this, \'youtube_url\', \'YouTube URL\')" title="Set YouTube URL"><img src="/static/img/youtube.png" style="width:12px; height:12px; filter:grayscale(1) invert(1);"></span>' +
            '<span style="cursor:pointer; font-size:12px; color:var(--text-secondary);" onclick="event.stopPropagation();promptLocalUrl(this, \'note\', \'Note\', {placeholder:\'Note...\', multiline:true})" title="Set note">&#9998;</span>' +
        '</div>' +
        '<div style="padding: 4px 8px;">' +
            '<span class="text-xs" style="color:var(--text-secondary);">Misc artists:</span>' +
            '<div id="new-song-misc-artists-' + n + '" class="flex flex-wrap gap-2" style="margin: 2px 0;"></div>' +
            '<div style="position:relative;">' +
                '<input type="text" class="new-song-misc-search text-xs px-1 border rounded" placeholder="+ Add misc artist..." style="border-color:var(--border); width:180px;" data-song-num="' + n + '">' +
                '<div class="new-song-misc-results" style="max-height:120px; overflow-y:auto; position:absolute; z-index:60; background:var(--bg-secondary,#fff); border:1px solid var(--border); border-radius:3px; display:none; width:180px;"></div>' +
            '</div>' +
        '</div>';
    container.appendChild(row);
    _initNewSongMiscSearch(n);
    // Auto-add target artist (from dropdown or page artist) as main
    var targetSelect = document.getElementById('add-album-target-artist');
    var targetId = targetSelect ? parseInt(targetSelect.value) : currentArtistId;
    var targetName = targetSelect ? targetSelect.options[targetSelect.selectedIndex].text : _currentArtistName();
    addNewSongArtist(n, targetId, targetName, true);
    validateAddAlbum();
    // Scroll modal so the new song and buttons stay visible
    var modal = container.closest('[style*="overflow-y"]');
    if (modal) setTimeout(function() { modal.scrollTop = modal.scrollHeight; }, 50);
}

function _currentArtistName() {
    if (typeof _allArtists !== 'undefined' && typeof _currentArtistId !== 'undefined') {
        var a = _allArtists.find(function(x) { return x.id === _currentArtistId; });
        if (a) return a.name;
    }
    return 'Current Artist';
}

function newSongArtistOptions(songNum) {
    var used = newSongUsedArtistIds(songNum);
    var opts = '<option value="">-- Add artist --</option>';
    if (typeof _allArtists !== 'undefined') {
        _allArtists.forEach(function(a) {
            if (used.indexOf(a.id) === -1) {
                opts += '<option value="' + a.id + '">' + a.name.replace(/</g, '&lt;') + '</option>';
            }
        });
    }
    return opts;
}

function newSongUsedArtistIds(songNum) {
    var ids = [];
    var container = document.getElementById('new-song-artists-' + songNum);
    if (container) {
        container.querySelectorAll('.new-song-artist-row').forEach(function(row) {
            if (row.dataset.artistId) ids.push(parseInt(row.dataset.artistId));
        });
    }
    return ids;
}

function addNewSongArtist(songNum, artistId, artistName, isMain) {
    var container = document.getElementById('new-song-artists-' + songNum);
    var count = container.children.length;
    var row = document.createElement('div');
    row.className = 'flex items-center gap-1 new-song-artist-row';
    row.dataset.artistId = artistId || '';
    row.innerHTML =
        '<span class="text-xs" style="margin-right: 4px;">' + (artistName || '').replace(/</g, '&lt;') + '</span>' +
        '<select class="new-song-artist-role text-xs px-1 border rounded" style="border-color:var(--border);" onchange="validateAddAlbum()">' +
            '<option value="main"' + (isMain ? ' selected' : '') + '>Main</option>' +
            '<option value="feat"' + (!isMain ? ' selected' : '') + '>Featured</option>' +
        '</select>' +
        (count > 0 ? '<button type="button" onclick="removeNewSongArtist(this,' + songNum + ')" class="text-red-500 text-xs">x</button>' : '');
    container.appendChild(row);
    updateNewSongArtistDropdown(songNum);
    validateAddAlbum();
}

function removeNewSongArtist(btn, songNum) {
    btn.parentElement.remove();
    updateNewSongArtistDropdown(songNum);
    validateAddAlbum();
}

function updateNewSongArtistDropdown(songNum) {
    var songDiv = document.getElementById('new-song-' + songNum);
    if (!songDiv) return;
    var select = songDiv.querySelector('.new-song-artist-select');
    if (select) {
        select.innerHTML = newSongArtistOptions(songNum);
        select.value = '';
    }
}

function onNewSongArtistChange(select, songNum) {
    var id = parseInt(select.value);
    if (!id) return;
    var artist = _allArtists.find(function(a) { return a.id === id; });
    if (!artist) return;
    addNewSongArtist(songNum, id, artist.name, false);
    select.value = '';
}

function _initNewSongMiscSearch(songNum) {
    var songDiv = document.getElementById('new-song-' + songNum);
    if (!songDiv) return;
    var input = songDiv.querySelector('.new-song-misc-search');
    var resultsDiv = songDiv.querySelector('.new-song-misc-results');
    if (!input || !resultsDiv) return;
    var timer;
    function refresh() {
        clearTimeout(timer);
        var q = input.value.trim();
        timer = setTimeout(function() {
            fetch('/misc/search-artists?q=' + encodeURIComponent(q), { headers: _csrfHeaders({}) })
                .then(function(r) { return r.json(); })
                .then(function(items) {
                    resultsDiv.innerHTML = '';
                    var usedIds = _getNewSongMiscArtistIds(songNum);
                    var filtered = items.filter(function(item) { return usedIds.indexOf(item.id) === -1; });
                    if (!filtered.length) { resultsDiv.style.display = 'none'; return; }
                    resultsDiv.style.display = 'block';
                    filtered.forEach(function(item) {
                        var row = document.createElement('div');
                        row.textContent = item.name;
                        row.style.cssText = 'font-size:11px; padding:2px 4px; cursor:pointer; border-radius:2px;';
                        row.addEventListener('mouseenter', function() { row.style.background = 'var(--link,#2563EB)'; row.style.color = '#fff'; });
                        row.addEventListener('mouseleave', function() { row.style.background = ''; row.style.color = ''; });
                        row.addEventListener('mousedown', function(e) {
                            e.preventDefault();
                            _addNewSongMiscArtist(songNum, item.id, item.name);
                            input.value = '';
                            resultsDiv.style.display = 'none';
                        });
                        resultsDiv.appendChild(row);
                    });
                });
        }, 150);
    }
    input.addEventListener('input', refresh);
    input.addEventListener('focus', refresh);
    input.addEventListener('blur', function() { setTimeout(function() { resultsDiv.style.display = 'none'; }, 200); });
    // + New button with country dropdown (matches misc page pattern)
    var createRow = document.createElement('div');
    createRow.style.cssText = 'display:flex; gap:4px; align-items:center; margin-top:2px;';
    var newBtn = document.createElement('button');
    newBtn.type = 'button';
    newBtn.textContent = '+ New';
    newBtn.style.cssText = 'font-size:10px; padding:2px 8px; border-radius:3px; background:var(--edit-on-button,#16a34a); color:var(--button-text,#fff); border:none; cursor:pointer;';
    var countrySel = document.createElement('select');
    countrySel.style.cssText = 'font-size:10px; padding:1px 4px; border:1px solid var(--border); border-radius:3px;';
    var countries = (typeof _allCountries !== 'undefined') ? _allCountries : [];
    var defaultCid = (typeof _currentArtistCountryId !== 'undefined') ? _currentArtistCountryId : '';
    countries.forEach(function(c) {
        var opt = document.createElement('option');
        opt.value = c.id; opt.textContent = c.name;
        if (c.id === defaultCid) opt.selected = true;
        countrySel.appendChild(opt);
    });
    newBtn.addEventListener('click', function() {
        var n = input.value.trim();
        if (!n) return;
        var cid = parseInt(countrySel.value);
        fetch('/misc/add-misc-artist', {
            method: 'POST',
            headers: _csrfHeaders({'Content-Type': 'application/json'}),
            body: JSON.stringify({name: n, country_id: cid}),
        }).then(function(r) { return r.json(); }).then(function(d) {
            _addNewSongMiscArtist(songNum, d.id, d.name);
            input.value = '';
            resultsDiv.style.display = 'none';
        });
    });
    createRow.appendChild(newBtn);
    createRow.appendChild(countrySel);
    input.parentElement.appendChild(createRow);
}

function _getNewSongMiscArtistIds(songNum) {
    var container = document.getElementById('new-song-misc-artists-' + songNum);
    var ids = [];
    if (container) {
        container.querySelectorAll('.new-song-misc-row').forEach(function(row) {
            ids.push(parseInt(row.dataset.miscArtistId));
        });
    }
    return ids;
}

function _addNewSongMiscArtist(songNum, miscId, miscName) {
    var container = document.getElementById('new-song-misc-artists-' + songNum);
    if (!container) return;
    var row = document.createElement('div');
    row.className = 'flex items-center gap-1 new-song-misc-row';
    row.dataset.miscArtistId = miscId;
    row.innerHTML =
        '<span class="text-xs" style="margin-right:4px;">' + miscName.replace(/</g, '&lt;') + '</span>' +
        '<select class="new-song-misc-role text-xs px-1 border rounded" style="border-color:var(--border);">' +
            '<option value="main">Main</option><option value="feat" selected>Featured</option>' +
        '</select>' +
        '<button type="button" onclick="this.parentElement.remove()" class="text-xs" style="color:var(--delete-button,#DC2626); background:none; border:none; cursor:pointer;">x</button>';
    container.appendChild(row);
}


function submitNewAlbum(artistId) {
    var name = document.getElementById('new-album-name').value.trim();
    var date = document.getElementById('new-album-date').value;
    var typeId = parseInt(document.getElementById('new-album-type').value);
    var noteEl = document.getElementById('new-album-note');
    var albumNote = noteEl ? noteEl.value.trim() : '';

    if (!name) { showToast('Album name is required'); return; }
    if (!isRealDate(date.trim())) { showToast('A valid full release date (yyyy-mm-dd) is required'); return; }

    var genreIds = [];
    document.querySelectorAll('#new-album-genres input:checked').forEach(function(cb) {
        genreIds.push(parseInt(cb.value));
    });
    if (!genreIds.length) { showToast('At least one genre is required'); return; }

    var songs = [];
    document.querySelectorAll('[id^="new-song-"]').forEach(function(songDiv) {
        // Existing song — just reference by ID
        if (songDiv.dataset.existingSongId) {
            songs.push({ existing_song_id: parseInt(songDiv.dataset.existingSongId) });
            return;
        }
        var nameInput = songDiv.querySelector('.new-album-song-name');
        var n = nameInput ? nameInput.value.trim() : '';
        if (!n) return;
        var artists = [];
        songDiv.querySelectorAll('.new-song-artist-row').forEach(function(row) {
            var role = row.querySelector('.new-song-artist-role');
            artists.push({
                artist_id: row.dataset.artistId ? parseInt(row.dataset.artistId) : null,
                is_main: role ? role.value === 'main' : true,
            });
        });
        var miscArtists = [];
        songDiv.querySelectorAll('.new-song-misc-row').forEach(function(mrow) {
            var role = mrow.querySelector('.new-song-misc-role');
            miscArtists.push({
                misc_artist_id: parseInt(mrow.dataset.miscArtistId),
                is_main: role ? role.value === 'main' : false,
            });
        });
        var songEntry = {
            name: n,
            is_promoted: songDiv.querySelector('.new-song-promoted') ? songDiv.querySelector('.new-song-promoted').checked : false,
            is_remix: songDiv.querySelector('.new-song-remix') ? songDiv.querySelector('.new-song-remix').checked : false,
            is_cover: songDiv.querySelector('.new-song-cover') ? songDiv.querySelector('.new-song-cover').checked : false,
            artists: artists,
            misc_artists: miscArtists,
        };
        if (songDiv.dataset.spotifyUrl) songEntry.spotify_url = songDiv.dataset.spotifyUrl;
        if (songDiv.dataset.youtubeUrl) songEntry.youtube_url = songDiv.dataset.youtubeUrl;
        if (songDiv.dataset.note) songEntry.note = songDiv.dataset.note;
        songs.push(songEntry);
    });

    if (!songs.length) { showToast('Add at least one song'); return; }

    var songCount = songs.length + ' song' + (songs.length !== 1 ? 's' : '');
    showConfirm('Add album?', 'Add album "' + name + '" with ' + songCount + '?', function() {
        var data = {
            name: name,
            release_date: date,
            album_type_id: typeId,
            genre_ids: genreIds,
            songs: songs,
            spotify_url: _newAlbumSpotifyUrl || null,
            note: albumNote || null,
        };

        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
    if (window._canEdit) headers['X-Edit-Source'] = 'editor';

        fetch('/edit/artist/' + artistId + '/add-album', {
            method: 'POST',
            headers: headers,
            body: 'data=' + encodeURIComponent(JSON.stringify(data)),
        }).then(function(r) {
            if (!r.ok) throw new Error('save failed');
            return r.json();
        }).then(function(respData) {
            if (respData && respData.album_id) {
                window.location.href = window.location.pathname + window.location.search + '#album-' + respData.album_id;
                window.location.reload();
            } else {
                window.location.reload();
            }
        }).catch(function() {
            showToast('Failed to add album — try again');
        });
    }, 'Add');
}

// Validate add-album modal on any input/change inside it (event delegation
// so it works even when the modal is loaded later via HTMX)
document.addEventListener('input', function(e) {
    if (e.target.closest('#add-album-modal')) validateAddAlbum();
});
document.addEventListener('change', function(e) {
    if (e.target.closest('#add-album-modal')) validateAddAlbum();
});

/* Search existing songs for add-album modal */

var _albumSongSearchTimer = null;
function debouncedAlbumSongSearch(artistId) {
    clearTimeout(_albumSongSearchTimer);
    _albumSongSearchTimer = setTimeout(function() { albumSongSearch(artistId); }, 600);
}

function albumSongSearch(artistId) {
    var input = document.getElementById('album-song-search');
    var results = document.getElementById('album-song-search-results');
    if (!input || !results) return;
    var q = input.value.trim();
    if (q.length < 2) { results.style.display = 'none'; return; }

    fetch('/edit/artist/' + artistId + '/search-songs?q=' + encodeURIComponent(q))
        .then(function(r) { return r.json(); })
        .then(function(songs) {
            if (!songs.length) {
                results.innerHTML = '<div class="px-3 py-2" style="color:var(--text-secondary);">No songs found</div>';
                results.style.display = 'block';
                return;
            }
            // Filter out songs already added to the album
            var addedIds = getAddedExistingSongIds();
            songs = songs.filter(function(s) { return addedIds.indexOf(s.id) === -1; });
            if (!songs.length) {
                results.innerHTML = '<div class="px-3 py-2" style="color:var(--text-secondary);">All matching songs already added</div>';
                results.style.display = 'block';
                return;
            }
            var html = '';
            var lastWasCurrent = null;
            songs.forEach(function(s) {
                if (lastWasCurrent !== null && lastWasCurrent && !s.is_current_artist) {
                    html += '<div style="border-top:1px solid var(--border); margin:2px 0;"></div>';
                }
                lastWasCurrent = s.is_current_artist;
                html += '<div class="px-3 py-1 cursor-pointer album-song-result" style="' +
                    (s.is_current_artist ? 'font-weight:500;' : '') +
                    '" data-song-id="' + s.id + '" data-song-name="' + s.name.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;') + '" data-artist-name="' + s.artist.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;') + '"' +
                    ' onmouseover="this.style.background=\'var(--bg-hover)\'" onmouseout="this.style.background=\'transparent\'">' +
                    '<span>' + s.name.replace(/</g, '&lt;') + '</span>' +
                    '<span style="color:var(--text-secondary);"> — ' + s.artist.replace(/</g, '&lt;') + ' (' + s.album.replace(/</g, '&lt;') + ')</span>' +
                    '</div>';
            });
            results.innerHTML = html;
            results.style.display = 'block';
        });
}

function getAddedExistingSongIds() {
    var ids = [];
    document.querySelectorAll('#new-album-songs [data-existing-song-id]').forEach(function(el) {
        ids.push(parseInt(el.dataset.existingSongId));
    });
    return ids;
}

function addExistingSongToAlbum(songId, songName, artistName) {
    _newAlbumSongCount++;
    var n = _newAlbumSongCount;
    var container = document.getElementById('new-album-songs');
    var row = document.createElement('div');
    row.id = 'new-song-' + n;
    row.className = 'mb-2 p-2 border rounded';
    row.style.borderColor = 'var(--border)';
    row.dataset.existingSongId = songId;
    row.innerHTML =
        '<div class="flex gap-2 items-center">' +
            '<span class="flex-1 text-sm">' + songName.replace(/</g, '&lt;') +
            ' <span style="color:var(--text-secondary); font-size:11px;">— ' + artistName.replace(/</g, '&lt;') + ' (existing)</span></span>' +
            '<button type="button" onclick="this.closest(\'[id^=new-song-]\').remove();validateAddAlbum()" class="text-xs px-1" style="color:var(--delete-button,#DC2626);">&times;</button>' +
        '</div>';
    container.appendChild(row);

    // Clear search
    var input = document.getElementById('album-song-search');
    if (input) input.value = '';
    var results = document.getElementById('album-song-search-results');
    if (results) results.style.display = 'none';

    validateAddAlbum();
    // Scroll modal so the new song and buttons stay visible
    var modal = container.closest('[style*="overflow-y"]');
    if (modal) setTimeout(function() { modal.scrollTop = modal.scrollHeight; }, 50);
}

// Delegated click handler for search results
document.addEventListener('click', function(e) {
    var item = e.target.closest('.album-song-result');
    if (item) {
        addExistingSongToAlbum(
            parseInt(item.dataset.songId),
            item.dataset.songName,
            item.dataset.artistName
        );
        return;
    }
    // Close search results when clicking outside
    var results = document.getElementById('album-song-search-results');
    var input = document.getElementById('album-song-search');
    if (results && input && !results.contains(e.target) && e.target !== input) {
        results.style.display = 'none';
    }
});

/* Remove song from album (no password required) */


function doRemoveFromAlbum(songId, albumId, deleteAlbum) {
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
    if (window._canEdit) headers['X-Edit-Source'] = 'editor';
    var body = deleteAlbum ? 'delete_album=1' : '';
    fetch('/edit/song/' + songId + '/remove-from-album/' + albumId, {
        method: 'POST',
        headers: headers,
        body: body,
    }).then(function(r) {
        if (!r.ok) throw new Error('failed');
        window.location.reload();
    }).catch(function() {
        showToast('Remove failed — try again');
    });
}

/* Drag-and-drop song reorder within album */

var _dragSongRow = null;

function moveSong(songId, albumId, targetSongId, direction) {
    fetch('/edit/album/' + albumId + '/move-song', {
        method: 'POST',
        headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
        body: 'song_id=' + songId + '&target_song_id=' + targetSongId + '&direction=' + direction,
    }).then(function(r) {
        if (!r.ok) throw new Error('failed');
        window.location.reload();
    }).catch(function() {
        showToast('Reorder failed — try again');
    });
}

function _clearDragIndicators() {
    var els = document.querySelectorAll('.song-drag-above, .song-drag-below');
    for (var i = 0; i < els.length; i++) {
        els[i].classList.remove('song-drag-above', 'song-drag-below');
    }
}

function _dragDirection(albumId, sourceRow, targetRow) {
    var rows = document.querySelectorAll('tr.album-row-' + albumId + '[data-song-id]');
    var srcIdx = -1, tgtIdx = -1;
    for (var i = 0; i < rows.length; i++) {
        if (rows[i] === sourceRow) srcIdx = i;
        if (rows[i] === targetRow) tgtIdx = i;
    }
    return srcIdx < tgtIdx ? 'down' : 'up';
}

document.addEventListener('mousedown', function(e) {
    var handle = e.target.closest('.drag-handle');
    if (!handle) return;
    var row = handle.closest('tr[data-song-id]');
    if (row) row.setAttribute('draggable', 'true');
});

document.addEventListener('mouseup', function() {
    if (_dragSongRow) return;
    var row = document.querySelector('tr[draggable="true"]');
    if (row) row.removeAttribute('draggable');
});

document.addEventListener('dragstart', function(e) {
    var row = e.target.closest('tr[data-song-id]');
    if (!row || !row.getAttribute('draggable')) return;
    _dragSongRow = row;
    row.style.opacity = '0.4';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', row.dataset.songId);
});

document.addEventListener('dragover', function(e) {
    if (!_dragSongRow) return;
    var targetRow = e.target.closest('tr[data-song-id]');
    if (!targetRow || targetRow === _dragSongRow) return;
    if (targetRow.dataset.albumId !== _dragSongRow.dataset.albumId) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    _clearDragIndicators();
    var dir = _dragDirection(targetRow.dataset.albumId, _dragSongRow, targetRow);
    targetRow.classList.add(dir === 'up' ? 'song-drag-above' : 'song-drag-below');
});

document.addEventListener('dragleave', function(e) {
    if (!_dragSongRow) return;
    var targetRow = e.target.closest('tr[data-song-id]');
    if (targetRow) targetRow.classList.remove('song-drag-above', 'song-drag-below');
});

document.addEventListener('drop', function(e) {
    if (!_dragSongRow) return;
    e.preventDefault();
    var targetRow = e.target.closest('tr[data-song-id]');
    if (!targetRow || targetRow === _dragSongRow) return;
    if (targetRow.dataset.albumId !== _dragSongRow.dataset.albumId) return;

    var albumId = _dragSongRow.dataset.albumId;
    var songId = _dragSongRow.dataset.songId;
    var targetSongId = targetRow.dataset.songId;
    var dir = _dragDirection(albumId, _dragSongRow, targetRow);
    _clearDragIndicators();
    moveSong(songId, albumId, targetSongId, dir === 'down' ? 'after' : 'before');
});

document.addEventListener('dragend', function(e) {
    if (_dragSongRow) {
        _dragSongRow.style.opacity = '';
        _dragSongRow.removeAttribute('draggable');
        _dragSongRow = null;
    }
    _clearDragIndicators();
});

/* Shared delete confirmation modal */

var _deleteIsAjax = false;

var _deleteRedirectUrl = null;

var _deleteOnSuccess = null;


function showDeleteConfirm(title, msg, action, ajax, btnLabel, redirectUrl, onSuccess) {
    _deleteIsAjax = !!ajax;
    _deleteRedirectUrl = redirectUrl || null;
    _deleteOnSuccess = (typeof onSuccess === 'function') ? onSuccess : null;
    document.getElementById('confirm-delete-title').textContent = title;
    document.getElementById('confirm-delete-msg').textContent = msg;
    var form = document.getElementById('confirm-delete-form');
    form.action = action;
    var pwField = document.getElementById('confirm-delete-pw');
    if (pwField) pwField.value = '';
    document.getElementById('confirm-delete-btn').textContent = btnLabel || 'Delete';
    document.getElementById('confirm-delete-modal').style.display = 'flex';
    focusModalPassword('confirm-delete-modal');
}

(function() {
    var form = document.getElementById('confirm-delete-form');
    if (!form) return;
    form.addEventListener('submit', function(e) {
        if (!_deleteIsAjax) return; // let normal form submit handle artist delete (redirect)
        e.preventDefault();
        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
    if (window._canEdit) headers['X-Edit-Source'] = 'editor';
        var body = new URLSearchParams(new FormData(form)).toString();
        fetch(form.action, {
            method: 'POST',
            headers: headers,
            body: body,
        }).then(function(r) {
            if (r.status === 403) { alert('Incorrect password'); return; }
            if (!r.ok) throw new Error('failed');
            document.getElementById('confirm-delete-modal').style.display = 'none';
            if (_deleteOnSuccess) {
                _deleteOnSuccess();
            } else if (_deleteRedirectUrl) {
                window.location.href = _deleteRedirectUrl;
            } else {
                window.location.reload();
            }
        }).catch(function() {
            showToast('Action failed — try again');
        });
    });
})();

// Song note editor — edit-mode only, triggered by right-click on song name cell
var activeSongNote = null;

function showSongNoteInput(event, tdEl) {
    event.preventDefault();
    event.stopPropagation();
    if (activeSongNote) closeSongNoteInput();

    var songId = tdEl.getAttribute('data-song-id');
    var existingNote = tdEl.getAttribute('data-song-note') || '';
    var overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed; z-index:10000; background:var(--bg-secondary); border:1px solid var(--border); border-radius:8px; padding:12px; box-shadow:0 4px 16px rgba(0,0,0,.25); width:240px;';

    var noteTitle = document.createElement('div');
    noteTitle.textContent = 'Song note';
    noteTitle.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:6px; color:var(--text-secondary);';
    overlay.appendChild(noteTitle);
    _makeDraggable(overlay, noteTitle);

    var textarea = document.createElement('textarea');
    textarea.value = existingNote;
    textarea.style.cssText = 'width:100%; height:80px; resize:vertical; background:var(--bg-primary); color:var(--text-primary); border:1px solid var(--border); border-radius:4px; padding:6px; font-size:12px; font-family:inherit;';
    overlay.appendChild(textarea);

    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex; gap:6px; margin-top:8px; justify-content:flex-end;';

    var saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'padding:4px 12px; border-radius:4px; border:none; background:var(--edit-on-button); color:#fff; cursor:pointer; font-size:12px;';
    saveBtn.onclick = function () { submitSongNote(songId, textarea.value.trim(), tdEl); };

    var cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'padding:4px 12px; border-radius:4px; border:1px solid var(--border); background:var(--bg-secondary); color:var(--text-primary); cursor:pointer; font-size:12px;';
    cancelBtn.onclick = closeSongNoteInput;

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    overlay.appendChild(btnRow);
    document.body.appendChild(overlay);

    var rect = getZoomedRect(tdEl);
    overlay.style.left = Math.min(rect.right - 240, window.innerWidth - 260) + 'px';
    overlay.style.top = (rect.bottom + 6) + 'px';

    textarea.focus();
    textarea.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { e.preventDefault(); closeSongNoteInput(); }
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitSongNote(songId, textarea.value.trim(), tdEl); }
    });

    activeSongNote = { overlay: overlay, td: tdEl };
}

function closeSongNoteInput() {
    if (!activeSongNote) return;
    activeSongNote.overlay.remove();
    activeSongNote = null;
}

function submitSongNote(songId, noteText, tdEl) {
    var formData = new FormData();
    formData.append('value', noteText);
    fetch('/edit/song/' + songId + '/note', { method: 'POST', headers: _csrfHeaders({}), body: formData })
        .then(function (r) { return r.text(); })
        .then(function (text) {
            var note = text.trim();
            if (note) {
                tdEl.classList.add('has-song-note');
                tdEl.setAttribute('data-song-note', note);
            } else {
                tdEl.classList.remove('has-song-note');
                tdEl.removeAttribute('data-song-note');
            }
            closeSongNoteInput();
        });
}

// Right-click on song name cell opens note editor (edit mode only)
document.addEventListener('contextmenu', function (e) {
    var td = e.target.closest('td.song-name-cell');
    if (!td) return;
    if (!window._canEdit) return;
    showSongNoteInput(e, td);
});

// 'n' key on hovered song name cell opens note editor (edit mode only)
var _hoveredSongCell = null;
document.addEventListener('mouseover', function (e) {
    var td = e.target.closest('td.song-name-cell');
    _hoveredSongCell = td || null;
});
document.addEventListener('keydown', function (e) {
    if (e.key !== 'n' || !_hoveredSongCell || activeSongNote) return;
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
    if (!window._canEdit) return;
    e.preventDefault();
    showSongNoteInput(e, _hoveredSongCell);
});

// Close song note overlay on outside click
document.addEventListener('mousedown', function (e) {
    if (activeSongNote && !activeSongNote.overlay.contains(e.target) && !activeSongNote.td.contains(e.target)) {
        closeSongNoteInput();
    }
});

// Album note editor — edit-mode only, triggered by right-click on album header cell
var activeAlbumNote = null;

function showAlbumNoteInput(event, tdEl) {
    event.preventDefault();
    event.stopPropagation();
    if (activeAlbumNote) closeAlbumNoteInput();

    var albumId = tdEl.getAttribute('data-album-id');
    var existingNote = tdEl.getAttribute('data-album-note') || '';
    var overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed; z-index:10000; background:var(--bg-secondary); border:1px solid var(--border); border-radius:8px; padding:12px; box-shadow:0 4px 16px rgba(0,0,0,.25); width:240px;';

    var noteTitle = document.createElement('div');
    noteTitle.textContent = 'Album note';
    noteTitle.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:6px; color:var(--text-secondary);';
    overlay.appendChild(noteTitle);
    _makeDraggable(overlay, noteTitle);

    var textarea = document.createElement('textarea');
    textarea.value = existingNote;
    textarea.style.cssText = 'width:100%; height:80px; resize:vertical; background:var(--bg-primary); color:var(--text-primary); border:1px solid var(--border); border-radius:4px; padding:6px; font-size:12px; font-family:inherit;';
    overlay.appendChild(textarea);

    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex; gap:6px; margin-top:8px; justify-content:flex-end;';

    var saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'padding:4px 12px; border-radius:4px; border:none; background:var(--edit-on-button); color:#fff; cursor:pointer; font-size:12px;';
    saveBtn.onclick = function () { submitAlbumNote(albumId, textarea.value.trim(), tdEl); };

    var cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'padding:4px 12px; border-radius:4px; border:1px solid var(--border); background:var(--bg-secondary); color:var(--text-primary); cursor:pointer; font-size:12px;';
    cancelBtn.onclick = closeAlbumNoteInput;

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    overlay.appendChild(btnRow);
    document.body.appendChild(overlay);

    var rect = getZoomedRect(tdEl);
    overlay.style.left = Math.min(rect.left, window.innerWidth - 260) + 'px';
    overlay.style.top = (rect.bottom + 6) + 'px';

    textarea.focus();
    textarea.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { e.preventDefault(); closeAlbumNoteInput(); }
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitAlbumNote(albumId, textarea.value.trim(), tdEl); }
    });

    activeAlbumNote = { overlay: overlay, td: tdEl };
}

function closeAlbumNoteInput() {
    if (!activeAlbumNote) return;
    activeAlbumNote.overlay.remove();
    activeAlbumNote = null;
}

function submitAlbumNote(albumId, noteText, tdEl) {
    var formData = new FormData();
    formData.append('value', noteText);
    fetch('/edit/album/' + albumId + '/note', { method: 'POST', headers: _csrfHeaders({}), body: formData })
        .then(function (r) { return r.text(); })
        .then(function (text) {
            var note = text.trim();
            if (note) {
                tdEl.classList.add('has-album-note');
                tdEl.setAttribute('data-album-note', note);
            } else {
                tdEl.classList.remove('has-album-note');
                tdEl.removeAttribute('data-album-note');
            }
            closeAlbumNoteInput();
        });
}

// Right-click on album header cell opens note editor (edit mode only)
document.addEventListener('contextmenu', function (e) {
    var td = e.target.closest('td.album-name-cell');
    if (!td) return;
    if (!window._canEdit) return;
    showAlbumNoteInput(e, td);
});

// 'n' key on hovered album header cell opens note editor (edit mode only)
var _hoveredAlbumCell = null;
document.addEventListener('mouseover', function (e) {
    var td = e.target.closest('td.album-name-cell');
    _hoveredAlbumCell = td || null;
});
document.addEventListener('keydown', function (e) {
    if (e.key !== 'n' || !_hoveredAlbumCell || activeAlbumNote) return;
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
    if (!window._canEdit) return;
    e.preventDefault();
    showAlbumNoteInput(e, _hoveredAlbumCell);
});

// Close album note overlay on outside click
document.addEventListener('mousedown', function (e) {
    if (activeAlbumNote && !activeAlbumNote.overlay.contains(e.target) && !activeAlbumNote.td.contains(e.target)) {
        closeAlbumNoteInput();
    }
});



function importAlbumFromSpotify(artistId) {
    _importFromSpotify(artistId, '/edit/spotify-album', 'spotify-album-url', 'spotify-album-import-btn');
}

function importPlaylistFromSpotify(artistId) {
    _importFromSpotify(artistId, '/edit/spotify-playlist', 'spotify-playlist-url', 'spotify-playlist-import-btn');
}

function _importFromSpotify(artistId, endpoint, inputId, btnId) {
    var urlInput = document.getElementById(inputId);
    var btn = document.getElementById(btnId);
    if (!urlInput || !urlInput.value.trim()) return;
    var btnLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Loading...';
    var headers = {};
    if (window._canEdit) headers['X-Edit-Source'] = 'editor';
    fetch(endpoint + '?url=' + encodeURIComponent(urlInput.value.trim()), { headers: headers })
        .then(function (r) {
            if (!r.ok) return r.json().then(function (d) { throw new Error(d.error || 'Import failed'); });
            return r.json();
        })
        .then(function (data) {
            if (data.artists) _allArtists = data.artists;
            _newAlbumSpotifyUrl = data.spotify_url || null;
            var nameEl = document.getElementById('new-album-name');
            if (nameEl) nameEl.value = data.name;
            var dateEl = document.getElementById('new-album-date');
            if (dateEl) { dateEl.value = data.release_date; dateEl.dispatchEvent(new Event('input', {bubbles: true})); }
            var typeEl = document.getElementById('new-album-type');
            if (typeEl) typeEl.value = String(data.album_type_id);
            // Clear existing songs and add imported tracks
            _newAlbumSongCount = 0;
            var songsContainer = document.getElementById('new-album-songs');
            if (songsContainer) songsContainer.innerHTML = '';
            data.tracks.forEach(function (track) {
                addNewAlbumSong(artistId);
                var songDiv = document.getElementById('new-song-' + _newAlbumSongCount);
                if (songDiv) {
                    var nameInput = songDiv.querySelector('.new-album-song-name');
                    if (nameInput) nameInput.value = track.name;
                    if (track.spotify_url) songDiv.dataset.spotifyUrl = track.spotify_url;
                }
            });
            validateAddAlbum();
        })
        .catch(function (e) { showToast(localizeCooldown(e.message || 'Spotify import failed')); })
        .finally(function () { btn.disabled = false; btn.textContent = btnLabel; });
}


/* ─── Auto-populate Spotify links ─── */

function autoPopulateSpotify(artistId, spotifyUrl) {
    var modal = document.getElementById('auto-spotify-modal');
    if (!modal) return;
    // Reset UI
    document.getElementById('auto-spotify-input-phase').style.display = '';
    document.getElementById('auto-spotify-progress-phase').style.display = 'none';
    document.getElementById('auto-spotify-review-phase').style.display = 'none';
    document.getElementById('auto-spotify-url').value = spotifyUrl || '';
    var startBtn = document.getElementById('auto-spotify-start-btn');
    if (startBtn) { startBtn.disabled = false; startBtn.textContent = 'Start'; }
    modal.style.display = 'flex';
    modal.dataset.artistId = artistId;
}

function autoSpotifyStart() {
    var modal = document.getElementById('auto-spotify-modal');
    var artistId = modal.dataset.artistId;
    var spotifyUrl = document.getElementById('auto-spotify-url').value.trim();
    var startBtn = document.getElementById('auto-spotify-start-btn');

    startBtn.disabled = true;
    startBtn.textContent = 'Starting...';

    // Show progress phase
    document.getElementById('auto-spotify-input-phase').style.display = 'none';
    document.getElementById('auto-spotify-progress-phase').style.display = '';
    document.getElementById('auto-spotify-progress-msg').textContent = 'Starting...';
    document.getElementById('auto-spotify-progress-bar').style.width = '0%';
    document.getElementById('auto-spotify-progress-bar').style.background = 'var(--link)';
    document.getElementById('auto-spotify-progress-pct').textContent = '0%';

    var form = new FormData();
    if (spotifyUrl) form.append('spotify_url', spotifyUrl);
    form.append('csrf_token', document.querySelector('meta[name="csrf-token"]').content);

    fetch('/edit/artist/' + artistId + '/auto-spotify', {method: 'POST', headers: _csrfHeaders(), body: form})
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.error) throw new Error(data.error);
            _pollAutoSpotify(data.job_id);
        })
        .catch(function (e) {
            document.getElementById('auto-spotify-progress-msg').textContent = localizeCooldown(e.message || 'Failed to start');
            document.getElementById('auto-spotify-progress-bar').style.width = '100%';
            document.getElementById('auto-spotify-progress-bar').style.background = 'var(--delete-button)';
            document.getElementById('auto-spotify-progress-pct').textContent = '';
            startBtn.disabled = false;
            startBtn.textContent = 'Start';
        });
}

function _pollAutoSpotify(jobId) {
    fetch('/edit/auto-spotify/progress?job_id=' + jobId)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.done) {
                _showAutoSpotifyResults(data.data);
            } else if (data.error) {
                document.getElementById('auto-spotify-progress-msg').textContent = localizeCooldown(data.error);
                document.getElementById('auto-spotify-progress-bar').style.width = '100%';
                document.getElementById('auto-spotify-progress-bar').style.background = 'var(--delete-button)';
                document.getElementById('auto-spotify-progress-pct').textContent = '';
            } else {
                document.getElementById('auto-spotify-progress-msg').textContent = data.progress || '';
                document.getElementById('auto-spotify-progress-bar').style.width = (data.percent || 0) + '%';
                document.getElementById('auto-spotify-progress-pct').textContent = (data.percent || 0) + '%';
                setTimeout(function () { _pollAutoSpotify(jobId); }, 500);
            }
        })
        .catch(function () {
            document.getElementById('auto-spotify-progress-msg').textContent = 'Lost connection. Please try again.';
            document.getElementById('auto-spotify-progress-bar').style.background = 'var(--delete-button)';
        });
}

function _showAutoSpotifyResults(data) {
    // Hide progress, show review phase
    document.getElementById('auto-spotify-progress-phase').style.display = 'none';
    document.getElementById('auto-spotify-review-phase').style.display = 'flex';

    var matchedByLink = data.matched_by_link || [];
    var needsReview = data.needs_review || [];
    var notFound = data.not_found || [];
    var artistLink = data.artist_link || null;
    var albumMatches = data.album_matches || [];

    // Artist & album links section (checkbox list, like songs)
    var entitySection = document.getElementById('auto-spotify-entity-section');
    var entityList = document.getElementById('auto-spotify-entity-list');
    entityList.innerHTML = '';
    var entityItems = [];
    if (artistLink) entityItems.push({ type: 'artist', id: artistLink.artist_id, label: 'Artist: ' + artistLink.name, url: artistLink.spotify_url });
    albumMatches.forEach(function (al) {
        entityItems.push({ type: 'album', id: al.album_id, label: 'Album: ' + al.name, url: al.spotify_url });
    });
    entityItems.forEach(function (it) {
        var row = document.createElement('div');
        row.className = 'flex items-center gap-2 py-1';
        row.innerHTML = '<label class="flex items-center gap-2 text-sm cursor-pointer">' +
            '<input type="checkbox" checked class="auto-spotify-entity-check cursor-pointer" ' +
            'data-entity-type="' + it.type + '" data-entity-id="' + it.id + '" data-spotify-url="' + _escAttr(it.url) + '">' +
            '<span class="text-primary-text">' + _escHtml(it.label) + '</span></label>';
        entityList.appendChild(row);
    });
    entitySection.style.display = entityItems.length ? '' : 'none';

    // Summary
    var summary = document.getElementById('auto-spotify-summary');
    var parts = [];
    if (artistLink) parts.push('artist link');
    if (albumMatches.length) parts.push(albumMatches.length + ' album link' + (albumMatches.length !== 1 ? 's' : ''));
    if (matchedByLink.length) parts.push(matchedByLink.length + ' matched by link');
    if (needsReview.length) parts.push(needsReview.length + ' need review');
    if (notFound.length) parts.push(notFound.length + ' not found');
    summary.textContent = parts.length ? parts.join(', ') : 'Nothing to update.';

    // Helper to build a checkbox list
    function _buildCheckList(container, items) {
        container.innerHTML = '';
        items.forEach(function (m) {
            var row = document.createElement('div');
            row.className = 'flex items-center gap-2 py-1';
            row.innerHTML = '<label class="flex items-center gap-2 text-sm cursor-pointer">' +
                '<input type="checkbox" checked data-song-id="' + m.song_id + '" data-spotify-url="' + _escAttr(m.spotify_url) + '" class="auto-spotify-check cursor-pointer">' +
                '<span class="text-primary-text">' + _escHtml(m.song_name) + '</span>' +
                (m.artists ? ' <span class="text-secondary-text">(' + _escHtml(m.artists) + ')</span>' : '') +
                '</label>';
            container.appendChild(row);
        });
    }

    // Build matched-by-link list
    _buildCheckList(document.getElementById('auto-spotify-link-list'), matchedByLink);


    // Build review list (each song shows up to 5 radio options)
    var reviewList = document.getElementById('auto-spotify-review-list');
    reviewList.innerHTML = '';
    needsReview.forEach(function (item) {
        var block = document.createElement('div');
        block.className = 'mb-3 pb-3';
        block.style.borderBottom = '1px solid var(--border)';

        var title = document.createElement('div');
        title.className = 'text-sm font-semibold text-primary-text mb-1';
        title.textContent = item.song_name;
        block.appendChild(title);

        var groupName = 'review-' + item.song_id;
        item.candidates.forEach(function (c, idx) {
            var label = document.createElement('label');
            label.className = 'flex items-start gap-2 py-0.5 text-sm cursor-pointer';
            label.innerHTML = '<input type="radio" name="' + groupName + '" ' +
                'data-song-id="' + item.song_id + '" data-spotify-url="' + _escAttr(c.spotify_url) + '" ' +
                'class="auto-spotify-review-radio mt-0.5 cursor-pointer"' + '>' +
                '<span><span class="text-primary-text">' + _escHtml(c.name) + '</span>' +
                '<span class="text-secondary-text"> — ' + _escHtml(c.artists) + '</span>' +
                '<span class="text-secondary-text text-xs block">' + _escHtml(c.album) + '</span></span>';
            block.appendChild(label);
        });

        // "None" option
        var noneLabel = document.createElement('label');
        noneLabel.className = 'flex items-center gap-2 py-0.5 text-sm cursor-pointer';
        noneLabel.innerHTML = '<input type="radio" name="' + groupName + '" ' +
            'data-song-id="' + item.song_id + '" data-spotify-url="" ' +
            'class="auto-spotify-review-radio cursor-pointer" checked>' +
            '<span class="text-secondary-text italic">None of these</span>';
        block.appendChild(noneLabel);

        reviewList.appendChild(block);
    });

    // Not found list
    var notFoundList = document.getElementById('auto-spotify-notfound-list');
    notFoundList.innerHTML = '';
    if (notFound.length) {
        var header = document.createElement('div');
        header.className = 'text-xs text-secondary-text mb-1 mt-2';
        header.textContent = 'Not found on Spotify (' + notFound.length + '):';
        notFoundList.appendChild(header);
        notFound.forEach(function (nf) {
            var row = document.createElement('div');
            row.className = 'text-xs text-secondary-text py-0.5';
            row.textContent = nf.song_name;
            notFoundList.appendChild(row);
        });
    }

    // Show/hide sections
    document.getElementById('auto-spotify-link-section').style.display = matchedByLink.length ? '' : 'none';
    document.getElementById('auto-spotify-review-section').style.display = needsReview.length ? '' : 'none';

    // "Check first option on all" toggle — only relevant when there are review groups
    var selectFirstWrap = document.getElementById('auto-spotify-select-first-wrap');
    var selectFirst = document.getElementById('auto-spotify-select-first');
    if (selectFirst) selectFirst.checked = false;
    if (selectFirstWrap) selectFirstWrap.style.display = needsReview.length ? '' : 'none';
}

/* Master toggle: pick the first candidate radio for every needs-review song,
   or revert each group to "None of these" when unchecked. */
function autoSpotifySelectFirstAll(checkbox) {
    var blocks = document.getElementById('auto-spotify-review-list').children;
    for (var i = 0; i < blocks.length; i++) {
        var radios = blocks[i].querySelectorAll('.auto-spotify-review-radio');
        if (!radios.length) continue;
        // First radio = top candidate; last radio = the "None of these" option.
        var target = checkbox.checked ? radios[0] : radios[radios.length - 1];
        target.checked = true;
    }
}

function autoSpotifyConfirm() {
    var selections = [];

    // Collect checked auto-matched
    document.querySelectorAll('.auto-spotify-check:checked').forEach(function (cb) {
        if (cb.dataset.spotifyUrl) {
            selections.push({song_id: parseInt(cb.dataset.songId), spotify_url: cb.dataset.spotifyUrl});
        }
    });

    // Collect selected review radio buttons
    var reviewRadios = document.querySelectorAll('.auto-spotify-review-radio:checked');
    reviewRadios.forEach(function (radio) {
        if (radio.dataset.spotifyUrl) {
            selections.push({song_id: parseInt(radio.dataset.songId), spotify_url: radio.dataset.spotifyUrl});
        }
    });

    // Collect checked artist + album link entries
    var artistLink = null;
    var albumSelections = [];
    document.querySelectorAll('.auto-spotify-entity-check:checked').forEach(function (cb) {
        if (!cb.dataset.spotifyUrl) return;
        if (cb.dataset.entityType === 'artist') {
            artistLink = {artist_id: parseInt(cb.dataset.entityId), spotify_url: cb.dataset.spotifyUrl};
        } else {
            albumSelections.push({album_id: parseInt(cb.dataset.entityId), spotify_url: cb.dataset.spotifyUrl});
        }
    });

    var asModal = document.getElementById('auto-spotify-modal');
    if (!selections.length && !artistLink && !albumSelections.length) {
        asModal.style.display = 'none';
        return;
    }

    var btn = document.getElementById('auto-spotify-confirm-btn');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    fetch('/edit/auto-spotify/confirm', {
        method: 'POST',
        headers: _csrfHeaders({'Content-Type': 'application/json'}),
        body: JSON.stringify({
            selections: selections,
            artist_link: artistLink,
            album_selections: albumSelections,
        }),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        document.getElementById('auto-spotify-modal').style.display = 'none';
        btn.disabled = false;
        btn.textContent = 'Confirm & Save';
        window.location.reload();
    })
    .catch(function () {
        btn.disabled = false;
        btn.textContent = 'Confirm & Save';
        alert('Failed to save. Please try again.');
    });
}

function _escHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function _escAttr(s) {
    return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// --- Bulk genre management (artist page edit mode) ---
var _bulkGenreScope = { artistId: null, artistName: '' };

function showBulkGenreModal(artistId, artistName) {
    _bulkGenreScope.artistId = artistId;
    _bulkGenreScope.artistName = artistName;

    document.getElementById('bulk-genre-artist-name').textContent = artistName;
    document.getElementById('bulk-genre-album-count').textContent = _bulkGenreAlbumCount(artistId);

    var container = document.getElementById('bulk-genre-checkboxes');
    container.innerHTML = (_allGenres || []).map(function(g) {
        return '<label class="text-sm" style="cursor:pointer;">' +
               '<input type="checkbox" data-bulk-genre="' + g.id + '" style="margin-right:3px;"> ' +
               g.name.replace(/</g, '&lt;') + '</label>';
    }).join('');

    document.getElementById('bulk-genre-modal').style.display = 'flex';
}

function _bulkGenreSelectedIds() {
    var ids = [];
    document.querySelectorAll('#bulk-genre-checkboxes input[data-bulk-genre]:checked').forEach(function(cb) {
        ids.push(parseInt(cb.dataset.bulkGenre));
    });
    return ids;
}

function _bulkGenreAlbumIdsForArtist(artistId) {
    var ids = [];
    var mainArtistEl = document.querySelector('[data-current-artist-id]');
    var mainArtistId = mainArtistEl ? parseInt(mainArtistEl.getAttribute('data-current-artist-id')) : 0;
    document.querySelectorAll('tr[id^="album-"]').forEach(function(row) {
        var childArtistId = null;
        row.classList.forEach(function(cls) {
            if (cls.indexOf('child-row-') === 0) {
                childArtistId = parseInt(cls.replace('child-row-', ''));
            }
        });
        var rowArtistId = childArtistId !== null ? childArtistId : mainArtistId;
        if (rowArtistId === artistId) {
            ids.push(parseInt(row.id.replace('album-', '')));
        }
    });
    return ids;
}

function _bulkGenreAlbumCount(artistId) {
    return _bulkGenreAlbumIdsForArtist(artistId).length;
}

function _bulkGenrePost(action, genreIds) {
    var body = 'action=' + encodeURIComponent(action);
    if (genreIds && genreIds.length) body += '&genre_ids=' + encodeURIComponent(genreIds.join(','));
    fetch('/edit/artist/' + _bulkGenreScope.artistId + '/bulk-genres', {
        method: 'POST',
        headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
        body: body,
    }).then(function(r) {
        if (!r.ok) throw new Error('save failed');
        return r.json();
    }).then(function(data) {
        _bulkGenreUpdateSpans(data.affected || []);
        if (!data.affected || !data.affected.length) {
            showToast('No changes to apply');
        } else {
            showToast('Updated genres on ' + data.affected.length + ' album(s)');
        }
    }).catch(function() {
        showToast('Failed to update genres — try again');
    });
}

function _bulkGenreUpdateSpans(affected) {
    affected.forEach(function(entry) {
        var span = document.querySelector(
            '.genre-edit[data-album-id="' + entry.album_id + '"]'
        );
        if (!span) return;
        span.textContent = entry.genre_names.length ? entry.genre_names.join(', ') : 'genres';
        span.setAttribute('data-genre-ids', JSON.stringify(entry.genre_ids));
        span.style.color = entry.genre_names.length ? '' : 'var(--text-secondary)';
    });
}

function bulkGenreApply() {
    var ids = _bulkGenreSelectedIds();
    if (!ids.length) return;
    var count = _bulkGenreAlbumCount(_bulkGenreScope.artistId);
    showConfirm(
        'Apply genres?',
        'Apply ' + ids.length + ' genre(s) to ' + count + ' album(s) by ' + _bulkGenreScope.artistName + '?',
        function() { _bulkGenrePost('apply', ids); },
        'Apply'
    );
}

function bulkGenreRemove() {
    var ids = _bulkGenreSelectedIds();
    if (!ids.length) return;
    var count = _bulkGenreAlbumCount(_bulkGenreScope.artistId);
    showConfirm(
        'Remove genres?',
        'Remove ' + ids.length + ' genre(s) from ' + count + ' album(s) by ' + _bulkGenreScope.artistName + '?',
        function() { _bulkGenrePost('remove', ids); },
        'Remove'
    );
}

function bulkGenreClear() {
    var count = _bulkGenreAlbumCount(_bulkGenreScope.artistId);
    showConfirm(
        'Clear all genres?',
        'Clear every genre from ' + count + ' album(s) by ' + _bulkGenreScope.artistName + '? This cannot be undone.',
        function() { _bulkGenrePost('clear', []); },
        'Clear'
    );
}

/* ====================================================================
   Shared misc-modal helpers + "combine misc artist into real artist"
   flow. Lives here (loaded on every page) so both the Misc page and the
   Views page can launch the combine modal. Pages that call
   _showCombineMiscArtist must define _allCountries and _allAlbumTypes.
   ==================================================================== */

/* ---------- shared modal helpers ---------- */
function _miscBackdrop(onClose) {
    var bd = document.createElement('div');
    bd.style.cssText = 'position:fixed;inset:0;z-index:200;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;padding:16px;';
    bd.onclick = function(e) { if (e.target === bd) { bd.remove(); if (onClose) onClose(); } };
    bd.addEventListener('keydown', function(e) { if (e.key === 'Escape') { bd.remove(); if (onClose) onClose(); } });
    document.body.appendChild(bd);
    return bd;
}
function _miscModal(width) {
    var m = document.createElement('div');
    m.style.cssText = 'background:var(--bg-secondary,#fff);border:1px solid var(--border,#ccc);border-radius:8px;padding:16px;width:100%;box-shadow:0 4px 16px rgba(0,0,0,0.3);max-height:80vh;overflow-y:auto;max-width:' + (width || 420) + 'px;';
    return m;
}
function _miscInput(placeholder, val) {
    var inp = document.createElement('input');
    inp.type = 'text'; inp.placeholder = placeholder || ''; inp.value = val || '';
    inp.style.cssText = 'width:100%;padding:6px 8px;font-size:13px;border:1px solid var(--border,#ccc);border-radius:4px;background:var(--bg-primary,#fff);color:var(--text-primary);box-sizing:border-box;';
    return inp;
}
function _miscBtn(label, bg, onClick) {
    var b = document.createElement('button');
    b.textContent = label;
    b.style.cssText = 'padding:6px 14px;font-size:12px;border:none;border-radius:4px;cursor:pointer;color:#fff;background:' + (bg || 'var(--link,#2563EB)') + ';';
    b.onclick = onClick;
    return b;
}
function _miscLabel(text) {
    var l = document.createElement('div');
    l.textContent = text;
    l.style.cssText = 'font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:4px;margin-top:10px;';
    return l;
}
function _miscSelect(options, selected) {
    var sel = document.createElement('select');
    sel.style.cssText = 'width:100%;padding:6px 8px;font-size:13px;border:1px solid var(--border,#ccc);border-radius:4px;background:var(--bg-primary,#fff);color:var(--text-primary);';
    options.forEach(function(o) {
        var opt = document.createElement('option');
        opt.value = o.id; opt.textContent = o.name;
        if (selected !== undefined && o.id == selected) opt.selected = true;
        sel.appendChild(opt);
    });
    return sel;
}
function _csrfJson() {
    // _csrfHeaders also adds X-Edit-Source for editors, which mutating /misc and
    // /edit endpoints require.
    return _csrfHeaders({'Content-Type': 'application/json'});
}

/* ---------- autocomplete helper ---------- */
function _miscAutocomplete(input, url, onSelect, minLen) {
    var list = document.createElement('div');
    list.style.cssText = 'position:absolute;left:0;right:0;top:100%;background:var(--bg-secondary,#fff);border:1px solid var(--border,#ccc);border-radius:0 0 4px 4px;max-height:160px;overflow-y:auto;z-index:10;display:none;';
    input.parentNode.style.position = 'relative';
    input.parentNode.appendChild(list);
    var timer = null;
    input.addEventListener('input', function() {
        clearTimeout(timer);
        var q = input.value.trim();
        if (q.length < (minLen || 1)) { list.style.display = 'none'; return; }
        timer = setTimeout(function() {
            fetch(url + '?q=' + encodeURIComponent(q)).then(function(r){return r.json();}).then(function(items) {
                list.innerHTML = '';
                if (!items.length) { list.style.display = 'none'; return; }
                items.forEach(function(item) {
                    var d = document.createElement('div');
                    d.textContent = item.name;
                    d.style.cssText = 'padding:5px 8px;font-size:12px;cursor:pointer;color:var(--text-primary);';
                    d.onmouseenter = function() { d.style.background = 'var(--row-alternate,#f3f4f6)'; };
                    d.onmouseleave = function() { d.style.background = ''; };
                    d.onclick = function() { onSelect(item); input.value = ''; list.style.display = 'none'; };
                    list.appendChild(d);
                });
                list.style.display = 'block';
            });
        }, 200);
    });
    document.addEventListener('click', function(e) {
        if (!input.contains(e.target) && !list.contains(e.target)) list.style.display = 'none';
    });
    return list;
}

/* ========== CONFIRM MISC->MISC MERGE (rich modal, shared with Views page) ========== */
function _showMergeConfirm(selectedIds, allArtists, onConfirm) {
    var keepId = selectedIds[0];
    var keepArtist = allArtists.find(function(a){return a.id === keepId;});
    var absorbArtists = selectedIds.slice(1).map(function(id) { return allArtists.find(function(a){return a.id === id;}); }).filter(Boolean);

    var overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;z-index:10001;';
    var panel = document.createElement('div');
    panel.style.cssText = 'background:var(--bg-primary);border:1px solid var(--border);border-radius:8px;padding:20px;max-width:500px;width:90%;max-height:80vh;overflow-y:auto;';

    var title = document.createElement('h3');
    title.textContent = 'Confirm Merge';
    title.style.cssText = 'margin:0 0 12px;font-size:16px;color:var(--text-primary);';
    panel.appendChild(title);

    var desc = document.createElement('p');
    desc.style.cssText = 'font-size:12px;color:var(--text-secondary);margin:0 0 12px;';
    desc.textContent = 'Songs from all selected artists will be merged into the first one ("' + keepArtist.name + '", ' + keepArtist.song_count + ' songs). The others will be deleted.';
    panel.appendChild(desc);

    // Result country for the kept artist — prefilled with its current country.
    var countryRow = document.createElement('div');
    countryRow.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:14px;';
    var countryLbl = document.createElement('span');
    countryLbl.textContent = 'Result country:';
    countryLbl.style.cssText = 'font-size:12px;color:var(--text-secondary);white-space:nowrap;';
    var countrySel = _miscSelect(_allCountries, keepArtist.country_id);
    countrySel.style.cssText += 'flex:1;';
    countryRow.appendChild(countryLbl);
    countryRow.appendChild(countrySel);
    panel.appendChild(countryRow);

    function _countryName(cid) {
        var c = _allCountries.find(function(x){return x.id === cid;});
        return c ? c.name : '';
    }

    var listDiv = document.createElement('div');
    listDiv.style.cssText = 'font-size:12px;';
    var loading = document.createElement('div');
    loading.textContent = 'Loading songs...';
    loading.style.cssText = 'color:var(--text-secondary);padding:8px 0;';
    listDiv.appendChild(loading);
    panel.appendChild(listDiv);

    fetch('/misc/artist-songs?ids=' + selectedIds.join(',')).then(function(r){return r.json();}).then(function(songMap) {
        listDiv.innerHTML = '';
        selectedIds.forEach(function(aid, idx) {
            var artist = allArtists.find(function(a){return a.id === aid;});
            if (!artist) return;
            var section = document.createElement('div');
            section.style.cssText = 'margin-bottom:12px;padding:8px 10px;border-radius:4px;border:1px solid var(--border);' + (idx === 0 ? 'background:rgba(34,197,94,0.08);border-color:rgba(34,197,94,0.3);' : 'background:rgba(239,68,68,0.06);border-color:rgba(239,68,68,0.2);');
            var header = document.createElement('div');
            header.style.cssText = 'font-weight:bold;margin-bottom:4px;display:flex;align-items:center;gap:6px;';
            var badge = document.createElement('span');
            badge.textContent = idx === 0 ? 'KEEP' : 'MERGE';
            badge.style.cssText = 'font-size:9px;padding:1px 5px;border-radius:3px;font-weight:bold;color:#fff;background:' + (idx === 0 ? '#22c55e' : '#ef4444') + ';';
            header.appendChild(badge);
            var nameSpan = document.createElement('span');
            nameSpan.textContent = artist.name;
            nameSpan.style.color = 'var(--text-primary)';
            header.appendChild(nameSpan);
            var countSpan = document.createElement('span');
            countSpan.textContent = '(' + artist.song_count + ' songs)';
            countSpan.style.cssText = 'color:var(--text-secondary);font-weight:normal;';
            header.appendChild(countSpan);
            var countryTag = document.createElement('span');
            countryTag.textContent = _countryName(artist.country_id);
            countryTag.style.cssText = 'font-size:10px;color:var(--text-secondary);font-weight:normal;margin-left:auto;border:1px solid var(--border);border-radius:3px;padding:1px 6px;';
            header.appendChild(countryTag);
            section.appendChild(header);
            var songs = songMap[String(aid)] || [];
            if (songs.length === 0) {
                var empty = document.createElement('div');
                empty.textContent = 'No songs';
                empty.style.cssText = 'color:var(--text-secondary);font-style:italic;padding-left:4px;';
                section.appendChild(empty);
            } else {
                songs.forEach(function(s) {
                    var songRow = document.createElement('div');
                    songRow.textContent = s.artists ? (s.name + ' — ' + s.artists) : s.name;
                    songRow.style.cssText = 'padding:1px 0 1px 4px;color:var(--text-secondary);';
                    section.appendChild(songRow);
                });
            }
            listDiv.appendChild(section);
        });
    });

    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;margin-top:14px;';
    var cancelBtn = _miscBtn('Cancel', '#6B7280', function() { overlay.remove(); });
    var confirmBtn = _miscBtn('Merge', '#7C3AED', function() { overlay.remove(); onConfirm(parseInt(countrySel.value)); });
    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(confirmBtn);
    panel.appendChild(btnRow);

    overlay.appendChild(panel);
    overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };
    document.body.appendChild(overlay);
}

/* ========== COMBINE MISC ARTIST INTO REAL ARTIST ========== */
function _showCombineMiscArtist(miscArtist, onDone) {
    var bd = _miscBackdrop(onDone);
    var modal = _miscModal(560);
    bd.appendChild(modal);

    var title = document.createElement('div');
    title.textContent = 'Combine "' + miscArtist.name + '" into a real artist';
    title.style.cssText = 'font-size:16px;font-weight:700;color:var(--text-primary);margin-bottom:6px;';
    modal.appendChild(title);

    var hint = document.createElement('div');
    hint.style.cssText = 'font-size:12px;color:var(--text-secondary);margin-bottom:12px;';
    hint.textContent = 'Pick the real artist, then merge each song into one of that artist’s songs. Songs you mark “not on artist page” stay on misc. The misc artist is removed once all its songs are merged.';
    modal.appendChild(hint);

    var raWrap = document.createElement('div');
    raWrap.appendChild(_miscLabel('Real artist'));
    var raInp = _miscInput('Search real artists...');
    raWrap.appendChild(raInp);
    modal.appendChild(raWrap);

    var songsWrap = document.createElement('div');
    songsWrap.style.cssText = 'margin-top:12px;max-height:46vh;overflow-y:auto;';
    modal.appendChild(songsWrap);

    var realArtist = null;   // {artist_id, name}
    var songs = [];          // [{id, name, state: 'pending'|'merged'|'skipped'}]
    var lastAutoMerged = 0;  // songs auto-merged because the real artist was already credited

    function renderSongs() {
        songsWrap.innerHTML = '';
        if (!realArtist) {
            var msg = document.createElement('div');
            msg.style.cssText = 'font-size:12px;color:var(--text-secondary);font-style:italic;';
            msg.textContent = 'Select a real artist to begin.';
            songsWrap.appendChild(msg);
            return;
        }
        if (lastAutoMerged > 0) {
            var note = document.createElement('div');
            note.style.cssText = 'font-size:11px;color:#0D9488;margin-bottom:6px;';
            note.textContent = '✓ Auto-merged ' + lastAutoMerged + ' song' + (lastAutoMerged === 1 ? '' : 's') + ' already credited to ' + realArtist.name + '.';
            songsWrap.appendChild(note);
        }
        var pending = songs.filter(function(s){ return s.state === 'pending'; }).length;
        var hdr = document.createElement('div');
        hdr.style.cssText = 'font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;';
        hdr.textContent = 'Songs (' + pending + ' remaining)';
        songsWrap.appendChild(hdr);

        songs.forEach(function(s) {
            var row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:5px 4px;border-bottom:1px solid var(--border,#eee);font-size:12px;';
            var nmeta = document.createElement('div');
            nmeta.style.cssText = 'flex:1;min-width:0;';
            var nm = document.createElement('div');
            nm.textContent = s.name;
            nm.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-primary);';
            nmeta.appendChild(nm);
            if (s.artists) {
                var art = document.createElement('div');
                art.textContent = s.artists;
                art.style.cssText = 'font-size:10px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
                nmeta.appendChild(art);
            }
            row.appendChild(nmeta);

            if (s.state === 'merged' || s.state === 'swapped') {
                nm.style.textDecoration = 'line-through';
                nm.style.color = 'var(--text-secondary)';
                var done = document.createElement('span');
                done.textContent = s.state === 'swapped' ? '✓ credit swapped' : '✓ merged';
                done.style.cssText = 'color:#0D9488;white-space:nowrap;';
                row.appendChild(done);
            } else if (s.state === 'skipped') {
                nm.style.color = 'var(--text-secondary)';
                var sk = document.createElement('span');
                sk.textContent = 'not on artist page';
                sk.style.cssText = 'color:var(--text-secondary);font-style:italic;white-space:nowrap;';
                row.appendChild(sk);
                var undo = _miscBtn('Undo', '#6B7280', function() { s.state = 'pending'; renderSongs(); });
                undo.style.cssText += 'font-size:10px;padding:2px 6px;';
                row.appendChild(undo);
            } else {
                var mergeInto = _miscBtn('Merge into…', '#0D9488', function() { _pickTarget(s); });
                mergeInto.style.cssText += 'font-size:11px;padding:3px 8px;';
                row.appendChild(mergeInto);
                var swap = _miscBtn('Swap credit', '#2563EB', function() { _swapCredit(s); });
                swap.style.cssText += 'font-size:11px;padding:3px 8px;';
                row.appendChild(swap);
                var skip = _miscBtn('Not on artist page', '#6B7280', function() { s.state = 'skipped'; renderSongs(); });
                skip.style.cssText += 'font-size:11px;padding:3px 8px;';
                row.appendChild(skip);
            }
            songsWrap.appendChild(row);
        });
    }

    function _pickTarget(songObj) {
        var pbd = _miscBackdrop();
        var pmodal = _miscModal(420);
        pbd.appendChild(pmodal);
        var ptitle = document.createElement('div');
        ptitle.textContent = 'Merge "' + songObj.name + '" into…';
        ptitle.style.cssText = 'font-size:14px;font-weight:700;color:var(--text-primary);margin-bottom:8px;';
        pmodal.appendChild(ptitle);
        var tInp = _miscInput('Search ' + realArtist.name + '’s songs...');
        pmodal.appendChild(tInp);
        var tList = document.createElement('div');
        tList.style.cssText = 'margin-top:8px;max-height:300px;overflow-y:auto;';
        pmodal.appendChild(tList);

        var timer = null;
        tInp.addEventListener('input', function() {
            clearTimeout(timer);
            var q = tInp.value.trim();
            if (q.length < 2) { tList.innerHTML = ''; return; }
            timer = setTimeout(function() {
                fetch('/misc/combine-targets?artist_id=' + realArtist.artist_id + '&q=' + encodeURIComponent(q))
                    .then(function(r){ return r.json(); })
                    .then(function(items) {
                        tList.innerHTML = '';
                        if (!items.length) {
                            var none = document.createElement('div');
                            none.style.cssText = 'font-size:12px;color:var(--text-secondary);padding:4px;';
                            none.textContent = 'No matching songs for this artist';
                            tList.appendChild(none);
                            return;
                        }
                        items.forEach(function(it) {
                            var d = document.createElement('div');
                            d.style.cssText = 'padding:6px 8px;cursor:pointer;color:var(--text-primary);border-radius:3px;';
                            var nmspan = document.createElement('div');
                            nmspan.textContent = it.name + (it.album ? ' (' + it.album + ')' : '');
                            nmspan.style.cssText = 'font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
                            d.appendChild(nmspan);
                            if (it.artists) {
                                var sub = document.createElement('div');
                                sub.textContent = it.artists;
                                sub.style.cssText = 'font-size:10px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
                                d.appendChild(sub);
                            }
                            d.onmouseenter = function(){ d.style.background = 'var(--row-alternate,#f3f4f6)'; };
                            d.onmouseleave = function(){ d.style.background = ''; };
                            d.onclick = function() { pbd.remove(); _openMergeForCombine(songObj, it); };
                            tList.appendChild(d);
                        });
                    });
            }, 200);
        });
        // Prefill with the misc song's name and run the search — usually the matching song shares its name.
        tInp.value = songObj.name;
        setTimeout(function(){ tInp.focus(); tInp.select(); tInp.dispatchEvent(new Event('input')); }, 0);
    }

    function _openMergeForCombine(songObj, targetItem) {
        showMergeDiffModal(targetItem.id, targetItem.name, songObj.id, songObj.name, miscArtist.name, '', {
            noPassword: true,
            confirmLabel: 'Merge',
            zIndex: 300,
            submitUrl: '/misc/combine-song',
            extraPayload: {
                misc_artist_id: miscArtist.id,
                real_artist_id: realArtist.artist_id,
                song_id: songObj.id,
                target_song_id: targetItem.id
            },
            onSuccess: function(resp) {
                songObj.state = 'merged';
                if (resp && resp.deleted) {
                    bd.remove();
                    if (onDone) onDone();
                    if (typeof showToast === 'function') showToast('Combined "' + miscArtist.name + '" into ' + realArtist.name);
                } else {
                    renderSongs();
                }
            }
        });
    }

    function _swapCredit(songObj) {
        if (songObj.has_album) { _doSwap(songObj, null); }
        else { _pickAlbumThenSwap(songObj); }
    }

    function _doSwap(songObj, albumPayload) {
        var body = {misc_artist_id: miscArtist.id, real_artist_id: realArtist.artist_id, song_id: songObj.id};
        if (albumPayload) body.album = albumPayload;
        fetch('/misc/swap-credit', {method: 'POST', headers: _csrfJson(), body: JSON.stringify(body)})
            .then(function(r){ return r.json(); })
            .then(function(res) {
                if (res.error) { alert(res.error === 'album_required' ? 'This song needs an album.' : res.error); return; }
                songObj.state = 'swapped';
                if (res.deleted) {
                    bd.remove();
                    if (onDone) onDone();
                    if (typeof showToast === 'function') showToast('Combined "' + miscArtist.name + '" into ' + realArtist.name);
                } else {
                    renderSongs();
                }
            });
    }

    function _pickAlbumThenSwap(songObj) {
        var abd = _miscBackdrop();
        var amodal = _miscModal(420);
        abd.appendChild(amodal);
        var t = document.createElement('div');
        t.textContent = 'Album for "' + songObj.name + '"';
        t.style.cssText = 'font-size:14px;font-weight:700;color:var(--text-primary);margin-bottom:4px;';
        amodal.appendChild(t);
        var sub = document.createElement('div');
        sub.textContent = 'This song has no album. Pick or create one on ' + realArtist.name + '.';
        sub.style.cssText = 'font-size:11px;color:var(--text-secondary);margin-bottom:10px;';
        amodal.appendChild(sub);

        var albumSel = document.createElement('select');
        albumSel.style.cssText = 'width:100%;padding:6px 8px;font-size:13px;border:1px solid var(--border);border-radius:4px;background:var(--bg-primary);color:var(--text-primary);';
        var optNew = document.createElement('option');
        optNew.value = '__new'; optNew.textContent = '+ Create new album';
        albumSel.appendChild(optNew);
        amodal.appendChild(albumSel);

        var newDiv = document.createElement('div');
        newDiv.style.cssText = 'margin-top:6px;';
        var newName = _miscInput('Album name');
        newDiv.appendChild(newName);
        var newDate = document.createElement('input');
        newDate.type = 'date';
        newDate.style.cssText = 'width:100%;padding:6px 8px;font-size:13px;border:1px solid var(--border);border-radius:4px;background:var(--bg-primary);color:var(--text-primary);box-sizing:border-box;margin-top:4px;';
        newDiv.appendChild(newDate);
        var newType = _miscSelect(_allAlbumTypes, 2);
        newType.style.marginTop = '4px';
        newDiv.appendChild(newType);
        amodal.appendChild(newDiv);
        function syncNew(){ newDiv.style.display = albumSel.value === '__new' ? 'block' : 'none'; }
        albumSel.onchange = syncNew;

        fetch('/misc/search-artist-albums?artist_id=' + realArtist.artist_id).then(function(r){ return r.json(); }).then(function(albums) {
            albums.forEach(function(a) {
                var o = document.createElement('option');
                o.value = a.id;
                o.textContent = a.name + (a.release_date ? ' (' + a.release_date.slice(0,4) + ')' : '');
                albumSel.insertBefore(o, optNew);
            });
            if (albums.length) albumSel.value = String(albums[0].id);
            syncNew();
        });

        var brow = document.createElement('div');
        brow.style.cssText = 'display:flex;gap:8px;margin-top:14px;justify-content:flex-end;';
        brow.appendChild(_miscBtn('Cancel', '#6B7280', function(){ abd.remove(); }));
        brow.appendChild(_miscBtn('Swap credit', '#2563EB', function() {
            var payload;
            if (albumSel.value === '__new') {
                var an = newName.value.trim();
                if (!an) { alert('Enter album name'); return; }
                payload = {name: an, release_date: newDate.value || null, album_type_id: parseInt(newType.value)};
            } else if (albumSel.value) {
                payload = {existing_id: parseInt(albumSel.value)};
            } else { alert('Pick an album'); return; }
            abd.remove();
            _doSwap(songObj, payload);
        }));
        amodal.appendChild(brow);
        syncNew();
    }

    _miscAutocomplete(raInp, '/misc/search-real-artists', function(item) {
        realArtist = item;
        raInp.value = item.name;
        _autoMergeThenLoad();
    });
    // Prefill with the misc artist's name and run the search — the real artist usually shares its name.
    raInp.value = miscArtist.name;
    raInp.dispatchEvent(new Event('input'));

    function _loadSongs() {
        fetch('/misc/artist-songs?ids=' + miscArtist.id).then(function(r){ return r.json(); }).then(function(data) {
            var list = data[String(miscArtist.id)] || [];
            songs = list.map(function(s){ return {id: s.id, name: s.name, artists: s.artists || '', has_album: !!s.has_album, state: 'pending'}; });
            renderSongs();
        });
    }

    function _autoMergeThenLoad() {
        lastAutoMerged = 0;
        songsWrap.innerHTML = '<div style="font-size:12px;color:var(--text-secondary);">Loading…</div>';
        // Songs the real artist is already credited on aren't merged — just drop the redundant misc credit.
        fetch('/misc/combine-auto-merge', {
            method: 'POST', headers: _csrfJson(),
            body: JSON.stringify({misc_artist_id: miscArtist.id, real_artist_id: realArtist.artist_id})
        }).then(function(r){ return r.json(); }).then(function(res) {
            if (res.deleted) {
                bd.remove();
                if (onDone) onDone();
                if (typeof showToast === 'function') showToast('Combined "' + miscArtist.name + '" into ' + realArtist.name);
                return;
            }
            lastAutoMerged = res.auto_merged || 0;
            _loadSongs();
        });
    }

    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex;gap:8px;margin-top:14px;justify-content:flex-end;';
    btnRow.appendChild(_miscBtn('Close', '#6B7280', function() { bd.remove(); if (onDone) onDone(); }));
    modal.appendChild(btnRow);

    renderSongs();
}
