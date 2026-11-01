/* ==============================================================================
   LexGuard — Case Card component (js/components/case-card.js)

   One renderer for a search result, reusable by search, bookmarks and the
   comparison tray. All interpolation is escaped; highlights arrive from the API
   as [start, end] ranges over plain text, so judgment text can never inject HTML.
   ============================================================================== */
(function (window) {
  'use strict';

  var LG = (window.LG = window.LG || {});

  function esc(value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /** Merge overlapping [start,end] ranges and clamp them to the text length. */
  function normalizeSpans(spans, length) {
    if (!Array.isArray(spans) || !spans.length) return [];
    var clean = spans
      .filter(function (s) {
        return Array.isArray(s) && s.length === 2 && Number.isFinite(s[0]) && Number.isFinite(s[1]);
      })
      .map(function (s) {
        return [Math.max(0, Math.min(s[0], length)), Math.max(0, Math.min(s[1], length))];
      })
      .filter(function (s) {
        return s[1] > s[0];
      })
      .sort(function (a, b) {
        return a[0] - b[0];
      });

    var out = [];
    clean.forEach(function (s) {
      var last = out[out.length - 1];
      if (last && s[0] <= last[1]) last[1] = Math.max(last[1], s[1]);
      else out.push(s.slice());
    });
    return out;
  }

  /** Escape the text, then wrap the highlight ranges in <mark>. */
  function renderHighlighted(text, spans) {
    var raw = String(text || '');
    var ranges = normalizeSpans(spans, raw.length);
    if (!ranges.length) return esc(raw);
    var html = '';
    var cursor = 0;
    ranges.forEach(function (r) {
      html += esc(raw.slice(cursor, r[0]));
      html += '<mark>' + esc(raw.slice(r[0], r[1])) + '</mark>';
      cursor = r[1];
    });
    return html + esc(raw.slice(cursor));
  }

  var MATCH_LABELS = {
    keyword: 'Keyword match',
    statute: 'Statute match',
    related: 'Related judgment',
    hybrid: 'Hybrid match',
  };

  function isPlaceholderBench(judge) {
    if (!judge) return true;
    return /hon'?ble\s+(bench|court)/i.test(judge.trim());
  }

  function looksInternal(citation) {
    return !!citation && /lexguard/i.test(citation);
  }

  function copyCitation(item) {
    var year = (item.decision_date || '').slice(0, 4) || item.year || '';
    var parts = [];
    if (item.case_no) parts.push(item.case_no + (year ? ', (' + year + ')' : ''));
    if (item.court) parts.push(item.court);
    return parts.join(' ') || item.title || '';
  }

  function chips(item) {
    var out = [];
    if (item.court) {
      out.push('<span class="lg-chip lg-chip--court">' + esc(item.court) + '</span>');
    }
    if (item.case_type) out.push('<span class="lg-chip">' + esc(item.case_type) + '</span>');
    var disposition = item.disposition || item.outcome;
    if (disposition) out.push('<span class="lg-chip lg-chip--outcome">' + esc(disposition) + '</span>');
    if (item.source_verified) {
      out.push('<span class="lg-chip lg-chip--verified"><i class="bi bi-patch-check-fill" aria-hidden="true"></i> Verified source</span>');
    } else {
      out.push('<span class="lg-chip lg-chip--unverified" title="No official source checked against this record">Unverified source</span>');
    }
    if (item.cited_by_count > 0) {
      out.push('<span class="lg-chip"><i class="bi bi-diagram-3" aria-hidden="true"></i> Cited in ' + esc(item.cited_by_count) + '</span>');
    }
    return out.join('');
  }

  function snippetBlock(item) {
    var list = Array.isArray(item.snippets) ? item.snippets : [];
    if (list.length) {
      return (
        '<div class="lg-case-card__snippet">' +
        list
          .map(function (s) {
            var page = s.page ? '<span class="lg-chip lg-chip--page">p. ' + esc(s.page) + '</span>' : '';
            return '<p>' + renderHighlighted(s.text, s.highlights) + page + '</p>';
          })
          .join('') +
        '</div>'
      );
    }
    if (item.summary) {
      var text = String(item.summary);
      var trimmed = text.length > 240 ? text.slice(0, 240).trim() + '…' : text;
      return '<div class="lg-case-card__snippet lg-case-card__snippet--summary">' + esc(trimmed) + '</div>';
    }
    return '';
  }

  function tagBlock(item) {
    var acts = (item.act_tags || []).slice(0, 3);
    var sections = (item.section_tags || []).slice(0, 3);
    var html = acts
      .map(function (a) {
        return '<span class="lg-chip lg-chip--act">' + esc(a) + '</span>';
      })
      .join('');
    html += sections
      .map(function (s) {
        return '<span class="lg-chip lg-chip--section">' + esc(s) + '</span>';
      })
      .join('');
    return html ? '<div class="lg-case-card__tags">' + html + '</div>' : '';
  }

  function matchChip(item) {
    if (item.match_type === 'browse' || item.relevance_score === null || item.relevance_score === undefined) {
      return '';
    }
    var label = MATCH_LABELS[item.match_type] || MATCH_LABELS.hybrid;
    var score = typeof item.relevance_score === 'number' ? item.relevance_score.toFixed(2) : '';
    return (
      '<span class="lg-chip lg-chip--match" title="Relative rank ' +
      esc(score) +
      ' within this result set — not a confidence score">' +
      esc(label) +
      '</span>'
    );
  }

  function citationRow(item) {
    var bits = [];
    if (item.citation_display) {
      bits.push('<span class="lg-case-card__cite-main">' + esc(item.citation_display) + '</span>');
    }
    if (item.official_citation && !looksInternal(item.official_citation)) {
      bits.push('<span class="lg-case-card__cite-official">' + esc(item.official_citation) + '</span>');
    } else if (item.repository_id) {
      bits.push('<span class="lg-case-card__cite-repo" title="Internal repository identifier, not an official citation">Repository ID ' + esc(item.repository_id) + '</span>');
    }
    if (!isPlaceholderBench(item.judge)) {
      bits.push('<span class="lg-case-card__bench"><i class="bi bi-person-fill" aria-hidden="true"></i> ' + esc(item.judge) + '</span>');
    } else {
      bits.push('<span class="lg-case-card__bench lg-case-card__bench--missing">Bench not recorded</span>');
    }
    return '<div class="lg-case-card__meta">' + bits.join('<span class="lg-dot" aria-hidden="true">·</span>') + '</div>';
  }

  function render(item) {
    if (!item) return '';
    var id = encodeURIComponent(item.id || '');
    var title = item.title || item.case_no || 'Untitled judgment';

    return (
      '<article class="lg-case-card" data-case-id="' + esc(item.id || '') + '">' +
      '<header class="lg-case-card__head">' +
      '<h3 class="lg-case-card__title"><a href="case-viewer.html?id=' + id + '">' + esc(title) + '</a></h3>' +
      '<div class="lg-case-card__badges">' + matchChip(item) + '</div>' +
      '</header>' +
      citationRow(item) +
      '<div class="lg-case-card__chips">' + chips(item) + '</div>' +
      snippetBlock(item) +
      tagBlock(item) +
      '<footer class="lg-case-card__actions">' +
      '<a class="btn btn-sm btn-gold" href="case-viewer.html?id=' + id + '" aria-label="Read judgment: ' + esc(title) + '">' +
      '<i class="bi bi-book-half" aria-hidden="true"></i> Read judgment</a>' +
      '<a class="btn btn-sm btn-judicial-outline" href="case-compare.html?case1=' + id + '">' +
      '<i class="bi bi-columns-gap" aria-hidden="true"></i> Compare</a>' +
      '<div class="lg-case-card__actions-end">' +
      '<button type="button" class="btn btn-sm btn-judicial-outline js-copy-citation" data-citation="' + esc(copyCitation(item)) + '" aria-label="Copy citation">' +
      '<i class="bi bi-quote" aria-hidden="true"></i><span class="d-none d-md-inline"> Copy citation</span></button>' +
      '<button type="button" class="btn btn-sm btn-judicial-outline js-bookmark" data-id="' + esc(item.id || '') + '" aria-pressed="false" aria-label="Save to bookmarks">' +
      '<i class="bi bi-bookmark" aria-hidden="true"></i></button>' +
      '</div>' +
      '</footer>' +
      '</article>'
    );
  }

  LG.components = LG.components || {};
  LG.components.caseCard = {
    render: render,
    escapeHtml: esc,
    renderHighlighted: renderHighlighted,
  };
})(window);
