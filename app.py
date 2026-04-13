#!/usr/bin/env python3
"""
Trinity Web App v3.0 - CLINICAL EDITION
- Drag & drop upload
- Interactive clinical visualizations
- Professional reports in browser
"""

import os
import uuid
import json
import subprocess
import re
import zipfile
import base64
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import threading
import plotly.graph_objs as go
import plotly.utils
import numpy as np

app = Flask(__name__)
CORS(app)

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
    """Parse Trinity output and extract metrics"""
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
    
    # Extract timeline for visualization
    timeline = []
    lines = output.split('\n')
    in_timeline = False
    for line in lines:
        if 'Time     S        D        T' in line:
            in_timeline = True
            continue
        if in_timeline and line.strip() and '─' not in line and 'SEIZURE' not in line:
            parts = line.split()
            if len(parts) >= 6:
                try:
                    timeline.append({
                        'time': float(parts[0]),
                        'S': float(parts[1]),
                        'D': float(parts[2]),
                        'T': float(parts[3]),
                        'risk': float(parts[4].replace('%', '')) / 100 if '%' in parts[4] else 0
                    })
                except:
                    pass
        if 'SEIZURE AT' in line:
            in_timeline = False
    
    result['timeline'] = timeline[:50]  # Limit for performance
    return result

def generate_clinical_charts(timeline, result):
    """Generate Plotly charts for clinical display"""
    charts = {}
    
    if timeline and len(timeline) > 0:
        times = [t['time'] for t in timeline]
        
        # Risk trajectory chart
        risk_fig = go.Figure()
        risk_fig.add_trace(go.Scatter(
            x=times, y=[t['risk'] for t in timeline],
            mode='lines', name='Risk Level',
            line=dict(color='#ef4444', width=2),
            fill='tozeroy', fillcolor='rgba(239,68,68,0.2)'
        ))
        risk_fig.update_layout(
            title='Seizure Risk Trajectory',
            xaxis_title='Time (seconds)',
            yaxis_title='Risk Level',
            template='plotly_dark',
            height=300,
            margin=dict(l=40, r=40, t=40, b=40)
        )
        charts['risk_chart'] = json.dumps(risk_fig, cls=plotly.utils.PlotlyJSONEncoder)
        
        # S-D-T components chart
        sdt_fig = go.Figure()
        sdt_fig.add_trace(go.Scatter(x=times, y=[t['S'] for t in timeline], mode='lines', name='S (Background)', line=dict(color='#60a5fa')))
        sdt_fig.add_trace(go.Scatter(x=times, y=[t['D'] for t in timeline], mode='lines', name='D (Evolution)', line=dict(color='#f59e0b')))
        sdt_fig.add_trace(go.Scatter(x=times, y=[t['T'] for t in timeline], mode='lines', name='T (Coupling)', line=dict(color='#22c55e')))
        sdt_fig.update_layout(
            title='S-D-T Component Dynamics',
            xaxis_title='Time (seconds)',
            yaxis_title='Normalized Value',
            template='plotly_dark',
            height=300,
            margin=dict(l=40, r=40, t=40, b=40)
        )
        charts['sdt_chart'] = json.dumps(sdt_fig, cls=plotly.utils.PlotlyJSONEncoder)
    
    # Risk gauge (for quick mode)
    if result.get('seizures_found', 0) > 0:
        risk_level = min(100, int(result.get('peak_ratios', [0])[0]) // 100) if result.get('peak_ratios') else 0
    else:
        risk_level = result.get('failed_seizures_count', 0) * 5 if result.get('failed_seizures_count', 0) > 0 else 5
    
    gauge_fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=risk_level,
        title={'text': "Clinical Risk Index"},
        domain={'x': [0, 1], 'y': [0, 1]},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1},
            'bar': {'color': "#a855f7"},
            'steps': [
                {'range': [0, 20], 'color': "rgba(34,197,94,0.3)"},
                {'range': [20, 50], 'color': "rgba(234,179,8,0.3)"},
                {'range': [50, 80], 'color': "rgba(245,158,11,0.3)"},
                {'range': [80, 100], 'color': "rgba(239,68,68,0.3)"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': risk_level
            }
        }
    ))
    gauge_fig.update_layout(height=250, margin=dict(l=40, r=40, t=40, b=40))
    charts['gauge_chart'] = json.dumps(gauge_fig, cls=plotly.utils.PlotlyJSONEncoder)
    
    return charts

