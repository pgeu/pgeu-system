#!/usr/bin/env python3
import subprocess
import os
import sys


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: check_video_audio.py <video_file> [video_file2 ...]")
        sys.exit(1)

    for v in sys.argv[1:]:
        sys.stdout.write("{}: ".format(os.path.basename(v)))
        sys.stdout.flush()

        r = subprocess.run([
            'ffmpeg',
            '-i', v,
            '-map', '0:a:0',
            '-af', 'astats',
            '-f', 'null',
            '-',
            ], capture_output=True, check=True)
        currchannel = 'unknown'
        for line in r.stderr.decode().splitlines():
            if 'Channel: ' in line:
                currchannel = line.split(':')[-1]
            if 'RMS peak dB' in line:
                val = line.split(':')[-1]
                if 'inf' in val:
                    print("Channel {} is silent.".format(currchannel))
                    break
        else:
            print("All channels have sound")
