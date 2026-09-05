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
    if (!p || typeof p !== 'object') return { nickname: '', points: 0 };
    return {
      nickname: typeof p.nickname === 'string' ? p.nickname : '',
      points: Number.isFinite(p.points) ? p.points : 0
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
      favorites: getFavorites()
    };
  }

  /** 清空所有数据（会弹确认框，在 app.js 里处理） */
  function resetAll() {
    try {
      localStorage.removeItem(KEY_PROFILE);
      localStorage.removeItem(KEY_HISTORY);
      localStorage.removeItem(KEY_FAVS);
    } catch (e) {
      console.warn('[storage] 清空失败：', e);
    }
  }

  /* ---------------------------------------------------------------
     把需要给外部使用的函数暴露出去
     --------------------------------------------------------------- */
  return {
    MAX_HISTORY,
    getProfile, setNickname, addPoint, getPoints,
    getHistory, addHistory, getHistoryByLang, countByLang, getRecent,
    deleteHistory, clearLang, updateInputLang,
    getFavorites, isFaved, toggleFavorite, removeFavorite,
    exportAll, resetAll
  };
})();