def generate_clinical_report_html(result, charts):
    """Generate HTML clinical report"""
    if result['mode'] == 'quick':
        severity = "HIGH" if result.get('seizures_found', 0) > 0 else "LOW"
        severity_color = "#ef4444" if severity == "HIGH" else "#22c55e"
        clinical_text = f"""
        <div style="background: rgba(0,0,0,0.3); padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;">
            <h4 style="color: #60a5fa;">Clinical Interpretation</h4>
            <p><strong>Seizure Risk:</strong> <span style="color: {severity_color};">{severity}</span></p>
            <p><strong>Seizures Predicted:</strong> {result.get('seizures_found', 0)}</p>
            <p><strong>Lead Times:</strong> {', '.join(result.get('lead_times', []))} seconds</p>
            <p><strong>Peak Emergence Ratio:</strong> {result.get('peak_ratios', ['—'])[0]}x baseline</p>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 0.5rem 0;">
            <p><strong>Recommendation:</strong> {("IMMEDIATE ATTENTION - Seizure imminent" if result.get('seizures_found', 0) > 0 else "Continue routine monitoring")}</p>
        </div>
        """
    else:
        ratio = result.get('failed_seizures_count', 0) / max(1, result.get('clinical_seizures_count', 1))
        clinical_text = f"""
        <div style="background: rgba(0,0,0,0.3); padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;">
            <h4 style="color: #60a5fa;">Clinical Interpretation</h4>
            <p><strong>Self-Correction Ratio:</strong> {ratio:.1f}:1 (failed:clinical)</p>
            <p><strong>Failed Seizures (Self-Corrected):</strong> <span style="color: #22c55e;">{result.get('failed_seizures_count', 0)}</span></p>
            <p><strong>Clinical Seizures:</strong> <span style="color: #ef4444;">{result.get('clinical_seizures_count', 0)}</span></p>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 0.5rem 0;">
            <p><strong>Interpretation:</strong> The brain successfully self-corrected {result.get('failed_seizures_count', 0)} times. For every clinical seizure, the brain prevented {ratio:.0f} seizures on its own.</p>
            <p><strong>Recommendation:</strong> Reinforce natural self-correction mechanisms through closed-loop neuromodulation.</p>
        </div>
        """
    
    return clinical_text

def _find_trinity_json(patient_id, base_dir):
    import glob, os
    files = glob.glob(str(base_dir / f"trinity_{patient_id}_*.json"))
    if not files:
        files = glob.glob(str(base_dir / "trinity_*.json"))
    return max(files, key=os.path.getmtime) if files else None

def run_trinity_quick(filepath, patient_id):
    try:
        cmd = ['python', str(TRINITY_QUICK), '--path', str(filepath.parent), '--patient', patient_id]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(BASE_DIR))
        parsed = parse_trinity_output(result.stdout, 'quick')
        json_path = _find_trinity_json(patient_id, BASE_DIR)
        if json_path:
            with open(json_path) as jf:
                parsed['trinity_json'] = json.load(jf)
        return parsed
    except Exception as e:
        return {'success': False, 'error': str(e), 'mode': 'quick'}

def run_trinity_deep(filepath, patient_id):
    try:
        cmd = ['python', str(TRINITY_DEEP), '--path', str(filepath.parent), '--patient', patient_id]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(BASE_DIR))
        parsed = parse_trinity_output(result.stdout, 'deep')
        json_path = _find_trinity_json(patient_id, BASE_DIR)
        if json_path:
            with open(json_path) as jf:
                parsed['trinity_json'] = json.load(jf)
        return parsed
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
                result = run_trinity_quick(filepath, patient_id)
            else:
                result = run_trinity_deep(filepath, patient_id)
            
            if result.get('success', False):
                # Generate clinical visualizations
                timeline = result.get('timeline', [])
                charts = generate_clinical_charts(timeline, result)
                clinical_report = generate_clinical_report_html(result, charts)
                
                jobs[job_id]['result'] = result
                jobs[job_id]['charts'] = charts
                jobs[job_id]['clinical_report'] = clinical_report
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

