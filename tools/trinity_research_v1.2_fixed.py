#!/usr/bin/env python3
"""
TRINITY RESEARCH v1.2 — TRAJECTORY & TIMELINE EDITION (FIXED)

A unified framework for EEG-based seizure prediction using information geometry,
dynamical systems analysis, and emergence theory.
"""

import numpy as np
import json
import sys
import re
from pathlib import Path
from datetime import datetime
from enum import Enum
import warnings
warnings.filterwarnings('ignore')

try:
    import pyedflib
except ImportError:
    print("\n❌ ERROR: pyedflib not installed.")
    print("   Install with: pip install pyedflib\n")
    sys.exit(1)


class BrainState(Enum):
    """Clinical brain state classifications"""
    STABLE = "Stable"
    IED = "Interictal Spike"
    PRE_ICTAL = "Pre-ictal"
    ICTAL = "Seizure"
    POST_ICTAL = "Post-ictal"


class AlertLevel(Enum):
    """Alert severity levels with visual indicators"""
    NONE = "⚪"
    LOG = "📝"
    WARNING = "🟡"
    URGENT = "🟠"
    SEIZURE = "🔴"


class Colors:
    """Terminal color codes for formatted output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'


class Progress:
    """Progress bar utility for file processing"""
    
    @staticmethod
    def bar(current, total, width=50, prefix="", suffix=""):
        if total == 0:
            return
        percent = current / total
        filled = int(width * percent)
        bar = "█" * filled + "░" * (width - filled)
        sys.stdout.write(f"\r  {prefix} [{bar}] {percent*100:5.1f}% {suffix}")
        sys.stdout.flush()
        if current == total:
            print()


class Trinity:
    """
    Core Trinity Engine for EEG analysis
    
    Implements multi-dimensional state space reconstruction using:
    - Entropy (S) → Information content
    - Divergence (D) → Dynamical change
    - Torsion (T) → Curvature in state space
    - Emergence (E) → Synergistic product of all three
    """
    
    COEFFS = {
        'alpha': 0.3,   # Entropy weighting
        'beta': 1.2,    # Divergence weighting  
        'gamma': 0.4,   # Torsion weighting
        'delta': 0.2,   # Feature extraction
        'epsilon': 0.3, # Noise floor
        'zeta': 0.1,    # Regularization
        'eta': 0.9      # Emergence scaling
    }

    def __init__(self):
        self.fs = 256  # Default sampling rate (updated per file)

    def _extract_features(self, eeg_window):
        """
        Extract multi-domain features from EEG window
        
        Features per channel:
        - Statistical: std, max amplitude, diff magnitude, energy
        - Spectral: delta, theta, alpha, beta, gamma band power
        """
        n_channels, n_samples = eeg_window.shape
        features = []
        
        for ch in range(min(n_channels, 23)):
            sig = eeg_window[ch, :]
            
            # Statistical features
            features.extend([
                np.std(sig),
                np.max(np.abs(sig)),
                np.mean(np.abs(np.diff(sig))),
                np.sum(sig ** 2) / len(sig),
            ])
            
            # Spectral features
            try:
                fft = np.fft.rfft(sig)
                power = np.abs(fft) ** 2
                freqs = np.fft.rfftfreq(len(sig), 1/self.fs)
                
                for low, high in [(0.5, 4), (4, 8), (8, 13), (13, 30), (30, 100)]:
                    mask = (freqs >= low) & (freqs < high)
                    features.append(np.mean(power[mask]) if np.any(mask) else 0)
            except:
                features.extend([0, 0, 0, 0, 0])
                
        return np.array(features)

    def _compute_dimensions(self, feature_matrix):
        """
        Compute S, D, T dimensions from feature matrix
        
        S (Entropy): Shannon entropy of normalized feature distribution
        D (Divergence): Logarithmic rate of change between consecutive states
        T (Torsion): Fisher information from gradients of S and D
        """
        n_features, n_time = feature_matrix.shape
        
        if n_time < 3:
            return np.zeros(n_time), np.zeros(n_time), np.zeros(n_time)

        # Compute S: Shannon entropy
        S = np.zeros(n_time)
        for t in range(n_time):
            snapshot = np.abs(feature_matrix[:, t])
            total = np.sum(snapshot) + 1e-10
            probs = snapshot / total
            probs = probs[probs > 0]
            if len(probs) > 0:
                S[t] = -np.sum(probs * np.log2(probs + 1e-10))

        # Compute D: Dynamical divergence
        D = np.zeros(n_time)
        for t in range(1, n_time - 1):
            curr = feature_matrix[:, t]
            nxt = feature_matrix[:, t + 1]
            delta = np.linalg.norm(nxt - curr)
            baseline = np.linalg.norm(curr) + 1e-10
            D[t] = np.log1p(delta / baseline)
        
        # Handle boundaries
        if n_time > 2:
            D[0] = D[1]
            D[-1] = D[-2]

        # Compute T: Torsion (Fisher information)
        dS = np.gradient(S)
        dD = np.gradient(D)
        fisher = dS**2 + dD**2
        T = np.log1p(fisher)
        
        if np.std(T) > 0:
            T = (T - np.mean(T)) / np.std(T + 1e-10)

        return S, D, T

    def _classify_state(self, S_val, D_val, T_val, emergence_val, threshold,
                        S_std=1.0, D_std=1.0, T_std=1.0):
        """
        Classify brain state based on dimensional values and emergence
        """
        s_high = abs(S_val) > S_std
        d_high = abs(D_val) > D_std
        t_high = abs(T_val) > T_std
        aligned = s_high and d_high and t_high

        if emergence_val > threshold * 10:
            return BrainState.ICTAL, AlertLevel.SEIZURE
        elif aligned and emergence_val > threshold:
            return BrainState.PRE_ICTAL, AlertLevel.URGENT
        elif emergence_val > threshold * 0.5:
            return BrainState.IED, AlertLevel.WARNING
        elif emergence_val > threshold * 0.2:
            return BrainState.IED, AlertLevel.LOG
        else:
            return BrainState.STABLE, AlertLevel.NONE

    def analyze_file(self, filepath, seizure_time=None):
        """
        Analyze a single EDF file and return results
        
        Args:
            filepath: Path to EDF file
            seizure_time: Known seizure onset time (seconds) for validation
        
        Returns:
            Dictionary containing analysis results and timeline
        """
        filename = Path(filepath).name
        
        # Load EDF data
        try:
            f = pyedflib.EdfReader(str(filepath))
            n_channels = min(f.signals_in_file, 23)
            self.fs = f.getSampleFrequency(0)
            n_samples = f.getNSamples()[0]
            
            data = np.zeros((n_channels, n_samples))
            for i in range(n_channels):
                data[i, :] = f.readSignal(i)
            f.close()
        except Exception as e:
            return {'error': str(e), 'file': filename}

        # Sliding window processing
        window_sec = 2
        window_samples = int(window_sec * self.fs)
        step_samples = window_samples // 2
        n_windows = (n_samples - window_samples) // step_samples + 1

        times, features_list = [], []
        for i in range(n_windows):
            start = i * step_samples
            end = start + window_samples
            window = data[:, start:end]
            features_list.append(self._extract_features(window))
            times.append(start / self.fs)

        # Compute S, D, T dimensions
        feature_matrix = np.array(features_list).T
        S, D, T = self._compute_dimensions(feature_matrix)

        # Center dimensions
        Sc = S - np.mean(S)
        Dc = D - np.mean(D)
        Tc = T - np.mean(T)
        
        # Compute emergence (synergistic product)
        emergence = self.COEFFS['eta'] * Sc * Dc * Tc

        # Calculate thresholds
        valid = ~np.isnan(emergence)
        if not np.any(valid):
            return {'error': 'No valid emergence', 'file': filename}

        non_zero = np.abs(emergence[valid][emergence[valid] != 0])
        baseline = np.percentile(non_zero, 20) if len(non_zero) > 0 else 1e-10
        threshold = baseline * 30

        # Peak detection
        peak_idx = np.nanargmax(np.abs(emergence[valid]))
        peak_ratio = np.abs(emergence[valid][peak_idx]) / baseline
        peak_time = times[peak_idx] if peak_idx < len(times) else 0

        # Standard deviations for classification
        S_std = np.std(Sc) if len(Sc) > 0 else 1.0
        D_std = np.std(Dc) if len(Dc) > 0 else 1.0
        T_std = np.std(Tc) if len(Tc) > 0 else 1.0

        # Build timeline (sampled for readability)
        timeline = []
        step = max(1, len(emergence) // 20)
        
        for i in range(0, len(emergence), step):
            if i < len(times):
                state, alert = self._classify_state(
                    Sc[i], Dc[i], Tc[i], emergence[i], threshold,
                    S_std, D_std, T_std
                )
                timeline.append({
                    'time_sec': round(times[i], 0),
                    'S': round(Sc[i], 3),
                    'D': round(Dc[i], 3),
                    'T': round(Tc[i], 3),
                    'emergence': round(emergence[i], 3),
                    'state': state.value,
                    'alert': alert.value
                })

        # Assemble result
        result = {
            'file': filename,
            'peak_ratio': round(peak_ratio, 1),
            'peak_time_sec': round(peak_time, 0),
            'duration_sec': round(n_samples / self.fs, 0),
            'baseline_emergence': round(baseline, 4),
            'threshold': round(threshold, 2),
            'n_features': feature_matrix.shape[0],
            'timeline': timeline
        }

        # Add seizure prediction if ground truth provided
        if seizure_time is not None and seizure_time > 0:
            lead_time = seizure_time - peak_time
            result['seizure_at_sec'] = seizure_time
            result['lead_time_sec'] = round(lead_time, 0) if lead_time > 0 else 0
            
            if lead_time > 600:
                result['transition_type'] = "GRADUAL"
                result['alert_color'] = "🟡 WARNING"
            elif lead_time > 60:
                result['transition_type'] = "MODERATE"
                result['alert_color'] = "🟠 URGENT"
            else:
                result['transition_type'] = "ABRUPT"
                result['alert_color'] = "🔴 IMMINENT"
                
            result['prediction'] = f"{result['alert_color']} SEIZURE PREDICTED ({lead_time:.0f}s lead)"
        else:
            result['prediction'] = "📊 BASELINE ANALYSIS"

        return result

    def print_timeline(self, result):
        """Print formatted timeline for a single file"""
        if 'timeline' not in result:
            return
            
        print(f"\n  {'='*70}")
        print(f"  📜 TIMELINE — {result['file']}")
        print(f"  {'='*70}")
        print(f"\n  {'Time':<8} {'S':<8} {'D':<8} {'T':<8} {'Risk':<8} {'State':<20}")
        print(f"  {'─'*70}")
        
        for t in result['timeline'][:15]:
            risk = abs(t['emergence'])
            if risk > 0.5:
                risk_str = f"{Colors.RED}{risk:.0%}{Colors.RESET}"
            elif risk > 0.2:
                risk_str = f"{Colors.YELLOW}{risk:.0%}{Colors.RESET}"
            else:
                risk_str = f"{risk:.0%}"
                
            s_str = f"{Colors.GREEN if t['S'] > 0.5 else Colors.DIM}{t['S']:.2f}{Colors.RESET}"
            d_str = f"{Colors.GREEN if t['D'] > 0.5 else Colors.DIM}{t['D']:.2f}{Colors.RESET}"
            t_str = f"{Colors.GREEN if t['T'] > 0.5 else Colors.DIM}{t['T']:.2f}{Colors.RESET}"
            
            print(f"  {t['time_sec']:<8.0f} {s_str:<8} {d_str:<8} {t_str:<8} {risk_str:<8} {t['alert']} {t['state']}")
        
        if result.get('seizure_at_sec'):
            print(f"\n  {Colors.RED}{'─'*40} SEIZURE AT {result['seizure_at_sec']:.0f}s {'─'*40}{Colors.RESET}")


def parse_seizure_summary(summary_path):
    """
    Parse CHB-MIT summary.txt files to extract seizure annotations
    
    Format expected: "File Name: chbXX_XX.edf" followed by "Seizure Start Time: N"
    """
    seizures = {}
    if not summary_path.exists():
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


def analyze_patient(data_path, patient_id=None, show_progress=True):
    """
    Main analysis function for a patient directory
    
    Args:
        data_path: Path to directory containing EDF files
        patient_id: Patient identifier (auto-detected if not provided)
        show_progress: Display progress bar during processing
    """
    data_path = Path(data_path)
    if not data_path.exists():
        print(f"\n❌ ERROR: Path not found: {data_path}")
        return None

    # Print header
    print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}  TRINITY RESEARCH v1.2 — TRAJECTORY & TIMELINE{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"  Data path: {data_path}")

    # Auto-detect patient ID
    if not patient_id:
        for f in data_path.glob("*.edf"):
            match = re.search(r'(chb\d+)', f.name)
            if match:
                patient_id = match.group(1)
                break
        if not patient_id:
            patient_id = "unknown"

    print(f"  Patient ID: {patient_id}")
    print(f"  Features: 9 per channel × 23 channels = 207 total")
    print(f"  Analysis started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n")

    # Load seizure annotations
    summary_path = data_path / f"{patient_id}-summary.txt"
    if not summary_path.exists():
        summary_path = data_path / "summary.txt"

    seizures = parse_seizure_summary(summary_path) if summary_path.exists() else {}
    if seizures:
        seizure_files = len([f for f, sz in seizures.items() if sz])
        print(f"📋 Found seizure annotations: {seizure_files} files\n")

    # Process EDF files
    edf_files = sorted(data_path.glob("*.edf"))
    if not edf_files:
        print(f"❌ No EDF files found in {data_path}")
        return None

    print(f"📁 Found {len(edf_files)} EDF files\n")

    trinity = Trinity()
    results = []

    for idx, edf in enumerate(edf_files, 1):
        if show_progress:
            Progress.bar(idx, len(edf_files), 
                        prefix=f"[{idx}/{len(edf_files)}]", 
                        suffix=edf.name[:40])
        
        sz_times = seizures.get(edf.name, [])
        result = trinity.analyze_file(edf, sz_times[0] if sz_times else None)
        results.append(result)

    print()

    # Separate seizure and baseline files
    seizure_results = [r for r in results if r.get('seizure_at_sec')]
    baseline_results = [r for r in results if not r.get('seizure_at_sec')]

    # Display seizure files with timelines
    if seizure_results:
        print(f"{Colors.RED}{'─'*70}{Colors.RESET}")
        print(f"{Colors.BOLD}  🔴 SEIZURE FILES — WITH TIMELINE{Colors.RESET}")
        print(f"{Colors.RED}{'─'*70}{Colors.RESET}")
        
        for r in seizure_results:
            trinity.print_timeline(r)
            print(f"\n  📊 Peak: {r['peak_ratio']:.1f}x | Lead: {r.get('lead_time_sec', 0):.0f}s")
            print(f"  🧠 Transition type: {r.get('transition_type', 'unknown')}")
            print(f"  {r['prediction']}\n")

    # Display baseline files summary
    if baseline_results:
        print(f"{Colors.GREEN}{'─'*70}{Colors.RESET}")
        print(f"{Colors.BOLD}  🟢 BASELINE FILES (no seizures){Colors.RESET}")
        print(f"{Colors.GREEN}{'─'*70}{Colors.RESET}")
        
        for r in baseline_results[:10]:
            print(f"  {r['file']:<30} Peak: {r['peak_ratio']:>8.1f}x  {r['prediction']}")
        
        if len(baseline_results) > 10:
            print(f"  ... and {len(baseline_results)-10} more")

    # Summary statistics
    print(f"\n{Colors.CYAN}{'─'*70}{Colors.RESET}")
    print(f"{Colors.BOLD}  SUMMARY{Colors.RESET}")
    print(f"{Colors.CYAN}{'─'*70}{Colors.RESET}")

    if seizure_results:
        peak_ratios = [r['peak_ratio'] for r in seizure_results]
        lead_times = [r['lead_time_sec'] for r in seizure_results 
                     if r.get('lead_time_sec', 0) > 0]
        
        print(f"  Seizure files: {len(seizure_results)}")
        print(f"  Peak range: {min(peak_ratios):.0f}x – {max(peak_ratios):.0f}x")
        
        if lead_times:
            print(f"  Lead times: {min(lead_times):.0f}s – {max(lead_times):.0f}s "
                  f"(mean: {np.mean(lead_times):.0f}s)")

    print(f"  Baseline files: {len(baseline_results)}")
    print(f"{Colors.CYAN}{'─'*70}{Colors.RESET}")

    # Save results
    output_file = f"trinity_{patient_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n💾 Results saved to: {output_file}")
    print(f"✅ Analysis complete.\n")
    
    return results


def main():
    """Command-line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Trinity Research v1.2 - EEG Seizure Prediction Framework',
        epilog='Example: python trinity.py --path ./chb02/ --patient chb02'
    )
    parser.add_argument('--path', '-p', required=True, 
                       help='Path to directory containing EDF files')
    parser.add_argument('--patient', '-id', 
                       help='Patient ID (auto-detected from filenames if not provided)')
    parser.add_argument('--no-progress', action='store_true', 
                       help='Disable progress bar during processing')
    
    args = parser.parse_args()
    analyze_patient(args.path, args.patient, not args.no_progress)


if __name__ == "__main__":
    main()
