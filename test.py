import scratchattach as sa
import time
import os
import threading
import sys

# --- IMPORTANT: Import the specific exception ---
try:
    from scratchattach.utils.exceptions import LoginFailure
except ImportError:
    print("Error: Could not import LoginFailure from scratchattach.utils.exceptions.")
    print("Please ensure scratchattach is installed correctly and is up to date.")
    print("Try running: pip install -U scratchattach")
    exit()

# --- Configuration ---

# --- Hardcoded Credentials (Less Secure - Replace with your actual credentials) ---
USERNAME = "Techtonic17"  # <--- PUT YOUR SCRATCH USERNAME HERE (Case-Sensitive)
PASSWORD = "Jack$$1717"  # <--- PUT YOUR SCRATCH PASSWORD HERE
# ---------------------------------------------------------------------------

USER_TO_MONITOR = "griffpatch"      # Replace with the username whose projects you want to monitor
NOTIFICATION_SOUND = "notification.wav"  # Optional: Path to a sound file (e.g., "C:/sounds/notify.wav" or relative path)
CHECK_INTERVAL = 5                # How often to fetch project data (seconds).
DISPLAY_INTERVAL = 60              # How often to update the summary display (seconds)
PROJECT_FETCH_LIMIT = 200       # Max projects to fetch per cycle

# --- Global Lock for Shared Data ---
stats_lock = threading.Lock()
project_stats = {} # Shared dictionary for project statistics

# --- Authentication and Client Setup ---
try:
    print(f"Attempting to log in as '{USERNAME}'...")
    session = sa.login(USERNAME, PASSWORD)
    print("Logged in successfully!")
except LoginFailure as e:
    print("-" * 30)
    print(f"Login failed: {e}") # The library's error message is informative
    print("\nPlease check:")
    print(f"1. Is the hardcoded USERNAME ('{USERNAME}') correct (check spelling, case sensitivity)?")
    print("2. Is the hardcoded PASSWORD correct?")
    print("3. Can you log in manually via the Scratch website (scratch.mit.edu) from this machine?")
    print("4. Is there a CAPTCHA or account issue on the Scratch website?")
    print("5. (Less likely) Potential temporary network/IP block.")
    print("-" * 30)
    exit()
except Exception as e:
    print(f"An unexpected error occurred during login: {e}")
    exit()

# --- Helper Function for Playing Sound (Optional) ---
def play_sound(sound_file):
    """Plays a sound file (if available). Requires the 'playsound' library."""
    if not sound_file or not os.path.exists(sound_file):
        if not hasattr(play_sound, "warning_printed"):
             if sound_file:
                 print(f"Info: Sound file '{sound_file}' not found or not specified. Sound notifications disabled.")
             play_sound.warning_printed = True
        return
    try:
        from playsound import playsound
        sound_thread = threading.Thread(target=playsound, args=(sound_file,), daemon=True)
        sound_thread.start()
    except ImportError:
         if not hasattr(play_sound, "warning_printed"):
             print("Info: 'playsound' library not found. Sound notifications disabled. Install with: pip install playsound")
             play_sound.warning_printed = True
    except Exception as e:
         if not hasattr(play_sound, "warning_printed"):
            print(f"Error playing sound '{sound_file}': {e}")
            play_sound.warning_printed = True


