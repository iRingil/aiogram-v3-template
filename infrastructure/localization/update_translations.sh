#!/bin/bash

cd ../..

source .venv/bin/activate

all_locales="en ru"

for locale in $all_locales; do
    pybabel update \
    --input-file=./src/tgbot/locales/messages.pot \
    --output-dir=./src/tgbot/locales \
    --width=120 \
    --init-missing \
    --update-header-comment \
    --locale="$locale"
done

deactivate
