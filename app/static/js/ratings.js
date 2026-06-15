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
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:200; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; padding:16px;';

    // Modal
    var modal = document.createElement('div');
    modal.style.cssText = 'background:var(--bg-secondary,#fff); border:1px solid var(--border,#ccc); border-radius:8px; padding:16px; width:100%; max-width:320px; box-shadow:0 4px 16px rgba(0,0,0,0.3);';

    // Song name
    var title = document.createElement('div');
    title.textContent = songName;
    title.style.cssText = 'font-size:14px; font-weight:600; color:var(--text-primary); margin-bottom:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;';
    modal.appendChild(title);

    // Score label
    var scoreLabel = document.createElement('div');
    scoreLabel.textContent = 'Score';
    scoreLabel.style.cssText = 'font-size:12px; color:var(--text-secondary,#6B7280); margin-bottom:6px;';
    modal.appendChild(scoreLabel);

    // Score buttons row
    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex; gap:8px; margin-bottom:14px;';
    var selectedScore = /^[0-5]$/.test(currentRating) ? currentRating : null;

    function makeScoreBtn(label) {
        var btn = document.createElement('button');
        btn.textContent = label;
        var isSelected = label === selectedScore;
        btn.style.cssText = 'flex:1; padding:10px 0; font-size:16px; font-weight:600; border:2px solid ' +
            (isSelected ? 'var(--link,#2563EB)' : 'var(--border,#ccc)') + '; border-radius:6px; cursor:pointer; background:' +
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
    noteLabel.style.cssText = 'font-size:12px; color:var(--text-secondary,#6B7280); margin-bottom:6px;';
    modal.appendChild(noteLabel);

    // Note textarea
    var textarea = document.createElement('textarea');
    textarea.value = currentNote;
    textarea.rows = 3;
    textarea.placeholder = 'Add a note...';
    textarea.style.cssText = 'width:100%; border:1px solid var(--border,#ccc); border-radius:6px; padding:8px; font-size:14px; font-family:inherit; resize:vertical; background:var(--bg-primary,#fff); color:var(--text-primary); box-sizing:border-box; margin-bottom:14px;';
    modal.appendChild(textarea);

    // Action buttons
    var actionRow = document.createElement('div');
    actionRow.style.cssText = 'display:flex; gap:8px; justify-content:flex-end;';

    var clearBtn = document.createElement('button');
    clearBtn.textContent = 'Clear';
    clearBtn.style.cssText = 'padding:8px 16px; font-size:14px; background:var(--delete-button,#DC2626); color:#fff; border:none; border-radius:6px; cursor:pointer;';
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
    cancelBtn.style.cssText = 'padding:8px 16px; font-size:14px; background:var(--bg-primary,#fff); color:var(--text-primary); border:1px solid var(--border,#ccc); border-radius:6px; cursor:pointer;';
    cancelBtn.onclick = function() { closeMobileModal(); };

    var saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'padding:8px 16px; font-size:14px; background:var(--link,#2563EB); color:#fff; border:none; border-radius:6px; cursor:pointer;';
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
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:200; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; padding:16px;';

    var modal = document.createElement('div');
    modal.style.cssText = 'background:var(--bg-secondary,#fff); border:1px solid var(--border,#ccc); border-radius:8px; padding:16px; width:100%; max-width:320px; box-shadow:0 4px 16px rgba(0,0,0,0.3);';

    var title = document.createElement('div');
    title.textContent = songName;
    title.style.cssText = 'font-size:14px; font-weight:600; color:var(--text-primary); margin-bottom:10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;';
    modal.appendChild(title);

    var noteDiv = document.createElement('div');
    noteDiv.textContent = note;
    noteDiv.style.cssText = 'font-size:14px; color:var(--text-primary); white-space:pre-wrap; line-height:1.5; max-height:60vh; overflow-y:auto;';
    modal.appendChild(noteDiv);

    var closeBtn = document.createElement('button');
    closeBtn.textContent = 'Close';
    closeBtn.style.cssText = 'margin-top:14px; padding:8px 16px; font-size:14px; background:var(--bg-primary,#fff); color:var(--text-primary); border:1px solid var(--border,#ccc); border-radius:6px; cursor:pointer; float:right;';
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

function showMobileSongInfoModal(cell) {
    closeMobileModal();

    var canEdit = !!window._canEdit;   // editor — independent of the (mobile-less) edit mode
    var songId = cell.getAttribute('data-song-id');
    // Album context (discography rows only) for album-scoped actions like remove/split.
    var _row = cell.closest('tr');
    var albumId = _row ? parseInt(_row.getAttribute('data-album-id'), 10) : NaN;
    if (isNaN(albumId)) albumId = null;

    // Known song data — seeded from the cell, enriched once the info endpoint returns.
    var songData = {
        name: _getSongNameFromCell(cell),
        note: cell.getAttribute('data-song-note') || '',
        main_artists: [], featured_artists: [], albums: [], genres: [],
        is_lead: false, is_promoted: false, is_cover: false, is_remix: false,
        spotify_url: '', youtube_url: '',
    };

    var backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:200; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; padding:16px;';

    var modal = document.createElement('div');
    modal.style.cssText = 'background:var(--bg-secondary,#fff); border:1px solid var(--border,#ccc); border-radius:8px; padding:16px; width:100%; max-width:320px; box-shadow:0 4px 16px rgba(0,0,0,0.3);';

    function _fieldRow(label, valueNode) {
        var row = document.createElement('div');
        row.style.cssText = 'margin-bottom:10px;';
        var l = document.createElement('div');
        l.textContent = label;
        l.style.cssText = 'font-size:11px; text-transform:uppercase; letter-spacing:0.03em; color:var(--text-secondary,#6B7280); margin-bottom:2px;';
        row.appendChild(l);
        if (typeof valueNode === 'string') {
            var v = document.createElement('div');
            v.textContent = valueNode;
            v.style.cssText = 'font-size:14px; color:var(--text-primary); white-space:pre-wrap; line-height:1.4; word-wrap:break-word;';
            row.appendChild(v);
        } else {
            row.appendChild(valueNode);
        }
        return row;
    }

    function _btn(label, kind) {
        var b = document.createElement('button');
        b.textContent = label;
        var base = 'padding:8px 16px; font-size:14px; border-radius:6px; cursor:pointer;';
        if (kind === 'primary') b.style.cssText = base + 'background:var(--link,#2563EB); color:#fff; border:none;';
        else if (kind === 'danger') b.style.cssText = base + 'background:var(--delete-button,#DC2626); color:#fff; border:none;';
        else b.style.cssText = base + 'background:var(--bg-primary,#fff); color:var(--text-primary); border:1px solid var(--border,#ccc);';
        return b;
    }

    function renderInfo() {
        modal.innerHTML = '';

        var body = document.createElement('div');
        body.style.cssText = 'max-height:60vh; overflow-y:auto;';
        modal.appendChild(body);

        var nameDiv = document.createElement('div');
        nameDiv.textContent = songData.name;
        nameDiv.style.cssText = 'font-size:16px; font-weight:600; color:var(--text-primary); line-height:1.3; word-wrap:break-word;';
        body.appendChild(_fieldRow('Song', nameDiv));

        var artistsText = (songData.main_artists || []).join(', ');
        if (songData.featured_artists && songData.featured_artists.length) {
            artistsText += (artistsText ? ' ' : '') + 'feat. ' + songData.featured_artists.join(', ');
        }
        if (artistsText) body.appendChild(_fieldRow('Artists', artistsText));

        if (songData.albums && songData.albums.length) {
            var albumWrap = document.createElement('div');
            albumWrap.style.cssText = 'font-size:14px; color:var(--text-primary); line-height:1.4;';
            songData.albums.forEach(function(al) {
                var line = al.name;
                if (al.year) line += ' (' + al.year + ')';
                if (al.genres && al.genres.length) line += ' · ' + al.genres.join(', ');
                var d = document.createElement('div');
                d.textContent = line;
                albumWrap.appendChild(d);
            });
            body.appendChild(_fieldRow(songData.albums.length > 1 ? 'Albums' : 'Album', albumWrap));
        }

        if (songData.genres && songData.genres.length) {
            body.appendChild(_fieldRow('Genres', songData.genres.join(', ')));
        }

        var tags = [];
        if (songData.is_lead) tags.push('Lead');
        if (songData.is_promoted) tags.push('Promoted');
        if (songData.is_cover) tags.push('Cover');
        if (songData.is_remix) tags.push('Remix');
        if (tags.length) body.appendChild(_fieldRow('Tags', tags.join(', ')));

        if (songData.note) body.appendChild(_fieldRow('Note', songData.note));

        if (songData.spotify_url || songData.youtube_url) {
            var links = document.createElement('div');
            links.style.cssText = 'display:flex; gap:14px; font-size:14px;';
            if (songData.spotify_url && songData.spotify_url !== 'n/a') {
                var sp = document.createElement('a');
                sp.href = songData.spotify_url; sp.target = '_blank'; sp.rel = 'noopener';
                sp.textContent = 'Spotify'; sp.style.color = 'var(--link,#2563EB)';
                links.appendChild(sp);
            }
            if (songData.youtube_url) {
                var yt = document.createElement('a');
                yt.href = songData.youtube_url; yt.target = '_blank'; yt.rel = 'noopener';
                yt.textContent = 'YouTube'; yt.style.color = 'var(--link,#2563EB)';
                links.appendChild(yt);
            }
            if (links.children.length) body.appendChild(_fieldRow('Links', links));
        }

        var footer = document.createElement('div');
        footer.style.cssText = 'display:flex; align-items:center; margin-top:14px;';
        if (canEdit && songId) {
            var edit = _btn('Edit', 'secondary');
            edit.onclick = renderEdit;
            footer.appendChild(edit);
        }
        var spacer = document.createElement('div');
        spacer.style.cssText = 'flex:1;';
        footer.appendChild(spacer);
        var closeBtn = _btn('Close', 'secondary');
        closeBtn.onclick = function() { closeMobileModal(); };
        footer.appendChild(closeBtn);
        modal.appendChild(footer);
    }

    function renderEdit() {
        modal.innerHTML = '';

        var nameLabel = document.createElement('div');
        nameLabel.textContent = 'Song Name';
        nameLabel.style.cssText = 'font-size:12px; color:var(--text-secondary,#6B7280); margin-bottom:4px;';
        modal.appendChild(nameLabel);

        var nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.value = songData.name;
        nameInput.style.cssText = 'width:100%; border:1px solid var(--border,#ccc); border-radius:6px; padding:8px; font-size:14px; font-weight:600; font-family:inherit; background:var(--bg-primary,#fff); color:var(--text-primary); box-sizing:border-box; margin-bottom:12px;';
        modal.appendChild(nameInput);

        var noteLabel = document.createElement('div');
        noteLabel.textContent = 'Note';
        noteLabel.style.cssText = 'font-size:12px; color:var(--text-secondary,#6B7280); margin-bottom:6px;';
        modal.appendChild(noteLabel);

        var textarea = document.createElement('textarea');
        textarea.value = songData.note;
        textarea.rows = 3;
        textarea.placeholder = 'Add a note...';
        textarea.style.cssText = 'width:100%; border:1px solid var(--border,#ccc); border-radius:6px; padding:8px; font-size:14px; font-family:inherit; resize:vertical; background:var(--bg-primary,#fff); color:var(--text-primary); box-sizing:border-box; margin-bottom:14px;';
        modal.appendChild(textarea);

        function _urlField(labelText, value, placeholder) {
            var l = document.createElement('div');
            l.textContent = labelText;
            l.style.cssText = 'font-size:12px; color:var(--text-secondary,#6B7280); margin-bottom:4px;';
            modal.appendChild(l);
            var inp = document.createElement('input');
            inp.type = 'url';
            inp.value = value || '';
            inp.placeholder = placeholder;
            inp.style.cssText = 'width:100%; border:1px solid var(--border,#ccc); border-radius:6px; padding:8px; font-size:14px; font-family:inherit; background:var(--bg-primary,#fff); color:var(--text-primary); box-sizing:border-box; margin-bottom:12px;';
            modal.appendChild(inp);
            return inp;
        }
        var spotifyInput = _urlField('Spotify URL', songData.spotify_url, 'https://open.spotify.com/… (or n/a)');
        var youtubeInput = _urlField('YouTube URL', songData.youtube_url, 'https://…');

        var actionRow = document.createElement('div');
        actionRow.style.cssText = 'display:flex; gap:8px; justify-content:flex-end;';

        var clearBtn = _btn('Clear', 'danger');
        clearBtn.onclick = function() {
            var fd = new FormData();
            fd.append('value', '');
            fetch('/edit/song/' + songId + '/note', { method: 'POST', headers: _csrfHeaders({}), body: fd })
                .then(function(r) { return r.text(); })
                .then(function() {
                    songData.note = '';
                    cell.classList.remove('has-song-note');
                    cell.removeAttribute('data-song-note');
                    renderInfo();
                });
        };

        var cancelBtn = _btn('Cancel', 'secondary');
        cancelBtn.onclick = function() { renderInfo(); };

        var saveBtn = _btn('Save', 'primary');
        saveBtn.onclick = function() {
            var newName = nameInput.value.trim();
            var nameChanged = newName && newName !== songData.name;
            var noteVal = textarea.value.trim();

            var namePromise = nameChanged
                ? fetch('/edit/song/' + songId + '/name', { method: 'POST', headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}), body: 'value=' + encodeURIComponent(newName) }).then(function(r) { return r.ok ? r.text() : null; })
                : Promise.resolve(null);

            var noteFd = new FormData();
            noteFd.append('value', noteVal);
            var notePromise = fetch('/edit/song/' + songId + '/note', { method: 'POST', headers: _csrfHeaders({}), body: noteFd }).then(function(r) { return r.text(); });

            function _urlPromise(field, newVal, oldVal) {
                if ((newVal || '') === (oldVal || '')) return Promise.resolve({ changed: false });
                return fetch('/edit/song/' + songId + '/' + field, {
                    method: 'POST',
                    headers: _csrfHeaders({ 'Content-Type': 'application/x-www-form-urlencoded' }),
                    body: 'value=' + encodeURIComponent(newVal),
                }).then(function(r) { return { changed: true, ok: r.ok, value: r.ok ? r.text() : null }; });
            }
            var spotifyPromise = _urlPromise('spotify-url', spotifyInput.value.trim(), songData.spotify_url);
            var youtubePromise = _urlPromise('youtube-url', youtubeInput.value.trim(), songData.youtube_url);

            Promise.all([namePromise, notePromise, spotifyPromise, youtubePromise]).then(function(results) {
                var savedName = results[0];
                var savedNote = results[1] ? results[1].trim() : '';
                if (savedName) {
                    var displayName = savedName.trim();
                    songData.name = displayName;
                    cell.setAttribute('title', displayName);
                    var editSpan = cell.querySelector('.edit-inline');
                    if (editSpan) editSpan.textContent = displayName;
                }
                songData.note = savedNote;
                if (savedNote) {
                    cell.classList.add('has-song-note');
                    cell.setAttribute('data-song-note', savedNote);
                } else {
                    cell.classList.remove('has-song-note');
                    cell.removeAttribute('data-song-note');
                }
                var sp = results[2], yt = results[3];
                var badUrl = (sp.changed && !sp.ok) || (yt.changed && !yt.ok);
                Promise.all([
                    sp.changed && sp.ok ? sp.value : Promise.resolve(null),
                    yt.changed && yt.ok ? yt.value : Promise.resolve(null),
                ]).then(function(urls) {
                    if (sp.changed && sp.ok) songData.spotify_url = urls[0] || '';
                    if (yt.changed && yt.ok) songData.youtube_url = urls[1] || '';
                    if (badUrl && typeof showBriefToast === 'function') showBriefToast('Invalid URL — must start with https://');
                    renderInfo();
                });
            });
        };

        actionRow.appendChild(clearBtn);
        actionRow.appendChild(cancelBtn);
        actionRow.appendChild(saveBtn);
        modal.appendChild(actionRow);

        // --- Song actions ---
        var sep = document.createElement('div');
        sep.style.cssText = 'border-top:1px solid var(--border,#ccc); margin:16px 0 10px;';
        modal.appendChild(sep);

        var actLabel = document.createElement('div');
        actLabel.textContent = 'Actions';
        actLabel.style.cssText = 'font-size:11px; text-transform:uppercase; letter-spacing:0.03em; color:var(--text-secondary,#6B7280); margin-bottom:8px;';
        modal.appendChild(actLabel);

        var actWrap = document.createElement('div');
        actWrap.style.cssText = 'display:flex; flex-wrap:wrap; gap:8px;';
        modal.appendChild(actWrap);

        function _action(label, kind, onclick) {
            var b = _btn(label, kind || 'secondary');
            b.onclick = onclick;
            actWrap.appendChild(b);
        }

        _action('Move to album', 'secondary', function() {
            showMobilePicker({
                title: 'Move to which album?',
                mode: 'search',
                placeholder: 'Search albums…',
                searchUrl: function(q) { return '/misc/search-albums?q=' + encodeURIComponent(q); },
                mapItems: function(data) {
                    return data.map(function(a) {
                        return { id: a.id, label: a.name + (a.release_date ? ' (' + a.release_date.slice(0, 4) + ')' : '') };
                    });
                },
                onSelect: function(item) {
                    fetch('/edit/song/' + songId + '/move-album', {
                        method: 'POST',
                        headers: _csrfHeaders({ 'Content-Type': 'application/x-www-form-urlencoded' }),
                        body: 'album_id=' + item.id,
                    }).then(function(r) {
                        if (r.ok) window.location.reload();
                        else if (typeof showBriefToast === 'function') showBriefToast('Move failed');
                    });
                },
            });
        });

        _action('Add to album', 'secondary', function() {
            showMobilePicker({
                title: 'Add to which album?',
                mode: 'search',
                placeholder: 'Search albums…',
                searchUrl: function(q) { return '/misc/search-albums?q=' + encodeURIComponent(q); },
                mapItems: function(data) {
                    return data.map(function(a) {
                        return { id: a.id, label: a.name + (a.release_date ? ' (' + a.release_date.slice(0, 4) + ')' : '') };
                    });
                },
                onSelect: function(item) {
                    fetch('/edit/song/' + songId + '/add-to-album', {
                        method: 'POST',
                        headers: _csrfHeaders({ 'Content-Type': 'application/x-www-form-urlencoded' }),
                        body: 'album_id=' + item.id,
                    }).then(function(r) {
                        if (r.ok) window.location.reload();
                        else if (typeof showBriefToast === 'function') showBriefToast('Add failed');
                    });
                },
            });
        });

        _action('Manage artists', 'secondary', function() {
            closeMobileModal();
            if (typeof showSongArtists === 'function') {
                showSongArtists({ stopPropagation: function() {} }, parseInt(songId, 10), cell);
            }
        });

        _action('Merge', 'secondary', function() {
            closeMobileModal();
            if (typeof _openMergePopover === 'function') {
                _openMergePopover(parseInt(songId, 10), songData.name, cell);
            }
        });

        if (albumId) {
            _action('Remove from album', 'secondary', function() {
                if (typeof showConfirm === 'function') {
                    showConfirm('Remove from album?', 'Remove "' + songData.name + '" from this album. If it is the only album, the song is deleted.', function() {
                        fetch('/edit/song/' + songId + '/remove-from-album/' + albumId, { method: 'POST', headers: _csrfHeaders({}) })
                            .then(function(r) { if (r.ok) window.location.reload(); else if (typeof showBriefToast === 'function') showBriefToast('Remove failed'); });
                    }, 'Remove');
                }
            });

            _action('Split', 'secondary', function() {
                fetch('/edit/song/' + songId + '/split', {
                    method: 'POST',
                    headers: _csrfHeaders({ 'Content-Type': 'application/x-www-form-urlencoded' }),
                    body: 'album_id=' + albumId,
                }).then(function(r) { if (r.ok) window.location.reload(); else if (typeof showBriefToast === 'function') showBriefToast('Split failed'); });
            });
        }

        _action('Delete', 'danger', function() {
            showMobilePassword({
                title: 'Delete song?',
                message: '"' + songData.name + '" will be permanently deleted. Enter your password to confirm.',
                confirmLabel: 'Delete',
                onConfirm: function(pw, helpers) {
                    fetch('/edit/song/' + songId + '/delete', {
                        method: 'POST',
                        headers: _csrfHeaders({ 'Content-Type': 'application/x-www-form-urlencoded' }),
                        body: 'password=' + encodeURIComponent(pw),
                        redirect: 'manual',
                    }).then(function(r) {
                        if (r.status === 403) { helpers.error('Incorrect password.'); return; }
                        helpers.close();
                        window.location.reload();
                    });
                },
            });
        });
    }

    renderInfo();

    if (songId) {
        fetch('/song/' + songId + '/info', { headers: { 'Accept': 'application/json' } })
            .then(function(r) { return r.ok ? r.json() : null; })
            .then(function(data) {
                if (!data) return;
                songData.name = data.name || songData.name;
                songData.main_artists = data.main_artists || [];
                songData.featured_artists = data.featured_artists || [];
                songData.albums = data.albums || [];
                songData.genres = data.genres || [];
                songData.is_lead = !!data.is_lead;
                songData.is_promoted = !!data.is_promoted;
                songData.is_cover = !!data.is_cover;
                songData.is_remix = !!data.is_remix;
                songData.note = data.note || '';
                songData.spotify_url = data.spotify_url || '';
                songData.youtube_url = data.youtube_url || '';
                // Only re-render if still showing the info view (not mid-edit).
                if (!modal.querySelector('input, textarea')) renderInfo();
            })
            .catch(function() {});
    }

    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    activeMobileModal = backdrop;

    backdrop.addEventListener('click', function(e) {
        if (e.target === backdrop) closeMobileModal();
    });
}

