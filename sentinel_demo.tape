Output "sentinel_demo.mp4"

Set Shell "bash"
Set FontSize 20
Set Width 1280
Set Height 720
Set Padding 30
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 50ms

# Vorbereitung im Hintergrund
Hide
Type "mkdir -p /tmp/demo_project && cd /tmp/demo_project && clear"
Enter
Show

# Szene 1: Ordner mit Sentinel schützen
Type "sentinel init 5"
Enter
Sleep 2s

# Szene 2: Wichtige Datei anlegen
Type "cat << 'CODE' > app.py"
Enter
Type "def calculate_payroll():"
Enter
Type "    # 500 lines of critical business logic..."
Enter
Type "    return {'status': 'success', 'payout': 42000}"
Enter
Type "CODE"
Enter
Sleep 1s
Type "cat app.py"
Enter
Sleep 3s

# Szene 3: Der Schock - Ein KI-Agent überschreibt/kürzt die Datei
Type "# ALERT: AI Agent hallucinated and truncated the code!"
Enter
Sleep 1s
Type "echo '// ... rest of implementation unchanged ...' > app.py"
Enter
Sleep 1s
Type "cat app.py"
Enter
Sleep 3s

# Szene 4: Rettung - Sentinel aufrufen
Type "sentinel"
Enter
Sleep 4s

# Szene 5: 1-Klick-Restore
Type "sentinel restore 1"
Enter
Sleep 2s

# Szene 6: Der Beweis - Alles ist wieder da!
Type "cat app.py"
Enter
Sleep 3s
