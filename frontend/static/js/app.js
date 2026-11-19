/**
 * Document Verification Pipeline — Interactive Client
 * Powered by Groq Llama, Tesseract OCR, and SQLite Audit Logs
 */

class KYCStudio {
    constructor() {
        this.selectedFile = null;
        this.processing = false;
        this.lastResult = null;
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
                if (e.target.files && e.target.files[0]) {
                    this.handleFileSelect(e.target.files[0]);
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
        window.clearFile = () => this.clearFile();
        window.resetForm = () => this.resetForm();
        window.copyLastResult = () => this.copyLastResult();
        window.downloadLastResult = () => this.downloadLastResult();
        window.switchResultTab = (tab) => this.switchResultTab(tab);
        window.loadRecords = () => this.loadRecords();
        window.viewRecordDetails = (id) => this.viewRecordDetails(id);

        // Clipboard paste image support
        document.addEventListener('paste', (e) => this.onPaste(e));
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
                this.handleFileSelect(files[0]);
            }
        });

        this.dropZone.addEventListener('click', () => {
            if (!this.selectedFile) {
                this.fileInput.click();
            }
        });
    }

    onPaste(e) {
        const items = e.clipboardData?.items;
        if (!items) return;

        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (item.kind === 'file') {
                const file = item.getAsFile();
                if (file && (file.type.startsWith('image/') || file.type === 'application/pdf')) {
                    e.preventDefault();
                    this.handleFileSelect(file);
                    this.showToast('Document pasted from clipboard');
                    break;
                }
            }
        }
    }

    handleFileSelect(file) {
        const validExtensions = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif'];
        const ext = '.' + file.name.split('.').pop().toLowerCase();

        if (!validExtensions.includes(ext) && !file.type.startsWith('image/')) {
            this.showToast('Please upload a PDF or image file (PNG, JPG, TIFF).');
            return;
        }

        if (file.size > 10 * 1024 * 1024) {
            this.showToast('File size exceeds 10 MB limit.');
            return;
        }

        this.selectedFile = file;

        // Update preview
        const preview = document.getElementById('file-preview');
        const nameEl = document.getElementById('file-name');
        const sizeEl = document.getElementById('file-size');
        const dropContent = this.dropZone.querySelector('.drop-zone-content');

        if (preview && nameEl && sizeEl) {
            nameEl.textContent = file.name;
            sizeEl.textContent = (file.size / (1024 * 1024)).toFixed(2) + ' MB';
            preview.classList.remove('hidden');
            if (dropContent) dropContent.classList.add('hidden');
        }

        if (this.btnProcess) {
            this.btnProcess.disabled = false;
        }
    }

    clearFile() {
        this.selectedFile = null;
        if (this.fileInput) this.fileInput.value = '';

        const preview = document.getElementById('file-preview');
        const dropContent = this.dropZone.querySelector('.drop-zone-content');

        if (preview) preview.classList.add('hidden');
        if (dropContent) dropContent.classList.remove('hidden');
        if (this.btnProcess) this.btnProcess.disabled = true;
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
        if (!this.selectedFile || this.processing) return;

        this.setProcessingState(true);
        this.animatePipelineNodes();

        const formData = new FormData();
        formData.append('file', this.selectedFile);

        try {
            const response = await fetch('/api/v1/kyc/process', {
                method: 'POST',
                body: formData,
            });

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

    handleProcessingSuccess(result) {
        this.lastResult = result;
        this.finalizePipelineNodes(result.audit_trail);
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

        // Meta sub
        const metaSub = document.getElementById('res-meta-sub');
        if (metaSub) {
            metaSub.textContent = `ID: ${result.verification_id} · Latency: ${result.processing_time_ms}ms`;
        }

        // Routing verdict banner
        const banner = document.getElementById('routing-verdict-banner');
        const badge = document.getElementById('routing-status-badge');
        const docType = document.getElementById('routing-doc-type');
        const confNum = document.getElementById('routing-confidence');
        const reasonsList = document.getElementById('routing-reasons-list');

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

        // Aadhaar security masking banner
        const maskNotice = document.getElementById('masked-security-notice');
        if (maskNotice) {
            if (result.masked || (result.document_type === 'aadhaar')) {
                maskNotice.classList.remove('hidden');
            } else {
                maskNotice.classList.add('hidden');
            }
        }

        // Render Fields
        const fieldsGrid = document.getElementById('fields-grid');
        const fieldsCount = document.getElementById('fields-count');
        const fields = result.fields || {};
        const scores = result.field_level_scores || {};
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
        const auditLogs = result.audit_trail || [];

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

        // Render Raw JSON
        const rawJsonEl = document.getElementById('raw-json-code');
        if (rawJsonEl) {
            rawJsonEl.textContent = JSON.stringify(result, null, 2);
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
