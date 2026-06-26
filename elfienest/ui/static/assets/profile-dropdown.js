/*!
 * Profile Dropdown — shared component for the ElfieNest console.
 * T13: 头像 SVG (8 color) + nickname + role pill + 退出登录
 *
 * Usage:
 *   ProfileDropdown.mount(container, { userData?, onLogout? })
 *   container.dispatchEvent(new CustomEvent('profile-dropdown:change-password'))
 *   container.dispatchEvent(new CustomEvent('profile-dropdown:edit-profile'))
 *
 * State: { user, csrf_token } loaded from /api/auth/me on mount (or passed in).
 * Renders: avatar SVG + nickname (fallback username) + role pill (admin red / user blue).
 * Dropdown: 改密码 / 编辑资料 / 退出登录.
 * 退出登录 → POST /api/auth/logout → redirect /login.html
 */
(function (global) {
  'use strict';

  // ── Avatar SVG renderer (per T13 spec) ──
  var AVATAR_COLORS = [
    '#ef4444', '#f97316', '#eab308', '#22c55e',
    '#06b6d4', '#3b82f6', '#a855f7', '#ec4899',
  ];

  function renderAvatar(username, colorIdx, size) {
    size = size || 36;
    var initial = (username || '?').charAt(0).toUpperCase();
    var fill = AVATAR_COLORS[(colorIdx % 8 + 8) % 8];
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '"' +
      ' style="display:block;border-radius:50%">' +
      '<circle cx="50%" cy="50%" r="50%" fill="' + fill + '"/>' +
      '<text x="50%" y="55%" font-size="' + (size * 0.5) + '" fill="#fff"' +
      ' text-anchor="middle" dominant-baseline="middle"' +
      ' font-family="system-ui,-apple-system,sans-serif" font-weight="600">' +
      escapeHtml(initial) + '</text></svg>';
  }

  var ICONS = {
    password: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 11V8a5 5 0 0 1 10 0v3"></path><path d="M6 11h12v9H6z"></path><path d="M12 15v2"></path></svg>',
    edit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z"></path><path d="m14 7 3 3"></path></svg>',
    logout: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 17l5-5-5-5"></path><path d="M15 12H3"></path><path d="M14 4h5v16h-5"></path></svg>',
    caret: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5"></path></svg>',
  };

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Inject scoped styles once ──
  var STYLE_ID = 'profile-dropdown-styles';
  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = [
      '.pd-trigger{',
      'display:flex;align-items:center;gap:8px;',
      'background:transparent;border:1px solid transparent;',
      'border-radius:var(--radius-sm,8px);padding:4px 8px;',
      'cursor:pointer;transition:background .15s,border-color .15s;',
      'color:var(--text-primary,#e8e8f0);font-size:13px;font-family:inherit;',
      '}',
      '.pd-trigger:hover{background:rgba(255,255,255,.04);border-color:var(--border-subtle,#2a2a40)}',
      '.pd-trigger.open{background:rgba(255,255,255,.06);border-color:var(--border-subtle,#2a2a40)}',
      '.pd-avatar{flex-shrink:0;line-height:0}',
      '.pd-meta{display:flex;flex-direction:column;align-items:flex-start;gap:2px;min-width:0}',
      '.pd-name{font-size:13px;font-weight:600;color:var(--text-primary,#e8e8f0);',
      'max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
      '.pd-role{font-size:10px;font-weight:600;padding:1px 7px;border-radius:99px;',
      'border:1px solid transparent;letter-spacing:0;text-transform:uppercase;line-height:1.4}',
      '.pd-role.admin{background:rgba(239,68,68,.15);color:var(--error,#ef4444);',
      'border-color:rgba(239,68,68,.3)}',
      '.pd-role.user{background:rgba(108,124,247,.15);color:var(--accent,#6c7cf7);',
      'border-color:rgba(108,124,247,.3)}',
      '.pd-caret{margin-left:2px;color:var(--text-secondary,#9898b0);',
      'transition:transform .15s;flex-shrink:0;line-height:0}',
      '.pd-caret svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round;stroke-width:2}',
      '.pd-trigger.open .pd-caret{transform:rotate(180deg)}',
      '.pd-menu{',
      'display:none;position:absolute;min-width:180px;',
      'background:var(--bg-secondary,#1a1a2e);border:1px solid var(--border-subtle,#2a2a40);',
      'border-radius:var(--radius-sm,8px);box-shadow:var(--shadow-md,0 4px 12px rgba(0,0,0,.4));',
      'padding:6px;z-index:300;overflow:hidden;',
      '}',
      '.pd-menu.open{display:block}',
      '.pd-menu-item{',
      'display:flex;align-items:center;gap:8px;width:100%;',
      'padding:9px 12px;border:none;background:transparent;',
      'color:var(--text-primary,#e8e8f0);font-size:13px;font-family:inherit;',
      'cursor:pointer;border-radius:6px;transition:background .12s;text-align:left;',
      '}',
      '.pd-menu-item svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round;stroke-width:2;flex-shrink:0}',
      '.pd-menu-item:hover{background:rgba(255,255,255,.06)}',
      '.pd-menu-item.danger{color:var(--error,#ef4444)}',
      '.pd-menu-item.danger:hover{background:rgba(239,68,68,.1)}',
      '.pd-menu-divider{height:1px;background:var(--border-subtle,#2a2a40);margin:4px 6px}',
      '.pd-placeholder{font-size:12px;color:var(--text-secondary,#9898b0);padding:4px 8px}',
    ].join('');
    document.head.appendChild(style);
  }

  // ── Mount ──
  function mount(container, options) {
    if (!container) return;
    options = options || {};
    injectStyles();

    // Clear any existing content to prevent duplicates
    container.innerHTML = '';

    // Wrapper for relative positioning of the menu
    var wrap = document.createElement('div');
    wrap.style.position = 'relative';
    wrap.style.display = 'inline-flex';
    container.appendChild(wrap);

    var trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'pd-trigger';
    trigger.setAttribute('aria-haspopup', 'true');
    trigger.setAttribute('aria-expanded', 'false');

    var menu = document.createElement('div');
    menu.className = 'pd-menu';
    menu.setAttribute('role', 'menu');
    wrap.appendChild(trigger);
    wrap.appendChild(menu);

    var state = { user: null, csrfToken: '' };
    var open = false;

    function setOpen(v) {
      open = v;
      trigger.classList.toggle('open', open);
      menu.classList.toggle('open', open);
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    function closeMenu() { setOpen(false); }

    function renderNotLoggedIn() {
      trigger.innerHTML = '<span class="pd-placeholder">未登录</span>';
      trigger.disabled = true;
      trigger.style.cursor = 'default';
      menu.innerHTML = '';
    }

    function renderUser(data) {
      state.user = data;
      state.csrfToken = data.csrf_token || '';

      var displayName = data.nickname || data.username || '?';
      var colorIdx = (typeof data.avatar_color === 'number') ? data.avatar_color : 0;
      var role = data.role || 'user';
      var roleClass = role === 'admin' ? 'admin' : 'user';
      var roleLabel = role === 'admin' ? 'admin' : 'user';

      trigger.innerHTML =
        '<span class="pd-avatar">' + renderAvatar(data.username, colorIdx, 28) + '</span>' +
        '<span class="pd-meta">' +
          '<span class="pd-name">' + escapeHtml(displayName) + '</span>' +
          '<span class="pd-role ' + roleClass + '">' + escapeHtml(roleLabel) + '</span>' +
        '</span>' +
        '<span class="pd-caret">' + ICONS.caret + '</span>';

      menu.innerHTML =
        '<button class="pd-menu-item" data-action="change-password" role="menuitem">' + ICONS.password + '改密码</button>' +
        '<button class="pd-menu-item" data-action="edit-profile" role="menuitem">' + ICONS.edit + '编辑资料</button>' +
        '<div class="pd-menu-divider"></div>' +
        '<button class="pd-menu-item danger" data-action="logout" role="menuitem">' + ICONS.logout + '退出登录</button>';
    }

    async function fetchMe() {
      try {
        var resp = await fetch('/api/auth/me', { credentials: 'include' });
        if (!resp.ok) { renderNotLoggedIn(); return; }
        var data = await resp.json();
        renderUser(data);
      } catch (e) {
        renderNotLoggedIn();
      }
    }

    // ── Event wiring ──
    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      if (trigger.disabled) return;
      setOpen(!open);
    });

    menu.addEventListener('click', function (e) {
      var item = e.target.closest('.pd-menu-item');
      if (!item) return;
      var action = item.dataset.action;
      closeMenu();
      if (action === 'logout') {
        doLogout();
      } else if (action === 'change-password') {
        container.dispatchEvent(new CustomEvent('profile-dropdown:change-password'));
      } else if (action === 'edit-profile') {
        container.dispatchEvent(new CustomEvent('profile-dropdown:edit-profile'));
      }
    });

    // Close on outside click
    document.addEventListener('click', function (e) {
      if (open && !wrap.contains(e.target)) closeMenu();
    });

    // Close on Escape
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && open) closeMenu();
    });

    async function doLogout() {
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          credentials: 'include',
          headers: { 'X-CSRF-Token': state.csrfToken },
        });
      } catch (_) { /* ignore — redirect anyway */ }
      if (typeof options.onLogout === 'function') {
        try { options.onLogout(); } catch (_) {}
      }
      window.location.href = '/static/login.html';
    }

    // ── Init: use provided userData or fetch ──
    if (options.userData) {
      renderUser(options.userData);
    } else {
      fetchMe();
    }

    return {
      refresh: fetchMe,
      close: closeMenu,
      getUser: function () { return state.user; },
    };
  }

  global.ProfileDropdown = { mount: mount, renderAvatar: renderAvatar };
})(window);
