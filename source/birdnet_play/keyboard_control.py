"""
Thread-based keyboard input for CLI playback control using readchar.
"""

import sys
import threading
import queue
from typing import Optional
from loguru import logger

try:
    import readchar
    READCHAR_AVAILABLE = True
except ImportError:
    READCHAR_AVAILABLE = False
    logger.error("readchar not installed - keyboard control will not work!")
    logger.error("Install with: poetry add readchar")


class KeyboardController:
    """Thread-based keyboard input handler using readchar."""
    
    def __init__(self):
        """Initialize keyboard controller with input thread."""
        if not READCHAR_AVAILABLE:
            raise RuntimeError("readchar not installed - cannot initialize keyboard controller")
        
        self.key_queue = queue.Queue()
        self.running = True
        
        # Start keyboard input thread
        self.thread = threading.Thread(target=self._input_thread, daemon=True)
        self.thread.start()
        logger.debug("Keyboard controller started")
    
    def _input_thread(self):
        """Background thread that reads keyboard input using readchar."""
        while self.running:
            try:
                # Blocking read using readchar (handles escape sequences automatically)
                key = readchar.readkey()
                
                # Map to our key names
                mapped_key = self._map_key(key)
                if mapped_key:
                    self.key_queue.put(mapped_key)
                    
            except Exception as e:
                if self.running:
                    logger.debug(f"Input thread error: {e}")
                break
    
    def _map_key(self, key: str) -> Optional[str]:
        """Map readchar key to our key names."""
        # readchar constants for special keys
        key_map = {
            readchar.key.LEFT: 'left',
            readchar.key.RIGHT: 'right',
            readchar.key.UP: 'up',
            readchar.key.DOWN: 'down',
            readchar.key.ENTER: 'enter',
            readchar.key.ESC: 'esc',
            readchar.key.BACKSPACE: 'backspace',
            ' ': 'space',
            'q': 'q',
            'Q': 'q',
            '\x03': 'ctrl_c',  # Ctrl+C
        }
        
        return key_map.get(key, key if len(key) == 1 else None)
    
    def get_key_nonblocking(self) -> Optional[str]:
        """
        Get key from queue (non-blocking).
        
        Returns:
            Key name or None if queue is empty
        """
        try:
            return self.key_queue.get_nowait()
        except queue.Empty:
            return None
    
    def stop(self):
        """Stop the keyboard controller."""
        self.running = False
    
    def __del__(self):
        """Cleanup on deletion."""
        self.stop()


def test_keyboard():
    """Test keyboard controller."""
    import time
    
    # Enable debug logging
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    
    print("Keyboard Controller Test (readchar-based)")
    print("=" * 60)
    print("Press keys:")
    print("  SPACE    - Space bar")
    print("  ← / →    - Arrow keys")
    print("  q        - Quit")
    print("=" * 60)
    print()
    
    try:
        controller = KeyboardController()
    except RuntimeError as e:
        print(f"Error: {e}")
        return
    
    try:
        print("Waiting for input...\n")
        while True:
            key = controller.get_key_nonblocking()
            
            if key:
                print(f"✓ Key detected: '{key}'")
                
                if key == 'q':
                    print("\nQuit detected, exiting...")
                    break
                elif key == 'space':
                    print("  → SPACE pressed")
                elif key == 'left':
                    print("  → LEFT arrow")
                elif key == 'right':
                    print("  → RIGHT arrow")
            
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        print("\nTest interrupted")
    finally:
        controller.stop()


if __name__ == "__main__":
    test_keyboard()