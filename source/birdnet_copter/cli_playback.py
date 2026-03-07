"""
CLI playback with keyboard control.
Extracted from the former cli.py to keep main.py concise.
"""

import time
from pathlib import Path
from typing import List, Dict

import sounddevice as sd
import soundfile as sf
from loguru import logger

from .player import AudioPlayer
from .keyboard_control import KeyboardController


def cli_playback(
    db_path: Path,
    detections: List[Dict],
    language_code: str,
    filter_context: dict,
    pm_seconds: float,
    use_sci: bool,
) -> None:
    """
    CLI playback with keyboard control.

    Args:
        db_path: Path to database.
        detections: List of detections to play.
        language_code: Language code for TTS.
        filter_context: Filter context dict.
        pm_seconds: PM buffer in seconds.
        use_sci: Use scientific names for TTS.
    """
    if not detections:
        logger.error("No detections to play")
        return

    # Minimal audio options for CLI playback
    audio_options = {
        'say_audio_number': True,
        'say_id': False,
        'say_confidence': False,
        'bird_name_option': 'scientific' if use_sci else 'local',
        'speech_speed': 1.0,
        'speech_loudness': 0,
        'noise_reduce_strength': None,
    }

    player = AudioPlayer(db_path, pm_seconds)
    controller = KeyboardController()

    current_index = 0
    is_playing = False
    current_audio_data = None
    current_sample_rate = None

    print()
    print("=" * 80)
    print(f"Playing {len(detections)} detection(s)")
    print("=" * 80)
    print("Controls: SPACE=Pause/Replay, ←=Previous, →=Next, q=Quit")
    print("=" * 80)
    print()

    try:
        while current_index < len(detections):
            detection = detections[current_index]

            if current_audio_data is None or not is_playing:
                try:
                    conf_pct = detection['confidence'] * 100
                    print(
                        f"\r[{current_index + 1}/{len(detections)}] Loading: "
                        f"#{detection['detection_id']} – "
                        f"{detection.get('local_name', detection['scientific_name'])} "
                        f"({conf_pct:.1f}%)",
                        end='', flush=True
                    )

                    audio_bytes = player.prepare_detection_audio(
                        detection,
                        audio_number=current_index + 1,
                        language_code=language_code,
                        filter_context=filter_context,
                        audio_options=audio_options,
                        disable_tts=False,
                    )
                    current_audio_data, current_sample_rate = sf.read(audio_bytes)

                except Exception as e:
                    logger.error(
                        f"\nFailed to prepare detection "
                        f"#{detection['detection_id']}: {e}"
                    )
                    current_index += 1
                    current_audio_data = None
                    continue

                conf_pct = detection['confidence'] * 100
                print(
                    f"\r[{current_index + 1}/{len(detections)}] Playing: "
                    f"#{detection['detection_id']} – "
                    f"{detection.get('local_name', detection['scientific_name'])} "
                    f"({conf_pct:.1f}%)       ",
                    end='', flush=True
                )
                sd.play(current_audio_data, current_sample_rate)
                is_playing = True

            while is_playing:
                key = controller.get_key_nonblocking()

                if key == 'space':
                    if sd.get_stream().active:
                        sd.stop()
                        is_playing = False
                        print(
                            "\r[PAUSED] Press SPACE to replay, "
                            "←/→ to navigate, q to quit",
                            end='', flush=True
                        )
                    else:
                        sd.play(current_audio_data, current_sample_rate)
                        is_playing = True
                        conf_pct = detection['confidence'] * 100
                        print(
                            f"\r[{current_index + 1}/{len(detections)}] Playing: "
                            f"#{detection['detection_id']} – "
                            f"{detection.get('local_name', detection['scientific_name'])} "
                            f"({conf_pct:.1f}%)       ",
                            end='', flush=True
                        )

                elif key == 'left':
                    sd.stop()
                    current_index = max(0, current_index - 1)
                    current_audio_data = None
                    is_playing = False
                    break

                elif key == 'right':
                    sd.stop()
                    current_index += 1
                    current_audio_data = None
                    is_playing = False
                    break

                elif key == 'q':
                    sd.stop()
                    print("\n\nPlayback stopped by user.")
                    return

                if not sd.get_stream().active:
                    is_playing = False
                    current_index += 1
                    current_audio_data = None
                    break

                time.sleep(0.05)

        print("\n\nPlayback finished!")

    except KeyboardInterrupt:
        sd.stop()
        print("\n\nPlayback interrupted.")
    except Exception as e:
        logger.error(f"Playback error: {e}")
        sd.stop()
    finally:
        controller.stop()