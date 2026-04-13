#!/usr/bin/env python3
"""
TRINITY CLINICAL INTEGRATION SUITE v1.1 - FIXED
======================================
Comprehensive clinical interface for Trinity seizure prediction system
"""

import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from datetime import datetime
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import uuid
import warnings
warnings.filterwarnings('ignore')


class ClinicalSeverity(Enum):
    """ILAE-aligned severity levels"""
    NORMAL = ("Normal", "#2ecc71", "Continue standard care")
    MILD = ("Mild", "#f1c40f", "Routine monitoring")
    MODERATE = ("Moderate", "#e67e22", "Enhanced surveillance")
    HIGH = ("High", "#e74c3c", "Intervention readiness")
    CRITICAL = ("Critical", "#8e44ad", "Immediate action required")
    RESOLVED = ("Resolved", "#3498db", "Self-corrected - document only")


@dataclass
class SeizureEvent:
    """Clinical seizure event model"""
    event_id: str
    start_time: float
    end_time: Optional[float]
    event_type: str
    severity: str
    peak_emergence: float
    clinical_features: List[str] = field(default_factory=list)
    outcome: str = "unknown"
    
    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())[:8]


class TrinityClinicalTranslator:
    """Core translation engine: S-D-T → Clinical terminology"""
    
    def __init__(self, patient_id: str, mrn: Optional[str] = None):
        self.patient_id = patient_id
        self.mrn = mrn or f"TR-{patient_id.upper()}"
        
    def translate_sdt(self, S: float, D: float, T: float, 
                     emergence: float, baseline: float) -> Dict[str, Any]:
        """Convert S-D-T to clinical terminology"""
        e_ratio = abs(emergence) / (baseline + 1e-10)
        
        # Background stability (S)
        if abs(S) < 0.5:
            background = "Organized background rhythm"
        elif abs(S) < 1.5:
            background = "Mild background disorganization"
        else:
            background = "Markedly disorganized background"
            
        # Pattern evolution (D)
        if abs(D) < 0.5:
            evolution = "Stable dynamics"
        elif abs(D) < 1.5:
            evolution = "Gradual pattern evolution"
        else:
            evolution = "Rapid pattern evolution"
            
        # State coupling (T)
        if abs(T) < 0.5:
            coupling = "Normal frequency interactions"
        elif abs(T) < 1.5:
            coupling = "Altered frequency coupling"
        else:
            coupling = "Disrupted cross-frequency relationships"
            
        # Determine severity
        if e_ratio >= 100:
            severity = ClinicalSeverity.CRITICAL
            impression = f"Ictal pattern (risk {e_ratio:.0f}x)"
        elif e_ratio >= 10:
            severity = ClinicalSeverity.HIGH
            impression = f"Pre-ictal pattern ({e_ratio:.0f}x)"
        elif e_ratio >= 1:
            severity = ClinicalSeverity.MODERATE
            impression = f"Interictal instability ({e_ratio:.0f}x)"
        elif e_ratio >= 0.3:
            severity = ClinicalSeverity.MILD
            impression = f"Mild background variability ({e_ratio:.0f}x)"
        else:
            severity = ClinicalSeverity.NORMAL
            impression = "Normal monitoring segment"
            
        return {
            'clinical_background': background,
            'pattern_evolution': evolution,
            'state_coupling': coupling,
            'risk_ratio': round(e_ratio, 1),
            'severity': severity.value[0],
            'clinical_impression': impression,
            'recommendation': severity.value[2],
            'color_code': severity.value[1]
        }