# --- Function to Fetch Project Data (Runs in a separate thread) ---
def fetch_project_data(username_to_monitor, stop_event):
    """Fetches project data, updates stats, and prints a summary of changes for the cycle."""
    global project_stats

    try:
        print(f"Connecting to target user '{username_to_monitor}'...")
        user = session.connect_user(username_to_monitor)
        if not user or not user.does_exist():
            print(f"Error: Could not find or connect to user '{username_to_monitor}'. Stopping data fetching.")
            stop_event.set()
            return
    except Exception as e:
        print(f"Error connecting to target user '{username_to_monitor}': {e}. Stopping data fetching.")
        stop_event.set()
        return

    print(f"Starting to monitor projects for user: {username_to_monitor} (checking every {CHECK_INTERVAL}s)")

    while not stop_event.is_set():
        start_time = time.monotonic()
        fetched_projects = []
        fetch_error = False
        try:
            print(f"Fetching projects (limit {PROJECT_FETCH_LIMIT})...", end="")
            sys.stdout.flush()
            fetched_projects = user.projects(limit=PROJECT_FETCH_LIMIT)
            print(f" Found {len(fetched_projects)}.")
            if not fetched_projects:
                print(f"No projects found for user {username_to_monitor} this cycle.")

        except Exception as e:
            print(f"\nError fetching project list for {username_to_monitor}: {e}")
            fetch_error = True
            # Still wait before next attempt
            if stop_event.wait(CHECK_INTERVAL): break
            continue # Skip update logic for this cycle if list fetch failed

        # --- Process fetched projects and detect changes for *this cycle* ---
        current_project_ids = set()
        cycle_changes = {} # Store changes for this cycle: {project_id: {'title': title, 'like_change': x, 'fav_change': y, 'new_likes': nl, 'new_favs': nf}}
        projects_updated_count = 0
        projects_failed_count = 0

        if fetched_projects:
            print(f"Updating details for {len(fetched_projects)} projects...")
            for project in fetched_projects:
                if stop_event.is_set(): break

                project_id = project.id
                if not project_id: continue

                current_project_ids.add(project_id)
                try:
                    project.update() # Get latest data
                    projects_updated_count += 1

                                        # ...existing code...
                    
                    # --- Calculate Changes ---
                    with stats_lock:  # Lock needed for reading old state and writing new
                        # Get or initialize stats entry
                        stats_entry = project_stats.setdefault(project_id, {
                            "title": project.title or f"Project {project_id}",
                            "likes": 0,
                            "favorites": 0,
                            "last_likes": -1,  # Marker for not yet initialized
                            "last_favorites": -1
                        })
                    
                        # Get current state *before* update for comparison
                        old_likes = stats_entry['likes']
                        old_favorites = stats_entry['favorites']
                        old_last_likes = stats_entry['last_likes']
                        old_last_favorites = stats_entry['last_favorites']
                    
                        # Get new state from fetched data
                        new_likes = project.loves if project.loves is not None else old_likes
                        new_favorites = project.favorites if project.favorites is not None else old_favorites
                        new_title = project.title or f"Project {project_id}"
                    
                        # Update the main stats immediately
                        stats_entry["title"] = new_title
                        stats_entry["likes"] = new_likes
                        stats_entry["favorites"] = new_favorites
                    
                        # Initialize last_likes/last_favorites properly on first successful fetch
                        if old_last_likes == -1 or old_last_favorites == -1:  # Check if uninitialized
                            stats_entry["last_likes"] = new_likes
                            stats_entry["last_favorites"] = new_favorites
                            like_change = 0
                            fav_change = 0
                        else:
                            # Calculate change based on the *previous* 'last known' value
                            like_change = new_likes - old_last_likes
                            fav_change = new_favorites - old_last_favorites
                    
                        # Store changes *for this cycle's report* if any occurred
                        if like_change > 0 or fav_change > 0:
                            cycle_changes[project_id] = {
                                'title': new_title,
                                'like_change': like_change,
                                'fav_change': fav_change,
                                'new_likes_total': new_likes,
                                'new_favs_total': new_favorites
                            }
                    
                    # ...existing code...



                except Exception as e:
                    projects_failed_count += 1
                    project_title_safe = project.title if project.title else f"ID {project_id}"
                    print(f"\nWarning: Error updating project {project_title_safe}: {e}")

            print(f"Finished updating stats. {projects_updated_count} success, {projects_failed_count} failed.")

        # --- Print Summary of Changes for THIS Cycle ---
        if cycle_changes:
            print("\n" + "=" * 15 + f" Changes Detected This Update Cycle ({time.strftime('%H:%M:%S')}) " + "=" * 15)
            # Sort changes by project title for consistent output
            sorted_change_ids = sorted(cycle_changes.keys(), key=lambda pid: cycle_changes[pid]['title'].lower())
            for pid in sorted_change_ids:
                changes = cycle_changes[pid]
                print(f"  Project: {changes['title']} ({pid})")
                if changes['like_change'] > 0:
                    print(f"    Likes:     +{changes['like_change']} (Now: {changes['new_likes_total']})")
                if changes['fav_change'] > 0:
                    print(f"    Favorites: +{changes['fav_change']} (Now: {changes['new_favs_total']})")
            print("=" * (30 + len(f" Changes Detected This Update Cycle ({time.strftime('%H:%M:%S')}) ")) + "\n")
            sys.stdout.flush()
            # Optionally play sound once for the whole batch of updates
            # play_sound(NOTIFICATION_SOUND) # Uncomment if you want one sound per batch

        # --- Update last_likes/last_favorites AFTER reporting cycle changes ---
        # This sets the baseline for the *next* cycle's comparison
        with stats_lock:
            for pid in current_project_ids: # Only update for projects seen this cycle
                 if pid in project_stats:
                      stats = project_stats[pid]
                      # Update last known values to the current values we just fetched/set
                      stats['last_likes'] = stats['likes']
                      stats['last_favorites'] = stats['favorites']


        # --- Remove old projects ---
        with stats_lock:
            current_tracked_ids = set(project_stats.keys())
            removed_ids = current_tracked_ids - current_project_ids
            if removed_ids:
                 print(f"Removing {len(removed_ids)} projects no longer found...")
                 for removed_id in removed_ids:
                    if removed_id in project_stats:
                        del project_stats[removed_id]

        # --- Wait for the next cycle ---
        elapsed_time = time.monotonic() - start_time
        wait_time = max(0, CHECK_INTERVAL - elapsed_time)
        print(f"Fetch cycle took {elapsed_time:.2f}s. Waiting {wait_time:.2f}s for next check.")
        if stop_event.wait(wait_time):
             break


