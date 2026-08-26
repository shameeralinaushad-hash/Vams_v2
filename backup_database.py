import os
import shutil
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "business.db")
BACKUP_DIR = os.path.join(BASE_DIR, "database", "backups")


def run_backup():
    if not os.path.exists(DB_PATH):
        print("No database file found — nothing to back up.")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"business_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    shutil.copy2(DB_PATH, backup_path)
    print(f"Backup created: {backup_path}")

    # Keep only the most recent 14 backups to avoid unlimited disk growth
    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.startswith("business_backup_")],
        reverse=True
    )
    for old_backup in backups[14:]:
        os.remove(os.path.join(BACKUP_DIR, old_backup))
        print(f"Removed old backup: {old_backup}")


if __name__ == "__main__":
    run_backup()