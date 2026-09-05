/* ==========================================================================
   app.js —— 泡泡改写前端主逻辑

   【它负责什么】
     1. 启动时从后端 /api/config 拉取配置，生成两个下拉框
     2. 底部导航切换三个页面
     3. 提交改写请求、渲染结果卡片（色条 + 双行解读 + 红心 + 复制）
     4. 积分累加与场景解锁（不刷新页面）
     5. 历史记录的分区展示、收藏管理、数据导出

   【阅读建议】
   代码按"工具函数 → 页面切换 → 三个页面各自的渲染逻辑 → 启动"的顺序排列，
   每一段前面都有注释说明它属于哪一块。
   ========================================================================== */

(function () {
  'use strict';

  /* =========================================================================
     零、全局状态
     ========================================================================= */

  // 从后端拉来的配置（场景、语言、七档风格及颜色）
  let CONFIG = null;

  // 当前这一次改写的结果，供红心收藏时读取
  let currentBatch = null;   // { historyId, input, sceneLabel, targetLabel, results:[] }

  // 历史页当前正在查看哪个语言分区（null 表示停留在四个方块的那一层）
  let currentHistoryLang = null;

  /* =========================================================================
     零点五、访问口令
     ========================================================================= */

  // 访客输入过的口令存在浏览器里，下次打开不用再输
  const CODE_KEY = 'pp_access_code';

  function getCode() {
    try { return localStorage.getItem(CODE_KEY) || ''; } catch (e) { return ''; }
  }
  function saveCode(c) {
    try { localStorage.setItem(CODE_KEY, c); } catch (e) { /* 无痕模式会失败，忽略 */ }
  }
  function clearCode() {
    try { localStorage.removeItem(CODE_KEY); } catch (e) {}
  }

  /** 显示口令遮罩层 */
  function showGate(msg) {
    $('gate').hidden = false;
    $('gateErr').textContent = msg || '';
    $('gateInput').value = '';
    $('gateInput').focus();
  }

  /** 校验口令；正确就存下来并关掉遮罩 */
  async function tryUnlock() {
    const code = $('gateInput').value.trim();
    if (!code) { $('gateErr').textContent = '请输入口令'; return; }

    $('gateBtn').disabled = true;
    $('gateBtn').textContent = '验证中…';
    try {
      const r = await fetch('/api/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code })
      });
      const d = await r.json();
      if (d.ok) {
        saveCode(code);
        $('gate').hidden = true;
        toast('已解锁');
      } else {
        $('gateErr').textContent = d.error || '口令不对';
      }
    } catch (e) {
      $('gateErr').textContent = '网络异常，请稍后重试';
    } finally {
      $('gateBtn').disabled = false;
      $('gateBtn').textContent = '进入';
    }
  }

  /* =========================================================================
     一、通用工具函数
     ========================================================================= */

  /** 简写：按 id 取元素 */
  function $(id) { return document.getElementById(id); }

  /**
   * 转义 HTML 特殊字符。
   * 【为什么必须做？】用户输入的文本会被拼进 innerHTML，
   * 如果不转义，输入 <script> 之类的内容就会被当成代码执行（XSS 安全问题）。
   */
  function esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /** 把时间戳格式化成 "09-05 14:30" 这种好读的形式 */
  function formatTime(ts) {
    const d = new Date(ts);
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  /** 屏幕底部弹一条轻提示，1.6 秒后自动消失 */
  let toastTimer = null;
  function toast(message) {
    const el = $('toast');
    el.textContent = message;
    el.classList.add('is-show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('is-show'), 1600);
  }

  /**
   * 复制文本到剪贴板。
   * 【需求：不通过 Ctrl+C，而是点按钮直接复制】
   * 优先用现代的 navigator.clipboard API；
   * 它需要 HTTPS 或 localhost 环境，所以准备了一个老办法作为降级方案，
   * 保证在任何环境下按钮都能用。
   */
  function copyToClipboard(text) {
    // 方案一：现代剪贴板 API
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text)
        .then(() => toast('已复制到剪贴板'))
        .catch(() => fallbackCopy(text));
      return;
    }
    // 方案二：降级方案
    fallbackCopy(text);
  }

  function fallbackCopy(text) {
    // 老办法：创建一个看不见的 textarea，选中它的内容再执行复制命令
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(ta);
    toast(ok ? '已复制到剪贴板' : '复制失败，请手动选中文字复制');
  }

  /* =========================================================================
     二、底部导航：三个页面的切换
     ========================================================================= */

  // 每个页面对应的标题，切换时同步更新顶部标题栏
  const PAGE_TITLES = {
    task:    ['任务执行区', 'Pragmatic Politeness Rephraser'],
    history: ['历史改写存储区', 'Archive by Target Language'],
    profile: ['个人专区', 'My Profile & Favourites']
  };

  function switchPage(name) {
    // 1. 所有页面先隐藏，再显示目标页面
    document.querySelectorAll('.page').forEach(p => p.classList.remove('page--active'));
    $('page-' + name).classList.add('page--active');

    // 2. 底部导航高亮
    document.querySelectorAll('.tabbar__btn').forEach(btn => {
      btn.classList.toggle('is-active', btn.dataset.page === name);
    });

    // 3. 更新顶部标题
    const t = PAGE_TITLES[name];
    $('pageTitle').textContent = t[0];
    $('pageSubtitle').textContent = t[1];

    // 4. 进入页面时刷新该页数据（保证数据永远是最新的）
    if (name === 'history') renderHistoryTiles();
    if (name === 'profile') renderProfilePage();

    // 5. 回到页面顶部
    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  /* =========================================================================
     三、页面一：任务执行区
     ========================================================================= */

  /* ---- 3.1 生成两个下拉框 ---- */
  function renderSelects() {
    const points = Storage.getPoints();

    // 场景下拉框：积分不够的场景显示成灰色不可选
    const sceneSel = $('sceneSelect');
    const prevScene = sceneSel.value;       // 记住用户原来选的，重建后尽量还原
    sceneSel.innerHTML = CONFIG.scenes.map(s => {
      const locked = s.lockedBy !== null && points < s.lockedBy;
      const label = locked ? `${s.label}（需${s.lockedBy}分解锁）` : s.label;
      return `<option value="${esc(s.key)}"${locked ? ' disabled' : ''}>${esc(label)}</option>`;
    }).join('');
    // 如果原来选的还能选，就还原选择
    if (prevScene && !sceneSel.querySelector(`option[value="${prevScene}"]`)?.disabled) {
      sceneSel.value = prevScene;
    }

    // 目标语言下拉框：四种语言始终可选
    const langSel = $('langSelect');
    if (!langSel.options.length) {
      langSel.innerHTML = CONFIG.languages.map(l =>
        `<option value="${esc(l.key)}">${esc(l.flag)} ${esc(l.label)}</option>`
      ).join('');
    }
  }

  /* ---- 3.2 引擎状态提示条 ---- */
  function renderEngineNotice() {
    const box = $('engineNotice');
    if (CONFIG.engineAvailable) {
      // 有额度信息就一并显示，方便你随时知道今天还能用多少次
      let quota = '';
      if (CONFIG.quota) {
        const q = CONFIG.quota;
        quota = `　今日剩余 <strong>${q.remaining}</strong> / ${q.limit} 次`;
      }
      box.innerHTML = `<div class="notice notice--info">
        大模型引擎已就绪（${esc(CONFIG.engineModel)}），改写结果与语用分析由模型实时生成。${quota}
      </div>`;
    } else {
      box.innerHTML = `<div class="notice notice--warn">
        <strong>离线演示模式</strong>：未检测到 API Key，当前由内置语用模板生成结果。
        在项目根目录新建 <code>.env</code> 并填入 DeepSeek 的 API Key 即可启用大模型引擎。
      </div>`;
    }
  }

  /* ---- 3.3 输入框字数统计 ---- */
  function bindCharCount() {
    const input = $('inputText');
    const counter = $('charCount');
    const max = CONFIG.maxInputLength;

    function update() {
      const len = input.value.length;
      counter.textContent = `${len} / ${max}`;
      counter.classList.toggle('is-over', len > max);
      // 超出上限或内容为空时，禁用提交按钮
      $('submitBtn').disabled = (len === 0 || len > max);
    }

    input.addEventListener('input', update);
    update();
  }

  /* ---- 3.4 最近 5 条历史请求 ---- */
  function renderRecent() {
    const box = $('recentList');
    const items = Storage.getRecent(5);

    if (!items.length) {
      box.innerHTML = `<div class="empty" style="padding:18px;">
        <span class="empty__icon">💬</span>还没有提问记录，试着改写第一句话吧
      </div>`;
      return;
    }

    box.innerHTML = items.map(h => `
      <div class="recent-item" data-fill="${esc(h.input)}" data-lang="${esc(h.targetLang)}" data-scene="${esc(h.scene)}">
        <span class="recent-item__text">${esc(h.input)}</span>
        <span class="recent-item__lang">${esc(h.targetLabel)}</span>
      </div>
    `).join('');

    // 点击某条最近记录，把它回填到输入框，方便重新改写
    box.querySelectorAll('.recent-item').forEach(el => {
      el.addEventListener('click', () => {
        $('inputText').value = el.dataset.fill;
        $('langSelect').value = el.dataset.lang;
        const opt = $('sceneSelect').querySelector(`option[value="${el.dataset.scene}"]`);
        if (opt && !opt.disabled) $('sceneSelect').value = el.dataset.scene;
        $('inputText').dispatchEvent(new Event('input'));
        $('inputText').focus();
        toast('已填回输入框');
      });
    });
  }

  /* ---- 3.5 提交改写请求 ---- */
  async function handleSubmit() {
    const text = $('inputText').value.trim();
    const scene = $('sceneSelect').value;
    const targetLang = $('langSelect').value;
    const includeSpecial = $('includeSpecial').checked;

    if (!text) { toast('请先输入要改写的文本'); return; }

    const btn = $('submitBtn');
    btn.disabled = true;
    btn.textContent = '改写中…';
    $('resultArea').innerHTML = `<div class="loading">正在生成各档礼貌程度的改写<span class="loading__dots"></span></div>`;

    try {
      // 向后端发请求。口令通过 X-Access-Code 请求头带上去
      const resp = await fetch('/api/rephrase', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Access-Code': getCode()
        },
        body: JSON.stringify({
          text: text,
          scene: scene,
          target_lang: targetLang,
          include_special: includeSpecial
        })
      });

      const data = await resp.json();

      // 口令不对或已被管理员改掉：清掉本地旧口令，重新弹遮罩
      if (resp.status === 401 || data.needCode) {
        clearCode();
        $('resultArea').innerHTML = '';
        showGate('口令已失效，请重新输入');
        return;
      }

      if (!resp.ok || !data.ok) {
        $('resultArea').innerHTML =
          `<div class="notice notice--error">改写失败：${esc(data.error || '服务器错误')}</div>`;
        return;
      }

      // 更新配置里的额度快照，让提示条上的"今日剩余"保持最新
      if (data.quota) CONFIG.quota = data.quota;
      renderEngineNotice();

      // ---- 成功：积 1 分（需求：积分仅与提问次数挂钩）----
      Storage.addPoint();

      // ---- 存入历史记录 ----
      const sceneLabel = CONFIG.scenes.find(s => s.key === scene).label;
      const langCfg = CONFIG.languages.find(l => l.key === targetLang);

      const record = Storage.addHistory({
        input: text,
        inputLang: data.input_lang,
        inputLangLabel: data.input_lang_label,
        scene: scene,
        sceneLabel: sceneLabel,
        targetLang: targetLang,
        targetLabel: langCfg.label,
        includeSpecial: includeSpecial,
        engine: data.engine,
        results: data.results
      });

      // ---- 记住这一批结果，供红心按钮使用 ----
      currentBatch = {
        historyId: record.id,
        input: text,
        sceneLabel: sceneLabel,
        targetLabel: langCfg.label,
        results: data.results
      };

      // ---- 渲染 ----
      renderResults(data);
      renderRecent();
      renderSelects();          // 积分变了，可能刚好解锁新场景（无需刷新页面）

    } catch (err) {
      console.error(err);
      $('resultArea').innerHTML =
        `<div class="notice notice--error">网络请求失败，请确认后端服务正在运行。</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = '开始改写';
    }
  }

  /* ---- 3.6 渲染结果卡片 ---- */
  function renderResults(data) {
    const box = $('resultArea');

    // 顶部信息条：识别出的原文语言 + 引擎说明
    let head = `<div class="section-title">改写结果 · 共 ${data.results.length} 档</div>`;
    head += `<div class="notice notice--info">
      系统识别的原文语言：<strong>${esc(data.input_lang_label)}</strong>
      ${data.engine === 'llm' ? '｜由大模型生成' : '｜由内置模板生成'}
    </div>`;
    if (data.note) {
      head += `<div class="notice notice--warn">${esc(data.note)}</div>`;
    }

    // 每一档一张卡片
    const cards = data.results.map((r, i) => `
      <div class="result-card" data-index="${i}">
        <!-- 顶部色条：颜色代表礼貌程度，红=粗鲁，绿=委婉，紫/粉=特殊风格 -->
        <div class="result-card__bar" style="background:${esc(r.color)}"></div>

        <div class="result-card__head">
          <span class="result-card__zh" style="color:${esc(r.color)}">${esc(r.zh)}</span>
          <span class="result-card__en">${esc(r.en)}</span>
        </div>

        <div class="result-card__text">${esc(r.text)}</div>

        <!-- 两行语言学 / 语用学解读 -->
        <div class="result-card__analysis">
          <div class="tag-line"><span class="tag-line__badge">语言</span><span>${esc(r.feature)}</span></div>
          <div class="tag-line"><span class="tag-line__badge">语用</span><span>${esc(r.strategy)}</span></div>
        </div>

        <div class="result-card__actions">
          <button class="icon-btn js-fav" data-index="${i}">♡ 收藏</button>
          <button class="icon-btn js-copy" data-index="${i}">⧉ 复制</button>
        </div>
      </div>
    `).join('');

    box.innerHTML = head + cards;

    // ---- 绑定红心收藏 ----
    box.querySelectorAll('.js-fav').forEach(btn => {
      btn.addEventListener('click', () => {
        const r = currentBatch.results[Number(btn.dataset.index)];
        const nowFaved = Storage.toggleFavorite(currentBatch.historyId, r, {
          input: currentBatch.input,
          sceneLabel: currentBatch.sceneLabel,
          targetLabel: currentBatch.targetLabel
        });
        btn.classList.toggle('is-faved', nowFaved);
        btn.textContent = nowFaved ? '♥ 已收藏' : '♡ 收藏';
        toast(nowFaved ? '已加入个人收藏' : '已取消收藏');
      });
    });

    // ---- 绑定一键复制 ----
    box.querySelectorAll('.js-copy').forEach(btn => {
      btn.addEventListener('click', () => {
        copyToClipboard(currentBatch.results[Number(btn.dataset.index)].text);
      });
    });
  }

  /* =========================================================================
     四、页面二：历史改写存储区
     ========================================================================= */

  /* ---- 4.1 第一层：四个语言方块 ---- */
  function renderHistoryTiles() {
    // 从分区详情返回时，要把详情层收起来
    $('historyTiles').hidden = false;
    $('historyDetail').hidden = true;
    currentHistoryLang = null;

    const counts = Storage.countByLang();
    $('langGrid').innerHTML = CONFIG.languages.map(l => `
      <div class="lang-tile" data-lang="${esc(l.key)}">
        <div class="lang-tile__flag">${esc(l.flag)}</div>
        <div class="lang-tile__name">${esc(l.label)}</div>
        <div class="lang-tile__count">${counts[l.key] || 0} 条记录</div>
      </div>
    `).join('');

    $('langGrid').querySelectorAll('.lang-tile').forEach(tile => {
      tile.addEventListener('click', () => openLangArchive(tile.dataset.lang));
    });
  }

  /* ---- 4.2 第二层：某个语言分区里的记录列表 ---- */
  function openLangArchive(langKey) {
    currentHistoryLang = langKey;
    const lang = CONFIG.languages.find(l => l.key === langKey);

    $('historyTiles').hidden = true;
    $('historyDetail').hidden = false;
    $('historyDetailTitle').textContent = `${lang.flag} ${lang.label}`;

    renderHistoryList();
  }

  function renderHistoryList() {
    const items = Storage.getHistoryByLang(currentHistoryLang);
    const box = $('historyList');

    if (!items.length) {
      box.innerHTML = `<div class="empty"><span class="empty__icon">🗂</span>这个语言分区还没有记录</div>`;
      return;
    }

    box.innerHTML = items.map(h => `
      <div class="history-item" data-id="${esc(h.id)}">
        <div class="history-item__head js-toggle">
          <div class="history-item__text">${esc(h.input)}</div>
          <div class="history-item__meta">
            <span class="chip">${esc(h.sceneLabel)}</span>
            <span class="chip">→ ${esc(h.targetLabel)}</span>
            <span>原文语言：${esc(h.inputLangLabel || '未识别')}</span>
            <span>· ${formatTime(h.ts)}</span>
            <button class="js-fix-lang" style="border:none;background:none;color:var(--brick);cursor:pointer;font-size:11px;padding:0;">修正</button>
            <button class="js-del" style="border:none;background:none;color:#C0392B;cursor:pointer;font-size:11px;padding:0;margin-left:auto;">删除</button>
          </div>
        </div>

        <!-- 展开后的各档结果，左侧竖色条直接体现礼貌程度 -->
        <div class="history-item__body" hidden>
          ${h.results.map(r => `
            <div class="mini-result">
              <div class="mini-result__bar" style="background:${esc(r.color)}"></div>
              <div style="flex:1;min-width:0;">
                <div class="mini-result__name" style="color:${esc(r.color)}">${esc(r.zh)} · ${esc(r.en)}</div>
                <div class="mini-result__text">${esc(r.text)}</div>
                <div class="tag-line" style="margin-top:3px;"><span class="tag-line__badge">语言</span><span>${esc(r.feature)}</span></div>
                <div class="tag-line"><span class="tag-line__badge">语用</span><span>${esc(r.strategy)}</span></div>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `).join('');

    // ---- 点击标题展开 / 收起 ----
    box.querySelectorAll('.history-item').forEach(item => {
      const body = item.querySelector('.history-item__body');

      item.querySelector('.js-toggle').addEventListener('click', (e) => {
        // 点到"修正""删除"这两个小按钮时不要触发展开
        if (e.target.classList.contains('js-fix-lang') || e.target.classList.contains('js-del')) return;
        body.hidden = !body.hidden;
      });

      // ---- 删除单条 ----
      item.querySelector('.js-del').addEventListener('click', () => {
        if (confirm('确定删除这条历史记录吗？（相关收藏也会一并移除）')) {
          Storage.deleteHistory(item.dataset.id);
          renderHistoryList();
          toast('已删除');
        }
      });

      // ---- 手动修正原文语言（弥补自动识别在短句上的误判）----
      item.querySelector('.js-fix-lang').addEventListener('click', () => {
        const options = CONFIG.languages.map((l, i) => `${i + 1}. ${l.label}`).join('\n');
        const input = prompt('自动识别可能在短句上出错，请选择正确的原文语言：\n' + options);
        const idx = Number(input) - 1;
        if (CONFIG.languages[idx]) {
          const l = CONFIG.languages[idx];
          Storage.updateInputLang(item.dataset.id, l.key, l.label);
          renderHistoryList();
          toast('已修正为：' + l.label);
        }
      });
    });
  }

  /* =========================================================================
     五、页面三：个人专区
     ========================================================================= */

  function renderProfilePage() {
    const profile = Storage.getProfile();

    // ---- 昵称 ----
    $('nicknameInput').value = profile.nickname;

    // ---- 积分与解锁进度 ----
    const points = profile.points;
    const need = CONFIG.unlockPoints;
    $('pointsValue').textContent = points;
    $('pointsProgress').style.width = Math.min(100, (points / need) * 100) + '%';
    $('pointsHint').textContent = points >= need
      ? '已解锁全部应用场景 🎉'
      : `再提问 ${need - points} 次即可解锁「对待事务机构或陌生人」场景`;

    // ---- 场景解锁清单 ----
    $('unlockList').innerHTML = CONFIG.scenes.map(s => {
      const locked = s.lockedBy !== null && points < s.lockedBy;
      return `<div class="unlock-item${locked ? ' unlock-item--locked' : ''}">
        <span>${locked ? '🔒' : '✅'}</span>
        <span>${esc(s.label)}</span>
        ${locked ? `<span class="unlock-item__need">需 ${s.lockedBy} 分</span>` : ''}
      </div>`;
    }).join('');

    // ---- 收藏列表 ----
    const favs = Storage.getFavorites();
    $('favCount').textContent = `(${favs.length})`;

    if (!favs.length) {
      $('favList').innerHTML = `<div class="empty"><span class="empty__icon">♡</span>还没有收藏，点击改写结果旁的红心即可收藏</div>`;
    } else {
      $('favList').innerHTML = favs.map(f => `
        <div class="fav-item">
          <div class="fav-item__bar" style="background:${esc(f.color)}"></div>
          <div class="fav-item__body">
            <div class="fav-item__text">${esc(f.text)}</div>
            <div class="fav-item__meta">
              <span class="chip" style="color:${esc(f.color)};background:transparent;border:1px solid ${esc(f.color)};">${esc(f.zh)}</span>
              <span class="chip">${esc(f.sceneLabel)}</span>
              <span class="chip">${esc(f.targetLabel)}</span>
            </div>
            <div class="fav-item__meta">原句：${esc(f.input)}</div>
          </div>
          <button class="fav-item__remove js-unfav" data-id="${esc(f.id)}" title="取消收藏">×</button>
        </div>
      `).join('');

      $('favList').querySelectorAll('.js-unfav').forEach(btn => {
        btn.addEventListener('click', () => {
          Storage.removeFavorite(btn.dataset.id);
          renderProfilePage();
          toast('已取消收藏');
        });
      });
    }
  }

  /* ---- 导出全部数据为 JSON 文件 ---- */
  function exportData() {
    const data = Storage.exportAll();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    // 造一个临时的下载链接并自动点击
    const a = document.createElement('a');
    a.href = url;
    a.download = `泡泡改写_数据备份_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast('已导出 JSON 文件');
  }

  /* =========================================================================
     六、启动：绑定所有事件，拉取配置
     ========================================================================= */

  function bindEvents() {
    // 底部导航
    document.querySelectorAll('.tabbar__btn').forEach(btn => {
      btn.addEventListener('click', () => switchPage(btn.dataset.page));
    });

    // 提交改写
    $('submitBtn').addEventListener('click', handleSubmit);

    // 口令遮罩：点按钮或按回车都能提交
    $('gateBtn').addEventListener('click', tryUnlock);
    $('gateInput').addEventListener('keydown', e => {
      if (e.key === 'Enter') tryUnlock();
    });

    // 历史页：返回语言分区
    $('historyBackBtn').addEventListener('click', renderHistoryTiles);

    // 历史页：清空当前语言分区
    $('clearLangBtn').addEventListener('click', () => {
      if (!currentHistoryLang) return;
      const lang = CONFIG.languages.find(l => l.key === currentHistoryLang);
      if (confirm(`确定清空「${lang.label}」分区的全部记录吗？此操作不可撤销。`)) {
        Storage.clearLang(currentHistoryLang);
        renderHistoryList();
        toast('已清空该分区');
      }
    });

    // 个人页：昵称输入即时保存
    $('nicknameInput').addEventListener('change', (e) => {
      Storage.setNickname(e.target.value);
      toast('昵称已保存');
    });

    // 个人页：导出 / 清空
    $('exportBtn').addEventListener('click', exportData);
    $('resetBtn').addEventListener('click', () => {
      if (confirm('这会删除全部历史记录、收藏、积分和昵称，确定吗？\n建议先点「导出全部数据」做个备份。')) {
        Storage.resetAll();
        renderProfilePage();
        renderRecent();
        renderSelects();
        toast('已清空所有数据');
      }
    });
  }

  /** 应用启动入口 */
  async function init() {
    try {
      const resp = await fetch('/api/config');
      CONFIG = await resp.json();
    } catch (e) {
      document.body.innerHTML =
        '<div style="padding:40px;text-align:center;color:#C0392B;">无法连接后端服务，请确认已运行 python app.py</div>';
      return;
    }

    renderEngineNotice();
    renderSelects();
    bindCharCount();
    renderRecent();
    bindEvents();

    // 服务器要求口令、而本地还没存过口令时，进门就弹遮罩
    if (CONFIG.codeRequired && !getCode()) showGate('');
  }

  // 等 HTML 结构准备好再启动
  document.addEventListener('DOMContentLoaded', init);
})();
