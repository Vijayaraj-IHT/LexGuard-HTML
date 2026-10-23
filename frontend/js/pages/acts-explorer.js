/**
 * LexGuard — Statutory & Acts Explorer Controller (acts-explorer.js)
 * Semester 5 Project · LexGuard Judicial Repository & Verification Platform
 */

$(document).ready(function () {
  'use strict';

  const ACTS_CATALOG = [
    {
      id: 'crpc',
      name: 'Code of Criminal Procedure, 1973 (Cr.P.C.)',
      shortName: 'Cr.P.C.',
      newEquiv: 'Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)',
      category: 'Criminal Procedure',
      badgeClass: 'badge-court-madras',
      description: 'Governs criminal investigations, trials, bail powers, and High Court inherent quashing jurisdiction.',
      sections: [
        {
          section: 'Section 482 CrPC',
          title: 'Inherent powers of High Court (Quashing FIR)',
          desc: 'Quashing of FIR, Charge Sheet, and criminal complaint proceedings to prevent abuse of process of the Court.',
          query: 'Section 482 CrPC quashing FIR abuse of process'
        },
        {
          section: 'Section 438 CrPC',
          title: 'Direction for grant of bail (Anticipatory Bail)',
          desc: 'Anticipatory bail applications before the High Court or Sessions Court for apprehended arrest.',
          query: 'Section 438 CrPC anticipatory bail'
        },
        {
          section: 'Section 439 CrPC',
          title: 'Special powers of High Court regarding bail (Regular Bail)',
          desc: 'Grant or cancellation of regular bail after judicial custody or arrest.',
          query: 'Section 439 CrPC regular bail'
        },
        {
          section: 'Section 397 CrPC',
          title: 'Calling for records to exercise powers of revision',
          desc: 'Criminal revision against interlocutory orders or jurisdictional errors by Magistrate.',
          query: 'Section 397 CrPC revision'
        }
      ]
    },
    {
      id: 'constitution',
      name: 'Constitution of India, 1950',
      shortName: 'Constitution',
      category: 'Constitutional Law',
      badgeClass: 'badge-court-supreme',
      description: 'Supreme constitutional charter guaranteeing fundamental rights, writ jurisdiction, and judicial review.',
      sections: [
        {
          section: 'Article 21',
          title: 'Protection of life and personal liberty',
          desc: 'Right to speedy trial, personal liberty against arbitrary incarceration, and fair procedure.',
          query: 'Article 21 life and personal liberty speedy trial'
        },
        {
          section: 'Article 226',
          title: 'Power of High Courts to issue certain writs',
          desc: 'Extraordinary original writ jurisdiction for enforcement of fundamental and statutory rights (Mandamus, Certiorari, Habeas Corpus).',
          query: 'Article 226 writ jurisdiction High Court'
        },
        {
          section: 'Article 32',
          title: 'Remedies for enforcement of fundamental rights',
          desc: 'Constitutional remedies directly before the Supreme Court of India.',
          query: 'Article 32 Supreme Court fundamental rights'
        },
        {
          section: 'Article 14',
          title: 'Equality before law & Arbitrariness Doctrine',
          desc: 'Non-arbitrariness, natural justice, and equal protection of the laws in state action.',
          query: 'Article 14 equality non-arbitrariness'
        }
      ]
    },
    {
      id: 'ipc',
      name: 'Indian Penal Code, 1860 (IPC)',
      shortName: 'IPC',
      newEquiv: 'Bharatiya Nyaya Sanhita, 2023 (BNS)',
      category: 'Substantive Criminal Law',
      badgeClass: 'badge-court-madurai',
      description: 'Defines offences and prescribing punishments across the Republic of India.',
      sections: [
        {
          section: 'Section 420 IPC',
          title: 'Cheating and dishonestly inducing delivery of property',
          desc: 'Distinction between breach of contract and criminal cheating at inception of agreement.',
          query: 'Section 420 IPC cheating dishonest intention'
        },
        {
          section: 'Section 406 IPC',
          title: 'Punishment for criminal breach of trust',
          desc: 'Entrustment of property and dishonest misappropriation under fiduciary duty.',
          query: 'Section 406 IPC criminal breach of trust'
        },
        {
          section: 'Section 302 IPC',
          title: 'Punishment for murder',
          desc: 'Circumstantial evidence, chain of custody, and last seen theory jurisprudence.',
          query: 'Section 302 IPC murder circumstantial evidence'
        },
        {
          section: 'Section 307 IPC',
          title: 'Attempt to murder',
          desc: 'Intention and knowledge necessary to constitute attempt to commit murder.',
          query: 'Section 307 IPC attempt to murder'
        }
      ]
    },
    {
      id: 'ni-act',
      name: 'Negotiable Instruments Act, 1881',
      shortName: 'NI Act',
      category: 'Commercial & Banking Law',
      badgeClass: 'badge badge-gold',
      description: 'Criminal enforcement of cheques and negotiable banking instruments.',
      sections: [
        {
          section: 'Section 138 NI Act',
          title: 'Dishonour of cheque for insufficiency of funds',
          desc: 'Statutory demand notice, 15-day period, and quasi-criminal cheque bounce proceedings.',
          query: 'Section 138 Negotiable Instruments Act cheque bounce'
        },
        {
          section: 'Section 139 NI Act',
          title: 'Presumption in favour of holder in due course',
          desc: 'Rebuttable statutory presumption of legally enforceable debt or liability.',
          query: 'Section 139 NI Act presumption enforceable debt'
        },
        {
          section: 'Section 141 NI Act',
          title: 'Offences by companies and vicarious liability',
          desc: 'Specific averments required against directors in charge of day-to-day business.',
          query: 'Section 141 NI Act vicarious liability director'
        }
      ]
    },
    {
      id: 'arbitration',
      name: 'Arbitration and Conciliation Act, 1996',
      shortName: 'Arbitration Act',
      category: 'Dispute Resolution & Commercial',
      badgeClass: 'badge bg-primary',
      description: 'Domestic and international commercial arbitrations and enforcement of awards.',
      sections: [
        {
          section: 'Section 34',
          title: 'Application for setting aside arbitral award',
          desc: 'Challenge to domestic awards on grounds of patent illegality and public policy.',
          query: 'Section 34 Arbitration and Conciliation Act patent illegality'
        },
        {
          section: 'Section 9',
          title: 'Interim measures by Court',
          desc: 'Preservation of assets, injunctions, and interim protection before or during arbitral proceedings.',
          query: 'Section 9 Arbitration Act interim measures'
        },
        {
          section: 'Section 11',
          title: 'Appointment of arbitrators by Chief Justice / Designated Court',
          desc: 'Prima facie examination of existence of valid arbitration agreement.',
          query: 'Section 11 Arbitration Act appointment of arbitrator'
        }
      ]
    }
  ];

  const $container = $('#acts-catalog-container');
  const $searchInput = $('#acts-search-input');

  /**
   * Render Acts Catalog.
   */
  function renderCatalog(filterQuery) {
    $container.empty();
    const q = (filterQuery || '').toLowerCase().trim();

    ACTS_CATALOG.forEach(function (act) {
      // Filter sections based on query
      const matchedSections = act.sections.filter(function (sec) {
        if (!q) return true;
        return (
          act.name.toLowerCase().includes(q) ||
          act.shortName.toLowerCase().includes(q) ||
          (act.newEquiv && act.newEquiv.toLowerCase().includes(q)) ||
          sec.section.toLowerCase().includes(q) ||
          sec.title.toLowerCase().includes(q) ||
          sec.desc.toLowerCase().includes(q)
        );
      });

      if (matchedSections.length === 0) return;

      const actHtml = `
        <div class="lg-statute-card shadow">
          <div class="d-flex align-items-start justify-content-between flex-wrap gap-2 mb-2 pb-2 border-bottom border-secondary border-opacity-25">
            <div>
              <div class="d-flex align-items-center gap-2 mb-1">
                <span class="badge ${act.badgeClass}">${act.category}</span>
                ${act.newEquiv ? `<span class="badge badge-court-red"><i class="bi bi-arrow-repeat me-1"></i>${act.newEquiv}</span>` : ''}
              </div>
              <h2 class="h5 fw-bold text-dark mb-1">${LG.utils.escapeHtml(act.name)}</h2>
              <p class="text-secondary small mb-0">${LG.utils.escapeHtml(act.description)}</p>
            </div>
            <div>
              <a href="search.html?q=${encodeURIComponent(act.shortName)}" class="btn btn-xs btn-judicial-outline">
                <i class="bi bi-search me-1"></i>Search All in ${LG.utils.escapeHtml(act.shortName)}
              </a>
            </div>
          </div>

          <div class="row g-3 mt-1">
            ${matchedSections.map(function (s) {
              return `
                <div class="col-md-6">
                  <a href="search.html?q=${encodeURIComponent(s.query)}" class="lg-statute-section-item">
                    <div class="d-flex align-items-center justify-content-between mb-1">
                      <span class="fw-bold text-danger font-mono">${LG.utils.escapeHtml(s.section)}</span>
                      <span class="badge bg-light text-danger border border-danger border-opacity-25 small">
                        Explore Precedents <i class="bi bi-arrow-right ms-1"></i>
                      </span>
                    </div>
                    <div class="fw-bold text-dark small mb-1">${LG.utils.escapeHtml(s.title)}</div>
                    <div class="text-secondary small lh-sm" style="font-size: 0.8rem;">${LG.utils.escapeHtml(s.desc)}</div>
                  </a>
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;

      $container.append(actHtml);
    });

    if ($container.children().length === 0) {
      $container.html(`
        <div class="card card-judicial text-center p-5">
          <i class="bi bi-search text-secondary display-6 mb-3"></i>
          <h3 class="h5 text-light">No matching statutory sections found</h3>
          <p class="text-secondary small mb-0">Try searching for generic terms like "CrPC", "bail", "quashing", or section numbers like "482".</p>
        </div>
      `);
    }
  }

  // Real-time Search Filter Handler
  $searchInput.on('input propertychange', function () {
    renderCatalog($(this).val());
  });

  // Initial Render
  renderCatalog();
});