document.addEventListener('click', function(e) {
    if (!_isMobile()) return;
    var cell = e.target.closest('td.song-name-cell');
    if (!cell) return;
    if (e.target.closest('a') || e.target.closest('button')) return;
    showMobileSongInfoModal(cell);
});

// Tapping an album header opens the album edit modal (editors only, mobile).
document.addEventListener('click', function(e) {
    if (!_isMobile() || !window._canEdit) return;
    var cell = e.target.closest('td.album-name-cell');
    if (!cell) return;
    if (e.target.closest('a, button, svg, [title="Copy link to album"]')) return;
    var albumId = parseInt(cell.getAttribute('data-album-id'), 10);
    if (!albumId) return;
    var name = '';
    for (var i = 0; i < cell.childNodes.length; i++) {
        var nd = cell.childNodes[i];
        if (nd.nodeType === 3 && nd.textContent.trim().length > 1) { name = nd.textContent.trim(); break; }
    }
    showMobileAlbumEdit(albumId, name);
});

/* Mobile album-edit modal — reorder songs + toggle promoted/remix/cover */

function showMobileAlbumEdit(albumId, albumName) {
    closeMobileModal();

    var dirty = false;          // reload the page on close if anything changed
    var songs = [];

    var backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:200; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; padding:16px;';

    var modal = document.createElement('div');
    modal.style.cssText = 'background:var(--bg-secondary,#fff); border:1px solid var(--border,#ccc); border-radius:8px; padding:16px; width:100%; max-width:340px; max-height:85vh; display:flex; flex-direction:column; box-shadow:0 4px 16px rgba(0,0,0,0.3);';

    function doClose() {
        if (dirty) { window.location.reload(); }
        else { closeMobileModal(); }
    }

    var albumData = { name: albumName, release_date: '', album_type: '', album_type_id: null, spotify_url: '', genres: [], genre_ids: [] };
    var genreOptions = null;   // cached /lookups/genres
    var typeOptions = null;    // cached /lookups/album-types

    var title = document.createElement('div');
    title.textContent = albumName;
    title.style.cssText = 'font-size:16px; font-weight:600; color:var(--text-primary); margin-bottom:12px; word-wrap:break-word;';
    modal.appendChild(title);

    var bodyArea = document.createElement('div');
    bodyArea.style.cssText = 'overflow-y:auto; flex:1;';
    modal.appendChild(bodyArea);

    var loading = document.createElement('div');
    loading.textContent = 'Loading…';
    loading.style.cssText = 'font-size:13px; color:var(--text-secondary,#6B7280);';
    bodyArea.appendChild(loading);

    var footerArea = document.createElement('div');
    footerArea.style.cssText = 'margin-top:14px; flex-shrink:0;';
    modal.appendChild(footerArea);

    function _btnEl(label, kind) {
        var b = document.createElement('button');
        b.textContent = label;
        var base = 'padding:8px 16px; font-size:14px; border-radius:6px; cursor:pointer;';
        if (kind === 'primary') b.style.cssText = base + 'background:var(--link,#2563EB); color:#fff; border:none;';
        else if (kind === 'danger') b.style.cssText = base + 'background:var(--delete-button,#DC2626); color:#fff; border:none;';
        else b.style.cssText = base + 'background:var(--bg-primary,#fff); color:var(--text-primary); border:1px solid var(--border,#ccc);';
        return b;
    }

    function _editHeaders() {
        return _csrfHeaders({ 'Content-Type': 'application/x-www-form-urlencoded', 'X-Edit-Source': 'mobile' });
    }

    function _toast(msg) {
        if (typeof showBriefToast === 'function') showBriefToast(msg);
    }

    function reorder(idx, dir) {
        var cur = songs[idx];
        var target = dir === 'up' ? songs[idx - 1] : songs[idx + 1];
        if (!cur || !target) return;
        fetch('/edit/album/' + albumId + '/move-song', {
            method: 'POST',
            headers: _editHeaders(),
            body: 'song_id=' + cur.id + '&target_song_id=' + target.id + '&direction=' + (dir === 'up' ? 'before' : 'after'),
        }).then(function(r) {
            if (!r.ok) throw new Error('failed');
            dirty = true;
            // reflect locally: swap and re-render without another round-trip
            songs.splice(idx, 1);
            songs.splice(dir === 'up' ? idx - 1 : idx + 1, 0, cur);
            render();
        }).catch(function() { _toast('Reorder failed — try again'); });
    }

    function toggleFlag(song, field, checkbox) {
        fetch('/edit/song/' + song.id + '/is-' + field, {
            method: 'POST',
            headers: _editHeaders(),
            body: 'checked=' + (checkbox.checked ? 'true' : ''),
        }).then(function(r) {
            if (!r.ok) throw new Error('failed');
            dirty = true;
            song['is_' + field] = checkbox.checked;
            // promoted off clears lead server-side; re-render so the star updates
            if (field === 'promoted' && !checkbox.checked) { song.is_lead = false; render(); }
        }).catch(function() {
            checkbox.checked = !checkbox.checked;
            _toast('Failed to save — try again');
        });
    }

    function toggleLead(song) {
        // is-lead is a server-side toggle that also sets promoted on / lead off
        fetch('/edit/song/' + song.id + '/is-lead', { method: 'POST', headers: _editHeaders() })
            .then(function(r) { if (!r.ok) throw new Error('failed'); return r.json(); })
            .then(function(d) {
                dirty = true;
                song.is_lead = d.is_lead;
                song.is_promoted = d.is_promoted;
                render();
            })
            .catch(function() { _toast('Failed to save — try again'); });
    }

    function _leadStar(song) {
        var star = document.createElement('span');
        star.textContent = '★';
        star.title = 'Lead track';
        star.setAttribute('role', 'checkbox');
        star.setAttribute('aria-checked', song.is_lead ? 'true' : 'false');
        star.style.cssText = 'cursor:pointer; font-size:19px; line-height:1; padding:2px 4px; color:' + (song.is_lead ? 'var(--lead-song,#f5a623)' : '#888') + ';';
        star.onclick = function() { toggleLead(song); };
        return star;
    }

    function _chevron(glyph, enabled, onclick) {
        var b = document.createElement('button');
        b.innerHTML = glyph;
        b.disabled = !enabled;
        b.style.cssText = 'width:28px; height:24px; line-height:1; font-size:12px; border:1px solid var(--border,#ccc); border-radius:4px; background:var(--bg-primary,#fff); color:var(--text-primary); cursor:' + (enabled ? 'pointer' : 'default') + '; opacity:' + (enabled ? '1' : '0.35') + ';';
        if (enabled) b.onclick = onclick;
        return b;
    }

    function _flagToggle(song, label, field) {
        var wrap = document.createElement('label');
        wrap.style.cssText = 'display:inline-flex; align-items:center; gap:4px; font-size:12px; color:var(--text-primary); cursor:pointer;';
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = !!song['is_' + field];
        cb.style.cssText = 'cursor:pointer;';
        cb.onchange = function() { toggleFlag(song, field, cb); };
        var txt = document.createElement('span');
        txt.textContent = label;
        wrap.appendChild(cb);
        wrap.appendChild(txt);
        return wrap;
    }

    var songListContainer = null;   // set while the editable song list is mounted (edit view)
    function render() {
        // Re-render the editable song list in place if it's mounted; never leave the edit view.
        if (songListContainer && document.body.contains(songListContainer)) renderSongList(songListContainer);
    }

    function renderSongList(container) {
        container.innerHTML = '';
        if (!songs.length) {
            var empty = document.createElement('div');
            empty.textContent = 'No songs in this album.';
            empty.style.cssText = 'font-size:13px; color:var(--text-secondary,#6B7280);';
            container.appendChild(empty);
            return;
        }
        songs.forEach(function(song, i) {
            var card = document.createElement('div');
            card.style.cssText = 'border:1px solid var(--border,#ccc); border-radius:6px; padding:8px; margin-bottom:8px;';

            var top = document.createElement('div');
            top.style.cssText = 'display:flex; align-items:center; gap:6px;';

            var reorderBox = document.createElement('div');
            reorderBox.style.cssText = 'display:flex; gap:3px; flex-shrink:0;';
            reorderBox.appendChild(_chevron('&#9650;', i > 0, function() { reorder(i, 'up'); }));
            reorderBox.appendChild(_chevron('&#9660;', i < songs.length - 1, function() { reorder(i, 'down'); }));
            top.appendChild(reorderBox);

            var name = document.createElement('div');
            name.textContent = song.name;
            name.style.cssText = 'flex:1; font-size:14px; font-weight:500; color:var(--text-primary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
            top.appendChild(name);
            card.appendChild(top);

            var flags = document.createElement('div');
            flags.style.cssText = 'display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-top:8px; padding-left:2px;';
            flags.appendChild(_leadStar(song));
            var flagGroup = document.createElement('div');
            flagGroup.style.cssText = 'display:flex; flex-wrap:wrap; align-items:center; gap:12px;';
            flagGroup.appendChild(_flagToggle(song, 'Promoted', 'promoted'));
            flagGroup.appendChild(_flagToggle(song, 'Remix', 'remix'));
            flagGroup.appendChild(_flagToggle(song, 'Cover', 'cover'));
            flags.appendChild(flagGroup);
            card.appendChild(flags);

            container.appendChild(card);
        });
    }

    function renderInfo() {
        title.textContent = albumData.name;
        bodyArea.innerHTML = '';
        songListContainer = null;

        var metaBits = [];
        if (albumData.release_date) metaBits.push(albumData.release_date.slice(0, 4));
        if (albumData.album_type) metaBits.push(albumData.album_type);
        if (albumData.genres.length) metaBits.push(albumData.genres.join(', '));
        if (metaBits.length) {
            var meta = document.createElement('div');
            meta.textContent = metaBits.join(' · ');
            meta.style.cssText = 'font-size:12px; color:var(--text-secondary,#6B7280); margin-bottom:10px;';
            bodyArea.appendChild(meta);
        }

        if (songs.length) {
            var listWrap = document.createElement('div');
            songs.forEach(function(song, i) {
                var row = document.createElement('div');
                row.style.cssText = 'display:flex; gap:8px; font-size:14px; color:var(--text-primary); padding:3px 0; align-items:baseline;';
                var num = document.createElement('span');
                num.textContent = (i + 1) + '.';
                num.style.cssText = 'color:var(--text-secondary,#6B7280); font-size:12px; flex-shrink:0; min-width:18px;';
                var tags = [];
                if (song.is_lead) tags.push('★ lead');
                if (song.is_promoted) tags.push('promoted');
                if (song.is_remix) tags.push('remix');
                if (song.is_cover) tags.push('cover');
                var nm = document.createElement('span');
                nm.textContent = song.name + (tags.length ? '  (' + tags.join(', ') + ')' : '');
                row.appendChild(num);
                row.appendChild(nm);
                listWrap.appendChild(row);
            });
            bodyArea.appendChild(listWrap);
        }

        footerArea.innerHTML = '';
        var f = document.createElement('div');
        f.style.cssText = 'display:flex; align-items:center;';
        var editBtn = _btnEl('Edit', 'secondary');
        editBtn.onclick = renderEdit;
        f.appendChild(editBtn);
        var sp = document.createElement('div');
        sp.style.cssText = 'flex:1;';
        f.appendChild(sp);
        var closeBtn = _btnEl('Close', 'secondary');
        closeBtn.onclick = doClose;
        f.appendChild(closeBtn);
        footerArea.appendChild(f);
    }

    function renderEdit() {
        title.textContent = albumData.name;
        bodyArea.innerHTML = '';
        footerArea.innerHTML = '';

        function _field(labelText, value, placeholder) {
            var l = document.createElement('div');
            l.textContent = labelText;
            l.style.cssText = 'font-size:12px; color:var(--text-secondary,#6B7280); margin-bottom:4px;';
            bodyArea.appendChild(l);
            var inp = document.createElement('input');
            inp.type = 'text';
            inp.value = value || '';
            if (placeholder) inp.placeholder = placeholder;
            inp.style.cssText = 'width:100%; border:1px solid var(--border,#ccc); border-radius:6px; padding:8px; font-size:14px; font-family:inherit; background:var(--bg-primary,#fff); color:var(--text-primary); box-sizing:border-box; margin-bottom:12px;';
            bodyArea.appendChild(inp);
            return inp;
        }
        var nameInput = _field('Album Name', albumData.name);
        var dateInput = _field('Release Date', albumData.release_date, 'YYYY-MM-DD');
        var spotifyInput = _field('Spotify URL', albumData.spotify_url, 'https://open.spotify.com/…');

        var saveRow = document.createElement('div');
        saveRow.style.cssText = 'display:flex; gap:8px; justify-content:flex-end; margin-bottom:6px;';
        var cancelBtn = _btnEl('Cancel', 'secondary');
        cancelBtn.onclick = renderInfo;
        var saveBtn = _btnEl('Save', 'primary');
        saveBtn.onclick = function() {
            var promises = [];
            if (nameInput.value.trim() && nameInput.value.trim() !== albumData.name) {
                promises.push(fetch('/edit/album/' + albumId + '/name', { method: 'POST', headers: _editHeaders(), body: 'value=' + encodeURIComponent(nameInput.value.trim()) })
                    .then(function(r) { if (r.ok) { albumData.name = nameInput.value.trim(); dirty = true; } }));
            }
            if (dateInput.value.trim() !== albumData.release_date) {
                promises.push(fetch('/edit/album/' + albumId + '/release-date', { method: 'POST', headers: _editHeaders(), body: 'value=' + encodeURIComponent(dateInput.value.trim()) })
                    .then(function(r) { if (r.ok) { albumData.release_date = dateInput.value.trim(); dirty = true; } else _toast('Invalid date'); }));
            }
            if (spotifyInput.value.trim() !== albumData.spotify_url) {
                promises.push(fetch('/edit/album/' + albumId + '/spotify-url', { method: 'POST', headers: _editHeaders(), body: 'value=' + encodeURIComponent(spotifyInput.value.trim()) })
                    .then(function(r) { if (r.ok) { albumData.spotify_url = spotifyInput.value.trim(); dirty = true; } else _toast('Invalid URL'); }));
            }
            Promise.all(promises).then(renderInfo);
        };
        saveRow.appendChild(cancelBtn);
        saveRow.appendChild(saveBtn);
        bodyArea.appendChild(saveRow);

        // Songs: reorder + flag toggles
        if (songs.length) {
            var songsSep = document.createElement('div');
            songsSep.style.cssText = 'border-top:1px solid var(--border,#ccc); margin:14px 0 10px;';
            bodyArea.appendChild(songsSep);
            var songsLabel = document.createElement('div');
            songsLabel.textContent = 'Songs';
            songsLabel.style.cssText = 'font-size:11px; text-transform:uppercase; letter-spacing:0.03em; color:var(--text-secondary,#6B7280); margin-bottom:8px;';
            bodyArea.appendChild(songsLabel);
            var songsWrap = document.createElement('div');
            bodyArea.appendChild(songsWrap);
            songListContainer = songsWrap;
            renderSongList(songsWrap);
        }

        var sep = document.createElement('div');
        sep.style.cssText = 'border-top:1px solid var(--border,#ccc); margin:14px 0 10px;';
        bodyArea.appendChild(sep);
        var actLabel = document.createElement('div');
        actLabel.textContent = 'Actions';
        actLabel.style.cssText = 'font-size:11px; text-transform:uppercase; letter-spacing:0.03em; color:var(--text-secondary,#6B7280); margin-bottom:8px;';
        bodyArea.appendChild(actLabel);
        var actWrap = document.createElement('div');
        actWrap.style.cssText = 'display:flex; flex-wrap:wrap; gap:8px;';
        bodyArea.appendChild(actWrap);
        function _act(label, kind, fn) { var b = _btnEl(label, kind || 'secondary'); b.onclick = fn; actWrap.appendChild(b); }

        _act('Edit genres', 'secondary', function() {
            _ensure(genreOptions, '/lookups/genres', function(opts) {
                genreOptions = opts;
                showMobilePicker({
                    title: 'Album genres', mode: 'multiselect',
                    options: opts.map(function(g) { return { id: g.id, label: g.name }; }),
                    selectedIds: albumData.genre_ids,
                    onDone: function(ids) {
                        fetch('/edit/album/' + albumId + '/genres', { method: 'POST', headers: _editHeaders(), body: 'genre_ids=' + ids.join(',') })
                            .then(function(r) { return r.ok ? r.json() : null; })
                            .then(function(names) {
                                if (names) { albumData.genres = names; albumData.genre_ids = ids; dirty = true; }
                            });
                    },
                });
            });
        });

        _act('Edit type', 'secondary', function() {
            _ensure(typeOptions, '/lookups/album-types', function(opts) {
                typeOptions = opts;
                showMobilePicker({
                    title: 'Album type', mode: 'select',
                    options: opts.map(function(t) { return { id: t.id, label: t.name, selected: t.id === albumData.album_type_id }; }),
                    onSelect: function(o) {
                        fetch('/edit/album/' + albumId + '/type', { method: 'POST', headers: _editHeaders(), body: 'album_type_id=' + o.id })
                            .then(function(r) { if (r.ok) { albumData.album_type = o.label; albumData.album_type_id = o.id; dirty = true; } });
                    },
                });
            });
        });

        _act('Add song', 'secondary', function() {
            showMobilePicker({
                title: 'Add which song?', mode: 'search', placeholder: 'Search songs…',
                searchUrl: function(q) { return '/edit/album/' + albumId + '/search-songs?q=' + encodeURIComponent(q); },
                mapItems: function(data) { return data.map(function(s) { return { id: s.id, label: s.name + ' — ' + s.artist }; }); },
                onSelect: function(item) {
                    fetch('/edit/album/' + albumId + '/add-song', { method: 'POST', headers: _editHeaders(), body: 'song_id=' + item.id })
                        .then(function(r) { if (r.ok) window.location.reload(); else _toast('Add failed'); });
                },
            });
        });

        _act('Move songs to artist', 'secondary', function() {
            var srcEl = document.querySelector('[data-current-artist-id]');
            var sourceId = srcEl ? srcEl.getAttribute('data-current-artist-id') : null;
            if (!sourceId) { _toast('Could not determine current artist'); return; }
            showMobilePicker({
                title: 'Move all songs to…', mode: 'search', placeholder: 'Search artists…',
                searchUrl: function(q) { return '/misc/search-real-artists?q=' + encodeURIComponent(q); },
                mapItems: function(data) { return data.map(function(a) { return { id: a.artist_id, label: a.name }; }); },
                onSelect: function(item) {
                    fetch('/edit/album/' + albumId + '/move-artist', { method: 'POST', headers: _editHeaders(), body: 'source_artist_id=' + sourceId + '&target_artist_id=' + item.id })
                        .then(function(r) { if (r.ok) window.location.reload(); else _toast('Move failed'); });
                },
            });
        });

        _act('Delete album', 'danger', function() {
            showMobilePassword({
                title: 'Delete album?',
                message: '"' + albumData.name + '" and its songs/ratings may be permanently deleted. Enter your password to confirm.',
                confirmLabel: 'Delete',
                onConfirm: function(pw, helpers) {
                    fetch('/edit/album/' + albumId + '/delete', { method: 'POST', headers: _editHeaders(), body: 'password=' + encodeURIComponent(pw), redirect: 'manual' })
                        .then(function(r) {
                            if (r.status === 403) { helpers.error('Incorrect password.'); return; }
                            helpers.close();
                            window.location.reload();
                        });
                },
            });
        });
    }

    function _ensure(cache, url, cb) {
        if (cache) { cb(cache); return; }
        fetch(url, { headers: { 'Accept': 'application/json' } })
            .then(function(r) { return r.ok ? r.json() : []; })
            .then(cb);
    }

    fetch('/album/' + albumId + '/songs', { headers: { 'Accept': 'application/json' } })
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(data) {
            if (!data) { loading.textContent = 'Failed to load.'; return; }
            albumData.name = data.album_name || albumData.name;
            albumData.release_date = data.release_date || '';
            albumData.album_type = data.album_type || '';
            albumData.album_type_id = data.album_type_id || null;
            albumData.spotify_url = data.spotify_url || '';
            albumData.genres = data.genres || [];
            albumData.genre_ids = data.genre_ids || [];
            songs = data.songs || [];
            renderInfo();
        })
        .catch(function() { loading.textContent = 'Failed to load.'; });

    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    activeMobileModal = backdrop;

    backdrop.addEventListener('click', function(e) {
        if (e.target === backdrop) doClose();
    });
}

