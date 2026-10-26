/**
 * LexGuard — Authentication & Session Management (lexguard-auth.js)
 * LexGuard Judicial Repository & Verification Platform
 *
 * Authentication is cookie-only in the browser: the JWT lives in the
 * backend's HttpOnly cookie and is never persisted in Web Storage. Only a
 * non-sensitive display profile (id/name/email/role/status) is kept in
 * tab-scoped sessionStorage so navigation can render synchronously. The
 * backend remains the authority for every permission decision.
 */

(function (window) {
  'use strict';

  window.LG = window.LG || {};

  const PROFILE_STORAGE_KEY = (LG.config && LG.config.PROFILE_STORAGE_KEY) || 'lg_profile';
  const LEGACY_SESSION_KEY = (LG.config && LG.config.SESSION_STORAGE_KEY) || 'lg_session';

  function canonicalRole(role) {
    const normalized = String(role || '').toLowerCase();
    if (normalized === 'senior_staff') return 'senior_staff';
    if (normalized === 'staff' || normalized === 'court_staff' || normalized === 'junior_staff') {
      return 'court_staff';
    }
    return normalized;
  }

  function sanitizeProfile(data) {
    if (!data || typeof data !== 'object') return null;
    return {
      user_id: data.user_id || data.id || null,
      name: data.name || 'User',
      email: data.email || '',
      role: data.role || 'public',
      status: data.status || 'active'
    };
  }

  // Remove any JWT-bearing session written by older frontend versions.
  try {
    window.localStorage.removeItem(LEGACY_SESSION_KEY);
  } catch (e) {}

  LG.session = {
    /**
     * Retrieve the non-sensitive display profile, if one is present.
     */
    get: function () {
      try {
        const raw = window.sessionStorage.getItem(PROFILE_STORAGE_KEY);
        return raw ? sanitizeProfile(JSON.parse(raw)) : null;
      } catch (e) {
        console.error('Failed to parse profile storage:', e);
        return null;
      }
    },

    /**
     * Save only display-profile fields. Tokens are deliberately discarded.
     */
    set: function (sessionData) {
      const profile = sanitizeProfile(sessionData);
      if (!profile) return;
      try {
        window.sessionStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
        window.localStorage.removeItem(LEGACY_SESSION_KEY);
      } catch (e) {
        console.error('Failed to save profile:', e);
      }
      if (sessionData && sessionData.csrf_token) {
        // Memory-only convenience for the current page. Subsequent pages
        // read the double-submit CSRF cookie directly.
        LG._csrf = sessionData.csrf_token;
      }
    },

    /**
     * Clear the display profile and any legacy token-bearing storage.
     */
    clear: function () {
      try {
        window.sessionStorage.removeItem(PROFILE_STORAGE_KEY);
        window.localStorage.removeItem(LEGACY_SESSION_KEY);
      } catch (e) {}
      LG._csrf = null;
    },

    /**
     * Backward-compatible accessor. Browser code must not possess the JWT;
     * authenticated requests rely on the HttpOnly cookie instead.
     */
    token: function () {
      return null;
    },

    /**
     * Get active user display info.
     */
    user: function () {
      const profile = LG.session.get();
      if (!profile) return null;
      return {
        id: profile.user_id,
        name: profile.name || 'User',
        email: profile.email || '',
        role: profile.role || 'public'
      };
    },

    /**
     * Whether a display profile is present. Protected API calls still fail
     * closed if the HttpOnly cookie is absent or expired.
     */
    isAuthenticated: function () {
      return !!LG.session.get();
    },

    /**
     * Check if the display profile has one of the specified roles. Senior
     * staff inherit ordinary staff UI access, but ordinary/legacy staff do
     * not satisfy a senior-only requirement.
     */
    hasRole: function (roles) {
      const user = LG.session.user();
      if (!user) return false;
      if (!Array.isArray(roles)) roles = [roles];

      const expanded = new Set();
      roles.forEach(function (role) {
        const target = String(role || '').toLowerCase();
        if (target === 'staff' || target === 'court_staff' || target === 'junior_staff') {
          expanded.add('court_staff');
          expanded.add('senior_staff');
        } else {
          expanded.add(target);
        }
      });
      return expanded.has(canonicalRole(user.role));
    },

    /**
     * Refresh the display profile from the authoritative /auth/me endpoint.
     * Returns the jQuery deferred when the API module is available.
     */
    hydrate: function () {
      if (!LG.api || !LG.api.auth || !LG.api.auth.me) return null;
      return LG.api.auth.me()
        .done(function (profile) {
          LG.session.set(profile);
        })
        .fail(function () {
          LG.session.clear();
        });
    }
  };

  /**
   * Route Guard: Check profile presence and role for UI routing. Backend
   * authorization remains authoritative for all protected resources.
   */
  LG.requireAuth = function (allowedRoles) {
    if (!LG.session.isAuthenticated()) {
      const redirectUrl = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = 'login.html?redirect=' + redirectUrl;
      return false;
    }

    if (allowedRoles && allowedRoles.length > 0) {
      if (!LG.session.hasRole(allowedRoles)) {
        window.location.href = 'unauthorized.html';
        return false;
      }
    }

    return true;
  };

})(window);
