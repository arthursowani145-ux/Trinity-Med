// Trinity-Med Web Application
let currentJobId = null;
let statusInterval = null;

function uploadFile() {
    const fileInput = document.getElementById('fileInput');
    const mode = document.querySelector('input[name="mode"]:checked').value;
    const patientId = document.getElementById('patientId').value;
    
    if (!fileInput.files.length) {
        alert('Please select an EDF file');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('mode', mode);
    formData.append('patient_id', patientId);
    
    document.getElementById('analyzeBtn').disabled = true;
    document.getElementById('analyzeBtn').innerHTML = '<span class="processing">⏳ Uploading...</span>';
    document.getElementById('progressContainer').style.display = 'block';
    document.getElementById('resultsCard').style.display = 'none';
    
    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        currentJobId = data.job_id;
        document.getElementById('analyzeBtn').innerHTML = '<span class="processing">🧠 Analyzing...</span>';
        if (statusInterval) clearInterval(statusInterval);
        statusInterval = setInterval(checkStatus, 2000);
    })
    .catch(err => {
        console.error(err);
        alert('Upload failed');
        resetForm();
    });
}

function checkStatus() {
    if (!currentJobId) return;
    
    fetch(`/status/${currentJobId}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById('progressFill').style.width = `${data.progress}%`;
            document.getElementById('progressText').textContent = `${data.status}... ${data.progress}%`;
            
            if (data.status === 'completed') {
                clearInterval(statusInterval);
                displayResults(data.result);
                resetForm();
            } else if (data.status === 'failed') {
                clearInterval(statusInterval);
                alert(`Analysis failed: ${data.error || 'Unknown error'}`);
                resetForm();
            }
        })
        .catch(err => console.error(err));
}

function displayResults(result) {
    document.getElementById('resultsCard').style.display = 'block';
    
    if (result.mode === 'quick') {
        displayQuickResults(result);
    } else {
        displayDeepResults(result);
    }
    
    document.getElementById('downloadBtn').onclick = () => {
        window.open(`/download/${currentJobId}`, '_blank');
    };
}

function displayQuickResults(result) {
    document.getElementById('resultTitle').textContent = '🔴 SEIZURE PREDICTION RESULTS';
    const seizures = result.seizures_found || 0;
    const leadTimes = result.lead_times || [];
    
    let html = `<div class="metric"><div class="metric-value">${seizures}</div><div>Seizures Predicted</div></div>`;
    html += `<div class="metric"><div class="metric-value">${leadTimes.join(', ') || 'N/A'}</div><div>Lead Times (s)</div></div>`;
    document.getElementById('resultsContent').innerHTML = html;
}

function displayDeepResults(result) {
    document.getElementById('resultTitle').textContent = '💚 FAILED SEIZURE DISCOVERY';
    const failed = result.failed_seizures_count || 0;
    
    let html = `<div class="metric failed-seizure"><div class="metric-value">${failed}</div><div>Failed Seizures Found</div></div>`;
    html += `<div class="metric"><div class="metric-value">Brain Self-Corrected</div><div>Natural Recovery Events</div></div>`;
    document.getElementById('resultsContent').innerHTML = html;
}

function resetForm() {
    document.getElementById('analyzeBtn').disabled = false;
    document.getElementById('analyzeBtn').innerHTML = 'Analyze EEG';
    document.getElementById('fileInput').value = '';
    currentJobId = null;
}

function clearResults() {
    document.getElementById('resultsCard').style.display = 'none';
    document.getElementById('progressContainer').style.display = 'none';
    document.getElementById('progressFill').style.width = '0%';
    if (statusInterval) clearInterval(statusInterval);
    currentJobId = null;
}

// Hamburger menu
function toggleMenu() {
    const menu = document.getElementById('sideMenu');
    menu.classList.toggle('open');
}
