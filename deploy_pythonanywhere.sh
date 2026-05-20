#!/bin/bash
# Ejecutar este script desde una consola Bash en PythonAnywhere
# Uso: bash deploy_pythonanywhere.sh TU_USUARIO_PA

PA_USER=${1:?"Uso: bash deploy_pythonanywhere.sh TU_USUARIO_PA"}
PROJECT_DIR="/home/$PA_USER/geopolitics-bot"
VENV_DIR="/home/$PA_USER/.virtualenvs/geopolitics-env"

echo "=== Instalando virtualenv ==="
pip install virtualenv --quiet
python -m virtualenv "$VENV_DIR" --python=python3.10

echo "=== Instalando dependencias ==="
source "$VENV_DIR/bin/activate"
pip install -r "$PROJECT_DIR/requirements.txt" --quiet

echo "=== Verificando .env ==="
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "AVISO: No existe .env. Copia .env.example y rellena tus claves:"
    echo "  cp $PROJECT_DIR/.env.example $PROJECT_DIR/.env"
    echo "  nano $PROJECT_DIR/.env"
else
    echo ".env encontrado OK"
fi

echo ""
echo "=== Despliegue listo ==="
echo "Siguiente paso: ve a la pestaña 'Tasks' en PythonAnywhere y crea una Always-on task con:"
echo ""
echo "  $VENV_DIR/bin/python $PROJECT_DIR/main.py"
echo ""
echo "Si tienes cuenta gratuita (no soporta Always-on tasks), usa la tarea programada"
echo "cada hora con el script runner_scheduled.py en su lugar."
