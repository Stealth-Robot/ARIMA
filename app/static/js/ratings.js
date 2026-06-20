/* Undo stack — client-side, session-scoped (cleared on page navigation) */

const undoStack = [];
const redoStack = [];

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
    const { songId, userId, previousRating, previousNote, artistSlug } = entry;

    function applyEntry() {
        const cell = userId
            ? document.getElementById('rating-' + songId + '-' + userId)
            : document.querySelector('[id^="rating-' + songId + '-"]');

        if (!cell) {
            showBriefToast(operationName + ' failed \u2014 try refreshing the page');
            return;
        }

        // Capture current cell state and push to the opposite stack
        const currentText = cell.textContent.trim();
        const capturedRating = /^[0-5]$/.test(currentText) ? parseInt(currentText) : null;
        const capturedNote = cell.getAttribute('data-note') || '';
        var _uid = userId || cell.id.replace('rating-' + songId + '-', '');
        if (targetStack.length >= 50) targetStack.shift();
        targetStack.push({ songId, userId: _uid, previousRating: capturedRating, previousNote: capturedNote, cellHTML: cell.outerHTML, artistSlug });
        if (window._updateBacklogCounts) window._updateBacklogCounts(cell, capturedRating, previousRating);

        var undoValues = { song_id: songId };
        if (userId) undoValues.user_id = userId;

        if (previousRating === null) {
            guardedAjax('/rate/delete', {
                target: cell,
                swap: 'outerHTML',
                values: undoValues,
            }, cell, entry.cellHTML);
        } else {
            undoValues.rating = previousRating;
            undoValues.note = previousNote || '';
            guardedAjax('/rate', {
                target: cell,
                swap: 'outerHTML',
                values: undoValues,
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

/* Mobile detection helper */
function _isMobile() {
    return window.innerWidth <= 768;
}

/* Mobile rating modal — score picker + note editor */

let activeMobileModal = null;

function _getSongNameFromRow(cell) {
    var row = cell.parentElement;
    var firstCell = row ? row.children[0] : null;
    if (!firstCell) return '';
    var title = firstCell.getAttribute('title');
    if (title) return title;
    var editSpan = firstCell.querySelector('.edit-inline');
    if (editSpan) return editSpan.textContent.trim();
    var mergeBtn = firstCell.querySelector('[data-song-name]');
    if (mergeBtn) return mergeBtn.dataset.songName;
    for (var i = 0; i < firstCell.childNodes.length; i++) {
        if (firstCell.childNodes[i].nodeType === 3) {
            var t = firstCell.childNodes[i].textContent.trim();
            if (t.length > 1) return t;
        }
    }
    return firstCell.textContent.trim().split('\n')[0].trim();
}

function closeMobileModal() {
    if (activeMobileModal) {
        activeMobileModal.remove();
        activeMobileModal = null;
    }
}

function showMobileRatingModal(cell, songId, targetUserId) {
    closeMobileModal();
    closeRatingInput();
    closeNoteInput();

    var songName = _getSongNameFromRow(cell);
    var currentRating = cell.textContent.trim();
    var currentNote = cell.getAttribute('data-note') || '';

    // Backdrop
    var backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:200; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; padding:1rem;';

    // Modal
    var modal = document.createElement('div');
    modal.style.cssText = 'background:var(--bg-secondary,#fff); border:0.0625rem solid var(--border,#ccc); border-radius:0.5rem; padding:1rem; width:100%; max-width:20rem; box-shadow:0 0.25rem 1rem rgba(0,0,0,0.3);';

    // Song name
    var title = document.createElement('div');
    title.textContent = songName;
    title.style.cssText = 'font-size:0.875rem; font-weight:600; color:var(--text-primary); margin-bottom:0.75rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;';
    modal.appendChild(title);

    // Score label
    var scoreLabel = document.createElement('div');
    scoreLabel.textContent = 'Score';
    scoreLabel.style.cssText = 'font-size:0.75rem; color:var(--text-secondary,#6B7280); margin-bottom:0.375rem;';
    modal.appendChild(scoreLabel);

    // Score buttons row
    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex; gap:0.5rem; margin-bottom:0.875rem;';
    var selectedScore = /^[0-5]$/.test(currentRating) ? currentRating : null;

    function makeScoreBtn(label) {
        var btn = document.createElement('button');
        btn.textContent = label;
        var isSelected = label === selectedScore;
        btn.style.cssText = 'flex:1; padding:0.625rem 0; font-size:1rem; font-weight:600; border:0.125rem solid ' +
            (isSelected ? 'var(--link,#2563EB)' : 'var(--border,#ccc)') + '; border-radius:0.375rem; cursor:pointer; background:' +
            (isSelected ? 'var(--link,#2563EB)' : 'var(--bg-primary,#fff)') + '; color:' +
            (isSelected ? '#fff' : 'var(--text-primary)') + ';';
        btn.onclick = function() {
            selectedScore = label;
            btnRow.querySelectorAll('button').forEach(function(b) {
                var sel = b.textContent === selectedScore;
                b.style.background = sel ? 'var(--link,#2563EB)' : 'var(--bg-primary,#fff)';
                b.style.color = sel ? '#fff' : 'var(--text-primary)';
                b.style.borderColor = sel ? 'var(--link,#2563EB)' : 'var(--border,#ccc)';
            });
        };
        return btn;
    }

    for (var i = 0; i <= 5; i++) {
        btnRow.appendChild(makeScoreBtn(String(i)));
    }
    modal.appendChild(btnRow);

    // Note label
    var noteLabel = document.createElement('div');
    noteLabel.textContent = 'Note';
    noteLabel.style.cssText = 'font-size:0.75rem; color:var(--text-secondary,#6B7280); margin-bottom:0.375rem;';
    modal.appendChild(noteLabel);

    // Note textarea
    var textarea = document.createElement('textarea');
    textarea.value = currentNote;
    textarea.rows = 3;
    textarea.placeholder = 'Add a note...';
    textarea.style.cssText = 'width:100%; border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; padding:0.5rem; font-size:0.875rem; font-family:inherit; resize:vertical; background:var(--bg-primary,#fff); color:var(--text-primary); box-sizing:border-box; margin-bottom:0.875rem;';
    modal.appendChild(textarea);

    // Action buttons
    var actionRow = document.createElement('div');
    actionRow.style.cssText = 'display:flex; gap:0.5rem; justify-content:flex-end;';

    var clearBtn = document.createElement('button');
    clearBtn.textContent = 'Clear';
    clearBtn.style.cssText = 'padding:0.5rem 1rem; font-size:0.875rem; background:var(--delete-button,#DC2626); color:#fff; border:none; border-radius:0.375rem; cursor:pointer;';
    clearBtn.onclick = function() {
        // Push undo state
        var prevText = currentRating;
        var previousRating = /^[0-5]$/.test(prevText) ? parseInt(prevText) : null;
        var previousNote = cell.getAttribute('data-note') || '';
        var artistSlug = window.location.pathname.replace(/^\/artists\//, '').replace(/\/$/, '');
        var _uid = targetUserId !== undefined ? targetUserId : cell.id.replace('rating-' + songId + '-', '');
        if (undoStack.length >= 50) undoStack.shift();
        undoStack.push({ songId: songId, userId: _uid, previousRating: previousRating, previousNote: previousNote, cellHTML: cell.outerHTML, artistSlug: artistSlug });
        redoStack.length = 0;
        if (window._updateBacklogCounts) window._updateBacklogCounts(cell, previousRating, null);

        closeMobileModal();
        var extraValues = targetUserId !== undefined ? { user_id: targetUserId } : {};
        guardedAjax('/rate/delete', {
            target: cell,
            swap: 'outerHTML',
            values: Object.assign({ song_id: songId }, extraValues),
        }, cell, cell.outerHTML);
    };

    var cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'padding:0.5rem 1rem; font-size:0.875rem; background:var(--bg-primary,#fff); color:var(--text-primary); border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; cursor:pointer;';
    cancelBtn.onclick = function() { closeMobileModal(); };

    var saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'padding:0.5rem 1rem; font-size:0.875rem; background:var(--link,#2563EB); color:#fff; border:none; border-radius:0.375rem; cursor:pointer;';
    saveBtn.onclick = function() {
        var newRating = selectedScore !== null ? parseInt(selectedScore) : null;
        var newNote = textarea.value.trim();

        // Push undo state
        var prevText = currentRating;
        var previousRating = /^[0-5]$/.test(prevText) ? parseInt(prevText) : null;
        var previousNote = cell.getAttribute('data-note') || '';
        var artistSlug = window.location.pathname.replace(/^\/artists\//, '').replace(/\/$/, '');
        var _uid = targetUserId !== undefined ? targetUserId : cell.id.replace('rating-' + songId + '-', '');
        if (undoStack.length >= 50) undoStack.shift();
        undoStack.push({ songId: songId, userId: _uid, previousRating: previousRating, previousNote: previousNote, cellHTML: cell.outerHTML, artistSlug: artistSlug });
        redoStack.length = 0;
        if (window._updateBacklogCounts) window._updateBacklogCounts(cell, previousRating, newRating);

        closeMobileModal();

        var extraValues = targetUserId !== undefined ? { user_id: targetUserId } : {};

        if (newRating === null && !newNote) {
            guardedAjax('/rate/delete', {
                target: cell,
                swap: 'outerHTML',
                values: Object.assign({ song_id: songId }, extraValues),
            }, cell, cell.outerHTML);
        } else {
            var values = Object.assign({ song_id: songId, note: newNote || '' }, extraValues);
            if (newRating !== null) values.rating = newRating;
            guardedAjax('/rate', {
                target: cell,
                swap: 'outerHTML',
                values: values,
            }, cell, cell.outerHTML);
        }
    };

    actionRow.appendChild(clearBtn);
    actionRow.appendChild(cancelBtn);
    actionRow.appendChild(saveBtn);
    modal.appendChild(actionRow);

    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    activeMobileModal = backdrop;

    // Close on backdrop click (not modal)
    backdrop.addEventListener('click', function(e) {
        if (e.target === backdrop) closeMobileModal();
    });
}

function showMobileNoteModal(cell) {
    closeMobileModal();
    var note = cell.getAttribute('data-note');
    if (!note) return;

    var songName = _getSongNameFromRow(cell);

    var backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:200; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; padding:1rem;';

    var modal = document.createElement('div');
    modal.style.cssText = 'background:var(--bg-secondary,#fff); border:0.0625rem solid var(--border,#ccc); border-radius:0.5rem; padding:1rem; width:100%; max-width:20rem; box-shadow:0 0.25rem 1rem rgba(0,0,0,0.3);';

    var title = document.createElement('div');
    title.textContent = songName;
    title.style.cssText = 'font-size:0.875rem; font-weight:600; color:var(--text-primary); margin-bottom:0.625rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;';
    modal.appendChild(title);

    var noteDiv = document.createElement('div');
    noteDiv.textContent = note;
    noteDiv.style.cssText = 'font-size:0.875rem; color:var(--text-primary); white-space:pre-wrap; line-height:1.5; max-height:60vh; overflow-y:auto;';
    modal.appendChild(noteDiv);

    var closeBtn = document.createElement('button');
    closeBtn.textContent = 'Close';
    closeBtn.style.cssText = 'margin-top:0.875rem; padding:0.5rem 1rem; font-size:0.875rem; background:var(--bg-primary,#fff); color:var(--text-primary); border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; cursor:pointer; float:right;';
    closeBtn.onclick = function() { closeMobileModal(); };
    modal.appendChild(closeBtn);

    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    activeMobileModal = backdrop;

    backdrop.addEventListener('click', function(e) {
        if (e.target === backdrop) closeMobileModal();
    });
}

// Mobile: tap non-editable rating cells with notes to view them
document.addEventListener('click', function(e) {
    if (!_isMobile()) return;
    var cell = e.target.closest('td.has-note');
    if (!cell) return;
    // Skip if it's an editable cell (those have their own onclick)
    if (cell.getAttribute('onclick')) return;
    // Skip if it's a song-name-cell (those have song-level notes, not rating notes)
    if (cell.classList.contains('song-name-cell')) return;
    showMobileNoteModal(cell);
});

// Mobile: tap song name cell to see full name and note
function _getSongNameFromCell(cell) {
    var title = cell.getAttribute('title');
    if (title) return title;
    var mergeBtn = cell.querySelector('[data-song-name]');
    if (mergeBtn) return mergeBtn.dataset.songName;
    var editSpan = cell.querySelector('.edit-inline');
    if (editSpan) return editSpan.textContent.trim();
    for (var i = 0; i < cell.childNodes.length; i++) {
        if (cell.childNodes[i].nodeType === 3) {
            var t = cell.childNodes[i].textContent.trim();
            if (t.length > 1) return t;
        }
    }
    return cell.textContent.trim();
}

/* Song view/edit — delegates to the shared edit modal (app/static/js/edit_modal.js). */
function showMobileSongInfoModal(cell) {
    return openEditModal(songEditConfig(cell));
}

document.addEventListener('click', function(e) {
    // Mobile: anyone can tap a song name for the info view. Desktop: editors
    // click a song name to open the edit modal (no global edit-mode toggle).
    if (!_isMobile() && !window._canEdit) return;
    var cell = e.target.closest('td.song-name-cell');
    if (!cell) return;
    if (e.target.closest('a') || e.target.closest('button')) return;
    showMobileSongInfoModal(cell);
});

// Clicking an album header opens the album edit modal (editors, any width).
document.addEventListener('click', function(e) {
    if (!window._canEdit) return;
    var cell = e.target.closest('td.album-name-cell');
    if (!cell) return;
    if (e.target.closest('a, button, svg, .collapse-arrow, [title="Copy link to album"]')) return;
    var albumId = parseInt(cell.getAttribute('data-album-id'), 10);
    if (!albumId) return;
    var name = '';
    for (var i = 0; i < cell.childNodes.length; i++) {
        var nd = cell.childNodes[i];
        if (nd.nodeType === 3 && nd.textContent.trim().length > 1) { name = nd.textContent.trim(); break; }
    }
    showMobileAlbumEdit(albumId, name);
});

/* Album view/edit — delegates to the shared edit modal (app/static/js/edit_modal.js). */
function showMobileAlbumEdit(albumId, albumName) {
    return openEditModal(albumEditConfig(albumId, albumName));
}

/* Artist edit — delegates to the shared edit modal (app/static/js/edit_modal.js). */
function showMobileArtistEdit(artistId) {
    return openEditModal(artistEditConfig(artistId));
}

/* Shared mobile bottom-sheet picker — search / single-select / multi-select.
   Stacks above other mobile modals (z-index 300); manages its own lifecycle. */
function showMobilePicker(opts) {
    var backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:300; background:rgba(0,0,0,0.5); display:flex; align-items:flex-end; justify-content:center;';
    var sheet = document.createElement('div');
    sheet.style.cssText = 'background:var(--bg-secondary,#fff); border-top-left-radius:0.75rem; border-top-right-radius:0.75rem; width:100%; max-width:30rem; max-height:80vh; display:flex; flex-direction:column; box-shadow:0 -0.25rem 1rem rgba(0,0,0,0.3);';

    function close() { backdrop.remove(); }
    backdrop.addEventListener('click', function(e) { if (e.target === backdrop) close(); });

    var head = document.createElement('div');
    head.style.cssText = 'padding:0.875rem 1rem 0.5rem; display:flex; align-items:center; gap:0.5rem; flex-shrink:0;';
    var h = document.createElement('div');
    h.textContent = opts.title || '';
    h.style.cssText = 'font-size:0.9375rem; font-weight:600; color:var(--text-primary); flex:1;';
    head.appendChild(h);
    var x = document.createElement('button');
    x.innerHTML = '&#10005;';
    x.style.cssText = 'border:none; background:none; font-size:1.125rem; color:var(--text-secondary,#6B7280); cursor:pointer;';
    x.onclick = close;
    head.appendChild(x);
    sheet.appendChild(head);

    var body = document.createElement('div');
    body.style.cssText = 'padding:0 1rem 1rem; overflow-y:auto; flex:1;';
    sheet.appendChild(body);

    function _rowBtn(label) {
        var b = document.createElement('button');
        b.textContent = label;
        b.style.cssText = 'display:flex; justify-content:space-between; align-items:center; gap:0.5rem; width:100%; text-align:left; padding:0.6875rem 0.375rem; font-size:0.875rem; border:none; border-bottom:0.0625rem solid var(--border,#eee); background:none; color:var(--text-primary); cursor:pointer;';
        return b;
    }

    if (opts.mode === 'search') {
        var input = document.createElement('input');
        input.type = 'text';
        input.placeholder = opts.placeholder || 'Search…';
        input.style.cssText = 'width:100%; border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; padding:0.5625rem; font-size:0.875rem; box-sizing:border-box; background:var(--bg-primary,#fff); color:var(--text-primary); margin-bottom:0.625rem;';
        body.appendChild(input);
        var results = document.createElement('div');
        body.appendChild(results);
        var timer;
        input.addEventListener('input', function() {
            clearTimeout(timer);
            var q = input.value.trim();
            if (q.length < 2) { results.innerHTML = ''; return; }
            timer = setTimeout(function() {
                fetch(opts.searchUrl(q), { headers: { 'Accept': 'application/json' } })
                    .then(function(r) { return r.ok ? r.json() : []; })
                    .then(function(data) {
                        var items = opts.mapItems ? opts.mapItems(data) : data;
                        results.innerHTML = '';
                        if (!items.length) {
                            results.innerHTML = '<div style="font-size:0.8125rem;color:var(--text-secondary,#6B7280);padding:0.5rem 0;">No matches.</div>';
                            return;
                        }
                        items.forEach(function(it) {
                            var row = _rowBtn(it.label);
                            row.onclick = function() { close(); opts.onSelect(it); };
                            results.appendChild(row);
                        });
                    });
            }, 250);
        });
        setTimeout(function() { input.focus(); }, 60);
    } else if (opts.mode === 'multiselect') {
        var selected = {};
        (opts.selectedIds || []).forEach(function(id) { selected[id] = true; });
        opts.options.forEach(function(o) {
            var lab = document.createElement('label');
            lab.style.cssText = 'display:flex; align-items:center; gap:0.625rem; padding:0.5625rem 0.375rem; font-size:0.875rem; border-bottom:0.0625rem solid var(--border,#eee); color:var(--text-primary); cursor:pointer;';
            var cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = !!selected[o.id];
            cb.onchange = function() { if (cb.checked) selected[o.id] = true; else delete selected[o.id]; };
            var sp = document.createElement('span');
            sp.textContent = o.label;
            lab.appendChild(cb);
            lab.appendChild(sp);
            body.appendChild(lab);
        });
        var done = document.createElement('button');
        done.textContent = 'Done';
        done.style.cssText = 'margin-top:0.75rem; width:100%; padding:0.6875rem; font-size:0.875rem; background:var(--link,#2563EB); color:#fff; border:none; border-radius:0.375rem; cursor:pointer;';
        done.onclick = function() { close(); opts.onDone(Object.keys(selected).map(Number)); };
        body.appendChild(done);
    } else { // 'select'
        (opts.options || []).forEach(function(o) {
            var row = _rowBtn(o.label);
            if (o.selected) {
                var chk = document.createElement('span');
                chk.innerHTML = '&#10003;';
                chk.style.color = 'var(--link,#2563EB)';
                row.appendChild(chk);
            }
            row.onclick = function() { close(); opts.onSelect(o); };
            body.appendChild(row);
        });
    }

    backdrop.appendChild(sheet);
    document.body.appendChild(backdrop);
    return { close: close };
}

/* Shared mobile password-confirm — for destructive edits (delete/merge). */
function showMobilePassword(opts) {
    var backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:310; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; padding:1rem;';
    var modal = document.createElement('div');
    modal.style.cssText = 'background:var(--bg-secondary,#fff); border:0.0625rem solid var(--border,#ccc); border-radius:0.5rem; padding:1rem; width:100%; max-width:20rem; box-shadow:0 0.25rem 1rem rgba(0,0,0,0.3);';

    function close() { backdrop.remove(); }

    if (opts.title) {
        var t = document.createElement('div');
        t.textContent = opts.title;
        t.style.cssText = 'font-size:0.9375rem; font-weight:600; color:var(--text-primary); margin-bottom:0.375rem;';
        modal.appendChild(t);
    }
    if (opts.message) {
        var m = document.createElement('div');
        m.textContent = opts.message;
        m.style.cssText = 'font-size:0.8125rem; color:var(--text-secondary,#6B7280); margin-bottom:0.625rem; white-space:pre-line;';
        modal.appendChild(m);
    }

    var checkbox = null;
    if (opts.checkboxLabel) {
        var cbWrap = document.createElement('label');
        cbWrap.style.cssText = 'display:flex; gap:0.5rem; align-items:flex-start; font-size:0.8125rem; color:var(--text-primary); margin-bottom:0.625rem; cursor:pointer;';
        checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.style.cssText = 'margin-top:0.1875rem; flex-shrink:0;';
        var cbText = document.createElement('span');
        cbText.textContent = opts.checkboxLabel;
        cbWrap.appendChild(checkbox);
        cbWrap.appendChild(cbText);
        modal.appendChild(cbWrap);
    }

    var input = document.createElement('input');
    input.type = 'password';
    input.placeholder = 'Password';
    input.autocomplete = 'current-password';
    input.style.cssText = 'width:100%; border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; padding:0.5625rem; font-size:0.875rem; box-sizing:border-box; background:var(--bg-primary,#fff); color:var(--text-primary); margin-bottom:0.375rem;';
    modal.appendChild(input);

    var err = document.createElement('div');
    err.style.cssText = 'font-size:0.75rem; color:var(--delete-button,#DC2626); min-height:1rem; margin-bottom:0.5rem;';
    modal.appendChild(err);

    var row = document.createElement('div');
    row.style.cssText = 'display:flex; gap:0.5rem; justify-content:flex-end;';
    var cancel = document.createElement('button');
    cancel.textContent = 'Cancel';
    cancel.style.cssText = 'padding:0.5rem 1rem; font-size:0.875rem; background:var(--bg-primary,#fff); color:var(--text-primary); border:0.0625rem solid var(--border,#ccc); border-radius:0.375rem; cursor:pointer;';
    cancel.onclick = close;
    var confirm = document.createElement('button');
    confirm.textContent = opts.confirmLabel || 'Confirm';
    confirm.style.cssText = 'padding:0.5rem 1rem; font-size:0.875rem; background:var(--delete-button,#DC2626); color:#fff; border:none; border-radius:0.375rem; cursor:pointer;';
    confirm.onclick = function() {
        if (checkbox && !checkbox.checked) { err.textContent = 'Please tick the box to acknowledge.'; return; }
        if (!input.value) { err.textContent = 'Enter your password.'; return; }
        err.textContent = '';
        opts.onConfirm(input.value, { close: close, error: function(msg) { err.textContent = msg; } });
    };
    row.appendChild(cancel);
    row.appendChild(confirm);
    modal.appendChild(row);

    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    setTimeout(function() { input.focus(); }, 60);
    backdrop.addEventListener('click', function(e) { if (e.target === backdrop) close(); });
}

/* Inline rating — spreadsheet-style type-and-go */

let activeInput = null;
let inputGeneration = 0;

function showRatingInput(event, songId, targetUserId) {
    event.stopPropagation();

    // Skip re-entry if this cell already owns the active input
    if (activeInput && activeInput.cell === event.currentTarget) return;

    // On mobile, use the modal instead of inline input
    if (_isMobile()) {
        showMobileRatingModal(event.currentTarget, songId, targetUserId);
        return;
    }

    closeRatingInput();

    const cell = event.currentTarget;
    highlightRow(cell.closest('tr'), true);
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
        width: 100%; height: 100%; border: none; outline: 0.125rem solid var(--link, #2563EB);
        text-align: center; font-size: inherit; font-family: inherit;
        background: transparent; padding: 0; margin: 0; box-sizing: border-box;
    `;

    // Clear cell and insert input
    cell.innerHTML = '';
    cell.appendChild(input);
    input.focus();
    input.select();
    const gen = ++inputGeneration;
    let submitted = false;
    activeInput = { input, cell, submit: function() { doSubmit(); } };

    function doSubmit() {
        if (submitted) return;
        submitted = true;
        const val = input.value.trim();
        if (val === '') {
            submitRating(cell, songId, null, targetUserId);
        } else if (/^[0-5]$/.test(val)) {
            submitRating(cell, songId, parseInt(val), targetUserId);
        } else {
            cancelRating(cell);
        }
    }

    // Key handlers — navigate (submit first if not already saved)
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === 'ArrowDown' || e.key === 's') {
            e.preventDefault();
            doSubmit();
            navigateToCell(cell, 'down');
        } else if (e.key === 'ArrowUp' || e.key === 'w') {
            e.preventDefault();
            doSubmit();
            navigateToCell(cell, 'up');
        } else if (e.key === 'ArrowRight' || e.key === 'd') {
            e.preventDefault();
            doSubmit();
            navigateToCell(cell, 'right');
        } else if (e.key === 'ArrowLeft' || e.key === 'a') {
            e.preventDefault();
            doSubmit();
            navigateToCell(cell, 'left');
        } else if (e.key === 'Escape') {
            e.preventDefault();
            if (!submitted) cancelRating(cell);
        } else if (e.key === 'n') {
            e.preventDefault();
            if (!submitted) cancelRating(cell);
            showNoteInput(cell, songId);
        } else if (e.key.length === 1 && !/^[0-5]$/.test(e.key)) {
            e.preventDefault();
        }
    });

    // Blur = submit (save on click-off)
    input.addEventListener('blur', () => {
        setTimeout(() => {
            if (gen === inputGeneration && !submitted) {
                doSubmit();
            }
        }, 100);
    });
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
    var _uid = targetUserId !== undefined ? targetUserId : cell.id.replace('rating-' + songId + '-', '');
    undoStack.push({ songId, userId: _uid, previousRating, previousNote, cellHTML: originalHTML, artistSlug });
    redoStack.length = 0;
    if (window._updateBacklogCounts) window._updateBacklogCounts(cell, previousRating, rating);

    activeInput = null;

    // Immediately restore cell content so re-entry before HTMX swap reads the correct value
    if (rating !== null) {
        cell.textContent = rating;
    } else if (cell.dataset.original) {
        cell.innerHTML = cell.dataset.original;
    } else {
        cell.textContent = '';
    }

    // Keep the row's rated/unrated filter state in sync when the user rates their own cell
    if (cell.classList.contains('my-cell')) {
        var _filterRow = cell.closest('tr');
        if (_filterRow && _filterRow.hasAttribute('data-my-rated')) {
            _filterRow.dataset.myRated = rating !== null ? '1' : '0';
        }
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
        activeInput.submit();
    }
}

window.addEventListener('beforeunload', function() {
    if (activeInput) activeInput.submit();
});

/* Note overlay — right-click or N key to add/edit notes */

let activeNote = null;

function showNoteInput(cell, songId) {
    closeNoteInput();
    closeRatingInput();

    const existingNote = cell.getAttribute('data-note') || '';

    // Get song name from first cell in the same row
    const row = cell.parentElement;
    const firstCell = row ? row.children[0] : null;
    const songLink = firstCell ? firstCell.querySelector('a') : null;
    const mergeBtn = firstCell ? firstCell.querySelector('[data-song-name]') : null;
    const songName = songLink ? songLink.textContent.trim() : mergeBtn ? mergeBtn.dataset.songName : (firstCell ? firstCell.childNodes[0].textContent.trim() : '');

    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed; z-index: 50; background: var(--bg-secondary, #fff); border: 0.125rem solid var(--link, #2563EB);
        border-radius: 0.25rem; padding: 0.375rem; box-shadow: 0 0.125rem 0.5rem rgba(0,0,0,0.2);
        width: 15rem;
    `;

    // Song name label
    const label = document.createElement('div');
    label.textContent = songName || 'Note';
    label.style.cssText = `
        font-size: 0.6875rem; font-weight: 600; color: var(--text-secondary, #6B7280); margin-bottom: 0.25rem;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    `;
    overlay.appendChild(label);
    _makeDraggable(overlay, label);

    const textarea = document.createElement('textarea');
    textarea.value = existingNote;
    textarea.rows = 3;
    textarea.style.cssText = `
        width: 100%; border: 0.0625rem solid var(--border, #ccc); border-radius: 0.1875rem; padding: 0.25rem;
        font-size: 0.8125rem; font-family: inherit; resize: vertical;
        background: var(--bg-primary, #fff); color: var(--text-primary, #000);
        box-sizing: border-box;
    `;
    textarea.placeholder = 'Add a note...';

    const btnRow = document.createElement('div');
    btnRow.style.cssText = 'display: flex; gap: 0.25rem; margin-top: 0.25rem; justify-content: flex-end;';

    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = `
        padding: 0.125rem 0.625rem; font-size: 0.75rem; background: var(--link, #2563EB);
        color: #fff; border: none; border-radius: 0.1875rem; cursor: pointer;
    `;
    saveBtn.onclick = () => submitNote(cell, songId, textarea.value.trim());

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = `
        padding: 0.125rem 0.625rem; font-size: 0.75rem; background: #6B7280;
        color: #fff; border: none; border-radius: 0.1875rem; cursor: pointer;
    `;
    cancelBtn.onclick = () => closeNoteInput();

    const deleteBtn = document.createElement('button');
    deleteBtn.textContent = 'Delete';
    deleteBtn.style.cssText = `
        padding: 0.125rem 0.625rem; font-size: 0.75rem; background: var(--delete-button,#DC2626);
        color: #fff; border: none; border-radius: 0.1875rem; cursor: pointer;
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
    if (rect.right + gap + overlayWidth < window.innerWidth) {
        overlay.style.left = (rect.right + gap) + 'px';
    } else {
        overlay.style.left = (rect.left - gap - overlayWidth) + 'px';
    }

    document.body.appendChild(overlay);
    var viewH = window.innerHeight;
    overlay.style.top = Math.max(0, Math.min(rect.top, viewH - overlay.offsetHeight - 35)) + 'px';
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
    });
}

function submitNote(cell, songId, noteText) {
    const ratingText = cell.textContent.trim();
    const rating = /^[0-5]$/.test(ratingText) ? parseInt(ratingText) : null;

    const previousNote = cell.getAttribute('title') || cell.getAttribute('data-note') || '';
    const artistSlug = window.location.pathname.replace(/^\/artists\//, '').replace(/\/$/, '');
    var _uid = cell.id.replace('rating-' + songId + '-', '');
    if (undoStack.length >= 50) undoStack.shift();
    undoStack.push({ songId, userId: _uid, previousRating: rating, previousNote, cellHTML: cell.outerHTML, artistSlug });
    redoStack.length = 0;

    closeNoteInput();

    const values = { song_id: songId, note: noteText || '' };
    if (rating !== null) values.rating = rating;
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

function showTooltip(event, tooltip, closestSelector, attributeName){
    if (_isMobile()) return;
    const td = event.target.closest(closestSelector);
    const note = td?.getAttribute(attributeName);
    if (!note) return;
    tooltip.textContent = note;
    const rect = getZoomedRect(td);
    tooltip.style.left = rect.right + 'px';
    tooltip.style.transform = 'translateX(-100%)';
    if (rect.top > 40) {
        tooltip.style.top = (rect.top - 4) + 'px';
        tooltip.style.bottom = 'auto';
        tooltip.style.transform += ' translateY(-100%)';
    } else {
        tooltip.style.top = (rect.bottom + 4) + 'px';
        tooltip.style.bottom = 'auto';
    }
    tooltip.style.opacity = '1';
    tooltip.style.display = 'block';
}

function hideTooltip(tooltip) {
    if (_tooltipSelecting) return;
    tooltip.style.opacity = '0';
    tooltip.style.display = 'none';
}

/* Note tooltip — event delegation, works for dynamically added cells */
var _tooltipSelecting = false;
(function () {
    const tooltip = document.getElementById('note-tooltip');
    if (!tooltip) return;

    // set up rating cell tooltip event listeners
    document.addEventListener('mouseover', (e) => showTooltip(e, tooltip, 'td.has-note', 'data-note'));
    tooltip.addEventListener('mousedown', function () { _tooltipSelecting = true; });
    document.addEventListener('mouseup', function () { _tooltipSelecting = false; });

    document.addEventListener('mouseout', function (e) {
        const td = e.target.closest('td.has-note');
        if (!td) return;
        if (!td.contains(e.relatedTarget) && e.relatedTarget !== tooltip && !tooltip.contains(e.relatedTarget)) {
            hideTooltip(tooltip);
        }
    });

    // Hide tooltip when mouse leaves the tooltip itself
    tooltip.addEventListener('mouseout', function (e) {
        if (!tooltip.contains(e.relatedTarget) && !e.relatedTarget?.closest('td.has-note') && !e.relatedTarget?.closest('td.song-name-cell.has-song-note') && !e.relatedTarget?.closest('td.album-name-cell.has-album-note')) {
            hideTooltip(tooltip);
        }
    });

    // set up song name cell tooltip event listeners
     document.addEventListener('mouseover', (e) => showTooltip(e, tooltip, 'td.song-name-cell.has-song-note', 'data-song-note'));

     document.addEventListener('mouseout', function (e) {
        const td = e.target.closest('td.song-name-cell.has-song-note');
        if (!td) return;
        if (!td.contains(e.relatedTarget) && e.relatedTarget !== tooltip && !tooltip.contains(e.relatedTarget)) {
            hideTooltip(tooltip);
        }
    });

    // set up album header cell tooltip event listeners
    document.addEventListener('mouseover', (e) => showTooltip(e, tooltip, 'td.album-name-cell.has-album-note', 'data-album-note'));

    document.addEventListener('mouseout', function (e) {
        const td = e.target.closest('td.album-name-cell.has-album-note');
        if (!td) return;
        if (!td.contains(e.relatedTarget) && e.relatedTarget !== tooltip && !tooltip.contains(e.relatedTarget)) {
            hideTooltip(tooltip);
        }
    });

    // Album date hover — show full date when year-only is displayed
    document.addEventListener('mouseover', (e) => showTooltip(e, tooltip, '.album-date-hover', 'data-full-date'));

    document.addEventListener('mouseout', function (e) {
        const el = e.target.closest('.album-date-hover');
        if (!el) return;
        if (!el.contains(e.relatedTarget) && e.relatedTarget !== tooltip && !tooltip.contains(e.relatedTarget)) {
            hideTooltip(tooltip);
        }
    });

    // Hide tooltip on scroll so it doesn't drift from the cell
    window.addEventListener('scroll', function () {
        if (tooltip.style.display !== 'none') {
            _tooltipSelecting = false;
            hideTooltip(tooltip);
        }
    });
})();

/* Real-time sync via polling */
(function () {
    var pollSeq = 0;
    var POLL_INTERVAL = 5000;
    var reloadTimers = {};

    function handleUpdate(data) {
        var cellId = 'rating-' + data.song_id + '-' + data.user_id;
        var cell = document.getElementById(cellId);
        if (!cell) return;
        if (activeInput && activeInput.cell === cell) return;
        fetch('/rate/cell?song_id=' + data.song_id + '&user_id=' + data.user_id)
            .then(function (r) { return r.text(); })
            .then(function (html) {
                cell.outerHTML = html;
                var row = document.getElementById(cellId);
                if (row) row = row.closest('tr');
                if (row && row.style.display !== 'none') { row.style.display = 'none'; row.offsetHeight; row.style.display = ''; }
            });
    }

    function viewingArtistId() {
        var el = document.querySelector('[data-current-artist-id]');
        return el ? parseInt(el.getAttribute('data-current-artist-id'), 10) : null;
    }

    // Collapse bursts (reorders, bulk imports) into a single refresh per key.
    function debounceReload(key, fn) {
        if (reloadTimers[key]) clearTimeout(reloadTimers[key]);
        reloadTimers[key] = setTimeout(function () { delete reloadTimers[key]; fn(); }, 500);
    }

    function handleContentEvent(eventType, data) {
        var viewing = viewingArtistId();
        if (viewing !== null) {
            // Artist discography page — only react to events for this artist.
            if (!data || data.artist_id !== viewing) return;
            if (eventType === 'artist-delete') {
                window.location.href = '/artists';
                return;
            }
            debounceReload('artist-' + viewing, function () {
                if (window.htmx && viewingArtistId() === viewing) {
                    htmx.ajax('GET', '/artists/' + viewing, { target: '#discography', swap: 'innerHTML' });
                }
            });
            return;
        }
        var path = window.location.pathname;
        if (path === '/' && eventType !== 'misc-update') {
            // Home — refresh the edit-driven sections (owned/maintained/backlog).
            debounceReload('home', function () {
                if (window.htmx && document.getElementById('home-live')) {
                    htmx.ajax('GET', '/', { target: '#home-live', swap: 'innerHTML' });
                }
            });
        } else if (path === '/misc' && typeof window._miscRefreshExpanded === 'function') {
            // Misc — re-fetch any expanded country in place.
            debounceReload('misc', window._miscRefreshExpanded);
        }
    }

    function poll() {
        fetch('/events/poll?since=' + pollSeq)
            .then(function (r) { if (!r.ok) return null; return r.json(); })
            .then(function (data) {
                if (!data) return;
                pollSeq = data.seq;
                data.events.forEach(function (e) {
                    if (e.event === 'rating-update') handleUpdate(e.data);
                    else handleContentEvent(e.event, e.data);
                });
            })
            .catch(function () {});
    }

    setInterval(poll, POLL_INTERVAL);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
    poll();
})();
