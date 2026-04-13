#!/usr/bin/env python3
"""
TRINITY CLINICAL GRAPHS v1.0
Professional EEG-style visualizations for clinicians

Graphs:
1. Raw EEG waveform (first 6 channels)
2. S-D-T component trajectories
3. Risk index over time
4. Clinical event timeline
"""

import json
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Use Agg backend for server environments
plt.switch_backend('Agg')

def generate_clinical_figure(trinity_result, failed_events=None, save_path=None):
    """
    Generate professional clinical figure with 4 panels
    """
    fig = plt.figure(figsize=(16, 12))
    
    # Get timeline data
    timeline = trinity_result.get('timeline', [])
    if not timeline:
        return None
    
    times = [t['time_sec'] for t in timeline]
    S_vals = [t['S'] for t in timeline]
    D_vals = [t['D'] for t in timeline]
    T_vals = [t['T'] for t in timeline]
    risk_vals = [abs(t['emergence']) for t in timeline]
    
    # Create 4 subplots
    gs = fig.add_gridspec(4, 1, height_ratios=[2, 1.5, 1.5, 1], hspace=0.3)
    
    # Panel 1: Risk Index (Main clinical panel)
    ax1 = fig.add_subplot(gs[0])
    ax1.fill_between(times, 0, risk_vals, alpha=0.3, color='#e74c3c', label='Risk Level')
    ax1.plot(times, risk_vals, color='#e74c3c', linewidth=1.5)
    ax1.set_ylabel('Risk Index', fontsize=11, fontweight='bold')
    ax1.set_title(f'Seizure Risk Trajectory - {trinity_result.get("file", "EEG Analysis")}', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.set_xlim(min(times), max(times))
    
    # Add seizure marker if present
    if trinity_result.get('seizure_at_sec'):
        ax1.axvline(x=trinity_result['seizure_at_sec'], color='red', linewidth=2, linestyle='--', 
                   label=f'Clinical Seizure ({trinity_result["seizure_at_sec"]:.0f}s)')
        ax1.legend(loc='upper left')
    
    # Add horizontal risk lines
    ax1.axhline(y=100, color='purple', linestyle=':', alpha=0.5, label='Critical (100x)')
    ax1.axhline(y=10, color='red', linestyle=':', alpha=0.5, label='High (10x)')
    ax1.axhline(y=1, color='orange', linestyle=':', alpha=0.5, label='Moderate (1x)')
    
    # Panel 2: S (Background Organization)
    ax2 = fig.add_subplot(gs[1])
    ax2.plot(times, S_vals, color='#3498db', linewidth=1.5)
    ax2.fill_between(times, -2, S_vals, alpha=0.2, color='#3498db')
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax2.set_ylabel('Background\nOrganization (S)', fontsize=10)
    ax2.set_title('EEG Background Stability', fontsize=10)
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.set_xlim(min(times), max(times))
    
    # Panel 3: D (Pattern Evolution)
    ax3 = fig.add_subplot(gs[2])
    ax3.plot(times, D_vals, color='#e67e22', linewidth=1.5)
    ax3.fill_between(times, -2, D_vals, alpha=0.2, color='#e67e22')
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax3.set_ylabel('Pattern\nEvolution (D)', fontsize=10)
    ax3.set_title('EEG Pattern Change Rate', fontsize=10)
    ax3.grid(True, alpha=0.3, linestyle='--')
    ax3.set_xlim(min(times), max(times))
    
    # Panel 4: T (Regional Coupling)
    ax4 = fig.add_subplot(gs[3])
    ax4.plot(times, T_vals, color='#2ecc71', linewidth=1.5)
    ax4.fill_between(times, -2, T_vals, alpha=0.2, color='#2ecc71')
    ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax4.set_xlabel('Time (seconds)', fontsize=11)
    ax4.set_ylabel('Regional\nCoupling (T)', fontsize=10)
    ax4.set_title('Brain Region Coordination', fontsize=10)
    ax4.grid(True, alpha=0.3, linestyle='--')
    ax4.set_xlim(min(times), max(times))
    
    # Add failed seizure markers if present
    if failed_events:
        for fe in failed_events:
            if fe.get('file') == trinity_result.get('file'):
                start = fe.get('start_sec', 0)
                end = start + fe.get('duration_sec', 0)
                for ax in [ax1, ax2, ax3, ax4]:
                    ax.axvspan(start, end, alpha=0.2, color='#2ecc71', label='Failed Seizure' if ax == ax1 else '')
    
    plt.suptitle('Trinity Clinical EEG Analysis', fontsize=14, fontweight='bold', y=0.98)
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"✅ Clinical figure saved: {save_path}")
    
    plt.close()
    return fig


