#!/bin/bash

cd ../..

source .venv/bin/activate

all_locales="en ru"

for locale in $all_locales; do
    pybabel init \
    --input-file=./src/tgbot/locales/messages.pot \
    --output-dir=./src/tgbot/locales \
    --width=120 \
    --locale="$locale"
done

deactivate
