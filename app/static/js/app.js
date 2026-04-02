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
    const row = checkbox.closest('tr');
    const songNameCell = row ? row.querySelector('td:first-child') : null;
    if (!songNameCell) return;
    if (checkbox.checked) {
        songNameCell.style.backgroundColor = 'var(--promoted-song)';
    } else {
        songNameCell.style.backgroundColor = '';
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
        font-size: inherit; font-family: inherit; padding: 0 2px;
        width: ${Math.max(80, span.offsetWidth)}px;
        background: var(--bg-primary); color: var(--text-primary);
    `;

    span.replaceWith(input);
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
            if (document.activeElement !== input) restore();
        }, 150);
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
        btn.addEventListener('mouseenter', function() { btn.style.background = 'var(--hover-bg, #e5e7eb)'; });
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
});

/* Inline rating — spreadsheet-style type-and-go */

let activeInput = null;

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

    // Blur = cancel
    input.addEventListener('blur', () => {
        // Small delay to allow Enter handler to fire first
        setTimeout(() => {
            if (activeInput && activeInput.cell === cell) {
                cancelRating(cell);
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
        padding: 2px 10px; font-size: 12px; background: #DC2626;
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
