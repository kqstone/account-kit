#!/usr/bin/env bash
# Bundles the demo pages: open dist/react.html?page=login|register|reset|admin[&native] (same for vue.html).
set -euo pipefail
cd "$(dirname "$0")"
ES=../../packages/account-ui-react/node_modules/.bin/esbuild
mkdir -p dist
NODE_PATH=../../packages/account-ui-react/node_modules $ES react.tsx --bundle --format=iife --jsx=automatic --outfile=dist/react.js --define:process.env.NODE_ENV='"production"' --log-level=warning
NODE_PATH=../../packages/account-ui-vue/node_modules $ES vue.ts --bundle --format=iife --outfile=dist/vue.js --define:process.env.NODE_ENV='"production"' --define:__VUE_OPTIONS_API__=true --define:__VUE_PROD_DEVTOOLS__=false --define:__VUE_PROD_HYDRATION_MISMATCH_DETAILS__=false --log-level=warning
sed 's/APP/react/' index.html > dist/react.html
sed 's/APP/vue/' index.html > dist/vue.html
