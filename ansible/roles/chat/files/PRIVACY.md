# Chat Privacy — What You Should Know

## Your messages disappear when the box restarts

Hearth stores chat messages in an encrypted space that only exists while the box is
running. When the box powers off or restarts, the key to that space is gone forever.
There is no way to recover the messages afterwards — not even for the person who
runs the box.

## Nobody can read old messages after a reboot

The messages are stored on the box in a way that requires a secret key to read.
That key is created fresh each time the box starts up and is never saved anywhere.
Once the box goes off, the key vanishes and the messages with it.

## The box operator can see messages while the box is running

This is not end-to-end encrypted chat. While the box is on and running, someone
with access to the box itself could read the messages stored in the chat database.
If that concerns you, keep sensitive conversations for in-person settings.

## No accounts, no tracking

You choose a nickname to join — that is all. No email address, no password, no
account is created. The nickname exists only for your current session and disappears
when you leave.

## This box does not connect to the internet

Messages never leave this box. They are not sent to any outside service, logged
remotely, or shared with anyone beyond the people in this room.
