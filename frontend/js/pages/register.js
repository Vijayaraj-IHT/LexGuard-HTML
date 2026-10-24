/**
 * LexGuard — Registration Page Controller (register.js)
 * LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  const $form = $('#register-form');
  const $name = $('#reg-name');
  const $email = $('#reg-email');
  const $role = $('#reg-role');
  const $credentialGroup = $('#credential-group');
  const $credentialLabel = $('#credential-label');
  const $credentialInput = $('#reg-credential');
  const $password = $('#reg-password');
  const $confirmPassword = $('#reg-confirm-password');
  const $alert = $('#register-alert');
  const $submitBtn = $('#register-submit-btn');

  // Handle role selection changes
  $role.on('change', function () {
    const selectedRole = $(this).val();
    if (selectedRole === 'advocate') {
      $credentialGroup.removeClass('d-none');
      $credentialLabel.text('Bar Council Enrollment Number');
      $credentialInput.attr('placeholder', 'MS/1234/2020').prop('required', true);
    } else if (selectedRole === 'scholar') {
      $credentialGroup.removeClass('d-none');
      $credentialLabel.text('University / Institutional ID');
      $credentialInput.attr('placeholder', 'NLU/RES/8821').prop('required', true);
    } else {
      // Public citizen
      $credentialGroup.addClass('d-none');
      $credentialInput.val('').prop('required', false);
    }
  });

  // Handle registration submission
  $form.on('submit', function (e) {
    e.preventDefault();
    $alert.addClass('d-none').text('');

    const name = $name.val().trim();
    const email = $email.val().trim();
    const role = $role.val();
    const credentialId = $credentialInput.val().trim();
    const password = $password.val();
    const confirmPassword = $confirmPassword.val();

    if (!name || !email || !password) {
      $alert.removeClass('d-none').text('Please fill in all required fields.');
      return;
    }

    if (password !== confirmPassword) {
      $alert.removeClass('d-none').text('Passwords do not match.');
      return;
    }

    if (password.length < 6) {
      $alert.removeClass('d-none').text('Password must be at least 6 characters.');
      return;
    }

    // Set loading state
    $submitBtn.prop('disabled', true).html(`
      <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
      <span>Registering...</span>
    `);

    const payload = {
      name: name,
      email: email,
      role: role,
      password: password,
      credential_id: credentialId || null
    };

    LG.api.auth.register(payload)
      .done(function () {
        LG.toast('Registration successful! You may now sign in.', 'success');
        setTimeout(function () {
          window.location.href = 'login.html';
        }, 1200);
      })
      .fail(function (xhr) {
        let msg = 'Registration failed. Please check your details.';
        if (xhr.responseJSON && xhr.responseJSON.detail) {
          msg = typeof xhr.responseJSON.detail === 'string'
            ? xhr.responseJSON.detail
            : JSON.stringify(xhr.responseJSON.detail);
        }
        $alert.removeClass('d-none').text(msg);
      })
      .always(function () {
        $submitBtn.prop('disabled', false).html(`
          <span>Register Account</span>
          <i class="bi bi-arrow-right"></i>
        `);
      });
  });
});
