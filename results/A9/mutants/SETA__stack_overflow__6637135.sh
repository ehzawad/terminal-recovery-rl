#!/bin/bash
cd /opt/dslproject/scripts
sed -i '1s|.*|#!/bin/bash /usr/local/bin/dslrun|' greet.dsl math.dsl transform.dsl
sed -i '/^# This script/d' math.dsl
sed -i "s|^        \"\")     continue ;;|        \"\")     continue ;;\n        '#!'*)  continue ;;|" /usr/local/bin/dslrun
