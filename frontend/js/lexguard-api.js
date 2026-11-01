/**
 * LexGuard — API Client Module (lexguard-api.js)
 * Full jQuery AJAX integration for all 9 API functional areas
 * LexGuard Judicial Repository & Verification Platform
 */

(function (window, $) {
  'use strict';

  window.LG = window.LG || {};

  /**
   * Generic API request handler wrapping $.ajax with JWT authentication,
   * CSRF protection, and standardized error processing.
   */
  function apiRequest(options, method, data) {
    if (typeof options === 'string') {
      options = {
        url: options,
        method: method || 'GET',
        data: data || null
      };
    }
    const url = options.url.startsWith('http')
      ? options.url
      : LG.config.API_BASE + (options.url.startsWith('/') ? options.url : '/' + options.url);

    const headers = options.headers || {};
    const token = LG.session.token();
    if (token) {
      headers['Authorization'] = 'Bearer ' + token;
    }
    const csrfToken = LG._csrf || LG.utils.getCookie(LG.config.CSRF_COOKIE_NAME) || (LG.session.get() ? LG.session.get().csrf_token : null);
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }

    const ajaxConfig = {
      url: url,
      method: options.method || 'GET',
      headers: headers,
      xhrFields: { withCredentials: true },
      dataType: options.dataType !== undefined ? options.dataType : 'json'
    };

    if (options.data) {
      if (options.isFormData) {
        ajaxConfig.data = options.data;
        ajaxConfig.processData = false;
        ajaxConfig.contentType = false;
      } else if (ajaxConfig.method === 'GET') {
        ajaxConfig.data = options.data;
      } else {
        ajaxConfig.data = JSON.stringify(options.data);
        ajaxConfig.contentType = 'application/json; charset=utf-8';
      }
    }

    return $.ajax(ajaxConfig).fail(function (xhr) {
      let errMsg = 'A network or server error occurred.';
      try {
        if (xhr.responseJSON && xhr.responseJSON.detail) {
          errMsg = typeof xhr.responseJSON.detail === 'string'
            ? xhr.responseJSON.detail
            : JSON.stringify(xhr.responseJSON.detail);
        } else if (xhr.responseText) {
          errMsg = xhr.responseText.substring(0, 150);
        }
      } catch (e) {}

      // Background calls (options.silent) must never redirect or toast on their own.
      if (options.silent) {
        return;
      }

      if (xhr.status === 401) {
        // If unauthenticated and on a protected page, redirect
        const currentPath = window.location.pathname.toLowerCase();
        if (!currentPath.includes('login') && !currentPath.includes('register') && !currentPath.includes('verify')) {
          LG.session.clear();
          LG.toast('Your session has expired. Please log in again.', 'warning');
          setTimeout(function () {
            window.location.href = 'login.html';
          }, 1200);
        }
      } else if (xhr.status === 403) {
        LG.toast('Access forbidden: ' + errMsg, 'danger');
      }

      return Promise.reject(xhr);
    });
  }

  // API Namespace
  LG.api = {
    request: apiRequest,

    /* -------------------------------------------------------------------------
       1. Authentication & RBAC (/auth)
       ------------------------------------------------------------------------- */
    auth: {
      login: function (email, password) {
        return apiRequest({
          url: '/auth/login',
          method: 'POST',
          data: { email: email, password: password }
        }).done(function (res) {
          if (res && res.access_token) {
            LG.session.set(res);
          }
        });
      },

      register: function (userData) {
        return apiRequest({
          url: '/auth/register',
          method: 'POST',
          data: userData
        });
      },

      logout: function () {
        return apiRequest({
          url: '/auth/logout',
          method: 'POST'
        }).always(function () {
          LG.session.clear();
          window.location.href = 'login.html';
        });
      },

      me: function () {
        return apiRequest({
          url: '/auth/me',
          method: 'GET'
        });
      }
    },

    /* -------------------------------------------------------------------------
       2. Case Repository & CIS Details (/cases)
       ------------------------------------------------------------------------- */
    cases: {
      list: function (params) {
        return apiRequest({
          url: '/cases/',
          method: 'GET',
          data: params || {}
        });
      },

      get: function (caseId) {
        return apiRequest({
          url: '/cases/' + encodeURIComponent(caseId),
          method: 'GET'
        });
      },

      verifyIntegrity: function (caseId) {
        return apiRequest({
          url: '/cases/' + encodeURIComponent(caseId) + '/verify-integrity',
          method: 'GET'
        });
      },

      getDownloadUrl: function (caseId) {
        const token = LG.session.token();
        return LG.config.API_BASE + '/cases/' + encodeURIComponent(caseId) + '/download' +
          (token ? '?token=' + encodeURIComponent(token) : '');
      },

      searchKeywords: function (caseId, keyword) {
        return apiRequest({
          url: '/cases/' + encodeURIComponent(caseId) + '/search-keywords',
          method: 'GET',
          data: { q: keyword }
        });
      },

      reExtract: function (caseId) {
        return apiRequest({
          url: '/cases/' + encodeURIComponent(caseId) + '/re-extract',
          method: 'POST'
        });
      },

      getStats: function () {
        return apiRequest({
          url: '/cases/stats',
          method: 'GET'
        });
      },

      search: function (query, params) {
        const payload = Object.assign({ query: query || '', limit: 20, offset: 0 }, params || {});
        return LG.api.search.query(payload);
      }
    },

    /* -------------------------------------------------------------------------
       3. Reciprocal Rank Fusion Search (/search)
       ------------------------------------------------------------------------- */
    search: {
      query: function (searchPayload) {
        return apiRequest({
          url: '/search/',
          method: 'POST',
          data: searchPayload
        });
      }
    },

    /* -------------------------------------------------------------------------
       4. Cryptographic Verification & Audit (/verification)
       ------------------------------------------------------------------------- */
    verification: {
      lookup: function (sha256Hash) {
        return apiRequest({
          url: '/verification/lookup',
          method: 'POST',
          data: { sha256_hash: sha256Hash }
        });
      }
    },

    /* -------------------------------------------------------------------------
       5. Precedent Comparator (/comparison)
       ------------------------------------------------------------------------- */
    comparison: {
      getPrecedents: function (caseId) {
        return apiRequest({
          url: '/comparison/precedents',
          method: 'GET',
          data: { case_id: caseId }
        });
      },

      compare: function (caseId1, caseId2) {
        return apiRequest({
          url: '/comparison/compare',
          method: 'POST',
          data: {
            case_id_1: caseId1,
            case_id_2: caseId2
          }
        });
      },

      compareMulti: function (caseIds) {
        return apiRequest({
          url: '/comparison/compare-multi',
          method: 'POST',
          data: { case_ids: caseIds }
        });
      }
    },

    /* -------------------------------------------------------------------------
       6. AI Draft Assistant (/draft)
       ------------------------------------------------------------------------- */
    draft: {
      analyze: function (draftText, caseType, court) {
        return apiRequest({
          url: '/draft/analyze',
          method: 'POST',
          data: {
            draft_text: draftText,
            case_type: caseType || 'Writ Petition',
            court: court || LG.config.COURT_MADRAS
          }
        });
      },

      getSessions: function () {
        return apiRequest({
          url: '/draft/sessions',
          method: 'GET'
        });
      },

      compareWithPrecedent: function (draftText, precedentCaseId) {
        return apiRequest({
          url: '/draft/compare-with-precedent',
          method: 'POST',
          data: {
            draft_text: draftText,
            precedent_case_id: precedentCaseId
          }
        });
      }
    },

    /* -------------------------------------------------------------------------
       7. Staff Administration & Merkle Audit Chain (/admin)
       ------------------------------------------------------------------------- */
    admin: {
      getQueue: function (statusFilter) {
        return apiRequest({
          url: '/admin/queue',
          method: 'GET',
          data: statusFilter ? { status_filter: statusFilter } : {}
        });
      },

      approve: function (caseId, notes) {
        return apiRequest({
          url: '/admin/approve/' + encodeURIComponent(caseId),
          method: 'POST',
          data: {
            status: 'published',
            review_note: (typeof notes === 'string' ? notes : (notes && notes.review_note) ? notes.review_note : 'Approved via Administrative Review')
          }
        });
      },

      getAuditLogs: function (limit, action) {
        const data = {};
        if (limit) data.limit = limit;
        if (action) data.action = action;
        return apiRequest({
          url: '/admin/audit-logs',
          method: 'GET',
          data: data
        });
      },

      verifyAuditChain: function () {
        return apiRequest({
          url: '/admin/verify-audit-chain',
          method: 'GET'
        });
      },

      getAnalytics: function () {
        return apiRequest({
          url: '/admin/analytics',
          method: 'GET'
        });
      }
    },

    /* -------------------------------------------------------------------------
       8. Saved Bookmarks (/bookmarks)
       ------------------------------------------------------------------------- */
    bookmarks: {
      list: function (binder) {
        const data = {};
        if (binder && binder !== 'all') data.binder = binder;
        return apiRequest({
          url: '/bookmarks/',
          method: 'GET',
          data: data
        });
      },

      getBinders: function () {
        return apiRequest({
          url: '/bookmarks/binders',
          method: 'GET'
        });
      },

      add: function (caseId, notes, binderName) {
        return apiRequest({
          url: '/bookmarks/',
          method: 'POST',
          data: {
            case_id: caseId,
            notes: notes || '',
            binder_name: binderName || 'General Research'
          }
        });
      },

      update: function (bookmarkId, data) {
        return apiRequest({
          url: '/bookmarks/' + encodeURIComponent(bookmarkId),
          method: 'PUT',
          data: data
        });
      },

      remove: function (bookmarkId) {
        return apiRequest({
          url: '/bookmarks/' + encodeURIComponent(bookmarkId),
          method: 'DELETE'
        });
      },

      exportMemo: function (binder) {
        const data = {};
        if (binder && binder !== 'all') data.binder = binder;
        return apiRequest({
          url: '/bookmarks/export-memo',
          method: 'GET',
          data: data
        });
      }
    },

    /* -------------------------------------------------------------------------
       9. Case Upload & Auto Ingestion Engine (/cases/upload)
       ------------------------------------------------------------------------- */
    upload: {
      uploadCase: function (formData) {
        return apiRequest({
          url: '/cases/upload',
          method: 'POST',
          data: formData,
          isFormData: true
        });
      },

      uploadAuto: function (formData) {
        return apiRequest({
          url: '/cases/upload-auto',
          method: 'POST',
          data: formData,
          isFormData: true
        });
      }
    },

    /**
     * Case-file preflight (system integrity checks).
     * Only getCasePreflightLatest is called automatically (by LG.preflight.init, read-only).
     * runCasePreflight is never called automatically, and quarantineMismatch is false unless a
     * staff member explicitly asks for it.
     */
    system: {
      getCasePreflightLatest: function (options) {
        return apiRequest($.extend({ url: '/system/case-preflight/latest', method: 'GET' }, options || {}));
      },

      runCasePreflight: function (mode, trigger, quarantineMismatch) {
        return apiRequest({
          url: '/system/case-preflight/runs',
          method: 'POST',
          data: {
            mode: mode,
            trigger: trigger,
            quarantine_mismatch: quarantineMismatch === true
          }
        });
      },

      getCasePreflightRun: function (runId) {
        return apiRequest({
          url: '/system/case-preflight/runs/' + encodeURIComponent(runId),
          method: 'GET'
        });
      }
    }
  };

})(window, window.jQuery);
