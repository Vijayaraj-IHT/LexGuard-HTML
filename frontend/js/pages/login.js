/**
 * LexGuard — Sign In Page Controller (login.js)
 * Semester 5 Project · LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  // If already authenticated, redirect immediately
  if (LG.session.isAuthenticated()) {
    const redirectUrl = LG.utils.getQueryParam('redirect');
    if (redirectUrl) {
      window.location.href = decodeURIComponent(redirectUrl);
    } else if (LG.session.hasRole(['staff', 'court_staff', 'senior_staff'])) {
      window.location.href = 'admin.html';
    } else {
      window.location.href = 'search.html';
    }
    return;
  }

  const $form = $('#login-form');
  const $email = $('#login-email');
  const $password = $('#login-password');
  const $alert = $('#login-alert');
  const $submitBtn = $('#login-submit-btn');

  // Toggle Password Visibility
  $('#toggle-password').on('click', function () {
    const type = $password.attr('type') === 'password' ? 'text' : 'password';
    $password.attr('type', type);
    $('#toggle-password-icon').toggleClass('bi-eye bi-eye-slash');
  });

  // Quick-fill test account chips
  $('.quick-fill-btn').on('click', function () {
    const email = $(this).data('email');
    const password = $(this).data('password');
    $email.val(email);
    $password.val(password);
    $alert.addClass('d-none').text('');
  });

  // Handle Form Submission
  $form.on('submit', function (e) {
    e.preventDefault();
    $alert.addClass('d-none').text('');

    const email = $email.val().trim();
    const password = $password.val();

    if (!email || !password) {
      $alert.removeClass('d-none').text('Please enter both email and password.');
      return;
    }

    // Set loading state
    $submitBtn.prop('disabled', true).html(`
      <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
      <span>Authenticating...</span>
    `);

    LG.api.auth.login(email, password)
      .done(function (res) {
        LG.toast('Authenticated as ' + (res.name || 'User') + ' (' + res.role + ')', 'success');

        const redirectUrl = LG.utils.getQueryParam('redirect');
        setTimeout(function () {
          if (redirectUrl) {
            window.location.href = decodeURIComponent(redirectUrl);
          } else if (res.role === 'staff' || res.role === 'court_staff' || res.role === 'senior_staff') {
            window.location.href = 'admin.html';
          } else {
            window.location.href = 'search.html';
          }
        }, 600);
      })
      .fail(function (xhr) {
        let msg = 'Authentication failed. Please verify your credentials.';
        if (xhr.responseJSON && xhr.responseJSON.detail) {
          msg = typeof xhr.responseJSON.detail === 'string'
            ? xhr.responseJSON.detail
            : JSON.stringify(xhr.responseJSON.detail);
        }
        $alert.removeClass('d-none').text(msg);
      })
      .always(function () {
        $submitBtn.prop('disabled', false).html(`
          <span>Sign In</span>
          <i class="bi bi-arrow-right"></i>
        `);
      });
  });
});
