#!/usr/bin/env python3
"""
Trinity Web App v3.0 - CLINICAL EDITION
Clean version - all routes properly defined
"""

import os
import uuid
import json
import subprocess
import re
import zipfile
import base64
import threading
import requests
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import plotly.graph_objs as go
import plotly.utils
import numpy as np

app = Flask(__name__)
CORS(app)

# Configuration
BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_FOLDER = BASE_DIR / 'uploads'
RESULTS_FOLDER = BASE_DIR / 'results'

ALLOWED_EXTENSIONS = {
    '.edf', '.edf+', '.bdf', '.bdf+', '.gdf', '.gdf2',
    '.fif', '.fif.gz', '.set', '.raw', '.vhdr', '.vmrk', '.eeg',
    '.cnt', '.nwb', '.xdf'
}

for folder in [UPLOAD_FOLDER, RESULTS_FOLDER]:
    folder.mkdir(parents=True, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

TRINITY_QUICK = BASE_DIR / 'tools' / 'trinity_research_v1.2_fixed.py'
TRINITY_DEEP = BASE_DIR / 'tools' / 'batch_failed_seizure_detector_v3.1.py'

jobs = {}

def allowed_file(filename):
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS

def parse_trinity_output(output, mode):
    result = {'success': True, 'mode': mode, 'raw_output': output[-3000:] if len(output) > 3000 else output}
    if mode == 'quick':
        lead_times = re.findall(r'Lead:\s*(\d+)s', output)
        peak_ratios = re.findall(r'Peak:\s*([\d,]+\.?\d*)x', output)
        result['seizures_found'] = len(lead_times)
        result['lead_times'] = lead_times
        result['peak_ratios'] = [p.replace(',', '') for p in peak_ratios]
    else:
        failed_matches = re.findall(r'💚 FAILED SEIZURES?:?\s*(\d+)', output)
        if not failed_matches:
            failed_matches = re.findall(r'FAILED SEIZURES?:?\s*(\d+)', output)
        result['failed_seizures_count'] = int(failed_matches[0]) if failed_matches else 0
        clinical_matches = re.findall(r'CLINICAL SEIZURES?:?\s*(\d+)', output)
        result['clinical_seizures_count'] = int(clinical_matches[0]) if clinical_matches else 0
    return result

def run_trinity_quick(filepath, patient_id):
    try:
        cmd = ['python', str(TRINITY_QUICK), '--path', str(filepath.parent), '--patient', patient_id]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(BASE_DIR))
        return parse_trinity_output(result.stdout, 'quick')
    except Exception as e:
        return {'success': False, 'error': str(e), 'mode': 'quick'}

def run_trinity_deep(filepath, patient_id):
    try:
        cmd = ['python', str(TRINITY_DEEP), '--path', str(filepath.parent), '--patient', patient_id]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(BASE_DIR))
        return parse_trinity_output(result.stdout, 'deep')
    except Exception as e:
        return {'success': False, 'error': str(e), 'mode': 'deep'}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    mode = request.form.get('mode', 'quick')
    patient_id = request.form.get('patient_id', 'upload')
    job_id = str(uuid.uuid4())[:12]
    filename = secure_filename(file.filename)
    filepath = UPLOAD_FOLDER / f"{job_id}_{filename}"
    file.save(filepath)
    jobs[job_id] = {'id': job_id, 'status': 'analyzing', 'progress': 30, 'mode': mode, 'filename': filename, 'patient_id': patient_id}
    def analyze():
        try:
            jobs[job_id]['progress'] = 50
            if mode == 'quick':
                result = run_trinity_quick(filepath, patient_id)
            else:
                result = run_trinity_deep(filepath, patient_id)
            if result.get('success', False):
                jobs[job_id]['result'] = result
                jobs[job_id]['status'] = 'completed'
                jobs[job_id]['progress'] = 100
            else:
                jobs[job_id]['status'] = 'failed'
                jobs[job_id]['error'] = result.get('error', 'Analysis failed')
        except Exception as e:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)
        finally:
            try:
                filepath.unlink()
            except:
                pass
    threading.Thread(target=analyze).start()
    return jsonify({'job_id': job_id})

@app.route('/analyze_url', methods=['POST'])
def analyze_url():
    data = request.get_json()
    file_url = data.get('url')
    mode = data.get('mode', 'quick')
    patient_id = data.get('patient_id', 'remote')
    if not file_url:
        return jsonify({'error': 'No URL provided'}), 400
    job_id = str(uuid.uuid4())[:12]
    filename = file_url.split('/')[-1].split('?')[0] or 'file.edf'
    jobs[job_id] = {'id': job_id, 'status': 'downloading', 'progress': 10, 'mode': mode, 'filename': filename, 'patient_id': patient_id}
    def download_and_analyze():
        filepath = None
        try:
            response = requests.get(file_url, timeout=300, stream=True)
            response.raise_for_status()
            filepath = UPLOAD_FOLDER / f"{job_id}_{filename}"
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            jobs[job_id]['progress'] = 50
            if mode == 'quick':
                result = run_trinity_quick(filepath, patient_id)
            else:
                result = run_trinity_deep(filepath, patient_id)
            if result.get('success', False):
                jobs[job_id]['result'] = result
                jobs[job_id]['status'] = 'completed'
                jobs[job_id]['progress'] = 100
            else:
                jobs[job_id]['status'] = 'failed'
                jobs[job_id]['error'] = result.get('error', 'Analysis failed')
        except Exception as e:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)
        finally:
            if filepath and filepath.exists():
                filepath.unlink()
    threading.Thread(target=download_and_analyze).start()
    return jsonify({'job_id': job_id})

