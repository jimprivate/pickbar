# VHS tape for the pickbar demo GIF.
# Render: docker build -t pickbar-vhs demo && docker run --rm -v "$PWD:/vhs" pickbar-vhs demo/demo.tape

Output demo.gif

Set FontSize 20
Set FontFamily "Noto Sans Mono CJK TC"
Set Width 1000
Set Height 560
Set Padding 16
Set TypingSpeed 60ms
Set Theme "Dracula"

Type "python3 -m pickbar"
Enter
Sleep 1.5s

# pick: move the highlight bar, wrap a little, confirm
Down
Sleep 600ms
Down
Sleep 600ms
Up
Sleep 600ms
Enter
Sleep 1.2s

# pick_multi: Space toggles and advances, CJK label included
Space
Sleep 500ms
Space
Sleep 500ms
Down
Sleep 400ms
Space
Sleep 800ms
Enter
Sleep 1.2s

# pick_dir: type-to-filter, dive into demo/, select it
Type "de"
Sleep 900ms
Enter
Sleep 900ms
Enter
Sleep 2.5s
