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

/* Navbar filter multiselect — open/close checkbox panel, POST list on close if changed */
function _filterGetChecked(panel) {
    return Array.from(panel.querySelectorAll('input[type="checkbox"]:checked'))
        .map(function(cb) { return cb.value; })
        .sort();
}

function _updateFilterLabel(wrapper) {
    var panel = wrapper.querySelector('.filter-panel');
    var labelEl = wrapper.querySelector('.filter-label');
    if (!panel || !labelEl) return;
    var label = wrapper.dataset.label || '';
    var checked = panel.querySelectorAll('input[type="checkbox"]:checked');
    if (checked.length === 0) {
        labelEl.textContent = label;
    } else if (checked.length === 1) {
        var name = checked[0].parentElement.querySelector('span').textContent.trim();
        labelEl.textContent = label + ': ' + name;
    } else {
        var firstName = checked[0].parentElement.querySelector('span').textContent.trim();
        labelEl.textContent = label + ': ' + firstName + ' +' + (checked.length - 1);
    }
}

function toggleFilterPanel(btn) {
    var wrapper = btn.closest('.filter-multiselect');
    var panel = wrapper.querySelector('.filter-panel');
    var isOpen = !panel.classList.contains('hidden');
    // Close any other open panels first (and apply them if dirty)
    document.querySelectorAll('.filter-multiselect').forEach(function(w) {
        if (w !== wrapper) _closeFilterPanel(w);
    });
    if (isOpen) {
        _closeFilterPanel(wrapper);
    } else {
        panel.dataset.initial = _filterGetChecked(panel).join(',');
        panel.classList.remove('hidden');
        var rect = btn.getBoundingClientRect();
        panel.style.position = 'fixed';
        panel.style.top = rect.bottom + 2 + 'px';
        panel.style.left = '';
        panel.style.right = '';
        var panelWidth = panel.offsetWidth;
        if (rect.right - panelWidth < 0) {
            panel.style.left = rect.left + 'px';
        } else {
            panel.style.right = (window.innerWidth - rect.right) + 'px';
        }
    }
}

function clearFilterPanel(btn) {
    var wrapper = btn.closest('.filter-multiselect');
    wrapper.querySelectorAll('input[type="checkbox"]').forEach(function(cb) { cb.checked = false; });
    _updateFilterLabel(wrapper);
}

function _closeFilterPanel(wrapper) {
    var panel = wrapper.querySelector('.filter-panel');
    if (!panel || panel.classList.contains('hidden')) return;
    panel.classList.add('hidden');
    var current = _filterGetChecked(panel);
    var initial = (panel.dataset.initial || '').split(',').filter(Boolean).sort();
    if (current.join(',') === initial.join(',')) return;
    var field = wrapper.dataset.field;
    // Send an empty sentinel so the server always sees the field, even with nothing checked
    var parts = [encodeURIComponent(field) + '='];
    current.forEach(function(v) { parts.push(encodeURIComponent(field) + '=' + encodeURIComponent(v)); });
    fetch('/profile/settings', {
        method: 'POST',
        headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
        body: parts.join('&'),
    }).then(function() { window.location.reload(); });
}

/* Outside click → close any open filter panel (triggers apply) */
document.addEventListener('click', function(e) {
    if (e.target.closest('.filter-multiselect')) return;
    document.querySelectorAll('.filter-multiselect').forEach(_closeFilterPanel);
});

/* Mousewheel scroll inside filter panels — nav's overflow-x:auto forces
   overflow-y to compute as auto (CSS spec), making it a scroll container
   that swallows wheel events from fixed-position child panels. */
document.addEventListener('wheel', function(e) {
    var panel = e.target.closest('.filter-panel');
    if (!panel || panel.classList.contains('hidden')) return;
    e.preventDefault();
    var delta = e.deltaY;
    if (e.deltaMode === 1) delta *= 28;
    panel.scrollTop += delta;
}, { passive: false });

/* Checkbox toggle inside a filter panel updates the button label live */
document.addEventListener('change', function(e) {
    if (e.target.type !== 'checkbox') return;
    var wrapper = e.target.closest('.filter-multiselect');
    if (wrapper) _updateFilterLabel(wrapper);
});

/* Initial label computation on page load */
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.filter-multiselect').forEach(_updateFilterLabel);
});

/* Hover background — reads hex from --hover-bg CSS variable and applies 0.2 opacity */
function _hoverBg() {
    var hex = getComputedStyle(document.documentElement).getPropertyValue('--hover-bg').trim();
    if (!hex || hex.length < 7) return 'rgba(128,128,128,0.2)';
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',0.2)';
}

/* Draggable popover utility — desktop only */
var _popoverDrag = { active: false, popover: null, handle: null, startX: 0, startY: 0, origLeft: 0, origTop: 0 };

