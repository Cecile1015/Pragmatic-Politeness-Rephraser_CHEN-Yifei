/* ==========================================================================
   storage.js —— 本地数据存储模块

   【作用】
   把"历史记录、收藏、昵称、积分"存进浏览器的 localStorage，
   这样刷新页面、关掉浏览器再打开，数据都还在。

   【为什么单独抽一个文件？】
   所有和存储相关的读写都集中在这里，app.js 只管调用，
   以后如果想改成存到服务器数据库，只需要改这一个文件。

   【数据结构】
     pp_profile   : { nickname: "昵称", points: 7 }
     pp_history   : [ { id, ts, input, inputLang, scene, sceneLabel,
                        targetLang, targetLabel, includeSpecial, results:[...] } ]
     pp_favorites : [ { id, historyId, ...一条改写结果的全部字段, input, sceneLabel, targetLabel, ts } ]
   ========================================================================== */

const Storage = (function () {

  // localStorage 里用到的三个键名，加 pp_ 前缀避免和其他网站冲突
  const KEY_PROFILE = 'pp_profile';
  const KEY_HISTORY = 'pp_history';
  const KEY_FAVS    = 'pp_favorites';
  const KEY_GAME    = 'pp_challenges';   // 游戏交互：历次挑战作答与得分

  // 历史记录上限。localStorage 总容量约 5MB，超过上限就淘汰最旧的一条
  const MAX_HISTORY = 200;

  /* ---------------------------------------------------------------
     底层读写：统一做 try/catch，避免浏览器禁用 localStorage 时整个页面崩掉
     （例如 Safari 无痕模式就可能禁止写入）
     --------------------------------------------------------------- */
  function read(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return fallback;
      return JSON.parse(raw);
    } catch (e) {
      console.warn('[storage] 读取失败：', key, e);
      return fallback;
    }
  }

  function write(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      console.warn('[storage] 写入失败（可能是空间已满）：', key, e);
      return false;
    }
  }

  /* ---------------------------------------------------------------
     生成唯一 ID：时间戳 + 随机数，够用且不需要额外的库
     --------------------------------------------------------------- */
  function makeId() {
    return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
  }

  /* =============================================================
     一、个人资料（昵称 + 积分）
     ============================================================= */

  function getProfile() {
    const p = read(KEY_PROFILE, null);
    // 第一次使用时给一份默认值
    if (!p || typeof p !== 'object') {
      return { nickname: '', points: 0, streak: 0, bestStreak: 0, lastDailyDay: '' };
    }
    return {
      nickname: typeof p.nickname === 'string' ? p.nickname : '',
      points: Number.isFinite(p.points) ? p.points : 0,
      // ---- 以下三项是"游戏交互"页新增的 ----
      streak: Number.isFinite(p.streak) ? p.streak : 0,               // 当前连续打卡天数
      bestStreak: Number.isFinite(p.bestStreak) ? p.bestStreak : 0,   // 历史最长连续
      lastDailyDay: typeof p.lastDailyDay === 'string' ? p.lastDailyDay : '' // 上次完成每日挑战的日期
    };
  }

  function setNickname(name) {
    const p = getProfile();
    p.nickname = String(name || '').slice(0, 16);
    write(KEY_PROFILE, p);
    return p;
  }

  /** 积分 +1（每提交一次改写请求调用一次） */
  function addPoint() {
    const p = getProfile();
    p.points = p.points + 1;
    write(KEY_PROFILE, p);
    return p;
  }

  function getPoints() {
    return getProfile().points;
  }

  /** 一次加多个积分（挑战完成时用，改写仍然是一次 +1） */
  function addPoints(n) {
    const p = getProfile();
    p.points = p.points + (Number(n) || 0);
    write(KEY_PROFILE, p);
    return p.points;
  }

  /* =============================================================
     二点五、游戏交互：连续打卡与挑战记录
     ============================================================= */

  /** 把 'YYYY-MM-DD' 往前推一天，用来判断"昨天有没有打卡" */
  function prevDay(dayStr) {
    const d = new Date(dayStr + 'T12:00:00');   // 用正午避免时区把日期推错
    d.setDate(d.getDate() - 1);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  /** 今天（浏览器本地时区）的 'YYYY-MM-DD' */
  function today() {
    const d = new Date();
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  /** 今天的每日挑战是否已经完成 */
  function dailyDone(day) {
    return getProfile().lastDailyDay === (day || today());
  }

  /**
   * 完成每日挑战后更新连续打卡天数。
   *
   * 规则：
   *   昨天也打了卡  -> 连续 +1
   *   昨天没打（断了）-> 重新从 1 开始
   *   今天已经打过   -> 不重复计算
   */
  function markDaily(day) {
    const d = day || today();
    const p = getProfile();
    if (p.lastDailyDay === d) return p;          // 今天已记过，不重复

    p.streak = (p.lastDailyDay === prevDay(d)) ? p.streak + 1 : 1;
    p.lastDailyDay = d;
    if (p.streak > p.bestStreak) p.bestStreak = p.streak;
    write(KEY_PROFILE, p);
    return p;
  }

  /**
   * 读取当前连续天数，但会先检查是否已经断了。
   * 例如上次打卡是三天前，那 streak 显示应该是 0 而不是旧值。
   */
  function currentStreak() {
    const p = getProfile();
    if (!p.lastDailyDay) return 0;
    const t = today();
    if (p.lastDailyDay === t || p.lastDailyDay === prevDay(t)) return p.streak;
    return 0;   // 断了
  }

  function getGames() {
    const l = read(KEY_GAME, []);
    return Array.isArray(l) ? l : [];
  }

  /** 存一条挑战记录（最多留 200 条，和历史记录一致） */
  function addGame(rec) {
    const l = getGames();
    l.unshift(Object.assign({ id: makeId(), ts: Date.now() }, rec));
    if (l.length > MAX_HISTORY) l.length = MAX_HISTORY;
    write(KEY_GAME, l);
    return l[0];
  }

  /** 挑战统计：做过几题、平均分、最高分 */
  function gameStats() {
    const l = getGames();
    if (!l.length) return { count: 0, avg: 0, best: 0 };
    const scores = l.map(g => Number(g.overall) || 0);
    return {
      count: l.length,
      avg: Math.round(scores.reduce((a, b) => a + b, 0) / scores.length),
      best: Math.max.apply(null, scores)
    };
  }

  /* =============================================================
     二、历史记录
     ============================================================= */

  function getHistory() {
    const list = read(KEY_HISTORY, []);
    return Array.isArray(list) ? list : [];
  }

  /**
   * 新增一条历史记录（最新的排在数组最前面）
   * @param {Object} record 完整请求记录
   * @returns {Object} 带上 id 和时间戳的记录
   */
  function addHistory(record) {
    const list = getHistory();
    const item = Object.assign({
      id: makeId(),
      ts: Date.now()
    }, record);

    list.unshift(item);

    // 超过上限就砍掉最旧的
    if (list.length > MAX_HISTORY) {
      list.length = MAX_HISTORY;
    }

    write(KEY_HISTORY, list);
    return item;
  }

  /** 取某个目标语言分区的记录（历史页第二层用） */
  function getHistoryByLang(langKey) {
    return getHistory().filter(h => h.targetLang === langKey);
  }

  /** 统计每种目标语言各有多少条（历史页方块上的数字） */
  function countByLang() {
    const counts = {};
    getHistory().forEach(h => {
      counts[h.targetLang] = (counts[h.targetLang] || 0) + 1;
    });
    return counts;
  }

  /** 取最近 N 条记录（任务页输入区下方显示最近 5 条） */
  function getRecent(n) {
    return getHistory().slice(0, n || 5);
  }

  function deleteHistory(id) {
    const list = getHistory().filter(h => h.id !== id);
    write(KEY_HISTORY, list);
    // 同时把指向这条记录的收藏也清掉，避免出现"孤儿收藏"
    const favs = getFavorites().filter(f => f.historyId !== id);
    write(KEY_FAVS, favs);
  }

  /** 清空某个语言分区 */
  function clearLang(langKey) {
    const removedIds = getHistory().filter(h => h.targetLang === langKey).map(h => h.id);
    write(KEY_HISTORY, getHistory().filter(h => h.targetLang !== langKey));
    write(KEY_FAVS, getFavorites().filter(f => removedIds.indexOf(f.historyId) === -1));
  }

  /** 手动修正某条记录的"原文语言"识别结果 */
  function updateInputLang(id, langKey, langLabel) {
    const list = getHistory();
    const item = list.find(h => h.id === id);
    if (item) {
      item.inputLang = langKey;
      item.inputLangLabel = langLabel;
      write(KEY_HISTORY, list);
    }
  }

  /* =============================================================
     三、收藏（红心）
     ============================================================= */

  function getFavorites() {
    const list = read(KEY_FAVS, []);
    return Array.isArray(list) ? list : [];
  }

  /** 判断某条历史记录下的某一档是否已收藏 */
  function isFaved(historyId, levelKey) {
    return getFavorites().some(f => f.historyId === historyId && f.key === levelKey);
  }

  /**
   * 切换收藏状态：已收藏就取消，未收藏就加入
   * @returns {boolean} 操作后是否处于"已收藏"状态
   */
  function toggleFavorite(historyId, result, context) {
    const favs = getFavorites();
    const idx = favs.findIndex(f => f.historyId === historyId && f.key === result.key);

    if (idx >= 0) {
      favs.splice(idx, 1);          // 取消收藏
      write(KEY_FAVS, favs);
      return false;
    }

    favs.unshift({
      id: makeId(),
      historyId: historyId,
      ts: Date.now(),
      // 改写结果本身
      key: result.key,
      zh: result.zh,
      en: result.en,
      color: result.color,
      text: result.text,
      feature: result.feature,
      strategy: result.strategy,
      // 上下文信息，方便在收藏页显示"这句话是在什么条件下改写出来的"
      input: context.input,
      sceneLabel: context.sceneLabel,
      targetLabel: context.targetLabel
    });
    write(KEY_FAVS, favs);
    return true;
  }

  function removeFavorite(favId) {
    write(KEY_FAVS, getFavorites().filter(f => f.id !== favId));
  }

  /* =============================================================
     四、数据导出与清空
     ============================================================= */

  /** 把全部数据打包成一个对象，用于导出 JSON 文件 */
  function exportAll() {
    return {
      exportedAt: new Date().toISOString(),
      app: '泡泡改写 2P Rephraser',
      profile: getProfile(),
      history: getHistory(),
      favorites: getFavorites(),
      challenges: getGames()
    };
  }

  /**
   * 只导出挑战作答，做成 CSV。
   * 【为什么单独做一个 CSV】
   * 这是受试者要发给研究者的东西，CSV 能直接拖进 Excel 或 R 做分析，
   * 比 JSON 好用得多。字段顺序按"情境→作答→得分"排，方便肉眼校对。
   */
  function exportGamesCSV() {
    const rows = getGames();
    const head = ['时间', '题号', '模式', '言语行为', '场景', '情境',
                  '作答', '总分', '得体度', '策略性', '自然度', '评分引擎'];

    // CSV 转义：字段里有逗号、引号或换行时，要用双引号包起来并把引号翻倍
    const cell = v => {
      const s = String(v == null ? '' : v);
      return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };

    const lines = [head.map(cell).join(',')];
    rows.forEach(g => {
      const d = g.dimensions || {};
      lines.push([
        new Date(g.ts).toISOString(), g.cid, g.mode === 'daily' ? '每日挑战' : '自由练习',
        g.act, g.sceneLabel, g.context, g.answer,
        g.overall, d.appropriateness, d.strategy, d.naturalness, g.engine
      ].map(cell).join(','));
    });

    // BOM 开头，否则 Excel 打开中文会乱码
    return '﻿' + lines.join('\r\n');
  }

  /** 清空所有数据（会弹确认框，在 app.js 里处理） */
  function resetAll() {
    try {
      localStorage.removeItem(KEY_PROFILE);
      localStorage.removeItem(KEY_HISTORY);
      localStorage.removeItem(KEY_FAVS);
      localStorage.removeItem(KEY_GAME);
    } catch (e) {
      console.warn('[storage] 清空失败：', e);
    }
  }

  /* ---------------------------------------------------------------
     把需要给外部使用的函数暴露出去
     --------------------------------------------------------------- */
  return {
    MAX_HISTORY,
    getProfile, setNickname, addPoint, addPoints, getPoints,
    getHistory, addHistory, getHistoryByLang, countByLang, getRecent,
    deleteHistory, clearLang, updateInputLang,
    getFavorites, isFaved, toggleFavorite, removeFavorite,
    // 游戏交互
    today, dailyDone, markDaily, currentStreak,
    getGames, addGame, gameStats, exportGamesCSV,
    exportAll, resetAll
  };
})();
