"""
Thread-based keyboard input for CLI playback control.
"""

import sys
import tty
import termios
import threading
import queue
from typing import Optional
from loguru import logger

try:
    import readchar
    READCHAR_AVAILABLE = True
except ImportError:
    READCHAR_AVAILABLE = False
    logger.warning("readchar not installed")


class KeyboardController:
    """Thread-based keyboard input handler."""
    
    def __init__(self):
        """Initialize keyboard controller with input thread."""
        self.key_queue = queue.Queue()
        self.running = True
        self.old_settings = None
        
        # Save and set terminal mode
        if sys.stdin.isatty():
            try:
                self.old_settings = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            except Exception as e:
                logger.warning(f"Could not set terminal mode: {e}")
        
        # Start keyboard input thread
        self.thread = threading.Thread(target=self._input_thread, daemon=True)
        self.thread.start()
        logger.debug("Keyboard controller started")
    
    def _input_thread(self):
            """Background thread that reads keyboard input."""
            while self.running:
                try:
                    if not sys.stdin.isatty():
                        break
                    
                    # Blocking read (OK in thread)
                    char = sys.stdin.read(1)
                    
                    # Handle escape sequences for arrow keys
                    if char == '\x1b':
                        # ESC detected - read rest of sequence
                        import select
                        
                        # Wait up to 100ms for next character
                        if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                            next_char = sys.stdin.read(1)
                            char += next_char
                            
                            # If it's '[', read the final character
                            if next_char == '[':
                                if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                                    final_char = sys.stdin.read(1)
                                    char += final_char
                    
                    # Map to key name
                    key = self._map_key(char)
                    if key:
                        self.key_queue.put(key)
                    else:
                        # Debug: show unmapped sequences
                        logger.debug(f"Unmapped key sequence: {repr(char)}")
                        
                except Exception as e:
                    if self.running:
                        logger.debug(f"Input thread error: {e}")
                    break
    
    def _map_key(self, char: str) -> Optional[str]:
        """Map raw character(s) to key name."""
        key_map = {
            '\x1b[D': 'left',
            '\x1b[C': 'right',
            '\x1b[A': 'up',
            '\x1b[B': 'down',
            ' ': 'space',
            'q': 'q',
            'Q': 'q',
            '\x03': 'ctrl_c',  # Ctrl+C
        }
        return key_map.get(char, char if len(char) == 1 else None)
    
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
        self.restore_terminal()
    
    def restore_terminal(self):
        """Restore original terminal settings."""
        if self.old_settings and sys.stdin.isatty():
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
                logger.debug("Terminal settings restored")
            except Exception as e:
                logger.warning(f"Could not restore terminal: {e}")
    
    def __del__(self):
        """Cleanup on deletion."""
        self.stop()

def test_keyboard():
    """Test keyboard controller."""
    import time
    
    # Enable debug logging
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    
    print("Keyboard Controller Test (Thread-based)")
    print("=" * 60)
    print("Press keys:")
    print("  SPACE    - Space bar")
    print("  ← / →    - Arrow keys")
    print("  q        - Quit")
    print("=" * 60)
    print()
    
    controller = KeyboardController()
    
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