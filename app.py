#!/usr/bin/env python3
"""
Trinity Web App v2.0
- Fetch EDF from URL (PhysioNet or any source)
- Drag & drop upload
- Quick mode (v1.2) + Deep Dive (v3.1)
- Timeline visualization
- Matches Termux results exactly
"""

import os
import uuid
import json
import tempfile
import subprocess
import re
import requests
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import threading

app = Flask(__name__)
CORS(app)

# Configuration
BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_FOLDER = BASE_DIR / 'uploads'
RESULTS_FOLDER = BASE_DIR / 'results'
UPLOAD_FOLDER.mkdir(exist_ok=True)
RESULTS_FOLDER.mkdir(exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

# Tool paths
TRINITY_QUICK = BASE_DIR / 'tools' / 'trinity_research_v1.2_fixed.py'
TRINITY_DEEP = BASE_DIR / 'tools' / 'batch_failed_seizure_detector_v3.1.py'

# Job storage
jobs = {}

def download_from_url(url, destination):
    """Download file from URL with progress"""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    
    with open(destination, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            yield downloaded, total_size

def run_trinity_quick(filepath, patient_id, job_id):
    """Run quick prediction (v1.2) - matches Termux output exactly"""
    try:
        cmd = [
            'python', str(TRINITY_QUICK),
            '--path', str(filepath.parent),
            '--patient', patient_id
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = result.stdout
        
        # Parse results exactly as they appear in Termux
        seizure_files = re.findall(r'📁 (chb\d+_\d+.*?\.edf)', output)
        lead_times = re.findall(r'Lead:\s*(\d+)s', output)
        peak_ratios = re.findall(r'Peak:\s*([\d,]+\.?\d*)x', output)
        
        # Check for failed seizure in output
        has_failed = '💚 FAILED SEIZURE' in output or 'failed seizure' in output.lower()
        
        # Count seizure predictions
        seizure_count = len([l for l in lead_times if l])
        
        return {
            'success': True,
            'mode': 'quick',
            'seizures_found': seizure_count,
            'lead_times': lead_times,
            'peak_ratios': [p.replace(',', '') for p in peak_ratios],
            'has_failed_seizure': has_failed,
            'raw_output': output
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Analysis timeout (5 minutes)'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def run_trinity_deep(filepath, patient_id, job_id):
    """Run deep dive (v3.1) - matches Termux output exactly"""
    try:
        cmd = [
            'python', str(TRINITY_DEEP),
            '--path', str(filepath.parent),
            '--patient', patient_id
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        output = result.stdout
        
        # Parse failed seizure count
        failed_matches = re.findall(r'💚 FAILED SEIZURES?: (\d+)', output)
        if not failed_matches:
            failed_matches = re.findall(r'FAILED SEIZURES?: (\d+)', output)
        
        failed_count = int(failed_matches[0]) if failed_matches else 0
        
        # Parse clinical seizures
        clinical_matches = re.findall(r'CLINICAL SEIZURES?: (\d+)', output)
        clinical_count = int(clinical_matches[0]) if clinical_matches else 0
        
        return {
            'success': True,
            'mode': 'deep',
            'failed_seizures_count': failed_count,
            'clinical_seizures_count': clinical_count,
            'raw_output': output
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Analysis timeout (10 minutes)'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fetch', methods=['POST'])
def fetch_from_url():
    """Fetch EDF file from URL and analyze"""
    data = request.get_json()
    url = data.get('url')
    mode = data.get('mode', 'quick')
    patient_id = data.get('patient_id', 'url_fetch')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    if not url.endswith('.edf'):
        return jsonify({'error': 'URL must point to an .edf file'}), 400
    
    job_id = str(uuid.uuid4())[:12]
    filepath = UPLOAD_FOLDER / f"{job_id}_fetched.edf"
    
    jobs[job_id] = {
        'id': job_id,
        'status': 'downloading',
        'progress': 0,
        'mode': mode,
        'url': url,
        'patient_id': patient_id,
        'created_at': datetime.now().isoformat()
    }
    
    def download_and_analyze():
        try:
            # Download file
            jobs[job_id]['status'] = 'downloading'
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        jobs[job_id]['progress'] = int(30 * downloaded / total_size)
            
            jobs[job_id]['progress'] = 30
            jobs[job_id]['status'] = 'analyzing'
            
            # Run analysis
            if mode == 'quick':
                result = run_trinity_quick(filepath, patient_id, job_id)
            else:
                result = run_trinity_deep(filepath, patient_id, job_id)
            
            if result['success']:
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
            # Cleanup
            try:
                filepath.unlink()
            except:
                pass
    
    thread = threading.Thread(target=download_and_analyze)
    thread.start()
    
    return jsonify({'job_id': job_id})

@app.route('/upload', methods=['POST'])
def upload_file():
    """Upload and analyze local EDF file"""
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
    
    jobs[job_id] = {
        'id': job_id,
        'status': 'analyzing',
        'progress': 30,
        'mode': mode,
        'filename': filename,
        'patient_id': patient_id,
        'created_at': datetime.now().isoformat()
    }
    
    def analyze():
        try:
            jobs[job_id]['progress'] = 50
            if mode == 'quick':
                result = run_trinity_quick(filepath, patient_id, job_id)
            else:
                result = run_trinity_deep(filepath, patient_id, job_id)
            
            if result['success']:
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
    
    thread = threading.Thread(target=analyze)
    thread.start()
    
    return jsonify({'job_id': job_id})

@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    response = {
        'status': job['status'],
        'progress': job.get('progress', 0),
        'mode': job.get('mode', 'quick')
    }
    
    if job['status'] == 'completed':
        response['result'] = job.get('result')
    elif job['status'] == 'failed':
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

if __name__ == '__main__':
    print("=" * 60)
    print("🧠 Trinity Web App v2.0")
    print("=" * 60)
    print("Features:")
    print("  - URL fetch from PhysioNet or any source")
    print("  - Drag & drop upload")
    print("  - Quick mode (v1.2) - Seizure prediction")
    print("  - Deep Dive (v3.1) - Failed seizure discovery")
    print("=" * 60)
    print(f"URL: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