def generate_batch_overview(all_results, failed_events=None, save_path=None):
    """
    Generate batch overview figure for multiple files
    """
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Extract metrics
    seizure_files = [r for r in all_results if r.get('seizure_at_sec')]
    peak_ratios = [r.get('peak_ratio', 0) for r in all_results if 'peak_ratio' in r]
    lead_times = [r.get('lead_time_sec', 0) for r in seizure_files]
    
    # Panel 1: Peak Risk Distribution
    ax1 = axes[0, 0]
    ax1.hist(peak_ratios, bins=20, color='steelblue', edgecolor='black', alpha=0.7)
    ax1.axvline(x=10, color='red', linestyle='--', linewidth=2, label='High Risk Threshold')
    ax1.axvline(x=1, color='orange', linestyle='--', linewidth=2, label='Moderate Threshold')
    ax1.set_xlabel('Peak Risk Index (x baseline)')
    ax1.set_ylabel('Number of Files')
    ax1.set_title('Risk Distribution Across Recording Sessions')
    ax1.legend()
    ax1.set_xscale('log')
    
    # Panel 2: Lead Times
    ax2 = axes[0, 1]
    if lead_times:
        colors = ['#2ecc71' if l > 300 else '#f39c12' if l > 60 else '#e74c3c' for l in lead_times]
        bars = ax2.bar(range(len(lead_times)), lead_times, color=colors, edgecolor='black')
        ax2.axhline(y=300, color='#2ecc71', linestyle='--', linewidth=2, label='Optimal (5 min)')
        ax2.axhline(y=60, color='#e74c3c', linestyle='--', linewidth=2, label='Minimal (1 min)')
        ax2.set_xlabel('Seizure Event Number')
        ax2.set_ylabel('Lead Time (seconds)')
        ax2.set_title('Seizure Prediction Lead Times')
        ax2.legend()
    else:
        ax2.text(0.5, 0.5, 'No clinical seizures detected', ha='center', va='center', transform=ax2.transAxes)
        ax2.set_title('Seizure Prediction Lead Times')
    
    # Panel 3: Failed vs Clinical Pie Chart
    ax3 = axes[1, 0]
    clinical = len(seizure_files)
    failed = len(failed_events) if failed_events else 0
    normal = len(all_results) - clinical - failed
    labels = ['Clinical Seizures', 'Failed/Aborted', 'Normal']
    sizes = [clinical, failed, normal]
    colors = ['#e74c3c', '#2ecc71', '#95a5a6']
    ax3.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    ax3.set_title('Seizure Event Distribution')
    
    # Panel 4: Summary Statistics
    ax4 = axes[1, 1]
    ax4.axis('off')
    stats_text = f"""
    CLINICAL SUMMARY
    ─────────────────────────────────────────
    Total Sessions:        {len(all_results)}
    Clinical Seizures:     {clinical}
    Failed/Aborted:        {failed}
    Normal Sessions:       {normal}
    
    ─────────────────────────────────────────
    Self-Correction Rate:  {failed/(clinical+failed)*100:.1f}% (if clinical+failed>0)
    Average Lead Time:     {np.mean(lead_times):.0f}s (if lead_times)
    Best Lead Time:        {max(lead_times) if lead_times else 0}s
    
    ─────────────────────────────────────────
    INTERPRETATION:
    The brain successfully self-corrected
    {failed} times without clinical seizure.
    """
    ax4.text(0.05, 0.95, stats_text, transform=ax4.transAxes, fontsize=10,
            verticalalignment='top', fontfamily='monospace')
    
    plt.suptitle('Trinity Clinical EEG Summary Report', fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"✅ Batch overview saved: {save_path}")
    
    plt.close()
    return fig


def generate_single_file_figure(trinity_result, output_path):
    """Generate single file clinical figure"""
    timeline = trinity_result.get('timeline', [])
    if not timeline:
        return None
    
    times = [t['time_sec'] for t in timeline]
    risk_vals = [abs(t['emergence']) for t in timeline]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Main risk plot
    ax.fill_between(times, 0, risk_vals, alpha=0.3, color='#e74c3c')
    ax.plot(times, risk_vals, color='#e74c3c', linewidth=1.5)
    
    # Threshold lines
    ax.axhline(y=100, color='purple', linestyle='--', alpha=0.7, label='Critical (100x)')
    ax.axhline(y=10, color='red', linestyle='--', alpha=0.7, label='High (10x)')
    ax.axhline(y=1, color='orange', linestyle='--', alpha=0.7, label='Moderate (1x)')
    
    if trinity_result.get('seizure_at_sec'):
        ax.axvline(x=trinity_result['seizure_at_sec'], color='red', linewidth=2, 
                  linestyle='--', label=f'Seizure at {trinity_result["seizure_at_sec"]:.0f}s')
    
    ax.set_xlabel('Time (seconds)', fontsize=12)
    ax.set_ylabel('Risk Index (x baseline)', fontsize=12)
    ax.set_title(f'Seizure Risk Analysis - {trinity_result.get("file", "EEG")}', fontsize=12)
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.set_yscale('log')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    return output_path


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate clinical graphs from Trinity output')
    parser.add_argument('--trinity', '-t', required=True, help='Trinity JSON output')
    parser.add_argument('--failed', '-f', help='Failed seizure report JSON')
    parser.add_argument('--output', '-o', required=True, help='Output image path (.png)')
    parser.add_argument('--batch', action='store_true', help='Batch mode (generate overview)')
    
    args = parser.parse_args()
    
    with open(args.trinity) as f:
        data = json.load(f)
    
    failed_events = None
    if args.failed and Path(args.failed).exists():
        with open(args.failed) as f:
            failed_data = json.load(f)
            failed_events = failed_data.get('failed_seizures', [])
    
    if args.batch:
        generate_batch_overview(data, failed_events, args.output)
    else:
        # Single file - assume data is a dict (single result)
        if isinstance(data, list):
            data = data[0] if data else {}
        generate_single_file_figure(data, args.output)
    
    print(f"✅ Graph saved: {args.output}")