function _makeDraggable(popover, handle) {
    if (window.innerWidth <= 768) return;
    handle.style.cursor = 'grab';
    handle.addEventListener('mousedown', function(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'BUTTON' || e.target.tagName === 'SELECT') return;
        var zoom = parseFloat(document.documentElement.style.zoom) || 1;
        var rect = popover.getBoundingClientRect();
        var left = rect.left / zoom;
        var top = rect.top / zoom;
        popover.style.transform = 'none';
        popover.style.left = left + 'px';
        popover.style.top = top + 'px';
        _popoverDrag.active = true;
        _popoverDrag.popover = popover;
        _popoverDrag.handle = handle;
        _popoverDrag.startX = e.clientX / zoom;
        _popoverDrag.startY = e.clientY / zoom;
        _popoverDrag.origLeft = left;
        _popoverDrag.origTop = top;
        handle.style.cursor = 'grabbing';
        e.preventDefault();
    });
}

document.addEventListener('mousemove', function(e) {
    if (!_popoverDrag.active) return;
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    _popoverDrag.popover.style.left = (_popoverDrag.origLeft + e.clientX / zoom - _popoverDrag.startX) + 'px';
    _popoverDrag.popover.style.top = (_popoverDrag.origTop + e.clientY / zoom - _popoverDrag.startY) + 'px';
});

document.addEventListener('mouseup', function() {
    if (!_popoverDrag.active) return;
    _popoverDrag.active = false;
    if (_popoverDrag.handle) _popoverDrag.handle.style.cursor = 'grab';
});

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

/* Generic confirm modal — non-destructive confirmations with a callback */
var _genericConfirmCallback = null;

function showConfirm(title, msg, onConfirm, btnLabel) {
    var modal = document.getElementById('generic-confirm-modal');
    if (!modal) { if (window.confirm(title + '\n\n' + msg) && onConfirm) onConfirm(); return; }
    _genericConfirmCallback = onConfirm || null;
    document.getElementById('generic-confirm-title').textContent = title;
    document.getElementById('generic-confirm-msg').textContent = msg || '';
    document.getElementById('generic-confirm-btn').textContent = btnLabel || 'Confirm';
    modal.style.display = 'flex';
}

document.addEventListener('DOMContentLoaded', function() {
    var modal = document.getElementById('generic-confirm-modal');
    if (!modal) return;
    document.getElementById('generic-confirm-cancel').addEventListener('click', function() {
        modal.style.display = 'none';
        _genericConfirmCallback = null;
    });
    document.getElementById('generic-confirm-btn').addEventListener('click', function() {
        modal.style.display = 'none';
        var cb = _genericConfirmCallback;
        _genericConfirmCallback = null;
        if (cb) cb();
    });
});

/* Copy a link to a page anchor (song or album) to the clipboard */
function copyAnchorLink(event, anchorId) {
    if (event) { event.stopPropagation(); event.preventDefault(); }
    var url = window.location.href.split('#')[0] + '#' + anchorId;
    function fallback() {
        var ta = document.createElement('textarea');
        ta.value = url;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); showToast('Link copied'); }
        catch (e) { showToast('Copy failed'); }
        document.body.removeChild(ta);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(function () { showToast('Link copied'); }).catch(fallback);
    } else {
        fallback();
    }
}

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
    document.querySelectorAll('.' + show).forEach(function (el) { el.classList.remove('hidden'); el.style.display = ''; });
    document.querySelectorAll('.' + hide).forEach(function (el) { el.classList.add('hidden'); el.style.display = ''; });
    document.cookie = 'stat_mode=' + val + '; path=/; max-age=31536000; SameSite=Lax';
}

function toggleHideUnrated(hide) {
    document.querySelectorAll('.unrated-cell').forEach(function(cell) {
        if (hide) {
            if (!cell.dataset.origText) cell.dataset.origText = cell.textContent.trim();
            cell.style.backgroundColor = '';
            cell.style.color = '';
            cell.textContent = '';
        } else {
            if (cell.dataset.origBg) cell.style.backgroundColor = cell.dataset.origBg;
            cell.style.color = 'var(--unrated-text)';
            cell.textContent = cell.dataset.origText || '';
        }
    });
    document.cookie = 'hide_unrated=' + (hide ? '1' : '0') + '; path=/; max-age=31536000; SameSite=Lax';
}

