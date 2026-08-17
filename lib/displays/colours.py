"""Named RGB constants for Button text_colour/back_colour, kept in one place so a colour's
meaning - and every button that uses it - stays easy to find, rather than the same tuple being
repeated at each button call site. Buttons are grouped by what the colour signals rather than
by screen, since unrelated buttons on different screens intentionally share a colour to signal
the same kind of action (e.g. every destructive/dismissive button is DANGER).
"""

# Every button in the app uses white text.
BUTTON_TEXT = (255, 255, 255)

# Backgrounds
PRIMARY = (0, 0, 0)            # Click, Capture, Older/Newer - the main action of the current screen
NEUTRAL = (90, 90, 90)         # Print, Back, Edit, Clear, Done, generic secondary actions
UTILITY = (60, 60, 60)         # EV+/-, Stop/Page corner buttons, </> arrows, on-screen keyboard keys
CONFIRM = (0, 110, 0)          # Speak, Send, Done - affirmative actions
DANGER = (150, 30, 30)         # Stop, Cancel, Reject, Back (out of an AI edit)
PLAY = (0, 90, 150)            # Play
PUBLISH = (150, 90, 0)         # Publish menu, Flickr
PRESET = (60, 60, 90)          # AI-edit preset prompt buttons

# Per-publisher accents, keyed by publisher type - shown in the Publish destination menu
# (PUBLISH_MENU_COLOURS in lib/review_station.py).
BSKY = (0, 133, 255)
CUSTARD_CREAM_SERVER = (120, 90, 40)
