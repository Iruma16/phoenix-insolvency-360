#!/bin/bash
# Script de validación para Fase 2 de Phoenix Legal

set -e

echo "🧪 Validando Fase 2..."
echo ""

# Activar entorno virtual
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "❌ Error: No se encontró .venv"
    exit 1
fi

# Test 1: Imports
echo "1️⃣  Verificando imports..."
python -c "
from app.core.logger import get_logger
from app.core.monitoring import get_monitor
print('   ✅ Logging')
print('   ✅ Monitoring')
"

# Test 2: Logging funcional
echo ""
echo "2️⃣  Verificando logging..."
python -c "
from app.core.logger import get_logger
import json

logger = get_logger()
logger.info('Test', case_id='TEST_001', action='test')
print('   ✅ Logging funcional')
"

# Test 3: Monitoring funcional
echo ""
echo "3️⃣  Verificando monitoring..."
python -c "
from app.core.monitoring import get_monitor

monitor = get_monitor()
with monitor.track_phase('test_phase', case_id='TEST_001'):
    pass

metrics = monitor.get_metrics()
assert 'test_phase' in metrics['phase_times']
print('   ✅ Monitoring funcional')
"

# Test 4: Tests unitarios
echo ""
echo "4️⃣  Ejecutando tests unitarios..."
pytest tests/test_logging.py tests/test_monitoring.py -q

echo ""
echo "✅ FASE 2 VALIDADA CORRECTAMENTE"
echo ""
echo "Sistema listo para:"
echo "  - Iniciar UI web: streamlit run app/ui/streamlit_mvp.py"
echo "  - Ver logs: tail -f clients_data/logs/phoenix_legal.log"
echo "  - Ejecutar tests: pytest tests/ -v"
echo ""

