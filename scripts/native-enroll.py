"""Installer-only local device enrollment command (no secrets printed).

Must be run elevated by the installer once, before starting SCM/Agent.
"""
import argparse
import os
import sys

from native_enrollment import provision


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provision", action="store_true")
    args = parser.parse_args()
    if os.name != "nt" or not args.provision:
        parser.error("Windows installer must supply --provision")
    result = provision()
    print("Local Agent enrollment ready, generation " + str(result["generation"]))


if __name__ == "__main__":
    main()
