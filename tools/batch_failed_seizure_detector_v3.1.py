#!/usr/bin/env python3
"""
BATCH FAILED SEIZURE DETECTOR v3.1
TWO-TIER DETECTION:
  Tier 1: Absolute elevation (catches noisy but real transitions)
  Tier 2: Sustained alignment (catches clean, stable transitions)
"""

import numpy as np
import pyedflib
import sys
import json
import re
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

def compute_baseline(data, fs, quiet_start=300, quiet_end=330):
    """Compute baseline S, D, T from a quiet period (default: 300-330s)"""
    start_sample = int(quiet_start * fs)
    end_sample = int(quiet_end * fs)
    
    n_channels = data.shape[0]
    window_data = data[:, start_sample:end_sample]
    
    channel_vars = [np.var(window_data[ch, :]) for ch in range(n_channels)]
    S = np.std(channel_vars)
    D = np.mean(np.abs(np.diff(channel_vars))) if len(channel_vars) > 1 else 0
    T = np.mean(np.abs(np.gradient(channel_vars))) if len(channel_vars) > 1 else 0
    
    return S, D, T

def analyze_single_edf(filepath, seizure_times=None):
    """Analyze single EDF file with TWO-TIER detection"""
    try:
        f = pyedflib.EdfReader(str(filepath))
        n_channels = min(f.signals_in_file, 23)
        fs = int(f.getSampleFrequency(0))
        n_samples = int(f.getNSamples()[0])
        
        # Read all data
        data = np.zeros((n_channels, n_samples))
        for i in range(n_channels):
            data[i, :] = f.readSignal(i)
        f.close()
        
        # Compute baseline from quiet period (300-330s)
        baseline_S, baseline_D, baseline_T = compute_baseline(data, fs)
        
        # Compute emergence over time
        window_sec = 2
        window_samples = int(window_sec * fs)
        step_samples = window_samples // 2
        n_windows = (n_samples - window_samples) // step_samples + 1
        
        times = []
        emergences = []
        s_proxies = []
        d_proxies = []
        t_proxies = []
        
        for i in range(n_windows):
            start = i * step_samples
            end = start + window_samples
            window = data[:, start:end]
            
            channel_vars = [np.var(window[ch, :]) for ch in range(n_channels)]
            S = np.std(channel_vars)
            D = np.mean(np.abs(np.diff(channel_vars))) if len(channel_vars) > 1 else 0
            T = abs(np.gradient(channel_vars)).mean() if len(channel_vars) > 1 else 0
            
            emergence = S * D * T
            
            emergences.append(emergence)
            s_proxies.append(S)
            d_proxies.append(D)
            t_proxies.append(T)
            times.append(start / fs)
        
        emergences = np.array(emergences)
        times = np.array(times)
        
        # Calculate peak ratio
        baseline_emergence = np.percentile(emergences[emergences > 0], 20) if len(emergences[emergences > 0]) > 0 else 1
        peak_ratio = max(emergences) / baseline_emergence if baseline_emergence > 0 else 1
        
        # Find sustained high emergence
        threshold = np.percentile(emergences, 70)
        high_mask = emergences > threshold
        
        # Find sustained periods (>30 seconds)
        sustained_periods = []
        in_period = False
        start_idx = 0
        
        for i, is_high in enumerate(high_mask):
            if is_high and not in_period:
                in_period = True
                start_idx = i
            elif not is_high and in_period:
                in_period = False
                duration = times[i-1] - times[start_idx]
                if duration > 30:
                    s_period = s_proxies[start_idx:i]
                    d_period = d_proxies[start_idx:i]
                    t_period = t_proxies[start_idx:i]
                    
                    # TIER 1: Absolute elevation (catches noisy transitions like chb02_30)
                    is_elevated = (
                        np.mean(s_period) > baseline_S * 10 and
                        np.mean(d_period) > baseline_D * 10 and
                        np.mean(t_period) > baseline_T * 10
                    )
                    
                    # TIER 2: Sustained alignment (catches clean transitions like chb02_01)
                    if len(s_period) > 2 and np.std(s_period) > 0:
                        corr_sd = abs(np.corrcoef(s_period, d_period)[0,1])
                        corr_st = abs(np.corrcoef(s_period, t_period)[0,1])
                        corr_dt = abs(np.corrcoef(d_period, t_period)[0,1])
                        avg_corr = (corr_sd + corr_st + corr_dt) / 3
                    else:
                        avg_corr = 0
                    
                    s_mean_norm = np.mean(s_period) / (np.std(s_period) + 1) if np.std(s_period) > 0 else 0
                    d_mean_norm = np.mean(d_period) / (np.std(d_period) + 1) if np.std(d_period) > 0 else 0
                    t_mean_norm = np.mean(t_period) / (np.std(t_period) + 1) if np.std(t_period) > 0 else 0
                    
                    is_aligned = (s_mean_norm > 0.5 and d_mean_norm > 0.5 and t_mean_norm > 0.5) and avg_corr > 0.6
                    
                    # FAILED SEIZURE if EITHER tier passes
                    is_failed_period = is_elevated or is_aligned
                    
                    sustained_periods.append({
                        'start': float(times[start_idx]),
                        'end': float(times[i-1]),
                        'duration': float(duration),
                        'peak_emergence': float(max(emergences[start_idx:i])),
                        'is_elevated': bool(is_elevated),
                        'is_aligned': bool(is_aligned),
                        'is_failed': bool(is_failed_period),
                        's_mean': float(np.mean(s_period)),
                        'd_mean': float(np.mean(d_period)),
                        't_mean': float(np.mean(t_period)),
                        'baseline_S': float(baseline_S),
                        'baseline_D': float(baseline_D),
                        'baseline_T': float(baseline_T),
                        'alignment_score': float(avg_corr)
                    })
        
        # Check for clinical seizure
        has_clinical_seizure = False
        if seizure_times:
            for sz_time in seizure_times:
                if sz_time < times[-1]:
                    has_clinical_seizure = True
                    break
        
        # Determine failed seizure (any period that is failed)
        true_failed_periods = [p for p in sustained_periods if p['is_failed']]
        is_failed_seizure = (not has_clinical_seizure and len(true_failed_periods) > 0)
        
        return {
            'filename': str(Path(filepath).name),
            'peak_ratio': float(peak_ratio),
            'has_clinical_seizure': bool(has_clinical_seizure),
            'is_failed_seizure': bool(is_failed_seizure),
            'failed_periods': true_failed_periods,
            'sustained_periods': sustained_periods,
            'duration_sec': float(n_samples / fs),
            'baseline': {
                'S': float(baseline_S),
                'D': float(baseline_D),
                'T': float(baseline_T)
            }
        }
        
    except Exception as e:
        return {
            'filename': str(Path(filepath).name), 
            'error': str(e),
            'is_failed_seizure': False,
            'has_clinical_seizure': False
        }