@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    job = jobs[job_id]
    response = {'status': job['status'], 'progress': job.get('progress', 0), 'mode': job.get('mode', 'quick')}
    if job['status'] == 'completed':
        response['result'] = job.get('result')
    if job['status'] == 'failed':
        response['error'] = job.get('error')
    return jsonify(response)

@app.route('/download/<job_id>')
def download(job_id):
    if job_id not in jobs:
        return "Job not found", 404
    job = jobs[job_id]
    result_file = RESULTS_FOLDER / f"{job_id}_results.json"
    with open(result_file, 'w') as f:
        json.dump(job.get('result', {}), f, indent=2)
    return send_file(result_file, as_attachment=True, download_name=f"trinity_{job_id}.json")

@app.route('/simulator')
def simulator():
    return render_template('simulator.html')

if __name__ == '__main__':
    print("🧠 Trinity Web App v3.0 - CLINICAL EDITION")
    print("=" * 60)
    print("URL: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)

@app.route('/clinical_report_text/<job_id>')
def clinical_report_text(job_id):
    """Generate clinical text report for a completed job"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    if job['status'] != 'completed':
        return jsonify({'error': 'Analysis not complete'}), 400
    
    # Get the result
    result = job.get('result', {})
    
    # Create a simple clinical report
    if result.get('mode') == 'quick':
        report = f"""
TRINITY CLINICAL REPORT
{'=' * 60}
File: {job.get('filename', 'unknown')}
Risk Level: {'HIGH' if result.get('seizures_found', 0) > 0 else 'LOW'}
Seizures Predicted: {result.get('seizures_found', 0)}
Lead Times: {', '.join(result.get('lead_times', []))} seconds
Peak Emergence: {result.get('peak_ratios', ['0'])[0]}x baseline

RECOMMENDATION: {'IMMEDIATE ATTENTION - Seizure imminent' if result.get('seizures_found', 0) > 0 else 'Continue routine monitoring'}
"""
    else:
        report = f"""
TRINITY CLINICAL REPORT
{'=' * 60}
File: {job.get('filename', 'unknown')}
FAILED SEIZURES DETECTED: {result.get('failed_seizures_count', 0)}
Clinical Seizures: {result.get('clinical_seizures_count', 0)}
Self-Correction Ratio: {result.get('failed_seizures_count', 0) / max(1, result.get('clinical_seizures_count', 1)):.1f}:1

INTERPRETATION: The brain self-corrected {result.get('failed_seizures_count', 0)} times without progressing to clinical seizure.
RECOMMENDATION: Reinforce natural self-correction mechanisms.
"""
    
    return jsonify({'report': report})

@app.route('/clinical_graph/<job_id>')
def clinical_graph(job_id):
    """Generate clinical graph for a completed job"""
    if job_id not in jobs:
        return "Job not found", 404
    
    job = jobs[job_id]
    if job['status'] != 'completed':
        return "Analysis not complete", 400
    
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import io
        
        result = job.get('result', {})
        timeline = result.get('timeline', [])
        
        if not timeline:
            return "No timeline data", 404
        
        # Create figure
        fig, ax = plt.subplots(figsize=(10, 4))
        times = [t['time_sec'] for t in timeline]
        risks = [abs(t['emergence']) for t in timeline]
        
        ax.fill_between(times, 0, risks, alpha=0.3, color='red')
        ax.plot(times, risks, 'r-', linewidth=1.5)
        ax.set_xlabel('Time (seconds)')
        ax.set_ylabel('Risk Index')
        ax.set_title(f'Seizure Risk - {job.get("filename", "Analysis")}')
        ax.grid(True, alpha=0.3)
        
        img = io.BytesIO()
        plt.savefig(img, format='png', dpi=100, bbox_inches='tight')
        plt.close()
        img.seek(0)
        
        return send_file(img, mimetype='image/png')
        
    except Exception as e:
        print(f"Graph error: {e}")
        return "Graph generation failed", 500

@app.route('/save_result/<job_id>', methods=['POST'])
def save_result(job_id):
    """Save analysis result permanently"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    if job['status'] != 'completed':
        return jsonify({'error': 'Analysis not complete'}), 400
    
    saved_dir = BASE_DIR / 'saved_results'
    saved_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{job.get('patient_id', 'unknown')}_{job.get('filename', 'result')}_{timestamp}.json"
    
    save_path = saved_dir / filename
    with open(save_path, 'w') as f:
        json.dump(job.get('result', {}), f, indent=2)
    
    return jsonify({'success': True, 'filename': filename})

@app.route('/list_saved_results')
def list_saved_results():
    """List all saved results"""
    saved_dir = BASE_DIR / 'saved_results'
    saved_dir.mkdir(exist_ok=True)
    
    results = []
    for file in sorted(saved_dir.glob('*.json'), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = file.stat()
        results.append({
            'filename': file.name,
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'url': f"/download_saved/{file.name}"
        })
    
    return jsonify({'results': results})

@app.route('/download_saved/<filename>')
def download_saved(filename):
    """Download a saved result"""
    saved_dir = BASE_DIR / 'saved_results'
    file_path = saved_dir / filename
    
    if not file_path.exists():
        return "File not found", 404
    
    return send_file(file_path, as_attachment=True)

@app.route('/delete_saved/<filename>', methods=['DELETE'])
def delete_saved(filename):
    """Delete a saved result"""
    saved_dir = BASE_DIR / 'saved_results'
    file_path = saved_dir / filename
    
    if file_path.exists():
        file_path.unlink()
        return jsonify({'success': True})
    
    return jsonify({'error': 'File not found'}), 404

