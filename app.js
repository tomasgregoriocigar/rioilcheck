'use strict';
/* ============================================================
   RI OIL CHECK — app logic
   Rules enforced here (same standard as the sibling RI Rate
   Check build):
   - Every price on the page comes from data/prices.json, which
     is sourced from EIA's published SHOPP series (Weekly Heating
     Oil and Propane Prices). Nothing is hard-coded except the
     documented dispersion offsets (10–50¢ buying-group range;
     30–70¢ deepest COD postings), and those are labeled on the
     page as documented ranges / computed guides — never as live
     dealer prices.
   - Any field the JSON stores as null renders as
     "not confirmed" — following the electricity site's pattern.
     If a benchmark figure cannot be verified, the site says so
     instead of estimating one.
   - Prior-week and year-ago values stored in the JSON are
     DERIVED from EIA's published change columns (current value
     minus the published change) and are labeled as derived on
     the page; EIA may revise prior-week values.
   - No dealer listings, no dealer-attributed prices, no
     referral/affiliate links, no enrollment or order buttons.
   ============================================================ */

function fmtPrice(n) {
  // 6.304 -> "$6.30" (display), full precision handled by fmtPrice3
  return '$' + Number(n).toFixed(2);
}

function fmtPrice3(n) {
  // EIA publishes to 3 decimals: 6.304 -> "$6.304"
  return '$' + Number(n).toFixed(3);
}

function fmtChange(n) {
  // signed dollars -> "+17.8¢" under a dollar, "+$2.67" at/above
  if (n === null || n === undefined) return 'not confirmed';
  const sign = n < 0 ? '−' : '+';
  const abs = Math.abs(n);
  if (abs < 1) return sign + (abs * 100).toFixed(1) + '¢';
  return sign + '$' + abs.toFixed(2);
}

function orNotConfirmed(v, format) {
  if (v === null || v === undefined) return 'not confirmed';
  return format ? format(v) : String(v);
}

function fmtDateLong(iso) {
  // "2026-10-12" -> "Monday, October 12, 2026" (UTC-safe)
  if (!iso) return 'not confirmed';
  const months = ['January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'];
  const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const d = new Date(iso + 'T00:00:00Z');
  if (isNaN(d.getTime())) return iso;
  return days[d.getUTCDay()] + ', ' + months[d.getUTCMonth()] + ' ' +
    d.getUTCDate() + ', ' + d.getUTCFullYear();
}

function fmtDateShort(iso) {
  if (!iso) return 'not confirmed';
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const d = new Date(iso + 'T00:00:00Z');
  if (isNaN(d.getTime())) return iso;
  return months[d.getUTCMonth()] + ' ' + d.getUTCDate() + ', ' + d.getUTCFullYear();
}

/* ============ browser-only rendering below ============ */

function rline(k, v, vcls) {
  return '<div class="rline"><span class="k">' + k + '</span><span class="dots"></span>' +
    '<span class="v' + (vcls ? ' ' + vcls : '') + '">' + v + '</span></div>';
}

function renderHero(oil) {
  if (!oil || oil.value === null || oil.value === undefined) {
    return '<p class="hero-price">RI AVERAGE THIS WEEK — not confirmed</p>' +
      '<p class="warning-box"><strong>BENCHMARK NOT CONFIRMED:</strong> the current RI residential ' +
      'heating oil figure could not be verified on EIA&rsquo;s published series this week. See the ' +
      'EIA series directly: <a href="https://www.eia.gov/dnav/pet/PET_PRI_WFR_DCUS_SRI_W.htm" rel="noopener">' +
      'EIA — Rhode Island Weekly Heating Oil and Propane Prices</a>. We never estimate this number.</p>';
  }
  return '<p class="hero-price">RI AVERAGE THIS WEEK — ' + fmtPrice(oil.value) + '/gal' +
    ' <span class="note">(residential heating oil)</span></p>' +
    '<div class="readout">' +
    rline('AS OF (COLLECTED)', fmtDateLong(oil.week_of), 'hot') +
    rline('PUBLISHED', fmtDateLong(oil.published)) +
    rline('FULL-PRECISION FIGURE', fmtPrice3(oil.value) + '/gal') +
    rline('SOURCE', 'EIA — Weekly Heating Oil and Propane Prices (SHOPP)') +
    '</div>';
}

function renderTrend(data) {
  const oil = data.heating_oil || {};
  const ws = data.wholesale_heating_oil || {};
  let html = '';
  html += rline('THIS WEEK (' + fmtDateShort(oil.week_of).toUpperCase() + ')',
    orNotConfirmed(oil.value, v => fmtPrice3(v) + '/gal'), 'hot');
  html += rline('LAST WEEK', orNotConfirmed(oil.prior_week_value, v => fmtPrice3(v) + '/gal (derived — see note)'));
  html += rline('CHANGE VS LAST WEEK', fmtChange(oil.change_vs_prior_week),
    (oil.change_vs_prior_week || 0) > 0 ? 'bad' : '');
  html += rline('SAME WEEK LAST YEAR', orNotConfirmed(oil.year_ago_value, v => fmtPrice3(v) + '/gal (derived — see note)'));
  html += rline('CHANGE VS LAST YEAR', fmtChange(oil.change_vs_year_ago),
    (oil.change_vs_year_ago || 0) > 0 ? 'bad' : '');
  html += rline('RI WHOLESALE (CONTEXT ONLY — NOT A RETAIL PRICE)',
    orNotConfirmed(ws.value, v => fmtPrice3(v) + '/gal'));
  html += '<p class="note">&gt; &ldquo;Derived&rdquo; values are arithmetic on EIA&rsquo;s own published ' +
    'change columns (this week&rsquo;s value minus the published change), not separate survey figures. ' +
    'EIA notes that values for the previous week may be revised to account for late submissions and ' +
    'corrections. Wholesale is shown only as a direction indicator — it is never blended into the ' +
    'retail benchmark, and no household can buy at the wholesale price.</p>';
  return html;
}

