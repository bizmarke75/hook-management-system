import os
import glob

def rename_shots(target_dir=r"C:\renders\dear_me"):
    """
    Renames all MP4 files in target_dir to shot1.mp4, shot2.mp4, ..., shotN.mp4
    ordered chronologically by creation/modification time.
    """
    if not os.path.exists(target_dir):
        print(f"❌ Directory not found: {target_dir}")
        return

    # Find all mp4 files
    mp4_files = sorted(glob.glob(os.path.join(target_dir, "*.mp4")), key=os.path.getmtime)
    
    if not mp4_files:
        print(f"⚠️ No MP4 files found in {target_dir}")
        return

    print(f"Found {len(mp4_files)} MP4 file(s) in {target_dir}.\nRenaming in chronological order...")

    # Step 1: Rename to temporary names to prevent collision if target filenames exist
    temp_files = []
    for idx, old_path in enumerate(mp4_files, start=1):
        dir_name, old_name = os.path.split(old_path)
        temp_name = f"_temp_shot_{idx}.mp4"
        temp_path = os.path.join(dir_name, temp_name)
        os.rename(old_path, temp_path)
        temp_files.append((temp_path, old_name, idx))

    # Step 2: Rename from temp names to shot1.mp4, shot2.mp4, etc.
    for temp_path, old_name, idx in temp_files:
        dir_name = os.path.dirname(temp_path)
        new_name = f"shot{idx}.mp4"
        new_path = os.path.join(dir_name, new_name)
        os.rename(temp_path, new_path)
        print(f"  🔄 Renamed: {old_name} ➔ {new_name}")

    print("\n✅ All MP4 files successfully renamed to shot1.mp4 ... shotN.mp4!")

if __name__ == "__main__":
    rename_shots()
