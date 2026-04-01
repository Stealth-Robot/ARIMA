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
        var rect = trigger.getBoundingClientRect();
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
            searchResults.style.display = 'none';
            searchResults.innerHTML = '';
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

/* Hamburger artist menu — toggle, outside-click, Escape */

function toggleArtistMenu() {
    var menu = document.getElementById('artist-menu');
    if (!menu) return;
    menu.style.display = menu.style.display === 'none' ? 'flex' : 'none';
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

    const existingNote = cell.getAttribute('title') || '';

    // Get song name from first cell in the same row
    const row = cell.parentElement;
    const songName = row ? row.children[0].textContent.trim() : '';

    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed; z-index: 50; background: #fff; border: 2px solid var(--link, #2563EB);
        border-radius: 4px; padding: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        width: 240px;
    `;

    // Song name label
    if (songName) {
        const label = document.createElement('div');
        label.textContent = songName;
        label.style.cssText = `
            font-size: 11px; font-weight: 600; color: #6B7280; margin-bottom: 4px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        `;
        overlay.appendChild(label);
    }

    const textarea = document.createElement('textarea');
    textarea.value = existingNote;
    textarea.rows = 3;
    textarea.style.cssText = `
        width: 100%; border: 1px solid #ccc; border-radius: 3px; padding: 4px;
        font-size: 13px; font-family: inherit; resize: vertical; color: #000;
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

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    overlay.appendChild(textarea);
    overlay.appendChild(btnRow);

    // Position: right of cell, top-aligned. Flip left if near right edge.
    const rect = cell.getBoundingClientRect();
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

    if (rating === null) {
        // No rating yet — can't attach a note without a rating
        closeNoteInput();
        return;
    }

    // Push previous state onto undo stack
    const previousNote = cell.getAttribute('title') || cell.getAttribute('data-note') || '';
    const artistSlug = window.location.pathname.replace(/^\/artists\//, '').replace(/\/$/, '');
    if (undoStack.length >= 50) undoStack.shift();
    undoStack.push({ songId, previousRating: rating, previousNote, cellHTML: cell.outerHTML, artistSlug });
    redoStack.length = 0;

    closeNoteInput();

    htmx.ajax('POST', '/rate', {
        target: cell,
        swap: 'outerHTML',
        values: { song_id: songId, rating: rating, note: noteText || '' },
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

// Note tooltip — shows on hover of entire rating cell
(function () {
    const tooltip = document.getElementById('note-tooltip');
    if (!tooltip) return;

    function show(e) {
        const td = e.currentTarget;
        const note = td.getAttribute('data-note');
        if (!note) return;
        tooltip.textContent = note;
        const rect = td.getBoundingClientRect();
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
    }

    function hide() {
        tooltip.style.opacity = '0';
    }

    function attach(root) {
        root.querySelectorAll('td.has-note').forEach(function (td) {
            td.addEventListener('mouseenter', show);
            td.addEventListener('mouseleave', hide);
        });
    }

    attach(document);

    // Re-attach after HTMX swaps
    document.addEventListener('htmx:afterSettle', function (e) {
        attach(e.detail.elt);
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