@app.route('/upload_batch', methods=['POST'])
def upload_batch():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.zip'):
        return jsonify({'error': 'Only .zip files are supported for batch processing'}), 400
    
    mode = request.form.get('mode', 'quick')
    patient_id = request.form.get('patient_id', 'batch')
    job_id = str(uuid.uuid4())[:12]
    
    zip_filename = secure_filename(file.filename)
    zip_path = UPLOAD_FOLDER / f"{job_id}_{zip_filename}"
    file.save(zip_path)
    
    extract_dir = UPLOAD_FOLDER / f"{job_id}_extracted"
    extract_dir.mkdir(exist_ok=True)
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_dir)
    
    edf_files = []
    for ext in ALLOWED_EXTENSIONS:
        edf_files.extend(extract_dir.glob(f'*{ext}'))
        edf_files.extend(extract_dir.glob(f'*{ext.upper()}'))
    edf_files = sorted(set(edf_files))
    
    jobs[job_id] = {
        'id': job_id,
        'status': 'analyzing',
        'progress': 0,
        'mode': mode,
        'batch': True,
        'total_files': len(edf_files),
        'files': [str(f) for f in edf_files],
        'patient_id': patient_id,
        'created_at': datetime.now().isoformat(),
        'results': []
    }
    
    def analyze_batch():
        results = []
        for i, filepath in enumerate(edf_files):
            jobs[job_id]['progress'] = int((i / len(edf_files)) * 100)
            jobs[job_id]['current_file'] = filepath.name
            
            if mode == 'quick':
                result = run_trinity_quick(filepath, patient_id)
            else:
                result = run_trinity_deep(filepath, patient_id)
            
            results.append({'file': filepath.name, 'result': result})
            jobs[job_id]['results'] = results
        
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['progress'] = 100
        
        try:
            zip_path.unlink()
            import shutil
            shutil.rmtree(extract_dir)
        except:
            pass
    
    thread = threading.Thread(target=analyze_batch)
    thread.start()
    
    return jsonify({'job_id': job_id, 'total_files': len(edf_files)})

@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    response = {
        'status': job['status'],
        'progress': job.get('progress', 0),
        'mode': job.get('mode', 'quick'),
        'batch': job.get('batch', False)
    }
    
    if job.get('batch'):
        response['total_files'] = job.get('total_files', 0)
        response['current_file'] = job.get('current_file', '')
        if job['status'] == 'completed':
            response['results'] = job.get('results', [])
    else:
        if job['status'] == 'completed':
            response['result'] = job.get('result')
            response['charts'] = job.get('charts', {})
            response['clinical_report'] = job.get('clinical_report', '')
    
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
        json.dump(job.get('result', job.get('results', {})), f, indent=2)
    
    return send_file(result_file, as_attachment=True, download_name=f"trinity_{job_id}.json")

# main block moved to end of file

