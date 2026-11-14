import sys
import os
import platform
import subprocess

def run_diag():
    out = []
    out.append(f"Python: {sys.version}")
    out.append(f"Platform: {platform.platform()}")
    out.append(f"Machine: {platform.machine()}")
    out.append(f"Architecture: {platform.architecture()}")
    out.append(f"Current Dir: {os.getcwd()}")
    
    bin_path = os.path.join(os.getcwd(), "bin", "challenge")
    out.append(f"Bin path: {bin_path} (exists: {os.path.exists(bin_path)})")
    if os.path.exists(bin_path):
        out.append(f"Bin stat: {oct(os.stat(bin_path).st_mode)}")
        try:
            res = subprocess.run([bin_path, "--help"], capture_output=True, text=True, timeout=5)
            out.append(f"Bin test rc: {res.returncode}")
            out.append(f"Bin stdout: {res.stdout[:200]}")
            out.append(f"Bin stderr: {res.stderr[:200]}")
        except Exception as e:
            out.append(f"Bin exec error: {e}")
            
    return "\n".join(out)

if __name__ == "__main__":
    print(run_diag())
