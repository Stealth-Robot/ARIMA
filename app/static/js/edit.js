/* Inline text/date edit — edit mode only */

function updatePromotedStyle(checkbox) {
    var row = checkbox.closest('tr');
    var cell = row ? row.querySelector('td:first-child') : null;
    if (!cell) return;
    var tag = cell.querySelector('.promoted-tag');
    if (checkbox.checked) {
        cell.style.borderLeft = '4px solid var(--promoted-song)';
        if (!tag) {
            tag = document.createElement('span');
            tag.className = 'promoted-tag';
            tag.style.cssText = 'font-size:9px;padding:1px 5px;margin-left:4px;border-radius:3px;background-color:var(--promoted-song);color:var(--text-primary);';
            tag.textContent = 'promoted';
            cell.appendChild(tag);
        }
    } else {
        cell.style.borderLeft = '1px solid var(--grid-line)';
        if (tag) tag.remove();
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
        font-size: inherit; font-family: inherit; font-weight: inherit;
        padding: 0 2px;
        width: ${Math.max(80, span.offsetWidth + 20)}px;
        background: var(--bg-primary); color: var(--text-primary);
    `;

    span.replaceWith(input);
    var settled = false;
    setTimeout(function() { settled = true; }, 300);
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
            dateWrapper.replaceWith(newSpan);
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
            if (settled && document.activeElement !== input) restore();
        }, 200);
    });
}

function showInlineDateEdit(event, endpoint, span, currentFullDate) {
    event.stopPropagation();

    const original = span.textContent.trim();
    const input = document.createElement('input');
    input.value = currentFullDate || '';
    input.style.cssText = `
        border: 1px solid var(--link, #2563EB); border-radius: 2px;
        font-size: inherit; padding: 0 2px;
        background: var(--bg-primary); color: var(--text-primary);
        width: 100px;
    `;
    applyDateFormat(input);

    var dateWrapper = input._dateWrapper || input;
    span.replaceWith(dateWrapper);
    input.focus();

    var committed = false;
    function commit() {
        if (committed) return;
        committed = true;
        const val = input.value.trim();
        if (val && !/^\d{4}-\d{2}-\d{2}$/.test(val)) {
            input.style.borderColor = 'var(--delete-button, red)';
            committed = false;
            return;
        }
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
            var displayYear = text ? text.substring(0, 4) : 'date';
            const newSpan = document.createElement('span');
            newSpan.className = 'edit-inline';
            newSpan.style.cursor = 'pointer';
            newSpan.dataset.fullDate = text || '';
            if (!text) newSpan.style.color = 'var(--text-secondary)';
            newSpan.setAttribute('onclick', "showInlineDateEdit(event, '" + endpoint + "', this, this.dataset.fullDate)");
            newSpan.textContent = displayYear;
            dateWrapper.replaceWith(newSpan);
        });
    }

    function restore() {
        const newSpan = document.createElement('span');
        newSpan.className = 'edit-inline';
        newSpan.style.cursor = 'pointer';
        newSpan.dataset.fullDate = currentFullDate || '';
        if (!currentFullDate) newSpan.style.color = 'var(--text-secondary)';
        newSpan.setAttribute('onclick', "showInlineDateEdit(event, '" + endpoint + "', this, this.dataset.fullDate)");
        newSpan.textContent = original;
        dateWrapper.replaceWith(newSpan);
    }

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); commit(); }
        else if (e.key === 'Escape') { e.preventDefault(); restore(); }
    });

    input.addEventListener('change', function() { commit(); });

    input.addEventListener('blur', function() {
        setTimeout(function() {
            if (document.activeElement !== input) restore();
        }, 300);
    });
}

/* Inline genre edit — checkbox popover */

var activeGenrePopover = null;

function closeGenrePopover() {
    if (activeGenrePopover) {
        activeGenrePopover.remove();
        activeGenrePopover = null;
    }
}

function showGenreEdit(event, albumId, span, allGenres, currentIds) {
    event.stopPropagation();
    closeGenrePopover();

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:180px; max-height:240px; overflow-y:auto;';

    var selected = currentIds.slice();

    allGenres.forEach(function(g) {
        var label = document.createElement('label');
        label.style.cssText = 'display:block; font-size:12px; padding:2px 0; cursor:pointer;';
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = g.id;
        cb.checked = selected.indexOf(g.id) !== -1;
        cb.style.marginRight = '4px';
        cb.addEventListener('change', function() {
            if (this.checked) { selected.push(g.id); }
            else { selected = selected.filter(function(x) { return x !== g.id; }); }
        });
        label.appendChild(cb);
        label.appendChild(document.createTextNode(g.name));
        popover.appendChild(label);
    });

    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex; gap:4px; margin-top:6px; justify-content:flex-end;';

    var saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'padding:2px 10px; font-size:12px; background:var(--link,#2563EB); color:#fff; border:none; border-radius:3px; cursor:pointer;';
    saveBtn.onclick = function() {
        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
        var ids = [];
        popover.querySelectorAll('input[type="checkbox"]:checked').forEach(function(cb) {
            ids.push(parseInt(cb.value));
        });
        fetch('/edit/album/' + albumId + '/genres', {
            method: 'POST',
            headers: headers,
            body: 'genre_ids=' + encodeURIComponent(ids.join(',')),
        }).then(function(r) {
            if (!r.ok) throw new Error('save failed');
            return r.json();
        }).then(function(names) {
            span.textContent = names.length ? names.join(', ') : 'genres';
            if (!names.length) span.style.color = 'var(--text-secondary)';
            else span.style.color = '';
            span.setAttribute('data-genre-ids', JSON.stringify(ids));
            closeGenrePopover();
        }).catch(function() {
            showToast('Failed to save genres — try again');
            closeGenrePopover();
        });
    };

    var cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'padding:2px 10px; font-size:12px; background:#6B7280; color:#fff; border:none; border-radius:3px; cursor:pointer;';
    cancelBtn.onclick = closeGenrePopover;

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    popover.appendChild(btnRow);

    var rect = getZoomedRect(span);
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    if (rect.bottom + 2 + popover.offsetHeight + 30 > viewH) {
        popover.style.top = Math.max(0, viewH - popover.offsetHeight - 30) + 'px';
    } else {
        popover.style.top = rect.bottom + 2 + 'px';
    }
    activeGenrePopover = popover;
}

document.addEventListener('click', function(e) {
    if (activeGenrePopover && !activeGenrePopover.contains(e.target)) {
        closeGenrePopover();
    }
});

/* Inline country edit — dropdown popover */

var activeCountryPopover = null;

function closeCountryPopover() {
    if (activeCountryPopover) {
        activeCountryPopover.remove();
        activeCountryPopover = null;
    }
}

function showCountryEdit(event, artistId, span, allCountries, currentId) {
    event.stopPropagation();
    closeCountryPopover();

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:180px; max-height:240px; overflow-y:auto;';

    allCountries.forEach(function(c) {
        var btn = document.createElement('div');
        btn.textContent = c.name;
        btn.style.cssText = 'padding:3px 6px; font-size:12px; cursor:pointer; border-radius:2px;';
        if (c.id === currentId) btn.style.fontWeight = 'bold';
        btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
        btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
        btn.addEventListener('click', function() {
            var csrfToken = document.querySelector('meta[name="csrf-token"]');
            var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
            if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
            fetch('/edit/artist/' + artistId + '/country', {
                method: 'POST',
                headers: headers,
                body: 'country_id=' + c.id,
            }).then(function(r) {
                if (!r.ok) throw new Error('save failed');
                return r.json();
            }).then(function(data) {
                span.textContent = data.country;
                span.setAttribute('data-country-id', data.id);
                closeCountryPopover();
            }).catch(function() {
                showToast('Failed to save country — try again');
                closeCountryPopover();
            });
        });
        popover.appendChild(btn);
    });

    var rect = getZoomedRect(span);
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    if (rect.bottom + 2 + popover.offsetHeight + 30 > viewH) {
        popover.style.top = Math.max(0, viewH - popover.offsetHeight - 30) + 'px';
    } else {
        popover.style.top = rect.bottom + 2 + 'px';
    }
    activeCountryPopover = popover;
}

document.addEventListener('click', function(e) {
    if (activeCountryPopover && !activeCountryPopover.contains(e.target)) {
        closeCountryPopover();
    }
    if (activeGenderPopover && !activeGenderPopover.contains(e.target)) {
        closeGenderPopover();
    }
});

/* Inline gender edit — pick gender popover */

var activeGenderPopover = null;
var GENDER_CSS_MAP = {0: '--gender-female', 1: '--gender-male', 2: '--gender-mixed', 3: '--gender-anime'};

function closeGenderPopover() {
    if (activeGenderPopover) {
        activeGenderPopover.remove();
        activeGenderPopover = null;
    }
}

function showGenderEdit(event, artistId, span, allGenders, currentId) {
    event.stopPropagation();
    closeGenderPopover();

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:180px; max-height:240px; overflow-y:auto;';

    allGenders.forEach(function(g) {
        var btn = document.createElement('div');
        btn.textContent = g.name;
        btn.style.cssText = 'padding:3px 6px; font-size:12px; cursor:pointer; border-radius:2px;';
        if (g.id === currentId) btn.style.fontWeight = 'bold';
        btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
        btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
        btn.addEventListener('click', function() {
            var csrfToken = document.querySelector('meta[name="csrf-token"]');
            var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
            if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
            fetch('/edit/artist/' + artistId + '/gender', {
                method: 'POST',
                headers: headers,
                body: 'gender_id=' + g.id,
            }).then(function(r) {
                if (!r.ok) throw new Error('save failed');
                return r.json();
            }).then(function(data) {
                span.textContent = data.gender;
                span.setAttribute('data-gender-id', data.id);
                var cssVar = GENDER_CSS_MAP[data.id] || '--text-primary';
                var headerDiv = span.closest('div[style*="border-left"]');
                if (headerDiv) {
                    headerDiv.style.borderLeftColor = 'var(' + cssVar + ')';
                }
                document.querySelectorAll('[data-artist-id="' + artistId + '"]').forEach(function(el) {
                    el.style.backgroundColor = 'var(' + cssVar + ')';
                });
                closeGenderPopover();
            }).catch(function() {
                showToast('Failed to save gender — try again');
                closeGenderPopover();
            });
        });
        popover.appendChild(btn);
    });

    var rect = getZoomedRect(span);
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    if (rect.bottom + 2 + popover.offsetHeight + 30 > viewH) {
        popover.style.top = Math.max(0, viewH - popover.offsetHeight - 30) + 'px';
    } else {
        popover.style.top = rect.bottom + 2 + 'px';
    }
    activeGenderPopover = popover;
}

/* Global Escape handler — closes all popovers and modals */
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        closeArtistMenu();
        closeAlbumMovePopover();
        closeAlbumAddPopover();
        closeAlbumSongSearchPopover();
        closeSongArtistPopover();
        closeMergePopover();
        closeSearchOverlay();
        var deleteModal = document.getElementById('confirm-delete-modal');
        if (deleteModal) deleteModal.style.display = 'none';
        var addAlbumModal = document.getElementById('add-album-modal');
        if (addAlbumModal) addAlbumModal.style.display = 'none';
        var convertModal = document.getElementById('convert-artist-modal');
        if (convertModal) convertModal.style.display = 'none';
    }
});
/* Inline album move — pick album popover */

var activeAlbumMovePopover = null;

function closeAlbumMovePopover() {
    if (activeAlbumMovePopover) {
        activeAlbumMovePopover.remove();
        activeAlbumMovePopover = null;
    }
}

function showAlbumMove(event, songId, span, allAlbums, currentAlbumId) {
    event.stopPropagation();
    closeAlbumMovePopover();
    closeAlbumAddPopover();
    closeAlbumSongSearchPopover();

    var others = allAlbums.filter(function(a) { return a.id !== currentAlbumId; });
    if (!others.length) {
        showToast('No other albums to move to');
        return;
    }

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:280px; max-height:320px; display:flex; flex-direction:column;';

    var title = document.createElement('div');
    title.textContent = 'Move to album:';
    title.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:4px; color:var(--text-secondary);';
    popover.appendChild(title);

    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search albums or artists...';
    searchInput.style.cssText = 'width:100%; font-size:11px; padding:4px 6px; margin-bottom:6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box;';
    popover.appendChild(searchInput);

    var listContainer = document.createElement('div');
    listContainer.style.cssText = 'overflow-y:auto; flex:1;';
    popover.appendChild(listContainer);

    function renderList(filter) {
        listContainer.innerHTML = '';
        var lc = (filter || '').toLowerCase();
        var parentMap = (typeof _artistParentMap !== 'undefined') ? _artistParentMap : {};
        // Group albums: merge children into their parent group, dedup preferring child entry
        var grouped = {};
        var groupOrder = [];
        var entryMap = {};
        others.forEach(function(a) {
            var group = parentMap[a.artist] || a.artist;
            if (lc && a.name.toLowerCase().indexOf(lc) === -1 && a.artist.toLowerCase().indexOf(lc) === -1 && group.toLowerCase().indexOf(lc) === -1) return;
            var isChild = a.artist !== group;
            var key = group + '::' + a.id;
            if (entryMap[key] && !isChild) return;
            var label = isChild ? a.name + ' (' + a.artist + ')' : a.name;
            var entry = { id: a.id, label: label, subgroup: isChild ? a.artist : '' };
            if (entryMap[key]) {
                var arr = grouped[group];
                for (var i = 0; i < arr.length; i++) { if (arr[i].id === a.id) { arr[i] = entry; break; } }
            } else {
                if (!grouped[group]) { grouped[group] = []; groupOrder.push(group); }
                grouped[group].push(entry);
            }
            entryMap[key] = true;
        });
        // Sort: current artist first, Misc. Artists second, rest alphabetical
        var currentArtistName = null;
        others.forEach(function(a) { if (a.artistId === _currentArtistId) currentArtistName = a.artist; });
        // Also treat parent of current artist as current
        if (!currentArtistName && parentMap[others[0] && others[0].artist]) {
            others.forEach(function(a) { if (a.artistId === _currentArtistId) currentArtistName = parentMap[a.artist] || a.artist; });
        }
        // Fallback: use the page's artist name (for parent artists with no direct albums)
        if (!currentArtistName && typeof _pageArtistName !== 'undefined') currentArtistName = _pageArtistName;
        groupOrder.sort(function(a, b) {
            var aIsMisc = a === 'Misc. Artists' && a !== currentArtistName;
            var bIsMisc = b === 'Misc. Artists' && b !== currentArtistName;
            var aRank = a === currentArtistName ? 0 : aIsMisc ? 2 : 1;
            var bRank = b === currentArtistName ? 0 : bIsMisc ? 2 : 1;
            if (aRank !== bRank) return aRank - bRank;
            return a.toLowerCase() < b.toLowerCase() ? -1 : a.toLowerCase() > b.toLowerCase() ? 1 : 0;
        });
        groupOrder.forEach(function(group) {
            var header = document.createElement('div');
            header.textContent = group;
            header.style.cssText = 'font-size:10px; font-weight:bold; padding:4px 6px 2px; color:var(--text-secondary); text-transform:uppercase;';
            listContainer.appendChild(header);
            // Sort: parent albums first, then children grouped by subunit
            grouped[group].sort(function(a, b) {
                if (!a.subgroup && b.subgroup) return -1;
                if (a.subgroup && !b.subgroup) return 1;
                if (a.subgroup !== b.subgroup) return a.subgroup.toLowerCase() < b.subgroup.toLowerCase() ? -1 : 1;
                return a.label.toLowerCase() < b.label.toLowerCase() ? -1 : a.label.toLowerCase() > b.label.toLowerCase() ? 1 : 0;
            });
            grouped[group].forEach(function(item) {
                var btn = document.createElement('div');
                btn.textContent = item.label;
                btn.style.cssText = 'padding:3px 6px 3px 14px; font-size:12px; cursor:pointer; border-radius:2px;';
                btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
                btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
                btn.addEventListener('click', function() {
                    var csrfToken = document.querySelector('meta[name="csrf-token"]');
                    var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
                    if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
                    fetch('/edit/song/' + songId + '/move-album', {
                        method: 'POST',
                        headers: headers,
                        body: 'album_id=' + item.id,
                    }).then(function(r) {
                        if (!r.ok) throw new Error('move failed');
                        return r.json();
                    }).then(function() {
                        closeAlbumMovePopover();
                        window.location.reload();
                    }).catch(function() {
                        showToast('Failed to move song — try again');
                        closeAlbumMovePopover();
                    });
                });
                listContainer.appendChild(btn);
            });
        });
        if (!groupOrder.length) {
            var empty = document.createElement('div');
            empty.textContent = 'No matches';
            empty.style.cssText = 'font-size:11px; color:var(--text-secondary); padding:6px;';
            listContainer.appendChild(empty);
        }
    }

    renderList('');
    searchInput.addEventListener('input', function() { renderList(searchInput.value); });

    var rect = getZoomedRect(span);
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    if (rect.bottom + 2 + popover.offsetHeight + 30 > viewH) {
        popover.style.top = Math.max(0, viewH - popover.offsetHeight - 30) + 'px';
    } else {
        popover.style.top = rect.bottom + 2 + 'px';
    }
    activeAlbumMovePopover = popover;
    searchInput.focus();
}

/* Add song to additional album popover */

var activeAlbumAddPopover = null;

function closeAlbumAddPopover() {
    if (activeAlbumAddPopover) {
        activeAlbumAddPopover.remove();
        activeAlbumAddPopover = null;
    }
}

function showAlbumAdd(event, songId, span, allAlbums, currentAlbumId) {
    event.stopPropagation();
    closeAlbumAddPopover();
    closeAlbumMovePopover();
    closeAlbumSongSearchPopover();

    var others = allAlbums.filter(function(a) { return a.id !== currentAlbumId; });
    if (!others.length) {
        showToast('No other albums available');
        return;
    }

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:280px; max-height:320px; display:flex; flex-direction:column;';

    var title = document.createElement('div');
    title.textContent = 'Add to album:';
    title.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:4px; color:var(--text-secondary);';
    popover.appendChild(title);

    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search albums or artists...';
    searchInput.style.cssText = 'width:100%; font-size:11px; padding:4px 6px; margin-bottom:6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box;';
    popover.appendChild(searchInput);

    var listContainer = document.createElement('div');
    listContainer.style.cssText = 'overflow-y:auto; flex:1;';
    popover.appendChild(listContainer);

    function renderList(filter) {
        listContainer.innerHTML = '';
        var lc = (filter || '').toLowerCase();
        var parentMap = (typeof _artistParentMap !== 'undefined') ? _artistParentMap : {};
        var grouped = {};
        var groupOrder = [];
        var entryMap = {};
        others.forEach(function(a) {
            var group = parentMap[a.artist] || a.artist;
            if (lc && a.name.toLowerCase().indexOf(lc) === -1 && a.artist.toLowerCase().indexOf(lc) === -1 && group.toLowerCase().indexOf(lc) === -1) return;
            var isChild = a.artist !== group;
            var key = group + '::' + a.id;
            if (entryMap[key] && !isChild) return;
            var label = isChild ? a.name + ' (' + a.artist + ')' : a.name;
            var entry = { id: a.id, label: label, subgroup: isChild ? a.artist : '' };
            if (entryMap[key]) {
                var arr = grouped[group];
                for (var i = 0; i < arr.length; i++) { if (arr[i].id === a.id) { arr[i] = entry; break; } }
            } else {
                if (!grouped[group]) { grouped[group] = []; groupOrder.push(group); }
                grouped[group].push(entry);
            }
            entryMap[key] = true;
        });
        var currentArtistName = null;
        others.forEach(function(a) { if (a.artistId === _currentArtistId) currentArtistName = a.artist; });
        if (!currentArtistName && parentMap[others[0] && others[0].artist]) {
            others.forEach(function(a) { if (a.artistId === _currentArtistId) currentArtistName = parentMap[a.artist] || a.artist; });
        }
        groupOrder.sort(function(a, b) {
            var aIsMisc = a === 'Misc. Artists' && a !== currentArtistName;
            var bIsMisc = b === 'Misc. Artists' && b !== currentArtistName;
            var aRank = a === currentArtistName ? 0 : aIsMisc ? 2 : 1;
            var bRank = b === currentArtistName ? 0 : bIsMisc ? 2 : 1;
            if (aRank !== bRank) return aRank - bRank;
            return a.toLowerCase() < b.toLowerCase() ? -1 : a.toLowerCase() > b.toLowerCase() ? 1 : 0;
        });
        groupOrder.forEach(function(group) {
            var header = document.createElement('div');
            header.textContent = group;
            header.style.cssText = 'font-size:10px; font-weight:bold; padding:4px 6px 2px; color:var(--text-secondary); text-transform:uppercase;';
            listContainer.appendChild(header);
            grouped[group].sort(function(a, b) {
                if (!a.subgroup && b.subgroup) return -1;
                if (a.subgroup && !b.subgroup) return 1;
                if (a.subgroup !== b.subgroup) return a.subgroup.toLowerCase() < b.subgroup.toLowerCase() ? -1 : 1;
                return a.label.toLowerCase() < b.label.toLowerCase() ? -1 : a.label.toLowerCase() > b.label.toLowerCase() ? 1 : 0;
            });
            grouped[group].forEach(function(item) {
                var btn = document.createElement('div');
                btn.textContent = item.label;
                btn.style.cssText = 'padding:3px 6px 3px 14px; font-size:12px; cursor:pointer; border-radius:2px;';
                btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
                btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
                btn.addEventListener('click', function() {
                    var csrfToken = document.querySelector('meta[name="csrf-token"]');
                    var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
                    if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
                    fetch('/edit/song/' + songId + '/add-to-album', {
                        method: 'POST',
                        headers: headers,
                        body: 'album_id=' + item.id,
                    }).then(function(r) {
                        if (r.status === 400) return r.json().then(function(d) { showToast(d.error || 'Failed'); throw new Error('bad'); });
                        if (!r.ok) throw new Error('failed');
                        return r.json();
                    }).then(function() {
                        closeAlbumAddPopover();
                        window.location.reload();
                    }).catch(function() {
                        closeAlbumAddPopover();
                    });
                });
                listContainer.appendChild(btn);
            });
        });
        if (!groupOrder.length) {
            var empty = document.createElement('div');
            empty.textContent = 'No matches';
            empty.style.cssText = 'font-size:11px; color:var(--text-secondary); padding:6px;';
            listContainer.appendChild(empty);
        }
    }

    renderList('');
    searchInput.addEventListener('input', function() { renderList(searchInput.value); });

    var rect = getZoomedRect(span);
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    if (rect.bottom + 2 + popover.offsetHeight + 30 > viewH) {
        popover.style.top = Math.max(0, viewH - popover.offsetHeight - 30) + 'px';
    } else {
        popover.style.top = rect.bottom + 2 + 'px';
    }
    activeAlbumAddPopover = popover;
    searchInput.focus();
}

/* Add existing song to album (search popover) */

var activeAlbumSongSearchPopover = null;

function closeAlbumSongSearchPopover() {
    if (activeAlbumSongSearchPopover) {
        activeAlbumSongSearchPopover.remove();
        activeAlbumSongSearchPopover = null;
    }
}

function showAlbumSongSearch(event, albumId, artistId, span) {
    event.stopPropagation();
    closeAlbumSongSearchPopover();
    closeAlbumMovePopover();
    closeAlbumAddPopover();

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:320px; max-height:360px; display:flex; flex-direction:column;';

    var title = document.createElement('div');
    title.textContent = 'Add song to album:';
    title.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:4px; color:var(--text-secondary);';
    popover.appendChild(title);

    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search existing or type new song name...';
    searchInput.style.cssText = 'width:100%; font-size:11px; padding:4px 6px; margin-bottom:6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box;';
    popover.appendChild(searchInput);

    var listContainer = document.createElement('div');
    listContainer.style.cssText = 'overflow-y:auto; flex:1;';
    popover.appendChild(listContainer);

    var debounceTimer = null;

    var _createSongNum = 0;

    function showCreateSongForm(name) {
        // Switch popover to creation mode
        listContainer.innerHTML = '';
        searchInput.style.display = 'none';
        title.textContent = 'Create new song:';
        popover.style.width = '380px';

        _createSongNum++;
        var sn = _createSongNum;

        var form = document.createElement('div');

        // Song name
        var nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.value = name;
        nameInput.placeholder = 'Song name';
        nameInput.className = 'create-song-name';
        nameInput.style.cssText = 'width:100%; font-size:12px; padding:4px 6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box; margin-bottom:6px;';
        form.appendChild(nameInput);

        // Checkboxes row
        var cbRow = document.createElement('div');
        cbRow.style.cssText = 'display:flex; gap:10px; margin-bottom:6px;';
        cbRow.innerHTML =
            '<label style="font-size:11px; cursor:pointer;"><input type="checkbox" class="create-song-promoted" style="margin-right:2px;"> Promoted</label>' +
            '<label style="font-size:11px; cursor:pointer;"><input type="checkbox" class="create-song-remix" style="margin-right:2px;"> Remix</label>';
        form.appendChild(cbRow);

        // Artists section
        var artistLabel = document.createElement('div');
        artistLabel.style.cssText = 'font-size:10px; font-weight:bold; color:var(--text-secondary); margin-bottom:3px;';
        artistLabel.textContent = 'Artists:';
        form.appendChild(artistLabel);

        var artistContainer = document.createElement('div');
        artistContainer.id = 'create-song-artists-' + sn;
        artistContainer.style.cssText = 'margin-bottom:4px;';
        form.appendChild(artistContainer);

        // Artist dropdown
        var artistSelect = document.createElement('select');
        artistSelect.style.cssText = 'font-size:11px; padding:2px 4px; border:1px solid var(--border,#ccc); border-radius:3px; margin-bottom:8px;';
        function refreshArtistSelect() {
            var used = [];
            artistContainer.querySelectorAll('.create-artist-row').forEach(function(r) {
                if (r.dataset.artistId) used.push(parseInt(r.dataset.artistId));
            });
            var opts = '<option value="">+ Add artist...</option>';
            if (typeof _allArtists !== 'undefined') {
                _allArtists.forEach(function(a) {
                    if (used.indexOf(a.id) === -1) {
                        opts += '<option value="' + a.id + '">' + a.name.replace(/</g, '&lt;') + '</option>';
                    }
                });
            }
            artistSelect.innerHTML = opts;
            artistSelect.value = '';
        }

        function addArtistRow(aid, aname, isMain) {
            var row = document.createElement('div');
            row.className = 'create-artist-row';
            row.dataset.artistId = aid;
            row.style.cssText = 'display:flex; align-items:center; gap:4px; margin-bottom:2px;';
            var nameSpan = document.createElement('span');
            nameSpan.textContent = aname;
            nameSpan.style.cssText = 'font-size:11px;';
            row.appendChild(nameSpan);
            var roleSelect = document.createElement('select');
            roleSelect.className = 'create-artist-role';
            roleSelect.style.cssText = 'font-size:10px; padding:1px 3px; border:1px solid var(--border,#ccc); border-radius:3px;';
            roleSelect.innerHTML = '<option value="main"' + (isMain ? ' selected' : '') + '>Main</option>' +
                                   '<option value="feat"' + (!isMain ? ' selected' : '') + '>Featured</option>';
            row.appendChild(roleSelect);
            if (artistContainer.children.length > 0) {
                var removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.textContent = 'x';
                removeBtn.style.cssText = 'font-size:10px; color:var(--delete-button,#DC2626); cursor:pointer; background:none; border:none; padding:0 2px;';
                removeBtn.addEventListener('click', function() { row.remove(); refreshArtistSelect(); });
                row.appendChild(removeBtn);
            }
            artistContainer.appendChild(row);
            refreshArtistSelect();
        }

        artistSelect.addEventListener('change', function() {
            var id = parseInt(artistSelect.value);
            if (!id) return;
            var artist = _allArtists.find(function(a) { return a.id === id; });
            if (artist) addArtistRow(id, artist.name, false);
        });
        form.appendChild(artistSelect);

        // Auto-add current artist as main
        var currentName = 'Current Artist';
        if (typeof _allArtists !== 'undefined') {
            var found = _allArtists.find(function(a) { return a.id === artistId; });
            if (found) currentName = found.name;
        }
        addArtistRow(artistId, currentName, true);

        // Buttons row
        var btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex; gap:6px; justify-content:flex-end;';
        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.textContent = 'Back';
        cancelBtn.style.cssText = 'font-size:11px; padding:4px 10px; border-radius:3px; background:var(--button-secondary,#e5e7eb); color:var(--text-primary); border:none; cursor:pointer;';
        cancelBtn.addEventListener('click', function() {
            searchInput.style.display = '';
            title.textContent = 'Add song to album:';
            popover.style.width = '320px';
            doSearch(searchInput.value.trim());
        });
        btnRow.appendChild(cancelBtn);
        var submitBtn = document.createElement('button');
        submitBtn.type = 'button';
        submitBtn.textContent = 'Create Song';
        submitBtn.style.cssText = 'font-size:11px; padding:4px 10px; border-radius:3px; background:var(--edit-on-button,#2563EB); color:var(--button-text,#fff); border:none; cursor:pointer;';
        submitBtn.addEventListener('click', function() {
            var songName = form.querySelector('.create-song-name').value.trim();
            if (!songName) { showToast('Song name is required'); return; }
            var artists = [];
            artistContainer.querySelectorAll('.create-artist-row').forEach(function(row) {
                var role = row.querySelector('.create-artist-role');
                artists.push({ artist_id: parseInt(row.dataset.artistId), is_main: role.value === 'main' });
            });
            if (!artists.length || !artists.some(function(a) { return a.is_main; })) {
                showToast('At least one main artist is required'); return;
            }
            var csrfToken = document.querySelector('meta[name="csrf-token"]');
            var headers = { 'Content-Type': 'application/json' };
            if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
            fetch('/edit/album/' + albumId + '/create-song', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    name: songName,
                    artists: artists,
                    is_promoted: form.querySelector('.create-song-promoted').checked,
                    is_remix: form.querySelector('.create-song-remix').checked,
                }),
            }).then(function(r) {
                if (r.status === 400) return r.json().then(function(d) { showToast(d.error || 'Failed'); throw new Error('bad'); });
                if (!r.ok) throw new Error('failed');
                return r.json();
            }).then(function() {
                closeAlbumSongSearchPopover();
                window.location.reload();
            }).catch(function(err) {
                if (err && err.message !== 'bad') {
                    showToast('Error creating song');
                    console.error('Create song error:', err);
                }
            });
        });
        btnRow.appendChild(submitBtn);
        form.appendChild(btnRow);

        listContainer.appendChild(form);
        nameInput.focus();
        nameInput.select();
    }

    function doSearch(query) {
        if (query.length < 2) {
            listContainer.innerHTML = '<div style="font-size:11px; color:var(--text-secondary); padding:6px;">Type at least 2 characters...</div>';
            return;
        }
        fetch('/edit/album/' + albumId + '/search-songs?q=' + encodeURIComponent(query))
            .then(function(r) { if (!r.ok) throw new Error(); return r.json(); })
            .then(function(results) {
                listContainer.innerHTML = '';
                // Always show create-new option at the top
                var createBtn = document.createElement('div');
                createBtn.style.cssText = 'padding:4px 6px; font-size:12px; cursor:pointer; border-radius:2px; border-bottom:1px solid var(--border,#ccc); padding-bottom:6px; margin-bottom:4px;';
                var plus = document.createElement('span');
                plus.textContent = '+ Create "' + query + '"';
                plus.style.cssText = 'color:var(--link,#2563EB); font-weight:bold;';
                createBtn.appendChild(plus);
                createBtn.addEventListener('mouseenter', function() { createBtn.style.background = _hoverBg(); });
                createBtn.addEventListener('mouseleave', function() { createBtn.style.background = ''; });
                createBtn.addEventListener('click', function(e) { e.stopPropagation(); showCreateSongForm(query); });
                listContainer.appendChild(createBtn);
                if (!results.length) {
                    var empty = document.createElement('div');
                    empty.textContent = 'No existing songs found';
                    empty.style.cssText = 'font-size:11px; color:var(--text-secondary); padding:6px;';
                    listContainer.appendChild(empty);
                    return;
                }
                var divider = document.createElement('div');
                divider.textContent = 'Or add existing:';
                divider.style.cssText = 'font-size:10px; font-weight:bold; color:var(--text-secondary); padding:4px 6px 2px;';
                listContainer.appendChild(divider);
                results.forEach(function(item) {
                    var btn = document.createElement('div');
                    btn.style.cssText = 'padding:4px 6px; font-size:12px; cursor:pointer; border-radius:2px;';
                    var nameSpan = document.createElement('span');
                    nameSpan.textContent = item.name;
                    btn.appendChild(nameSpan);
                    var detailSpan = document.createElement('span');
                    detailSpan.textContent = ' — ' + item.artist + ' / ' + item.album;
                    detailSpan.style.cssText = 'color:var(--text-secondary); font-size:11px;';
                    btn.appendChild(detailSpan);
                    btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
                    btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
                    btn.addEventListener('click', function() {
                        var csrfToken = document.querySelector('meta[name="csrf-token"]');
                        var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
                        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
                        fetch('/edit/album/' + albumId + '/add-song', {
                            method: 'POST',
                            headers: headers,
                            body: 'song_id=' + item.id + '&artist_id=' + (typeof _currentArtistId !== 'undefined' ? _currentArtistId : ''),
                        }).then(function(r) {
                            if (r.status === 400) return r.json().then(function(d) { showToast(d.error || 'Failed'); throw new Error('bad'); });
                            if (!r.ok) throw new Error('failed');
                            return r.json();
                        }).then(function() {
                            closeAlbumSongSearchPopover();
                            window.location.reload();
                        }).catch(function() {
                            closeAlbumSongSearchPopover();
                        });
                    });
                    listContainer.appendChild(btn);
                });
            })
            .catch(function() {
                listContainer.innerHTML = '<div style="font-size:11px; color:var(--text-secondary); padding:6px;">Search failed</div>';
            });
    }

    listContainer.innerHTML = '<div style="font-size:11px; color:var(--text-secondary); padding:6px;">Type at least 2 characters...</div>';

    searchInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function() { doSearch(searchInput.value.trim()); }, 250);
    });

    var rect = getZoomedRect(span);
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    if (rect.bottom + 2 + popover.offsetHeight + 30 > viewH) {
        popover.style.top = Math.max(0, viewH - popover.offsetHeight - 30) + 'px';
    } else {
        popover.style.top = rect.bottom + 2 + 'px';
    }
    activeAlbumSongSearchPopover = popover;
    searchInput.focus();
}

document.addEventListener('click', function(e) {
    if (activeAlbumMovePopover && !activeAlbumMovePopover.contains(e.target)) {
        closeAlbumMovePopover();
    }
    if (activeAlbumAddPopover && !activeAlbumAddPopover.contains(e.target)) {
        closeAlbumAddPopover();
    }
    if (activeAlbumSongSearchPopover && !activeAlbumSongSearchPopover.contains(e.target)) {
        closeAlbumSongSearchPopover();
    }
    if (activeSongArtistPopover && !activeSongArtistPopover.contains(e.target)) {
        closeSongArtistPopover();
    }
    if (activeMergePopover && !activeMergePopover.contains(e.target)) {
        closeMergePopover();
    }
});

/* Song merge popover */

var activeMergePopover = null;

function closeMergePopover() {
    if (activeMergePopover) {
        activeMergePopover.remove();
        activeMergePopover = null;
    }
}

document.addEventListener('click', function(e) {
    var btn = e.target.closest('.merge-btn');
    if (!btn) return;
    e.stopPropagation();
    var songId = parseInt(btn.dataset.songId);
    var songName = btn.dataset.songName;
    _openMergePopover(songId, songName, btn);
});

function _openMergePopover(songId, songName, span) {
    event.stopPropagation();
    closeMergePopover();

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:340px; max-height:360px; display:flex; flex-direction:column;';

    var title = document.createElement('div');
    title.textContent = 'Merge into "' + songName + '":';
    title.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:4px; color:var(--text-secondary);';
    popover.appendChild(title);

    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search songs...';
    searchInput.style.cssText = 'width:100%; font-size:11px; padding:4px 6px; margin-bottom:6px; border:1px solid var(--border,#ccc); border-radius:3px; background:var(--bg-primary,#fff); color:var(--text-primary,#000); box-sizing:border-box;';
    popover.appendChild(searchInput);

    var listContainer = document.createElement('div');
    listContainer.style.cssText = 'overflow-y:auto; flex:1;';
    popover.appendChild(listContainer);

    var searchMode = false;
    var searchTimer = null;
    var candidates = null;

    function renderResults(items) {
        listContainer.innerHTML = '';
        if (!items || !items.length) {
            var empty = document.createElement('div');
            empty.textContent = 'No matching songs found.';
            empty.style.cssText = 'font-size:11px; color:var(--text-secondary); padding:6px;';
            listContainer.appendChild(empty);
            return;
        }
        items.forEach(function(item) {
            var btn = document.createElement('div');
            btn.textContent = item.name + ' \u2014 ' + item.artist + ' (' + item.album + ')';
            btn.style.cssText = 'padding:4px 6px; font-size:11px; cursor:pointer; border-radius:2px;';
            btn.addEventListener('mouseenter', function() { btn.style.background = _hoverBg(); });
            btn.addEventListener('mouseleave', function() { btn.style.background = ''; });
            btn.addEventListener('click', function() {
                closeMergePopover();
                showMergeConfirm(songId, songName, item.id, item.name, item.artist, item.album);
            });
            listContainer.appendChild(btn);
        });
    }

    // Load default candidates
    listContainer.innerHTML = '<div style="font-size:11px; color:var(--text-secondary); padding:6px;">Loading...</div>';
    fetch('/edit/song/' + songId + '/merge-candidates', {
        headers: _csrfHeaders({})
    }).then(function(r) { return r.json(); }).then(function(data) {
        candidates = data;
        if (!searchMode) renderResults(candidates);
    }).catch(function() {
        listContainer.innerHTML = '<div style="font-size:11px; color:var(--text-secondary); padding:6px;">Failed to load candidates</div>';
    });

    searchInput.addEventListener('input', function() {
        var q = searchInput.value.trim();
        if (!q) {
            searchMode = false;
            if (candidates) renderResults(candidates);
            return;
        }
        searchMode = true;
        if (q.length < 2) {
            renderResults([]);
            return;
        }
        if (searchTimer) clearTimeout(searchTimer);
        searchTimer = setTimeout(function() {
            fetch('/edit/song/' + songId + '/merge-search?q=' + encodeURIComponent(q), {
                headers: _csrfHeaders({})
            }).then(function(r) { return r.json(); }).then(function(data) {
                if (searchMode) renderResults(data);
            }).catch(function() {
                renderResults([]);
            });
        }, 300);
    });

    var rect = getZoomedRect(span);
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    if (rect.bottom + 2 + popover.offsetHeight + 30 > viewH) {
        popover.style.top = Math.max(0, viewH - popover.offsetHeight - 30) + 'px';
    } else {
        popover.style.top = rect.bottom + 2 + 'px';
    }
    activeMergePopover = popover;
    searchInput.focus();
}

function showMergeConfirm(keptId, keptName, absorbedId, absorbedName, absorbedArtist, absorbedAlbum) {
    var msg = 'Merge "' + absorbedName + ' \u2014 ' + absorbedArtist + ' (' + absorbedAlbum + ')" into "' + keptName + '"? The absorbed song will be deleted. Ratings and links will be combined.';
    showDeleteConfirm('Merge songs?', msg, '/edit/song/' + keptId + '/merge', true, 'Merge');
    // Override the form submit to include absorbed_song_id
    var form = document.getElementById('confirm-delete-form');
    // Remove any previous absorbed_song_id hidden input
    var prev = form.querySelector('input[name="absorbed_song_id"]');
    if (prev) prev.remove();
    var hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.name = 'absorbed_song_id';
    hidden.value = absorbedId;
    form.appendChild(hidden);
}

/* Song artist management popover */

var activeSongArtistPopover = null;

function closeSongArtistPopover() {
    if (activeSongArtistPopover) {
        activeSongArtistPopover.remove();
        activeSongArtistPopover = null;
    }
}


function _updateCollabLabel(songId, artists) {
    var row = document.getElementById('song-' + songId);
    if (!row) return;
    var td = row.querySelector('td');
    if (!td) return;
    // Remove existing collab label span (italic span inside the td)
    var existing = td.querySelector('span[style*="font-style: italic"]');
    if (existing) existing.remove();
    var currentId = (typeof _currentArtistId !== 'undefined') ? _currentArtistId : null;
    var isAnimePage = (typeof _isAnimePage !== 'undefined') ? _isAnimePage : false;
    var ANIME_GENDER_ID = 3;
    var others = artists.filter(function(a) { return a.artist_id !== currentId; });
    // Bucket other artists the same way the server does
    var mainNames = [], byNames = [], forNames = [], featNames = [];
    others.forEach(function(a) {
        var isOtherAnime = a.gender_id === ANIME_GENDER_ID;
        if (isAnimePage && !isOtherAnime && a.is_main) {
            byNames.push(a.name);
        } else if (!isAnimePage && isOtherAnime) {
            forNames.push(a.name);
        } else if (a.is_main) {
            mainNames.push(a.name);
        } else {
            featNames.push(a.name);
        }
    });
    var parts = [];
    if (mainNames.length) parts.push('(with ' + mainNames.join(', ') + ')');
    if (byNames.length) parts.push('(by ' + byNames.join(', ') + ')');
    if (forNames.length) parts.push('(for ' + forNames.join(', ') + ')');
    if (featNames.length) parts.push('(feat. ' + featNames.join(', ') + ')');
    if (parts.length) {
        var label = document.createElement('span');
        label.style.cssText = 'color: var(--text-secondary); font-style: italic;';
        label.textContent = parts.join(' ');
        td.appendChild(document.createTextNode(' '));
        td.appendChild(label);
    }
}

function showSongArtists(event, songId, span) {
    event.stopPropagation();
    closeSongArtistPopover();
    closeAlbumMovePopover();
    closeAlbumAddPopover();
    closeAlbumSongSearchPopover();

    var artists = (typeof _songArtists !== 'undefined' && _songArtists[songId]) ? _songArtists[songId] : [];
    var allArtists = (typeof _allArtists !== 'undefined') ? _allArtists : [];

    var popover = document.createElement('div');
    popover.style.cssText =
        'position:fixed; z-index:50; background:var(--bg-secondary,#fff); border:2px solid var(--link,#2563EB);' +
        'border-radius:4px; padding:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2); width:260px; max-height:320px; overflow-y:auto;';

    var title = document.createElement('div');
    title.textContent = 'Song artists:';
    title.style.cssText = 'font-size:11px; font-weight:bold; margin-bottom:6px; color:var(--text-secondary);';
    popover.appendChild(title);

    var listContainer = document.createElement('div');
    listContainer.id = 'song-artist-list-' + songId;

    function renderList() {
        listContainer.innerHTML = '';
        artists.forEach(function(a) {
            var row = document.createElement('div');
            row.style.cssText = 'display:flex; align-items:center; gap:6px; padding:2px 0;';

            var name = document.createElement('span');
            name.textContent = a.name;
            name.style.cssText = 'font-size:12px; flex:1;';
            row.appendChild(name);

            var roleBtn = document.createElement('button');
            roleBtn.textContent = a.is_main ? 'Main' : 'Feat';
            roleBtn.style.cssText = 'font-size:10px; padding:1px 6px; border:1px solid var(--border); border-radius:3px; cursor:pointer; background:' + (a.is_main ? 'var(--link,#2563EB)' : 'transparent') + '; color:' + (a.is_main ? '#fff' : 'var(--text-secondary)') + ';';
            roleBtn.addEventListener('click', function() {
                fetch('/edit/song/' + songId + '/artists/' + a.artist_id + '/role', {
                    method: 'POST',
                    headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
                }).then(function(r) {
                    if (!r.ok) throw new Error('failed');
                    return r.json();
                }).then(function(data) {
                    a.is_main = data.is_main;
                    renderList();
                    _updateCollabLabel(songId, artists);
                });
            });
            row.appendChild(roleBtn);

            if (artists.length > 1) {
                var removeBtn = document.createElement('button');
                removeBtn.textContent = '\u00d7';
                removeBtn.style.cssText = 'font-size:13px; color:var(--delete-button,#DC2626); background:none; border:none; cursor:pointer; padding:0 2px;';
                removeBtn.addEventListener('click', function() {
                    fetch('/edit/song/' + songId + '/artists/' + a.artist_id, {
                        method: 'DELETE',
                        headers: _csrfHeaders({}),
                    }).then(function(r) {
                        if (!r.ok) throw new Error('failed');
                        artists = artists.filter(function(x) { return x.artist_id !== a.artist_id; });
                        _songArtists[songId] = artists;
                        renderList();
                        rebuildOptions();
                        _updateCollabLabel(songId, artists);
                    });
                });
                row.appendChild(removeBtn);
            }

            listContainer.appendChild(row);
        });
    }

    renderList();
    popover.appendChild(listContainer);

    // Add artist dropdown
    var addRow = document.createElement('div');
    addRow.style.cssText = 'margin-top:6px; border-top:1px solid var(--border); padding-top:6px;';

    var select = document.createElement('select');
    select.style.cssText = 'font-size:11px; width:100%; padding:2px 4px; border:1px solid var(--border); border-radius:3px;';

    function rebuildOptions() {
        select.innerHTML = '';
        var opt0 = document.createElement('option');
        opt0.value = '';
        opt0.textContent = '+ Add artist...';
        select.appendChild(opt0);
        var usedIds = artists.map(function(a) { return a.artist_id; });
        allArtists.forEach(function(a) {
            if (usedIds.indexOf(a.id) === -1) {
                var opt = document.createElement('option');
                opt.value = a.id;
                opt.textContent = a.name;
                select.appendChild(opt);
            }
        });
    }
    rebuildOptions();

    select.addEventListener('change', function() {
        var artistId = parseInt(select.value);
        if (!artistId) return;
        var artist = allArtists.find(function(a) { return a.id === artistId; });
        if (!artist) return;
        fetch('/edit/song/' + songId + '/artists', {
            method: 'POST',
            headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
            body: 'artist_id=' + artistId + '&is_main=false',
        }).then(function(r) {
            if (!r.ok) throw new Error('failed');
            artists.push({ artist_id: artistId, name: artist.name, is_main: false });
            _songArtists[songId] = artists;
            renderList();
            rebuildOptions();
            _updateCollabLabel(songId, artists);
        });
    });

    addRow.appendChild(select);
    popover.appendChild(addRow);

    var rect = getZoomedRect(span);
    popover.style.left = rect.left + 'px';

    document.body.appendChild(popover);
    var zoom = parseFloat(document.documentElement.style.zoom) || 1;
    var viewH = window.innerHeight / zoom;
    if (rect.bottom + 2 + popover.offsetHeight + 30 > viewH) {
        popover.style.top = Math.max(0, viewH - popover.offsetHeight - 30) + 'px';
    } else {
        popover.style.top = rect.bottom + 2 + 'px';
    }
    activeSongArtistPopover = popover;
}

/* Add album modal helpers */

var _newAlbumSongCount = 0;

function resetAddAlbumModal() {
    _newAlbumSongCount = 0;
    var name = document.getElementById('new-album-name');
    if (name) name.value = '';
    var date = document.getElementById('new-album-date');
    if (date) date.value = '';
    var type = document.getElementById('new-album-type');
    if (type) type.selectedIndex = 0;
    document.querySelectorAll('#new-album-genres input').forEach(function(cb) { cb.checked = false; });
    var songs = document.getElementById('new-album-songs');
    if (songs) songs.innerHTML = '';
    var searchInput = document.getElementById('album-song-search');
    if (searchInput) searchInput.value = '';
    var searchResults = document.getElementById('album-song-search-results');
    if (searchResults) { searchResults.style.display = 'none'; searchResults.innerHTML = ''; }
    validateAddAlbum();
}

function validateAddAlbum() {
    var btn = document.getElementById('add-album-submit-btn');
    if (!btn) return;
    var valid = true;

    var name = document.getElementById('new-album-name');
    if (!name || !name.value.trim()) valid = false;

    var songDivs = document.querySelectorAll('#new-album-songs > [id^="new-song-"]');
    if (!songDivs.length) valid = false;

    songDivs.forEach(function(div) {
        // Existing songs are always valid
        if (div.dataset.existingSongId) return;
        var songName = div.querySelector('.new-album-song-name');
        if (!songName || !songName.value.trim()) valid = false;
        var hasMain = false;
        div.querySelectorAll('.new-song-artist-row').forEach(function(row) {
            var role = row.querySelector('.new-song-artist-role');
            if (role && role.value === 'main') hasMain = true;
        });
        if (!hasMain) valid = false;
    });

    btn.disabled = !valid;
    btn.style.opacity = valid ? '1' : '0.5';
    btn.style.cursor = valid ? 'pointer' : 'not-allowed';
}

function addNewAlbumSong(currentArtistId) {
    _newAlbumSongCount++;
    var n = _newAlbumSongCount;
    var container = document.getElementById('new-album-songs');
    var row = document.createElement('div');
    row.id = 'new-song-' + n;
    row.className = 'mb-2 p-2 border rounded';
    row.style.borderColor = 'var(--border)';
    row.innerHTML =
        '<div class="flex gap-2 items-center mb-1">' +
            '<input type="text" placeholder="Song name" class="flex-1 px-2 py-1 border rounded text-sm new-album-song-name" style="border-color:var(--border);" oninput="validateAddAlbum()">' +
            '<label class="text-xs"><input type="checkbox" class="new-song-promoted"> Promoted</label>' +
            '<label class="text-xs"><input type="checkbox" class="new-song-remix"> Remix</label>' +
            '<button type="button" onclick="this.closest(\'[id^=new-song-]\').remove();validateAddAlbum()" class="text-xs px-1" style="color:var(--delete-button,#DC2626);">&times;</button>' +
        '</div>' +
        '<div class="flex items-center gap-2" style="padding: 4px 8px;">' +
            '<span class="text-xs" style="color:var(--text-secondary);">Artists:</span>' +
            '<div id="new-song-artists-' + n + '" class="flex flex-wrap gap-2" style="margin-right: 4px;"></div>' +
            '<select class="new-song-artist-select text-xs px-1 border rounded" style="border-color:var(--border); max-width:150px;" onchange="onNewSongArtistChange(this,' + n + ')">' +
                newSongArtistOptions(n) +
            '</select>' +
        '</div>';
    container.appendChild(row);
    // Auto-add current artist as main
    addNewSongArtist(n, currentArtistId, _currentArtistName(), true);
    validateAddAlbum();
    // Scroll modal so the new song and buttons stay visible
    var modal = container.closest('[style*="overflow-y"]');
    if (modal) setTimeout(function() { modal.scrollTop = modal.scrollHeight; }, 50);
}

function _currentArtistName() {
    if (typeof _allArtists !== 'undefined' && typeof _currentArtistId !== 'undefined') {
        var a = _allArtists.find(function(x) { return x.id === _currentArtistId; });
        if (a) return a.name;
    }
    return 'Current Artist';
}

function newSongArtistOptions(songNum) {
    var used = newSongUsedArtistIds(songNum);
    var opts = '<option value="">-- Add artist --</option>';
    if (typeof _allArtists !== 'undefined') {
        _allArtists.forEach(function(a) {
            if (used.indexOf(a.id) === -1) {
                opts += '<option value="' + a.id + '">' + a.name.replace(/</g, '&lt;') + '</option>';
            }
        });
    }
    return opts;
}

function newSongUsedArtistIds(songNum) {
    var ids = [];
    var container = document.getElementById('new-song-artists-' + songNum);
    if (container) {
        container.querySelectorAll('.new-song-artist-row').forEach(function(row) {
            if (row.dataset.artistId) ids.push(parseInt(row.dataset.artistId));
        });
    }
    return ids;
}

function addNewSongArtist(songNum, artistId, artistName, isMain) {
    var container = document.getElementById('new-song-artists-' + songNum);
    var count = container.children.length;
    var row = document.createElement('div');
    row.className = 'flex items-center gap-1 new-song-artist-row';
    row.dataset.artistId = artistId || '';
    row.innerHTML =
        '<span class="text-xs" style="margin-right: 4px;">' + (artistName || '').replace(/</g, '&lt;') + '</span>' +
        '<select class="new-song-artist-role text-xs px-1 border rounded" style="border-color:var(--border);" onchange="validateAddAlbum()">' +
            '<option value="main"' + (isMain ? ' selected' : '') + '>Main</option>' +
            '<option value="feat"' + (!isMain ? ' selected' : '') + '>Featured</option>' +
        '</select>' +
        (count > 0 ? '<button type="button" onclick="removeNewSongArtist(this,' + songNum + ')" class="text-red-500 text-xs">x</button>' : '');
    container.appendChild(row);
    updateNewSongArtistDropdown(songNum);
    validateAddAlbum();
}

function removeNewSongArtist(btn, songNum) {
    btn.parentElement.remove();
    updateNewSongArtistDropdown(songNum);
    validateAddAlbum();
}

function updateNewSongArtistDropdown(songNum) {
    var songDiv = document.getElementById('new-song-' + songNum);
    if (!songDiv) return;
    var select = songDiv.querySelector('.new-song-artist-select');
    if (select) {
        select.innerHTML = newSongArtistOptions(songNum);
        select.value = '';
    }
}

function onNewSongArtistChange(select, songNum) {
    var id = parseInt(select.value);
    if (!id) return;
    var artist = _allArtists.find(function(a) { return a.id === id; });
    if (!artist) return;
    addNewSongArtist(songNum, id, artist.name, false);
    select.value = '';
}

function submitNewAlbum(artistId) {
    var name = document.getElementById('new-album-name').value.trim();
    var date = document.getElementById('new-album-date').value;
    var typeId = parseInt(document.getElementById('new-album-type').value);

    if (!name) { showToast('Album name is required'); return; }

    var genreIds = [];
    document.querySelectorAll('#new-album-genres input:checked').forEach(function(cb) {
        genreIds.push(parseInt(cb.value));
    });
    if (!genreIds.length) { showToast('At least one genre is required'); return; }

    var songs = [];
    document.querySelectorAll('[id^="new-song-"]').forEach(function(songDiv) {
        // Existing song — just reference by ID
        if (songDiv.dataset.existingSongId) {
            songs.push({ existing_song_id: parseInt(songDiv.dataset.existingSongId) });
            return;
        }
        var nameInput = songDiv.querySelector('.new-album-song-name');
        var n = nameInput ? nameInput.value.trim() : '';
        if (!n) return;
        var artists = [];
        songDiv.querySelectorAll('.new-song-artist-row').forEach(function(row) {
            var role = row.querySelector('.new-song-artist-role');
            artists.push({
                artist_id: row.dataset.artistId ? parseInt(row.dataset.artistId) : null,
                is_main: role ? role.value === 'main' : true,
            });
        });
        songs.push({
            name: n,
            is_promoted: songDiv.querySelector('.new-song-promoted') ? songDiv.querySelector('.new-song-promoted').checked : false,
            is_remix: songDiv.querySelector('.new-song-remix') ? songDiv.querySelector('.new-song-remix').checked : false,
            artists: artists,
        });
    });

    if (!songs.length) { showToast('Add at least one song'); return; }

    var data = {
        name: name,
        release_date: date,
        album_type_id: typeId,
        genre_ids: genreIds,
        songs: songs,
    };

    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;

    fetch('/edit/artist/' + artistId + '/add-album', {
        method: 'POST',
        headers: headers,
        body: 'data=' + encodeURIComponent(JSON.stringify(data)),
    }).then(function(r) {
        if (!r.ok) throw new Error('save failed');
        return r.json();
    }).then(function() {
        window.location.reload();
    }).catch(function() {
        showToast('Failed to add album — try again');
    });
}

// Validate add-album modal on any input/change inside it
var _addAlbumModal = document.getElementById('add-album-modal');
if (_addAlbumModal) {
    _addAlbumModal.addEventListener('input', validateAddAlbum);
    _addAlbumModal.addEventListener('change', validateAddAlbum);
}

/* Search existing songs for add-album modal */

var _albumSongSearchTimer = null;
function debouncedAlbumSongSearch(artistId) {
    clearTimeout(_albumSongSearchTimer);
    _albumSongSearchTimer = setTimeout(function() { albumSongSearch(artistId); }, 250);
}

function albumSongSearch(artistId) {
    var input = document.getElementById('album-song-search');
    var results = document.getElementById('album-song-search-results');
    if (!input || !results) return;
    var q = input.value.trim();
    if (q.length < 2) { results.style.display = 'none'; return; }

    fetch('/edit/artist/' + artistId + '/search-songs?q=' + encodeURIComponent(q))
        .then(function(r) { return r.json(); })
        .then(function(songs) {
            if (!songs.length) {
                results.innerHTML = '<div class="px-3 py-2" style="color:var(--text-secondary);">No songs found</div>';
                results.style.display = 'block';
                return;
            }
            // Filter out songs already added to the album
            var addedIds = getAddedExistingSongIds();
            songs = songs.filter(function(s) { return addedIds.indexOf(s.id) === -1; });
            if (!songs.length) {
                results.innerHTML = '<div class="px-3 py-2" style="color:var(--text-secondary);">All matching songs already added</div>';
                results.style.display = 'block';
                return;
            }
            var html = '';
            var lastWasCurrent = null;
            songs.forEach(function(s) {
                if (lastWasCurrent !== null && lastWasCurrent && !s.is_current_artist) {
                    html += '<div style="border-top:1px solid var(--border); margin:2px 0;"></div>';
                }
                lastWasCurrent = s.is_current_artist;
                html += '<div class="px-3 py-1 cursor-pointer album-song-result" style="' +
                    (s.is_current_artist ? 'font-weight:500;' : '') +
                    '" data-song-id="' + s.id + '" data-song-name="' + s.name.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;') + '" data-artist-name="' + s.artist.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;') + '"' +
                    ' onmouseover="this.style.background=\'var(--bg-hover)\'" onmouseout="this.style.background=\'transparent\'">' +
                    '<span>' + s.name.replace(/</g, '&lt;') + '</span>' +
                    '<span style="color:var(--text-secondary);"> — ' + s.artist.replace(/</g, '&lt;') + ' (' + s.album.replace(/</g, '&lt;') + ')</span>' +
                    '</div>';
            });
            results.innerHTML = html;
            results.style.display = 'block';
        });
}

function getAddedExistingSongIds() {
    var ids = [];
    document.querySelectorAll('#new-album-songs [data-existing-song-id]').forEach(function(el) {
        ids.push(parseInt(el.dataset.existingSongId));
    });
    return ids;
}

function addExistingSongToAlbum(songId, songName, artistName) {
    _newAlbumSongCount++;
    var n = _newAlbumSongCount;
    var container = document.getElementById('new-album-songs');
    var row = document.createElement('div');
    row.id = 'new-song-' + n;
    row.className = 'mb-2 p-2 border rounded';
    row.style.borderColor = 'var(--border)';
    row.dataset.existingSongId = songId;
    row.innerHTML =
        '<div class="flex gap-2 items-center">' +
            '<span class="flex-1 text-sm">' + songName.replace(/</g, '&lt;') +
            ' <span style="color:var(--text-secondary); font-size:11px;">— ' + artistName.replace(/</g, '&lt;') + ' (existing)</span></span>' +
            '<button type="button" onclick="this.closest(\'[id^=new-song-]\').remove();validateAddAlbum()" class="text-xs px-1" style="color:var(--delete-button,#DC2626);">&times;</button>' +
        '</div>';
    container.appendChild(row);

    // Clear search
    var input = document.getElementById('album-song-search');
    if (input) input.value = '';
    var results = document.getElementById('album-song-search-results');
    if (results) results.style.display = 'none';

    validateAddAlbum();
    // Scroll modal so the new song and buttons stay visible
    var modal = container.closest('[style*="overflow-y"]');
    if (modal) setTimeout(function() { modal.scrollTop = modal.scrollHeight; }, 50);
}

// Delegated click handler for search results
document.addEventListener('click', function(e) {
    var item = e.target.closest('.album-song-result');
    if (item) {
        addExistingSongToAlbum(
            parseInt(item.dataset.songId),
            item.dataset.songName,
            item.dataset.artistName
        );
        return;
    }
    // Close search results when clicking outside
    var results = document.getElementById('album-song-search-results');
    var input = document.getElementById('album-song-search');
    if (results && input && !results.contains(e.target) && e.target !== input) {
        results.style.display = 'none';
    }
});

/* Remove song from album (no password required) */

function confirmRemoveFromAlbum(songId, albumId, songName, albumName) {
    if (!confirm('Remove "' + songName + '" from "' + albumName + '"?\n\nIf this is the song\'s only album, the song will be deleted.')) return;
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
    fetch('/edit/song/' + songId + '/remove-from-album/' + albumId, {
        method: 'POST',
        headers: headers,
        body: '',
    }).then(function(r) {
        if (!r.ok) throw new Error('failed');
        window.location.reload();
    }).catch(function() {
        showToast('Remove failed — try again');
    });
}

/* Reorder song within album */

function reorderSong(songId, albumId, direction) {
    fetch('/edit/album/' + albumId + '/reorder-song', {
        method: 'POST',
        headers: _csrfHeaders({'Content-Type': 'application/x-www-form-urlencoded'}),
        body: 'song_id=' + songId + '&direction=' + direction,
    }).then(function(r) {
        if (!r.ok) throw new Error('failed');
        window.location.reload();
    }).catch(function() {
        showToast('Reorder failed — try again');
    });
}

/* Shared delete confirmation modal */

var _deleteIsAjax = false;

var _deleteRedirectUrl = null;

function confirmDeleteAlbum(albumId, albumName) {
    fetch('/edit/album/' + albumId + '/delete-info')
        .then(function(r) {
            if (!r.ok) throw new Error('status ' + r.status);
            return r.json();
        })
        .then(function(data) {
            var msg = albumName + ' will be permanently deleted.';
            if (data.songs_deleted > 0) {
                msg += '\n\n' + data.songs_deleted + ' song' + (data.songs_deleted !== 1 ? 's' : '') +
                       ' and ' + data.ratings_deleted + ' rating' + (data.ratings_deleted !== 1 ? 's' : '') +
                       ' will also be deleted.';
                if (data.songs_deleted < data.songs) {
                    msg += ' ' + (data.songs - data.songs_deleted) + ' song' +
                           (data.songs - data.songs_deleted !== 1 ? 's' : '') +
                           ' on other albums will be kept.';
                }
            } else if (data.songs > 0) {
                msg += '\n\nAll ' + data.songs + ' song' + (data.songs !== 1 ? 's' : '') +
                       ' are on other albums and will be kept.';
            }
            showDeleteConfirm('Delete album?', msg, '/edit/album/' + albumId + '/delete', true);
        })
        .catch(function() {
            showDeleteConfirm('Delete album?', albumName + ' will be permanently deleted.',
                              '/edit/album/' + albumId + '/delete', true);
        });
}

function showDeleteConfirm(title, msg, action, ajax, btnLabel, redirectUrl) {
    _deleteIsAjax = !!ajax;
    _deleteRedirectUrl = redirectUrl || null;
    document.getElementById('confirm-delete-title').textContent = title;
    document.getElementById('confirm-delete-msg').textContent = msg;
    var form = document.getElementById('confirm-delete-form');
    form.action = action;
    // Clean up any leftover merge hidden input
    var prev = form.querySelector('input[name="absorbed_song_id"]');
    if (prev) prev.remove();
    document.getElementById('confirm-delete-pw').value = '';
    document.getElementById('confirm-delete-btn').textContent = btnLabel || 'Delete';
    document.getElementById('confirm-delete-modal').style.display = 'flex';
}

(function() {
    var form = document.getElementById('confirm-delete-form');
    if (!form) return;
    form.addEventListener('submit', function(e) {
        if (!_deleteIsAjax) return; // let normal form submit handle artist delete (redirect)
        e.preventDefault();
        var pw = document.getElementById('confirm-delete-pw').value;
        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        var headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken.content;
        var body = 'password=' + encodeURIComponent(pw);
        var absorbedInput = form.querySelector('input[name="absorbed_song_id"]');
        if (absorbedInput) body += '&absorbed_song_id=' + absorbedInput.value;
        fetch(form.action, {
            method: 'POST',
            headers: headers,
            body: body,
        }).then(function(r) {
            if (r.status === 403) { alert('Incorrect password'); return; }
            if (!r.ok) throw new Error('failed');
            document.getElementById('confirm-delete-modal').style.display = 'none';
            if (_deleteRedirectUrl) {
                window.location.href = _deleteRedirectUrl;
            } else {
                window.location.reload();
            }
        }).catch(function() {
            showToast('Action failed — try again');
        });
    });
})();

// Song note editor — edit-mode only, triggered by right-click on song name cell
var activeSongNote = null;

function showSongNoteInput(event, tdEl) {
    event.preventDefault();
    event.stopPropagation();
    if (activeSongNote) closeSongNoteInput();

    var songId = tdEl.getAttribute('data-song-id');
    var existingNote = tdEl.getAttribute('data-song-note') || '';
    var overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed; z-index:10000; background:var(--bg-secondary); border:1px solid var(--border); border-radius:8px; padding:12px; box-shadow:0 4px 16px rgba(0,0,0,.25); width:240px;';

    var textarea = document.createElement('textarea');
    textarea.value = existingNote;
    textarea.style.cssText = 'width:100%; height:80px; resize:vertical; background:var(--bg-primary); color:var(--text-primary); border:1px solid var(--border); border-radius:4px; padding:6px; font-size:12px; font-family:inherit;';
    overlay.appendChild(textarea);

    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex; gap:6px; margin-top:8px; justify-content:flex-end;';

    var saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'padding:4px 12px; border-radius:4px; border:none; background:var(--edit-on-button); color:#fff; cursor:pointer; font-size:12px;';
    saveBtn.onclick = function () { submitSongNote(songId, textarea.value.trim(), tdEl); };

    var cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'padding:4px 12px; border-radius:4px; border:1px solid var(--border); background:var(--bg-secondary); color:var(--text-primary); cursor:pointer; font-size:12px;';
    cancelBtn.onclick = closeSongNoteInput;

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    overlay.appendChild(btnRow);
    document.body.appendChild(overlay);

    var rect = getZoomedRect(tdEl);
    overlay.style.left = Math.min(rect.right - 240, window.innerWidth - 260) + 'px';
    overlay.style.top = (rect.bottom + 6) + 'px';

    textarea.focus();
    textarea.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { e.preventDefault(); closeSongNoteInput(); }
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitSongNote(songId, textarea.value.trim(), tdEl); }
    });

    activeSongNote = { overlay: overlay, td: tdEl };
}

function closeSongNoteInput() {
    if (!activeSongNote) return;
    activeSongNote.overlay.remove();
    activeSongNote = null;
}

function submitSongNote(songId, noteText, tdEl) {
    var formData = new FormData();
    formData.append('value', noteText);
    fetch('/edit/song/' + songId + '/note', { method: 'POST', headers: _csrfHeaders({}), body: formData })
        .then(function (r) { return r.text(); })
        .then(function (text) {
            var note = text.trim();
            if (note) {
                tdEl.classList.add('has-song-note');
                tdEl.setAttribute('data-song-note', note);
            } else {
                tdEl.classList.remove('has-song-note');
                tdEl.removeAttribute('data-song-note');
            }
            closeSongNoteInput();
        });
}

// Right-click on song name cell opens note editor (edit mode only)
document.addEventListener('contextmenu', function (e) {
    var td = e.target.closest('td.song-name-cell');
    if (!td) return;
    if (!td.querySelector('.edit-inline')) return;
    showSongNoteInput(e, td);
});

// 'n' key on hovered song name cell opens note editor (edit mode only)
var _hoveredSongCell = null;
document.addEventListener('mouseover', function (e) {
    var td = e.target.closest('td.song-name-cell');
    _hoveredSongCell = td || null;
});
document.addEventListener('keydown', function (e) {
    if (e.key !== 'n' || !_hoveredSongCell || activeSongNote) return;
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
    if (!_hoveredSongCell.querySelector('.edit-inline')) return;
    e.preventDefault();
    showSongNoteInput(e, _hoveredSongCell);
});

// Close song note overlay on outside click
document.addEventListener('click', function (e) {
    if (activeSongNote && !activeSongNote.overlay.contains(e.target) && !activeSongNote.td.contains(e.target)) {
        closeSongNoteInput();
    }
});