class EMUVisualizer:
    """Generate EMU-optimized visual displays"""
    
    def __init__(self, translator: TrinityClinicalTranslator):
        self.translator = translator
        
    def generate_bedside_display(self, result: Dict, 
                                  failed_events: List[Dict] = None,
                                  save_path: Optional[str] = None) -> plt.Figure:
        """Generate bedside monitor display"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        timeline = result.get('timeline', [])
        if not timeline:
            return fig
            
        times = [t['time_sec'] for t in timeline]
        risks = [abs(t['emergence']) for t in timeline]
        
        # Risk trajectory
        ax1 = axes[0, 0]
        ax1.plot(times, risks, 'b-', linewidth=2)
        ax1.fill_between(times, 0, risks, alpha=0.3, color='red')
        if result.get('seizure_at_sec'):
            ax1.axvline(result['seizure_at_sec'], color='red', linestyle='--', linewidth=2)
        ax1.set_yscale('log')
        ax1.set_xlabel('Time (seconds)')
        ax1.set_ylabel('Risk Index')
        ax1.set_title('Seizure Risk Trajectory')
        ax1.grid(True, alpha=0.3)
        
        # S-D-T components
        ax2 = axes[0, 1]
        S_vals = [t['S'] for t in timeline]
        D_vals = [t['D'] for t in timeline]
        T_vals = [t['T'] for t in timeline]
        ax2.plot(times, S_vals, label='S (Background)', linewidth=2)
        ax2.plot(times, D_vals, label='D (Evolution)', linewidth=2)
        ax2.plot(times, T_vals, label='T (Coupling)', linewidth=2)
        ax2.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        ax2.set_xlabel('Time (seconds)')
        ax2.set_ylabel('Normalized Value')
        ax2.set_title('Component Dynamics')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Risk distribution
        ax3 = axes[1, 0]
        ax3.hist(risks, bins=20, color='steelblue', edgecolor='black')
        ax3.set_xlabel('Risk Level')
        ax3.set_ylabel('Frequency')
        ax3.set_title('Risk Distribution')
        
        # Event timeline
        ax4 = axes[1, 1]
        ax4.axis('off')
        y = 0.8
        if result.get('seizure_at_sec'):
            ax4.text(0.1, y, f"⚡ CLINICAL SEIZURE at {result['seizure_at_sec']:.0f}s", 
                    color='red', fontweight='bold', fontsize=10)
            y -= 0.2
        if failed_events:
            for fe in failed_events[:3]:
                if fe.get('file') == result.get('file'):
                    ax4.text(0.1, y, f"💚 Failed seizure: {fe.get('duration_sec', 0):.0f}s", 
                            color='blue', fontsize=10)
                    y -= 0.15
        ax4.set_title('Event Timeline')
        
        plt.suptitle(f'Trinity Bedside Monitor | {result["file"]}')
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"✅ Display saved: {save_path}")
            
        return fig
    
    def generate_24h_overview(self, all_results: List[Dict], 
                              failed_events: List[Dict] = None,
                              save_path: Optional[str] = None) -> plt.Figure:
        """Generate 24-hour EMU overview"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # Risk distribution across all files
        ax1 = axes[0, 0]
        all_risks = [r.get('peak_ratio', 0) for r in all_results]
        ax1.hist(all_risks, bins=20, color='steelblue', edgecolor='black')
        ax1.axvline(x=10, color='red', linestyle='--', label='High risk threshold')
        ax1.axvline(x=1, color='orange', linestyle='--', label='Moderate threshold')
        ax1.set_xlabel('Peak Risk Index')
        ax1.set_ylabel('Number of Files')
        ax1.set_title('Risk Distribution')
        ax1.legend()
        
        # Lead times
        ax2 = axes[0, 1]
        seizure_files = [r for r in all_results if r.get('seizure_at_sec')]
        leads = [r.get('lead_time_sec', 0) for r in seizure_files]
        if leads:
            colors = []
            for l in leads:
                if l > 300:
                    colors.append('green')
                elif l > 60:
                    colors.append('orange')
                else:
                    colors.append('red')
            ax2.bar(range(len(leads)), leads, color=colors)
            ax2.axhline(y=300, color='green', linestyle='--', label='5 min (optimal)')
            ax2.axhline(y=60, color='red', linestyle='--', label='1 min (minimal)')
            ax2.set_xlabel('Seizure Event')
            ax2.set_ylabel('Lead Time (seconds)')
            ax2.set_title('Prediction Lead Times')
            ax2.legend()
        
        # Failed vs Clinical
        ax3 = axes[1, 0]
        clinical = len(seizure_files)
        failed = len(failed_events) if failed_events else 0
        labels = ['Clinical Seizures', 'Failed/Aborted', 'No Event']
        sizes = [clinical, failed, len(all_results) - clinical - failed]
        colors = ['#e74c3c', '#3498db', '#95a5a6']
        ax3.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%')
        ax3.set_title('Seizure Event Distribution')
        
        # Summary text
        ax4 = axes[1, 1]
        ax4.axis('off')
        avg_lead = int(np.mean(leads)) if leads else 0
        text = f"""
        PATIENT SUMMARY
        ─────────────────
        Total Files: {len(all_results)}
        Clinical Seizures: {clinical}
        Failed Seizures: {failed}
        Self-Correction Rate: {failed/(clinical+failed)*100:.1f}% if (clinical+failed)>0 else 0
        
        Average Lead Time: {avg_lead}s
        Best Lead Time: {max(leads) if leads else 0}s
        """
        ax4.text(0.1, 0.5, text, fontsize=12, fontfamily='monospace',
                verticalalignment='center')
        
        plt.suptitle(f'24-Hour EMU Overview | Patient: {self.translator.mrn}')
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"✅ Overview saved: {save_path}")
            
        return fig


class FailedSeizureIntegrator:
    """Integrate failed seizure detection into clinical workflow"""
    
    def __init__(self, translator: TrinityClinicalTranslator):
        self.translator = translator
        
    def process_failed_seizures(self, failed_report_path: str) -> List[Dict]:
        """Load and process failed seizure detector output"""
        with open(failed_report_path) as f:
            report = json.load(f)
        
        integrated_events = []
        for event in report.get('failed_seizures', []):
            integrated_events.append({
                'file': event.get('filename', 'unknown'),
                'start_sec': event.get('start_sec', 0),
                'duration_sec': event.get('duration_sec', 0),
                'peak_ratio': event.get('peak_ratio', 0),
                'clinical_interpretation': self._interpret_failed_seizure(event)
            })
        return integrated_events
    
    def _interpret_failed_seizure(self, event: Dict) -> str:
        """Generate clinical interpretation"""
        duration = event.get('duration_sec', 0)
        ratio = event.get('peak_ratio', 0)
        return (f"Self-resolved high-risk event: {ratio:.0f}x baseline "
                f"lasting {duration:.0f}s. Brain self-corrected without clinical seizure.")


