=====================================
EXE Build Instructions
=====================================

[Requirements]
- Windows 10/11
- Python 3.8 or later (https://www.python.org/downloads/)

[Steps]

1. Install Python
   - Download from https://www.python.org/downloads/
   - IMPORTANT: Check "Add Python to PATH" during installation

2. Double-click "build_exe.bat"
   - A virtual environment will be created
   - Only required libraries will be installed
   - EXE will be created with optimizations

3. After build completes:
   - Output: dist_package\GaroonGoogleSync.exe

4. Add credentials.json to "dist_package" folder

5. Zip and distribute

=====================================
Size Optimization (--onefile mode)
=====================================

This build uses virtual environment + excludes:

Excluded modules:
- numpy, pandas, matplotlib, PIL, scipy, cv2
- torch, tensorflow, keras
- IPython, notebook, jupyter
- pytest, unittest, pydoc, doctest
- lib2to3, xmlrpc, multiprocessing
- distutils, setuptools, pkg_resources
- idlelib, turtledemo

Expected size: ~20-40MB (vs 100MB+ without optimization)

=====================================
Troubleshooting
=====================================

- "python is not recognized" error
  -> Reinstall Python with "Add Python to PATH" checked

- Build fails
  -> Delete "venv" folder and try again

- Slow startup (5-10 seconds)
  -> Normal for --onefile mode
  -> Files are extracted to temp folder on each startup

=====================================