# --- Function to Display Summary (Runs in a separate thread) ---
# (No changes needed in this function)
def display_summary(stop_event):
    """Displays a summary of project stats periodically."""
    global project_stats
    last_displayed_time = 0

    while not stop_event.is_set():
        current_time = time.time()

        if current_time - last_displayed_time >= DISPLAY_INTERVAL:
            print("\n" * 80)
            print("--- Live Scratch Project Tracker ---")
            print(f"--- Monitoring User: {USER_TO_MONITOR} ---")
            print(f"--- Logged in as: {USERNAME} ---") # Display logged in user
            print(f"--- Last Display Update: {time.strftime('%Y-%m-%d %H:%M:%S')} ---") # Clarified purpose
            print("-" * 40) # Wider separator

            with stats_lock:
                current_stats_copy = dict(project_stats)

            if not current_stats_copy:
                print("\nNo project data available yet or fetch in progress...")
            else:
                total_likes = 0
                total_favorites = 0
                sorted_project_ids = sorted(
                    current_stats_copy.keys(),
                    key=lambda pid: current_stats_copy.get(pid, {}).get('title', '').lower() # Sort case-insensitively
                )

                print(f"Current Stats for {len(sorted_project_ids)} tracked projects:") # Clarified purpose
                for project_id in sorted_project_ids:
                    stats = current_stats_copy.get(project_id) # Safely get stats
                    if not stats: continue # Skip if somehow missing after sorting

                    print(f"\n  Project: {stats.get('title', 'N/A')} ({project_id})")
                    likes = stats.get('likes', 'N/A')
                    favorites = stats.get('favorites', 'N/A')
                    print(f"    Likes: {likes}")
                    print(f"    Favorites: {favorites}")
                    total_likes += stats.get('likes', 0) # Add safely
                    total_favorites += stats.get('favorites', 0) # Add safely

                print("-" * 40)
                print(f"Total Likes Across Tracked: {total_likes}")
                print(f"Total Favorites Across Tracked: {total_favorites}")
                print("-" * 40)

            sys.stdout.flush()
            last_displayed_time = current_time

        if stop_event.wait(1): # Check stop event every second
             break