/* Mobile artist-edit modal — view + edit, mirrors the song/album modals. */
function showMobileArtistEdit(artistId) {
    closeMobileModal();

    var dirty = false;
    var data = { name: '', spotify_url: '', gender_id: null, gender: '', country_id: null, country: '',
        owner_id: null, owner: '', maintainer_id: null, maintainer: '',
        is_disbanded: false, is_complete: false, is_tracked: false };
    var genderOpts = null, countryOpts = null, userOpts = null;

    var backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:200; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; padding:16px;';
    var modal = document.createElement('div');
    modal.style.cssText = 'background:var(--bg-secondary,#fff); border:1px solid var(--border,#ccc); border-radius:8px; padding:16px; width:100%; max-width:340px; max-height:85vh; display:flex; flex-direction:column; box-shadow:0 4px 16px rgba(0,0,0,0.3);';

    function doClose() { if (dirty) window.location.reload(); else closeMobileModal(); }
    function _editHeaders() { return _csrfHeaders({ 'Content-Type': 'application/x-www-form-urlencoded', 'X-Edit-Source': 'mobile' }); }
    function _toast(m) { if (typeof showBriefToast === 'function') showBriefToast(m); }
    function _ensure(cache, url, cb) {
        if (cache) { cb(cache); return; }
        fetch(url, { headers: { 'Accept': 'application/json' } }).then(function(r) { return r.ok ? r.json() : []; }).then(cb);
    }
    function _btnEl(label, kind) {
        var b = document.createElement('button');
        b.textContent = label;
        var base = 'padding:8px 16px; font-size:14px; border-radius:6px; cursor:pointer;';
        if (kind === 'primary') b.style.cssText = base + 'background:var(--link,#2563EB); color:#fff; border:none;';
        else if (kind === 'danger') b.style.cssText = base + 'background:var(--delete-button,#DC2626); color:#fff; border:none;';
        else b.style.cssText = base + 'background:var(--bg-primary,#fff); color:var(--text-primary); border:1px solid var(--border,#ccc);';
        return b;
    }

    var title = document.createElement('div');
    title.style.cssText = 'font-size:16px; font-weight:600; color:var(--text-primary); margin-bottom:12px; word-wrap:break-word;';
    modal.appendChild(title);
    var bodyArea = document.createElement('div');
    bodyArea.style.cssText = 'overflow-y:auto; flex:1;';
    bodyArea.textContent = 'Loading…';
    modal.appendChild(bodyArea);
    var footerArea = document.createElement('div');
    footerArea.style.cssText = 'margin-top:14px; flex-shrink:0;';
    modal.appendChild(footerArea);

    function _infoRow(label, value) {
        var row = document.createElement('div');
        row.style.cssText = 'margin-bottom:8px;';
        var l = document.createElement('div');
        l.textContent = label;
        l.style.cssText = 'font-size:11px; text-transform:uppercase; letter-spacing:0.03em; color:var(--text-secondary,#6B7280);';
        var v = document.createElement('div');
        v.textContent = value || '—';
        v.style.cssText = 'font-size:14px; color:var(--text-primary);';
        row.appendChild(l); row.appendChild(v);
        return row;
    }

    function renderInfo() {
        title.textContent = data.name;
        bodyArea.innerHTML = '';
        bodyArea.appendChild(_infoRow('Gender', data.gender));
        bodyArea.appendChild(_infoRow('Country', data.country));
        bodyArea.appendChild(_infoRow('Owner', data.owner));
        bodyArea.appendChild(_infoRow('Maintainer', data.maintainer));
        var flags = [];
        if (data.is_disbanded) flags.push('Inactive');
        if (data.is_complete) flags.push('Complete');
        if (data.is_tracked) flags.push('Tracked');
        if (flags.length) bodyArea.appendChild(_infoRow('Status', flags.join(', ')));

        footerArea.innerHTML = '';
        var f = document.createElement('div');
        f.style.cssText = 'display:flex; align-items:center;';
        var editBtn = _btnEl('Edit', 'secondary');
        editBtn.onclick = renderEdit;
        f.appendChild(editBtn);
        var sp = document.createElement('div'); sp.style.cssText = 'flex:1;'; f.appendChild(sp);
        var closeBtn = _btnEl('Close', 'secondary');
        closeBtn.onclick = doClose;
        f.appendChild(closeBtn);
        footerArea.appendChild(f);
    }

    function renderEdit() {
        title.textContent = data.name;
        bodyArea.innerHTML = '';
        footerArea.innerHTML = '';

        function _field(labelText, value, placeholder) {
            var l = document.createElement('div');
            l.textContent = labelText;
            l.style.cssText = 'font-size:12px; color:var(--text-secondary,#6B7280); margin-bottom:4px;';
            bodyArea.appendChild(l);
            var inp = document.createElement('input');
            inp.type = 'text'; inp.value = value || '';
            if (placeholder) inp.placeholder = placeholder;
            inp.style.cssText = 'width:100%; border:1px solid var(--border,#ccc); border-radius:6px; padding:8px; font-size:14px; font-family:inherit; background:var(--bg-primary,#fff); color:var(--text-primary); box-sizing:border-box; margin-bottom:12px;';
            bodyArea.appendChild(inp);
            return inp;
        }
        var nameInput = _field('Artist Name', data.name);
        var spotifyInput = _field('Spotify URL', data.spotify_url, 'https://open.spotify.com/…');

        var saveRow = document.createElement('div');
        saveRow.style.cssText = 'display:flex; gap:8px; justify-content:flex-end; margin-bottom:10px;';
        var cancelBtn = _btnEl('Cancel', 'secondary'); cancelBtn.onclick = renderInfo;
        var saveBtn = _btnEl('Save', 'primary');
        saveBtn.onclick = function() {
            var promises = [];
            if (nameInput.value.trim() && nameInput.value.trim() !== data.name) {
                promises.push(fetch('/edit/artist/' + artistId + '/name', { method: 'POST', headers: _editHeaders(), body: 'value=' + encodeURIComponent(nameInput.value.trim()) })
                    .then(function(r) { if (r.ok) { data.name = nameInput.value.trim(); dirty = true; } }));
            }
            if (spotifyInput.value.trim() !== data.spotify_url) {
                promises.push(fetch('/edit/artist/' + artistId + '/spotify-url', { method: 'POST', headers: _editHeaders(), body: 'value=' + encodeURIComponent(spotifyInput.value.trim()) })
                    .then(function(r) { if (r.ok) { data.spotify_url = spotifyInput.value.trim(); dirty = true; } else _toast('Invalid URL'); }));
            }
            Promise.all(promises).then(renderInfo);
        };
        saveRow.appendChild(cancelBtn); saveRow.appendChild(saveBtn);
        bodyArea.appendChild(saveRow);

        // status toggles
        function _toggle(labelText, field, endpoint) {
            var lab = document.createElement('label');
            lab.style.cssText = 'display:flex; align-items:center; gap:8px; font-size:14px; color:var(--text-primary); margin-bottom:8px; cursor:pointer;';
            var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!data[field]; cb.style.cssText = 'cursor:pointer;';
            cb.onchange = function() {
                fetch('/edit/artist/' + artistId + '/' + endpoint, { method: 'POST', headers: _editHeaders(), body: 'value=' + (cb.checked ? '1' : '0') })
                    .then(function(r) { if (r.ok) { data[field] = cb.checked; dirty = true; } else { cb.checked = !cb.checked; _toast('Failed'); } });
            };
            var sp = document.createElement('span'); sp.textContent = labelText;
            lab.appendChild(cb); lab.appendChild(sp);
            bodyArea.appendChild(lab);
        }
        _toggle('Inactive', 'is_disbanded', 'is-disbanded');
        _toggle('Complete', 'is_complete', 'is-complete');
        _toggle('Tracked', 'is_tracked', 'is-tracked');

        var sep = document.createElement('div');
        sep.style.cssText = 'border-top:1px solid var(--border,#ccc); margin:8px 0 10px;';
        bodyArea.appendChild(sep);
        var actLabel = document.createElement('div');
        actLabel.textContent = 'Actions';
        actLabel.style.cssText = 'font-size:11px; text-transform:uppercase; letter-spacing:0.03em; color:var(--text-secondary,#6B7280); margin-bottom:8px;';
        bodyArea.appendChild(actLabel);
        var actWrap = document.createElement('div');
        actWrap.style.cssText = 'display:flex; flex-wrap:wrap; gap:8px;';
        bodyArea.appendChild(actWrap);
        function _act(label, kind, fn) { var b = _btnEl(label, kind || 'secondary'); b.onclick = fn; actWrap.appendChild(b); }

        _act('Gender', 'secondary', function() {
            _ensure(genderOpts, '/lookups/genders', function(opts) {
                genderOpts = opts;
                showMobilePicker({ title: 'Gender', mode: 'select',
                    options: opts.map(function(g) { return { id: g.id, label: g.name, selected: g.id === data.gender_id }; }),
                    onSelect: function(o) {
                        fetch('/edit/artist/' + artistId + '/gender', { method: 'POST', headers: _editHeaders(), body: 'gender_id=' + o.id })
                            .then(function(r) { if (r.ok) { data.gender = o.label; data.gender_id = o.id; dirty = true; } });
                    } });
            });
        });
        _act('Country', 'secondary', function() {
            _ensure(countryOpts, '/lookups/countries', function(opts) {
                countryOpts = opts;
                showMobilePicker({ title: 'Country', mode: 'select',
                    options: opts.map(function(c) { return { id: c.id, label: c.name, selected: c.id === data.country_id }; }),
                    onSelect: function(o) {
                        fetch('/edit/artist/' + artistId + '/country', { method: 'POST', headers: _editHeaders(), body: 'country_id=' + o.id })
                            .then(function(r) { if (r.ok) { data.country = o.label; data.country_id = o.id; dirty = true; } });
                    } });
            });
        });
        function _userPick(roleLabel, field, endpoint) {
            _ensure(userOpts, '/lookups/users', function(opts) {
                userOpts = opts;
                var options = [{ id: '', label: '— None —', selected: !data[field + '_id'] }].concat(
                    opts.map(function(u) { return { id: u.id, label: u.name, selected: u.id === data[field + '_id'] }; }));
                showMobilePicker({ title: roleLabel, mode: 'select', options: options,
                    onSelect: function(o) {
                        fetch('/edit/artist/' + artistId + '/' + endpoint, { method: 'POST', headers: _editHeaders(), body: 'user_id=' + (o.id === '' ? '' : o.id) })
                            .then(function(r) { if (r.ok) { data[field] = (o.id === '' ? '' : o.label); data[field + '_id'] = (o.id === '' ? null : o.id); dirty = true; } });
                    } });
            });
        }
        _act('Owner', 'secondary', function() { _userPick('Owner', 'owner', 'owner'); });
        _act('Maintainer', 'secondary', function() { _userPick('Maintainer', 'maintainer', 'maintainer'); });

        _act('Manage genres', 'secondary', function() {
            closeMobileModal();
            if (typeof showBulkGenreModal === 'function') showBulkGenreModal(artistId, data.name);
        });
        _act('Auto-fill Spotify', 'secondary', function() {
            if (typeof autoPopulateSpotify === 'function') autoPopulateSpotify(artistId);
        });
        _act('Delete artist', 'danger', function() {
            showMobilePassword({ title: 'Delete artist?',
                message: '"' + data.name + '" and all related data will be permanently deleted. Enter your password to confirm.',
                confirmLabel: 'Delete',
                onConfirm: function(pw, helpers) {
                    fetch('/edit/artist/' + artistId + '/delete', { method: 'POST', headers: _editHeaders(), body: 'password=' + encodeURIComponent(pw), redirect: 'manual' })
                        .then(function(r) { if (r.status === 403) { helpers.error('Incorrect password.'); return; } helpers.close(); window.location = '/'; });
                } });
        });
    }

    fetch('/artist/' + artistId + '/edit-info', { headers: { 'Accept': 'application/json' } })
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(d) {
            if (!d) { bodyArea.textContent = 'Failed to load.'; return; }
            data.name = d.name || ''; data.spotify_url = d.spotify_url || '';
            data.gender_id = d.gender_id; data.gender = d.gender || '';
            data.country_id = d.country_id; data.country = d.country || '';
            data.owner_id = d.owner_id; data.owner = d.owner || '';
            data.maintainer_id = d.maintainer_id; data.maintainer = d.maintainer || '';
            data.is_disbanded = !!d.is_disbanded; data.is_complete = !!d.is_complete; data.is_tracked = !!d.is_tracked;
            renderInfo();
        })
        .catch(function() { bodyArea.textContent = 'Failed to load.'; });

    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    activeMobileModal = backdrop;
    backdrop.addEventListener('click', function(e) { if (e.target === backdrop) doClose(); });
}

