// Lists view: every list the pipeline reads (ADR-028). Admins add, edit,
// deactivate and import; reviewers can look. The API enforces the same rule.

const KINDS = {
    newspaper: { label: 'Newspapers', help: 'Publications entries can be filed under. City and language fill the form automatically.',
        columns: [['hrms_id', 'HRMS ID'], ['city', 'Edition city'], ['language', 'Language'], ['frequency', 'Frequency']],
        fields: ['name', 'hrms_id', 'city', 'language', 'frequency'] },
    feed: { label: 'Feeds', help: 'RSS links the scheduled sync reads. Each feed belongs to a newspaper.',
        columns: [['parent', 'Newspaper'], ['url', 'Feed URL']],
        fields: ['name', 'parent', 'url'] },
    category: { label: 'Categories', help: 'Main categories the AI can choose from.',
        columns: [['hrms_id', 'HRMS ID'], ['control', 'Shown on']], fields: ['name', 'hrms_id', 'control'] },
    sub_category: { label: 'Sub-categories', help: 'Up to three are chosen per entry.',
        columns: [['hrms_id', 'HRMS ID'], ['control', 'Shown on']], fields: ['name', 'hrms_id', 'control'] },
    keyword: { label: 'Keywords', help: 'The fixed keyword list entries are tagged from.',
        columns: [['hrms_id', 'HRMS ID']], fields: ['name', 'hrms_id'] },
    news_type: { label: 'News types', help: 'Values for the News Type field.', columns: [], fields: ['name'] },
    province: { label: 'Provinces', help: 'Values for the Province field. Cities belong to these.', columns: [], fields: ['name'] },
    city: { label: 'Cities', help: 'Places the AI can choose for the City field. Each belongs to a province.',
        columns: [['parent', 'Province']], fields: ['name', 'parent'] },
};
const PARENT_KIND = { feed: 'newspaper', city: 'province' };

// Field label + input type, per field. Choices offer suggestions, not limits,
// except "control" which mirrors the two HRMS values.
const FIELD = {
    name: { label: 'Name', required: true },
    hrms_id: { label: 'HRMS ID', type: 'number', hint: 'The ID this entry has in HRMS, so exports line up.' },
    parent: { label: 'Belongs to', required: true },
    url: { label: 'Feed URL', type: 'url', required: true, hint: 'Must start with http:// or https://' },
    city: { label: 'Edition city' },
    language: { label: 'Language', suggest: ['English', 'Urdu', 'Sindhi'] },
    frequency: { label: 'Frequency', suggest: ['Daily', 'Weekly', 'Monthly'] },
    control: { label: 'Shown on', options: [['ShowonBoth', 'Form and reports'], ['ShowonReport', 'Reports only']] },
};

let currentKind = 'newspaper';
let rows = [];
let editing = null;  // the row being edited, or null when adding

function showListNotice(html, kind = 'info') {
    $('list-notice-text').innerHTML = html;  // callers pass escaped HTML
    $('list-notice').dataset.kind = kind;
    $('list-notice').hidden = false;
}
$('list-notice-close').addEventListener('click', () => { $('list-notice').hidden = true; });

async function loadSummary() {
    const summary = await apiJson('/lookups/summary');
    $('kind-nav').innerHTML = Object.entries(KINDS).map(([kind, k]) => {
        const s = summary[kind] || { total: 0, active: 0 };
        return `<button type="button" data-kind="${kind}" ${kind === currentKind ? 'aria-current="true"' : ''}>
            <span>${esc(k.label)}</span><span class="count">${s.active}${s.total !== s.active ? ` / ${s.total}` : ''}</span></button>`;
    }).join('');
}

async function selectKind(kind) {
    currentKind = kind;
    document.querySelectorAll('#kind-nav button').forEach(b => {
        if (b.dataset.kind === kind) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
    });
    $('list-title').textContent = KINDS[kind].label;
    $('list-help').textContent = KINDS[kind].help;
    $('list-search').value = '';
    $('list-tbody').innerHTML = '<tr><td class="muted">Loading…</td></tr>';
    try {
        rows = await apiJson(`/lookups?kind=${encodeURIComponent(kind)}`);
        renderTable();
    } catch (err) {
        if (err.status !== 401) $('list-tbody').innerHTML = `<tr><td class="muted">Couldn't load: ${esc(err.message)}</td></tr>`;
    }
}

