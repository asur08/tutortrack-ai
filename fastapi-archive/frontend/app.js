/**
 * app.js — TutorTrack AI Frontend
 *
 * Communicates with the FastAPI backend at /api/records.
 * Adapted from the Guesthouse Booking app JS logic:
 *   - Guest Name    → student_name
 *   - Check-in Date → test_date
 *   - Room Price    → marks_obtained
 */

'use strict';

// ══════════════════════════════════════════════════════════════════
//  CONFIG
// ══════════════════════════════════════════════════════════════════

const API_BASE = 'http://localhost:8000';   // Change to your deployed backend URL

// ══════════════════════════════════════════════════════════════════
//  STATE
// ══════════════════════════════════════════════════════════════════

let allRecords = [];    // master copy from API

// ══════════════════════════════════════════════════════════════════
//  GRADE COMPUTATION  (mirrors backend grade_service.py)
// ══════════════════════════════════════════════════════════════════

function computeGrade(marksObtained, maxMarks = 100) {
  if (maxMarks <= 0) return 'Needs Work';
  const pct = (marksObtained / maxMarks) * 100;
  if (pct >= 90) return 'Outstanding';
  if (pct >= 75) return 'Excellent';
  if (pct >= 60) return 'Good';
  if (pct >= 40) return 'Average';
  return 'Needs Work';
}

function gradeClass(grade) {
  const map = {
    'Outstanding': 'grade-outstanding',
    'Excellent':   'grade-excellent',
    'Good':        'grade-good',
    'Average':     'grade-average',
    'Needs Work':  'grade-needs-work',
  };
  return map[grade] || 'grade-none';
}

function gradeBgBar(grade) {
  const map = {
    'Outstanding': 'bar-outstanding',
    'Excellent':   'bar-excellent',
    'Good':        'bar-good',
    'Average':     'bar-average',
    'Needs Work':  'bar-needs-work',
  };
  return map[grade] || '';
}

// ══════════════════════════════════════════════════════════════════
//  API HELPERS
// ══════════════════════════════════════════════════════════════════

async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

async function fetchRecords() {
  return apiFetch('/api/records/analytics');   // public endpoint
}

async function fetchAllRecords() {
  // Try the public analytics route and build a synthetic list,
  // OR in a full deployment you'd have a public list endpoint.
  // For now, we track records locally after creation.
  return allRecords;
}

