"""
Updates search.html with nationwide courts, legal domain, and case type filters.
"""
for p in ['e:/SEM 5 PROJECT/Lexguard/lexguard-html/search.html', 'e:/SEM 5 PROJECT/LexGuard-HTML/frontend/search.html']:
    with open(p, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update total cases badge
    content = content.replace('208 Indexed Judgments', '130 Verified Court Judgments')

    # 2. Update Court filter options
    old_courts = """              <select class="form-select form-select-sm" id="filter-court">
                <option value="">All Jurisdictions</option>
                <option value="Madras High Court (Principal Seat)">Madras HC (Principal Seat)</option>
                <option value="Madras High Court (Madurai Bench)">Madras HC (Madurai Bench)</option>
                <option value="Supreme Court of India">Supreme Court of India</option>
              </select>"""

    new_courts = """              <select class="form-select form-select-sm" id="filter-court">
                <option value="">All Jurisdictions (All India)</option>
                <option value="Madras High Court (Principal Seat, Chennai)">Madras HC (Principal Seat)</option>
                <option value="Madras High Court (Madurai Bench)">Madras HC (Madurai Bench)</option>
                <option value="High Court of Gujarat at Ahmedabad">Gujarat High Court</option>
                <option value="High Court of Judicature at Bombay">Bombay High Court (All Benches)</option>
                <option value="Supreme Court of India">Supreme Court of India</option>
                <option value="High Court at Calcutta">Calcutta High Court</option>
                <option value="High Court of Jammu & Kashmir">Jammu & Kashmir High Court</option>
              </select>"""

    if old_courts in content:
        content = content.replace(old_courts, new_courts)

    # 3. Add Legal Domain & Case Type dropdowns before apply button
    old_btn = '<button type="button" class="btn btn-sm btn-gold w-100" id="apply-filters-btn">'
    new_filters = """            <!-- Legal Domain / Subject Area -->
            <div class="mb-3">
              <label for="filter-domain" class="form-label text-secondary small fw-semibold">Legal Domain</label>
              <select class="form-select form-select-sm" id="filter-domain">
                <option value="">All Subject Matters</option>
                <option value="Criminal Law">Criminal Law</option>
                <option value="Constitutional Law">Constitutional Law</option>
                <option value="Civil Law">Civil Law</option>
                <option value="Commercial & Arbitration">Commercial & Arbitration</option>
                <option value="Banking & Negotiable Instruments">Banking & NI Act</option>
                <option value="Service & Employment Law">Service Law</option>
                <option value="Family Law">Family Law</option>
              </select>
            </div>

            <!-- Case Nature / Type -->
            <div class="mb-3">
              <label for="filter-casetype" class="form-label text-secondary small fw-semibold">Case Type</label>
              <select class="form-select form-select-sm" id="filter-casetype">
                <option value="">All Case Types</option>
                <option value="Criminal Original Petition">Criminal Original Petition (482/Bail)</option>
                <option value="Writ Petition">Writ Petition (Article 226)</option>
                <option value="Criminal Appeal">Criminal Appeal</option>
                <option value="Civil Appeal">Civil Appeal</option>
                <option value="Civil Revision Petition">Civil Revision Petition</option>
                <option value="Special Leave Petition">Special Leave Petition</option>
              </select>
            </div>

            <button type="button" class="btn btn-sm btn-gold w-100" id="apply-filters-btn">"""

    if old_btn in content and 'filter-domain' not in content:
        content = content.replace(old_btn, new_filters)

    with open(p, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Updated {p} successfully!')