(function () {
    var sel = document.getElementById('stat-mode');
    if (!sel) return;
    var match = document.cookie.match(/(?:^|;\s*)stat_mode=([^;]+)/);
    if (match && match[1] !== sel.value) {
        sel.value = match[1];
        switchStatMode(match[1]);
    }
    // Restore hide-unrated state
    var cb = document.getElementById('hide-unrated');
    var hideMatch = document.cookie.match(/(?:^|;\s*)hide_unrated=([^;]+)/);
    if (cb && hideMatch && hideMatch[1] === '1') {
        cb.checked = true;
        toggleHideUnrated(true);
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

// Reusable drag-to-scroll
// opts.pageMode: scroll window instead of el.scrollLeft
// opts.xOnly: only scroll horizontally
// opts.allowLinks: allow drag to start on <a> elements (click suppressed if dragged)
var _activeDrag = null;
function _initDragScroll(el, opts) {
    var pageMode = opts && opts.pageMode;
    var xOnly = opts && opts.xOnly;
    var allowLinks = opts && opts.allowLinks;
    var state = { dragging: false, startX: 0, startY: 0, savedX: 0, savedY: 0, moved: false };

    el.addEventListener('mousedown', function(e) {
        if (e.button !== 0 || _activeDrag) return;
        if (e.target.closest('input, textarea, select, [contenteditable]')) return;
        if (!allowLinks && e.target.closest('a, button, [onclick]')) return;
        state.dragging = true;
        state.moved = false;
        state.startX = e.clientX;
        state.startY = e.clientY;
        state.savedX = pageMode ? window.scrollX : el.scrollLeft;
        state.savedY = pageMode ? window.scrollY : 0;
        _activeDrag = state;
        document.body.style.cursor = 'grabbing';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });

    document.addEventListener('mousemove', function(e) {
        if (_activeDrag !== state || !state.dragging) return;
        var dx = e.clientX - state.startX;
        var dy = e.clientY - state.startY;
        if (!state.moved && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
        state.moved = true;
        if (pageMode) {
            window.scrollTo(state.savedX - dx, xOnly ? window.scrollY : state.savedY - dy);
        } else {
            el.scrollLeft = state.savedX - dx;
        }
    });

    document.addEventListener('mouseup', function() {
        if (_activeDrag !== state || !state.dragging) return;
        state.dragging = false;
        _activeDrag = null;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        if (state.moved) {
            el.addEventListener('click', function suppress(e) {
                e.preventDefault();
                e.stopPropagation();
                el.removeEventListener('click', suppress, true);
            }, true);
        }
    });

    window.addEventListener('blur', function() {
        if (_activeDrag === state && state.dragging) {
            state.dragging = false;
            _activeDrag = null;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }
    });
}

// Artist bottom nav: drag to scroll its own scrollLeft
(function() {
    var nav = document.querySelector('.artist-nav');
    if (nav) _initDragScroll(nav, { allowLinks: true });
})();

// Top navbar: drag to scroll its own scrollLeft
(function() {
    var topNav = document.querySelector('nav');
    if (topNav) _initDragScroll(topNav, { allowLinks: true });
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
    if (input._dateFormatApplied) return;
    input._dateFormatApplied = true;
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
    if (input._dateFormatApplied) return;
    input._dateFormatApplied = true;
    input.type = 'text';
    input.placeholder = 'YYYY-MM-DD HH:MM';
    input.maxLength = 16;
    input.style.fontFamily = 'monospace';

    var updateGuide = _setupDateGuide(input, 'YYYY-MM-DD HH:MM');

    input.addEventListener('input', function() {
        var raw = this.value;
        var pos = this.selectionStart;

        // Only auto-format when typing at the end (new input, not mid-edit)
        if (pos < raw.length) { updateGuide(); return; }

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
    var root = e.detail.target || e.detail.elt;
    root.querySelectorAll('[data-date-format]').forEach(applyDateFormat);
    root.querySelectorAll('[data-datetime-format]').forEach(applyDateTimeFormat);
    formatUtcDates(root);

    // Update artist navbar active indicator after HTMX navigation
    var header = root.querySelector('[data-current-artist-id]');
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

    // Restore album/subunit collapse state after content swap
    if (typeof _restoreCollapseState === 'function') _restoreCollapseState();
});

// Force repaint on row after HTMX outerHTML swap to fix collapsed borders
document.addEventListener('htmx:afterSettle', function(e) {
    var elt = e.detail.elt;
    if (!elt) return;
    var cell = (elt.id && elt.id.startsWith('rating-')) ? elt
             : elt.querySelector('[id^="rating-"]');
    if (cell) {
        var row = cell.closest('tr');
        if (row && row.style.display !== 'none') {
            row.style.display = 'none'; row.offsetHeight; row.style.display = '';
        }
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
        if (!el) return;
        // Expand collapsed parent sections so the element is visible
        if (el.style.display === 'none') {
            // Expand child section if song is inside one
            var childClass = Array.from(el.classList).find(function(c) { return c.indexOf('child-row-') === 0; });
            if (childClass) {
                var childId = childClass.replace('child-row-', '');
                if (typeof _expandRows === 'function') _expandRows('child-row', childId);
                var state = (typeof _getCollapsed === 'function') ? _getCollapsed() : {};
                delete state['child-' + childId];
                if (typeof _saveCollapsed === 'function') _saveCollapsed(state);
            }
            // Expand album section if song is inside one
            var albumClass = Array.from(el.classList).find(function(c) { return c.indexOf('album-row-') === 0; });
            if (albumClass) {
                var albumId = albumClass.replace('album-row-', '');
                if (typeof _expandRows === 'function') _expandRows('album-row', albumId);
                var state2 = (typeof _getCollapsed === 'function') ? _getCollapsed() : {};
                delete state2['album-' + albumId];
                if (typeof _saveCollapsed === 'function') _saveCollapsed(state2);
            }
        }
        el.scrollIntoView({ block: 'center', behavior: 'smooth' });
        highlightRow(el);
    }
    window.addEventListener('load', highlightHash);
    window.addEventListener('hashchange', highlightHash);
})();

// Re-stripe visible table rows to maintain alternating background
function restripeTable(table) {
    if (!table) return;
    table.querySelectorAll('tbody tr').forEach(function (row, i) {
        row.style.backgroundColor = i % 2 === 1 ? 'var(--row-alternate)' : '';
    });
}

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
        restripeTable(btn.closest('table'));
    } else {
        fetch(btn.dataset.url)
            .then(function (r) { return r.text(); })
            .then(function (html) {
                btn.closest('tr').insertAdjacentHTML('afterend', html);
                btn.dataset.expanded = 'true';
                btn.classList.add('expanded');
                restripeTable(btn.closest('table'));
                var sel = document.getElementById('stat-mode');
                if (sel) switchStatMode(sel.value);
            });
    }
});

function handleSubscribeToggle(cb, artistId) {
    if (cb.checked) {
        fetch('/artist/' + artistId + '/unrated-count')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.unrated === 0) {
                    doSubscribe(cb, artistId);
                } else {
                    showSubscribeConfirm(cb, artistId, data);
                }
            })
            .catch(function() { doSubscribe(cb, artistId); });
    } else {
        doSubscribe(cb, artistId);
    }
}