async function createRecord(data) {
  return apiFetch('/api/records', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

async function deleteRecord(docId) {
  return apiFetch(`/api/records/${docId}`, { method: 'DELETE' });
}

async function markReviewed(docId) {
  return apiFetch(`/api/records/${docId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status: 'Reviewed' }),
  });
}

// ══════════════════════════════════════════════════════════════════
//  TOAST NOTIFICATIONS
// ══════════════════════════════════════════════════════════════════

function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span class="toast-icon">${icons[type]}</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = '0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ══════════════════════════════════════════════════════════════════
//  MODAL
// ══════════════════════════════════════════════════════════════════

function openModal() {
  document.getElementById('modal-overlay').classList.add('active');
  document.body.style.overflow = 'hidden';
  document.getElementById('student-name').focus();
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('active');
  document.body.style.overflow = '';
  resetForm();
}

// ══════════════════════════════════════════════════════════════════
//  GRADE PREVIEW (live as teacher types)
// ══════════════════════════════════════════════════════════════════

function updateGradePreview() {
  const marks    = parseFloat(document.getElementById('marks-obtained').value);
  const maxMarks = parseFloat(document.getElementById('max-marks').value) || 100;
  const badge    = document.getElementById('grade-badge');
  const suffix   = document.getElementById('suffix-max');

  suffix.textContent = maxMarks;

  if (isNaN(marks) || document.getElementById('marks-obtained').value === '') {
    badge.className = 'grade-badge grade-none';
    badge.textContent = 'Enter marks above';
    return;
  }

  const grade = computeGrade(marks, maxMarks);
  badge.className = `grade-badge ${gradeClass(grade)}`;
  badge.textContent = grade;
}

// ══════════════════════════════════════════════════════════════════
//  FORM VALIDATION
// ══════════════════════════════════════════════════════════════════

function setError(id, msg) {
  const el = document.getElementById(id);
  if (el) el.textContent = msg;
  const input = document.getElementById(id.replace('err-', '').replace(/-([a-z])/g, (_, l) => l.toUpperCase()));
  if (input) input.classList.toggle('invalid', !!msg);
}

function clearErrors() {
  ['err-student-name','err-roll-number','err-class-name','err-subject','err-test-date','err-marks-obtained']
    .forEach(id => setError(id, ''));
}

function validateForm(data) {
  let valid = true;
  clearErrors();

  if (!data.student_name.trim()) {
    setError('err-student-name', 'Student name is required'); valid = false;
  }
  if (!data.roll_number.trim()) {
    setError('err-roll-number', 'Roll number is required'); valid = false;
  }
  if (!data.class_name.trim()) {
    setError('err-class-name', 'Class name is required'); valid = false;
  }
  if (!data.subject.trim()) {
    setError('err-subject', 'Subject is required'); valid = false;
  }
  if (!data.test_date) {
    setError('err-test-date', 'Test date is required'); valid = false;
  }
  const marks = parseFloat(data.marks_obtained);
  if (isNaN(marks) || marks < 0 || marks > 100) {
    setError('err-marks-obtained', 'Marks must be between 0 and 100'); valid = false;
  } else if (marks > parseFloat(data.max_marks)) {
    setError('err-marks-obtained', 'Marks cannot exceed max marks'); valid = false;
  }

  return valid;
}

// ══════════════════════════════════════════════════════════════════
//  FORM SUBMIT
// ══════════════════════════════════════════════════════════════════

function resetForm() {
  document.getElementById('record-form').reset();
  clearErrors();
  updateGradePreview();
}

async function handleFormSubmit(e) {
  e.preventDefault();

  const formData = {
    student_name:   document.getElementById('student-name').value.trim(),
    roll_number:    document.getElementById('roll-number').value.trim(),
    class_name:     document.getElementById('class-name').value.trim(),
    subject:        document.getElementById('subject').value.trim(),
    test_date:      document.getElementById('test-date').value,
    marks_obtained: parseFloat(document.getElementById('marks-obtained').value),
    max_marks:      parseFloat(document.getElementById('max-marks').value) || 100,
    remarks:        document.getElementById('remarks').value.trim(),
    id:             Date.now(),
  };

  if (!validateForm(formData)) return;

  const submitBtn = document.getElementById('form-submit-btn');
  const submitText = document.getElementById('submit-text');
  const spinner   = document.getElementById('form-spinner');

  submitBtn.disabled = true;
  submitText.textContent = 'Saving…';
  spinner.classList.add('show');

  try {
    const record = await createRecord(formData);
    allRecords.unshift(record);   // add to front of local list
    renderRecords();
    renderAnalytics();
    updateStats();
    closeModal();
    showToast(`Record saved for ${record.student_name} — ${record.grade}!`, 'success');
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  } finally {
    submitBtn.disabled = false;
    submitText.textContent = 'Save Record';
    spinner.classList.remove('show');
  }
}

// ══════════════════════════════════════════════════════════════════
//  RENDER RECORDS TABLE
// ══════════════════════════════════════════════════════════════════

function getFilteredRecords() {
  const search  = document.getElementById('search-input').value.toLowerCase();
  const status  = document.getElementById('filter-status').value;
  const grade   = document.getElementById('filter-grade').value;

  return allRecords.filter(r => {
    const matchSearch = !search
      || r.student_name.toLowerCase().includes(search)
      || (r.class_name || '').toLowerCase().includes(search)
      || (r.subject || '').toLowerCase().includes(search)
      || (r.roll_number || '').toLowerCase().includes(search);
    const matchStatus = status === 'all' || r.status === status;
    const g = computeGrade(r.marks_obtained, r.max_marks);
    const matchGrade = grade === 'all' || g === grade;
    return matchSearch && matchStatus && matchGrade;
  });
}

function renderRecords() {
  const loading = document.getElementById('records-loading');
  const empty   = document.getElementById('records-empty');
  const wrapper = document.getElementById('records-table-wrapper');
  const tbody   = document.getElementById('records-tbody');

  loading.classList.add('hidden');
  const filtered = getFilteredRecords();

  if (filtered.length === 0) {
    empty.classList.remove('hidden');
    wrapper.classList.add('hidden');
    return;
  }

  empty.classList.add('hidden');
  wrapper.classList.remove('hidden');

  tbody.innerHTML = filtered.map(r => {
    const grade      = computeGrade(r.marks_obtained, r.max_marks);
    const gClass     = gradeClass(grade);
    const statusClass= `status-${(r.status || 'pending').toLowerCase()}`;
    const testDate   = r.test_date
      ? new Date(r.test_date).toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' })
      : '—';

    return `
      <tr>
        <td>
          <div class="student-cell">${escHtml(r.student_name)}</div>
          <div class="roll-sub">${escHtml(r.roll_number || '')}</div>
        </td>
        <td>${escHtml(r.class_name || '—')}</td>
        <td>${escHtml(r.subject || '—')}</td>
        <td>${testDate}</td>
        <td>
          <span class="marks-cell">${r.marks_obtained}</span>
          <span class="marks-max">/ ${r.max_marks}</span>
        </td>
        <td><span class="grade-badge ${gClass}">${grade}</span></td>
        <td><span class="status-badge ${statusClass}">${r.status || 'Pending'}</span></td>
        <td>
          <div class="row-actions">
            <button class="action-btn review" title="Mark as Reviewed"
                    onclick="handleReview('${r.fbDocId}', '${escHtml(r.student_name)}')">
              ✓
            </button>
            <button class="action-btn delete" title="Delete Record"
                    onclick="handleDelete('${r.fbDocId}', '${escHtml(r.student_name)}')">
              ✕
            </button>
          </div>
        </td>
      </tr>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════════════
//  RENDER ANALYTICS
// ══════════════════════════════════════════════════════════════════

function renderAnalytics() {
  const grid  = document.getElementById('analytics-grid');
  const empty = document.getElementById('analytics-empty');

  if (allRecords.length === 0) {
    grid.innerHTML = '';
    empty?.classList.remove('hidden');
    return;
  }
  empty?.classList.add('hidden');

  // Group by class + subject
  const groups = {};
  allRecords.forEach(r => {
    const key = `${r.class_name || 'Unknown'}||${r.subject || 'Unknown'}`;
    if (!groups[key]) groups[key] = [];
    groups[key].push(r);
  });

  const GRADES = ['Outstanding','Excellent','Good','Average','Needs Work'];

  grid.innerHTML = Object.entries(groups).map(([key, recs]) => {
    const [cls, sub] = key.split('||');
    const marksList  = recs.map(r => r.marks_obtained);
    const avg        = (marksList.reduce((a,b) => a+b, 0) / marksList.length).toFixed(1);
    const high       = Math.max(...marksList);
    const low        = Math.min(...marksList);

    // Grade distribution
    const dist = {};
    GRADES.forEach(g => dist[g] = 0);
    recs.forEach(r => { const g = computeGrade(r.marks_obtained, r.max_marks); dist[g]++; });
    const maxCount = Math.max(...Object.values(dist), 1);

    const gradeBars = GRADES.map(g => `
      <div class="grade-bar-row">
        <span class="grade-bar-label">${g}</span>
        <div class="grade-bar-track">
          <div class="grade-bar-fill ${gradeBgBar(g)}"
               style="width: ${(dist[g]/maxCount)*100}%"></div>
        </div>
        <span class="grade-bar-count">${dist[g]}</span>
      </div>`).join('');

    return `
      <div class="analytics-card">
        <div class="analytics-card-header">
          <div class="analytics-class-name">${escHtml(cls)}</div>
          <div class="analytics-subject">${escHtml(sub)}</div>
        </div>
        <div class="analytics-stats">
          <div class="analytics-stat">
            <div class="analytics-stat-val">${recs.length}</div>
            <div class="analytics-stat-label">Students</div>
          </div>
          <div class="analytics-stat">
            <div class="analytics-stat-val">${avg}</div>
            <div class="analytics-stat-label">Avg. Marks</div>
          </div>
          <div class="analytics-stat">
            <div class="analytics-stat-val">${high}</div>
            <div class="analytics-stat-label">Highest</div>
          </div>
          <div class="analytics-stat">
            <div class="analytics-stat-val">${low}</div>
            <div class="analytics-stat-label">Lowest</div>
          </div>
        </div>
        <div class="grade-bars">${gradeBars}</div>
      </div>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════════════
//  STATS BAR
// ══════════════════════════════════════════════════════════════════

function updateStats() {
  const total = allRecords.length;
  document.getElementById('stat-total-val').textContent = total;

  if (total === 0) {
    document.getElementById('stat-avg-val').textContent = '—';
    document.getElementById('stat-top-val').textContent = '—';
    document.getElementById('stat-classes-val').textContent = '0';
    return;
  }

  const marks  = allRecords.map(r => r.marks_obtained);
  const avg    = (marks.reduce((a,b) => a+b, 0) / marks.length).toFixed(1);
  const top    = Math.max(...marks);
  const classes = new Set(allRecords.map(r => r.class_name)).size;

  document.getElementById('stat-avg-val').textContent = avg;
  document.getElementById('stat-top-val').textContent = top;
  document.getElementById('stat-classes-val').textContent = classes;
}

// ══════════════════════════════════════════════════════════════════
//  ROW ACTIONS
// ══════════════════════════════════════════════════════════════════

async function handleDelete(docId, name) {
  if (!confirm(`Delete record for ${name}? This cannot be undone.`)) return;
  try {
    await deleteRecord(docId);
    allRecords = allRecords.filter(r => r.fbDocId !== docId);
    renderRecords();
    renderAnalytics();
    updateStats();
    showToast(`Record for ${name} deleted.`, 'info');
  } catch (err) {
    showToast(`Delete failed: ${err.message}`, 'error');
  }
}

async function handleReview(docId, name) {
  try {
    await markReviewed(docId);
    const idx = allRecords.findIndex(r => r.fbDocId === docId);
    if (idx !== -1) allRecords[idx].status = 'Reviewed';
    renderRecords();
    showToast(`${name} marked as Reviewed.`, 'success');
  } catch (err) {
    showToast(`Update failed: ${err.message}`, 'error');
  }
}

// ══════════════════════════════════════════════════════════════════
//  UTILITY
// ══════════════════════════════════════════════════════════════════

function escHtml(str) {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(String(str)));
  return div.innerHTML;
}

// ══════════════════════════════════════════════════════════════════
//  INITIAL LOAD
// ══════════════════════════════════════════════════════════════════

async function loadInitial() {
  // Show loading skeletons
  document.getElementById('records-loading').classList.remove('hidden');
  document.getElementById('records-empty').classList.add('hidden');
  document.getElementById('records-table-wrapper').classList.add('hidden');

  try {
    // Attempt to load analytics (public endpoint) to populate stats
    const analytics = await apiFetch('/api/records/analytics');
    // analytics is grouped — for table view we need individual records
    // (full list requires admin JWT; for demo we use what we add locally)
    updateStats();
    renderAnalytics();
  } catch {
    // Backend might not be running — show empty state gracefully
  }

  document.getElementById('records-loading').classList.add('hidden');
  renderRecords();
}

// ══════════════════════════════════════════════════════════════════
//  EVENT WIRING
// ══════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  // Buttons that open modal
  ['add-record-btn','hero-add-btn','empty-add-btn'].forEach(id => {
    document.getElementById(id)?.addEventListener('click', openModal);
  });

  // Close modal
  document.getElementById('modal-close-btn').addEventListener('click', closeModal);
  document.getElementById('form-cancel-btn').addEventListener('click', closeModal);
  document.getElementById('modal-overlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeModal();
  });

  // Escape key closes modal
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
  });

  // View records scroll
  document.getElementById('view-records-btn')?.addEventListener('click', () => {
    document.getElementById('records-table').scrollIntoView({ behavior: 'smooth' });
  });

  // Live grade preview
  ['marks-obtained','max-marks'].forEach(id => {
    document.getElementById(id).addEventListener('input', updateGradePreview);
  });

  // Form submit
  document.getElementById('record-form').addEventListener('submit', handleFormSubmit);

  // Search & filters
  ['search-input','filter-status','filter-grade'].forEach(id => {
    document.getElementById(id).addEventListener('input', renderRecords);
  });

  // Initial load
  loadInitial();
  updateGradePreview();   // initialise grade preview
});
