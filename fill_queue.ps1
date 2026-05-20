# ============================================================
#  Autonomía del bot caza-nichos.
#  1) Lanza el agente curador-cola (headless) para que ESCRIBA el
#     lote en _cola_lote.json (calidad-Claude, usa tu suscripción).
#  2) El script mete el lote en la cola de forma determinista.
#  Lo ejecuta el Programador de Tareas de Windows una vez al día.
# ============================================================
Set-Location C:\Users\34696\geopolitics-bot
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$log = "curador.log"

"==== $(Get-Date -Format 'yyyy-MM-dd HH:mm') curador START ====" | Out-File -Append -Encoding utf8 $log
Remove-Item _cola_lote.json -ErrorAction SilentlyContinue

$prompt = @'
Prepara un lote de contenido para los próximos 2 días. Cantidades:
4 listicle, 4 curiosity, 2 personality, 2 sexo. NO generes country_data.
Respeta las reglas de niche_generator.py y no repitas ángulos recientes.
Tu ÚNICO entregable: escribe con la herramienta Write un archivo llamado
_cola_lote.json con un array JSON de items, cada uno con esta forma exacta:
{"mode": "...", "tweets": ["...", "..."], "title": "etiqueta-unica", "source": "curador"}
Cada tweet <= 280 caracteres. NO ejecutes queue_manager.py: del add-file se
encarga el script. Termina cuando _cola_lote.json esté escrito.
'@

# 1) Generar el lote (el agente escribe _cola_lote.json)
claude -p $prompt --agent curador-cola --permission-mode bypassPermissions *>> $log

# 2) Ingerir el lote en la cola (determinista, lo hace el script)
if (Test-Path _cola_lote.json) {
    python queue_manager.py add-file _cola_lote.json *>> $log
} else {
    "ERROR: el curador no generó _cola_lote.json (no se añadió nada)." | Out-File -Append -Encoding utf8 $log
}
python queue_manager.py status *>> $log
"==== $(Get-Date -Format 'yyyy-MM-dd HH:mm') curador END ====" | Out-File -Append -Encoding utf8 $log