# --- Function to Monitor Changes and Play Notifications (Runs in the main thread) ---
# (This function remains largely the same, providing near real-time checks
# between the main fetch cycles. It now compares current 'likes'/'favorites'
# against 'last_likes'/'last_favorites' which are updated by the fetch thread)
def monitor_changes(stop_event):
    """Monitors for changes between fetch cycles and plays notifications."""
    global project_stats
    print("Change monitor started (checks between main updates)...") # Clarified purpose

    while not stop_event.is_set():
        # Acquire lock before reading stats
        with stats_lock:
            project_ids_snapshot = list(project_stats.keys())

            for project_id in project_ids_snapshot:
                if project_id not in project_stats: continue

                stats = project_stats[project_id]
                # Skip check if stats haven't been properly initialized by fetch thread
                if stats.get('last_likes', -1) == -1: continue

                project_title = stats.get('title', f'ID {project_id}')
                current_likes = stats.get('likes', 0)
                current_favorites = stats.get('favorites', 0)
                # Compare against the 'last known' values set by the *fetch* thread
                last_likes = stats.get('last_likes', 0)
                last_favorites = stats.get('last_favorites', 0)

                # NOTE: This check is based on the *most recently fetched data*
                # vs the *baseline set after the previous fetch*. Changes reported
                # here might be duplicates of the Cycle Summary Report if the
                # monitor runs right after a fetch completes, but could catch
                # very rapid changes between fetches.
                like_change = current_likes - last_likes
                fav_change = current_favorites - last_favorites

                notification_triggered = False

                if like_change > 0:
                    print(f"\n--- Monitor Change ---") # Indicate this is from monitor
                    print(f"  Project: '{project_title}'")
                    print(f"  Likes: +{like_change} (Cur: {current_likes}, LastFetchBaseline: {last_likes})")
                    print(f"------------------------")
                    sys.stdout.flush()
                    notification_triggered = True

                if fav_change > 0:
                    if not notification_triggered:
                         print(f"\n--- Monitor Change ---")
                         print(f"  Project: '{project_title}'")
                    print(f"  Favorites: +{fav_change} (Cur: {current_favorites}, LastFetchBaseline: {last_favorites})")
                    print(f"------------------------")
                    sys.stdout.flush()
                    notification_triggered = True

                if notification_triggered:
                    play_sound(NOTIFICATION_SOUND)
                    # IMPORTANT: We *don't* update last_likes/favs here.
                    # The fetch_project_data thread is responsible for setting
                    # the baseline 'last_' values after its cycle.

        # Short sleep outside the lock
        if stop_event.wait(1.0): # Check slightly less frequently (e.g., 1s)
            break


# --- Main Execution ---
if __name__ == "__main__":

    stop_event = threading.Event()

    print("Initializing threads...")
    data_thread = threading.Thread(
        target=fetch_project_data, args=(USER_TO_MONITOR, stop_event), daemon=True
    )
    display_thread = threading.Thread(
        target=display_summary, args=(stop_event,), daemon=True
    )
    # Decide if you still need the high-frequency monitor thread.
    # If the cycle summary from fetch_project_data is enough, you can comment this out.
    monitor_thread = threading.Thread(
        target=monitor_changes, args=(stop_event,), daemon=True
    )

    data_thread.start()
    display_thread.start()
    monitor_thread.start() # Start the high-frequency monitor if desired

    # Keep main thread alive to handle Ctrl+C
    try:
        while not stop_event.is_set():
            # Just wait, threads are doing the work
            # Check event periodically to allow faster exit if threads signal stop
            if stop_event.wait(1.0):
                 break # Exit loop if stop event is set by threads
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Stopping threads...")
        stop_event.set()
    except Exception as e:
        print(f"\nAn unexpected error occurred in the main loop: {e}")
        stop_event.set()
    finally:
        print("Waiting for threads to finish...")
        # Wait for threads to finish (with timeout)
        data_thread.join(timeout=CHECK_INTERVAL + 5)
        display_thread.join(timeout=5)
        monitor_thread.join(timeout=5) # Join the monitor thread too
        print("Monitoring finished.")