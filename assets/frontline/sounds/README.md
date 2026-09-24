# Frontline sound effects

The WAV files in this folder are converted from recordings in the Xonotic game data
(https://github.com/xonotic/xonotic-data.pk3dir, folders `sound/weapons`, `sound/object`
and `sound/misc`) by `tools/frontline/prepare_sounds.py`, which mixes them to mono,
resamples them to 32 kHz, trims and normalizes them.

Xonotic's data is licensed under the GNU General Public License, version 3 or (at your
option) any later version. A copy of the license is in `GPL-3.0.txt` in this folder.
The source recordings are the files listed in `prepare_sounds.py`.