def parse_seizure_summary(summary_path):
    """Parse CHB-MIT summary file"""
    seizures = {}
    if not Path(summary_path).exists():
        return seizures
    
    with open(summary_path) as f:
        content = f.read()
    
    current_file = None
    for line in content.split('\n'):
        if 'File Name:' in line:
            current_file = line.split(':')[-1].strip()
            seizures[current_file] = []
        elif 'Seizure Start Time:' in line and current_file:
            nums = re.findall(r'\d+', line)
            if nums:
                seizures[current_file].append(int(nums[0]))
    return seizures

def analyze_patient(data_path, patient_id=None, max_workers=4):
    """Batch analyze all EDF files"""
    data_path = Path(data_path)
    
    print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}  🔍 BATCH FAILED SEIZURE DETECTOR v3.1{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"  Data path: {data_path}")
    print(f"  Method: TWO-TIER detection")
    print(f"    Tier 1: Absolute elevation (>10x baseline)")
    print(f"    Tier 2: Sustained alignment (>0.6 correlation)")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n")
    
    # Find seizure annotations
    summary_path = data_path / f"{patient_id}-summary.txt" if patient_id else data_path / "summary.txt"
    if not summary_path.exists():
        summary_path = data_path / "summary.txt"
    
    seizures = parse_seizure_summary(summary_path)
    print(f"📋 Found seizure annotations for {len(seizures)} files\n")
    
    # Find all EDF files
    edf_files = sorted(data_path.glob("*.edf"))
    print(f"📁 Found {len(edf_files)} EDF files\n")
    
    # Analyze files
    results = []
    try:
        from tqdm import tqdm
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm", "-q"])
        from tqdm import tqdm
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for edf in edf_files:
            sz_times = seizures.get(edf.name, [])
            futures[executor.submit(analyze_single_edf, edf, sz_times)] = edf.name
        
        for future in tqdm(as_completed(futures), total=len(futures), desc="Analyzing EDF files"):
            result = future.result()
            results.append(result)
    
    # Categorize results
    failed_seizures = [r for r in results if r.get('is_failed_seizure', False)]
    clinical_seizures = [r for r in results if r.get('has_clinical_seizure', False)]
    ied_clusters = [r for r in results if not r.get('has_clinical_seizure', False) and not r.get('is_failed_seizure', False) and r.get('sustained_periods')]
    normal = [r for r in results if not r.get('has_clinical_seizure', False) and not r.get('is_failed_seizure', False) and not r.get('sustained_periods') and 'error' not in r]
    errors = [r for r in results if 'error' in r]
    
    # Display failed seizures
    if failed_seizures:
        print(f"\n{Colors.GREEN}{'='*70}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.GREEN}  💚 TRUE FAILED SEIZURES DETECTED ({len(failed_seizures)} files){Colors.RESET}")
        print(f"{Colors.GREEN}{'='*70}{Colors.RESET}")
        
        for fs in failed_seizures:
            print(f"\n  {Colors.GREEN}📁 {fs['filename']}{Colors.RESET}")
            print(f"  {'─'*60}")
            print(f"  📊 Peak ratio: {fs['peak_ratio']:.1f}x")
            
            for p in fs.get('failed_periods', [])[:3]:
                print(f"\n  ⏱️  FAILED SEIZURE PERIOD:")
                print(f"     Time: {p['start']:.0f}s → {p['end']:.0f}s")
                print(f"     Duration: {p['duration']:.0f} seconds")
                print(f"     Detection: {'ELEVATED' if p['is_elevated'] else ''} {'ALIGNED' if p['is_aligned'] else ''}".strip())
                if p['is_elevated']:
                    print(f"     S: {p['s_mean']:.0f} (baseline {p['baseline_S']:.0f}) = {p['s_mean']/p['baseline_S']:.1f}x")
                    print(f"     D: {p['d_mean']:.0f} (baseline {p['baseline_D']:.0f}) = {p['d_mean']/p['baseline_D']:.1f}x")
                    print(f"     T: {p['t_mean']:.0f} (baseline {p['baseline_T']:.0f}) = {p['t_mean']/p['baseline_T']:.1f}x")
            
            print(f"\n  🧠 → Brain self-corrected without seizing")
    
    # Summary
    print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}  SUMMARY{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"\n  {Colors.GREEN}💚 FAILED SEIZURES: {len(failed_seizures)}{Colors.RESET}")
    print(f"  🔴 CLINICAL SEIZURES: {len(clinical_seizures)}")
    print(f"  📈 IED CLUSTERS: {len(ied_clusters)}")
    print(f"  🟢 NORMAL BASELINE: {len(normal)}")
    if errors:
        print(f"  ⚠️ ERRORS: {len(errors)}")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}")
    
    # Save report
    report_file = data_path / f"failed_seizure_report_v3.1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    def convert_to_serializable(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        else:
            return obj
    
    report_data = {
        'timestamp': datetime.now().isoformat(),
        'total_files': len(results),
        'failed_seizures': [
            {
                'filename': fs['filename'],
                'peak_ratio': convert_to_serializable(fs['peak_ratio']),
                'failed_periods': [
                    {
                        'start': convert_to_serializable(p['start']),
                        'end': convert_to_serializable(p['end']),
                        'duration': convert_to_serializable(p['duration']),
                        'detection_method': 'ELEVATED' if p['is_elevated'] else 'ALIGNED'
                    }
                    for p in fs.get('failed_periods', [])
                ]
            }
            for fs in failed_seizures
        ]
    }
    
    with open(report_file, 'w') as f:
        json.dump(report_data, f, indent=2, default=convert_to_serializable)
    
    print(f"\n💾 Report saved: {report_file}")
    print(f"✅ Analysis complete.\n")
    
    return failed_seizures

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--path', '-p', required=True, help='Path to EDF files')
    parser.add_argument('--patient', '-id', help='Patient ID')
    args = parser.parse_args()
    
    analyze_patient(args.path, args.patient)
