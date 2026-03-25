#!/bin/bash
# volume-teardown.sh — Hearth chat encrypted volume teardown.
#
# Run on stop/shutdown by hearth-volume.service. Unmounts the chat volume and
# closes the dm-crypt mapping. Errors are ignored — if either step fails the
# system is shutting down anyway.

MAPPING="chat-volume"
MOUNT="/srv/cafebox/chat-data"

umount "$MOUNT" 2>/dev/null || true
cryptsetup close "$MAPPING" 2>/dev/null || true
