/**
 * LexGuard — Toast Notification System (lexguard-toast.js)
 * Semester 5 Project · LexGuard Judicial Repository & Verification Platform
 */

(function (window) {
  'use strict';

  window.LG = window.LG || {};

  /**
   * Ensure the toast container element exists in the DOM.
   */
  function ensureToastContainer() {
    let container = document.getElementById('lg-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'lg-toast-container';
      container.className = 'lg-toast-container toast-container';
      document.body.appendChild(container);
    }
    return container;
  }

  /**
   * Show a Bootstrap 5 notification toast.
   * @param {string} message - Message text or HTML.
   * @param {string} type - 'success', 'danger'|'error', 'warning', 'info'
   * @param {string} [title] - Optional title
   */
  LG.toast = function (message, type, title) {
    type = type || 'info';
    if (type === 'error') type = 'danger';

    let icon = 'bi-info-circle-fill text-info';
    let defaultTitle = 'LexGuard Notification';

    if (type === 'success') {
      icon = 'bi-check-circle-fill text-success';
      defaultTitle = 'Success';
    } else if (type === 'danger') {
      icon = 'bi-exclamation-octagon-fill text-danger';
      defaultTitle = 'Notice';
    } else if (type === 'warning') {
      icon = 'bi-exclamation-triangle-fill text-warning';
      defaultTitle = 'Attention';
    }

    const toastTitle = title || defaultTitle;
    const container = ensureToastContainer();

    const toastId = 'toast-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
    const toastHtml = `
      <div id="${toastId}" class="toast lg-toast" role="alert" aria-live="assertive" aria-atomic="true" data-bs-delay="4500">
        <div class="toast-header bg-dark text-light border-bottom border-secondary border-opacity-25">
          <i class="bi ${icon} me-2 fs-6"></i>
          <strong class="me-auto font-sans fs-6">${LG.utils.escapeHtml(toastTitle)}</strong>
          <small class="text-secondary">Just now</small>
          <button type="button" class="btn-close btn-close-white ms-2" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
        <div class="toast-body fs-7">
          ${LG.utils.escapeHtml(message)}
        </div>
      </div>
    `;

    container.insertAdjacentHTML('beforeend', toastHtml);
    const toastEl = document.getElementById(toastId);

    if (window.bootstrap && window.bootstrap.Toast) {
      const bsToast = new window.bootstrap.Toast(toastEl);
      bsToast.show();
      toastEl.addEventListener('hidden.bs.toast', function () {
        toastEl.remove();
      });
    } else {
      // Fallback if bootstrap JS is not loaded yet
      setTimeout(function () {
        if (toastEl) toastEl.remove();
      }, 4500);
    }
  };

})(window);
