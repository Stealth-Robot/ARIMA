/* Rating popover — reads colours from CSS custom properties (theme-driven) */

let activePopover = null;

function getRatingColours() {
    const style = getComputedStyle(document.documentElement);
    return {
        5: {bg: style.getPropertyValue('--rating-5-bg').trim(), text: style.getPropertyValue('--rating-text-light').trim()},
        4: {bg: style.getPropertyValue('--rating-4-bg').trim(), text: style.getPropertyValue('--rating-text-dark').trim()},
        3: {bg: style.getPropertyValue('--rating-3-bg').trim(), text: style.getPropertyValue('--rating-text-dark').trim()},
        2: {bg: style.getPropertyValue('--rating-2-bg').trim(), text: style.getPropertyValue('--rating-text-dark').trim()},
        1: {bg: style.getPropertyValue('--rating-1-bg').trim(), text: style.getPropertyValue('--rating-text-dark').trim()},
        0: {bg: style.getPropertyValue('--rating-0-bg').trim(), text: style.getPropertyValue('--rating-text-light').trim()},
    };
}

function showRatingPopover(event, songId) {
    event.stopPropagation();
    closeRatingPopover();

    const cell = event.currentTarget;
    const colours = getRatingColours();
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
            background-color: ${colours[score].bg};
            color: ${colours[score].text};
        `;
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            closeRatingPopover();
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
        width: 24px; height: 24px; border: 1px solid var(--grid-line, #ccc); border-radius: 3px;
        cursor: pointer; font-size: 14px; background: var(--row-alternate, #f5f5f5);
        color: var(--text-secondary, #666);
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
