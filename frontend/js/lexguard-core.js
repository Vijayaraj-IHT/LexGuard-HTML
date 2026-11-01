/**
 * LexGuard — Core Utilities & Configuration (lexguard-core.js)
 * LexGuard Judicial Repository & Verification Platform
 */

(function (window) {
  'use strict';

  window.LG = window.LG || {};

  /**
   * Resolve the API base URL.
   *
   * Order:
   *   1. <meta name="lg-api-base" content="...">  — per-deployment override
   *   2. window.LG_API_BASE                       — runtime override (tests, embeds)
   *   3. legacy dev heuristic                     — static server on :8888 / file://
   *   4. same origin /api/v1                      — served behind scripts/serve.py or a proxy
   */
  function resolveApiBase() {
    var meta = document.querySelector && document.querySelector('meta[name="lg-api-base"]');
    var candidate = (meta && meta.getAttribute('content')) || window.LG_API_BASE || '';
    if (candidate) return String(candidate).replace(/\/+$/, '');

    var isStaticDev =
      window.location.protocol === 'file:' || window.location.port === '8888';
    if (isStaticDev) return 'http://127.0.0.1:8000/api/v1';

    return '/api/v1';
  }

  // Core Configuration
  LG.config = {
    API_BASE: resolveApiBase(),
    SESSION_STORAGE_KEY: 'lg_session',
    CSRF_COOKIE_NAME: 'lexguard_csrf_token',
    APP_NAME: 'LexGuard',
    COURT_MADRAS: 'Madras High Court (Principal Seat)',
    COURT_MADURAI: 'Madras High Court (Madurai Bench)',
    COURT_SUPREME: 'Supreme Court of India'
  };

  // CSRF token cache
  LG._csrf = null;

  // Utility helpers
  LG.utils = {
    /**
     * Read a cookie value by name.
     */
    getCookie: function (name) {
      const match = document.cookie.match(new RegExp('(^|;\\s*)(' + name + ')=([^;]*)'));
      return match ? decodeURIComponent(match[3]) : null;
    },

    /**
     * Escape special HTML characters to prevent XSS.
     */
    escapeHtml: function (str) {
      if (str === null || str === undefined) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    },

    /**
     * Format an ISO date string to DD Month YYYY.
     */
    formatDate: function (isoString) {
      if (!isoString) return '—';
      try {
        const d = new Date(isoString);
        if (isNaN(d.getTime())) return isoString;
        return d.toLocaleDateString('en-IN', {
          day: 'numeric',
          month: 'short',
          year: 'numeric'
        });
      } catch (e) {
        return isoString;
      }
    },

    /**
     * Format ISO date string to full date and time.
     */
    formatDateTime: function (isoString) {
      if (!isoString) return '—';
      try {
        const d = new Date(isoString);
        if (isNaN(d.getTime())) return isoString;
        return d.toLocaleDateString('en-IN', {
          day: 'numeric',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });
      } catch (e) {
        return isoString;
      }
    },

    /**
     * Truncate a SHA-256 hash or hex string for display.
     */
    truncateHash: function (hash, len) {
      if (!hash) return '—';
      len = len || 8;
      if (hash.length <= len * 2 + 3) return hash;
      return hash.substring(0, len) + '...' + hash.substring(hash.length - len);
    },

    /**
     * Copy text to the user's clipboard and display a confirmation toast.
     */
    copyToClipboard: function (text, successMsg) {
      if (!text) return;
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(function () {
          LG.toast(successMsg || 'Copied to clipboard', 'success');
        }).catch(function () {
          LG.utils._fallbackCopy(text, successMsg);
        });
      } else {
        LG.utils._fallbackCopy(text, successMsg);
      }
    },

    _fallbackCopy: function (text, successMsg) {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      try {
        document.execCommand('copy');
        LG.toast(successMsg || 'Copied to clipboard', 'success');
      } catch (err) {
        LG.toast('Unable to copy to clipboard', 'danger');
      }
      document.body.removeChild(textarea);
    },

    /**
     * Get a query parameter value from the URL.
     */
    getQueryParam: function (param) {
      const urlParams = new URLSearchParams(window.location.search);
      return urlParams.get(param);
    },

    /**
     * Format a score float (0-1) to percentage string.
     */
    formatScore: function (score) {
      if (score === null || score === undefined) return '0%';
      const num = parseFloat(score);
      if (isNaN(num)) return '0%';
      return Math.round(num > 1 ? num : num * 100) + '%';
    },

    /**
     * Returns appropriate CSS badge class for a court name.
     */
    courtBadgeClass: function (court) {
      if (!court) return 'badge bg-secondary';
      const c = court.toLowerCase();
      if (c.includes('supreme')) return 'badge badge-court-supreme';
      if (c.includes('madurai')) return 'badge badge-court-madurai';
      if (c.includes('madras') || c.includes('chennai')) return 'badge badge-court-madras';
      return 'badge bg-secondary';
    },

    /**
     * Returns appropriate CSS badge class for a case/verification status.
     */
    statusBadgeClass: function (status) {
      if (!status) return 'badge bg-secondary';
      const s = status.toLowerCase();
      if (s === 'published' || s === 'verified' || s === 'active') return 'badge badge-status-verified';
      if (s.includes('pending')) return 'badge badge-status-pending';
      if (s === 'rejected' || s === 'tampered' || s === 'suspended') return 'badge badge-status-rejected';
      return 'badge bg-secondary';
    },

    /**
     * Return user-friendly badge HTML for role.
     */
    getRoleBadge: function (role) {
      switch (role) {
        case 'staff':
        case 'court_staff':
        case 'senior_staff':
          return '<span class="badge badge-gold"><i class="bi bi-shield-check me-1"></i>Court Staff</span>';
        case 'advocate':
          return '<span class="badge bg-primary"><i class="bi bi-briefcase me-1"></i>Advocate</span>';
        case 'scholar':
          return '<span class="badge bg-info text-dark"><i class="bi bi-mortarboard me-1"></i>Legal Scholar</span>';
        case 'public':
        default:
          return '<span class="badge bg-secondary"><i class="bi bi-person me-1"></i>Citizen</span>';
      }
    },

    /**
     * Return human-friendly name for role.
     */
    getRoleDisplayName: function (role) {
      switch (role) {
        case 'staff':
        case 'court_staff':
        case 'senior_staff':
          return 'Court Staff / Registrar';
        case 'advocate':
          return 'Advocate / Legal Counsel';
        case 'scholar':
          return 'Legal Scholar / Researcher';
        case 'public':
        default:
          return 'Citizen / Public';
      }
    }
  };

  /**
   * Brand logo fallback. Brand images have class "brand-logo-img" inside a
   * ".brand-emblem" wrapper. If the logo file fails to load, the wrapper gets
   * "is-fallback" and shows the built-in shield icon instead.
   * 'error' events on <img> do not bubble, so this uses a capture listener on
   * the document. That keeps the markup free of inline onerror handlers (CSP).
   */
  if (window.document && window.document.addEventListener) {
    window.document.addEventListener('error', function (event) {
      var target = event.target;
      if (target && target.classList && target.classList.contains('brand-logo-img')) {
        var wrap = target.closest ? target.closest('.brand-emblem') : null;
        if (wrap) wrap.classList.add('is-fallback');
      }
    }, true);
  }

})(window);
