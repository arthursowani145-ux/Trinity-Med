#!/usr/bin/env python3
"""
TRINITY CLINICAL TRANSLATOR v2.1
Translates Trinity S-D-T analysis into plain clinical narrative
for neurologists and clinicians.

S = Surface       — Background EEG organization
D = Depth         — Rate of pattern change
T = Time          — Regional coupling / torsion
Emergence = S×D×T — Synergistic risk index
"""

from datetime import datetime

SDT_HIGH = 1.0
SDT_CRIT = 2.5


def _describe_S(val):
    if val > SDT_CRIT:
        return "background brain activity became highly disorganized and erratic"
    elif val > SDT_HIGH:
        return "background brain activity showed elevated irregularity"
    elif val < -SDT_HIGH:
        return "background brain activity was unusually suppressed and quiet"
    else:
        return "background brain activity was within normal range"

def _describe_D(val):
    if val > SDT_CRIT:
        return "brain patterns were changing at a critically rapid rate"
    elif val > SDT_HIGH:
        return "brain patterns were evolving faster than normal"
    elif val < -SDT_HIGH:
        return "brain pattern evolution was slowed or frozen"
    else:
        return "brain pattern changes were within normal range"

def _describe_T(val):
    if val > SDT_CRIT:
        return "brain regions showed strong abnormal coupling"
    elif val > SDT_HIGH:
        return "inter-regional brain coordination was elevated"
    elif val < -SDT_HIGH:
        return "brain regions appeared decoupled from each other"
    else:
        return "inter-regional brain coordination was normal"

def _alignment_summary(S, D, T):
    high = sum([abs(S) > SDT_HIGH, abs(D) > SDT_HIGH, abs(T) > SDT_HIGH])
    if high == 3:
        return "All three Trinity domains (Surface, Depth, Time) were simultaneously elevated — full alignment."
    elif high == 2:
        return "Two of three Trinity domains were simultaneously elevated — partial alignment."
    elif high == 1:
        return "Only one Trinity domain was elevated — no significant alignment."
    else:
        return "All three domains were within normal range — brain was stable."

def _risk_level_from_timeline(timeline, seizure_at, lead_time):
    """
    Derive risk from actual classified states in the timeline,
    not just the raw peak ratio (which is relative to a tiny baseline
    and can inflate misleadingly).

    Rule: if a clinical seizure was annotated, minimum risk is HIGH.
    Lead time refines upward to CRITICAL if warning was very short.
    """
    if not timeline:
        return "LOW"

    has_ictal    = any(t.get("state") == "Seizure"          for t in timeline)
    has_preictal = any(t.get("state") == "Pre-ictal"        for t in timeline)
    has_ied      = any(t.get("state") == "Interictal Spike" for t in timeline)

    if seizure_at:
        # Confirmed clinical seizure — always at least HIGH
        if not lead_time or lead_time <= 60:
            return "CRITICAL"   # Seizure at onset or very short warning
        elif lead_time <= 300:
            return "HIGH"       # Less than 5 min warning
        else:
            return "HIGH"       # Long warning — still HIGH, seizure confirmed
    elif has_ictal:
        return "HIGH"
    elif has_preictal:
        return "MODERATE"
    elif has_ied:
        return "LOW-MODERATE"
    else:
        return "LOW"

def _format_time(sec):
    sec = int(sec)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h > 0:   return f"{h}h {m}m {s}s"
    elif m > 0: return f"{m}m {s}s"
    else:       return f"{s}s"


