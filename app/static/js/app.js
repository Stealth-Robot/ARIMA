/* Zoom-aware bounding rect — corrects for non-standard CSS zoom on html element */
function getZoomedRect(el) {
    var rect = el.getBoundingClientRect();
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    return {
        top: rect.top / zoom,
        bottom: rect.bottom / zoom,
        left: rect.left / zoom,
        right: rect.right / zoom,
        width: rect.width / zoom,
        height: rect.height / zoom,
    };
}

/* CSRF — inject X-CSRFToken header on every HTMX request */

document.body.addEventListener('htmx:configRequest', function (e) {
    var token = document.querySelector('meta[name="csrf-token"]');
    if (token) {
        e.detail.headers['X-CSRFToken'] = token.content;
    }
});

/* Hover background — reads hex from --hover-bg CSS variable and applies 0.2 opacity */
function _hoverBg() {
    var hex = getComputedStyle(document.documentElement).getPropertyValue('--hover-bg').trim();
    if (!hex || hex.length < 7) return 'rgba(128,128,128,0.2)';
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',0.2)';
}

/* Search section collapse — persists across searches within the session */
function _getSearchCollapsed() {
    try { return JSON.parse(sessionStorage.getItem('search-collapse')) || {}; } catch(e) { return {}; }
}
function _applySearchCollapse() {
    var state = _getSearchCollapsed();
    document.querySelectorAll('.search-section-body').forEach(function(body) {
        var section = body.dataset.section;
        var arrow = document.querySelector('.search-section-arrow[data-section="' + section + '"]');
        if (state[section]) {
            body.style.display = 'none';
            if (arrow) arrow.style.transform = 'rotate(-90deg)';
        }
    });
}
document.addEventListener('click', function(e) {
    var header = e.target.closest('.search-section-header');
    if (!header) return;
    var section = header.dataset.section;
    var body = document.querySelector('.search-section-body[data-section="' + section + '"]');
    var arrow = header.querySelector('.search-section-arrow');
    if (!body) return;
    var state = _getSearchCollapsed();
    if (body.style.display === 'none') {
        body.style.display = '';
        if (arrow) arrow.style.transform = '';
        delete state[section];
    } else {
        body.style.display = 'none';
        if (arrow) arrow.style.transform = 'rotate(-90deg)';
        state[section] = 1;
    }
    sessionStorage.setItem('search-collapse', JSON.stringify(state));
});

/* Global search — overlay with debounced input, dropdown results */

function openSearchOverlay() {
    var overlay = document.getElementById('search-overlay');
    var input = document.getElementById('global-search');
    var trigger = document.getElementById('search-trigger');
    if (overlay && trigger) {
        var rect = getZoomedRect(trigger);
        overlay.style.top = (rect.bottom + 4) + 'px';
        // Align right edge with trigger button, but don't go off left edge
        var left = rect.right - 320;
        if (left < 8) left = 8;
        overlay.style.left = left + 'px';
        overlay.style.display = 'block';
        if (input) input.focus();
    }
}

function closeSearchOverlay() {
    var overlay = document.getElementById('search-overlay');
    var input = document.getElementById('global-search');
    var results = document.getElementById('search-results');
    if (overlay) overlay.style.display = 'none';
    if (results) { results.style.display = 'none'; results.innerHTML = ''; }
    if (input) { input.value = ''; input.blur(); }
}

(function () {
    var searchTimer = null;
    var searchInput = document.getElementById('global-search');
    var searchResults = document.getElementById('search-results');
    var searchOverlay = document.getElementById('search-overlay');

    if (!searchInput || !searchResults) return;

    searchInput.addEventListener('input', function () {
        clearTimeout(searchTimer);
        var q = searchInput.value.trim();
        if (q.length < 2) {
            searchResults.innerHTML = q.length === 1
                ? '<div style="padding: 10px 14px; font-size: 13px; color: var(--text-secondary);">Type at least 2 characters to search</div>'
                : '';
            searchResults.style.display = q.length === 1 ? 'block' : 'none';
            return;
        }
        searchTimer = setTimeout(function () {
            fetch('/search?q=' + encodeURIComponent(q))
                .then(function (r) {
                    if (!r.ok) { throw new Error('server error'); }
                    return r.text();
                })
                .then(function (html) {
                    searchResults.innerHTML = html;
                    searchResults.style.display = 'block';
                    _applySearchCollapse();
                })
                .catch(function () {
                    searchResults.innerHTML = '<p class="text-red-400 p-4">Search unavailable \u2014 try again</p>';
                    searchResults.style.display = 'block';
                });
        }, 300);
    });

    searchInput.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            e.preventDefault();
            closeSearchOverlay();
        }
    });

    document.addEventListener('click', function (e) {
        if (searchOverlay && searchOverlay.style.display !== 'none') {
            var trigger = document.getElementById('search-trigger');
            if (!searchOverlay.contains(e.target) && e.target !== trigger && !trigger.contains(e.target)) {
                closeSearchOverlay();
            }
        }
    });
})();

/* Artist stats — toggle between % complete and # remaining columns */
function switchStatMode(val) {
    var show = val === 'pct' ? 'col-set1' : 'col-set2';
    var hide = val === 'pct' ? 'col-set2' : 'col-set1';
    document.querySelectorAll('.' + show).forEach(function (el) { el.style.display = ''; });
    document.querySelectorAll('.' + hide).forEach(function (el) { el.style.display = 'none'; });
    document.cookie = 'stat_mode=' + val + '; path=/; max-age=31536000; SameSite=Lax';
}

(function () {
    var sel = document.getElementById('stat-mode');
    if (!sel) return;
    var match = document.cookie.match(/(?:^|;\s*)stat_mode=([^;]+)/);
    if (match && match[1] !== sel.value) {
        sel.value = match[1];
        switchStatMode(match[1]);
    }
})();

/* Artist navbar — convert vertical wheel scroll to horizontal + center active */
(function () {
    var nav = document.querySelector('.artist-nav');
    if (!nav) return;
    nav.addEventListener('wheel', function (e) {
        var menu = document.getElementById('artist-menu');
        if (menu && menu.contains(e.target)) return;
        if (e.deltaY === 0) return;
        e.preventDefault();
        nav.scrollLeft += e.deltaY;
    }, { passive: false });
    // Scroll active artist to center on page load
    var active = nav.querySelector('a[style*="font-weight: bold"]');
    if (active) {
        nav.scrollLeft = active.offsetLeft - nav.offsetWidth / 2 + active.offsetWidth / 2;
    }
})();

/* Hamburger artist menu — toggle, outside-click, Escape */

function toggleArtistMenu() {
    var menu = document.getElementById('artist-menu');
    if (!menu) return;
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

function closeArtistMenu() {
    var menu = document.getElementById('artist-menu');
    if (menu) menu.style.display = 'none';
}

document.addEventListener('click', function (e) {
    var menu = document.getElementById('artist-menu');
    var btn = document.getElementById('hamburger-btn');
    if (!menu || menu.style.display === 'none') return;
    if (!menu.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
        closeArtistMenu();
    }
});

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        closeArtistMenu();
        closeAlbumMovePopover();
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

/* Undo stack — client-side, session-scoped (cleared on page navigation) */

const undoStack = [];
const redoStack = [];
let sessionExpiredToastActive = false;

function showSessionExpiredToast() {
    if (sessionExpiredToastActive) return;
    sessionExpiredToastActive = true;
    var toast = document.createElement('div');
    toast.textContent = 'Session expired \u2014 please log in again';
    toast.style.cssText = [
        'position:fixed',
        'bottom:24px',
        'left:50%',
        'transform:translateX(-50%)',
        'background:#1f2937',
        'color:#fff',
        'padding:10px 20px',
        'border-radius:6px',
        'font-size:14px',
        'z-index:9999',
        'box-shadow:0 2px 8px rgba(0,0,0,0.3)',
        'pointer-events:none',
    ].join(';');
    document.body.appendChild(toast);
    setTimeout(function () { toast.remove(); sessionExpiredToastActive = false; }, 3000);
}

function showBriefToast(message) {
    var toast = document.createElement('div');
    toast.textContent = message;
    toast.style.cssText = [
        'position:fixed',
        'bottom:24px',
        'left:50%',
        'transform:translateX(-50%)',
        'background:#1f2937',
        'color:#fff',
        'padding:10px 20px',
        'border-radius:6px',
        'font-size:14px',
        'z-index:9999',
        'box-shadow:0 2px 8px rgba(0,0,0,0.3)',
        'pointer-events:none',
    ].join(';');
    document.body.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 3000);
}

