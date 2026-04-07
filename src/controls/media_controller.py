"""Media controller — macOS app-specific AppleScript for media commands.

Uses Music/Spotify/Podcasts direct control instead of raw key codes
to avoid emoji keyboard and other macOS shortcut conflicts.
"""

import subprocess


class MediaController:
    def _run(self, script: str) -> None:
        try:
            subprocess.run(["osascript", "-e", script], check=True, timeout=3,
                           capture_output=True)
        except Exception as exc:
            print(f"[media_controller] AppleScript failed: {exc}")

    def play_pause(self) -> None:
        self._run("""
            if application "Music" is running then
                tell application "Music" to playpause
            else if application "Spotify" is running then
                tell application "Spotify" to playpause
            else if application "Podcasts" is running then
                tell application "Podcasts" to playpause
            end if
        """)

    def next_track(self) -> None:
        self._run("""
            if application "Music" is running then
                tell application "Music" to next track
            else if application "Spotify" is running then
                tell application "Spotify" to next track
            end if
        """)

    def prev_track(self) -> None:
        self._run("""
            if application "Music" is running then
                tell application "Music" to previous track
            else if application "Spotify" is running then
                tell application "Spotify" to previous track
            end if
        """)

    def volume_up(self) -> None:
        self._run(
            'set volume output volume (output volume of (get volume settings) + 10)'
        )

    def volume_down(self) -> None:
        self._run(
            'set volume output volume (output volume of (get volume settings) - 10)'
        )