class ClinicalReportGenerator:

    @staticmethod
    def generate_clinical_summary(result: dict) -> str:
        if not result:
            return "No analysis data available."

        lines = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        filename   = result.get("file", result.get("filename", "Unknown"))
        duration   = result.get("duration_sec", 0)
        peak_ratio = result.get("peak_ratio", 0)
        peak_time  = result.get("peak_time_sec", 0)
        baseline   = result.get("baseline_emergence", 0)
        timeline   = result.get("timeline", [])
        seizure_at = result.get("seizure_at_sec")
        lead_time  = result.get("lead_time_sec", 0)
        transition = result.get("transition_type", "")

        # Risk is driven by classified states, not raw ratio
        risk = _risk_level_from_timeline(timeline, seizure_at, lead_time)

        risk_symbols = {
            "CRITICAL":     "🔴",
            "HIGH":         "🟠",
            "MODERATE":     "🟡",
            "LOW-MODERATE": "🟡",
            "LOW":          "🟢",
        }
        risk_color = risk_symbols.get(risk, "⚪")

        # ── Header ──
        lines += [
            "=" * 64,
            "  TRINITY CLINICAL REPORT",
            f"  Generated : {now}",
            f"  File      : {filename}",
            f"  Duration  : {_format_time(duration)} ({duration/60:.0f} minutes)",
            "=" * 64, "",
        ]

        # ── Overall risk ──
        risk_text = {
            "CRITICAL":
                "A clinical seizure occurred with very short or no advance warning.",
            "HIGH":
                "A clinical seizure was confirmed in this recording." + (
                    f" Trinity predicted it {lead_time:.0f} seconds ({lead_time/60:.1f} minutes) in advance."
                    if lead_time and lead_time > 0 else
                    " Trinity detected it at onset with no advance warning."
                ),
            "MODERATE":
                "Pre-ictal patterns were observed. Brain was approaching seizure threshold.",
            "LOW-MODERATE":
                "Interictal discharges were present. The brain self-corrected each time without progressing to seizure.",
            "LOW":
                "Brain activity was within normal baseline range throughout this recording.",
        }
        lines += [
            f"  OVERALL RISK: {risk_color} {risk}",
            f"  {risk_text.get(risk, '')}",
            f"  (Trinity peak emergence: {peak_ratio:.0f}x above local baseline)",
            "",
        ]

        # ── Seizure event ──
        lines += ["  SEIZURE EVENT", "  " + "-"*50]
        if seizure_at:
            lines += [
                f"  A clinical seizure was recorded at {_format_time(seizure_at)} into the recording.",
                f"  Trinity detected the onset {lead_time:.0f} seconds ({lead_time/60:.1f} minutes) in advance.",
                "",
            ]
            if transition == "GRADUAL":
                lines.append(
                    "  The transition was GRADUAL — pre-ictal changes built slowly over several\n"
                    "  minutes, providing a sufficient window for clinical intervention."
                )
            elif transition == "MODERATE":
                lines.append(
                    "  The transition was MODERATE — pre-ictal escalation occurred over one to\n"
                    "  ten minutes. Prompt clinical response was needed."
                )
            else:
                lines.append(
                    "  The transition was ABRUPT — the brain moved from baseline to ictal state\n"
                    "  rapidly. The intervention window was very short."
                )
        else:
            lines += [
                "  No clinical seizure was annotated in this recording.",
                "  Trinity characterized this as a baseline or self-correcting session.",
            ]
        lines.append("")

        # ── Peak event narrative ──
        if timeline:
            peak_entry = max(timeline, key=lambda t: abs(t.get("emergence", 0)))
            S, D, T = peak_entry["S"], peak_entry["D"], peak_entry["T"]
            emg   = peak_entry["emergence"]
            t_str = _format_time(peak_entry["time_sec"])
            state = peak_entry.get("state", "Unknown")

            lines += [
                "  PEAK EMERGENCE EVENT", "  " + "-"*50,
                f"  At {t_str}, Trinity recorded its highest emergence value.",
                f"  Brain state at this moment was classified as: {state}.",
                "",
                "  What was happening:",
                f"    • {_describe_S(S).capitalize()}.",
                f"    • {_describe_D(D).capitalize()}.",
                f"    • {_describe_T(T).capitalize()}.",
                "",
                f"  {_alignment_summary(S, D, T)}",
                "",
            ]

        # ── Timeline summary ──
        if timeline:
            ied_times    = [t for t in timeline if t.get("state") == "Interictal Spike"]
            preict_times = [t for t in timeline if t.get("state") == "Pre-ictal"]
            ictal_times  = [t for t in timeline if t.get("state") == "Seizure"]
            stable_count = sum(1 for t in timeline if t.get("state") == "Stable")

            # If a seizure was annotated but timeline sampling missed the ictal window,
            # note it explicitly so the count is not misleadingly zero
            annotated_seizure_note = ""
            if seizure_at and len(ictal_times) == 0:
                annotated_seizure_note = f" (clinical seizure annotated at {_format_time(seizure_at)} — outside sampled windows)"

            lines += [
                "  RECORDING TIMELINE SUMMARY", "  " + "-"*50,
                f"  Total timepoints sampled : {len(timeline)}",
                f"  Stable periods           : {stable_count} ({stable_count/len(timeline)*100:.0f}% of recording)",
                f"  Interictal spikes (IEDs) : {len(ied_times)}",
                f"  Pre-ictal periods        : {len(preict_times)}",
                f"  Ictal (seizure) periods  : {len(ictal_times)}{annotated_seizure_note}",
                "",
            ]

            if ied_times:
                times_str = ", ".join(_format_time(t["time_sec"]) for t in ied_times[:5])
                suffix = " and others." if len(ied_times) > 5 else "."
                lines += [
                    f"  Interictal spikes were detected at: {times_str}{suffix}",
                    "  These are brief abnormal discharges. Each time, the brain self-corrected",
                    "  without progressing to a full clinical seizure.", "",
                ]

            if preict_times:
                times_str = ", ".join(_format_time(t["time_sec"]) for t in preict_times[:3])
                lines += [
                    f"  Pre-ictal activity was observed at: {times_str}.",
                    "  The brain was approaching seizure threshold but had not yet crossed it.", "",
                ]

            if ictal_times:
                times_str = ", ".join(_format_time(t["time_sec"]) for t in ictal_times[:3])
                lines += [
                    f"  Ictal (seizure-level) activity was detected at: {times_str}.",
                    "  All three Trinity domains aligned simultaneously at these moments.", "",
                ]

        # ── S-D-T explanation ──
        lines += [
            "  UNDERSTANDING THE TRINITY LENS", "  " + "-"*50,
            "  Trinity monitors three dimensions of brain dynamics simultaneously:",
            "",
            "  S — Surface (Background Organization):",
            "    How organized the brain's baseline electrical activity is.",
            "    Elevated S signals a disrupted, chaotic background.",
            "",
            "  D — Depth (Pattern Evolution):",
            "    How rapidly brain activity patterns are changing.",
            "    Elevated D signals fast, unstable transitions.",
            "",
            "  T — Time (Regional Coupling):",
            "    How tightly different brain regions are locked together.",
            "    Elevated T signals abnormal inter-regional synchrony.",
            "",
            "  Emergence (S × D × T):",
            "    When all three dimensions rise together, emergence spikes.",
            "    This convergence is Trinity's core seizure risk signal.",
            "    The brain self-corrects when emergence peaks but does not",
            "    sustain — a failed seizure. It progresses when emergence",
            "    is sustained and all three domains stay aligned.",
            "",
        ]

        # ── Recommendation ──
        lines += ["  CLINICAL RECOMMENDATION", "  " + "-"*50]

        if risk == "CRITICAL":
            lines += [
                "  🔴 IMMEDIATE ACTION REQUIRED",
                "  Seizure onset was detected with very short lead time.",
                "  Activate seizure response protocol immediately.",
                "  Notify attending neurologist.",
                "  Administer rescue medication if clinically indicated.",
            ]
        elif risk == "HIGH":
            lines += [
                "  🟠 ALERT CLINICAL TEAM",
                "  Significant ictal activity was detected.",
                "  Notify clinical team promptly.",
                "  Prepare rescue medication.",
                "  Increase monitoring frequency.",
            ]
        elif risk in ("MODERATE", "LOW-MODERATE"):
            lines += [
                "  🟡 MONITOR CLOSELY",
                "  Abnormal discharges were present but self-corrected.",
                "  No immediate intervention required.",
                "  Re-evaluate within 15 minutes.",
                "  Consider medication review if IEDs are increasing in frequency.",
            ]
        else:
            lines += [
                "  🟢 ROUTINE MONITORING",
                "  Brain dynamics were within acceptable baseline range.",
                "  No immediate action required.",
                "  Continue standard monitoring protocol.",
            ]

        lines += ["", "="*64, "  End of Trinity Clinical Report", "="*64]
        return "\n".join(lines)


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) < 2:
        print("Usage: python trinity_clinical_translator_v2.1.py <trinity_output.json>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        data = json.load(f)
    if isinstance(data, list):
        for item in data:
            print(ClinicalReportGenerator.generate_clinical_summary(item))
            print()
    else:
        print(ClinicalReportGenerator.generate_clinical_summary(data))