function doSubscribe(cb, artistId) {
    fetch('/artist/' + artistId + '/subscribe', {method: 'POST', headers: _csrfHeaders()})
        .then(function(r) { if (!r.ok) cb.checked = !cb.checked; });
}

function showSubscribeConfirm(cb, artistId, data) {
    var existing = document.getElementById('subscribe-confirm-modal');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.id = 'subscribe-confirm-modal';
    overlay.className = 'fixed inset-0 flex items-center justify-center';
    overlay.style.cssText = 'background:rgba(0,0,0,0.5);z-index:100;';
    overlay.onclick = function(e) {
        if (e.target === overlay) { cb.checked = false; overlay.remove(); }
    };

    var box = document.createElement('div');
    box.className = 'bg-secondary-bg border border-border rounded-lg p-6';
    box.style.cssText = 'width:380px;max-width:90vw;';

    var title = document.createElement('h3');
    title.className = 'text-lg font-bold mb-2 text-primary-text';
    title.textContent = 'Subscribe';

    var msg = document.createElement('p');
    msg.className = 'text-sm mb-4 text-secondary-text';
    msg.style.whiteSpace = 'pre-line';
    msg.textContent = 'You have ' + data.unrated + ' unrated song' + (data.unrated !== 1 ? 's' : '') + ' out of ' + data.total + ' (with current filters).\nAre you sure you want to subscribe?';

    var btnRow = document.createElement('div');
    btnRow.className = 'flex gap-3 justify-end';

    var cancelBtn = document.createElement('button');
    cancelBtn.className = 'px-4 py-2 rounded text-sm text-primary-text';
    cancelBtn.style.backgroundColor = 'var(--button-secondary)';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.onclick = function() { cb.checked = false; overlay.remove(); };

    var confirmBtn = document.createElement('button');
    confirmBtn.className = 'px-4 py-2 rounded text-sm text-white';
    confirmBtn.style.backgroundColor = 'var(--link, #2563EB)';
    confirmBtn.textContent = 'Subscribe';
    confirmBtn.onclick = function() { overlay.remove(); doSubscribe(cb, artistId); };

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(confirmBtn);
    box.appendChild(title);
    box.appendChild(msg);
    box.appendChild(btnRow);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    confirmBtn.focus();

    overlay.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); confirmBtn.click(); }
        else if (e.key === 'Escape') { e.preventDefault(); cancelBtn.click(); }
    });
}
