// Reports view: the triage feed and the grounded chat.
// Syncs run on a schedule (ADR-029), so there is no sync button here.

// Minimal Markdown for answers: paragraphs, bullet lists, **bold**, headings
// as bold lines. The text is escaped FIRST, so the only markup that can
// appear is the markup added here.
function renderAnswer(text) {
    const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    let html = '', inList = false;
    for (const line of esc(text).split('\n')) {
        const item = line.match(/^\s*[*-]\s+(.*)$/);
        if (item) {
            if (!inList) { html += '<ul>'; inList = true; }
            html += `<li>${inline(item[1])}</li>`;
            continue;
        }
        if (inList) { html += '</ul>'; inList = false; }
        const heading = line.match(/^#{1,4}\s+(.*)$/);
        if (heading) html += `<p><strong>${inline(heading[1])}</strong></p>`;
        else if (line.trim()) html += `<p>${inline(line)}</p>`;
    }
    return inList ? html + '</ul>' : html;
}

// --- Feed --------------------------------------------------------------------
const SEVERITY_LABEL = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' };

function reportHtml(item) {
    const severity = SEVERITY_LABEL[item.severity] ? item.severity : 'low';
    const lang = item.language === 'urdu' ? ' lang="ur"' : '';
    const href = safeUrl(item.link);
    const title = esc(item.title);
    const summary = esc(item.summary || '');
    const categories = (item.categories || []).join(', ');
    const tags = (item.tags || []).join(', ');
    const labels = [categories, tags].filter(Boolean).map(esc).join(' · ');
    const reasoning = esc(item.reasoning || '');

    return `
        <li class="report sev-${severity}">
            <div class="report-meta">
                <span class="sev">${SEVERITY_LABEL[severity]}</span>
                <span>${esc(item.source || 'Unknown source')}</span>
                <span aria-hidden="true">·</span>
                <time datetime="${esc(item.published_at || '')}">${esc(shortDate(item.published_at))}</time>
            </div>
            <h3 dir="auto"${lang}>${href
                ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${title}</a>`
                : title}</h3>
            ${summary ? `<p class="summary" dir="auto"${lang}>${summary}</p>` : ''}
            ${labels ? `<p class="labels">${labels}</p>` : ''}
            ${reasoning ? `<details><summary>Why this rating</summary><p>${reasoning}</p></details>` : ''}
        </li>`;
}

async function loadFeed() {
    const list = $('feed-list');
    try {
        const data = await apiJson('/feed?limit=40');
        if (Array.isArray(data) && data.length > 0) {
            list.innerHTML = data.map(reportHtml).join('');
            $('feed-count').textContent = `${data.length} most recent`;
        } else {
            list.innerHTML = '<li class="empty">No reports yet. They appear after the next scheduled sync.</li>';
            $('feed-count').textContent = '';
        }
    } catch (err) {
        if (err.status === 401) return;
        list.innerHTML = `<li class="empty">Couldn't load reports: ${esc(err.message)}</li>`;
        $('feed-count').textContent = '';
    }
}
$('feed-refresh').addEventListener('click', loadFeed);

// --- Chat --------------------------------------------------------------------
let chatBusy = false;

function sourcesHtml(sources) {
    if (!sources.length) return '';
    const items = sources.map(s => {
        const href = safeUrl(s.link);
        const label = `${esc(s.source || 'Unknown')}, ${esc(shortDate(s.published))}`;
        const title = esc(s.title || '');
        return `<li>${label}: ${href
            ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer" dir="auto">${title}</a>`
            : `<span dir="auto">${title}</span>`}</li>`;
    }).join('');
    return `<div class="sources">Reports searched<ol>${items}</ol></div>`;
}

async function ask(query) {
    if (chatBusy || !query) return;
    chatBusy = true;
    $('send-btn').disabled = true;
    $('chat-intro')?.remove();

    const log = $('chat-log');
    const userMsg = document.createElement('div');
    userMsg.className = 'msg-user';
    userMsg.dir = 'auto';
    userMsg.textContent = query;
    const bot = document.createElement('div');
    bot.className = 'msg-bot';
    bot.innerHTML = '<p class="msg-status">Searching reports…</p><div class="msg-body"></div><div class="msg-extra"></div>';
    $('chat-inner').append(userMsg, bot);
    log.scrollTop = log.scrollHeight;

    const status = bot.querySelector('.msg-status');
    const body = bot.querySelector('.msg-body');
    const extra = bot.querySelector('.msg-extra');
    let answer = '', sources = [], buffer = '';

    try {
        const res = await api('/chat', { method: 'POST', body: { query } });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (!line.trim()) continue;
                let msg;
                try { msg = JSON.parse(line); } catch (e) { continue; }
                if (msg.type === 'status') status.textContent = msg.data;
                if (msg.type === 'sources') sources = Array.isArray(msg.data) ? msg.data : [];
                if (msg.type === 'content') {
                    answer += msg.data;
                    status.hidden = true;
                    body.innerHTML = renderAnswer(answer);
                    log.scrollTop = log.scrollHeight;
                }
                if (msg.type === 'error') {
                    status.hidden = true;
                    extra.insertAdjacentHTML('beforeend', `<p class="msg-error">${esc(msg.data)}</p>`);
                }
            }
        }
        if (answer) extra.insertAdjacentHTML('beforeend', sourcesHtml(sources));
    } catch (err) {
        status.hidden = true;
        if (err.status !== 401) extra.innerHTML = `<p class="msg-error">Couldn't get an answer: ${esc(err.message)}</p>`;
    } finally {
        chatBusy = false;
        $('send-btn').disabled = false;
        log.scrollTop = log.scrollHeight;
    }
}

$('chat-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const input = $('chat-input');
    const query = input.value.trim();
    if (!query || chatBusy) return;
    input.value = '';
    ask(query);
});
document.querySelectorAll('[data-q]').forEach(btn => btn.addEventListener('click', () => ask(btn.dataset.q)));

// Loaded once per signed-in user; the Refresh button reloads on demand.
let feedLoadedFor = null;
views.reports = {
    open() {
        if (feedLoadedFor !== currentUser.username) { feedLoadedFor = currentUser.username; loadFeed(); }
    },
};
