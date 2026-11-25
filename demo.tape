# ─────────────────────────────────────────────────────────────
# Poseidon Agent — TUI Demo (VHS)
# Genera el GIF con:  vhs demo.tape
# ─────────────────────────────────────────────────────────────

Output docs/assets/tui-demo.gif

# Tema oscuro y profesional
Set Theme "Dracula"
Set FontSize 16
Set Width 1200
Set Height 720
Set Padding 24
Set Framerate 24
Set TypingSpeed 60ms

# 1. Abrir la interfaz
Type "poseidon tui"
Enter
Sleep 2s

# 2. Navegar a Phase 1a en el panel de fases
Down
Sleep 700ms

# 3. Enfocar el campo "Spec Path" y escribir un ejemplo
Tab
Tab
Type "specs/US-001.md"
Sleep 1s

# 4. Ejecutar la fase seleccionada
Ctrl+R
Sleep 2s

# 5. Mostrar un par de líneas de salida del log (simulación)
#    En la demo real estas líneas llegan del worker de PhaseRunner.
Type "Aislando Memoria para Goldfish"
Enter
Sleep 600ms
Type "Guardado en specs/US-001.spec.md"
Enter
Sleep 600ms

# 6. Pausa final para que el GIF no se corte de golpe
Sleep 3s
Ctrl+Q
Sleep 1s