function guardedAjax(url, options, cell, cellHTML) {
    if (cell) {
        function onBeforeSwap(evt) {
            if (evt.detail.target !== cell) return;
            cell.removeEventListener('htmx:beforeSwap', onBeforeSwap);
            var xhr = evt.detail.xhr;
            var isLoginPage = (xhr.responseURL && xhr.responseURL.indexOf('/login') !== -1) ||
                (xhr.responseText && xhr.responseText.indexOf('id="login-form"') !== -1);
            var isAuthError = xhr.status === 401 || xhr.status === 403;
            if (isLoginPage || isAuthError) {
                evt.detail.shouldSwap = false;
                cell.outerHTML = cellHTML;
                showSessionExpiredToast();
            }
        }
        cell.addEventListener('htmx:beforeSwap', onBeforeSwap);
    }
    htmx.ajax('POST', url, options);
}

function runUndoRedo(entry, targetStack, operationName) {
    const { songId, previousRating, previousNote, artistSlug } = entry;

    function applyEntry() {
        const cell = document.querySelector('[id^="rating-' + songId + '-"]');

        if (!cell) {
            showBriefToast(operationName + ' failed \u2014 try refreshing the page');
            return;
        }

        // Capture current cell state and push to the opposite stack
        const currentText = cell.textContent.trim();
        const capturedRating = /^[0-5]$/.test(currentText) ? parseInt(currentText) : null;
        const capturedNote = cell.getAttribute('data-note') || '';
        if (targetStack.length >= 50) targetStack.shift();
        targetStack.push({ songId, previousRating: capturedRating, previousNote: capturedNote, cellHTML: cell.outerHTML, artistSlug });

        if (previousRating === null) {
            guardedAjax('/rate/delete', {
                target: cell,
                swap: 'outerHTML',
                values: { song_id: songId },
            }, cell, entry.cellHTML);
        } else {
            guardedAjax('/rate', {
                target: cell,
                swap: 'outerHTML',
                values: { song_id: songId, rating: previousRating, note: previousNote || '' },
            }, cell, entry.cellHTML);
        }
    }

    // Navigate to the artist tab if not already there, then apply
    const currentSlug = window.location.pathname.replace(/^\/artists\//, '').replace(/\/$/, '');
    if (artistSlug && artistSlug !== currentSlug) {
        const navLink = document.querySelector('a[hx-get*="/artists/' + artistSlug + '"]');
        if (navLink) {
            navLink.click();
            document.addEventListener('htmx:afterSettle', function onSettle() {
                document.removeEventListener('htmx:afterSettle', onSettle);
                applyEntry();
            });
        } else {
            window.location.href = '/artists/' + artistSlug;
        }
    } else {
        applyEntry();
    }
}

document.addEventListener('keydown', function (e) {
    if (!(e.ctrlKey || e.metaKey)) return;
    const tag = document.activeElement && document.activeElement.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;

    if (e.shiftKey && e.key === 'z') {
        e.preventDefault();
        const entry = redoStack.pop();
        if (!entry) return;
        runUndoRedo(entry, undoStack, 'redo');
        return;
    }

    if (!e.shiftKey && e.key === 'z') {
        e.preventDefault();
        const entry = undoStack.pop();
        if (!entry) return;
        runUndoRedo(entry, redoStack, 'undo');
    }
});

/* Inline text/date edit — edit mode only */

function updatePromotedStyle(checkbox) {
    var row = checkbox.closest('tr');
    var cell = row ? row.querySelector('td:first-child') : null;
    if (!cell) return;
    var tag = cell.querySelector('.promoted-tag');
    if (checkbox.checked) {
        cell.style.borderLeft = '4px solid var(--promoted-song)';
        if (!tag) {
            tag = document.createElement('span');
            tag.className = 'promoted-tag';
            tag.style.cssText = 'font-size:9px;padding:1px 5px;margin-left:4px;border-radius:3px;background-color:var(--promoted-song);color:var(--text-primary);';
            tag.textContent = 'promoted';
            cell.appendChild(tag);
        }
    } else {
        cell.style.borderLeft = '1px solid var(--grid-line)';
        if (tag) tag.remove();
    }
}

function showInlineEdit(event, endpoint, span) {
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
    setTimeout(function() { settled = true; }, 300);
    input.focus();
    input.select();

    function commit() {
        const val = input.value.trim();
        const csrfToken = document.querySelector('meta[name="csrf-token"]');
        const headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
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
            newSpan.textContent = text || 'date';
            input.replaceWith(newSpan);
        });
    }

    function restore() {
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
        setTimeout(function() {
            if (settled && document.activeElement !== input) restore();
        }, 200);
    });
}

/**
 * Apply yyyy-mm-dd auto-formatting to a text input.
 * Strips non-digits, auto-inserts hyphens, caps at 10 chars.
 */
function applyDateFormat(input) {
    input.type = 'text';
    input.placeholder = 'yyyy-mm-dd';
    input.maxLength = 10;
    input.style.fontFamily = 'monospace';
    input.addEventListener('input', function() {
        var v = this.value.replace(/[^0-9]/g, '');
        if (v.length > 4) v = v.slice(0, 4) + '-' + v.slice(4);
        if (v.length > 7) v = v.slice(0, 7) + '-' + v.slice(7);
        if (v.length > 10) v = v.slice(0, 10);
        this.value = v;
        this.style.borderColor = '';
    });
}

// Auto-apply to all date inputs with the data-date-format attribute
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('[data-date-format]').forEach(applyDateFormat);
});
// Also apply after HTMX swaps (for fragments loaded dynamically)
document.addEventListener('htmx:afterSettle', function(e) {
    e.detail.elt.querySelectorAll('[data-date-format]').forEach(applyDateFormat);

    // Update artist navbar active indicator after HTMX navigation
    var header = e.detail.elt.querySelector('[data-current-artist-id]');
    if (header) {
        var activeId = header.dataset.currentArtistId;
        document.querySelectorAll('[data-artist-id]').forEach(function(link) {
            if (link.dataset.artistId === activeId) {
                link.style.fontWeight = 'bold';
                link.style.borderBottom = '2px solid var(--artist-button-text)';
            } else {
                link.style.fontWeight = '';
                link.style.borderBottom = '';
            }
        });
    }
});