class FHIRExporter:
    """Export Trinity results to HL7 FHIR R4 format"""
    
    def __init__(self, translator: TrinityClinicalTranslator):
        self.translator = translator
        
    def create_observation_bundle(self, trinity_results: List[Dict],
                                   failed_events: List[Dict] = None) -> Dict:
        """Create FHIR Bundle with observations"""
        bundle = {
            "resourceType": "Bundle",
            "id": str(uuid.uuid4()),
            "type": "collection",
            "entry": []
        }
        
        for i, result in enumerate(trinity_results[:10]):
            if 'error' in result:
                continue
            obs = {
                "resourceType": "Observation",
                "id": f"obs-{i}",
                "status": "final",
                "code": {
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": "94744-3",
                        "display": "Seizure probability"
                    }]
                },
                "subject": {"reference": f"Patient/{self.translator.mrn}"},
                "valueQuantity": {
                    "value": result.get('peak_ratio', 0),
                    "unit": "x baseline"
                }
            }
            bundle["entry"].append({"resource": obs})
            
        return bundle
    
    def export_to_file(self, bundle: Dict, output_path: str):
        """Export FHIR bundle to JSON file"""
        with open(output_path, 'w') as f:
            json.dump(bundle, f, indent=2)
        print(f"✅ FHIR bundle exported: {output_path}")


class TrinityClinicalInterface:
    """Unified clinical interface"""
    
    def __init__(self, patient_id: str, mrn: Optional[str] = None):
        self.translator = TrinityClinicalTranslator(patient_id, mrn)
        self.visualizer = EMUVisualizer(self.translator)
        self.integrator = FailedSeizureIntegrator(self.translator)
        self.exporter = FHIRExporter(self.translator)
        
    def process_session(self, trinity_json: str, 
                       failed_json: Optional[str] = None,
                       output_dir: str = './clinical_output/') -> Dict:
        """Process complete monitoring session"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        with open(trinity_json) as f:
            trinity_results = json.load(f)
        
        failed_events = None
        if failed_json and Path(failed_json).exists():
            failed_events = self.integrator.process_failed_seizures(failed_json)
            print(f"✅ Integrated {len(failed_events)} failed seizures")
        
        outputs = {}
        
        # Generate 24h overview
        overview_path = Path(output_dir) / f"overview_{self.translator.patient_id}.png"
        self.visualizer.generate_24h_overview(trinity_results, failed_events, str(overview_path))
        outputs['overview'] = str(overview_path)
        
        # Generate bedside displays for seizure files
        bedside_paths = []
        for result in trinity_results:
            if result.get('seizure_at_sec'):
                path = Path(output_dir) / f"bedside_{result['file'].replace('.edf', '.png')}"
                self.visualizer.generate_bedside_display(result, failed_events, str(path))
                bedside_paths.append(str(path))
        outputs['bedside_displays'] = bedside_paths
        
        # Export FHIR
        bundle = self.exporter.create_observation_bundle(trinity_results, failed_events)
        fhir_path = Path(output_dir) / f"fhir_{self.translator.patient_id}.json"
        self.exporter.export_to_file(bundle, str(fhir_path))
        outputs['fhir'] = str(fhir_path)
        
        print(f"\n✅ Clinical integration complete for {self.translator.patient_id}")
        return outputs


def main():
    import argparse
    import glob
    
    parser = argparse.ArgumentParser(description='Trinity Clinical Integration Suite')
    parser.add_argument('--trinity', '-t', required=True, help='Trinity JSON output')
    parser.add_argument('--failed', '-f', help='Failed seizure report JSON (supports wildcards)')
    parser.add_argument('--patient', '-p', required=True, help='Patient ID')
    parser.add_argument('--mrn', '-m', help='Medical Record Number')
    parser.add_argument('--output', '-o', default='./clinical_output/', help='Output directory')
    
    args = parser.parse_args()
    
    # Handle wildcard for failed file
    failed_path = args.failed
    if failed_path and '*' in failed_path:
        matches = glob.glob(failed_path)
        if matches:
            failed_path = matches[0]
            print(f"Using failed report: {failed_path}")
    
    interface = TrinityClinicalInterface(args.patient, args.mrn)
    outputs = interface.process_session(args.trinity, failed_path, args.output)
    
    print("\n📁 Generated files:")
    for key, path in outputs.items():
        print(f"  {key}: {path}")


if __name__ == "__main__":
    main()
