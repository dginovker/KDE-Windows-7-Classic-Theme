#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
x86_64-w64-mingw32-windres native-bench.rc -O coff -o native-bench-res.o
# Inbox DLLs keep the Windows oracle independent of runtime updates or borrowed DLLs.
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror -municode -mwindows -ffreestanding -fno-builtin -fno-stack-protector -nostdlib -Wl,-e,reference_entry native-bench.c native-bench-res.o -o native-bench.exe -luser32 -lgdi32 -lcomctl32 -luxtheme -lshell32 -lkernel32
python - <<'PY'
import re, subprocess
names=re.findall(r'DLL Name: (\S+)',subprocess.check_output(['x86_64-w64-mingw32-objdump','-p','native-bench.exe'],text=True))
assert set(n.lower() for n in names)=={'comctl32.dll','gdi32.dll','kernel32.dll','shell32.dll','user32.dll','uxtheme.dll'},names
print('Collector uses only inbox Windows 7 DLLs:',', '.join(names))
PY