function bandRange(benchValue, band) {
  if (benchValue === null || benchValue === undefined) return 'not confirmed';
  if (band.offset_low === 0 || band.offset_low === null) {
    return fmtPrice(benchValue) + '/gal and up';
  }
  const low = benchValue + band.offset_low;
  const high = benchValue + band.offset_high;
  return fmtPrice(low) + ' – ' + fmtPrice(high) + '/gal';
}

function renderBands(data) {
  const bench = data.heating_oil ? data.heating_oil.value : null;
  const bands = (data.fair_price_bands && data.fair_price_bands.bands) || [];
  let html = '';
  bands.forEach(b => {
    const typeBadge = b.basis_type === 'documented range'
      ? '<span class="badge ok">DOCUMENTED RANGE</span>'
      : '<span class="badge warn">COMPUTED GUIDE</span>';
    html += '<article class="card">' +
      '<div class="card-top"><span class="card-name">' + b.label + '</span>' +
      '<span class="band-range">' + bandRange(bench, b) + '</span></div>' +
      '<div>' + typeBadge +
      '<span class="badge">NOT A LIVE DEALER PRICE</span></div>' +
      '<p>' + b.description + '</p>' +
      '<p class="note">Source: <a href="' + b.source_url + '" rel="noopener">' + b.source_name + '</a></p>' +
      '</article>';
  });
  if (data.fair_price_bands && data.fair_price_bands.note) {
    html += '<p class="note">' + data.fair_price_bands.note + '</p>';
  }
  return html;
}

function renderPropane(p) {
  if (!p || p.value === null || p.value === undefined) {
    return '<p class="big"><strong>RI residential propane benchmark: not confirmed — see EIA series.</strong> ' +
      'The current RI propane figure could not be verified on EIA&rsquo;s published series this week, so this ' +
      'site prints no number rather than an estimate. The series itself: ' +
      '<a href="https://www.eia.gov/dnav/pet/PET_PRI_WFR_DCUS_SRI_W.htm" rel="noopener">EIA — Rhode Island ' +
      'Weekly Heating Oil and Propane Prices</a>. Everything below about your legal rights stands regardless ' +
      'of the benchmark.</p>';
  }
  return '<p class="big">The same SHOPP survey publishes one statewide average for <strong>residential ' +
    'propane</strong>:</p>' +
    '<p class="hero-price">RI PROPANE AVERAGE — ' + fmtPrice(p.value) + '/gal</p>' +
    '<div class="readout">' +
    rline('AS OF (COLLECTED)', fmtDateLong(p.week_of), 'hot') +
    rline('PUBLISHED', fmtDateLong(p.published)) +
    rline('FULL-PRECISION FIGURE', fmtPrice3(p.value) + '/gal') +
    rline('LAST WEEK', orNotConfirmed(p.prior_week_value, v => fmtPrice3(v) + '/gal (derived)')) +
    rline('CHANGE VS LAST WEEK', fmtChange(p.change_vs_prior_week),
      (p.change_vs_prior_week || 0) > 0 ? 'bad' : '') +
    rline('SAME WEEK LAST YEAR', orNotConfirmed(p.year_ago_value, v => fmtPrice3(v) + '/gal (derived)')) +
    rline('CHANGE VS LAST YEAR', fmtChange(p.change_vs_year_ago),
      (p.change_vs_year_ago || 0) > 0 ? 'bad' : '') +
    rline('SOURCE', 'EIA — Weekly Heating Oil and Propane Prices (SHOPP)') +
    '</div>' +
    '<p class="note">Same basis and cadence as the oil benchmark: a statewide survey average, taxes ' +
    'excluded — a benchmark, not a quote. Propane pricing is even less visible than oil (tank arrangements ' +
    'and dealer-specific fees), which is exactly why the disclosure rights below matter.</p>';
}

function init() {
  fetch('data/prices.json').then(r => r.json()).then(data => {
    document.getElementById('benchmark-hero').innerHTML = renderHero(data.heating_oil);
    document.getElementById('trend').innerHTML = renderTrend(data);
    document.getElementById('fair-bands').innerHTML = renderBands(data);
    document.getElementById('propane-benchmark').innerHTML = renderPropane(data.propane);
    if (data.checked_date) {
      document.getElementById('checked-date').textContent = data.checked_date;
    }
  }).catch(err => {
    const box = '<p class="error-box">!! DATA FAILED TO LOAD. This page reads data/prices.json — ' +
      'open it through a local web server, not as a file:// page. See BUILD_NOTES.md for preview ' +
      'instructions. Until the data loads, treat every price on this page as not confirmed and check ' +
      'the EIA series directly.</p>';
    document.getElementById('benchmark-hero').innerHTML = box;
    console.error(err);
  });
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { fmtPrice, fmtPrice3, fmtChange, orNotConfirmed, fmtDateLong, fmtDateShort, bandRange };
}
