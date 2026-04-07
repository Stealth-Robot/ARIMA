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

/* CSRF helper for fetch calls */
function _csrfHeaders(extra) {
    var h = extra || {};
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) h['X-CSRFToken'] = meta.content;
    return h;
}

/* Hover background — reads hex from --hover-bg CSS variable and applies 0.2 opacity */
function _hoverBg() {
    var hex = getComputedStyle(document.documentElement).getPropertyValue('--hover-bg').trim();
    if (!hex || hex.length < 7) return 'rgba(128,128,128,0.2)';
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',0.2)';
}

/* Toast notifications */

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

// Alias used throughout edit popovers
var showToast = showBriefToast;

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
        // Align right edge with trigger button, but don't go off left edge
        var left = rect.right - 320;
        if (left < 8) left = 8;
        overlay.style.left = left + 'px';
        overlay.style.top = '';
        overlay.style.bottom = '';
        overlay.style.display = 'block';
        var zoom = parseFloat(document.documentElement.style.zoom) || 1;
        var viewH = window.innerHeight / zoom;
        if (rect.bottom + 4 + overlay.offsetHeight + 30 > viewH) {
            overlay.style.top = Math.max(0, viewH - overlay.offsetHeight - 30) + 'px';
        } else {
            overlay.style.top = (rect.bottom + 4) + 'px';
        }
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

function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

