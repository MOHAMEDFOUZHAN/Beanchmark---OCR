# backup_manager.py
import os
import shutil
from pathlib import Path

class MirrorBackup:
    def __init__(self, main_db_path, backup_folder):
        self.main_db = Path(main_db_path)

        # Make backup folder
        self.backup_folder = Path(backup_folder)
        self.backup_folder.mkdir(exist_ok=True)

        # Mirror DB path
        self.mirror_db = self.backup_folder / "inventory - BenchmarkMMS"

    def mirror_backup(self):
        """Create an exact mirror of the main database"""
        try:
            if not self.main_db.exists():
                print("Main DB not found. Mirror failed.")
                return False

            shutil.copy2(self.main_db, self.mirror_db)
            print(f"Mirror updated: {self.mirror_db}")
            return True

        except Exception as e:
            print(f"Mirror backup failed: {e}")
            return False
