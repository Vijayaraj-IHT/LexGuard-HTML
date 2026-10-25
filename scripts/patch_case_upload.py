with open('lexguard-html/js/pages/case-upload.js', 'r', encoding='utf-8') as f:
    content = f.read()

target = """    LG.api.upload.uploadAuto(formData)
      .done(function (res) {
        $successCaseId.text(res.id || 'N/A');
        $successFileHash.text(res.file_hash || 'SHA-256 Registered');
        $successViewBtn.attr('href', 'case-viewer.html?id=' + encodeURIComponent(res.id));
        $successModal.show();
        $autoForm[0].reset();
        $autoFileLabel.text('Choose or Drop Judgment PDF');
        selectedAutoFile = null;
        LG.toast('Document ingested and parsed by CIS engine!', 'success');
      })"""

replacement = """    LG.api.upload.uploadAuto(formData)
      .done(function (res) {
        $successCaseId.text(res.id || 'N/A');
        $successFileHash.text(res.file_hash || 'SHA-256 Registered');
        $successViewBtn.attr('href', 'case-viewer.html?id=' + encodeURIComponent(res.id));
        $autoForm[0].reset();
        $autoFileLabel.text('Choose or Drop Judgment PDF');
        selectedAutoFile = null;
        LG.toast('Document ingested and parsed by CIS engine!', 'success');

        // Populate and display Auto-Extract Review Card
        const data = res.extracted_data || res;
        const cid = res.id || res.case_id;
        const conf = Math.round((res.overall_confidence || data.overall_confidence || 0.88) * 100);

        $('#review-case-id').val(cid);
        $('#review-display-title').text(data.title || 'Extracted Case Docket');
        $('#review-confidence-badge').html(`<i class="bi bi-check-circle-fill me-1"></i>${conf}% Confidence (${conf >= 75 ? 'High' : 'Moderate'})`);
        $('#review-sha-seal').text('SHA-256: ' + (res.file_hash ? res.file_hash.substring(0, 16) + '...' : 'Sealed'));

        $('#review-caseno').val(data.case_no || '');
        if (data.court) $('#review-court').val(data.court);
        $('#review-title').val(data.title || '');
        $('#review-judge').val(data.judge || '');
        $('#review-parties').val(data.parties || '');
        $('#review-acts').val(Array.isArray(data.act_tags) ? data.act_tags.join(', ') : (data.act_tags || ''));
        $('#review-sections').val(Array.isArray(data.section_tags) ? data.section_tags.join(', ') : (data.section_tags || ''));
        $('#review-ratio').val(data.ratio_decidendi || '');
        $('#review-summary').val(data.summary || data.facts || '');

        $('#review-split-btn').attr('href', 'case-review.html?id=' + encodeURIComponent(cid));
        $('#review-dossier-btn').attr('href', 'case-viewer.html?id=' + encodeURIComponent(cid));

        $('#auto-review-card').removeClass('d-none');
        $('html, body').animate({
          scrollTop: $('#auto-review-card').offset().top - 80
        }, 400);
      })"""

if target in content:
    content = content.replace(target, replacement)
    approve_logic = """
  // Approve & Seal from Review Card
  $('#review-approve-btn').on('click', function () {
    const cid = $('#review-case-id').val();
    if (!cid) return;
    const $btn = $(this);
    $btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm me-1"></span>Sealing Case...');

    LG.api.admin.approve(cid, 'Approved directly from Ingestion Review Workstation')
      .done(function () {
        LG.toast('Case successfully approved, cryptographically sealed, and published!', 'success');
        $btn.html('<i class="bi bi-check2-circle me-1"></i>Approved & Published');
        setTimeout(function () {
          window.location.href = 'case-viewer.html?id=' + encodeURIComponent(cid);
        }, 1000);
      })
      .fail(function (xhr) {
        LG.toast('Approval error or already published.', 'warning');
        $btn.prop('disabled', false).html('<i class="bi bi-shield-check me-1"></i>Approve & Seal Case');
      });
  });
});
"""
    content = content.rstrip()
    if content.endswith('});'):
        content = content[:-3] + approve_logic
    with open('lexguard-html/js/pages/case-upload.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print('case-upload.js successfully updated!')
else:
    print('Target not matched.')