function toggleArtistMenu() {
    var menu = document.getElementById('artist-menu');
    if (!menu) return;
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

function closeArtistMenu() {
    var menu = document.getElementById('artist-menu');
    if (menu) {
        menu.style.display = 'none';
        // Clear silent search state
        var highlighted = menu.querySelector('.artist-menu-item[style*="outline"]');
        if (highlighted) highlighted.style.outline = '';
    }
}

document.addEventListener('click', function (e) {
    var menu = document.getElementById('artist-menu');
    var btn = document.getElementById('hamburger-btn');
    if (!menu || menu.style.display === 'none') return;
    if (!menu.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
        closeArtistMenu();
    }
});

// Drag-to-scroll on artist navbar
(function() {
    var nav = document.querySelector('.artist-nav');
    if (!nav) return;
    var dragging = false, startX = 0, savedScroll = 0, moved = false;

    nav.addEventListener('mousedown', function(e) {
        dragging = true;
        moved = false;
        startX = e.pageX;
        savedScroll = nav.scrollLeft;
        nav.style.cursor = 'grabbing';
        nav.style.userSelect = 'none';
        e.preventDefault();
    });

    document.addEventListener('mousemove', function(e) {
        if (!dragging) return;
        var dx = e.pageX - startX;
        if (Math.abs(dx) > 5) moved = true;
        nav.scrollLeft = savedScroll - dx;
    });

    document.addEventListener('mouseup', function() {
        if (!dragging) return;
        dragging = false;
        nav.style.cursor = 'grab';
        nav.style.userSelect = '';
        // Suppress click if dragged
        if (moved) {
            nav.addEventListener('click', function suppress(e) {
                e.preventDefault();
                e.stopPropagation();
                nav.removeEventListener('click', suppress, true);
            }, true);
        }
    });

    nav.addEventListener('mouseleave', function() {
        if (dragging) {
            dragging = false;
            nav.style.cursor = 'grab';
            nav.style.userSelect = '';
        }
    });
})();

// Silent search in artist hamburger menu
(function() {
    var _searchBuf = '';
    var _searchTimer = null;
    var _lastHighlight = null;

    document.addEventListener('keydown', function(e) {
        var menu = document.getElementById('artist-menu');
        if (!menu || menu.style.display === 'none') return;
        // Ignore if user is typing in an input/textarea/select
        var tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
        // Only single printable characters
        if (e.key.length !== 1 || e.ctrlKey || e.metaKey || e.altKey) return;

        e.preventDefault();
        _searchBuf += e.key.toLowerCase();
        clearTimeout(_searchTimer);
        _searchTimer = setTimeout(function() { _searchBuf = ''; }, 800);

        // Find first matching artist link
        var items = menu.querySelectorAll('.artist-menu-item');
        var match = null;
        for (var i = 0; i < items.length; i++) {
            if (items[i].textContent.trim().toLowerCase().indexOf(_searchBuf) === 0) {
                match = items[i];
                break;
            }
        }
        if (match) {
            // Remove previous highlight
            if (_lastHighlight) _lastHighlight.style.outline = '';
            // Scroll into view and highlight
            match.scrollIntoView({ block: 'nearest' });
            match.style.outline = '2px solid var(--navbar-active, #fff)';
            _lastHighlight = match;
        }
    });
})();

/* Format UTC dates to local 12h time for changelog and similar elements */
function formatUtcDates(root) {
    (root || document).querySelectorAll('.changelog-date').forEach(function(td) {
        var utc = td.dataset.utc;
        if (!utc) return;
        var d = new Date(utc);
        if (isNaN(d)) return;
        var pad = function(n) { return n < 10 ? '0' + n : n; };
        var h = d.getHours();
        var ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        td.textContent = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
            + '  ' + pad(h) + ':' + pad(d.getMinutes()) + ' ' + ampm;
    });
}
formatUtcDates();

/* Date formatting helpers */

/**
 * Apply yyyy-mm-dd auto-formatting to a text input.
 * Strips non-digits, auto-inserts hyphens, caps at 10 chars.
 */
function _setupDateGuide(input, pattern) {
    /**
     * Add a persistent format guide behind a date input.
     * Uses a wrapper span that inherits the input's layout properties.
     */
    var wrapper = document.createElement('span');
    wrapper.style.cssText = 'position:relative; display:inline-block;';
    // Inherit width from input if set, otherwise use flex
    var inputWidth = input.style.width;
    if (inputWidth) {
        wrapper.style.width = inputWidth;
        input.style.width = '100%';
    }
    // Inherit flex properties
    var inputFlex = input.style.flex;
    if (inputFlex) {
        wrapper.style.flex = inputFlex;
        input.style.flex = '';
    }
    if (input.classList.contains('flex-1')) {
        input.classList.remove('flex-1');
        wrapper.style.flex = '1';
    }

    var guide = document.createElement('input');
    guide.type = 'text';
    guide.value = pattern;
    guide.disabled = true;
    guide.tabIndex = -1;
    guide.style.cssText = 'position:absolute; left:0; top:0; width:100%; height:100%; box-sizing:border-box; pointer-events:none; background:transparent !important; border:transparent; color:var(--text-secondary); opacity:0.4; margin:0;';

    if (input.parentNode) {
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(guide);
        wrapper.appendChild(input);
    } else {
        wrapper.appendChild(guide);
        wrapper.appendChild(input);
        input._dateWrapper = wrapper;
    }

    // Clone exact box model from real input after layout
    requestAnimationFrame(function() {
        var cs = getComputedStyle(input);
        guide.style.padding = cs.padding;
        guide.style.font = cs.font;
        guide.style.letterSpacing = cs.letterSpacing;
        guide.style.borderWidth = cs.borderWidth;
        guide.style.borderStyle = 'solid';
        guide.style.borderColor = 'transparent';
    });

    function updateGuide() {
        var v = input.value;
        if (!v) { guide.value = pattern; return; }
        var visible = '';
        for (var i = 0; i < pattern.length; i++) {
            visible += i < v.length ? ' ' : pattern[i];
        }
        guide.value = visible;
    }

    return updateGuide;
}

function applyDateFormat(input) {
    input.type = 'text';
    input.placeholder = 'yyyy-mm-dd';
    input.maxLength = 10;
    input.style.fontFamily = 'monospace';

    var updateGuide = _setupDateGuide(input, 'yyyy-mm-dd');

    input.addEventListener('input', function() {
        var raw = this.value;
        var pos = this.selectionStart;
        // Count digits before cursor in the old value
        var digitsBefore = (raw.slice(0, pos).match(/[0-9]/g) || []).length;
        var v = raw.replace(/[^0-9]/g, '');
        if (v.length > 4) v = v.slice(0, 4) + '-' + v.slice(4);
        if (v.length > 7) v = v.slice(0, 7) + '-' + v.slice(7);
        if (v.length > 10) v = v.slice(0, 10);
        this.value = v;
        this.style.borderColor = '';
        // Restore cursor: find position after the same number of digits
        var newPos = 0;
        var count = 0;
        while (newPos < v.length && count < digitsBefore) {
            if (/[0-9]/.test(v[newPos])) count++;
            newPos++;
        }
        this.setSelectionRange(newPos, newPos);
        updateGuide();
    });

    updateGuide();
}

/**
 * Apply yyyy-mm-dd hh:mm auto-formatting to a text input.
 */
function applyDateTimeFormat(input) {
    input.type = 'text';
    input.placeholder = 'YYYY-MM-DD HH:MM';
    input.maxLength = 16;
    input.style.fontFamily = 'monospace';

    var updateGuide = _setupDateGuide(input, 'YYYY-MM-DD HH:MM');

    input.addEventListener('input', function() {
        var raw = this.value;
        var pos = this.selectionStart;
        var digitsBefore = (raw.slice(0, pos).match(/[0-9]/g) || []).length;
        var v = raw.replace(/[^0-9]/g, '');
        if (v.length > 4) v = v.slice(0, 4) + '-' + v.slice(4);
        if (v.length > 7) v = v.slice(0, 7) + '-' + v.slice(7);
        if (v.length > 10) v = v.slice(0, 10) + ' ' + v.slice(10);
        if (v.length > 13) v = v.slice(0, 13) + ':' + v.slice(13);
        if (v.length > 16) v = v.slice(0, 16);
        this.value = v;
        var newPos = 0;
        var count = 0;
        while (newPos < v.length && count < digitsBefore) {
            if (/[0-9]/.test(v[newPos])) count++;
            newPos++;
        }
        this.setSelectionRange(newPos, newPos);
        updateGuide();
    });

    updateGuide();
}

// Auto-apply to all date/datetime inputs
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('[data-date-format]').forEach(applyDateFormat);
    document.querySelectorAll('[data-datetime-format]').forEach(applyDateTimeFormat);
});

