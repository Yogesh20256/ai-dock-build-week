let activeId;
const localChats = new Map();
const tabs = document.querySelector('#tabs');
const views = document.querySelector('#views');

window.dock.sites().then(sites => {
  sites.forEach((site, index) => {
    const tab = document.createElement('button');
    tab.textContent = site.short || site.name;
    tab.dataset.id = site.id;
    tab.addEventListener('click', () => select(site.id));
    tabs.appendChild(tab);

    const view = site.type === 'ollama' ? createLocalChat(site) : createWebView(site);
    views.appendChild(view);
    if (index === 0) select(site.id);
  });
});

function select(id) {
  activeId = id;
  document.querySelectorAll('nav button').forEach(el => el.classList.toggle('active', el.dataset.id === id));
  document.querySelectorAll('.provider-view').forEach(el => el.classList.toggle('active', el.id === `view-${id}`));
}

function createWebView(site) {
  const view = document.createElement('webview');
  view.id = `view-${site.id}`;
  view.className = 'provider-view';
  view.src = site.url;
  view.setAttribute('useragent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36');
  view.setAttribute('partition', `persist:ai-dock-${site.id}`);
  view.setAttribute('allowpopups', 'true');
  return view;
}

function createLocalChat(site) {
  const panel = document.createElement('div');
  panel.id = `view-${site.id}`;
  panel.className = 'provider-view local-chat';
  panel.innerHTML = `
    <div class="local-status"><span class="status-dot"></span>${site.name} · running locally</div>
    <div class="messages"><div class="message assistant">Hey! I’m ${site.name}, running privately on this laptop. How can I help?</div></div>
    <form class="composer">
      <label class="think-toggle" title="Enable deeper reasoning for this question">
        <input type="checkbox"><span>Think</span>
      </label>
      <textarea rows="2" placeholder="Message ${site.name}…"></textarea><button type="submit">➤</button>
    </form>`;
  const history = [];
  localChats.set(site.id, { history, panel, model: site.model });
  const form = panel.querySelector('form');
  const input = panel.querySelector('textarea');
  form.addEventListener('submit', event => { event.preventDefault(); sendLocal(site.id); });
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
  });
  return panel;
}

function addLocalMessage(panel, role, content, extraClass = '') {
  const message = document.createElement('div');
  message.className = `message ${role} ${extraClass}`;
  message.textContent = content;
  panel.querySelector('.messages').appendChild(message);
  message.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return message;
}

async function sendLocal(id) {
  const chat = localChats.get(id);
  const input = chat.panel.querySelector('textarea');
  const think = chat.panel.querySelector('.think-toggle input').checked;
  const text = input.value.trim();
  if (!text || chat.busy) return;
  input.value = '';
  chat.history.push({ role: 'user', content: text });
  addLocalMessage(chat.panel, 'user', text);
  const waiting = addLocalMessage(chat.panel, 'assistant', think ? 'Thinking deeply…' : 'Answering…', 'waiting');
  chat.busy = true;
  try {
    let answer = await window.dock.ollamaChat(chat.model, chat.history, think);
    answer = answer.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
    waiting.textContent = answer || 'I finished thinking but produced no visible answer.';
    waiting.classList.remove('waiting');
    chat.history.push({ role: 'assistant', content: answer });
  } catch (error) {
    waiting.textContent = `Could not reach Ollama: ${error.message}`;
    waiting.classList.add('error');
  } finally {
    chat.busy = false;
    input.focus();
  }
}

document.querySelector('#reload').addEventListener('click', () => {
  const view = document.querySelector(`#view-${activeId}`);
  if (view?.reload) view.reload();
});
document.querySelector('#hide').addEventListener('click', window.dock.collapse);
document.querySelector('#quit').addEventListener('click', window.dock.quit);
document.querySelector('#orb').addEventListener('click', window.dock.expand);

window.dock.onState(collapsed => document.body.classList.toggle('collapsed', collapsed));
window.dock.onReload(id => document.querySelector(`#view-${id}`)?.reload?.());
