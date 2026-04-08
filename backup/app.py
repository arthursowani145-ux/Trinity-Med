#!/usr/bin/env python3
"""
Trinity-Med Web Application
Seizure Prediction & Failed Seizure Detection
"""

import os
import uuid
import json
import subprocess
import re
from datetime import datetime
from pathlib import Path
from threading import Thread
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Configuration
BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_FOLDER = BASE_DIR / 'uploads'
RESULTS_FOLDER = BASE_DIR / 'data' / 'results'

for folder in [UPLOAD_FOLDER, RESULTS_FOLDER]:
    folder.mkdir(parents=True, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Job storage
jobs = {}

# Tool paths
TRINITY_QUICK = BASE_DIR / 'tools' / 'trinity_research_v1.2_fixed.py'
TRINITY_DEEP = BASE_DIR / 'tools' / 'batch_failed_seizure_detector_v3.1.py'

def run_trinity_quick(filepath, patient_id):
    """Run quick prediction (v1.2)"""
    try:
        cmd = [
            'python', str(TRINITY_QUICK),
            '--path', str(filepath.parent),
            '--patient', patient_id
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = result.stdout
        
        # Parse results
        seizure_files = re.findall(r'📁 (chb\d+_\d+.*?\.edf)', output)
        lead_times = re.findall(r'Lead: (\d+)s', output)
        peak_ratios = re.findall(r'Peak: ([\d,]+\.?\d*)x', output)
        
        return {
            'success': True,
            'mode': 'quick',
            'seizures_found': len(seizure_files),
            'lead_times': lead_times,
            'peak_ratios': peak_ratios,
            'raw_output': output[-3000:] if len(output) > 3000 else output
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def run_trinity_deep(filepath, patient_id):
    """Run deep dive (v3.1)"""
    try:
        cmd = [
            'python', str(TRINITY_DEEP),
            '--path', str(filepath.parent),
            '--patient', patient_id
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        output = result.stdout
        
        # Parse failed seizures
        failed_matches = re.findall(r'📁 (chb\d+_\d+.*?\.edf).*?💚 FAILED SEIZURES DETECTED', output, re.DOTALL)
        
        return {
            'success': True,
            'mode': 'deep',
            'failed_seizures_count': len(failed_matches),
            'raw_output': output[-3000:] if len(output) > 3000 else output
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/tool')
def tool():
    return render_template('tool.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400
    
    if not file.filename.endswith('.edf'):
        return jsonify({'error': 'Only .edf files are supported'}), 400
    
    mode = request.form.get('mode', 'quick')
    patient_id = request.form.get('patient_id', 'unknown')
    job_id = str(uuid.uuid4())[:12]
    
    safe_name = secure_filename(file.filename)
    filepath = UPLOAD_FOLDER / f"{job_id}_{safe_name}"
    file.save(filepath)
    
    jobs[job_id] = {
        'id': job_id,
        'status': 'queued',
        'mode': mode,
        'filename': safe_name,
        'patient_id': patient_id,
        'created_at': datetime.now().isoformat()
    }
    
    def run_analysis():
        jobs[job_id]['status'] = 'processing'
        jobs[job_id]['progress'] = 30
        
        if mode == 'quick':
            result = run_trinity_quick(filepath, patient_id)
        else:
            result = run_trinity_deep(filepath, patient_id)
        
        if result['success']:
            jobs[job_id]['result'] = result
            jobs[job_id]['status'] = 'completed'
            jobs[job_id]['progress'] = 100
        else:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = result.get('error', 'Unknown error')
        
        # Clean up file
        try:
            filepath.unlink()
        except:
            pass
    
    thread = Thread(target=run_analysis)
    thread.start()
    
    return jsonify({'job_id': job_id, 'status': 'queued'})

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

@app.route('/reviews', methods=['GET', 'POST'])
def reviews():
    reviews_file = BASE_DIR / 'data' / 'reviews.json'
    
    if request.method == 'POST':
        review = request.get_json()
        review['timestamp'] = datetime.now().isoformat()
        
        if reviews_file.exists():
            with open(reviews_file, 'r') as f:
                reviews_data = json.load(f)
        else:
            reviews_data = []
        
        reviews_data.append(review)
        
        with open(reviews_file, 'w') as f:
            json.dump(reviews_data, f, indent=2)
        
        return jsonify({'success': True})
    else:
        if reviews_file.exists():
            with open(reviews_file, 'r') as f:
                reviews_data = json.load(f)
            return jsonify({'reviews': reviews_data[-20:]})
        return jsonify({'reviews': []})

if __name__ == '__main__':
    print("=" * 60)
    print("🧠 Trinity-Med Web Application")
    print("=" * 60)
    print(f"Quick Prediction Tool: v1.2")
    print(f"Deep Dive Tool: v3.1")
    print(f"URL: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