/* HTMX after-settle handlers */
document.addEventListener('htmx:afterSettle', function(e) {
    e.detail.elt.querySelectorAll('[data-date-format]').forEach(applyDateFormat);
    formatUtcDates(e.detail.elt);

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
    var cell = (elt.id && elt.id.startsWith('rating-')) ? elt
             : elt.querySelector('[id^="rating-"]');
    if (cell) {
        var row = cell.closest('tr');
        if (row) { row.style.display = 'none'; row.offsetHeight; row.style.display = ''; }
    }
});

/* Navigation and highlighting */

function navigateToCell(cell, direction) {
    const row = cell.parentElement;
    const colIndex = Array.from(row.children).indexOf(cell);

    if (direction === 'up' || direction === 'down') {
        let targetRow = direction === 'down' ? row.nextElementSibling : row.previousElementSibling;
        while (targetRow) {
            const targetCell = targetRow.children[colIndex];
            if (targetCell && targetCell.getAttribute('onclick')) {
                highlightRow(targetRow, true);
                targetCell.click();
                return;
            }
            targetRow = direction === 'down' ? targetRow.nextElementSibling : targetRow.previousElementSibling;
        }
    } else {
        let sibling = direction === 'right' ? cell.nextElementSibling : cell.previousElementSibling;
        while (sibling) {
            if (sibling.getAttribute('onclick')) {
                highlightRow(sibling.closest('tr'), true);
                sibling.click();
                return;
            }
            sibling = direction === 'right' ? sibling.nextElementSibling : sibling.previousElementSibling;
        }
    }
}

function highlightRow(tr, fast) {
    if (!tr || tr.tagName !== 'TR') return;
    var cls = fast ? 'highlight-glow-fast' : 'highlight-glow';
    tr.classList.remove('highlight-glow', 'highlight-glow-fast');
    void tr.offsetWidth;
    tr.classList.add(cls);
    tr.addEventListener('animationend', function() {
        tr.classList.remove(cls);
    }, { once: true });
}

// Highlight row when navigating via hash fragment (search jump)
(function() {
    function highlightHash() {
        var hash = location.hash;
        if (!hash) return;
        var el = document.getElementById(hash.slice(1));
        highlightRow(el);
    }
    window.addEventListener('load', highlightHash);
    window.addEventListener('hashchange', highlightHash);
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
