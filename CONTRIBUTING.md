# Contributing to Personal Download Manager (PDM)

Thank you for your interest in contributing to Personal Download Manager! PDM is built as an open-source, community-driven project dedicated to delivering a fast, privacy-first, and modern download accelerator.

---

## 🛠️ Development Setup

### Prerequisites
* **Windows 10 or 11** (64-bit)
* **Python 3.10+** (Python 3.12 recommended)
* **Node.js** (for checking extension JavaScript syntax)
* **Git**

### Step-by-Step Environment Setup
1. Fork and clone the repository:
   ```powershell
   git clone https://github.com/your-username/personal-download-manager.git
   cd personal-download-manager
   ```
2. Create and activate a virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
3. Install development dependencies:
   ```powershell
   pip install -r requirements.txt
   pip install pytest pytest-qt pyinstaller
   ```
4. Run the desktop application:
   ```powershell
   python pdm/main.py
   ```

---

## 🧪 Testing & Code Quality

Before opening a pull request, ensure all tests pass:

```powershell
# Run backend engine and Qt test suite
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest tests/ -v

# Verify Extension JavaScript syntax
node --check extension/background.js
node --check extension/content.js
```

---

## 🌿 Branching & Pull Request Guidelines

1. Create a feature branch with a descriptive name:
   ```powershell
   git checkout -b feature/stream-audio-filter
   ```
2. Follow existing code conventions:
   * **Python:** PEP 8 compliance, explicit type hints, and clean error handling.
   * **Extension JavaScript:** Vanilla JavaScript (ES2022+), no external bundlers/frameworks required for the extension to maintain maximum performance.
   * **CSS:** Clean class hierarchies, dark-mode glassmorphism design tokens, and strict `!important` usage only where necessary to avoid page style collisions.
3. Write or update tests in `tests/` for any new engine logic or URL parser.
4. Submit a Pull Request detailing the changes and linking relevant issues.

---

## 📜 License Notice

By contributing to Personal Download Manager, you agree that your contributions will be licensed under the **GNU General Public License v3.0 (GPLv3)**.
