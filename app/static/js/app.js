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
