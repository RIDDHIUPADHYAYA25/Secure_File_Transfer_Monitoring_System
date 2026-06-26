import subprocess
import time
import os
import sqlite3

def get_db_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "instance", "sentinel.db")

def get_audit_log_count():
    try:
        conn = sqlite3.connect(get_db_path())
        try:
            return conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        finally:
            conn.close()
    except Exception as e:
        print(f"Error querying DB: {e}")
        return 0

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.dirname(script_dir)
    db_path = get_db_path()

    if not os.path.exists(db_path):
        print(f"Database does not exist at {db_path} yet. Please run app.py once first.")
        return

    initial_count = get_audit_log_count()
    print(f"Baseline audit_logs count: {initial_count}")

    # Start app.py as a subprocess
    print("Starting app.py subprocess...")
    python_exe = os.path.join(workspace_dir, ".venv", "Scripts", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = "python"
    
    print(f"Using python executable: {python_exe}")
    print(f"Running app.py in working directory: {script_dir}")
    proc = subprocess.Popen(
        [python_exe, "app.py"], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        cwd=script_dir,
        text=True
    )
    
    # Wait for startup
    time.sleep(5)

    test_file_path = os.path.join(script_dir, "instance", "monitored_folder", "concurrency_test.txt")
    try:
        # 1. Create file
        print(f"Creating file: {test_file_path}")
        with open(test_file_path, "w") as f:
            f.write("concurrency testing file create")
        time.sleep(2)  # Wait for event handler to process

        # 2. Modify file
        print(f"Modifying file: {test_file_path}")
        with open(test_file_path, "a") as f:
            f.write("\nconcurrency testing file modified")
        time.sleep(2)  # Wait for event handler to process

        # 3. Delete file
        print(f"Deleting file: {test_file_path}")
        if os.path.exists(test_file_path):
            os.remove(test_file_path)
        time.sleep(2)  # Wait for event handler to process

    except Exception as e:
        print(f"File operation error: {e}")

    # Stop Flask app
    print("Terminating app.py...")
    proc.terminate()
    try:
        stdout, stderr = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()

    print("\n--- Flask stdout ---")
    print(stdout)
    print("\n--- Flask stderr ---")
    print(stderr)

    final_count = get_audit_log_count()
    print(f"\nFinal audit_logs count: {final_count}")
    print(f"New audit logs added: {final_count - initial_count}")

    # Check if 'database is locked' appears in stderr/stdout
    locked_in_stdout = "database is locked" in stdout.lower()
    locked_in_stderr = "database is =)locked" in stderr.lower()
    if locked_in_stdout or locked_in_stderr:
        print("\nFAILED: 'database is locked' error was detected!")
    else:
        print("\nSUCCESS: No database locked error detected.")

    if final_count > initial_count:
        print("SUCCESS: New rows appeared in audit_logs.")
        # Print the last few logs
        conn = sqlite3.connect(db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT timestamp, event_type, file_name, status FROM audit_logs ORDER BY id DESC LIMIT 5").fetchall()
            for r in rows:
                print(f"  [{r['timestamp']}] {r['event_type']} - {r['file_name']} (Status: {r['status']})")
        finally:
            conn.close()
    else:
        print("FAILED: No new rows appeared in audit_logs.")

if __name__ == "__main__":
    main()
