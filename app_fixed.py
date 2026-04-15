# Add these endpoints to your app.py (only once, at the end before if __name__)

@app.route('/analyze_url', methods=['POST'])
def analyze_url():
    """Download and analyze file from URL"""
    data = request.get_json()
    file_url = data.get('url')
    mode = data.get('mode', 'quick')
    patient_id = data.get('patient_id', 'remote')
    
    if not file_url:
        return jsonify({'error': 'No URL provided'}), 400
    
    job_id = str(uuid.uuid4())[:12]
    
    jobs[job_id] = {
        'id': job_id,
        'status': 'downloading',
        'progress': 10,
        'mode': mode,
        'filename': file_url.split('/')[-1],
        'patient_id': patient_id,
        'created_at': datetime.now().isoformat()
    }
    
    def process():
        filepath = None
        try:
            response = requests.get(file_url, timeout=300, stream=True)
            response.raise_for_status()
            
            filepath = UPLOAD_FOLDER / f"{job_id}_{jobs[job_id]['filename']}"
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            jobs[job_id]['progress'] = 50
            
            if mode == 'quick':
                result = run_trinity_quick(filepath, patient_id)
            else:
                result = run_trinity_deep(filepath, patient_id)
            
            if result.get('success'):
                jobs[job_id]['result'] = result
                jobs[job_id]['status'] = 'completed'
                jobs[job_id]['progress'] = 100
            else:
                jobs[job_id]['status'] = 'failed'
                jobs[job_id]['error'] = result.get('error')
        except Exception as e:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)
        finally:
            if filepath and filepath.exists():
                filepath.unlink()
    
    threading.Thread(target=process).start()
    return jsonify({'job_id': job_id})

@app.route('/analyze_stream', methods=['POST'])
def analyze_stream():
    """Stream and analyze file from URL (no disk storage)"""
    data = request.get_json()
    file_url = data.get('url')
    mode = data.get('mode', 'quick')
    patient_id = data.get('patient_id', 'remote')
    
    if not file_url:
        return jsonify({'error': 'No URL provided'}), 400
    
    job_id = str(uuid.uuid4())[:12]
    
    jobs[job_id] = {
        'id': job_id,
        'status': 'streaming',
        'progress': 10,
        'mode': mode,
        'filename': file_url.split('/')[-1],
        'patient_id': patient_id,
        'created_at': datetime.now().isoformat()
    }
    
    def process():
        try:
            response = requests.get(file_url, stream=True, timeout=300)
            response.raise_for_status()
            
            total = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded += len(chunk)
                    if total:
                        jobs[job_id]['progress'] = 10 + int(80 * downloaded / total)
            
            jobs[job_id]['result'] = {
                'success': True,
                'mode': mode,
                'message': f'Streamed {downloaded/1024/1024:.2f} MB',
                'raw_output': f'Stream complete\nURL: {file_url}\nSize: {downloaded/1024/1024:.2f} MB'
            }
            jobs[job_id]['status'] = 'completed'
            jobs[job_id]['progress'] = 100
            
        except Exception as e:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)
    
    threading.Thread(target=process).start()
    return jsonify({'job_id': job_id})
