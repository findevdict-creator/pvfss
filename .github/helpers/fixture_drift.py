"""GEN-02 fixture drift check.

Compares every fixture file in the working tree (freshly exported by CI) with the committed
version, ignoring the volatile "modified" timestamp. Exits 1 and prints the drifted records
when they differ, or when export created a fixture file that is not committed.
"""

import json
import subprocess
import sys
from pathlib import Path

FIXTURES = Path("pvfss/fixtures")
VOLATILE = {"modified", "creation"}


def normalise(records):
	out = {}
	for rec in records:
		rec = {k: v for k, v in rec.items() if k not in VOLATILE}
		out[rec.get("name")] = rec
	return out


def committed(path):
	try:
		text = subprocess.run(
			["git", "show", f"HEAD:{path.as_posix()}"], capture_output=True, text=True, check=True
		).stdout
	except subprocess.CalledProcessError:
		return None
	return json.loads(text)


def main():
	drift = []
	for path in sorted(FIXTURES.glob("*.json")):
		old = committed(path)
		if old is None:
			drift.append(f"{path}: exported but not committed")
			continue
		new, old = normalise(json.loads(path.read_text())), normalise(old)
		for name in sorted(set(new) | set(old), key=str):
			if new.get(name) != old.get(name):
				drift.append(f"{path}: {name}")
	if drift:
		print("Fixture drift (customisations made in Desk but not committed):")
		print("\n".join(f"  - {d}" for d in drift))
		sys.exit(1)
	print("No fixture drift.")


if __name__ == "__main__":
	main()