@app.route('/analyze_path', methods=['POST'])
def analyze_path():
    """Analyze file from local path (for manual entry)"""
    data = request.get_json()
    filepath = data.get('filepath')
    mode = data.get('mode', 'quick')
    patient_id = data.get('patient_id', 'local')
    
    if not filepath:
        return jsonify({'error': 'No file path provided'}), 400
    
    path = Path(filepath)
    if not path.exists():
        return jsonify({'error': f'File not found: {filepath}'}), 404
    
    if not allowed_file(path.name):
        return jsonify({'error': f'Unsupported format. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    job_id = str(uuid.uuid4())[:12]
    
    jobs[job_id] = {
        'id': job_id,
        'status': 'analyzing',
        'progress': 30,
        'mode': mode,
        'filename': path.name,
        'filepath': str(path),
        'patient_id': patient_id,
        'created_at': datetime.now().isoformat()
    }
    
    def analyze():
        try:
            jobs[job_id]['progress'] = 50
            if mode == 'quick':
                result = run_trinity_quick(path, patient_id)
            else:
                result = run_trinity_deep(path, patient_id)
            
            if result.get('success', False):
                timeline = result.get('timeline', [])
                charts = generate_clinical_charts(timeline, result)
                clinical_report = generate_clinical_report_html(result, charts)
                
                jobs[job_id]['result'] = result
                jobs[job_id]['charts'] = charts
                jobs[job_id]['clinical_report'] = clinical_report
                jobs[job_id]['status'] = 'completed'
                jobs[job_id]['progress'] = 100
            else:
                jobs[job_id]['status'] = 'failed'
                jobs[job_id]['error'] = result.get('error', 'Analysis failed')
        except Exception as e:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)
    
    thread = threading.Thread(target=analyze)
    thread.start()
    
    return jsonify({'job_id': job_id})

@app.route('/clinical_graph/<job_id>')
def clinical_graph(job_id):
    """Generate and return clinical graph as PNG"""
    if job_id not in jobs:
        return "Job not found", 404
    
    job = jobs[job_id]
    if job['status'] != 'completed':
        return "Analysis not complete", 400
    
    # Import graph generator
    import sys
    sys.path.insert(0, str(BASE_DIR / 'tools'))
    from trinity_clinical_graphs import generate_single_file_figure, generate_batch_overview
    
    # Create temp file for graph
    graph_path = RESULTS_FOLDER / f"{job_id}_clinical.png"
    
    if job.get('batch'):
        # Batch overview
        generate_batch_overview(job.get('results', []), None, str(graph_path))
    else:
        # Single file
        result = job.get('result', {})
        timeline = result.get('timeline', [])
        if timeline:
            # Create fake result dict for graph
            graph_result = {
                'file': job.get('filename', 'unknown'),
                'timeline': timeline,
                'seizure_at_sec': result.get('seizure_at_sec'),
                'peak_ratio': result.get('peak_ratio')
            }
            generate_single_file_figure(graph_result, str(graph_path))
        else:
            return "No timeline data for graph", 404
    
    return send_file(graph_path, mimetype='image/png')

@app.route('/clinical_report_text/<job_id>')
def clinical_report_text(job_id):
    """Generate clinical text report"""
    if job_id not in jobs:
        return "Job not found", 404
    
    job = jobs[job_id]
    if job['status'] != 'completed':
        return "Analysis not complete", 400
    
    # Import clinical translator
    import sys
    sys.path.insert(0, str(BASE_DIR / 'tools'))
    from trinity_clinical_translator_v21 import ClinicalReportGenerator
    
    if job.get('batch'):
        first = job.get('results', [{}])[0].get('result', {})
        trinity_json = first.get('trinity_json', [{}])
        item = trinity_json[0] if isinstance(trinity_json, list) else trinity_json
        report = ClinicalReportGenerator.generate_clinical_summary(item)
    else:
        result = job.get('result', {})
        trinity_json = result.get('trinity_json')
        if trinity_json:
            item = trinity_json[0] if isinstance(trinity_json, list) else trinity_json
        else:
            item = result
            item['file'] = job.get('filename', 'unknown')
        report = ClinicalReportGenerator.generate_clinical_summary(item)
    
    return jsonify({'report': report})

@app.route('/debug/<job_id>')
def debug_job(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'not found'}), 404
    job = jobs[job_id]
    result = job.get('result', {})
    return jsonify({
        'result_keys': list(result.keys()),
        'has_trinity_json': 'trinity_json' in result,
        'trinity_json_type': type(result.get('trinity_json')).__name__,
        'trinity_json_len': len(result.get('trinity_json', [])) if isinstance(result.get('trinity_json'), list) else 'n/a',
        'status': job.get('status'),
    })

if __name__ == '__main__':
    print("=" * 60)
    print("🧠 Trinity Web App v3.0 - CLINICAL EDITION")
    print("=" * 60)
    print(f"URL: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
