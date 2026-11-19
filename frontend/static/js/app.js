/**
 * Document Verification Pipeline — Interactive Client
 * Powered by Groq Llama, Tesseract OCR, and SQLite Audit Logs
 */

class KYCStudio {
    constructor() {
        this.selectedFiles = [];
        this.ingestionMode = 'multi';
        this.processing = false;
        this.lastResult = null;
        this.activeDocIndex = 0;
        this.currentTab = 'fields';

        this.dropZone = document.getElementById('drop-zone');
        this.fileInput = document.getElementById('file-input');
        this.btnProcess = document.getElementById('btn-process');
        this.btnCopy = document.getElementById('btn-copy-json');
        this.btnDownload = document.getElementById('btn-download-json');

        this.initEventListeners();
        this.setupDropZone();
        this.loadStats();
        this.loadRecords();
    }

    initEventListeners() {
        if (this.fileInput) {
            this.fileInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files.length > 0) {
                    this.handleFilesSelect(Array.from(e.target.files));
                }
            });
        }

        const browseBtn = document.getElementById('btn-browse');
        if (browseBtn) {
            browseBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.fileInput.click();
            });
        }

        // Global functions exposed to window
        window.processDocument = () => this.processDocument();
        window.runSample = (key) => this.runSample(key);
        window.runMultiSample = (key) => this.runMultiSample(key);
        window.setIngestionMode = (mode) => this.setIngestionMode(mode);
        window.clearFile = () => this.clearAllFiles();
        window.clearAllFiles = () => this.clearAllFiles();
        window.removeFileAt = (index) => this.removeFileAt(index);
        window.resetForm = () => this.resetForm();
        window.copyLastResult = () => this.copyLastResult();
        window.downloadLastResult = () => this.downloadLastResult();
        window.switchResultTab = (tab) => this.switchResultTab(tab);
        window.switchActiveDoc = (idx) => this.switchActiveDoc(idx);
        window.loadRecords = () => this.loadRecords();
        window.viewRecordDetails = (id) => this.viewRecordDetails(id);

        // Clipboard paste image support
        document.addEventListener('paste', (e) => this.onPaste(e));
    }

    setIngestionMode(mode) {
        this.ingestionMode = mode;
        const btnMulti = document.getElementById('mode-multi-btn');
        const btnSingle = document.getElementById('mode-single-btn');
        const titleEl = document.getElementById('drop-zone-title');
        const hintEl = document.getElementById('drop-zone-hint');

        if (mode === 'multi') {
            btnMulti?.classList.add('mode-btn--active');
            btnSingle?.classList.remove('mode-btn--active');
            if (titleEl) titleEl.textContent = 'Drag & drop your KYC documents (Select 2 or more)';
            if (hintEl) hintEl.textContent = 'Upload Primary ID (PAN) + Secondary ID (Aadhaar / Passport / DL) for cross-matching';
        } else {
            btnSingle?.classList.add('mode-btn--active');
            btnMulti?.classList.remove('mode-btn--active');
            if (titleEl) titleEl.textContent = 'Drag & drop single KYC document';
            if (hintEl) hintEl.textContent = 'Upload 1 document (PDF, PNG, JPG, or TIFF)';
        }
    }

    setupDropZone() {
        if (!this.dropZone) return;

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach((name) => {
            this.dropZone.addEventListener(name, (e) => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
            document.body.addEventListener(name, (e) => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
        });

        ['dragenter', 'dragover'].forEach((name) => {
            this.dropZone.addEventListener(name, () => this.dropZone.classList.add('drag-over'), false);
        });

        ['dragleave', 'drop'].forEach((name) => {
            this.dropZone.addEventListener(name, () => this.dropZone.classList.remove('drag-over'), false);
        });

        this.dropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer?.files;
            if (files && files.length > 0) {
                this.handleFilesSelect(Array.from(files));
            }
        });

        this.dropZone.addEventListener('click', (e) => {
            // Only trigger file picker if not clicking on remove buttons or list items
            if (e.target.closest('.btn-clear-all') || e.target.closest('.btn-remove-single-file')) {
                return;
            }
            if (this.selectedFiles.length === 0) {
                this.fileInput.click();
            }
        });
    }

    onPaste(e) {
        const items = e.clipboardData?.items;
        if (!items) return;

        const pastedFiles = [];
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (item.kind === 'file') {
                const file = item.getAsFile();
                if (file && (file.type.startsWith('image/') || file.type === 'application/pdf')) {
                    pastedFiles.push(file);
                }
            }
        }
        if (pastedFiles.length > 0) {
            e.preventDefault();
            this.handleFilesSelect(pastedFiles);
            this.showToast(`${pastedFiles.length} document(s) pasted from clipboard`);
        }
    }

    handleFilesSelect(files) {
        const validExtensions = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif'];
        const validFiles = [];

        for (const file of files) {
            const ext = '.' + file.name.split('.').pop().toLowerCase();
            if (!validExtensions.includes(ext) && !file.type.startsWith('image/')) {
                this.showToast(`Skipped ${file.name}: unsupported format.`);
                continue;
            }
            if (file.size > 10 * 1024 * 1024) {
                this.showToast(`Skipped ${file.name}: exceeds 10 MB limit.`);
                continue;
            }
            validFiles.push(file);
        }

        if (this.ingestionMode === 'single') {
            this.selectedFiles = validFiles.slice(0, 1);
        } else {
            this.selectedFiles = [...this.selectedFiles, ...validFiles].slice(0, 5);
        }

        this.renderFilePreviews();
    }

    removeFileAt(index) {
        if (index >= 0 && index < this.selectedFiles.length) {
            this.selectedFiles.splice(index, 1);
            this.renderFilePreviews();
        }
    }

    clearAllFiles() {
        this.selectedFiles = [];
        if (this.fileInput) this.fileInput.value = '';
        this.renderFilePreviews();
    }

    renderFilePreviews() {
        const container = document.getElementById('file-previews-container');
        const list = document.getElementById('file-previews-list');
        const countLabel = document.getElementById('preview-count-label');
        const dropContent = this.dropZone.querySelector('.drop-zone-content');

        if (!container || !list) return;

        if (this.selectedFiles.length === 0) {
            container.classList.add('hidden');
            if (dropContent) dropContent.classList.remove('hidden');
            if (this.btnProcess) this.btnProcess.disabled = true;
            return;
        }

        if (dropContent) dropContent.classList.add('hidden');
        container.classList.remove('hidden');

        if (countLabel) {
            countLabel.textContent = `${this.selectedFiles.length} Document${this.selectedFiles.length > 1 ? 's' : ''} Attached`;
        }

        list.innerHTML = '';
        this.selectedFiles.forEach((file, idx) => {
            const isFirst = idx === 0;
            const isSecond = idx === 1;
            const roleBadge = isFirst
                ? 'Primary ID (e.g. PAN)'
                : (isSecond ? 'Secondary ID (e.g. Aadhaar)' : `Doc ${idx + 1}`);

            const card = document.createElement('div');
            card.className = 'file-card-item';
            card.innerHTML = `
                <div class="file-card-left">
                    <span class="doc-role-badge">${roleBadge}</span>
                    <i class="fas ${file.name.endsWith('.pdf') ? 'fa-file-pdf text-danger' : 'fa-file-image text-accent'}"></i>
                    <div class="file-card-info">
                        <div class="file-card-name" title="${file.name}">${file.name}</div>
                        <div class="file-card-size">${(file.size / (1024 * 1024)).toFixed(2)} MB</div>
                    </div>
                </div>
                <button type="button" class="btn-remove-single-file" onclick="removeFileAt(${idx})" title="Remove document">
                    <i class="fas fa-trash-can"></i>
                </button>
            `;
            list.appendChild(card);
        });

        if (this.btnProcess) {
            this.btnProcess.disabled = false;
        }
    }

    resetForm() {
        this.clearFile();
        this.resetPipelineNodes();
        const resultsContent = document.getElementById('results-content');
        const resultsEmpty = document.getElementById('results-empty');
        if (resultsContent) resultsContent.classList.add('hidden');
        if (resultsEmpty) resultsEmpty.classList.remove('hidden');

        const metaSub = document.getElementById('res-meta-sub');
        if (metaSub) metaSub.textContent = 'Awaiting document processing...';

        if (this.btnCopy) this.btnCopy.disabled = true;
        if (this.btnDownload) this.btnDownload.disabled = true;
    }

    resetPipelineNodes() {
        for (let i = 1; i <= 5; i++) {
            const node = document.getElementById(`node-stage-${i}`);
            const badge = document.getElementById(`badge-stage-${i}`);
            if (node) {
                node.className = 'pipe-node';
            }
            if (badge) {
                badge.textContent = 'Ready';
            }
        }
    }

    animatePipelineNodes() {
        this.resetPipelineNodes();
        let step = 1;
        const interval = setInterval(() => {
            if (step > 5 || !this.processing) {
                clearInterval(interval);
                return;
            }
            for (let i = 1; i <= 5; i++) {
                const node = document.getElementById(`node-stage-${i}`);
                const badge = document.getElementById(`badge-stage-${i}`);
                if (i < step) {
                    node?.classList.remove('node--active');
                    node?.classList.add('node--done');
                    if (badge) badge.textContent = 'Done';
                } else if (i === step) {
                    node?.classList.add('node--active');
                    if (badge) badge.textContent = 'Running...';
                }
            }
            step++;
        }, 350);
    }

    finalizePipelineNodes(auditTrail) {
        if (!auditTrail || !Array.isArray(auditTrail)) return;

        auditTrail.forEach((stage, idx) => {
            const nodeIdx = idx + 1;
            const node = document.getElementById(`node-stage-${nodeIdx}`);
            const badge = document.getElementById(`badge-stage-${nodeIdx}`);

            if (node) {
                node.className = 'pipe-node node--done';
            }
            if (badge) {
                badge.textContent = `${Math.round(stage.execution_time_ms)}ms`;
            }
        });
    }

    async processDocument() {
        if (this.selectedFiles.length === 0 || this.processing) return;

        this.setProcessingState(true);
        this.animatePipelineNodes();

        try {
            let response;
            if (this.selectedFiles.length === 1) {
                const formData = new FormData();
                formData.append('file', this.selectedFiles[0]);
                response = await fetch('/api/v1/kyc/process', {
                    method: 'POST',
                    body: formData,
                });
            } else {
                const formData = new FormData();
                this.selectedFiles.forEach((file) => {
                    formData.append('files', file);
                });
                response = await fetch('/api/v1/kyc/verify-multiple', {
                    method: 'POST',
                    body: formData,
                });
            }

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Pipeline processing failed.');
            }

            const result = await response.json();
            this.handleProcessingSuccess(result);
        } catch (err) {
            console.error(err);
            this.showToast(`Error: ${err.message}`);
        } finally {
            this.setProcessingState(false);
        }
    }

    async runSample(sampleKey) {
        if (this.processing) return;

        this.setProcessingState(true);
        this.animatePipelineNodes();

        try {
            const response = await fetch(`/api/v1/kyc/sample/${sampleKey}`, {
                method: 'POST',
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Sample verification failed.');
            }

            const result = await response.json();
            this.handleProcessingSuccess(result);
            this.showToast(`Verified sample: ${sampleKey}`);
        } catch (err) {
            console.error(err);
            this.showToast(`Error: ${err.message}`);
        } finally {
            this.setProcessingState(false);
        }
    }

    async runMultiSample(sampleKey) {
        if (this.processing) return;

        this.setProcessingState(true);
        this.animatePipelineNodes();

        try {
            const response = await fetch(`/api/v1/kyc/sample-multi/${sampleKey}`, {
                method: 'POST',
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Multi-document sample verification failed.');
            }

            const result = await response.json();
            this.handleProcessingSuccess(result);
            this.showToast(`Verified loan KYC combo: ${sampleKey}`);
        } catch (err) {
            console.error(err);
            this.showToast(`Error: ${err.message}`);
        } finally {
            this.setProcessingState(false);
        }
    }

    handleProcessingSuccess(result) {
        this.lastResult = result;

        // If multi-doc, aggregate audit trails for nodes
        if (result.batch_id && result.documents && result.documents.length > 0) {
            this.finalizePipelineNodes(result.documents[0].audit_trail);
        } else {
            this.finalizePipelineNodes(result.audit_trail);
        }

        this.renderResults(result);
        this.loadStats();
        this.loadRecords();

        if (this.btnCopy) this.btnCopy.disabled = false;
        if (this.btnDownload) this.btnDownload.disabled = false;
    }

    renderResults(result) {
        const emptyState = document.getElementById('results-empty');
        const contentState = document.getElementById('results-content');
        if (emptyState) emptyState.classList.add('hidden');
        if (contentState) contentState.classList.remove('hidden');

        const metaSub = document.getElementById('res-meta-sub');
        const banner = document.getElementById('routing-verdict-banner');
        const badge = document.getElementById('routing-status-badge');
        const docType = document.getElementById('routing-doc-type');
        const confNum = document.getElementById('routing-confidence');
        const reasonsList = document.getElementById('routing-reasons-list');
        const crossCard = document.getElementById('cross-document-card');
        const multiDocNav = document.getElementById('multi-doc-nav');

        const isMulti = Boolean(result.batch_id && result.documents);

        if (isMulti) {
            // Multi-document Loan KYC Result
            if (metaSub) {
                metaSub.textContent = `Batch ID: ${result.batch_id} · Latency: ${result.total_processing_time_ms}ms · Documents: ${result.documents.length}`;
            }

            const status = result.overall_routing_status || 'MANUAL_REVIEW';
            if (banner) {
                banner.className = `verdict-banner verdict-${status === 'PASS' ? 'pass' : (status === 'FAIL' ? 'fail' : 'warn')}`;
            }
            if (badge) badge.textContent = status;
            if (docType) docType.textContent = `LOAN KYC RECONCILIATION (${result.documents.length} DOCS)`;
            if (confNum) confNum.textContent = `${Math.round((result.cross_match_score || 1) * 100)}%`;

            if (reasonsList) {
                reasonsList.innerHTML = '';
                (result.overall_reasons || []).forEach((r) => {
                    const li = document.createElement('li');
                    li.textContent = r;
                    reasonsList.appendChild(li);
                });
            }

            // Cross Document Reconciliation Card
            if (crossCard) {
                crossCard.classList.remove('hidden');
                const crossBadge = document.getElementById('cross-score-badge');
                const crossTableBody = document.getElementById('cross-table-body');

                const cross = result.cross_consistency || {};
                const score = Math.round((result.cross_match_score || 1) * 100);

                if (crossBadge) {
                    crossBadge.textContent = `${score}% Match Score`;
                    crossBadge.className = `cross-score-pill ${score >= 85 ? '' : (score >= 60 ? 'cross-score-pill--warn' : 'cross-score-pill--fail')}`;
                }

                if (crossTableBody) {
                    crossTableBody.innerHTML = '';

                    // Name Row
                    const nameSim = Math.round((cross.name_similarity || 1) * 100);
                    let nameBadgeClass = 'cross-status-badge--match';
                    let nameBadgeText = `MATCH (${nameSim}%)`;
                    if (nameSim < 70) {
                        nameBadgeClass = 'cross-status-badge--mismatch';
                        nameBadgeText = `CONFLICT (${nameSim}%)`;
                    } else if (nameSim < 85) {
                        nameBadgeClass = 'cross-status-badge--partial';
                        nameBadgeText = `ABBREVIATION (${nameSim}%)`;
                    }

                    const trName = document.createElement('tr');
                    trName.innerHTML = `
                        <td><strong>Applicant Name</strong></td>
                        <td>${cross.name_doc1 || 'N/A'}</td>
                        <td>${cross.name_doc2 || 'N/A'}</td>
                        <td><span class="cross-status-badge ${nameBadgeClass}"><i class="fas ${cross.name_match ? 'fa-check' : 'fa-triangle-exclamation'}"></i> ${nameBadgeText}</span></td>
                    `;
                    crossTableBody.appendChild(trName);

                    // DOB Row
                    const dobMatch = cross.dob_match;
                    const dobBadgeClass = dobMatch ? 'cross-status-badge--match' : 'cross-status-badge--mismatch';
                    const dobBadgeText = dobMatch ? 'VERIFIED MATCH' : 'DOB MISMATCH';

                    const trDob = document.createElement('tr');
                    trDob.innerHTML = `
                        <td><strong>Date of Birth (DOB)</strong></td>
                        <td>${cross.dob_doc1 || 'N/A'}</td>
                        <td>${cross.dob_doc2 || 'N/A'}</td>
                        <td><span class="cross-status-badge ${dobBadgeClass}"><i class="fas ${dobMatch ? 'fa-check' : 'fa-xmark'}"></i> ${dobBadgeText}</span></td>
                    `;
                    crossTableBody.appendChild(trDob);

                    // Father's Name Row
                    if (cross.fathers_name_doc1 || cross.fathers_name_doc2) {
                        const fn1 = cross.fathers_name_doc1 || 'N/A';
                        const fn2 = cross.fathers_name_doc2 || 'N/A';
                        const fnMatch = cross.fathers_name_match !== false;
                        const fnBadgeClass = fnMatch ? 'cross-status-badge--match' : 'cross-status-badge--partial';
                        const fnBadgeText = fnMatch ? 'MATCH' : 'REQUIRES REVIEW';

                        const trFn = document.createElement('tr');
                        trFn.innerHTML = `
                            <td><strong>Father's Name</strong></td>
                            <td>${fn1}</td>
                            <td>${fn2}</td>
                            <td><span class="cross-status-badge ${fnBadgeClass}"><i class="fas ${fnMatch ? 'fa-check' : 'fa-info-circle'}"></i> ${fnBadgeText}</span></td>
                        `;
                        crossTableBody.appendChild(trFn);
                    }
                }
            }

            // Setup document tabs
            if (multiDocNav) {
                multiDocNav.classList.remove('hidden');
                const btnContainer = document.getElementById('doc-nav-buttons');
                if (btnContainer) {
                    btnContainer.innerHTML = '';
                    result.documents.forEach((doc, idx) => {
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className = `doc-nav-btn ${idx === 0 ? 'doc-nav-btn--active' : ''}`;
                        btn.id = `doc-nav-btn-${idx}`;
                        const docLabel = doc.document_type ? doc.document_type.toUpperCase() : `DOC ${idx + 1}`;
                        btn.innerHTML = `<i class="fas ${doc.routing_status === 'PASS' ? 'fa-check text-success' : 'fa-triangle-exclamation text-warning'}"></i> Doc ${idx + 1}: ${docLabel} (${doc.routing_status})`;
                        btn.onclick = () => this.switchActiveDoc(idx);
                        btnContainer.appendChild(btn);
                    });
                }
            }

            this.activeDocIndex = 0;
            this.renderSingleDocDetails(result.documents[0]);

        } else {
            // Single Document Result
            if (crossCard) crossCard.classList.add('hidden');
            if (multiDocNav) multiDocNav.classList.add('hidden');

            if (metaSub) {
                metaSub.textContent = `ID: ${result.verification_id} · Latency: ${result.processing_time_ms}ms`;
            }

            const status = result.routing_status || 'MANUAL_REVIEW';
            if (banner) {
                banner.className = `verdict-banner verdict-${status === 'PASS' ? 'pass' : (status === 'FAIL' ? 'fail' : 'warn')}`;
            }
            if (badge) badge.textContent = status;
            if (docType) {
                docType.textContent = result.document_type ? result.document_type.replace('_', ' ').toUpperCase() : 'UNKNOWN ID';
            }
            if (confNum) confNum.textContent = `${Math.round(result.confidence * 100)}%`;

            if (reasonsList) {
                reasonsList.innerHTML = '';
                const reasons = result.routing_reasons && result.routing_reasons.length > 0
                    ? result.routing_reasons
                    : ['All policy and security rules processed.'];
                reasons.forEach((r) => {
                    const li = document.createElement('li');
                    li.textContent = r;
                    reasonsList.appendChild(li);
                });
            }

            this.renderSingleDocDetails(result);
        }

        // Render Raw JSON
        const rawJsonEl = document.getElementById('raw-json-code');
        if (rawJsonEl) {
            rawJsonEl.textContent = JSON.stringify(result, null, 2);
        }
    }

    switchActiveDoc(idx) {
        if (!this.lastResult || !this.lastResult.documents || !this.lastResult.documents[idx]) return;
        this.activeDocIndex = idx;

        // Update active nav button
        document.querySelectorAll('.doc-nav-btn').forEach((btn, i) => {
            if (i === idx) {
                btn.classList.add('doc-nav-btn--active');
            } else {
                btn.classList.remove('doc-nav-btn--active');
            }
        });

        this.renderSingleDocDetails(this.lastResult.documents[idx]);
    }

    renderSingleDocDetails(doc) {
        if (!doc) return;

        // Aadhaar security masking notice
        const maskNotice = document.getElementById('masked-security-notice');
        if (maskNotice) {
            if (doc.masked || doc.document_type === 'aadhaar') {
                maskNotice.classList.remove('hidden');
            } else {
                maskNotice.classList.add('hidden');
            }
        }

        // Render Extracted Fields
        const fieldsGrid = document.getElementById('fields-grid');
        const fieldsCount = document.getElementById('fields-count');
        const fields = doc.fields || {};
        const scores = doc.field_level_scores || {};
        const fieldEntries = Object.entries(fields);

        if (fieldsCount) fieldsCount.textContent = fieldEntries.length;
        if (fieldsGrid) {
            fieldsGrid.innerHTML = '';
            if (fieldEntries.length === 0) {
                fieldsGrid.innerHTML = '<p class="text-muted">No fields could be extracted from this document scan.</p>';
            } else {
                fieldEntries.forEach(([key, value]) => {
                    const score = scores[key] ? Math.round(scores[key] * 100) : 95;
                    const card = document.createElement('div');
                    card.className = 'field-card';
                    card.innerHTML = `
                        <div class="field-header">
                            <span class="field-key">${key.replace('_', ' ')}</span>
                            <span class="field-confidence-pill">${score}% Conf</span>
                        </div>
                        <div class="field-val">${Array.isArray(value) ? value.join(', ') : value}</div>
                        <div class="field-meter-bg">
                            <div class="field-meter-fill" style="width: ${score}%;"></div>
                        </div>
                    `;
                    fieldsGrid.appendChild(card);
                });
            }
        }

        // Render Audit Timeline
        const auditTimeline = document.getElementById('audit-timeline');
        const auditCount = document.getElementById('audit-count');
        const auditLogs = doc.audit_trail || [];

        if (auditCount) auditCount.textContent = auditLogs.length;
        if (auditTimeline) {
            auditTimeline.innerHTML = '';
            auditLogs.forEach((log) => {
                const item = document.createElement('div');
                item.className = 'audit-item';
                const statusColor = log.status === 'SUCCESS' ? 'text-success' : (log.status === 'WARNING' ? 'text-warning' : 'text-danger');
                item.innerHTML = `
                    <div class="audit-item-top">
                        <span class="audit-stage-name">${log.stage_name}</span>
                        <span class="audit-time-pill">${log.execution_time_ms} ms</span>
                    </div>
                    <div class="audit-item-mid ${statusColor}">● ${log.status} · ${log.input_summary || ''}</div>
                    <div class="audit-item-out">${log.output_summary || ''}</div>
                `;
                auditTimeline.appendChild(item);
            });
        }
    }

    switchResultTab(tabName) {
        this.currentTab = tabName;
        ['fields', 'audit', 'json'].forEach((t) => {
            const btn = document.getElementById(`tab-btn-${t}`);
            const view = document.getElementById(`tab-view-${t}`);
            if (t === tabName) {
                btn?.classList.add('res-tab--active');
                view?.classList.remove('hidden');
            } else {
                btn?.classList.remove('res-tab--active');
                view?.classList.add('hidden');
            }
        });
    }

    setProcessingState(isProcessing) {
        this.processing = isProcessing;
        const progress = document.getElementById('progress-container');
        if (this.btnProcess) {
            this.btnProcess.disabled = isProcessing;
            this.btnProcess.innerHTML = isProcessing
                ? '<i class="fas fa-spinner fa-spin"></i> Processing Pipeline...'
                : '<i class="fas fa-bolt"></i> Run Pipeline Verification';
        }
        if (progress) {
            if (isProcessing) {
                progress.classList.remove('hidden');
            } else {
                progress.classList.add('hidden');
            }
        }
    }

    async loadStats() {
        try {
            const res = await fetch('/api/v1/kyc/stats');
            if (!res.ok) return;
            const data = await res.json();

            const totalEl = document.getElementById('stat-total');
            const passEl = document.getElementById('stat-pass');
            const manualEl = document.getElementById('stat-manual');
            const latencyEl = document.getElementById('stat-latency');

            if (totalEl) totalEl.textContent = data.total_processed;
            if (passEl) passEl.textContent = `${data.pass_rate_percent}%`;
            if (manualEl) {
                const manualRate = data.total_processed > 0
                    ? Math.round((data.manual_review_count / data.total_processed) * 100)
                    : 0;
                manualEl.textContent = `${manualRate}%`;
            }
            if (latencyEl) latencyEl.textContent = `${Math.round(data.avg_latency_ms)}ms`;
        } catch (e) {
            console.warn('Could not load stats:', e);
        }
    }

    async loadRecords() {
        const filterEl = document.getElementById('filter-status');
        const status = filterEl ? filterEl.value : 'ALL';
        const tbody = document.getElementById('history-table-body');
        if (!tbody) return;

        try {
            const url = status === 'ALL' ? '/api/v1/kyc/records' : `/api/v1/kyc/records?status=${status}`;
            const res = await fetch(url);
            if (!res.ok) return;
            const records = await res.json();

            tbody.innerHTML = '';
            if (records.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-muted">No stored verification records found in SQLite.</td></tr>';
                return;
            }

            records.forEach((r) => {
                const tr = document.createElement('tr');
                const badgeClass = r.routing_status === 'PASS'
                    ? 'table-badge--pass'
                    : (r.routing_status === 'FAIL' ? 'table-badge--fail' : 'table-badge--manual');

                tr.innerHTML = `
                    <td class="font-mono text-accent">${r.verification_id}</td>
                    <td>${r.created_at ? r.created_at.replace('T', ' ').substring(0, 19) : 'Just now'}</td>
                    <td><strong>${r.document_type ? r.document_type.toUpperCase() : 'N/A'}</strong></td>
                    <td class="text-muted">${r.filename || 'Direct Upload'}</td>
                    <td><span class="table-badge ${badgeClass}">${r.routing_status}</span></td>
                    <td class="font-mono">${Math.round((r.confidence || 0) * 100)}%</td>
                    <td class="font-mono">${Math.round(r.processing_time_ms || 0)}ms</td>
                    <td>
                        <button type="button" class="btn btn-ghost btn-sm" onclick="viewRecordDetails('${r.verification_id}')">
                            <i class="fas fa-eye"></i> View
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } catch (e) {
            console.warn('Could not load verification records:', e);
        }
    }

    async viewRecordDetails(verificationId) {
        try {
            const res = await fetch(`/api/v1/kyc/records/${verificationId}`);
            if (!res.ok) throw new Error('Record not found.');
            const data = await res.json();

            // Transform into ProcessingResult format and render
            const result = {
                verification_id: data.verification_id,
                document_type: data.document_type,
                confidence: data.confidence,
                routing_status: data.routing_status,
                routing_reasons: data.routing_reasons,
                fields: data.masked_fields || data.extracted_fields,
                masked: data.masked,
                field_level_scores: data.field_level_scores,
                extraction_warnings: data.warnings,
                processing_time_ms: data.processing_time_ms,
                audit_trail: data.audit_logs || [],
            };

            this.renderResults(result);
            window.location.hash = 'results-content';
            this.showToast(`Loaded verification ${verificationId}`);
        } catch (e) {
            this.showToast(`Error: ${e.message}`);
        }
    }

    copyLastResult() {
        if (!this.lastResult) return;
        navigator.clipboard.writeText(JSON.stringify(this.lastResult, null, 2))
            .then(() => this.showToast('JSON copied to clipboard!'))
            .catch(() => this.showToast('Failed to copy to clipboard.'));
    }

    downloadLastResult() {
        if (!this.lastResult) return;
        const blob = new Blob([JSON.stringify(this.lastResult, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `verification_${this.lastResult.verification_id || 'result'}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    showToast(msg) {
        const toast = document.getElementById('toast');
        if (!toast) return;
        toast.textContent = msg;
        toast.classList.remove('hidden');
        toast.classList.add('toast--show');
        clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => {
            toast.classList.remove('toast--show');
            setTimeout(() => toast.classList.add('hidden'), 350);
        }, 2500);
    }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    window.kycStudio = new KYCStudio();
});
