#!/usr/bin/env bash
# Fetches every team service into ./services and installs dependencies.
# Run once: bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p services
S=services

fetch() {  # fetch <dir> <repo> [branch]
  [ -d "$S/$1/.git" ] && { git -C "$S/$1" pull -q; return; }
  git clone -q --depth 1 ${3:+-b "$3"} "https://github.com/$2.git" "$S/$1"
}

# Mayur: shared DB. Uses the integration branch until it is merged into main.
fetch shared-db "${MAYUR_REPO:-peeyusha06/referralops_demo}" "${MAYUR_BRANCH:-integration/matrix360-platform}"
# Peeyusha: Demand Radar
fetch radar peeyusha06/matrix360-demand-radar
# Avinash, Tanmayi and Pratha publish their code as zip files.
fetch _avinash AvinashWasHere21/interchangeable-chatbot
fetch _tanmayi tanmayi1005/matrix
fetch _pratha  pratha-source/Matrix-360
rm -rf $S/chat $S/engage $S/qualifier
unzip -q -o $S/_avinash/Matrix360dayonechatbot.zip -d $S/_avinash/x && mv $S/_avinash/x/property-desk $S/chat
unzip -q -o $S/_tanmayi/matrix360.zip -d $S/_tanmayi/x && mv $S/_tanmayi/x/matrix360 $S/engage
unzip -q -o $S/_pratha/AI_Lead_Qualifier.zip -d $S/_pratha/x && mv $S/_pratha/x/AI_Lead_Qualifier $S/qualifier
rm -f $S/engage/.env   # never use a committed .env; start.sh sets the variables
# Shalini's site is not on GitHub yet. Copy it in if it sits next to this folder.
if [ -d ../shree-heights-main ]; then
  rm -rf $S/site && cp -R ../shree-heights-main $S/site && rm -rf $S/site/node_modules
  # One-line change so the form endpoint comes from the environment (see patches/).
  (cd $S/site && patch -s -p1 < ../../patches/shalini-chat-widget.patch)   # adds Avinash's chat widget
  sed -i.bak "s|^export const FORM_ENDPOINT = '';|export const FORM_ENDPOINT = import.meta.env.VITE_FORM_ENDPOINT \|\| '';|" $S/site/src/data/site.js && rm $S/site/src/data/site.js.bak
fi

python3 -m venv .venv
.venv/bin/pip install -q -r $S/shared-db/requirements.txt -r $S/chat/requirements.txt
(cd $S/engage && npm ci --silent)
[ -d $S/site ] && (cd $S/site && npm ci --silent) || true
echo "Setup done. Next: bash start.sh"