/* Shared mobile bottom-sheet picker — search / single-select / multi-select.
   Stacks above other mobile modals (z-index 300); manages its own lifecycle. */
function showMobilePicker(opts) {
    var backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:300; background:rgba(0,0,0,0.5); display:flex; align-items:flex-end; justify-content:center;';
    var sheet = document.createElement('div');
    sheet.style.cssText = 'background:var(--bg-secondary,#fff); border-top-left-radius:12px; border-top-right-radius:12px; width:100%; max-width:480px; max-height:80vh; display:flex; flex-direction:column; box-shadow:0 -4px 16px rgba(0,0,0,0.3);';

    function close() { backdrop.remove(); }
    backdrop.addEventListener('click', function(e) { if (e.target === backdrop) close(); });

    var head = document.createElement('div');
    head.style.cssText = 'padding:14px 16px 8px; display:flex; align-items:center; gap:8px; flex-shrink:0;';
    var h = document.createElement('div');
    h.textContent = opts.title || '';
    h.style.cssText = 'font-size:15px; font-weight:600; color:var(--text-primary); flex:1;';
    head.appendChild(h);
    var x = document.createElement('button');
    x.innerHTML = '&#10005;';
    x.style.cssText = 'border:none; background:none; font-size:18px; color:var(--text-secondary,#6B7280); cursor:pointer;';
    x.onclick = close;
    head.appendChild(x);
    sheet.appendChild(head);

    var body = document.createElement('div');
    body.style.cssText = 'padding:0 16px 16px; overflow-y:auto; flex:1;';
    sheet.appendChild(body);

    function _rowBtn(label) {
        var b = document.createElement('button');
        b.textContent = label;
        b.style.cssText = 'display:flex; justify-content:space-between; align-items:center; gap:8px; width:100%; text-align:left; padding:11px 6px; font-size:14px; border:none; border-bottom:1px solid var(--border,#eee); background:none; color:var(--text-primary); cursor:pointer;';
        return b;
    }

    if (opts.mode === 'search') {
        var input = document.createElement('input');
        input.type = 'text';
        input.placeholder = opts.placeholder || 'Search…';
        input.style.cssText = 'width:100%; border:1px solid var(--border,#ccc); border-radius:6px; padding:9px; font-size:14px; box-sizing:border-box; background:var(--bg-primary,#fff); color:var(--text-primary); margin-bottom:10px;';
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
                            results.innerHTML = '<div style="font-size:13px;color:var(--text-secondary,#6B7280);padding:8px 0;">No matches.</div>';
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
            lab.style.cssText = 'display:flex; align-items:center; gap:10px; padding:9px 6px; font-size:14px; border-bottom:1px solid var(--border,#eee); color:var(--text-primary); cursor:pointer;';
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
        done.style.cssText = 'margin-top:12px; width:100%; padding:11px; font-size:14px; background:var(--link,#2563EB); color:#fff; border:none; border-radius:6px; cursor:pointer;';
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
    backdrop.style.cssText = 'position:fixed; inset:0; z-index:310; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; padding:16px;';
    var modal = document.createElement('div');
    modal.style.cssText = 'background:var(--bg-secondary,#fff); border:1px solid var(--border,#ccc); border-radius:8px; padding:16px; width:100%; max-width:320px; box-shadow:0 4px 16px rgba(0,0,0,0.3);';

    function close() { backdrop.remove(); }

    if (opts.title) {
        var t = document.createElement('div');
        t.textContent = opts.title;
        t.style.cssText = 'font-size:15px; font-weight:600; color:var(--text-primary); margin-bottom:6px;';
        modal.appendChild(t);
    }
    if (opts.message) {
        var m = document.createElement('div');
        m.textContent = opts.message;
        m.style.cssText = 'font-size:13px; color:var(--text-secondary,#6B7280); margin-bottom:10px; white-space:pre-line;';
        modal.appendChild(m);
    }

    var input = document.createElement('input');
    input.type = 'password';
    input.placeholder = 'Password';
    input.autocomplete = 'current-password';
    input.style.cssText = 'width:100%; border:1px solid var(--border,#ccc); border-radius:6px; padding:9px; font-size:14px; box-sizing:border-box; background:var(--bg-primary,#fff); color:var(--text-primary); margin-bottom:6px;';
    modal.appendChild(input);

    var err = document.createElement('div');
    err.style.cssText = 'font-size:12px; color:var(--delete-button,#DC2626); min-height:16px; margin-bottom:8px;';
    modal.appendChild(err);

    var row = document.createElement('div');
    row.style.cssText = 'display:flex; gap:8px; justify-content:flex-end;';
    var cancel = document.createElement('button');
    cancel.textContent = 'Cancel';
    cancel.style.cssText = 'padding:8px 16px; font-size:14px; background:var(--bg-primary,#fff); color:var(--text-primary); border:1px solid var(--border,#ccc); border-radius:6px; cursor:pointer;';
    cancel.onclick = close;
    var confirm = document.createElement('button');
    confirm.textContent = opts.confirmLabel || 'Confirm';
    confirm.style.cssText = 'padding:8px 16px; font-size:14px; background:var(--delete-button,#DC2626); color:#fff; border:none; border-radius:6px; cursor:pointer;';
    confirm.onclick = function() {
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
        position: fixed; z-index: 50; background: var(--bg-secondary, #fff); border: 2px solid var(--link, #2563EB);
        border-radius: 4px; padding: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        width: 240px;
    `;

    // Song name label
    const label = document.createElement('div');
    label.textContent = songName || 'Note';
    label.style.cssText = `
        font-size: 11px; font-weight: 600; color: var(--text-secondary, #6B7280); margin-bottom: 4px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    `;
    overlay.appendChild(label);
    _makeDraggable(overlay, label);

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
    if (rect.right + gap + overlayWidth < window.innerWidth) {
        overlay.style.left = (rect.right + gap) + 'px';
    } else {
        overlay.style.left = (rect.left - gap - overlayWidth) + 'px';
    }

    document.body.appendChild(overlay);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
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

/* Real-time rating sync via polling */
(function () {
    var pollSeq = 0;
    var POLL_INTERVAL = 10000;

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

    function poll() {
        fetch('/events/poll?since=' + pollSeq)
            .then(function (r) { if (!r.ok) return null; return r.json(); })
            .then(function (data) {
                if (!data) return;
                pollSeq = data.seq;
                data.events.forEach(function (e) {
                    if (e.event === 'rating-update') handleUpdate(e.data);
                });
            })
            .catch(function () {});
    }

    setInterval(poll, POLL_INTERVAL);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
    poll();
})();
