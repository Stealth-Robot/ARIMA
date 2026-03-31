/* Rating popover — replaces hx-prompt with inline coloured buttons */

const RATING_COLOURS = {
    5: {bg: '#FF0016', text: '#FFFFFF'},
    4: {bg: '#FF8E1E', text: '#000000'},
    3: {bg: '#FEFF2A', text: '#000000'},
    2: {bg: '#9EFFA4', text: '#000000'},
    1: {bg: '#8AB5FC', text: '#000000'},
    0: {bg: '#9200FC', text: '#FFFFFF'},
};

let activePopover = null;

function showRatingPopover(event, songId) {
    event.stopPropagation();
    closeRatingPopover();

    const cell = event.currentTarget;
    const popover = document.createElement('div');
    popover.className = 'rating-popover';
    popover.style.cssText = `
        position: absolute; z-index: 50; display: flex; gap: 2px;
        padding: 4px; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        background: white; border: 1px solid #ccc; left: 50%; top: 100%;
        transform: translateX(-50%); white-space: nowrap;
    `;

    // Buttons 0-5
    for (let score = 0; score <= 5; score++) {
        const btn = document.createElement('button');
        btn.textContent = score;
        btn.style.cssText = `
            width: 24px; height: 24px; border: none; border-radius: 3px;
            cursor: pointer; font-weight: bold; font-size: 11px;
            background-color: ${RATING_COLOURS[score].bg};
            color: ${RATING_COLOURS[score].text};
        `;
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            closeRatingPopover();
            // Submit via HTMX
            htmx.ajax('POST', '/rate', {
                target: cell,
                swap: 'outerHTML',
                values: {song_id: songId, rating: score},
            });
        });
        popover.appendChild(btn);
    }

    // Clear button (×)
    const clearBtn = document.createElement('button');
    clearBtn.textContent = '×';
    clearBtn.style.cssText = `
        width: 24px; height: 24px; border: 1px solid #ccc; border-radius: 3px;
        cursor: pointer; font-size: 14px; background: #f5f5f5; color: #666;
    `;
    clearBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        closeRatingPopover();
        htmx.ajax('POST', '/rate/delete', {
            target: cell,
            swap: 'outerHTML',
            values: {song_id: songId},
        });
    });
    popover.appendChild(clearBtn);

    cell.style.position = 'relative';
    cell.appendChild(popover);
    activePopover = popover;
}

function closeRatingPopover() {
    if (activePopover) {
        activePopover.remove();
        activePopover = null;
    }
}

// Close popover on click outside
document.addEventListener('click', closeRatingPopover);
