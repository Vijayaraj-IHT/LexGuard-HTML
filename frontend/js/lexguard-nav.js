/**
 * LexGuard — Dynamic Navigation & Layout Shell (lexguard-nav.js)
 * Semester 5 Project · LexGuard Judicial Repository & Verification Platform
 */

(function (window, $) {
  'use strict';

  window.LG = window.LG || {};
  LG.nav = {};

  /**
   * Initializes the shared Top Navbar and Sidebar navigation.
   */
  LG.nav.init = function () {
    const activePage = document.body.dataset.activePage || '';
    const user = LG.session.user();
    const isStaff = LG.session.hasRole(['staff', 'court_staff', 'senior_staff']);

    // 1. Render Top Navbar
    const navbarSlot = document.getElementById('navbar-slot');
    if (navbarSlot) {
      navbarSlot.innerHTML = `
        <nav class="lg-navbar">
          <!-- Mobile Sidebar Toggle -->
          <button class="btn btn-sm btn-judicial-outline d-lg-none me-2" id="sidebar-toggle" type="button" aria-label="Toggle navigation">
            <i class="bi bi-list fs-5"></i>
          </button>

          <!-- Brand Logo -->
          <a class="navbar-brand me-4" href="search.html">
            <div class="brand-emblem"><i class="bi bi-shield-fill-check"></i></div>
            <span>LexGuard</span>
          </a>

          <!-- Quick Search Bar (Navbar) -->
          <form class="d-none d-md-flex align-items-center ms-2 me-auto" id="nav-quick-search-form" style="max-width: 420px; width: 100%;">
            <div class="input-group input-group-sm">
              <span class="input-group-text bg-dark border-secondary border-opacity-25 text-secondary">
                <i class="bi bi-search"></i>
              </span>
              <input type="text" class="form-control" id="nav-quick-search-input" placeholder="Search case law, citation, CNR..." aria-label="Quick Search">
            </div>
          </form>

          <!-- Right Navigation Tools & User Menu -->
          <div class="d-flex align-items-center ms-auto gap-2">
            <!-- Theme Toggle -->
            <button class="btn btn-sm btn-judicial-outline p-1 px-2" id="theme-toggle" type="button" title="Toggle Light/Dark Theme">
              <i class="bi bi-moon-stars" id="theme-icon"></i>
            </button>

            <!-- Bookmarks Shortcut -->
            <a href="bookmarks.html" class="btn btn-sm btn-judicial-outline position-relative" title="Saved Bookmarks">
              <i class="bi bi-bookmark"></i>
            </a>

            <!-- User Profile / Session Menu -->
            ${user ? `
              <div class="dropdown">
                <button class="btn btn-sm btn-judicial-outline dropdown-toggle d-flex align-items-center gap-2" type="button" id="userMenuDropdown" data-bs-toggle="dropdown" aria-expanded="false">
                  <div class="rounded-circle bg-secondary bg-opacity-25 d-inline-flex align-items-center justify-content-center text-light" style="width: 26px; height: 26px; font-size: 0.75rem; font-weight: 700;">
                    ${LG.utils.escapeHtml((user.name || 'U').charAt(0).toUpperCase())}
                  </div>
                  <span class="d-none d-sm-inline fw-semibold">${LG.utils.escapeHtml(user.name)}</span>
                </button>
                <ul class="dropdown-menu dropdown-menu-dark dropdown-menu-end shadow" aria-labelledby="userMenuDropdown">
                  <li class="px-3 py-2 border-bottom border-secondary border-opacity-25">
                    <div class="fw-bold text-light">${LG.utils.escapeHtml(user.name)}</div>
                    <div class="small text-secondary">${LG.utils.escapeHtml(user.email)}</div>
                    <div class="mt-1">${LG.utils.getRoleBadge(user.role)}</div>
                  </li>
                  <li><a class="dropdown-item" href="bookmarks.html"><i class="bi bi-bookmarks me-2 text-warning"></i>My Saved Cases</a></li>
                  ${isStaff ? '<li><a class="dropdown-item" href="admin.html"><i class="bi bi-speedometer2 me-2 text-info"></i>Staff Workstation</a></li>' : ''}
                  <li><hr class="dropdown-divider border-secondary border-opacity-25"></li>
                  <li><a class="dropdown-item text-danger" href="javascript:void(0);" id="nav-logout-btn"><i class="bi bi-box-arrow-right me-2"></i>Sign Out</a></li>
                </ul>
              </div>
            ` : `
              <a href="login.html" class="btn btn-sm btn-gold">
                <i class="bi bi-box-arrow-in-right me-1"></i>Sign In
              </a>
            `}
          </div>
        </nav>
      `;
    }

    // 2. Render Left Sidebar
    const sidebarSlot = document.getElementById('sidebar-slot');
    if (sidebarSlot) {
      sidebarSlot.innerHTML = `
        <aside class="lg-sidebar" id="main-sidebar">
          <div class="lg-sidebar-section">
            <div class="lg-sidebar-heading">Legal Research</div>
            <ul class="lg-sidebar-nav">
              <li>
                <a href="search.html" class="lg-sidebar-link ${activePage === 'search' ? 'active' : ''}">
                  <i class="bi bi-search"></i>
                  <span>Hybrid Search</span>
                </a>
              </li>
              <li>
                <a href="acts-explorer.html" class="lg-sidebar-link ${activePage === 'acts' ? 'active' : ''}">
                  <i class="bi bi-book-half"></i>
                  <span>Statutory Explorer</span>
                </a>
              </li>
              <li>
                <a href="case-compare.html" class="lg-sidebar-link ${activePage === 'compare' ? 'active' : ''}">
                  <i class="bi bi-columns-gap"></i>
                  <span>Precedent Compare</span>
                </a>
              </li>
              <li>
                <a href="bookmarks.html" class="lg-sidebar-link ${activePage === 'bookmarks' ? 'active' : ''}">
                  <i class="bi bi-bookmarks"></i>
                  <span>Saved Research</span>
                </a>
              </li>
              <li>
                <a href="cause-list.html" class="lg-sidebar-link ${activePage === 'causelist' ? 'active' : ''}">
                  <i class="bi bi-clock-history"></i>
                  <span>Daily Cause List</span>
                </a>
              </li>
            </ul>
          </div>

          <div class="lg-sidebar-section">
            <div class="lg-sidebar-heading">Judicial Integrity</div>
            <ul class="lg-sidebar-nav">
              <li>
                <a href="verify.html" class="lg-sidebar-link ${activePage === 'verify' ? 'active' : ''}">
                  <i class="bi bi-shield-check"></i>
                  <span>Public Verifier</span>
                  <span class="lg-sidebar-badge">0-byte</span>
                </a>
              </li>
              <li>
                <a href="draft-assistant.html" class="lg-sidebar-link ${activePage === 'draft' ? 'active' : ''}">
                  <i class="bi bi-pen"></i>
                  <span>Draft Assistant</span>
                </a>
              </li>
              <li>
                <a href="case-upload.html" class="lg-sidebar-link ${activePage === 'upload' ? 'active' : ''}">
                  <i class="bi bi-cloud-arrow-up"></i>
                  <span>Case Ingestion</span>
                </a>
              </li>
              <li>
                <a href="screenshots-gallery.html" class="lg-sidebar-link ${activePage === 'gallery' ? 'active' : ''}">
                  <i class="bi bi-camera-fill text-warning"></i>
                  <span>Visual Showcase</span>
                  <span class="badge bg-warning text-dark ms-auto">30</span>
                </a>
              </li>
            </ul>
          </div>

          ${isStaff ? `
            <div class="lg-sidebar-section">
              <div class="lg-sidebar-heading">Court Administration</div>
              <ul class="lg-sidebar-nav">
                <li>
                  <a href="admin.html" class="lg-sidebar-link ${activePage === 'admin' ? 'active' : ''}">
                    <i class="bi bi-shield-lock"></i>
                    <span>Staff Workstation</span>
                    <span class="badge badge-gold ms-auto">STAFF</span>
                  </a>
                </li>
                <li>
                  <a href="audit-ledger.html" class="lg-sidebar-link ${activePage === 'audit' ? 'active' : ''}">
                    <i class="bi bi-diagram-3-fill text-warning"></i>
                    <span>Merkle Audit Ledger</span>
                  </a>
                </li>
              </ul>
            </div>
          ` : ''}

          <div class="mt-auto p-3 border-top border-secondary border-opacity-15">
            <div class="d-flex align-items-center gap-2">
              <div class="text-success"><i class="bi bi-circle-fill" style="font-size: 0.6rem;"></i></div>
              <div class="small text-secondary">
                <span class="text-light fw-semibold">LexGuard v2.4</span> · Madras HC &amp; SC
              </div>
            </div>
          </div>
        </aside>
      `;
    }

    // Attach Event Handlers
    // Sidebar toggle for mobile
    $('#sidebar-toggle').on('click', function () {
      $('#main-sidebar').toggleClass('show');
    });

    // Close mobile sidebar when clicking outside
    $(document).on('click', function (e) {
      if (!$(e.target).closest('#main-sidebar, #sidebar-toggle').length) {
        $('#main-sidebar').removeClass('show');
      }
    });

    // Logout click
    $('#nav-logout-btn').on('click', function (e) {
      e.preventDefault();
      LG.api.auth.logout();
    });

    // Quick search enter
    $('#nav-quick-search-form').on('submit', function (e) {
      e.preventDefault();
      const q = $('#nav-quick-search-input').val().trim();
      if (q) {
        window.location.href = 'search.html?q=' + encodeURIComponent(q);
      }
    });

    // Theme toggle init — Courtroom Red & White Light Theme
    document.documentElement.setAttribute('data-theme', 'light');
    document.documentElement.setAttribute('data-bs-theme', 'light');
    localStorage.setItem('lg_theme', 'light');
    $('#theme-icon').attr('class', 'bi bi-sun-fill text-danger');

    $('#theme-toggle').on('click', function () {
      LG.toast('Courtroom Red & White judicial theme is active.', 'info');
    });
  };

  // Auto-run when DOM ready
  $(document).ready(function () {
    LG.nav.init();
  });

})(window, window.jQuery);