function cellHtml(row, field) {
    const value = row[field];
    if (value === null || value === undefined || value === '') return '<td class="muted">–</td>';
    if (field === 'url') {
        const href = safeUrl(value);
        return `<td class="url">${href ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(value)}</a>` : esc(value)}</td>`;
    }
    if (field === 'control') return `<td>${esc(value === 'ShowonReport' ? 'Reports only' : 'Form and reports')}</td>`;
    return `<td class="${field === 'hrms_id' ? 'num' : ''}">${esc(value)}</td>`;
}

function renderTable() {
    const k = KINDS[currentKind];
    const q = $('list-search').value.trim().toLowerCase();
    const showInactive = $('show-inactive').checked;
    const shown = rows.filter(r => (showInactive || r.active) && (!q || r.name.toLowerCase().includes(q)));

    $('list-thead').innerHTML = `<tr><th>Name</th>${k.columns.map(([, label]) => `<th>${esc(label)}</th>`).join('')}
        <th>Status</th><th class="admin-only"><span class="sr-only">Actions</span></th></tr>`;
    $('list-tbody').innerHTML = shown.length ? shown.map(r => `
        <tr class="${r.active ? '' : 'inactive'}">
            <td dir="auto">${esc(r.name)}</td>
            ${k.columns.map(([field]) => cellHtml(r, field)).join('')}
            <td><span class="pill ${r.active ? 'on' : ''}">${r.active ? 'Active' : 'Inactive'}</span></td>
            <td class="admin-only"><button class="btn btn-small" type="button" data-edit="${r.id}">Edit</button></td>
        </tr>`).join('')
        : `<tr><td colspan="${k.columns.length + 3}" class="muted">${rows.length ? 'Nothing matches.' : 'This list is empty.'}</td></tr>`;

    const hidden = rows.filter(r => !r.active).length;
    $('list-count').textContent = `${shown.length} shown` + (!showInactive && hidden ? ` · ${hidden} inactive hidden` : '');
}

// --- Add / edit ----------------------------------------------------------------
async function openEditor(row) {
    editing = row;
    const kind = currentKind;
    const k = KINDS[kind];
    $('entry-title').textContent = row ? `Edit ${k.label.toLowerCase().replace(/s$/, '')}` : `Add to ${k.label}`;
    $('entry-error').textContent = '';
    $('entry-active').checked = row ? row.active : true;

    let parentNames = [];
    if (PARENT_KIND[kind]) {
        parentNames = (await apiJson(`/lookups?kind=${PARENT_KIND[kind]}`)).map(r => r.name);
    }

    $('entry-fields').innerHTML = k.fields.map(field => {
        const f = FIELD[field];
        const id = `entry-${field}`;
        const value = row?.[field] ?? '';
        const label = field === 'parent' ? (kind === 'feed' ? 'Newspaper' : 'Province') : f.label;
        let input;
        if (field === 'parent') {
            input = `<select id="${id}" class="input" required><option value="">Choose…</option>
                ${parentNames.map(n => `<option ${n === value ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select>`;
        } else if (f.options) {
            input = `<select id="${id}" class="input"><option value="">–</option>
                ${f.options.map(([v, text]) => `<option value="${esc(v)}" ${v === value ? 'selected' : ''}>${esc(text)}</option>`).join('')}</select>`;
        } else {
            const list = f.suggest ? ` list="${id}-list"` : '';
            input = `<input id="${id}" class="input" type="${f.type || 'text'}" value="${esc(value)}"${f.required ? ' required' : ''}${list}>`
                + (f.suggest ? `<datalist id="${id}-list">${f.suggest.map(s => `<option value="${esc(s)}">`).join('')}</datalist>` : '');
        }
        return `<div class="field"><label for="${id}">${esc(label)}</label>${input}${f.hint ? `<span class="hint">${esc(f.hint)}</span>` : ''}</div>`;
    }).join('');
    $('entry-dialog').showModal();
}

$('entry-cancel').addEventListener('click', () => $('entry-dialog').close());

$('entry-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = { active: $('entry-active').checked };
    for (const field of KINDS[currentKind].fields) body[field] = $(`entry-${field}`).value.trim();
    $('entry-save').disabled = true;
    try {
        if (editing) await apiJson(`/lookups/${editing.id}`, { method: 'PATCH', body });
        else await apiJson('/lookups', { method: 'POST', body: { kind: currentKind, ...body } });
        $('entry-dialog').close();
        await Promise.all([loadSummary(), selectKind(currentKind)]);
    } catch (err) {
        if (err.status !== 401) $('entry-error').textContent = err.message;
    } finally {
        $('entry-save').disabled = false;
    }
});

$('add-btn').addEventListener('click', () => openEditor(null));
$('list-tbody').addEventListener('click', (e) => {
    const id = e.target.closest('[data-edit]')?.dataset.edit;
    if (id) openEditor(rows.find(r => String(r.id) === id));
});
$('kind-nav').addEventListener('click', (e) => {
    const kind = e.target.closest('[data-kind]')?.dataset.kind;
    if (kind && kind !== currentKind) selectKind(kind);
});
$('list-search').addEventListener('input', renderTable);
$('show-inactive').addEventListener('change', renderTable);

// --- HRMS Excel import ---------------------------------------------------------
const KIND_LABEL = { category: 'categories', sub_category: 'sub-categories', keyword: 'keywords', newspaper: 'newspapers' };

$('import-btn').addEventListener('click', () => $('import-file').click());
$('import-file').addEventListener('change', async () => {
    const file = $('import-file').files[0];
    $('import-file').value = '';
    if (!file) return;
    $('import-btn').disabled = true;
    showListNotice(`Importing ${esc(file.name)}…`);
    try {
        const r = await apiJson('/lookups/import', {
            method: 'POST', raw: file, headers: { 'Content-Type': 'application/octet-stream' },
        });
        const failed = r.failed.length
            ? `<ul>${r.failed.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : '';
        showListNotice(`Imported ${esc(KIND_LABEL[r.kind] || r.kind)} from ${esc(file.name)}: `
            + `${r.inserted} added, ${r.updated} updated, ${r.failed.length} skipped.${failed}`, r.failed.length ? 'error' : 'info');
        await loadSummary();
        await selectKind(r.kind);
    } catch (err) {
        if (err.status !== 401) showListNotice(`Import failed: ${esc(err.message)}`, 'error');
    } finally {
        $('import-btn').disabled = false;
    }
});

views.lists = {
    async open() {
        try {
            await loadSummary();
            await selectKind(currentKind);
        } catch (err) {
            if (err.status !== 401) showListNotice(`Couldn't load lists: ${esc(err.message)}`, 'error');
        }
    },
};