// Force repaint on row after HTMX outerHTML swap to fix collapsed borders
document.addEventListener('htmx:afterSettle', function(e) {
    var elt = e.detail.elt;
    if (!elt) return;
    // For outerHTML swaps, elt is the parent — look for a rating cell inside it
    var cell = (elt.id && elt.id.startsWith('rating-')) ? elt
             : elt.querySelector('[id^="rating-"]');
    if (cell) {
        var row = cell.closest('tr');
        if (row) { row.style.display = 'none'; row.offsetHeight; row.style.display = ''; }
    }
});

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

    span.replaceWith(input);
    input.focus();

    function commit() {
        const val = input.value.trim();
        if (val && !/^\d{4}-\d{2}-\d{2}$/.test(val)) {
            input.style.borderColor = 'var(--delete-button, red)';
            return;
        }
        const csrfToken = document.querySelector('meta[name="csrf-token"]');
        const headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
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
            input.replaceWith(newSpan);
        });
    }

    function restore() {
        const newSpan = document.createElement('span');
        newSpan.className = 'edit-inline';
        newSpan.style.cursor = 'pointer';
        newSpan.dataset.fullDate = currentFullDate || '';
        if (!currentFullDate) newSpan.style.color = 'var(--text-secondary)';
        newSpan.setAttribute('onclick', "showInlineDateEdit(event, '" + endpoint + "', this, this.dataset.fullDate)");
        newSpan.textContent = original;
        input.replaceWith(newSpan);
    }

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); commit(); }
        else if (e.key === 'Escape') { e.preventDefault(); restore(); }
    });

    input.addEventListener('change', function() { commit(); });

    input.addEventListener('blur', function() {
        setTimeout(function() {
            if (document.activeElement !== input) restore();
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
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:180px; max-height:240px; overflow-y:auto;';

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
        popover.appendChild(label);
    });

    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex; gap:4px; margin-top:6px; justify-content:flex-end;';

    var saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'padding:2px 10px; font-size:12px; background:var(--link,#2563EB); color:#fff; border:none; border-radius:3px; cursor:pointer;';
    saveBtn.onclick = function() {
        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
        // Re-read checkboxes for current state
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

    // Position below the span
    var rect = getZoomedRect(span);
    popover.style.top = rect.bottom + 2 + 'px';
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    activeGenrePopover = popover;
}

// Close genre popover on outside click
document.addEventListener('click', function(e) {
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

function showCountryEdit(event, artistId, span, allCountries, currentId) {
    event.stopPropagation();
    closeCountryPopover();

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:180px; max-height:240px; overflow-y:auto;';

    allCountries.forEach(function(c) {
        var btn = document.createElement('div');
        btn.textContent = c.name;
        btn.style.cssText = 'padding:3px 6px; font-size:12px; cursor:pointer; border-radius:2px;';
        if (c.id === currentId) btn.style.fontWeight = 'bold';
        btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
        btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
        btn.addEventListener('click', function() {
            var csrfToken = document.querySelector('meta[name="csrf-token"]');
            var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
            if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
            fetch('/edit/artist/' + artistId + '/country', {
                method: 'POST',
                headers: headers,
                body: 'country_id=' + c.id,
            }).then(function(r) {
                if (!r.ok) throw new Error('save failed');
                return r.json();
            }).then(function(data) {
                span.textContent = data.country;
                span.setAttribute('data-country-id', data.id);
                closeCountryPopover();
            }).catch(function() {
                showToast('Failed to save country — try again');
                closeCountryPopover();
            });
        });
        popover.appendChild(btn);
    });

    var rect = getZoomedRect(span);
    popover.style.top = rect.bottom + 2 + 'px';
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    activeCountryPopover = popover;
}

document.addEventListener('click', function(e) {
    if (activeCountryPopover && !activeCountryPopover.contains(e.target)) {
        closeCountryPopover();
    }
    if (activeGenderPopover && !activeGenderPopover.contains(e.target)) {
        closeGenderPopover();
    }
});

/* Inline gender edit — pick gender popover */

var activeGenderPopover = null;
var GENDER_CSS_MAP = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed', 3: '--gender-anime'};

function closeGenderPopover() {
    if (activeGenderPopover) {
        activeGenderPopover.remove();
        activeGenderPopover = null;
    }
}

function showGenderEdit(event, artistId, span, allGenders, currentId) {
    event.stopPropagation();
    closeGenderPopover();

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:180px; max-height:240px; overflow-y:auto;';

    allGenders.forEach(function(g) {
        var btn = document.createElement('div');
        btn.textContent = g.name;
        btn.style.cssText = 'padding:3px 6px; font-size:12px; cursor:pointer; border-radius:2px;';
        if (g.id === currentId) btn.style.fontWeight = 'bold';
        btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
        btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
        btn.addEventListener('click', function() {
            var csrfToken = document.querySelector('meta[name="csrf-token"]');
            var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
            if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
            fetch('/edit/artist/' + artistId + '/gender', {
                method: 'POST',
                headers: headers,
                body: 'gender_id=' + g.id,
            }).then(function(r) {
                if (!r.ok) throw new Error('save failed');
                return r.json();
            }).then(function(data) {
                span.textContent = data.gender;
                span.setAttribute('data-gender-id', data.id);
                // Update the left border colour on the artist header
                var cssVar = GENDER_CSS_MAP[data.id] || '--text-primary';
                var headerDiv = span.closest('div[style*="border-left"]');
                if (headerDiv) {
                    headerDiv.style.borderLeftColor = 'var(' + cssVar + ')';
                }
                // Update navbar pills and menu items for this artist
                document.querySelectorAll('[data-artist-id="' + artistId + '"]').forEach(function(el) {
                    el.style.backgroundColor = 'var(' + cssVar + ')';
                });
                closeGenderPopover();
            }).catch(function() {
                showToast('Failed to save gender — try again');
                closeGenderPopover();
            });
        });
        popover.appendChild(btn);
    });

    var rect = getZoomedRect(span);
    popover.style.top = rect.bottom + 2 + 'px';
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    activeGenderPopover = popover;
}

/* Inline album move — pick album popover */

var activeAlbumMovePopover = null;

function closeAlbumMovePopover() {
    if (activeAlbumMovePopover) {
        activeAlbumMovePopover.remove();
        activeAlbumMovePopover = null;
    }
}

function showAlbumMove(event, songId, span, allAlbums, currentAlbumId) {
    event.stopPropagation();
    closeAlbumMovePopover();
    closeAlbumAddPopover();
    closeAlbumSongSearchPopover();

    var others = allAlbums.filter(function(a) { return a.id !== currentAlbumId; });
    if (!others.length) {
        showToast('No other albums to move to');
        return;
    }

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:280px; max-height:320px; display:flex; flex-direction:column;';

    var title = document.createElement('div');
    title.textContent = 'Move to album:';
    title.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:4px; color:var(--text-secondary);';
    popover.appendChild(title);

    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search albums or artists...';
    searchInput.style.cssText = 'width:100%; font-size:11px; padding:4px 6px; margin-bottom:6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box;';
    popover.appendChild(searchInput);

    var listContainer = document.createElement('div');
    listContainer.style.cssText = 'overflow-y:auto; flex:1;';
    popover.appendChild(listContainer);

    function renderList(filter) {
        listContainer.innerHTML = '';
        var lc = (filter || '').toLowerCase();
        var parentMap = (typeof _artistParentMap !== 'undefined') ? _artistParentMap : {};
        // Group albums: merge children into their parent group, dedup preferring child entry
        var grouped = {};
        var groupOrder = [];
        var entryMap = {};
        others.forEach(function(a) {
            if (lc && a.name.toLowerCase().indexOf(lc) === -1 && a.artist.toLowerCase().indexOf(lc) === -1) return;
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
        // Sort: current artist first, Misc. Artists second, rest alphabetical
        var currentArtistName = null;
        others.forEach(function(a) { if (a.artistId === _currentArtistId) currentArtistName = a.artist; });
        // Also treat parent of current artist as current
        if (!currentArtistName && parentMap[others[0] && others[0].artist]) {
            others.forEach(function(a) { if (a.artistId === _currentArtistId) currentArtistName = parentMap[a.artist] || a.artist; });
        }
        groupOrder.sort(function(a, b) {
            var aRank = a === currentArtistName ? 0 : a === 'Misc. Artists' ? 1 : 2;
            var bRank = b === currentArtistName ? 0 : b === 'Misc. Artists' ? 1 : 2;
            if (aRank !== bRank) return aRank - bRank;
            return a.toLowerCase() < b.toLowerCase() ? -1 : a.toLowerCase() > b.toLowerCase() ? 1 : 0;
        });
        groupOrder.forEach(function(group) {
            var header = document.createElement('div');
            header.textContent = group;
            header.style.cssText = 'font-size:10px; font-weight:bold; padding:4px 6px 2px; color:var(--text-secondary); text-transform:uppercase;';
            listContainer.appendChild(header);
            // Sort: parent albums first, then children grouped by subunit
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
                btn.addEventListener('click', function() {
                    var csrfToken = document.querySelector('meta[name="csrf-token"]');
                    var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
                    if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
                    fetch('/edit/song/' + songId + '/move-album', {
                        method: 'POST',
                        headers: headers,
                        body: 'album_id=' + item.id,
                    }).then(function(r) {
                        if (!r.ok) throw new Error('move failed');
                        return r.json();
                    }).then(function() {
                        closeAlbumMovePopover();
                        window.location.reload();
                    }).catch(function() {
                        showToast('Failed to move song — try again');
                        closeAlbumMovePopover();
                    });
                });
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

    renderList('');
    searchInput.addEventListener('input', function() { renderList(searchInput.value); });

    var rect = getZoomedRect(span);
    popover.style.top = rect.bottom + 2 + 'px';
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    activeAlbumMovePopover = popover;
    searchInput.focus();
}

/* Add song to additional album popover */

var activeAlbumAddPopover = null;

function closeAlbumAddPopover() {
    if (activeAlbumAddPopover) {
        activeAlbumAddPopover.remove();
        activeAlbumAddPopover = null;
    }
}

function showAlbumAdd(event, songId, span, allAlbums, currentAlbumId) {
    event.stopPropagation();
    closeAlbumAddPopover();
    closeAlbumMovePopover();
    closeAlbumSongSearchPopover();

    var others = allAlbums.filter(function(a) { return a.id !== currentAlbumId; });
    if (!others.length) {
        showToast('No other albums available');
        return;
    }

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:280px; max-height:320px; display:flex; flex-direction:column;';

    var title = document.createElement('div');
    title.textContent = 'Add to album:';
    title.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:4px; color:var(--text-secondary);';
    popover.appendChild(title);

    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search albums or artists...';
    searchInput.style.cssText = 'width:100%; font-size:11px; padding:4px 6px; margin-bottom:6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box;';
    popover.appendChild(searchInput);

    var listContainer = document.createElement('div');
    listContainer.style.cssText = 'overflow-y:auto; flex:1;';
    popover.appendChild(listContainer);

    function renderList(filter) {
        listContainer.innerHTML = '';
        var lc = (filter || '').toLowerCase();
        var parentMap = (typeof _artistParentMap !== 'undefined') ? _artistParentMap : {};
        var grouped = {};
        var groupOrder = [];
        var entryMap = {};
        others.forEach(function(a) {
            if (lc && a.name.toLowerCase().indexOf(lc) === -1 && a.artist.toLowerCase().indexOf(lc) === -1) return;
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
        var currentArtistName = null;
        others.forEach(function(a) { if (a.artistId === _currentArtistId) currentArtistName = a.artist; });
        if (!currentArtistName && parentMap[others[0] && others[0].artist]) {
            others.forEach(function(a) { if (a.artistId === _currentArtistId) currentArtistName = parentMap[a.artist] || a.artist; });
        }
        groupOrder.sort(function(a, b) {
            var aRank = a === currentArtistName ? 0 : a === 'Misc. Artists' ? 1 : 2;
            var bRank = b === currentArtistName ? 0 : b === 'Misc. Artists' ? 1 : 2;
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
                btn.addEventListener('click', function() {
                    var csrfToken = document.querySelector('meta[name="csrf-token"]');
                    var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
                    if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
                    fetch('/edit/song/' + songId + '/add-to-album', {
                        method: 'POST',
                        headers: headers,
                        body: 'album_id=' + item.id,
                    }).then(function(r) {
                        if (r.status === 400) return r.json().then(function(d) { showToast(d.error || 'Failed'); throw new Error('bad'); });
                        if (!r.ok) throw new Error('failed');
                        return r.json();
                    }).then(function() {
                        closeAlbumAddPopover();
                        window.location.reload();
                    }).catch(function() {
                        closeAlbumAddPopover();
                    });
                });
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

    renderList('');
    searchInput.addEventListener('input', function() { renderList(searchInput.value); });

    var rect = getZoomedRect(span);
    popover.style.top = rect.bottom + 2 + 'px';
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    activeAlbumAddPopover = popover;
    searchInput.focus();
}

/* Add existing song to album (search popover) */

var activeAlbumSongSearchPopover = null;

function closeAlbumSongSearchPopover() {
    if (activeAlbumSongSearchPopover) {
        activeAlbumSongSearchPopover.remove();
        activeAlbumSongSearchPopover = null;
    }
}

function showAlbumSongSearch(event, albumId, artistId, span) {
    event.stopPropagation();
    closeAlbumSongSearchPopover();
    closeAlbumMovePopover();
    closeAlbumAddPopover();

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:320px; max-height:360px; display:flex; flex-direction:column;';

    var title = document.createElement('div');
    title.textContent = 'Add song to album:';
    title.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:4px; color:var(--text-secondary);';
    popover.appendChild(title);

    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search existing or type new song name...';
    searchInput.style.cssText = 'width:100%; font-size:11px; padding:4px 6px; margin-bottom:6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box;';
    popover.appendChild(searchInput);

    var listContainer = document.createElement('div');
    listContainer.style.cssText = 'overflow-y:auto; flex:1;';
    popover.appendChild(listContainer);

    var debounceTimer = null;

    var _createSongNum = 0;

    function showCreateSongForm(name) {
        // Switch popover to creation mode
        listContainer.innerHTML = '';
        searchInput.style.display = 'none';
        title.textContent = 'Create new song:';
        popover.style.width = '380px';

        _createSongNum++;
        var sn = _createSongNum;

        var form = document.createElement('div');

        // Song name
        var nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.value = name;
        nameInput.placeholder = 'Song name';
        nameInput.className = 'create-song-name';
        nameInput.style.cssText = 'width:100%; font-size:12px; padding:4px 6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box; margin-bottom:6px;';
        form.appendChild(nameInput);

        // Checkboxes row
        var cbRow = document.createElement('div');
        cbRow.style.cssText = 'display:flex; gap:10px; margin-bottom:6px;';
        cbRow.innerHTML =
            '<label style="font-size:11px; cursor:pointer;"><input type="checkbox" class="create-song-promoted" style="margin-right:2px;"> Promoted</label>' +
            '<label style="font-size:11px; cursor:pointer;"><input type="checkbox" class="create-song-remix" style="margin-right:2px;"> Remix</label>';
        form.appendChild(cbRow);

        // Artists section
        var artistLabel = document.createElement('div');
        artistLabel.style.cssText = 'font-size:10px; font-weight:bold; color:var(--text-secondary); margin-bottom:3px;';
        artistLabel.textContent = 'Artists:';
        form.appendChild(artistLabel);

        var artistContainer = document.createElement('div');
        artistContainer.id = 'create-song-artists-' + sn;
        artistContainer.style.cssText = 'margin-bottom:4px;';
        form.appendChild(artistContainer);

        // Artist dropdown
        var artistSelect = document.createElement('select');
        artistSelect.style.cssText = 'font-size:11px; padding:2px 4px; border:1px solid var(--border,#ccc); border-radius:3px; margin-bottom:8px;';
        function refreshArtistSelect() {
            var used = [];
            artistContainer.querySelectorAll('.create-artist-row').forEach(function(r) {
                if (r.dataset.artistId) used.push(parseInt(r.dataset.artistId));
            });
            var opts = '<option value="">+ Add artist...</option>';
            if (typeof _allArtists !== 'undefined') {
                _allArtists.forEach(function(a) {
                    if (used.indexOf(a.id) === -1) {
                        opts += '<option value="' + a.id + '">' + a.name.replace(/</g, '&lt;') + '</option>';
                    }
                });
            }
            artistSelect.innerHTML = opts;
            artistSelect.value = '';
        }

        function addArtistRow(aid, aname, isMain) {
            var row = document.createElement('div');
            row.className = 'create-artist-row';
            row.dataset.artistId = aid;
            row.style.cssText = 'display:flex; align-items:center; gap:4px; margin-bottom:2px;';
            var nameSpan = document.createElement('span');
            nameSpan.textContent = aname;
            nameSpan.style.cssText = 'font-size:11px;';
            row.appendChild(nameSpan);
            var roleSelect = document.createElement('select');
            roleSelect.className = 'create-artist-role';
            roleSelect.style.cssText = 'font-size:10px; padding:1px 3px; border:1px solid var(--border,#ccc); border-radius:3px;';
            roleSelect.innerHTML = '<option value="main"' + (isMain ? ' selected' : '') + '>Main</option>' +
                                   '<option value="feat"' + (!isMain ? ' selected' : '') + '>Featured</option>';
            row.appendChild(roleSelect);
            if (artistContainer.children.length > 0) {
                var removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.textContent = 'x';
                removeBtn.style.cssText = 'font-size:10px; color:var(--delete-button,#DC2626); cursor:pointer; background:none; border:none; padding:0 2px;';
                removeBtn.addEventListener('click', function() { row.remove(); refreshArtistSelect(); });
                row.appendChild(removeBtn);
            }
            artistContainer.appendChild(row);
            refreshArtistSelect();
        }

        artistSelect.addEventListener('change', function() {
            var id = parseInt(artistSelect.value);
            if (!id) return;
            var artist = _allArtists.find(function(a) { return a.id === id; });
            if (artist) addArtistRow(id, artist.name, false);
        });
        form.appendChild(artistSelect);

        // Auto-add current artist as main
        var currentName = 'Current Artist';
        if (typeof _allArtists !== 'undefined') {
            var found = _allArtists.find(function(a) { return a.id === artistId; });
            if (found) currentName = found.name;
        }
        addArtistRow(artistId, currentName, true);

        // Buttons row
        var btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex; gap:6px; justify-content:flex-end;';
        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.textContent = 'Back';
        cancelBtn.style.cssText = 'font-size:11px; padding:4px 10px; border-radius:3px; background:var(--button-secondary,#e5e7eb); color:var(--text-primary); border:none; cursor:pointer;';
        cancelBtn.addEventListener('click', function() {
            searchInput.style.display = '';
            title.textContent = 'Add song to album:';
            popover.style.width = '320px';
            doSearch(searchInput.value.trim());
        });
        btnRow.appendChild(cancelBtn);
        var submitBtn = document.createElement('button');
        submitBtn.type = 'button';
        submitBtn.textContent = 'Create Song';
        submitBtn.style.cssText = 'font-size:11px; padding:4px 10px; border-radius:3px; background:var(--edit-on-button,#2563EB); color:var(--button-text,#fff); border:none; cursor:pointer;';
        submitBtn.addEventListener('click', function() {
            var songName = form.querySelector('.create-song-name').value.trim();
            if (!songName) { showToast('Song name is required'); return; }
            var artists = [];
            artistContainer.querySelectorAll('.create-artist-row').forEach(function(row) {
                var role = row.querySelector('.create-artist-role');
                artists.push({ artist_id: parseInt(row.dataset.artistId), is_main: role.value === 'main' });
            });
            if (!artists.length || !artists.some(function(a) { return a.is_main; })) {
                showToast('At least one main artist is required'); return;
            }
            var csrfToken = document.querySelector('meta[name="csrf-token"]');
            var headers = { 'Content-Type': 'application/json' };
            if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
            fetch('/edit/album/' + albumId + '/create-song', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    name: songName,
                    artists: artists,
                    is_promoted: form.querySelector('.create-song-promoted').checked,
                    is_remix: form.querySelector('.create-song-remix').checked,
                }),
            }).then(function(r) {
                if (r.status === 400) return r.json().then(function(d) { showToast(d.error || 'Failed'); throw new Error('bad'); });
                if (!r.ok) throw new Error('failed');
                return r.json();
            }).then(function() {
                closeAlbumSongSearchPopover();
                window.location.reload();
            }).catch(function(err) {
                if (err && err.message !== 'bad') {
                    showToast('Error creating song');
                    console.error('Create song error:', err);
                }
            });
        });
        btnRow.appendChild(submitBtn);
        form.appendChild(btnRow);

        listContainer.appendChild(form);
        nameInput.focus();
        nameInput.select();
    }

    function doSearch(query) {
        if (query.length < 2) {
            listContainer.innerHTML = '<div style="font-size:11px; color:var(--text-secondary); padding:6px;">Type at least 2 characters...</div>';
            return;
        }
        fetch('/edit/album/' + albumId + '/search-songs?q=' + encodeURIComponent(query))
            .then(function(r) { if (!r.ok) throw new Error(); return r.json(); })
            .then(function(results) {
                listContainer.innerHTML = '';
                // Always show create-new option at the top
                var createBtn = document.createElement('div');
                createBtn.style.cssText = 'padding:4px 6px; font-size:12px; cursor:pointer; border-radius:2px; border-bottom:1px solid var(--border,#ccc); padding-bottom:6px; margin-bottom:4px;';
                var plus = document.createElement('span');
                plus.textContent = '+ Create "' + query + '"';
                plus.style.cssText = 'color:var(--link,#2563EB); font-weight:bold;';
                createBtn.appendChild(plus);
                createBtn.addEventListener('mouseenter', function() { createBtn.style.background = _hoverBg(); });
                createBtn.addEventListener('mouseleave', function() { createBtn.style.background = ''; });
                createBtn.addEventListener('click', function(e) { e.stopPropagation(); showCreateSongForm(query); });
                listContainer.appendChild(createBtn);
                if (!results.length) {
                    var empty = document.createElement('div');
                    empty.textContent = 'No existing songs found';
                    empty.style.cssText = 'font-size:11px; color:var(--text-secondary); padding:6px;';
                    listContainer.appendChild(empty);
                    return;
                }
                var divider = document.createElement('div');
                divider.textContent = 'Or add existing:';
                divider.style.cssText = 'font-size:10px; font-weight:bold; color:var(--text-secondary); padding:4px 6px 2px;';
                listContainer.appendChild(divider);
                results.forEach(function(item) {
                    var btn = document.createElement('div');
                    btn.style.cssText = 'padding:4px 6px; font-size:12px; cursor:pointer; border-radius:2px;';
                    var nameSpan = document.createElement('span');
                    nameSpan.textContent = item.name;
                    btn.appendChild(nameSpan);
                    var detailSpan = document.createElement('span');
                    detailSpan.textContent = ' — ' + item.artist + ' / ' + item.album;
                    detailSpan.style.cssText = 'color:var(--text-secondary); font-size:11px;';
                    btn.appendChild(detailSpan);
                    btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
                    btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
                    btn.addEventListener('click', function() {
                        var csrfToken = document.querySelector('meta[name="csrf-token"]');
                        var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
                        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
                        fetch('/edit/album/' + albumId + '/add-song', {
                            method: 'POST',
                            headers: headers,
                            body: 'song_id=' + item.id + '&artist_id=' + (typeof _currentArtistId !== 'undefined' ? _currentArtistId : ''),
                        }).then(function(r) {
                            if (r.status === 400) return r.json().then(function(d) { showToast(d.error || 'Failed'); throw new Error('bad'); });
                            if (!r.ok) throw new Error('failed');
                            return r.json();
                        }).then(function() {
                            closeAlbumSongSearchPopover();
                            window.location.reload();
                        }).catch(function() {
                            closeAlbumSongSearchPopover();
                        });
                    });
                    listContainer.appendChild(btn);
                });
            })
            .catch(function() {
                listContainer.innerHTML = '<div style="font-size:11px; color:var(--text-secondary); padding:6px;">Search failed</div>';
            });
    }

    listContainer.innerHTML = '<div style="font-size:11px; color:var(--text-secondary); padding:6px;">Type at least 2 characters...</div>';

    searchInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function() { doSearch(searchInput.value.trim()); }, 250);
    });

    var rect = getZoomedRect(span);
    popover.style.top = rect.bottom + 2 + 'px';
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    activeAlbumSongSearchPopover = popover;
    searchInput.focus();
}

document.addEventListener('click', function(e) {
    if (activeAlbumMovePopover && !activeAlbumMovePopover.contains(e.target)) {
        closeAlbumMovePopover();
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
    event.stopPropagation();
    closeMergePopover();

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:340px; max-height:360px; display:flex; flex-direction:column;';

    var title = document.createElement('div');
    title.textContent = 'Merge into "' + songName + '":';
    title.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:4px; color:var(--text-secondary);';
    popover.appendChild(title);

    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search songs...';
    searchInput.style.cssText = 'width:100%; font-size:11px; padding:4px 6px; margin-bottom:6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box;';
    popover.appendChild(searchInput);

    var listContainer = document.createElement('div');
    listContainer.style.cssText = 'overflow-y:auto; flex:1;';
    popover.appendChild(listContainer);

    var searchMode = false;
    var searchTimer = null;
    var candidates = null;

    function renderResults(items) {
        listContainer.innerHTML = '';
        if (!items || !items.length) {
            var empty = document.createElement('div');
            empty.textContent = 'No matching songs found.';
            empty.style.cssText = 'font-size:11px; color:var(--text-secondary); padding:6px;';
            listContainer.appendChild(empty);
            return;
        }
        items.forEach(function(item) {
            var btn = document.createElement('div');
            btn.textContent = item.name + ' \u2014 ' + item.artist + ' (' + item.album + ')';
            btn.style.cssText = 'padding:4px 6px; font-size:11px; cursor:pointer; border-radius:2px;';
            btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
            btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
            btn.addEventListener('click', function() {
                closeMergePopover();
                showMergeConfirm(songId, songName, item.id, item.name, item.artist, item.album);
            });
            listContainer.appendChild(btn);
        });
    }

    // Load default candidates
    listContainer.innerHTML = '<div style="font-size:11px; color:var(--text-secondary); padding:6px;">Loading...</div>';
    fetch('/edit/song/' + songId + '/merge-candidates', {
        headers: _csrfHeaders({})
    }).then(function(r) { return r.json(); }).then(function(data) {
        candidates = data;
        if (!searchMode) renderResults(candidates);
    }).catch(function() {
        listContainer.innerHTML = '<div style="font-size:11px; color:var(--text-secondary); padding:6px;">Failed to load candidates</div>';
    });

    searchInput.addEventListener('input', function() {
        var q = searchInput.value.trim();
        if (!q) {
            searchMode = false;
            if (candidates) renderResults(candidates);
            return;
        }
        searchMode = true;
        if (q.length < 2) {
            renderResults([]);
            return;
        }
        if (searchTimer) clearTimeout(searchTimer);
        searchTimer = setTimeout(function() {
            fetch('/edit/song/' + songId + '/merge-search?q=' + encodeURIComponent(q), {
                headers: _csrfHeaders({})
            }).then(function(r) { return r.json(); }).then(function(data) {
                if (searchMode) renderResults(data);
            }).catch(function() {
                renderResults([]);
            });
        }, 300);
    });

    var rect = getZoomedRect(span);
    popover.style.top = rect.bottom + 2 + 'px';
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    activeMergePopover = popover;
    searchInput.focus();
}

function showMergeConfirm(keptId, keptName, absorbedId, absorbedName, absorbedArtist, absorbedAlbum) {
    var msg = 'Merge "' + absorbedName + ' \u2014 ' + absorbedArtist + ' (' + absorbedAlbum + ')" into "' + keptName + '"? The absorbed song will be deleted. Ratings and links will be combined.';
    showDeleteConfirm('Merge songs?', msg, '/edit/song/' + keptId + '/merge', true, 'Merge');
    // Override the form submit to include absorbed_song_id
    var form = document.getElementById('confirm-delete-form');
    // Remove any previous absorbed_song_id hidden input
    var prev = form.querySelector('input[name="absorbed_song_id"]');
    if (prev) prev.remove();
    var hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.name = 'absorbed_song_id';
    hidden.value = absorbedId;
    form.appendChild(hidden);
}

/* Song artist management popover */

var activeSongArtistPopover = null;

function closeSongArtistPopover() {
    if (activeSongArtistPopover) {
        activeSongArtistPopover.remove();
        activeSongArtistPopover = null;
    }
}

function _csrfHeaders(extra) {
    var h = extra || {};
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) h['X-CSRFToken'] = meta.content;
    return h;
}

function _updateCollabLabel(songId, artists) {
    var row = document.getElementById('song-' + songId);
    if (!row) return;
    var td = row.querySelector('td');
    if (!td) return;
    // Remove existing collab label span (italic span inside the td)
    var existing = td.querySelector('span[style*="font-style: italic"]');
    if (existing) existing.remove();
    // Build new label from other main artists (excluding current page artist)
    var currentId = (typeof _currentArtistId !== 'undefined') ? _currentArtistId : null;
    var otherMain = artists.filter(function(a) { return a.is_main && a.artist_id !== currentId; });
    if (otherMain.length > 0) {
        var label = document.createElement('span');
        label.style.cssText = 'color: var(--text-secondary); font-style: italic;';
        label.textContent = '(feat. ' + otherMain.map(function(a) { return a.name; }).join(', ') + ')';
        td.appendChild(document.createTextNode(' '));
        td.appendChild(label);
    }
}

function showSongArtists(event, songId, span) {
    event.stopPropagation();
    closeSongArtistPopover();
    closeAlbumMovePopover();
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

            if (artists.length > 1) {
                var removeBtn = document.createElement('button');
                removeBtn.textContent = '\u00d7';
                removeBtn.style.cssText = 'font-size:13px; color:var(--delete-button,#DC2626); background:none; border:none; cursor:pointer; padding:0 2px;';
                removeBtn.addEventListener('click', function() {
                    fetch('/edit/song/' + songId + '/artists/' + a.artist_id, {
                        method: 'DELETE',
                        headers: _csrfHeaders({}),
                    }).then(function(r) {
                        if (!r.ok) throw new Error('failed');
                        artists = artists.filter(function(x) { return x.artist_id !== a.artist_id; });
                        _songArtists[songId] = artists;
                        renderList();
                        rebuildOptions();
                        _updateCollabLabel(songId, artists);
                    });
                });
                row.appendChild(removeBtn);
            }

            listContainer.appendChild(row);
        });
    }

    renderList();
    popover.appendChild(listContainer);

    // Add artist dropdown
    var addRow = document.createElement('div');
    addRow.style.cssText = 'margin-top:6px; border-top:1px solid var(--border); padding-top:6px;';

    var select = document.createElement('select');
    select.style.cssText = 'font-size:11px; width:100%; padding:2px 4px; border:1px solid var(--border); border-radius:3px;';

    function rebuildOptions() {
        select.innerHTML = '';
        var opt0 = document.createElement('option');
        opt0.value = '';
        opt0.textContent = '+ Add artist...';
        select.appendChild(opt0);
        var usedIds = artists.map(function(a) { return a.artist_id; });
        allArtists.forEach(function(a) {
            if (usedIds.indexOf(a.id) === -1) {
                var opt = document.createElement('option');
                opt.value = a.id;
                opt.textContent = a.name;
                select.appendChild(opt);
            }
        });
    }
    rebuildOptions();

    select.addEventListener('change', function() {
        var artistId = parseInt(select.value);
        if (!artistId) return;
        var artist = allArtists.find(function(a) { return a.id === artistId; });
        if (!artist) return;
        fetch('/edit/song/' + songId + '/artists', {
            method: 'POST',
            headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
            body: 'artist_id=' + artistId + '&is_main=false',
        }).then(function(r) {
            if (!r.ok) throw new Error('failed');
            artists.push({ artist_id: artistId, name: artist.name, is_main: false });
            _songArtists[songId] = artists;
            renderList();
            rebuildOptions();
            _updateCollabLabel(songId, artists);
        });
    });

    addRow.appendChild(select);
    popover.appendChild(addRow);

    var rect = getZoomedRect(span);
    popover.style.top = rect.bottom + 2 + 'px';
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    activeSongArtistPopover = popover;
}

/* Add album modal helpers */

var _newAlbumSongCount = 0;

function resetAddAlbumModal() {
    _newAlbumSongCount = 0;
    var name = document.getElementById('new-album-name');
    if (name) name.value = '';
    var date = document.getElementById('new-album-date');
    if (date) date.value = '';
    var type = document.getElementById('new-album-type');
    if (type) type.selectedIndex = 0;
    document.querySelectorAll('#new-album-genres input').forEach(function(cb) { cb.checked = false; });
    var songs = document.getElementById('new-album-songs');
    if (songs) songs.innerHTML = '';
    var searchInput = document.getElementById('album-song-search');
    if (searchInput) searchInput.value = '';
    var searchResults = document.getElementById('album-song-search-results');
    if (searchResults) { searchResults.style.display = 'none'; searchResults.innerHTML = ''; }
    validateAddAlbum();
}

function validateAddAlbum() {
    var btn = document.getElementById('add-album-submit-btn');
    if (!btn) return;
    var valid = true;

    var name = document.getElementById('new-album-name');
    if (!name || !name.value.trim()) valid = false;

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
            '<button type="button" onclick="this.closest(\'[id^=new-song-]\').remove();validateAddAlbum()" class="text-xs px-1" style="color:var(--delete-button,#DC2626);">&times;</button>' +
        '</div>' +
        '<div class="flex items-center gap-2 ml-2">' +
            '<span class="text-xs" style="color:var(--text-secondary);">Artists:</span>' +
            '<div id="new-song-artists-' + n + '" class="flex flex-wrap gap-2"></div>' +
            '<select class="new-song-artist-select text-xs px-1 border rounded" style="border-color:var(--border);" onchange="onNewSongArtistChange(this,' + n + ')">' +
                newSongArtistOptions(n) +
            '</select>' +
        '</div>';
    container.appendChild(row);
    // Auto-add current artist as main
    addNewSongArtist(n, currentArtistId, _currentArtistName(), true);
    validateAddAlbum();
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
        '<span class="text-xs">' + (artistName || '').replace(/</g, '&lt;') + '</span>' +
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

function submitNewAlbum(artistId) {
    var name = document.getElementById('new-album-name').value.trim();
    var date = document.getElementById('new-album-date').value;
    var typeId = parseInt(document.getElementById('new-album-type').value);

    if (!name) { showToast('Album name is required'); return; }

    var genreIds = [];
    document.querySelectorAll('#new-album-genres input:checked').forEach(function(cb) {
        genreIds.push(parseInt(cb.value));
    });

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
        songs.push({
            name: n,
            is_promoted: songDiv.querySelector('.new-song-promoted') ? songDiv.querySelector('.new-song-promoted').checked : false,
            is_remix: songDiv.querySelector('.new-song-remix') ? songDiv.querySelector('.new-song-remix').checked : false,
            artists: artists,
        });
    });

    if (!songs.length) { showToast('Add at least one song'); return; }

    var data = {
        name: name,
        release_date: date,
        album_type_id: typeId,
        genre_ids: genreIds,
        songs: songs,
    };

    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;

    fetch('/edit/artist/' + artistId + '/add-album', {
        method: 'POST',
        headers: headers,
        body: 'data=' + encodeURIComponent(JSON.stringify(data)),
    }).then(function(r) {
        if (!r.ok) throw new Error('save failed');
        return r.json();
    }).then(function() {
        window.location.reload();
    }).catch(function() {
        showToast('Failed to add album — try again');
    });
}

// Validate add-album modal on any input/change inside it
var _addAlbumModal = document.getElementById('add-album-modal');
if (_addAlbumModal) {
    _addAlbumModal.addEventListener('input', validateAddAlbum);
    _addAlbumModal.addEventListener('change', validateAddAlbum);
}

/* Search existing songs for add-album modal */

var _albumSongSearchTimer = null;
function debouncedAlbumSongSearch(artistId) {
    clearTimeout(_albumSongSearchTimer);
    _albumSongSearchTimer = setTimeout(function() { albumSongSearch(artistId); }, 250);
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

function confirmRemoveFromAlbum(songId, albumId, songName, albumName) {
    if (!confirm('Remove "' + songName + '" from "' + albumName + '"?\n\nIf this is the song\'s only album, the song will be deleted.')) return;
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
    fetch('/edit/song/' + songId + '/remove-from-album/' + albumId, {
        method: 'POST',
        headers: headers,
        body: '',
    }).then(function(r) {
        if (!r.ok) throw new Error('failed');
        window.location.reload();
    }).catch(function() {
        showToast('Remove failed — try again');
    });
}

/* Reorder song within album */

function reorderSong(songId, albumId, direction) {
    fetch('/edit/album/' + albumId + '/reorder-song', {
        method: 'POST',
        headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
        body: 'song_id=' + songId + '&direction=' + direction,
    }).then(function(r) {
        if (!r.ok) throw new Error('failed');
        window.location.reload();
    }).catch(function() {
        showToast('Reorder failed — try again');
    });
}

/* Shared delete confirmation modal */

var _deleteIsAjax = false;

var _deleteRedirectUrl = null;

function confirmDeleteAlbum(albumId, albumName) {
    fetch('/edit/album/' + albumId + '/delete-info')
        .then(function(r) {
            if (!r.ok) throw new Error('status ' + r.status);
            return r.json();
        })
        .then(function(data) {
            var msg = albumName + ' will be permanently deleted.';
            if (data.songs_deleted > 0) {
                msg += '\n\n' + data.songs_deleted + ' song' + (data.songs_deleted !== 1 ? 's' : '') +
                       ' and ' + data.ratings_deleted + ' rating' + (data.ratings_deleted !== 1 ? 's' : '') +
                       ' will also be deleted.';
                if (data.songs_deleted < data.songs) {
                    msg += ' ' + (data.songs - data.songs_deleted) + ' song' +
                           (data.songs - data.songs_deleted !== 1 ? 's' : '') +
                           ' on other albums will be kept.';
                }
            } else if (data.songs > 0) {
                msg += '\n\nAll ' + data.songs + ' song' + (data.songs !== 1 ? 's' : '') +
                       ' are on other albums and will be kept.';
            }
            showDeleteConfirm('Delete album?', msg, '/edit/album/' + albumId + '/delete', true);
        })
        .catch(function() {
            showDeleteConfirm('Delete album?', albumName + ' will be permanently deleted.',
                              '/edit/album/' + albumId + '/delete', true);
        });
}

function showDeleteConfirm(title, msg, action, ajax, btnLabel, redirectUrl) {
    _deleteIsAjax = !!ajax;
    _deleteRedirectUrl = redirectUrl || null;
    document.getElementById('confirm-delete-title').textContent = title;
    document.getElementById('confirm-delete-msg').textContent = msg;
    var form = document.getElementById('confirm-delete-form');
    form.action = action;
    // Clean up any leftover merge hidden input
    var prev = form.querySelector('input[name="absorbed_song_id"]');
    if (prev) prev.remove();
    document.getElementById('confirm-delete-pw').value = '';
    document.getElementById('confirm-delete-btn').textContent = btnLabel || 'Delete';
    document.getElementById('confirm-delete-modal').style.display = 'flex';
}

(function() {
    var form = document.getElementById('confirm-delete-form');
    if (!form) return;
    form.addEventListener('submit', function(e) {
        if (!_deleteIsAjax) return; // let normal form submit handle artist delete (redirect)
        e.preventDefault();
        var pw = document.getElementById('confirm-delete-pw').value;
        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
        var body = 'password=' + encodeURIComponent(pw);
        var absorbedInput = form.querySelector('input[name="absorbed_song_id"]');
        if (absorbedInput) body += '&absorbed_song_id=' + absorbedInput.value;
        fetch(form.action, {
            method: 'POST',
            headers: headers,
            body: body,
        }).then(function(r) {
            if (r.status === 403) { alert('Incorrect password'); return; }
            if (!r.ok) throw new Error('failed');
            document.getElementById('confirm-delete-modal').style.display = 'none';
            if (_deleteRedirectUrl) {
                window.location.href = _deleteRedirectUrl;
            } else {
                window.location.reload();
            }
        }).catch(function() {
            showToast('Action failed — try again');
        });
    });
})();

/* Inline rating — spreadsheet-style type-and-go */

let activeInput = null;
let inputGeneration = 0;

function showRatingInput(event, songId, targetUserId) {
    event.stopPropagation();
    closeRatingInput();

    const cell = event.currentTarget;
    const currentValue = cell.textContent.trim();

    // Save original content for cancel
    cell.dataset.original = cell.innerHTML;
    cell.dataset.songId = songId;
    if (targetUserId !== undefined) {
        cell.dataset.targetUserId = targetUserId;
    }

    // Create input
    const input = document.createElement('input');
    input.type = 'text';
    input.inputMode = 'numeric';
    input.maxLength = 1;
    input.value = currentValue;
    input.style.cssText = `
        width: 100%; height: 100%; border: none; outline: 2px solid var(--link, #2563EB);
        text-align: center; font-size: inherit; font-family: inherit;
        background: transparent; padding: 0; margin: 0; box-sizing: border-box;
    `;

    // Clear cell and insert input
    cell.innerHTML = '';
    cell.appendChild(input);
    input.focus();
    input.select();
    const gen = ++inputGeneration;
    activeInput = { input, cell };

    // Key handlers
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === 'ArrowDown' || e.key === 's') {
            e.preventDefault();
            submitAndNavigate(cell, songId, targetUserId, 'down');
        } else if (e.key === 'ArrowUp' || e.key === 'w') {
            e.preventDefault();
            submitAndNavigate(cell, songId, targetUserId, 'up');
        } else if (e.key === 'ArrowRight' || e.key === 'd') {
            e.preventDefault();
            submitAndNavigate(cell, songId, targetUserId, 'right');
        } else if (e.key === 'ArrowLeft' || e.key === 'a') {
            e.preventDefault();
            submitAndNavigate(cell, songId, targetUserId, 'left');
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cancelRating(cell);
        } else if (e.key === 'n') {
            e.preventDefault();
            cancelRating(cell);
            showNoteInput(cell, songId);
        } else if (e.key.length === 1 && !/^[0-5]$/.test(e.key)) {
            // Block non-0-5 characters
            e.preventDefault();
        }
    });

    // Blur = submit (save on click-off)
    input.addEventListener('blur', () => {
        setTimeout(() => {
            if (gen === inputGeneration && activeInput && activeInput.cell === cell) {
                submitAndNavigate(cell, songId, targetUserId, null);
            }
        }, 100);
    });
}

function submitAndNavigate(cell, songId, targetUserId, direction) {
    const val = activeInput ? activeInput.input.value.trim() : '';
    if (val === '') {
        submitRating(cell, songId, null, targetUserId);
    } else if (/^[0-5]$/.test(val)) {
        submitRating(cell, songId, parseInt(val), targetUserId);
    } else {
        cancelRating(cell);
    }
    if (direction) navigateToCell(cell, direction);
}

function submitRating(cell, songId, rating, targetUserId) {
    // Push previous state onto undo stack before mutating
    const originalHTML = cell.dataset.original || cell.innerHTML;
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = originalHTML;
    const prevText = tempDiv.textContent.trim();
    const previousRating = /^[0-5]$/.test(prevText) ? parseInt(prevText) : null;
    const previousNote = cell.getAttribute('title') || cell.getAttribute('data-note') || '';
    const artistSlug = window.location.pathname.replace(/^\/artists\//, '').replace(/\/$/, '');
    if (undoStack.length >= 50) undoStack.shift();
    undoStack.push({ songId, previousRating, previousNote, cellHTML: originalHTML, artistSlug });
    redoStack.length = 0;

    activeInput = null;

    // Immediately restore cell content so re-entry before HTMX swap reads the correct value
    if (rating !== null) {
        cell.textContent = rating;
    } else if (cell.dataset.original) {
        cell.innerHTML = cell.dataset.original;
    } else {
        cell.textContent = '';
    }

    const extraValues = targetUserId !== undefined ? { user_id: targetUserId } : {};

    if (rating === null) {
        // Delete rating
        htmx.ajax('POST', '/rate/delete', {
            target: cell,
            swap: 'outerHTML',
            values: Object.assign({ song_id: songId }, extraValues),
        });
    } else {
        htmx.ajax('POST', '/rate', {
            target: cell,
            swap: 'outerHTML',
            values: Object.assign({ song_id: songId, rating: rating }, extraValues),
        });
    }
}

function cancelRating(cell) {
    if (cell.dataset.original !== undefined) {
        cell.innerHTML = cell.dataset.original;
        delete cell.dataset.original;
        delete cell.dataset.songId;
    }
    activeInput = null;
}

function closeRatingInput() {
    if (activeInput) {
        cancelRating(activeInput.cell);
    }
}

/* Note overlay — right-click or N key to add/edit notes */

let activeNote = null;

function showNoteInput(cell, songId) {
    closeNoteInput();
    closeRatingInput();

    const existingNote = cell.getAttribute('data-note') || '';

    // Get song name from first cell in the same row
    const row = cell.parentElement;
    const songName = row ? row.children[0].textContent.trim() : '';

    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed; z-index: 50; background: var(--bg-secondary, #fff); border: 2px solid var(--link, #2563EB);
        border-radius: 4px; padding: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        width: 240px;
    `;

    // Song name label
    if (songName) {
        const label = document.createElement('div');
        label.textContent = songName;
        label.style.cssText = `
            font-size: 11px; font-weight: 600; color: var(--text-secondary, #6B7280); margin-bottom: 4px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        `;
        overlay.appendChild(label);
    }

    const textarea = document.createElement('textarea');
    textarea.value = existingNote;
    textarea.rows = 3;
    textarea.style.cssText = `
        width: 100%; border: 1px solid var(--border, #ccc); border-radius: 3px; padding: 4px;
        font-size: 13px; font-family: inherit; resize: vertical;
        background: var(--bg-primary, #fff); color: var(--text-primary, #000);
        box-sizing: border-box;
    `;
    textarea.placeholder = 'Add a note...';

    const btnRow = document.createElement('div');
    btnRow.style.cssText = 'display: flex; gap: 4px; margin-top: 4px; justify-content: flex-end;';

    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = `
        padding: 2px 10px; font-size: 12px; background: var(--link, #2563EB);
        color: #fff; border: none; border-radius: 3px; cursor: pointer;
    `;
    saveBtn.onclick = () => submitNote(cell, songId, textarea.value.trim());

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = `
        padding: 2px 10px; font-size: 12px; background: #6B7280;
        color: #fff; border: none; border-radius: 3px; cursor: pointer;
    `;
    cancelBtn.onclick = () => closeNoteInput();

    const deleteBtn = document.createElement('button');
    deleteBtn.textContent = 'Delete';
    deleteBtn.style.cssText = `
        padding: 2px 10px; font-size: 12px; background: var(--delete-button,#DC2626);
        color: #fff; border: none; border-radius: 3px; cursor: pointer;
    `;
    deleteBtn.onclick = () => submitNote(cell, songId, '');

    btnRow.appendChild(deleteBtn);
    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    overlay.appendChild(textarea);
    overlay.appendChild(btnRow);

    // Position: right of cell, top-aligned. Flip left if near right edge.
    const rect = getZoomedRect(cell);
    const overlayWidth = 240;
    const gap = 4;
    overlay.style.top = rect.top + 'px';
    if (rect.right + gap + overlayWidth < window.innerWidth) {
        overlay.style.left = (rect.right + gap) + 'px';
    } else {
        overlay.style.left = (rect.left - gap - overlayWidth) + 'px';
    }

    document.body.appendChild(overlay);
    textarea.focus();
    activeNote = { overlay, cell };

    textarea.addEventListener('keydown', (e) => {
        e.stopPropagation();
        if (e.key === 'Escape') {
            e.preventDefault();
            closeNoteInput();
        } else if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitNote(cell, songId, textarea.value.trim());
        }
        // Shift+Enter: allow default (newline in textarea)
    });
}

function submitNote(cell, songId, noteText) {
    // Capture previous state before closing overlay (title attr holds current note)
    const ratingText = cell.textContent.trim();
    const rating = /^[0-5]$/.test(ratingText) ? parseInt(ratingText) : null;

    // Push previous state onto undo stack
    const previousNote = cell.getAttribute('title') || cell.getAttribute('data-note') || '';
    const artistSlug = window.location.pathname.replace(/^\/artists\//, '').replace(/\/$/, '');
    if (undoStack.length >= 50) undoStack.shift();
    undoStack.push({ songId, previousRating: rating, previousNote, cellHTML: cell.outerHTML, artistSlug });
    redoStack.length = 0;

    closeNoteInput();

    const values = { song_id: songId, note: noteText || '' };
    if (rating !== null) values.rating = rating;
    // Extract user_id from cell ID (format: rating-{songId}-{userId})
    const cellParts = cell.id.split('-');
    if (cellParts.length >= 3) values.user_id = cellParts[2];

    htmx.ajax('POST', '/rate', {
        target: cell,
        swap: 'outerHTML',
        values: values,
    });
}

function closeNoteInput() {
    if (activeNote) {
        activeNote.overlay.remove();
        activeNote = null;
    }
}

// Right-click on rating cells opens note editor
document.addEventListener('contextmenu', (e) => {
    const cell = e.target.closest('td[onclick*="showRatingInput"]');
    if (cell) {
        e.preventDefault();
        const match = cell.getAttribute('onclick').match(/showRatingInput\(event,\s*(\d+)/);
        if (match) {
            showNoteInput(cell, parseInt(match[1]));
        }
    }
});

// Close note overlay on outside click
document.addEventListener('click', (e) => {
    if (activeNote && !activeNote.overlay.contains(e.target)) {
        closeNoteInput();
    }
});

// Note tooltip — event delegation, works for dynamically added cells
(function () {
    const tooltip = document.getElementById('note-tooltip');
    if (!tooltip) return;

    document.addEventListener('mouseover', function (e) {
        const td = e.target.closest('td.has-note');
        if (!td) return;
        const note = td.getAttribute('data-note');
        if (!note) return;
        tooltip.textContent = note;
        const rect = getZoomedRect(td);
        tooltip.style.left = rect.left + rect.width / 2 + 'px';
        tooltip.style.transform = 'translateX(-50%)';
        // Position above cell; if too close to top, show below
        if (rect.top > 40) {
            tooltip.style.top = (rect.top - 4) + 'px';
            tooltip.style.bottom = 'auto';
            tooltip.style.transform += ' translateY(-100%)';
        } else {
            tooltip.style.top = (rect.bottom + 4) + 'px';
            tooltip.style.bottom = 'auto';
        }
        tooltip.style.opacity = '1';
    });

    document.addEventListener('mouseout', function (e) {
        const td = e.target.closest('td.has-note');
        if (!td) return;
        // Only hide if we're leaving the td (not entering a child)
        if (!td.contains(e.relatedTarget)) {
            tooltip.style.opacity = '0';
        }
    });
})();

// Real-time rating sync via SSE — one connection per browser via BroadcastChannel
(function () {
    var channel = (typeof BroadcastChannel !== 'undefined') ? new BroadcastChannel('sse-ratings') : null;

    function handleUpdate(data) {
        var cellId = 'rating-' + data.song_id + '-' + data.user_id;
        var cell = document.getElementById(cellId);
        if (!cell) return;
        fetch('/rate/cell?song_id=' + data.song_id + '&user_id=' + data.user_id)
            .then(function (r) { return r.text(); })
            .then(function (html) {
                cell.outerHTML = html;
                // Force repaint to fix collapsed borders after outerHTML swap
                var row = document.getElementById(cellId);
                if (row) row = row.closest('tr');
                if (row) { row.style.display = 'none'; row.offsetHeight; row.style.display = ''; }
            });
    }

    // Listen for updates from leader tab
    if (channel) {
        channel.addEventListener('message', function (e) {
            if (e.data && e.data.type === 'rating-update') handleUpdate(e.data);
        });
    }

    // Leader election: first tab to set the flag owns the SSE connection
    var isLeader = false;
    try {
        if (!localStorage.getItem('sse-leader')) {
            localStorage.setItem('sse-leader', Date.now());
            isLeader = true;
        }
    } catch (e) {
        isLeader = true; // localStorage unavailable, just connect
    }

    // Take over leadership if current leader is stale (>60s)
    if (!isLeader) {
        try {
            var ts = parseInt(localStorage.getItem('sse-leader'), 10);
            if (Date.now() - ts > 60000) {
                localStorage.setItem('sse-leader', Date.now());
                isLeader = true;
            }
        } catch (e) {
            isLeader = true;
        }
    }

    if (!isLeader) return;

    // Keep leadership timestamp fresh
    var heartbeat = setInterval(function () {
        try { localStorage.setItem('sse-leader', Date.now()); } catch (e) {}
    }, 20000);

    // Relinquish leadership on tab close
    window.addEventListener('beforeunload', function () {
        clearInterval(heartbeat);
        try { localStorage.removeItem('sse-leader'); } catch (e) {}
    });

    var source = new EventSource('/events/ratings');

    source.addEventListener('rating-update', function (e) {
        var data = JSON.parse(e.data);
        handleUpdate(data);
        // Broadcast to other tabs
        if (channel) {
            channel.postMessage({ type: 'rating-update', song_id: data.song_id, user_id: data.user_id });
        }
    });
})();

// Subunit expand/collapse toggle on stats pages
document.addEventListener('click', function (e) {
    const btn = e.target.closest('.expand-btn');
    if (!btn) return;
    e.stopPropagation();
    const artistId = btn.dataset.artistId;
    if (btn.dataset.expanded === 'true') {
        document.querySelectorAll('[data-subunit-for="' + artistId + '"]').forEach(function (row) {
            row.remove();
        });
        btn.dataset.expanded = 'false';
        btn.classList.remove('expanded');
    } else {
        fetch(btn.dataset.url)
            .then(function (r) { return r.text(); })
            .then(function (html) {
                btn.closest('tr').insertAdjacentHTML('afterend', html);
                btn.dataset.expanded = 'true';
                btn.classList.add('expanded');
                var sel = document.getElementById('stat-mode');
                if (sel) switchStatMode(sel.value);
            });
    }
});

function navigateToCell(cell, direction) {
    const row = cell.parentElement;
    const colIndex = Array.from(row.children).indexOf(cell);

    if (direction === 'up' || direction === 'down') {
        let targetRow = direction === 'down' ? row.nextElementSibling : row.previousElementSibling;
        while (targetRow) {
            const targetCell = targetRow.children[colIndex];
            if (targetCell && targetCell.getAttribute('onclick')) {
                targetCell.click();
                return;
            }
            targetRow = direction === 'down' ? targetRow.nextElementSibling : targetRow.previousElementSibling;
        }
    } else {
        // left/right — find adjacent clickable td in same row
        let sibling = direction === 'right' ? cell.nextElementSibling : cell.previousElementSibling;
        while (sibling) {
            if (sibling.getAttribute('onclick')) {
                sibling.click();
                return;
            }
            sibling = direction === 'right' ? sibling.nextElementSibling : sibling.previousElementSibling;
        }
    }
}
