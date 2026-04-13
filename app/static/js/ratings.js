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

/* Mobile detection helper */
function _isMobile() {
    return window.innerWidth <= 768;
}

/* Mobile rating modal — score picker + note editor */

let activeMobileModal = null;

function _getSongNameFromRow(cell) {
    var row = cell.parentElement;
    var firstCell = row ? row.children[0] : null;
    var link = firstCell ? firstCell.querySelector('a') : null;
    var mergeBtn = firstCell ? firstCell.querySelector('[data-song-name]') : null;
    return link ? link.textContent.trim() : mergeBtn ? mergeBtn.dataset.songName : (firstCell ? firstCell.childNodes[0].textContent.trim() : '');
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
        if (undoStack.length >= 50) undoStack.shift();
        undoStack.push({ songId: songId, previousRating: previousRating, previousNote: previousNote, cellHTML: cell.outerHTML, artistSlug: artistSlug });
        redoStack.length = 0;

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
        if (undoStack.length >= 50) undoStack.shift();
        undoStack.push({ songId: songId, previousRating: previousRating, previousNote: previousNote, cellHTML: cell.outerHTML, artistSlug: artistSlug });
        redoStack.length = 0;

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

/* Inline rating — spreadsheet-style type-and-go */

let activeInput = null;
let inputGeneration = 0;

function showRatingInput(event, songId, targetUserId) {
    event.stopPropagation();

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
    if (undoStack.length >= 50) undoStack.shift();
    undoStack.push({ songId, previousRating: rating, previousNote, cellHTML: cell.outerHTML, artistSlug });
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
    tooltip.style.left = rect.left + rect.width / 2 + 'px';
    tooltip.style.transform = 'translateX(-50%)';
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
        if (!tooltip.contains(e.relatedTarget) && !e.relatedTarget?.closest('td.has-note') && !e.relatedTarget?.closest('td.song-name-cell.has-song-note')) {
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
})();

/* Real-time rating sync via SSE with leader election.
 *
 * One tab holds the SSE connection and broadcasts updates to others via
 * BroadcastChannel. When the leader closes, it signals other tabs to elect
 * a new leader. A heartbeat + stale check ensures recovery if a leader
 * crashes without a clean close.
 */
(function () {
    var LEADER_KEY = 'sse-leader';
    var HEARTBEAT_MS = 5000;
    var STALE_MS = 15000;
    var tabId = Date.now() + '-' + Math.random().toString(36).slice(2);
    var channel = (typeof BroadcastChannel !== 'undefined') ? new BroadcastChannel('sse-ratings') : null;
    var source = null;
    var heartbeatTimer = null;
    var staleCheckTimer = null;
    var isLeader = false;

    function handleUpdate(data) {
        var cellId = 'rating-' + data.song_id + '-' + data.user_id;
        var cell = document.getElementById(cellId);
        if (!cell) return;
        fetch('/rate/cell?song_id=' + data.song_id + '&user_id=' + data.user_id)
            .then(function (r) { return r.text(); })
            .then(function (html) {
                cell.outerHTML = html;
                var row = document.getElementById(cellId);
                if (row) row = row.closest('tr');
                if (row && row.style.display !== 'none') { row.style.display = 'none'; row.offsetHeight; row.style.display = ''; }
            });
    }

    function startSSE() {
        if (source) return;
        source = new EventSource('/events/ratings');
        source.addEventListener('rating-update', function (e) {
            var data = JSON.parse(e.data);
            handleUpdate(data);
            if (channel) {
                channel.postMessage({ type: 'rating-update', song_id: data.song_id, user_id: data.user_id });
            }
        });
    }

    function stopSSE() {
        if (source) { source.close(); source = null; }
    }

    function becomeLeader() {
        if (isLeader) return;
        isLeader = true;
        try { localStorage.setItem(LEADER_KEY, tabId + ':' + Date.now()); } catch (e) {}
        startSSE();
        // Heartbeat: update timestamp so other tabs know we're alive
        heartbeatTimer = setInterval(function () {
            try { localStorage.setItem(LEADER_KEY, tabId + ':' + Date.now()); } catch (e) {}
        }, HEARTBEAT_MS);
    }

    function resign() {
        isLeader = false;
        if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
        stopSSE();
        try { localStorage.removeItem(LEADER_KEY); } catch (e) {}
        // Tell other tabs to elect a new leader
        if (channel) channel.postMessage({ type: 'need-leader' });
    }

    function tryClaimLeadership() {
        if (isLeader) return;
        // Atomic-ish claim: write our tabId, read it back after a brief delay
        try { localStorage.setItem(LEADER_KEY, tabId + ':' + Date.now()); } catch (e) {}
        setTimeout(function () {
            try {
                var val = localStorage.getItem(LEADER_KEY) || '';
                if (val.indexOf(tabId) === 0) {
                    becomeLeader();
                }
            } catch (e) {
                // localStorage unavailable — just become leader
                becomeLeader();
            }
        }, 50 + Math.random() * 100);
    }

    function checkForStaleLeader() {
        if (isLeader) return;
        try {
            var val = localStorage.getItem(LEADER_KEY);
            if (!val) { tryClaimLeadership(); return; }
            var parts = val.split(':');
            var ts = parseInt(parts[1], 10);
            if (Date.now() - ts > STALE_MS) {
                // Leader is stale (crashed without resigning)
                tryClaimLeadership();
            }
        } catch (e) {
            tryClaimLeadership();
        }
    }

    // Listen for broadcasts from other tabs
    if (channel) {
        channel.addEventListener('message', function (e) {
            if (e.data && e.data.type === 'rating-update') {
                handleUpdate(e.data);
            } else if (e.data && e.data.type === 'need-leader') {
                // Leader resigned — try to claim
                tryClaimLeadership();
            }
        });
    }

    // Initial election: claim if no leader, or if leader is stale
    checkForStaleLeader();

    // Periodic stale check in case leader crashed without broadcasting
    staleCheckTimer = setInterval(checkForStaleLeader, STALE_MS);

    // Clean resignation on tab close
    window.addEventListener('beforeunload', function () {
        if (isLeader) resign();
        if (staleCheckTimer) clearInterval(staleCheckTimer);
    });
})();
