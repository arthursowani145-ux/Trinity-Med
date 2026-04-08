# 🧠 Trinity-Med Web Application

## Seizure Prediction & Failed Seizure Discovery

Trinity-Med is a web-based tool that analyzes EEG data to predict epileptic seizures and discover hidden brain self-correction events.

## Features

### Quick Prediction Mode (v1.2)
- Predicts clinical seizures with lead times
- 100% detection rate on CHB-MIT dataset
- Average warning: 139 seconds

### Deep Dive Mode (v3.1)
- Discovers failed seizures (brain self-correction)
- Reveals when the brain prevents seizures naturally
- Found 26 failed seizures in a single patient

## Installation

```bash
git clone https://github.com/yourusername/trinity-web-app.git
cd trinity-web-app
pip install -r requirements.txt
python app.py

Then open http://localhost:5000

Usage

1. Select analysis mode (Quick or Deep Dive)
2. Upload an EDF file
3. View results
4. Download report

Research Validation

· Validated on CHB-MIT Scalp EEG Database (PhysioNet)
· 36 files, 3 clinical seizures, 26 failed seizures discovered
· Peak ratios up to 64 million × baseline

Citation

If you use Trinity-Med in your research, please cite:

```
Trinity Research Team. (2026). Trinity-Med: Seizure Prediction and Failed Seizure Discovery. GitHub.
```

License

MIT License - Open source for research purposes

Disclaimer

For research use only. Not FDA approved. Always consult a physician.
