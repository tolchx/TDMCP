#!/bin/sh
# Instala los hooks mecánicos del gate en .git/hooks (git no versiona .git/hooks,
# por eso viven en scripts/hooks/ y se copian con este instalador).
# Uso:  sh scripts/install_hooks.sh
set -e
cd "$(dirname "$0")/.."
cp scripts/hooks/pre-commit .git/hooks/pre-commit
cp scripts/hooks/pre-push   .git/hooks/pre-push
chmod +x .git/hooks/pre-commit .git/hooks/pre-push
echo "hooks instalados:"
echo "  .git/hooks/pre-commit  -> exige .git/gate-allowlist (lo escribe loop_gate.py --do-commit; vence 60 min)"
echo "  .git/hooks/pre-push    -> exige .git/judge-ok fresco (30 min) tras el OK del juez"
