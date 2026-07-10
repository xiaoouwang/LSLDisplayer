import json
from collections import defaultdict

import pyxdf
import numpy as np
import pandas as pd
import wave
from pathlib import Path

xdf_file = "newtest.xdf"
# This creates a Path object representing the "exports" directory.
output_dir = Path("exports")
# This creates the "exports" directory if it doesn't already exist.
output_dir.mkdir(exist_ok=True)

streams, header = pyxdf.load_xdf(xdf_file)

print(f"Nombre de streams trouvés : {len(streams)}\n")

manifest = {
    "source_file": str(Path(xdf_file).resolve()),
    "streams": [],
}


def unwrap_lsl_value(value):
    if isinstance(value, list) and len(value) == 1:
        return value[0]
    return value


def normalize_desc_dict(data):
    if isinstance(data, defaultdict):
        data = dict(data)
    if isinstance(data, dict):
        return {str(key): normalize_desc_dict(value) for key, value in data.items()}
    if isinstance(data, list):
        return [normalize_desc_dict(value) for value in data]
    return data


def parse_resolution_block(block):
    if not block:
        return None
    if isinstance(block, list):
        block = block[0]
    return {
        "width": int(float(unwrap_lsl_value(block.get("X", 0)))),
        "height": int(float(unwrap_lsl_value(block.get("Y", 0)))),
    }


def extract_display_setup(info):
    desc = info.get("desc")
    if not desc or not desc[0]:
        return None

    desc = normalize_desc_dict(desc[0])
    setup = desc.get("setup")
    if not setup:
        return None
    if isinstance(setup, list):
        setup = setup[0]

    display = setup.get("display")
    if not display:
        return None
    if isinstance(display, list):
        display = display[0]

    primary = parse_resolution_block(display.get("resolution_primary"))
    virtual = parse_resolution_block(display.get("resolution_virtual"))
    monitor_count = unwrap_lsl_value(display.get("monitors"))

    if not primary and not virtual:
        return None

    return {
        "monitor_count": int(monitor_count) if monitor_count is not None else None,
        "primary": primary,
        "virtual_origin": virtual,
    }


def build_monitor_layout(display_setup):
    primary = display_setup.get("primary") or {"width": 1920, "height": 1200}
    virtual = display_setup.get("virtual_origin") or {"width": 0, "height": 0}
    primary_height = primary["height"]
    monitors = []

    if virtual["width"] < 0:
        monitors.append(
            {
                "label": "Display 1",
                "x": virtual["width"],
                "y": virtual["height"],
                "width": abs(virtual["width"]),
                "height": primary_height,
            }
        )

    monitors.append(
        {
            "label": "Primary",
            "x": 0,
            "y": 0,
            "width": primary["width"],
            "height": primary["height"],
        }
    )

    return monitors


def monitor_label_for_point(x, y, monitors):
    if not monitors:
        return ""
    for monitor in monitors:
        if (
            monitor["x"] <= x < monitor["x"] + monitor["width"]
            and monitor["y"] <= y < monitor["y"] + monitor["height"]
        ):
            return monitor["label"]
    return "Unknown"


def export_audio_wav(data, sample_rate, channel_count, output_path):
    """Write LSL audio samples (float, roughly -1..1) to a WAV file."""
    audio = np.asarray(data, dtype=np.float64)
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)

    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype(np.int16)

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(channel_count)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(pcm.tobytes())


for i, stream in enumerate(streams):
    info = stream["info"]

    name = info["name"][0]
    stream_type = info["type"][0]
    channel_count = int(info["channel_count"][0])
    nominal_srate = float(info["nominal_srate"][0])

    data = stream["time_series"]
    timestamps = stream["time_stamps"]

    print(f"[{i}] {name}")
    print(f"    Type : {stream_type}")
    print(f"    Canaux : {channel_count}")
    print(f"    Fréquence : {nominal_srate} Hz")
    print(f"    Échantillons : {len(timestamps)}\n")

    # Si le stream est vide
    if len(timestamps) == 0:
        continue

    safe_name = name.replace(" ", "_").replace("/", "_")
    start_time = float(timestamps[0])
    end_time = float(timestamps[-1])
    stream_entry = {
        "index": i,
        "name": name,
        "type": stream_type,
        "channel_count": channel_count,
        "nominal_srate": nominal_srate,
        "start_time": start_time,
        "end_time": end_time,
        "sample_count": len(timestamps),
    }

    display_setup = extract_display_setup(info)
    if display_setup:
        stream_entry["display"] = {
            **display_setup,
            "monitors": build_monitor_layout(display_setup),
        }

    if stream_type.lower() == "audio" and nominal_srate > 0:
        output_path = output_dir / f"{i}_{safe_name}.wav"
        export_audio_wav(data, nominal_srate, channel_count, output_path)
        duration_s = len(timestamps) / nominal_srate
        stream_entry["file"] = output_path.name
        manifest["streams"].append(stream_entry)
        print(f"Exporté vers : {output_path} ({duration_s:.2f} s)\n")
        continue

    # Noms de colonnes
    columns = [f"ch_{j+1}" for j in range(channel_count)]

    # Cas 1 : stream multicanal classique
    if channel_count > 1:
        df = pd.DataFrame(data, columns=columns)

    # Cas 2 : stream à un seul canal
    else:
        df = pd.DataFrame(data, columns=["value"])

    df.insert(0, "timestamp", timestamps)

    monitors = stream_entry.get("display", {}).get("monitors")
    if monitors and channel_count >= 2:
        xs = df["ch_1"].astype(float)
        ys = df["ch_2"].astype(float)
        df.insert(
            1,
            "monitor",
            [monitor_label_for_point(x, y, monitors) for x, y in zip(xs, ys)],
        )

    output_path = output_dir / f"{i}_{safe_name}.csv"
    stream_entry["file"] = output_path.name
    manifest["streams"].append(stream_entry)

    df.to_csv(output_path, index=False, encoding="utf-8")
    print(f"Exporté vers : {output_path}\n")

manifest_path = output_dir / "manifest.json"
manifest_path.write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
print(f"Manifest écrit vers : {manifest_path}\n")