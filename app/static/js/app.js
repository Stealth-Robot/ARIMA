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

/* Inline rating — spreadsheet-style type-and-go */

let activeInput = null;

function showRatingInput(event, songId) {
    event.stopPropagation();
    closeRatingInput();

    const cell = event.currentTarget;
    const currentValue = cell.textContent.trim();

    // Save original content for cancel
    cell.dataset.original = cell.innerHTML;
    cell.dataset.songId = songId;

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
        if (e.key === 'Enter') {
            e.preventDefault();
            const val = input.value.trim();
            if (val === '') {
                // Empty = delete rating
                submitRating(cell, songId, null);
            } else if (/^[0-5]$/.test(val)) {
                submitRating(cell, songId, parseInt(val));
            }
            // Invalid input — do nothing, stay in input
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cancelRating(cell);
        } else if (e.key === 'n') {
            e.preventDefault();
            cancelRating(cell);
            showNoteInput(cell, songId);
        } else if (e.key === 'ArrowDown' || e.key === 's') {
            e.preventDefault();
            cancelRating(cell);
            navigateToCell(cell, 'down');
        } else if (e.key === 'ArrowUp' || e.key === 'w') {
            e.preventDefault();
            cancelRating(cell);
            navigateToCell(cell, 'up');
        } else if (e.key === 'ArrowRight' || e.key === 'd') {
            e.preventDefault();
            cancelRating(cell);
            navigateToCell(cell, 'right');
        } else if (e.key === 'ArrowLeft' || e.key === 'a') {
            e.preventDefault();
            cancelRating(cell);
            navigateToCell(cell, 'left');
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

function submitRating(cell, songId, rating) {
    activeInput = null;

    if (rating === null) {
        // Delete rating
        htmx.ajax('POST', '/rate/delete', {
            target: cell,
            swap: 'outerHTML',
            values: { song_id: songId },
        });
    } else {
        htmx.ajax('POST', '/rate', {
            target: cell,
            swap: 'outerHTML',
            values: { song_id: songId, rating: rating },
        });
    }

    // Auto-advance to next cell below after a brief delay (wait for HTMX swap)
    const colIndex = Array.from(cell.parentElement.children).indexOf(cell);
    const currentRow = cell.parentElement;

    setTimeout(() => {
        // Walk rows to find next song row (skip album headers)
        let nextRow = currentRow.nextElementSibling;
        while (nextRow) {
            const nextCell = nextRow.children[colIndex];
            if (nextCell && nextCell.getAttribute('onclick')) {
                nextCell.click();
                break;
            }
            nextRow = nextRow.nextElementSibling;
        }
    }, 300);
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

    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: absolute; z-index: 50; background: #fff; border: 2px solid var(--link, #2563EB);
        border-radius: 4px; padding: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        min-width: 200px;
    `;

    const textarea = document.createElement('textarea');
    textarea.value = existingNote;
    textarea.rows = 3;
    textarea.style.cssText = `
        width: 100%; border: 1px solid #ccc; border-radius: 3px; padding: 4px;
        font-size: 13px; font-family: inherit; resize: vertical; color: #000;
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

    // Position relative to cell
    const rect = cell.getBoundingClientRect();
    overlay.style.position = 'fixed';
    overlay.style.left = rect.left + 'px';
    overlay.style.top = (rect.bottom + 2) + 'px';

    document.body.appendChild(overlay);
    textarea.focus();
    activeNote = { overlay, cell };

    textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            closeNoteInput();
        }
    });
}

function submitNote(cell, songId, noteText) {
    closeNoteInput();

    // Get current rating value from cell text
    const ratingText = cell.textContent.trim();
    const rating = /^[0-5]$/.test(ratingText) ? parseInt(ratingText) : null;

    if (rating === null) {
        // No rating yet — can't attach a note without a rating
        return;
    }

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
        const match = cell.getAttribute('onclick').match(/showRatingInput\(event,\s*(\d+)\)/);
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
